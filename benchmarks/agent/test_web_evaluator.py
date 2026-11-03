"""Real browser negative controls, NEVER coding-agent trial measurements."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from web_codegen import generate

HERE = Path(__file__).resolve().parent


def main():
    source = (HERE / 'baselines/sedrava/counter.sdr').read_text()
    with tempfile.TemporaryDirectory(prefix='benchmark-negative-controls-') as tmp:
        root = Path(tmp)
        ordinary = generate(source)
        variants = {
            'hidden-display': ordinary.replace('</head>', '<style>output{display:none!important}</style></head>'),
            'missing-persistence': generate('\n'.join(line for line in source.splitlines() if not line.startswith('persist '))),
            'second-page-exception': ordinary.replace('</body>', '''<script>
if (!sessionStorage.getItem('negative-control') && document.querySelector('output[data-state="count"]').innerText.trim() === '2') {
    throw new Error('negative-control second-page exception');
}
sessionStorage.setItem('negative-control', 'yes');
</script></body>'''),
        }
        for name, html in variants.items():
            candidate = root / name
            candidate.mkdir()
            (candidate / 'index.html').write_text(html)
            report = root / (name+'.json')
            command = [sys.executable, str(HERE/'evaluate_web_candidate.py'),
                       '--directory', str(candidate), '--value-selector', 'output[data-state="count"]',
                       '--increment-label', 'Add', '--decrement-label', 'Subtract', '--reset-label', 'Reset',
                       '--output', str(report)]
            if os.environ.get('SEDRAVA_CHROMIUM'):
                command += ['--chromium', os.environ['SEDRAVA_CHROMIUM']]
            result = subprocess.run(command, check=False, timeout=130)
            data = json.loads(report.read_text())
            assert result.returncode != 0 and data['passed'] is False, name
            if name == 'hidden-display':
                assert 'visible' in data['error'], data
            elif name == 'missing-persistence':
                assert 'C06' in data['error'] and len(data['observations']) == 5, data
            else:
                assert 'negative-control second-page exception' in data['error'], data
                assert len(data['observations']) == 8, data
            print('PASS negative control:', name, flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
