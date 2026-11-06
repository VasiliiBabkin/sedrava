"""Hash actual outputs and identify their exact checked-out source, no success inference."""
import hashlib,json,os,platform,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
files={}
for name in ('dist','build/typed-errors-browser','build/core-a2','build/namespace-core','build/typed-errors-android/app/build/outputs','build/typed-errors-android/app/build/test-results','build/typed-errors-android/app/build/reports'):
    for path in sorted((ROOT/name).rglob('*')):
        if path.is_file():files[str(path.relative_to(ROOT))]=hashlib.sha256(path.read_bytes()).hexdigest()
receipt={'source_sha':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'run_url':('https://github.com/'+os.environ['GITHUB_REPOSITORY']+'/actions/runs/'+os.environ['GITHUB_RUN_ID']) if os.environ.get('GITHUB_RUN_ID') else None,'python':platform.python_version(),'sha256':files,'status':'experimental outputs; consult actual tests; not publication approval'}
out=ROOT/'build/typed-errors-receipt.json';out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(receipt,indent=2)+'\n');print(out)
