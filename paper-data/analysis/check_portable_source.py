"""Locally compile the packaged sources; no upload or robot access."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import zipfile

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parent.parent


def main():
    archive = ROOT / 'output/AEGIS_LaTeX_source.zip'
    compiler = shutil.which('tectonic')
    if not compiler:
        raise RuntimeError('Tectonic is required for this local portability test')
    folder = Path(tempfile.mkdtemp(prefix='portable-source-', dir=ROOT / 'tmp'))
    with zipfile.ZipFile(archive) as source:
        for entry in source.infolist():
            path = Path(entry.filename)
            if path.is_absolute() or '..' in path.parts:
                raise ValueError('Unsafe archive path')
        source.extractall(folder)
    result = {
        'passed': True,
        'tested_archive': str(archive.relative_to(ROOT)),
        'tested_archive_sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
        'method': 'Fresh local extraction; compile with Tectonic; compare page counts and complete extracted PDF text',
        'overleaf_executed': False,
        'external_submission_or_upload': False,
    }
    for name in ('main', 'supplementary'):
        subprocess.run([compiler, '--keep-logs', f'{name}.tex'], cwd=folder, check=True)
        reference = PdfReader(ROOT / f'output/pdf/{name}.pdf')
        portable = PdfReader(folder / f'{name}.pdf')
        expected = [p.extract_text() for p in reference.pages]
        actual = [p.extract_text() for p in portable.pages]
        assert len(reference.pages) == len(portable.pages), name
        assert expected == actual, f'{name}: PDF text differs'
        result[name] = {'pages': len(portable.pages), 'extracted_text_identical': True}
    (ROOT / 'analysis/portable_source_validation.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
