"""Isolated Unlimited OCR 2 process. Uses installed model/environment unchanged."""
import argparse
import importlib.util
import json
import os
from pathlib import Path


def convert(source, output, root, max_length=16384):
    root, source, output = Path(root).resolve(), Path(source).resolve(), Path(output).resolve()
    os.environ.update(HF_HOME=str(root/'.hf-cache'), HF_MODULES_CACHE=str(root/'.hf-cache/modules'),
                      HF_HUB_OFFLINE='1', MPLCONFIGDIR=str(root/'.mpl-cache'))
    import fitz
    import torch
    from transformers import AutoModel, AutoTokenizer
    model_dir = root/'Unlimited-OCR-model'
    manifest = json.loads((model_dir/'download_manifest.json').read_text(encoding='utf-8'))
    if manifest.get('id') != 'baidu/Unlimited-OCR-2':
        raise ValueError('Expected installed Unlimited OCR 2 model')
    if not torch.cuda.is_available():
        raise RuntimeError('Unlimited OCR 2 requires available CUDA')
    spec = importlib.util.spec_from_file_location('installed_uocr_runner', root/'test_local.py')
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    output.mkdir(parents=True, exist_ok=True)
    tokenizer = AutoTokenizer.from_pretrained(str(model_dir), trust_remote_code=True, local_files_only=True)
    model = AutoModel.from_pretrained(str(model_dir), trust_remote_code=True, local_files_only=True,
        use_safetensors=True, torch_dtype=torch.bfloat16, attn_implementation='eager').eval().cuda()
    pages = []
    with fitz.open(source) as doc:
        for index in range(len(doc)):
            dest = output/f'page-{index+1:04d}'
            dest.mkdir(exist_ok=True)
            result_file = dest/'page.json'
            if result_file.exists():
                cached = json.loads(result_file.read_text(encoding='utf-8'))
                if cached.get('model_revision') == manifest['sha'] and cached.get('source_sha256') == __import__('hashlib').sha256(source.read_bytes()).hexdigest():
                    pages.append(cached)
                    continue
            image = dest/'input.png'
            doc[index].get_pixmap(dpi=300).save(image)
            with torch.inference_mode():
                result = model.infer(tokenizer, image_file=[str(image)], crop_mode=False,
                    output_path=str(dest), image_size=1024, max_length=max_length,
                    no_repeat_ngram_size=35, ngram_window=1024, save_results=False,
                    return_dict=True, eval_mode=True, tps_interval=1000)
            raw = result['text']
            (dest/'raw.txt').write_text(raw, encoding='utf-8')
            if result['finish_reason'] != 'stop' or result['num_pages_out'] != 1:
                raise RuntimeError(f'Incomplete OCR on page {index+1}: {result["finish_reason"]}')
            text = runner.save_markdown(raw, dest, [str(image)])
            if not text.strip():
                raise RuntimeError(f'Empty OCR on page {index+1}')
            row = {'page': index+1, 'text': text, 'model_revision': manifest['sha'],
                   'source_sha256': __import__('hashlib').sha256(source.read_bytes()).hexdigest(),
                   'engine': 'unlimited-ocr-2', 'finish_reason': result['finish_reason']}
            result_file.write_text(json.dumps(row, ensure_ascii=False, indent=2), encoding='utf-8')
            pages.append(row)
            print(f'OCR page {index+1}/{len(doc)} complete', flush=True)
    (output/'pages.json').write_text(json.dumps(pages, ensure_ascii=False, indent=2), encoding='utf-8')
    return pages


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--input', required=True)
    p.add_argument('--output', required=True)
    p.add_argument('--root', required=True)
    a = p.parse_args()
    convert(a.input, a.output, a.root)
