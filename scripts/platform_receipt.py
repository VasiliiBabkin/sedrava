"""Bind generated preview files and evidence to an actual checkout and tool versions."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1]
def command(*args):
    p=subprocess.run(args,capture_output=True,text=True,check=True)
    return (p.stdout or p.stderr).strip()
def main():
    root=ROOT/'build';files={}
    for folder in ('platform','platform-evidence','platform-dist'):
        for path in sorted((root/folder).rglob('*')):
            if path.is_file():files[path.relative_to(root).as_posix()]=hashlib.sha256(path.read_bytes()).hexdigest()
    import os
    receipt={'schema':1,'status':'experimental-preview-not-release','git_sha':command('git','rev-parse','HEAD'),'python':sys.version,'node':command('node','--version'),'ci_run':os.environ.get('GITHUB_RUN_ID'),'ci_url':(os.environ.get('GITHUB_SERVER_URL','https://github.com')+'/'+os.environ.get('GITHUB_REPOSITORY','VasiliiBabkin/sedrava')+'/actions/runs/'+os.environ['GITHUB_RUN_ID']) if os.environ.get('GITHUB_RUN_ID') else None,'tracked_changes':command('git','status','--porcelain','--untracked-files=no'),'artifacts_sha256':files}
    path=root/'platform-manifest.json';path.write_text(json.dumps(receipt,indent=2)+'\n');print(path)
if __name__=='__main__':main()
