"""Isolated local-only MinerU worker for a PDF or a directory of PDFs."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import re
import time
from pathlib import Path


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--config', required=True, type=Path)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding='utf-8-sig'))
    os.environ.update(MINERU_HOME=config['model_home'], MINERU_MODEL_SOURCE='local',
                      MINERU_MODEL_SMALL_BACKEND='onnx', MINERU_MODEL_VLM_ENGINE='llama-cpp')
    if config.get('temp_dir'):
        import tempfile
        scratch = Path(config['temp_dir']); scratch.mkdir(parents=True, exist_ok=True)
        os.environ['TEMP'] = os.environ['TMP'] = str(scratch)
        tempfile.tempdir = str(scratch)
    from mineru.parser import parse
    from mineru.parser.base import ParseResult
    from mineru.parser.writer import FileBasedDataWriter
    from mineru.version import __version__
    files = sorted(p for p in args.input.iterdir() if p.is_file() and p.suffix.lower() == '.pdf') if args.input.is_dir() else [args.input]
    if not files or any(not p.is_file() or p.suffix.lower() != '.pdf' for p in files):
        parser.error('Input must contain PDF files')
    if args.output.exists():
        parser.error('Output must be a new directory; existing results are preserved')
    args.output.mkdir(parents=True)
    summary = {'status': 'running', 'engine': 'mineru', 'version': __version__, 'tier': 'standard', 'ocr_mode': 'ocr',
               'network_upload': False, 'documents': [], 'failures': []}
    for pdf in files:
        start = time.perf_counter()
        try:
            digest = hashlib.sha256(pdf.read_bytes()).hexdigest()
            print('Converting: ' + pdf.name, flush=True)
            result = parse(pdf, tier='standard', ocr_mode='ocr')
            folder = args.output / pdf.stem
            if folder.exists(): raise ValueError('Conflicting PDF stems: ' + pdf.stem)
            folder.mkdir()
            result.save(FileBasedDataWriter(str(folder)))
            materialized = ParseResult.from_json((folder / 'middle_json.json').read_text(encoding='utf-8'))
            indices = [p.page_idx for p in materialized.pages]
            if indices != list(range(len(indices))): raise ValueError('Missing or unordered physical pages')
            import pypdfium2
            original = pypdfium2.PdfDocument(str(pdf))
            try:
                if len(indices) != len(original): raise ValueError('Converted page count differs from original PDF')
            finally:
                original.close()
            if hashlib.sha256(pdf.read_bytes()).hexdigest() != digest: raise ValueError('Source PDF changed during conversion')
            pages = []
            for page in materialized.pages:
                single = ParseResult(materialized.middle_json.model_copy(update={'pages': [page]}))
                text = single.markdown()
                pages.append({'page': page.page_idx + 1, 'text': text, 'text_layer': None,
                              'image_count': len(re.findall(r'!\[[^\]]*\]\(|<img\b', text)),
                              'layout': 'mineru-standard-ocr'})
            if not any(p['text'].strip() for p in pages): raise ValueError('Empty MinerU document')
            write_json(folder / 'pages.json', pages)
            markdown = folder / (pdf.stem + '.md')
            (folder / 'markdown.md').rename(markdown)
            row = {'pdf': str(pdf.resolve()), 'pdf_sha256': digest, 'directory': folder.name,
                   'markdown': markdown.relative_to(args.output).as_posix(), 'pages': len(pages),
                   'characters': sum(len(p['text']) for p in pages), 'seconds': round(time.perf_counter()-start, 2),
                   'engine': 'mineru', 'version': __version__, 'tier': 'standard', 'ocr_mode': 'ocr'}
            write_json(folder / 'source-manifest.json', row)
            summary['documents'].append(row)
            print('Saved: ' + str(markdown), flush=True)
        except Exception as exc:
            summary['failures'].append({'pdf': str(pdf), 'error': str(exc)})
            print('Failed: ' + pdf.name + ': ' + str(exc), flush=True)
        write_json(args.output / 'conversion-summary.json', summary)
    summary['status'] = 'partial' if summary['failures'] else 'completed'
    write_json(args.output / 'conversion-summary.json', summary)
    raise SystemExit(1 if summary['failures'] else 0)


if __name__ == '__main__':
    main()
