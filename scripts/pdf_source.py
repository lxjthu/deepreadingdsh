"""Read-only PDF access for the original-document viewer.

The viewer never ships a PDF engine to the browser: it asks this module for one
rendered page image, the page geometry, and the word boxes that build the
selectable text layer. Nothing here writes to the source file.
"""
from __future__ import annotations

import threading
from pathlib import Path

MAX_BYTES = 512 * 1024 * 1024
MIN_SCALE = 0.2
MAX_SCALE = 4.0
MAX_PIXELS = 40_000_000
MAX_WORDS = 40_000
CACHE_SIZE = 64

_lock = threading.Lock()
_meta_cache: dict[tuple, dict] = {}
_meta_order: list[tuple] = []
_word_cache: dict[tuple, list] = {}
_word_order: list[tuple] = []
_render_cache: dict[tuple, bytes] = {}
_render_order: list[tuple] = []


def fitz_module():
    """Import PyMuPDF under either of its module names."""
    try:
        import pymupdf
        return pymupdf
    except ImportError:
        import fitz
        return fitz


def available():
    try:
        fitz_module()
    except ImportError:
        return False
    return True


def _stat_key(path, *extra):
    info = Path(path).stat()
    return (str(path), info.st_mtime_ns, info.st_size, *extra)


def _remember(cache, order, key, value):
    cache[key] = value
    order.append(key)
    while len(order) > CACHE_SIZE:
        cache.pop(order.pop(0), None)


def _check_source(path):
    path = Path(path)
    if path.suffix.lower() != '.pdf': raise ValueError('该附件不是 PDF 文件')
    if not path.is_file(): raise ValueError('PDF 原文件不存在，可能已被移动或删除')
    if path.stat().st_size > MAX_BYTES: raise ValueError('PDF 文件过大，无法在工作台中打开')
    return path


def _open(path):
    fitz = fitz_module()
    doc = fitz.open(str(path))
    if doc.needs_pass:
        doc.close()
        raise ValueError('PDF 已加密，需要密码才能显示')
    if doc.page_count < 1:
        doc.close()
        raise ValueError('PDF 没有页面')
    return doc


def describe(path):
    """Return page count and per-page geometry in PDF points."""
    path = _check_source(path)
    key = _stat_key(path)
    with _lock:
        cached = _meta_cache.get(key)
    if cached is not None: return cached
    doc = _open(path)
    try:
        pages = []
        for index in range(doc.page_count):
            rect = doc[index].rect
            pages.append({'number': index + 1, 'width': round(rect.width, 3), 'height': round(rect.height, 3)})
        meta = {'page_count': len(pages), 'pages': pages,
                'title': str((doc.metadata or {}).get('title') or '').strip(),
                'encrypted': False}
    finally:
        doc.close()
    with _lock:
        _remember(_meta_cache, _meta_order, key, meta)
    return meta


def _page(doc, number, page_count):
    try:
        number = int(number)
    except (TypeError, ValueError):
        raise ValueError('页码无效') from None
    if not 1 <= number <= page_count: raise ValueError('页码超出范围')
    return doc[number - 1]


def page_words(path, number):
    """Return word boxes in PDF points with a top-left origin (PyMuPDF convention)."""
    path = _check_source(path)
    meta = describe(path)
    number = int(number)
    key = _stat_key(path, number)
    with _lock:
        cached = _word_cache.get(key)
    if cached is not None: return cached
    doc = _open(path)
    try:
        page = _page(doc, number, meta['page_count'])
        words = []
        for item in page.get_text('words'):
            text = str(item[4]).strip()
            if not text: continue
            words.append([round(float(item[0]), 2), round(float(item[1]), 2),
                          round(float(item[2]), 2), round(float(item[3]), 2), text])
            if len(words) >= MAX_WORDS: break
    finally:
        doc.close()
    with _lock:
        _remember(_word_cache, _word_order, key, words)
    return words


def render_page(path, number, scale):
    """Render one page to PNG bytes at ``scale`` (CSS pixels per PDF point)."""
    path = _check_source(path)
    meta = describe(path)
    try:
        scale = float(scale)
    except (TypeError, ValueError):
        raise ValueError('缩放比例无效') from None
    if scale != scale: raise ValueError('缩放比例无效')
    scale = max(MIN_SCALE, min(MAX_SCALE, scale))
    number = int(number)
    key = _stat_key(path, number, round(scale, 3))
    with _lock:
        cached = _render_cache.get(key)
    if cached is not None: return cached
    doc = _open(path)
    try:
        page = _page(doc, number, meta['page_count'])
        rect = page.rect
        if rect.width * scale * rect.height * scale > MAX_PIXELS:
            raise ValueError('页面尺寸过大，请降低缩放比例')
        pixmap = page.get_pixmap(matrix=fitz_module().Matrix(scale, scale), alpha=False)
        data = pixmap.tobytes('png')
    finally:
        doc.close()
    with _lock:
        _remember(_render_cache, _render_order, key, data)
    return data
