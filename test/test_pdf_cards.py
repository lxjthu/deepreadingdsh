import json
import threading
import time
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

import test_pdf_viewer
from server import Store, Handler, ThreadingHTTPServer
import pdf_cards

CARD = {'title': '研究卡片', 'summary': '依据选段生成的摘要', 'tags': ['研究', '证据'],
        'body_markdown': '## 核心观点\n研究\n## 依据/证据\n原文\n## 阅读笔记\n笔记\n## 启发或用途\n待验证'}


class PdfCardsTests(unittest.TestCase):
    setUp = test_pdf_viewer.PdfViewerTests.setUp
    tearDown = test_pdf_viewer.PdfViewerTests.tearDown
    _second_paper = test_pdf_viewer.PdfViewerTests._second_paper

    def payload(self):
        return {'entry_id': self.entry, 'source_sha256': pdf_cards.fingerprint(self.pdf),
                'segments': [{'page': 1, 'start_word': 0, 'end_word': 2, 'start_offset': 1, 'end_offset': 4}]}

    def test_source_positions_multipage_and_rejections(self):
        body = self.payload()
        body['segments'].append({'page': 2, 'start_word': 0, 'end_word': 1})
        value = pdf_cards.selection(self.store, body)
        self.assertEqual(value['selected_text'], 'age 1 rese\n\nPage 2')
        self.assertEqual([s['page'] for s in value['segments']], [1, 2])
        self.assertTrue(value['segments'][0]['rects'])
        self.assertIn('text', value['context_after'])
        for change in [{'source_sha256': 'stale'}, {'segments': [{'page': 99, 'start_word': 0, 'end_word': 1}]},
                       {'segments': [{'page': 1, 'start_word': -1, 'end_word': 1}]}, {'segments': []},
                       {'segments': [{'page': 1, 'start_word': 0, 'end_word': 0, 'start_offset': 3, 'end_offset': 2}]}]:
            with self.subTest(change=change), self.assertRaises(ValueError):
                pdf_cards.selection(self.store, {**body, **change})

    def test_deduplicate_generate_edit_export_and_reopen(self):
        first = pdf_cards.enqueue(self.store, self.payload())
        second = pdf_cards.enqueue(self.store, self.payload())
        self.assertEqual(first['id'], second['id'])
        self.assertTrue(second['duplicate'])
        self.store.update(first['id'], status='running')
        with patch.object(self.store, 'model_call', return_value={'content': json.dumps(CARD)}):
            result = self.store.run_task(self.store.task(first['id']))
        self.store.update(first['id'], status='completed')
        listing = pdf_cards.listing(self.store, self.entry)
        card = listing['items'][0]
        self.assertEqual(card['selected_text'], 'age 1 rese')
        self.assertEqual(card['id'], result['card_id'])
        self.assertTrue(card['source_current'])
        self.assertIn('source_sha256:', card['markdown'])
        self.assertIn('pdf_positions:', card['markdown'])
        self.assertIn('[[', card['markdown'])
        self.assertEqual(card['segments'][0]['start_word'], 0)
        pdf_cards.operation(self.store, {'op': 'edit', 'entry_id': self.entry, 'id': card['id'], **CARD, 'title': '已编辑'})
        reopened = Store(self.home)
        self.assertEqual(pdf_cards.listing(reopened, self.entry)['items'][0]['title'], '已编辑')
        self.assertTrue((self.home/'backups/before-pdf-cards.sqlite3').is_file())
        with self.assertRaises(ValueError):
            pdf_cards.operation(self.store, {'op': 'edit', 'entry_id': self.other, 'id': card['id'], **CARD})

    def test_cancel_late_result_and_changed_pdf_do_not_save(self):
        created = pdf_cards.enqueue(self.store, self.payload())
        self.store.update(created['id'], status='running')
        def cancelled(*args):
            self.store.cancel(created['id'])
            return {'content': json.dumps(CARD)}
        with patch.object(self.store, 'model_call', side_effect=cancelled), self.assertRaises(InterruptedError):
            self.store.run_task(self.store.task(created['id']))
        self.assertEqual(pdf_cards.listing(self.store, self.entry)['items'], [])
        pdf_cards.operation(self.store, {'op': 'retry', 'entry_id': self.entry, 'id': created['id']})
        self.assertEqual(self.store.task(created['id'])['status'], 'queued')
        self.store.update(created['id'], status='running')
        def changed(*args):
            with self.pdf.open('ab') as file: file.write(b'\n')
            return {'content': json.dumps(CARD)}
        with patch.object(self.store, 'model_call', side_effect=changed), self.assertRaisesRegex(ValueError, '变化'):
            self.store.run_task(self.store.task(created['id']))
        self.assertEqual(self.store.rows('SELECT id FROM pdf_cards'), [])
        with self.assertRaises(ValueError): pdf_cards.validate_content({**CARD, 'body_markdown': '缺少四节'})

    def test_reader_authorization_is_entry_and_route_scoped(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        server.store, server.token = self.store, 'internal-secret'
        server.base = 'http://127.0.0.1:%d' % server.server_address[1]
        threading.Thread(target=server.serve_forever, daemon=True).start()
        def request(path, token, body=None, origin=None):
            headers = {'X-Reading-Token': token, 'Content-Type': 'application/json'}
            if origin: headers['Origin'] = origin
            return urllib.request.urlopen(urllib.request.Request(server.base + path, headers=headers,
                data=json.dumps(body).encode() if body is not None else None))
        try:
            session = json.load(request('/api/pdf/session', 'internal-secret', {'entry_id': self.entry}))
            token = session['url'].split('&token=')[1]
            self.assertNotIn('internal-secret', session['url'])
            self.assertEqual(json.load(request('/api/pdf/meta?entry_id='+self.entry, token))['page_count'], 2)
            self.assertTrue(request('/api/pdf/raw?entry_id='+self.entry, token).read().startswith(b'%PDF'))
            task = json.load(request('/api/cards', token, self.payload()))
            self.assertTrue(task['id'])
            for page in ('/card','/card.js','/card.css'):
                self.assertTrue(request(page, token).read())
            batch = json.load(request('/api/cards/batch', token, {'entry_id':self.entry,'annotation_ids':['missing']}))
            self.assertEqual(len(batch['errors']),1)
            self.assertEqual(json.load(request('/api/visuals?entry_id='+self.entry,token))['items'],[])
            for path, body in [('/bridge/next', None), ('/api/state', None), ('/api/file?path=topics.sqlite3', None),
                               ('/bridge/notes/status',None),('/bridge/notes/configure',{'path':'C:/untrusted'}),
                               ('/api/visuals?entry_id='+self.other,None),
                               ('/api/visual/image?entry_id='+self.other+'&id=missing',None),
                               ('/api/cards/visual',{'entry_id':self.other,'annotation_ids':['missing']}),
                               ('/api/cards?entry_id='+self.other, None), ('/api/cards', {**self.payload(), 'entry_id': self.other}),
                               ('/api/cards/batch', {'entry_id':self.other,'annotation_ids':['missing']}),
                               ('/api/cards/render', {'entry_id':self.other,'id':'missing','text':'正文'}),
                               ('/api/pdf/session', {'entry_id': self.entry})]:
                with self.subTest(path=path), self.assertRaises(urllib.error.HTTPError) as caught:
                    request(path, token, body)
                self.assertEqual(caught.exception.code, 403)
            with self.assertRaises(urllib.error.HTTPError):
                request('/api/cards', token, self.payload(), 'https://untrusted.example')
            self.store.reader_sessions[token]['expires'] = time.monotonic() - 1
            with self.assertRaises(urllib.error.HTTPError): request('/api/cards?entry_id='+self.entry, token)
        finally:
            server.shutdown(); server.server_close()

    def highlight(self, page=1):
        payload=self.payload()
        payload['segments'][0]['page']=page
        source=pdf_cards.selection(self.store,payload)
        return self.store.update_annotation({'entry_id':self.entry,'op':'create','item':{
            'kind':'highlight','page':page,'color':'yellow','quote':source['selected_text'],
            'rects':source['segments'][0]['rects'],'segments':payload['segments'],'source_sha256':payload['source_sha256']}})['items'][-1]

    def test_batch_highlights_queue_once_and_report_individual_failures(self):
        first, second = self.highlight(1), self.highlight(2)
        changed=self.store.update_annotation({'entry_id':self.entry,'op':'update','item':{'id':first['id'],'note':'笔记'}})['items'][0]
        self.assertEqual(changed['segments'],first['segments'])
        self.assertEqual(changed['source_sha256'],first['source_sha256'])
        payload={'entry_id':self.entry,'annotation_ids':[first['id'],second['id'],'missing',first['id']]}
        result=pdf_cards.enqueue_batch(self.store,payload)
        self.assertEqual(len(result['items']),2)
        self.assertEqual(len(result['errors']),1)
        self.assertEqual(len(self.store.rows("SELECT id FROM tasks WHERE task='pdf.card'")),2)
        repeated=pdf_cards.enqueue_batch(self.store,payload)
        self.assertTrue(all(item['duplicate'] for item in repeated['items']))
        with self.pdf.open('ab') as file:file.write(b'\n')
        stale=pdf_cards.enqueue_batch(self.store,{'entry_id':self.entry,'annotation_ids':[first['id']]})
        self.assertEqual(len(stale['errors']),1)
        self.assertIn('变化',stale['errors'][0]['error'])
        with self.assertRaises(ValueError):pdf_cards.enqueue_batch(self.store,{'entry_id':self.entry,'annotation_ids':[]})

    def test_legacy_highlight_requires_matching_text_and_geometry(self):
        legacy=self.highlight()
        legacy.pop('segments');legacy.pop('source_sha256')
        source=pdf_cards.annotation_selection(self.store,self.entry,legacy)
        self.assertEqual(source['selected_text'],'age 1 rese')
        with self.assertRaisesRegex(ValueError,'唯一定位'):
            pdf_cards.annotation_selection(self.store,self.entry,{**legacy,'rects':[[.8,.8,.9,.9]]})
        with self.assertRaises(ValueError):
            pdf_cards.annotation_selection(self.store,self.entry,{**legacy,'quote':'不存在的原句'})

    def make_card(self):
        task=pdf_cards.enqueue(self.store,self.payload())
        self.store.update(task['id'],status='running')
        with patch.object(self.store,'model_call',return_value={'content':json.dumps(CARD)}):
            self.store.run_task(self.store.task(task['id']))
        self.store.update(task['id'],status='completed')
        return pdf_cards.listing(self.store,self.entry)['items'][0]

    def test_bibliography_snapshot_export_and_legacy_backfill(self):
        entry=self.store.entry(self.entry)
        entry['metadata']={**entry.get('metadata',{}),'authors':['作者甲','作者乙'],'year':2026,'journal':'研究期刊','volume':'8','issue':'2','pages':'53–65','doi':'10.1234/test'}
        self.store.workspace.update(entry)
        card=self.make_card()
        self.assertEqual(card['paper_metadata']['authors'],['作者甲','作者乙'])
        self.assertEqual(card['paper_metadata']['year'],2026)
        self.assertIn('研究期刊',card['paper_citation'])
        self.assertIn('paper_metadata:',card['markdown'])
        self.assertIn('10.1234/test',card['markdown'])
        entry['metadata']['journal']='新期刊';self.store.workspace.update(entry)
        self.assertEqual(pdf_cards.listing(self.store,self.entry)['items'][0]['paper_metadata']['journal'],'研究期刊')
        legacy={key:value for key,value in card.items() if key not in ('paper_metadata','paper_citation','paper_metadata_origin')}
        with self.store.db() as db:db.execute('UPDATE pdf_cards SET payload=? WHERE id=?',(json.dumps(legacy),card['id']))
        fallback=pdf_cards.listing(self.store,self.entry)['items'][0]
        self.assertEqual(fallback['paper_metadata_origin'],'current_library')
        self.assertEqual(fallback['paper_metadata']['journal'],'新期刊')
        pdf_cards.operation(self.store,{'op':'edit','entry_id':self.entry,'id':card['id'],**CARD})
        self.assertEqual(pdf_cards.listing(self.store,self.entry)['items'][0]['paper_metadata_origin'],'legacy_backfill')

    def test_editor_rejects_stale_save_and_sanitizes_markdown(self):
        card=self.make_card()
        request={'op':'edit','entry_id':self.entry,'id':card['id'],**CARD,'expected_updated':card['updated']}
        pdf_cards.operation(self.store,request)
        with self.assertRaisesRegex(ValueError,'其他窗口'):
            pdf_cards.operation(self.store,request)
        rendered=pdf_cards.render_card(self.store,{'entry_id':self.entry,'id':card['id'],'text':'## 预览\n<script>alert(1)</script><img src="https://example.com/a.png"><b>正文</b>'})
        self.assertIn('<h2',rendered['html'])
        self.assertNotIn('<script',rendered['html'])
        self.assertNotIn('src="https://example.com',rendered['html'])
        with self.assertRaises(ValueError):
            pdf_cards.render_card(self.store,{'entry_id':self.other,'id':card['id'],'text':'正文'})

    def test_combined_same_page_creates_one_card_and_is_order_independent(self):
        first=self.highlight()
        payload=self.payload();payload['segments']=[{'page':1,'start_word':3,'end_word':3}]
        source=pdf_cards.selection(self.store,payload)
        second=self.store.update_annotation({'entry_id':self.entry,'op':'create','item':{
            'kind':'highlight','page':1,'color':'yellow','quote':source['selected_text'],'rects':source['segments'][0]['rects'],
            'segments':source['segments'],'source_sha256':source['source_sha256']}})['items'][-1]
        body={'entry_id':self.entry,'annotation_ids':[second['id'],first['id']],'generation_mode':'combined'}
        result=pdf_cards.enqueue_batch(self.store,body)
        self.assertEqual(result['errors'],[])
        self.assertEqual(len({item['id'] for item in result['items']}),1)
        task_id=result['items'][0]['id']
        repeated=pdf_cards.enqueue_batch(self.store,{**body,'annotation_ids':list(reversed(body['annotation_ids']))})
        self.assertEqual(repeated['items'][0]['id'],task_id)
        self.assertTrue(all(item['duplicate'] for item in repeated['items']))
        separate=pdf_cards.enqueue_batch(self.store,{**body,'generation_mode':'separate'})
        self.assertEqual(len({item['id'] for item in separate['items']}),2)
        self.assertNotIn(task_id,[item['id'] for item in separate['items']])
        self.store.update(task_id,status='running')
        with patch.object(self.store,'model_call',return_value={'content':json.dumps(CARD)}) as model:
            self.store.run_task(self.store.task(task_id))
        self.assertEqual(model.call_count,1)
        self.assertIn('不一定连续',model.call_args[0][1][1]['content'])
        card=pdf_cards.listing(self.store,self.entry)['items'][0]
        self.assertEqual(card['generation_mode'],'combined')
        self.assertEqual(len(card['selection_parts']),2)
        self.assertEqual(card['selection_parts'][1]['selected_text'],'text')
        self.assertEqual([segment['page'] for segment in card['segments']],[1,1])
        self.assertIn('选段 2',card['selected_text'])
        self.assertIn('选段 2 的上下文',card['markdown'])
        self.assertIn('generation_mode: "combined"',card['markdown'])

    def test_combined_can_use_nonadjacent_pages(self):
        self.pdf.unlink();test_pdf_viewer.make_pdf(self.pdf,3)
        first,third=self.highlight(1),self.highlight(3)
        result=pdf_cards.enqueue_batch(self.store,{'entry_id':self.entry,'annotation_ids':[third['id'],first['id']],'generation_mode':'combined'})
        self.assertEqual(result['errors'],[])
        params=json.loads(self.store.task(result['items'][0]['id'])['params'])
        self.assertEqual([segment['page'] for segment in params['segments']],[1,3])
        self.assertEqual(len(params['selection_parts']),2)
        with self.pdf.open('ab') as file:file.write(b'\n')
        with patch.object(self.store,'model_call') as model,self.assertRaisesRegex(ValueError,'变化'):
            self.store.run_task(self.store.task(result['items'][0]['id']))
        model.assert_not_called()

    def test_combined_invalid_highlight_submits_nothing_and_rejects_unknown_mode(self):
        first=self.highlight()
        result=pdf_cards.enqueue_batch(self.store,{'entry_id':self.entry,'annotation_ids':[first['id'],'missing'],'generation_mode':'combined'})
        self.assertEqual(result['generation_mode'],'combined')
        self.assertEqual(result['items'],[])
        self.assertEqual(len(result['errors']),1)
        self.assertEqual(self.store.rows("SELECT id FROM tasks WHERE task='pdf.card'"),[])
        with self.assertRaisesRegex(ValueError,'生成方式'):
            pdf_cards.enqueue_batch(self.store,{'entry_id':self.entry,'annotation_ids':[first['id']],'generation_mode':'invalid'})


if __name__ == '__main__': unittest.main()
