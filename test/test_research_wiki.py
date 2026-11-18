"""Isolated fixtures, never write synthetic papers into the installed library."""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from server import Store, restore_archive
from research_wiki import dump, locate_segment_evidence


class WikiTests(unittest.TestCase):
    def test_one_validation_repair_preserves_strict_rejection_and_checkpoints(self):
        params={'topic_id':self.topic,'task':'wiki.extract','entry_ids':[self.ids[0]]}
        task=self.s.new_task(params)['id'];self.s.update(task,status='running')
        bad={'content':dump({'records':[self.body(evidence=[{'quote':'伪造的引文'}])]})}
        good={'content':dump({'records':[self.body()]})}
        with patch.object(self.s,'model_call',side_effect=[bad,good]) as call:
            result=self.w.extract(params,task)
            self.assertEqual(call.call_count,2)
            self.assertEqual([m['role'] for m in call.call_args.args[1]],['system','user','assistant','user'])
            self.assertIn('伪造的引文',call.call_args.args[1][-1]['content'])
        self.assertEqual(result['chunks'],1)
        self.assertEqual(len(self.s.rows('SELECT * FROM wiki_checkpoints')),1)
        with self.s.db() as db:db.execute('DELETE FROM wiki_checkpoints')
        with patch.object(self.s,'model_call',side_effect=[bad,bad]) as call:
            with self.assertRaisesRegex(ValueError,'证据不在当前正文分段'):self.w.extract(params,task)
            self.assertEqual(call.call_count,2)
        self.assertEqual(self.s.rows('SELECT * FROM wiki_checkpoints'),[])

    def test_pdf_line_wrapping_retains_the_exact_source_and_model_quote(self):
        text='前言。采用资源\n  基础观解释企业行为。'
        value={'quote':'采用资源基础观解释企业行为。'}
        locate_segment_evidence(value,text,100,'paper')
        self.assertEqual(value['quote'],text[3:])
        self.assertEqual(value['model_quote'],'采用资源基础观解释企业行为。')
        self.assertEqual(value['match_method'],'whitespace_only')
        self.assertEqual((value['start'],value['end']),(103,100+len(text)))
        source=self.w.source(self.ids[0])
        evidence={'quote':'本文采用资源基础观，使用CFPS2020数据。'}
        locate_segment_evidence(evidence,source['text'],0,self.ids[0])
        proposal=self.propose(self.body(evidence=[evidence]))
        saved=self.detail(proposal)['records'][0]['body']['evidence'][0]
        self.assertEqual(source['text'][saved['start']:saved['end']],saved['quote'])
        self.assertEqual(saved['model_quote'],evidence['model_quote'])
        self.assertEqual(saved['match_method'],'whitespace_only')

    def test_missing_ambiguous_and_incorrectly_positioned_quotes_still_fail(self):
        for value,text in [({'quote':'采用不存在理论'},'采用资源\n基础观'),({'quote':'资源基础观'},'资源\n基础观。资源 基础观'),({'quote':'资源基础观','start':0,'end':5},'资源\n基础观')]:
            with self.assertRaises(ValueError):locate_segment_evidence(value,text,0,'paper')
        with self.assertRaises(ValueError):self.propose(self.body(evidence=[{'quote':'本文采用资源基础观','model_quote':'使用不存在理论','match_method':'whitespace_only'}]))

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name)
        self.s=Store(self.root/'home'); self.w=self.s.wiki
        self.topic=self.s.create_topic('研究 Wiki 测试')['id']; self.ids=[]
        for n in range(2):
            p=self.root/f'paper{n}.md'
            p.write_text(f'# 独立论文 {n}\n\n本文采用资源基础观，使用CFPS 2020数据。数字化采用投入比例测量。\n另一种方法仅在综述提及。信度0.8属于本研究。\n',encoding='utf-8')
            self.ids.append(self.s.import_file({'path':str(p),'topic_id':self.topic},'test')['entry_ids'][0])

    def tearDown(self): self.s.stop.set(); self.tmp.cleanup()
    def body(self, kind='theory',name='资源基础观',relation='adopts',**kw):
        return {'kind':kind,'name':name,'relation':relation,'details':{},'evidence':[{'quote':'本文采用资源基础观，使用CFPS 2020数据。'}],**kw}
    def propose(self, body=None,index=0): return self.w.propose(self.ids[index],body or self.body())
    def detail(self,r): return self.w.detail(r['entity_id'])
    def confirm(self,r):
        d=self.detail(r); c=d['candidates'][-1]
        if c['stale']:c=self.w.rebase(c['id'])
        self.w.review([{'id':c['id'],'hash':c['hash']}]);return self.detail(r)

    def test_shared_theory_and_dataset_and_topic_views(self):
        for body in [self.body(),self.body('dataset','CFPS','uses',details={'years':'2020','sample':'制造业子样本'})]:
            a=self.propose(body);b=self.propose(body,1);self.assertEqual(a['entity_id'],b['entity_id'])
            self.assertEqual(len(self.detail(a)['records']),2)
        other=self.s.create_topic('另一主题')['id'];self.s.link(other,self.ids[0])
        self.assertEqual(self.w.listing({'topic_id':other})['total'],2)

    def test_same_name_authors_not_merged(self):
        b=self.body('author','张伟','cites')
        self.assertNotEqual(self.propose(b)['entity_id'],self.propose(b,1)['entity_id'])
    def test_reliable_author_identifier_and_conflict(self):
        b=self.body('author','张伟','cites',identity={'orcid':'0000-0001'})
        a=self.propose(b); self.assertEqual(a['entity_id'],self.propose(b,1)['entity_id'])
        b['identity']['orcid']='0000-0002';self.assertNotEqual(a['entity_id'],self.propose(b,1)['entity_id'])
    def test_alias_review_and_explicit_relink(self):
        a=self.propose();self.confirm(a)
        b=self.propose(self.body(name='Resource Based View',aliases=['资源基础观']),1)
        self.assertEqual(a['entity_id'],b['entity_id'])
        c=self.detail(b)['candidates'][0]
        new=self.w.relink({'id':c['id'],'hash':c['hash'],'target':''})
        self.assertNotEqual(new['target'],a['entity_id'])
        c=self.w.relink({'id':new['id'],'hash':new['hash'],'target':a['entity_id']})
        self.w.review([{'id':c['id'],'hash':c['hash']}])
        self.assertIn('Resource Based View',self.detail(a)['entity']['aliases'])
    def test_variable_roles_and_operationalizations_are_paper_scoped(self):
        a=self.propose(self.body('variable','数字化','measures',details={'role':'自变量','operationalization':'投入比例'}))
        b=self.propose(self.body('variable','数字化','measures',details={'role':'中介变量','operationalization':'词频'}),1)
        self.assertEqual(a['entity_id'],b['entity_id'])
        d=self.detail(a);self.assertEqual([r['body']['details']['role'] for r in d['records']],['自变量','中介变量'])
        self.assertNotIn('role',d['entity']['identity'])
    def test_scale_versions_and_case_boundaries_are_separate(self):
        for kind,relation,key in [('scale','uses','version'),('case','studies','boundary')]:
            a=self.propose(self.body(kind,'同名实体',relation,identity={key:'原始'}))
            b=self.propose(self.body(kind,'同名实体',relation,identity={key:'修订'}))
            self.assertNotEqual(a['entity_id'],b['entity_id'])
    def test_mentions_remain_mentions(self):
        a=self.propose(self.body('method','固定效应','mentions'))
        self.assertEqual(self.confirm(a)['records'][0]['body']['relation'],'mentions')
    def test_evidence_quote_offsets_versions_and_bibliographic_boundary(self):
        for ev in [{'quote':'伪造原文'},{'quote':'本文采用','start':0,'end':4},{'quote':'本文采用','hash':'bad'}]:
            with self.assertRaises(ValueError):self.propose(self.body(evidence=[ev]))
        r=self.propose();ev=self.detail(r)['records'][0]['body']['evidence'][0]
        self.assertIsNone(ev['physical_page']);self.assertTrue(ev['version']);self.assertTrue(ev['hash'])
        s=self.w.source(self.ids[0],'bibliography')
        with self.assertRaises(ValueError):self.propose(self.body(evidence=[{'layer':'bibliography','quote':s['text']}]))
    def test_claims_and_typed_links_need_independent_evidence(self):
        with self.assertRaises(ValueError):self.propose(self.body(claims=[{'text':'定义'}]))
        r=self.propose(self.body(links=[{'kind':'variable','name':'数字化','relation':'theoretical_basis','evidence':[{'quote':'本文采用资源基础观'}]}]))
        self.assertEqual(len(self.detail(r)['records'][0]['body']['links']),1)
    def test_typed_link_stable_backlink_and_merge_redirect(self):
        v=self.propose(self.body('variable','数字化','measures'));self.confirm(v)
        t=self.propose(self.body(links=[{'kind':'variable','name':'数字化','relation':'theoretical_basis','evidence':[{'quote':'本文采用资源基础观'}]}]));self.confirm(t)
        link=self.detail(t)['records'][0]['body']['links'][0]
        self.assertEqual(link['entity_id'],v['entity_id'])
        self.assertEqual(self.detail(v)['backlinks'][0]['resolution'],'稳定实体关联')
        self.w.edit({'entity_id':v['entity_id'],'revision':1,'name':'数字化水平','aliases':[]})
        self.assertIn('数字化',self.detail(v)['entity']['aliases'])
        self.assertEqual(self.detail(v)['backlinks'][0]['entity_id'],t['entity_id'])
    def test_pending_history_restoration_remains_reviewable(self):
        r=self.propose();self.w.edit({'entity_id':r['entity_id'],'revision':0,'note':'待审核时的笔记'})
        h=self.detail(r)['history'][0];self.confirm(r)
        c=self.w.restore({'entity_id':r['entity_id'],'history_id':h['id']})
        self.w.review([{'id':c['id'],'hash':c['hash']}])
        d=self.detail(r);self.assertEqual(d['records'][0]['status'],'pending')
        self.assertEqual(len(d['candidates']),1);self.assertFalse(d['candidates'][0]['stale'])
    def test_idempotence_and_retracted_not_resurrected(self):
        r=self.propose();self.confirm(r)
        self.w.edit({'entity_id':r['entity_id'],'revision':1,'record_id':r['id'],'retract':True})
        self.assertTrue(self.propose()['unchanged']);self.assertEqual(self.detail(r)['records'][0]['status'],'retracted')
    def test_stale_hash_and_stale_page_refused(self):
        r=self.propose();c=self.detail(r)['candidates'][0]
        with self.assertRaises(ValueError):self.w.review([{'id':c['id'],'hash':'bad'}])
        self.w.edit({'entity_id':r['entity_id'],'revision':0,'note':'人工笔记保留'})
        with self.assertRaisesRegex(ValueError,'陈旧'):self.w.review([{'id':c['id'],'hash':c['hash']}])
        c=self.w.rebase(c['id']);self.w.review([{'id':c['id'],'hash':c['hash']}])
        self.assertEqual(self.detail(r)['entity']['note'],'人工笔记保留')
    def test_source_change_invalidates_candidate_and_context(self):
        r=self.propose();self.confirm(r)
        entry=self.s.workspace.get(self.ids[0]);md=self.s.workspace.path(entry['sources'][-1]['markdown'])
        md.write_text(md.read_text(encoding='utf-8')+'\n新修订',encoding='utf-8')
        self.assertTrue(self.detail(r)['records'][0]['stale']);self.assertEqual(self.w.context(self.ids),[])
        c=self.propose(index=1);candidate=self.detail(c)['candidates'][0]
        entry=self.s.workspace.get(self.ids[1]);md=self.s.workspace.path(entry['sources'][-1]['markdown']);md.write_text('原文已改变',encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'来源'):self.w.review([{'id':candidate['id'],'hash':candidate['hash']}])
    def test_manual_correction_survives_reextract(self):
        r=self.propose();d=self.confirm(r);b=copy.deepcopy(d['records'][0]['body']);b['relation']='discusses'
        self.w.edit({'entity_id':r['entity_id'],'revision':1,'record_id':r['id'],'body':b})
        self.propose();self.assertEqual(self.detail(r)['records'][0]['body']['relation'],'discusses')
    def test_atomic_batch_review(self):
        a=self.propose();b=self.propose(self.body('dataset','CFPS','uses'));ca=self.detail(a)['candidates'][0];cb=self.detail(b)['candidates'][0]
        with self.assertRaises(ValueError):self.w.review([{'id':ca['id'],'hash':ca['hash']},{'id':cb['id'],'hash':'bad'}])
        self.assertEqual(self.detail(a)['records'][0]['status'],'pending')
    def test_merge_undo_and_restore_consistency(self):
        a=self.propose(self.body('author','张伟','cites'));b=self.propose(self.body('author','张伟','cites'),1)
        self.confirm(a);self.confirm(b)
        mid=self.w.merge({'source':a['entity_id'],'target':b['entity_id'],'revisions':[1,1]})['id']
        self.assertEqual(len(self.detail(b)['records']),2);self.assertEqual(self.detail(a)['redirect'],b['entity_id'])
        self.w.undo_merge({'id':mid});self.assertEqual(len(self.detail(a)['records']),1);self.assertEqual(len(self.detail(b)['records']),1)
        d=self.detail(a);h=next(h for h in d['history'] if h['revision']==1)
        self.w.edit({'entity_id':a['entity_id'],'revision':d['entity']['revision'],'note':'新笔记'})
        c=self.w.restore({'entity_id':a['entity_id'],'history_id':h['id']})
        self.assertEqual(self.detail(a)['entity']['note'],'新笔记')
        self.w.review([{'id':c['id'],'hash':c['hash']}]);self.assertEqual(self.detail(a)['entity']['note'],'')
    def test_restart_migration_and_backup_restore(self):
        r=self.propose();self.confirm(r);restored=self.root/'restored'
        restore_archive(self.s.backup()['path'],restored);new=Store(restored)
        self.assertEqual(new.wiki.detail(r['entity_id'])['records'][0]['status'],'confirmed')
        again=Store(restored);self.assertEqual(again.wiki.listing({})['total'],1)
    def test_complete_match_search_beyond_fifty_and_pagination(self):
        for i in range(65): self.propose(self.body(name=f'理论{i}'))
        self.assertEqual(self.w.matches('theory','理论64')[0]['name'],'理论64')
        page=self.w.listing({'offset':'50','limit':'20'});self.assertEqual(len(page['items']),15);self.assertEqual(page['total'],65)
    def test_chunk_resume_cancel_failure_and_full_text(self):
        entry=self.s.workspace.get(self.ids[0]);md=self.s.workspace.path(entry['sources'][-1]['markdown']);md.write_text('正文\n'*12000+'\n附录关键变量',encoding='utf-8')
        task=self.s.new_task({'task':'wiki.extract','entry_ids':[self.ids[0]],'topic_id':self.topic})['id'];self.s.update(task,status='running')
        calls=[]
        def failing(_,messages):
            calls.append(messages)
            if len(calls)==2:raise RuntimeError('quota')
            return {'content':'{"records":[]}','finish_reason':'stop'}
        with patch.object(self.s,'model_call',side_effect=failing):
            with self.assertRaisesRegex(RuntimeError,'quota'):self.s.run_task(self.s.task(task))
        fresh=Store(self.s.home);self.assertEqual(fresh.task(task)['status'],'interrupted');fresh.resume(task);fresh.update(task,status='running')
        resumed=[]
        def answer(_,messages):resumed.append(json.loads(messages[1]['content']));return {'content':'{"records":[]}','finish_reason':'stop'}
        with patch.object(fresh,'model_call',side_effect=answer):fresh.run_task(fresh.task(task))
        self.assertEqual(resumed[0]['offset'],11000);self.assertIn('附录关键变量',resumed[-1]['text'])
        fresh.cancel(task)
        with self.assertRaises(InterruptedError):fresh.wiki.extract(json.loads(fresh.task(task)['params']),task)
    def test_model_extraction_validates_and_reuses_controlled_response(self):
        task=self.s.new_task({'task':'wiki.extract','entry_ids':[self.ids[0]],'topic_id':self.topic})['id'];self.s.update(task,status='running')
        with patch.object(self.s,'model_call',return_value={'content':dump({'records':[self.body()]}),'finish_reason':'stop'}) as model:
            r=self.s.run_task(self.s.task(task));self.assertEqual(r['new_records'],1)
            self.s.run_task(self.s.task(task));self.assertEqual(model.call_count,1)
        self.assertEqual(self.w.listing({})['total'],1)


if __name__=='__main__':unittest.main()
