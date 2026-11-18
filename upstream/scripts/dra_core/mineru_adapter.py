"""Run local MinerU in its own environment; never fall back or upload PDFs."""
from __future__ import annotations
import base64
import json
import os
import subprocess
import tempfile
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[2]


def runtime_config():
    path = Path(os.environ.get('DRA_MINERU_CONFIG', PACKAGE / 'references/mineru.local.json'))
    if not path.is_file():
        raise RuntimeError('Local MinerU requires references/mineru.local.json or DRA_MINERU_CONFIG; use --pdf-engine pymupdf for explicit text-layer extraction')
    config = json.loads(path.read_text(encoding='utf-8-sig'))
    if not Path(config['python']).is_file():
        raise RuntimeError('MinerU Python not found: ' + config['python'])
    if not Path(config['model_home']).is_dir():
        raise RuntimeError('MinerU model home not found: ' + config['model_home'])
    return path, config


def convert(input_path, output_path):
    config_path, config = runtime_config()
    command = [config['python'], str(PACKAGE / 'scripts/mineru_worker.py'),
               '--input', str(Path(input_path).resolve()), '--output', str(Path(output_path).resolve()),
               '--config', str(config_path.resolve())]
    result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', errors='replace',
                            timeout=config.get('timeout_seconds', 7200),
                            env={**os.environ, 'PYTHONIOENCODING': 'utf-8', 'PYTHONUTF8': '1'})
    manifest = Path(output_path) / 'conversion-summary.json'
    if result.returncode or not manifest.is_file():
        failures = json.loads(manifest.read_text(encoding='utf-8')).get('failures') if manifest.is_file() else None
        raise RuntimeError('MinerU conversion failed: ' + (json.dumps(failures, ensure_ascii=False) if failures else (result.stderr + '\n' + result.stdout)[-4000:]))
    return json.loads(manifest.read_text(encoding='utf-8'))


def extract(path):
    _, config = runtime_config()
    scratch = config.get('temp_dir')
    if scratch: Path(scratch).mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='dra-mineru-', dir=scratch) as temp:
        summary = convert(path, Path(temp) / 'output')
        row = summary['documents'][0]
        folder = Path(temp) / 'output' / row['directory']
        pages = json.loads((folder / 'pages.json').read_text(encoding='utf-8'))
        assets = {p.relative_to(folder).as_posix(): base64.b64encode(p.read_bytes()).decode('ascii')
                  for name in ('assets', 'images') for p in (folder / name).rglob('*') if p.is_file()}
        return {'pages': pages, 'image_assets': assets, 'mineru': {k:v for k,v in row.items() if k not in ('directory','markdown')},
                'structured_json': json.loads((folder / 'middle_json.json').read_text(encoding='utf-8'))}
