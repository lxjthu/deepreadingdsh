import json
import hashlib
import unittest
from pathlib import Path
from unittest.mock import patch

import test_pdf_viewer
from test_pdf_cards import CARD
import pdf_cards
import pdf_visual
from server import Store

RECOGNITION={'kind':'mixed','markdown':'公式：$$y=\\frac{x_1}{2}$$\n\n|指标|值|\n|---|---|\n|系数|0.25|','uncertainties':['下标需核对']}


class VisualCardsTests(unittest.TestCase):
    setUp=test_pdf_viewer.PdfViewerTests.setUp
    tearDown=test_pdf_viewer.PdfViewerTests.tearDown
    _second_paper=test_pdf_viewer.PdfViewerTests._second_paper

    def box(self,page=1):
        return self.store.update_annotation({'entry_id':self.entry,'op':'create','item':{'kind':'box','page':page,'color':'yellow','rects':[[.1,.1,.9,.4]]}})['items'][-1]

    def task(self,marks,mode='separate'):
        result=pdf_visual.enqueue(self.store,{'entry_id':self.entry,'annotation_ids':[mark['id'] for mark in marks],'generation_mode':mode})
        self.assertEqual(result['errors'],[])
        task_id=result['items'][0]['id'];self.store.update(task_id,status='running')
        return task_id

    def test_crop_recognize_card_and_obsidian_files(self):
        task_id=self.task([self.box()])
        with patch.object(self.store,'model_call',side_effect=[{'content':json.dumps(RECOGNITION),'reported_model':'vision'},{'content':json.dumps(CARD)}]) as model:
            result=self.store.run_task(self.store.task(task_id))
        self.assertEqual(model.call_count,2)
        image=model.call_args_list[0].kwargs['images'][0]
        self.assertEqual(image['mediaType'],'image/png')
        card=pdf_cards.listing(self.store,self.entry)['items'][0]
        self.assertEqual(card['input_kind'],'visual');self.assertEqual(card['visual_recognition'][0]['status'],'machine_unverified')
        self.assertIn('\\frac',card['visual_recognition'][0]['markdown']);self.assertIn('|系数|',card['selected_text'])
        path=Path(result['note_path']);self.assertTrue(path.is_file())
        self.assertIn('![[./images/',path.read_text(encoding='utf-8'))
        asset=card['images'][0];image_path=path.parent/'images'/(asset['sha256']+'.png')
        self.assertEqual(hashlib.sha256(image_path.read_bytes()).hexdigest(),asset['sha256'])
        self.assertTrue(pdf_visual.image_bytes(self.store,self.entry,asset['region_id']).startswith(b'\x89PNG'))
        with self.assertRaises(ValueError):pdf_visual.image_bytes(self.store,self.other,asset['region_id'])
        with patch.object(self.store,'model_call') as model:
            self.store.run_task(self.store.task(task_id))
        model.assert_not_called()

    def test_combined_boxes_keep_images_and_use_one_card_request(self):
        marks=[self.box(1),self.box(2)];task_id=self.task(marks,'combined')
        repeated=pdf_visual.enqueue(self.store,{'entry_id':self.entry,'annotation_ids':[mark['id'] for mark in reversed(marks)],'generation_mode':'combined'})
        self.assertEqual({item['id'] for item in repeated['items']},{task_id})
        with patch.object(self.store,'model_call',side_effect=[{'content':json.dumps(RECOGNITION)},{'content':json.dumps({**RECOGNITION,'kind':'figure'})},{'content':json.dumps(CARD)}]) as model:
            self.store.run_task(self.store.task(task_id))
        self.assertEqual(model.call_count,3)
        self.assertNotIn('images',model.call_args_list[-1].kwargs)
        card=pdf_cards.listing(self.store,self.entry)['items'][0]
        self.assertEqual(len(card['images']),2);self.assertEqual([s['page'] for s in card['segments']],[1,2])
        self.assertEqual(card['generation_mode'],'combined')

    def test_failed_card_retry_reuses_recognition_and_source_changes_fail(self):
        task_id=self.task([self.box()])
        with patch.object(self.store,'model_call',side_effect=[{'content':json.dumps(RECOGNITION)},RuntimeError('card failed')]),self.assertRaisesRegex(RuntimeError,'card failed'):
            self.store.run_task(self.store.task(task_id))
        self.assertEqual(len(pdf_visual.listing(self.store,self.entry)['items']),1)
        with patch.object(self.store,'model_call',return_value={'content':json.dumps(CARD)}) as model:
            self.store.run_task(self.store.task(task_id))
        self.assertEqual(model.call_count,1)
        with self.pdf.open('ab') as file:file.write(b'\n')
        with self.assertRaisesRegex(ValueError,'变化'):self.store.run_task(self.store.task(task_id))

    def test_cancelled_ocr_does_not_commit_result(self):
        task_id=self.task([self.box()])
        def cancelled(*args,**kwargs):
            self.store.cancel(task_id)
            return {'content':json.dumps(RECOGNITION)}
        with patch.object(self.store,'model_call',side_effect=cancelled),self.assertRaises(InterruptedError):
            self.store.run_task(self.store.task(task_id))
        self.assertEqual(pdf_visual.listing(self.store,self.entry)['items'],[])
        self.assertEqual(self.store.rows('SELECT id FROM pdf_cards'),[])

    def test_note_folder_change_copies_files_and_rejects_external_overwrite(self):
        task_id=self.task([self.box()])
        with patch.object(self.store,'model_call',side_effect=[{'content':json.dumps(RECOGNITION)},{'content':json.dumps(CARD)}]):self.store.run_task(self.store.task(task_id))
        self.store.update(task_id,status='completed')
        card=pdf_cards.listing(self.store,self.entry)['items'][0]
        old=Path(card['note_file']['path']);new=Path(self.tmp.name)/'Obsidian 卡片'
        self.store.notes.configure(str(new))
        self.assertTrue(old.exists());self.assertTrue((new/old.name).exists())
        self.assertEqual(len(list((new/'images').glob('*.png'))),1)
        reopened=Store(self.home);self.assertEqual(reopened.notes.root,new)
        target=new/old.name;target.write_text('external user edit',encoding='utf-8')
        result=pdf_cards.operation(self.store,{'entry_id':self.entry,'id':card['id'],'op':'edit',**CARD,'title':'Changed'})
        self.assertTrue(result['note_file']['error']);self.assertEqual(target.read_text(encoding='utf-8'),'external user edit')
        self.assertEqual(pdf_cards.listing(self.store,self.entry)['items'][0]['title'],'Changed')

    def test_new_destination_collision_is_not_overwritten_or_activated(self):
        task_id=self.task([self.box()])
        with patch.object(self.store,'model_call',side_effect=[{'content':json.dumps(RECOGNITION)},{'content':json.dumps(CARD)}]):self.store.run_task(self.store.task(task_id))
        self.store.update(task_id,status='completed')
        card=pdf_cards.listing(self.store,self.entry)['items'][0];old_root=self.store.notes.root
        target=Path(self.tmp.name)/'conflict';target.mkdir();file=target/('card-'+card['id']+'.md');file.write_text('unrelated',encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'未启用'):self.store.notes.configure(str(target))
        self.assertEqual(file.read_text(encoding='utf-8'),'unrelated');self.assertEqual(self.store.notes.root,old_root)

    def test_note_failure_is_visible_and_retry_does_not_repeat_models(self):
        task_id=self.task([self.box()])
        with patch.object(self.store,'model_call',side_effect=[{'content':json.dumps(RECOGNITION)},{'content':json.dumps(CARD)}]),patch.object(self.store.notes,'prepare',side_effect=PermissionError('read only')):
            with self.assertRaisesRegex(ValueError,'笔记同步失败'):self.store.run_task(self.store.task(task_id))
        self.assertEqual(len(self.store.rows('SELECT id FROM pdf_cards')),1)
        self.assertTrue(pdf_cards.listing(self.store,self.entry)['items'][0]['note_file']['error'])
        with patch.object(self.store,'model_call') as model:self.store.run_task(self.store.task(task_id))
        model.assert_not_called()
        self.assertIsNone(pdf_cards.listing(self.store,self.entry)['items'][0]['note_file']['error'])


if __name__=='__main__':unittest.main()
