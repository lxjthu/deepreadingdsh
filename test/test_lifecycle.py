import json
import sqlite3
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from server import Store, validate_home, instance_lock, pid_alive
from unittest.mock import patch

class LifecycleTests(unittest.TestCase):
    def test_cancel_without_resume_allows_the_next_task(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(tmp);topic=store.create_topic('t')['id']
            first=store.new_task({'topic_id':topic,'task':'import','path':'first'})['id']
            second=store.new_task({'topic_id':topic,'task':'import','path':'second'})['id']
            def run(row):
                if row['id']==first:return store.model_call(first,[])
                return {'kept':True}
            store.run_task=run;worker=threading.Thread(target=store.worker);worker.start()
            try:
                deadline=time.monotonic()+3
                while not store.rows('SELECT id FROM calls') and time.monotonic()<deadline:time.sleep(.01)
                store.cancel(first)
                deadline=time.monotonic()+3
                while store.task(second)['status']!='completed' and time.monotonic()<deadline:time.sleep(.01)
                self.assertEqual(store.task(first)['status'],'cancelled')
                self.assertEqual(store.task(second)['status'],'completed')
            finally:store.stop.set();worker.join(2)
            self.assertFalse(worker.is_alive())

    def test_unconfirmed_lock_owner_is_never_removed(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock=Path(tmp)/'.service.lock';lock.write_text('123')
            with patch('server.pid_alive',side_effect=OSError('process inspection failed')):
                with self.assertRaises(OSError):
                    with instance_lock(tmp):pass
            self.assertEqual(lock.read_text(),'123')
            with self.assertRaises(ValueError):pid_alive(0)

    def test_write_permission_failure_does_not_change_existing_library(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(tmp);topic=store.create_topic('keep')['id']
            real_open=Path.open
            def deny(path,*args,**kwargs):
                if path.name.startswith('.write-probe-'):raise PermissionError('denied')
                return real_open(path,*args,**kwargs)
            with patch.object(Path,'open',deny):
                with self.assertRaises(PermissionError):validate_home(tmp)
            self.assertEqual(store.topic(topic)['name'],'keep')
    def test_immediate_resume_releases_worker_and_rejects_old_answer(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'研究 空间')
            topic=store.create_topic('t')['id']
            task=store.new_task({'topic_id':topic,'task':'import','path':'unused'})['id']
            calls=[]
            def run(row):
                calls.append(row['id'])
                if len(calls)==1: return store.model_call(row['id'],[{'role':'user','content':'old'}])
                raise ValueError('resume failure')
            store.run_task=run
            worker=threading.Thread(target=store.worker); worker.start()
            try:
                deadline=time.monotonic()+3
                request=None
                while not request and time.monotonic()<deadline:
                    request=store.next_call()['request'];time.sleep(.01)
                self.assertIsNotNone(request)
                store.cancel(task);store.cancel(task);store.resume(task)
                with self.assertRaisesRegex(ValueError,'Stale'):
                    store.answer_call({'id':request['id'],'lease':request['lease'],'content':'old','finish_reason':'stop'})
                deadline=time.monotonic()+3
                while store.task(task)['status']!='failed' and time.monotonic()<deadline: time.sleep(.01)
                self.assertEqual(store.task(task)['error'],'resume failure')
                self.assertEqual(len(calls),2)
                self.assertEqual(store.rows('SELECT status FROM calls')[0]['status'],'abandoned')
            finally: store.stop.set();worker.join(2)
            self.assertFalse(worker.is_alive())

    def test_directory_validation_preserves_library_and_rejects_unknown_or_busy(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            fresh=root/'中文 空目录'
            self.assertTrue(validate_home(str(fresh))['empty'])
            store=Store(fresh)
            topic=store.create_topic('keep')['id']
            self.assertFalse(validate_home(str(fresh))['empty'])
            self.assertEqual(store.topic(topic)['name'],'keep')
            with instance_lock(fresh):
                with self.assertRaisesRegex(ValueError,'其他实例'):validate_home(str(fresh))
            unknown=root/'unknown';unknown.mkdir();(unknown/'note.txt').write_text('keep')
            with self.assertRaisesRegex(ValueError,'非空目录'):validate_home(str(unknown))
            self.assertEqual((unknown/'note.txt').read_text(),'keep')
            with store.db() as db:db.execute('PRAGMA user_version=99')
            with self.assertRaisesRegex(ValueError,'版本不兼容'):validate_home(str(fresh))
            with self.assertRaisesRegex(ValueError,'绝对路径'):validate_home('relative')

    def test_usage_unknown_is_not_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(tmp);topic=store.create_topic('t')['id']
            task=store.new_task({'topic_id':topic,'task':'import','path':'unused'})['id']
            store.update(task,status='running')
            for usage in (None,{'inputTokens':5,'outputTokens':2}):
                result=[]
                thread=threading.Thread(target=lambda:result.append(store.model_call(task,[])));thread.start()
                req=None
                while not req: req=store.next_call()['request'];time.sleep(.01)
                store.answer_call({**req,'content':'answer','finish_reason':'stop','usage':usage})
                thread.join(2)
                self.assertEqual(result[0]['usage'],usage)
            self.assertEqual([r['usage'] for r in store.state()['tasks'][0]['model_calls']],[None,{'inputTokens':5,'outputTokens':2}])

if __name__=='__main__':unittest.main()
