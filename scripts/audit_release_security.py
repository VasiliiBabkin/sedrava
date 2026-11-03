"""Policy audit: exactly one reviewed, pinned OIDC publisher is allowed."""
import json
import hashlib
from pathlib import Path
import re
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.rc_archive import inspect_payload

# Reviewed Git blob (not a mutable version tag). Change only after workflow review.
REVIEWED_PUBLISH_WORKFLOW_BLOB = 'b48a3c6ae399a64926fb9731dae9724a5b969d63'

def approved_publisher(data):
    actual = hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
    if actual != REVIEWED_PUBLISH_WORKFLOW_BLOB:
        raise ValueError('Unreviewed PyPI publishing workflow content')
    return True

def audit(root=ROOT):
    root=Path(root);pins=json.loads((root/'.github/action-pins.json').read_text())
    approved={ref.rsplit('@',1)[0]+'@'+sha for ref,sha in pins.items()}
    workflows=list((root/'.github/workflows').glob('*.yml'))
    publication_steps=0
    for path in workflows:
        text=path.read_text()
        if path.name == 'publish-pypi.yml':
            approved_publisher(path.read_bytes())
            uses=re.findall(r'uses:\s+(\S+)',text)
            if any(ref not in approved or not re.search(r'@[a-f0-9]{40}$',ref) for ref in uses):
                raise ValueError('Unpinned/unauthorized publisher action')
            if sum('/checkout@' in ref for ref in uses)!=text.count('persist-credentials: false'):
                raise ValueError('Publisher persists checkout credentials')
            publication_steps += 1
            continue
        if not re.search(r'^permissions:\n(?:  [a-z-]+: read\n)+',text,re.M):raise ValueError('Explicit read-only permissions required: '+path.name)
        if re.search(r'(?m)^\s*(?:contents|actions|packages|id-token|checks):\s*(?:write|write-all)',text) or 'secrets.' in text or 'pull_request_target:' in text:
            raise ValueError('Privileged release workflow: '+path.name)
        if re.search(r'\b(?:twine\s+upload|gh\s+release\s+(?:create|upload|edit|delete)|gh-action-pypi-publish)\b',text):raise ValueError('Publisher in preparation workflows')
        if re.search(r'^\s*(?:<<:|[\w-]+:\s*[&*]\w)',text,re.M):raise ValueError('Workflow policy aliases not allowed')
        uses=re.findall(r'uses:\s+(\S+)',text)
        if any(ref not in approved or not re.search(r'@[a-f0-9]{40}$',ref) for ref in uses):raise ValueError('Unpinned/unapproved action: '+path.name)
        if sum('/checkout@' in ref for ref in uses)!=text.count('persist-credentials: false'):raise ValueError('Checkout credentials persisted')
    paths=subprocess.check_output(['git','ls-files','-z'],cwd=root).decode().split('\0')
    scanned=0
    for relative in paths:
        if not relative:continue
        file=root/relative
        if file.is_symlink():raise ValueError('Unexpected tracked symlink')
        inspect_payload(relative,file.read_bytes());scanned+=1
    return {'result':'PASS','workflow_count':len(workflows),'tracked_files_scanned':scanned,'permissions':'read only except reviewed PyPI OIDC publishing job','actions':'full reviewed commit SHAs','publication_steps':publication_steps,'scan':'high-confidence key/token and private/local filename checks; not a proof of absence of every possible secret'}

if __name__=='__main__':
    print(json.dumps(audit(),sort_keys=True,indent=2))
