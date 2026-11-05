"""Record actual site artifact hashes and CI identity; never publish a site."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
site = ROOT / 'build/site'
evidence = ROOT / 'build/site-evidence'
evidence.mkdir(parents=True, exist_ok=True)
run = os.environ.get('GITHUB_RUN_ID')
repo = os.environ.get('GITHUB_REPOSITORY')
receipt = {
    'schema': 1,
    'git_sha': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
    'ci_url': f'https://github.com/{repo}/actions/runs/{run}' if run and repo else None,
    'files': {str(p.relative_to(site)): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in sorted(site.rglob('*')) if p.is_file()},
    'deployment': False,
}
(evidence / 'BUILD.json').write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n')
