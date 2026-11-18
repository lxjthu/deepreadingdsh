import json
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
import base64
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from server import Store, restore_archive, Handler, ThreadingHTTPServer
from library import matching_entry


class FolderLibraryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.store = Store(self.root/'data')
        self.topic = self.store.create_topic('数字农业')['id']
        self.folder = self.root/'中文 论文'
        (self.folder/'子目录').mkdir(parents=True)
        self.one = self.folder/'001.md'
        self.one.write_text('# 数字农业与农户收入的机制研究\n作者：张三；李四\n年份：2024\n期刊：农业经济\n关键词：数字农业；农户收入\n## 摘要\n数字农业通过市场信息改善农户收入。\n\n## 方法\n使用面板数据。', encoding='utf-8')

    def tearDown(self):
        self.store.stop.set()
        self.tmp.cleanup()

    def run_batch(self, **extra):
        task = self.store.new_task({'topic_id':self.topic,'task':'import','path':str(self.folder),'engine':'pymupdf',**extra})['id']
        self.store.update(task,status='running')
        return task, self.store.run_task(self.store.task(task))

    def test_recursive_dedup_metadata_and_attachments(self):
        copy = self.folder/'子目录'/'重复.md'
        copy.write_bytes(self.one.read_bytes())
        other = self.folder/'子目录'/'different.markdown'
        other.write_text(self.one.read_text(encoding='utf-8')+'\n完整附录。',encoding='utf-8')
        (self.folder/'notes.png').write_bytes(b'not a paper')
        task, result = self.run_batch()
        self.assertEqual(result['processed'],3)
        self.assertEqual(result['duplicates'],1)
        self.assertEqual(len(result['skipped']),1)
        library = self.store.state()['library']
        self.assertEqual(len(library),1)
        entry = library[0]
        self.assertEqual(entry['title'],'数字农业与农户收入的机制研究')
        self.assertEqual(entry['authors'],['张三','李四'])
        self.assertEqual(entry['year'],2024)
        self.assertEqual(entry['reading_status'],'has_pdf')
        self.assertEqual(entry['metadata_completeness'],'full')
        self.assertIn('数字农业',entry['tags'])
        self.assertEqual(len(entry['attachments']),2)
        self.assertEqual(len(self.store.state()['links']),1)
        self.assertTrue(all(self.store.workspace.path(a['path']).is_file() for a in entry['attachments']))
        self.assertEqual(self.one.read_bytes(),copy.read_bytes())
        self.assertEqual(self.store.documents({'topic_id':self.topic,'entry_ids':[entry['id']]})[0]['entry_id'],entry['id'])
        self.store.update(task,status='completed',result=json.dumps(result))
        _, repeated = self.run_batch()
        self.assertEqual(repeated['duplicates'],3)
        self.assertEqual(len(self.store.state()['library']),1)

    def test_partial_failure_resume_and_snapshot_paths(self):
        bad=self.folder/'bad.txt';bad.write_text('not CNKI or WoS',encoding='utf-8')
        task=self.store.new_task({'topic_id':self.topic,'task':'import','path':str(self.folder)})['id']
        self.store.update(task,status='running')
        with self.assertRaisesRegex(ValueError,'导入失败'):self.store.run_task(self.store.task(task))
        progress=json.loads(self.store.task(task)['result'])
        self.assertEqual(progress['failed'],1)
        self.assertEqual(len(self.store.workspace.entries()),1)
        bad.write_text('SrcDatabase-来源库: 期刊\nTitle-题名: 新的农业研究\nAuthor-作者: 王五\nYear-年: 2023\n',encoding='utf-8')
        extra=self.folder/'not-in-snapshot.md';extra.write_text('# 后来加入的文件',encoding='utf-8')
        result=self.store.run_task(self.store.task(task))
        self.assertEqual(result['failed'],0)
        self.assertEqual(result['total'],2)
        self.assertEqual(len(self.store.workspace.entries()),2)

    def test_model_broker_works_during_import_and_failed_ai_is_visible(self):
        task=self.store.new_task({'topic_id':self.topic,'task':'import','path':str(self.folder),'auto_organize':True})['id']
        self.store.update(task,status='running')
        results=[]
        worker=threading.Thread(target=lambda:results.append(self.store.run_task(self.store.task(task))),daemon=True)
        worker.start()
        request=None
        for _ in range(50):
            request=self.store.next_call()['request']
            if request:break
            time.sleep(.03)
        self.assertIsNotNone(request)
        meta={'title':'数字农业与农户收入的机制研究','authors':['张三','李四'],'year':2024,'journal':'农业经济','keywords':['市场信息'],'abstract':'数字农业通过市场信息改善农户收入。','language':'zh'}
        self.store.answer_call({'id':request['id'],'lease':request['lease'],'content':json.dumps(meta),'finish_reason':'stop'})
        worker.join(3)
        self.assertFalse(worker.is_alive())
        self.assertEqual(self.store.state()['library'][0]['metadata_origin'],'dsh_model')
        # New source with a failing model must still retain its original and mark review.
        other=self.folder/'new.md';other.write_text('# 另一篇完全不同的数字经济论文\n研究新机制。',encoding='utf-8')
        with patch.object(self.store,'model_call',side_effect=RuntimeError('quota unavailable')):
            _, result=self.run_batch(auto_organize=True)
        self.assertEqual(result['review_count'],1)
        self.assertTrue(any('quota unavailable' in w for e in self.store.state()['library'] for w in e['review_warnings']))

    def test_conflicting_dois_and_years_do_not_merge(self):
        base={'entry_id':'one','title':'A study of digital agriculture and productivity','metadata':{'doi':'10.1234/one','year':2024},'metadata_origin':'content'}
        other={**base,'entry_id':'two','metadata':{'doi':'10.1234/two','year':2024}}
        self.assertIsNone(matching_entry(base,[other]))
        other['metadata']={'year':2025}
        self.assertIsNone(matching_entry(base,[other]))

    def test_ai_can_improve_a_previously_imported_filename_title(self):
        self.one.write_text('An unlabelled paper about agriculture.',encoding='utf-8')
        self.run_batch()
        self.assertEqual(self.store.state()['library'][0]['title'],'001')
        metadata={'title':'Agricultural Information and Household Income','authors':['Zhang'],'year':2024}
        with patch.object(self.store,'model_call',return_value={'content':json.dumps(metadata),'finish_reason':'stop'}):
            self.run_batch(auto_organize=True)
        self.assertEqual(self.store.state()['library'][0]['title'],metadata['title'])

    def test_pdf_and_markdown_share_one_bibliographic_entry(self):
        import fitz
        title='Digital Agriculture and Rural Household Income'
        (self.folder/'paper.md').write_text('# '+title+'\nDOI: 10.1234/agri.2024\n\n## Abstract\nDigital agriculture improves rural household income.',encoding='utf-8')
        pdf=fitz.open();page=pdf.new_page()
        page.insert_text((72,72),title+'\nDOI: 10.1234/agri.2024\nAbstract\nDigital agriculture improves rural household income.')
        pdf.save(self.folder/'paper.pdf');pdf.close()
        _,result=self.run_batch()
        self.assertEqual(result['failed'],0)
        matching=[e for e in self.store.state()['library'] if e['doi']=='10.1234/agri.2024']
        self.assertEqual(len(matching),1)
        self.assertEqual({a['file_type'] for a in matching[0]['attachments']},{'md','pdf'})

    def test_staged_directory_upload_and_library_http(self):
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        server.store,server.token=self.store,'test-token'
        server.base=f'http://127.0.0.1:{server.server_address[1]}'
        threading.Thread(target=server.serve_forever,daemon=True).start()
        def request(path,body=None):
            headers={'X-Reading-Token':server.token,'Content-Type':'application/json'}
            data=json.dumps(body).encode() if body is not None else None
            with urllib.request.urlopen(urllib.request.Request(server.base+path,data=data,headers=headers)) as response:return json.load(response)
        try:
            staged=request('/api/upload',{'name':'研究.md','relative_path':'论文/子目录/研究.md','data':base64.b64encode(self.one.read_bytes()).decode(),'stage':True})
            self.assertFalse(self.store.state()['tasks'])
            result=request('/api/import',{'topic_id':self.topic,'paths':[staged],'auto_organize':False})
            self.store.update(result['id'],status='running')
            self.store.run_task(self.store.task(result['id']))
            entry=request('/api/library')['items'][0]
            self.assertEqual(entry['attachments'][0]['label'],'研究.md')
            self.assertEqual(entry['attachments'][0]['relative_path'],'论文/子目录/研究.md')
            request('/api/library',{'entry_id':entry['id'],'note':'本机文献笔记','tags':['农业']})
            self.assertEqual(request('/api/library')['items'][0]['note'],'本机文献笔记')
        finally:server.shutdown();server.server_close()

    def test_library_edits_status_and_backup_restore(self):
        task,result=self.run_batch()
        entry=self.store.state()['library'][0]
        self.store.update_library({'entry_id':entry['id'],'metadata':{**entry,'year':2025},'tags':['重要'],'note':'检查识别策略','is_pinned':True})
        reading=self.store.new_task({'topic_id':self.topic,'task':'read.quant','entry_ids':[entry['id']]})['id']
        self.assertEqual(self.store.state()['library'][0]['reading_status'],'reading')
        self.store.update(reading,status='completed',result=json.dumps({'artifacts':[]}))
        self.store.update(task,status='completed',result=json.dumps(result))
        self.assertEqual(self.store.state()['library'][0]['reading_status'],'read')
        archive=self.store.backup()['path'];restore_archive(archive,self.root/'restore')
        recovered=Store(self.root/'restore').state()['library'][0]
        self.assertEqual(recovered['note'],'检查识别策略')
        self.assertEqual(recovered['year'],2025)
        self.assertEqual(recovered['tags'],['重要'])
        self.assertEqual(len(recovered['timeline']),1)


if __name__ == '__main__': unittest.main()
