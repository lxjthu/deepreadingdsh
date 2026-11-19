import io
import copy
import json
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
import urllib.error
import zipfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from server import Store, Handler, ThreadingHTTPServer, restore_archive, TASKS, ROOT, instance_lock, pid_alive
from dra_core.prompt_loader import PromptLoader
from dra_core.pipeline import prepare


PAPER='''# 数字化与企业生产率

## 摘要
数字化转型提高企业生产率。数字化通过信息共享促进企业生产率。本文使用面板数据和固定效应识别策略，理论基础是资源基础观。指标采用软件投入比例测量。研究情境为制造业，存在内生性和测量误差。

## 方法
The resource-based theory explains how digitalization improves productivity through information sharing. Panel data cover manufacturing firms. Fixed effects models measure productivity. Institutional context and measurement error require further checks.
'''


class WorkbenchTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.home=Path(self.tmp.name)/'research'
        self.store=Store(self.home)
        self.t1=self.store.create_topic('数字化')['id']
        self.t2=self.store.create_topic('企业效率')['id']
        self.paper=Path(self.tmp.name)/'paper.md'
        self.paper.write_text(PAPER,encoding='utf-8')
        result=self.store.import_file({'topic_id':self.t1,'path':str(self.paper)},'test')
        self.entry=result['entry_ids'][0]
    def tearDown(self):
        self.store.stop.set()
        self.tmp.cleanup()

    def new(self,task='read.quant',**extra):
        return self.store.new_task({'topic_id':self.t1,'task':task,'entry_ids':[self.entry],**extra})['id']

    def test_shared_document_dedup_and_topic_isolation(self):
        self.store.import_file({'topic_id':self.t2,'path':str(self.paper)},'test')
        state=self.store.state()
        self.assertEqual(len(state['documents']),1)
        self.assertEqual(len(state['links']),2)
        t3=self.store.create_topic('空主题')['id']
        with self.assertRaisesRegex(ValueError,'不属于'):
            self.store.new_task({'topic_id':t3,'task':'qa','entry_ids':[self.entry],'question':'解释机制'})
        self.assertEqual(self.paper.read_text(encoding='utf-8'),PAPER)

    def test_model_broker_lease_and_cancel(self):
        task=self.new()
        self.store.update(task,status='running')
        result=[]
        thread=threading.Thread(target=lambda:result.append(self.store.model_call(task,[{'role':'user','content':'test'}])))
        thread.start()
        for _ in range(30):
            req=self.store.next_call()['request']
            if req:break
            time.sleep(.03)
        with self.assertRaisesRegex(ValueError,'Stale'):
            self.store.answer_call({'id':req['id'],'lease':'wrong'})
        self.store.answer_call({'id':req['id'],'lease':req['lease'],'content':'完整回答','finish_reason':'stop'})
        thread.join(2)
        self.assertEqual(result[0]['content'],'完整回答')
        with self.assertRaisesRegex(ValueError,'Stale'):
            self.store.answer_call({'id':req['id'],'lease':req['lease']})
        self.store.cancel(task)
        self.store.resume(task)
        self.assertEqual(self.store.task(task)['status'],'queued')

    def test_checkpoint_resume_keeps_finished_steps(self):
        task=self.new()
        self.store.update(task,status='running')
        calls=[]
        def broken(*args):
            calls.append(1)
            if len(calls)==2:raise RuntimeError('simulated quota')
            return {'content':'理论分析与证据。','finish_reason':'stop','reported_model':'test/model','usage':{'inputTokens':17,'outputTokens':8}}
        with patch.object(self.store,'model_call',side_effect=broken):
            with self.assertRaisesRegex(RuntimeError,'simulated quota'):self.store.run_task(self.store.task(task))
        saved=list((self.store.workspace.root/'runs'/f'{task}-0').glob('step-*.json'))
        self.assertEqual(len(saved),1)
        self.assertEqual(json.loads(saved[0].read_text(encoding='utf-8'))['usage'],{'inputTokens':17,'outputTokens':8})
        resumed=[]
        def answer(*args):
            resumed.append(1)
            return {'content':'继续分析。','finish_reason':'stop','reported_model':'test/model'}
        with patch.object(self.store,'model_call',side_effect=answer):
            result=self.store.run_task(self.store.task(task))
        self.assertEqual(result['runs'][0]['status'],'completed')
        total_steps=len(json.loads((self.store.workspace.root/'runs'/f'{task}-0'/'plan.json').read_text(encoding='utf-8'))['steps'])
        self.assertEqual(len(resumed),total_steps-1)
        self.assertTrue(self.store.workspace.path(result['artifacts'][0]['path']).exists())

    def test_idea_lab_evidence_and_continuation(self):
        task=self.new('idea-lab')
        result=self.store.run_task(self.store.task(task))
        self.assertTrue(result['constructs'])
        self.assertTrue(result['ideas'])
        evidence=result['constructs'][0]['evidence'][0]
        self.assertEqual(evidence['source_tier'],'P0')
        self.assertIn(evidence['quote'],PAPER)
        self.store.update(task,status='completed',result=json.dumps(result,ensure_ascii=False))
        task2=self.new('idea-lab.deepen',question='沿用构念提出识别策略')
        calls=[]
        def capture(_,messages):
            calls.append(messages)
            return {'content':'候选识别方案，需核验。','finish_reason':'stop','reported_model':'test/model'}
        with patch.object(self.store,'model_call',side_effect=capture):
            second=self.store.run_task(self.store.task(task2))
        self.assertTrue(json.loads(calls[0][1]['content'])['previous_result'])
        self.assertIn('候选',second['analysis'])

    def test_six_gap_types_without_inventing_relationship(self):
        from idea_lab import run_idea_lab_pipeline
        r=run_idea_lab_pipeline(evidence_pack={'entries':[{'entry_id':'e1','title':'T','evidence':[{'quote':'A descriptive passage with no identified relationship.','source_tier':'P0','source_kind':'source_window'}]}]},topic='topic')
        self.assertEqual(len(r['gaps']),6)
        self.assertEqual(r['ideas'][0]['hypotheses'],[])

    def test_restart_and_backup_restore(self):
        task=self.new()
        self.store.update(task,status='running')
        fresh=Store(self.home)
        self.assertEqual(fresh.task(task)['status'],'interrupted')
        archive=fresh.backup()['path']
        restored=Path(self.tmp.name)/'restored'
        restore_archive(archive,restored)
        recovered=Store(restored)
        self.assertEqual(len(recovered.state()['topics']),2)
        self.assertEqual(recovered.workspace.entries()[0]['entry_id'],self.entry)
        self.assertEqual(len(recovered.state()['links']),1)
        with self.assertRaises(ValueError):restore_archive(archive,restored)

    def test_zip_traversal_rejected(self):
        path=Path(self.tmp.name)/'malicious.zip'
        with zipfile.ZipFile(path,'w') as z:
            z.writestr('manifest.json',json.dumps({'format':'dsh-deep-reading','version':1}))
            z.writestr('../escape','bad')
        with self.assertRaisesRegex(ValueError,'Unsafe'):restore_archive(path,Path(self.tmp.name)/'restore')

    def test_every_exposed_workflow_binds_prompts(self):
        docs=self.store.documents({'topic_id':self.t1,'entry_ids':[self.entry]})
        docs[0]['metadata']['abstract']='This paper examines digitalization and productivity.'
        # Different workflows need different explicit input variables.
        variables={'rules':'GB/T 7714', 'selection':'数字化转型提高企业生产率。'}
        loader=PromptLoader(self.store.workspace.root)
        for task in TASKS:
            if task in ('import','idea-lab','idea-lab.deepen','wiki.extract','pdf.card'):continue
            with self.subTest(task=task):
                current=copy.deepcopy(docs)
                if task in ('compare','synthesize','writing-style.batch'):
                    other=copy.deepcopy(docs[0]);other['entry_id']='second-paper';other['title']='另一篇研究';current.append(other)
                plan=prepare(task,current,{'question':'解释机制','topic':'数字化','variables':variables},loader)
                self.assertTrue(plan['steps'])
                self.assertTrue(plan['prompts'])

    def test_http_access_and_path_boundaries(self):
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        server.store,server.token=self.store,'test-secret'
        server.base=f'http://127.0.0.1:{server.server_address[1]}'
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        def request(path,origin=None):
            headers={'X-Reading-Token':'test-secret'}
            if origin:headers['Origin']=origin
            return urllib.request.urlopen(urllib.request.Request(server.base+path,headers=headers))
        try:
            with self.assertRaises(urllib.error.HTTPError):urllib.request.urlopen(server.base+'/api/state')
            with self.assertRaises(urllib.error.HTTPError):request('/api/state','http://evil.example')
            with self.assertRaises(urllib.error.HTTPError):request('/api/file?path=../topics.sqlite3')
            self.assertEqual(json.load(request('/api/state'))['topics'][0]['name'],'数字化')
            slots=json.load(request('/api/prompts'))['slots']
            self.assertTrue(slots)
            self.assertTrue(json.load(request('/api/prompt?slot='+slots[0]))['text'])
        finally:server.shutdown();server.server_close()

    def test_single_instance_lock_and_sanitized_render(self):
        import os
        from dra_core.reader_render import render
        self.assertTrue(pid_alive(os.getpid()))
        with instance_lock(self.home):
            with self.assertRaisesRegex(RuntimeError,'已有工作台'): 
                with instance_lock(self.home): pass
        self.assertFalse((self.home/'.service.lock').exists())
        html=render('# Test\n\n<script>alert(1)</script>\n\n[bad](javascript:alert(1))')['html']
        self.assertNotIn('<script',html)
        self.assertNotIn('javascript:',html)


if __name__=='__main__':unittest.main()
