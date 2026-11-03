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
    receipt={'schema':1,'status':'experimental-preview-not-release','git_sha':command('git','rev-parse','HEAD'),'python':sys.version,'node':command('node','--version'),'ci_run':os.environ.get('GITHUB_RUN_ID'),'artifacts_sha256':files}
    path=root/'platform-manifest.json';path.write_text(json.dumps(receipt,indent=2)+'\n');print(path)
if __name__=='__main__':main()
