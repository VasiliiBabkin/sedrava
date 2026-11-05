"""Bind actual experimental outputs to the checkout, never to an assumed PR SHA."""
import hashlib,json,os,platform,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
files={}
for name in ('dist','build/core-a2'):
    for path in sorted((ROOT/name).rglob('*')):
        if path.is_file() and path.name!='receipt.json':files[str(path.relative_to(ROOT))]=hashlib.sha256(path.read_bytes()).hexdigest()
receipt={'source_sha':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'run_url':('https://github.com/'+os.environ['GITHUB_REPOSITORY']+'/actions/runs/'+os.environ['GITHUB_RUN_ID']) if os.environ.get('GITHUB_RUN_ID') else None,'python':platform.python_version(),'node':subprocess.check_output(['node','--version'],text=True).strip(),'sha256':files,'status':'experimental; see actual test results, not a release approval'}
output=ROOT/'build/core-a2/receipt.json';output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');print(output)
