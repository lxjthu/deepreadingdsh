"""Read-only OCR triage. Never uploads a document."""
from pathlib import Path
from .workspace import digest

PADDLE_URL = 'https://aistudio.baidu.com/paddleocr'


def guide(path, tessdata=None, language='eng'):
    import pymupdf
    path = Path(path)
    if path.suffix.lower() != '.pdf': raise ValueError('OCR guide expects a PDF')
    with pymupdf.open(path) as pdf:
        pages = []
        for i, page in enumerate(pdf):
            text = page.get_text()
            bad = sum(c == '\ufffd' or (ord(c)<32 and c not in '\r\n\t') for c in text)
            status = 'needs_ocr' if len(text.strip()) < 30 else 'quality_review_required' if bad/max(1,len(text))>.01 else 'text_layer_available'
            pages.append({'physical_page':i+1,'characters':len(text),'status':status})
    local = bool(tessdata) and all((Path(tessdata)/(name+'.traineddata')).is_file() for name in language.split('+'))
    from .mineru_adapter import runtime_config
    try:
        runtime_config(); mineru = True
    except (RuntimeError,KeyError,OSError,ValueError): mineru = False
    return {'status':'completed','input_sha256':digest(path.read_bytes()),'pages':pages,
            'ocr_guidance':{'needed':any(p['status']!='text_layer_available' for p in pages),'local_configured':mineru or local,
                'default_engine':'mineru','mineru_configured':mineru,'tesseract_configured':local,
                'url':PADDLE_URL,'message':'本地 PDF 默认使用 MinerU standard 强制 OCR，文字层状态仅作诊断。可用 ocr convert 导出 Markdown、图片和逐页数据；PaddleOCR 网页保留为用户选择的备用入口。',
                'limits':'文字层存在仅是初筛，乱码、双栏顺序仍需核对；网站登录、导出界面、额度和费用未验证。'},'network_called':False}
