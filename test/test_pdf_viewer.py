import json
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from server import Handler, Store, ThreadingHTTPServer
import pdf_source

try:
    import pymupdf
except ImportError:  # older wheels only expose fitz
    import fitz as pymupdf

PAPER = '# 验证论文\n\n## 摘要\n这段正文用于验证标记与原文窗口。\n'


def make_pdf(path, pages=2):
    document = pymupdf.open()
    for index in range(pages):
        page = document.new_page(width=300, height=400)
        page.insert_text((40, 60), 'Page %d research text' % (index + 1), fontsize=14)
    document.save(str(path))
    document.close()


class PdfViewerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / 'library'
        self.store = Store(self.home)
        self.topic = self.store.create_topic('验证')['id']
        paper = Path(self.tmp.name) / 'paper.md'
        paper.write_text(PAPER, encoding='utf-8')
        self.entry = self.store.import_file({'topic_id': self.topic, 'path': str(paper)}, 'test')['entry_ids'][0]
        folder = self.store.workspace.path('sources/' + self.entry)
        folder.mkdir(parents=True, exist_ok=True)
        self.pdf = folder / 'paper.pdf'
        make_pdf(self.pdf, 2)
        record = self.store.workspace.get(self.entry)
        record.setdefault('sources', []).append({
            'path': ('sources/' + self.entry + '/paper.pdf'), 'sha256': 'test', 'original_name': 'paper.pdf'})
        self.store.workspace.update(record)
        self.other = self.store.import_file({'topic_id': self.topic,
                                             'path': str(self._second_paper())}, 'test')['entry_ids'][0]

    def _second_paper(self):
        path = Path(self.tmp.name) / 'second.md'
        path.write_text('# 没有原文的文献\n\n## 摘要\n一篇文章可以只有题录。\n', encoding='utf-8')
        return path

    def tearDown(self):
        self.store.stop.set()
        self.tmp.cleanup()

    def test_page_geometry_render_and_words(self):
        self.assertTrue(pdf_source.available())
        meta = pdf_source.describe(self.pdf)
        self.assertEqual(meta['page_count'], 2)
        self.assertEqual([(page['width'], page['height']) for page in meta['pages']], [(300, 400), (300, 400)])
        image = pdf_source.render_page(self.pdf, 1, 1.5)
        self.assertTrue(image.startswith(b'\x89PNG'))
        words = pdf_source.page_words(self.pdf, 2)
        text = ' '.join(word[4] for word in words)
        self.assertIn('Page', text)
        self.assertIn('2', text)
        for x0, y0, x1, y1, _ in words:
            self.assertLessEqual(x0, x1)
            self.assertLessEqual(y0, y1)
            self.assertGreaterEqual(x0, 0)
            self.assertLessEqual(x1, 300)
        with self.assertRaisesRegex(ValueError, '页码超出范围'):
            pdf_source.page_words(self.pdf, 5)
        with self.assertRaisesRegex(ValueError, '不是 PDF'):
            pdf_source.describe(Path(self.tmp.name) / 'paper.md')

    def test_annotation_create_update_delete(self):
        created = self.store.update_annotation({'entry_id': self.entry, 'op': 'create', 'item': {
            'page': 1, 'kind': 'highlight', 'color': 'yellow',
            'rects': [[0.1, 0.2, 0.5, 0.25], [-1, -1, 2, 2]], 'quote': '原文引文', 'note': ''}})
        self.assertEqual(len(created['items']), 1)
        mark = created['items'][0]
        self.assertEqual(mark['page'], 1)
        self.assertEqual(mark['kind'], 'highlight')
        self.assertEqual(mark['quote'], '原文引文')
        self.assertEqual(len(mark['rects']), 2)
        self.assertEqual(mark['rects'][1], [0.0, 0.0, 1.0, 1.0])
        file = self.store.workspace.path('annotations/' + self.entry + '.json')
        self.assertTrue(file.is_file())
        self.assertEqual(json.loads(file.read_text(encoding='utf-8'))['entry_id'], self.entry)

        updated = self.store.update_annotation({'entry_id': self.entry, 'op': 'update',
                                                'item': {'id': mark['id'], 'note': '我的备注'}})
        changed = updated['items'][0]
        self.assertEqual(changed['note'], '我的备注')
        self.assertEqual(changed['rects'], mark['rects'])
        self.assertEqual(changed['kind'], 'highlight')

        removed = self.store.update_annotation({'entry_id': self.entry, 'op': 'delete', 'item': {'id': mark['id']}})
        self.assertEqual(removed['items'], [])
        self.assertEqual(self.store.annotations(self.entry), [])

    def test_annotation_rejects_bad_input(self):
        cases = [
            ({'entry_id': self.entry, 'op': 'create', 'item': {'page': 9, 'kind': 'box', 'color': 'blue', 'rects': [[0, 0, .1, .1]]}}, '页码超出范围'),
            ({'entry_id': self.entry, 'op': 'create', 'item': {'page': 1, 'kind': 'drop', 'color': 'blue', 'rects': [[0, 0, .1, .1]]}}, '类型无效'),
            ({'entry_id': self.entry, 'op': 'create', 'item': {'page': 1, 'kind': 'box', 'color': 'teal', 'rects': [[0, 0, .1, .1]]}}, '颜色无效'),
            ({'entry_id': self.entry, 'op': 'create', 'item': {'page': 1, 'kind': 'box', 'color': 'blue', 'rects': []}}, '区域为空'),
            ({'entry_id': self.entry, 'op': 'create', 'item': {'page': 1, 'kind': 'box', 'color': 'blue', 'rects': [['a', 0, 1, 1]]}}, '区域无效'),
            ({'entry_id': self.entry, 'op': 'explode', 'item': {'id': 'x'}}, '未知的标记操作'),
            ({'entry_id': self.other, 'op': 'create', 'item': {'page': 1, 'kind': 'note', 'color': 'pink', 'rects': [[0, 0, .1, .1]]}}, '没有可显示的 PDF'),
            ({'entry_id': '../escape', 'op': 'create', 'item': {}}, '未找到该文献'),
        ]
        for payload, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(ValueError, message):
                    self.store.update_annotation(payload)
        self.assertFalse(self.store.workspace.path('annotations').exists() and
                         any(self.store.workspace.path('annotations').glob('*.json')))

    def test_state_reports_mark_counts_and_document_has_no_annotation(self):
        self.store.update_annotation({'entry_id': self.entry, 'op': 'create', 'item': {
            'page': 2, 'kind': 'note', 'color': 'green', 'rects': [[0.4, 0.4, 0.5, 0.5]], 'note': '便签'}})
        state = self.store.state()
        self.assertEqual(state['annotation_counts'], {self.entry: 1})
        self.assertNotIn('annotations', state['documents'][0])

    def test_http_pdf_endpoints(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        server.store, server.token = self.store, 'test-secret'
        server.base = 'http://127.0.0.1:%d' % server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        def request(path, method='GET', body=None):
            headers = {'X-Reading-Token': 'test-secret'}
            data = None
            if body is not None:
                headers['Content-Type'] = 'application/json'
                data = json.dumps(body).encode('utf-8')
            return urllib.request.urlopen(urllib.request.Request(server.base + path, data=data,
                                                                 method=method, headers=headers))
        try:
            page = request('/pdf').read().decode('utf-8')
            self.assertIn('pdf.js', page)
            self.assertTrue(request('/pdf.js').read())
            self.assertTrue(request('/katex/katex.min.js').read())
            self.assertTrue(request('/katex/fonts/KaTeX_Main-Regular.woff2').read())
            meta = json.load(request('/api/pdf/meta?entry_id=' + self.entry))
            self.assertEqual(meta['page_count'], 2)
            self.assertTrue(meta['raw_path'].startswith('workspace/sources/'))
            image = request('/api/pdf/page?entry_id=%s&page=1&scale=1.4' % self.entry)
            self.assertEqual(image.headers['Content-Type'], 'image/png')
            self.assertTrue(image.read().startswith(b'\x89PNG'))
            words = json.load(request('/api/pdf/text?entry_id=%s&page=1' % self.entry))
            self.assertTrue(words['words'])
            created = json.load(request('/api/annotations', 'POST', {'entry_id': self.entry, 'op': 'create', 'item': {
                'page': 1, 'kind': 'box', 'color': 'orange', 'rects': [[0.2, 0.2, 0.4, 0.3]], 'quote': '', 'note': ''}}))
            self.assertEqual(len(created['items']), 1)
            listing = json.load(request('/api/annotations?entry_id=' + self.entry))
            self.assertEqual(len(listing['items']), 1)
            with self.assertRaises(urllib.error.HTTPError) as context:
                request('/api/pdf/page?entry_id=%s&page=99' % self.entry)
            self.assertEqual(context.exception.code, 400)
            with self.assertRaises(urllib.error.HTTPError):
                urllib.request.urlopen(server.base + '/api/pdf/meta?entry_id=' + self.entry)
        finally:
            server.shutdown()
            server.server_close()


if __name__ == '__main__':
    unittest.main()
