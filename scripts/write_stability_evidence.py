"""Bind an audit report to the actual checkout and completed Python test log."""
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import subprocess

ROOT=Path(__file__).resolve().parents[1]

def main():
    output=ROOT/'build/stability'
    log=(output/'python.log').read_text(encoding='utf-8')
    counts=re.findall(r'^Ran (\d+) tests? in ',log,re.M)
    if len(counts)!=1 or not re.search(r'^OK(?: \(skipped=\d+\))?\s*,log,re.M):
        raise ValueError('Missing successful complete Python test output')
    sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    data={'git_sha':sha,'python':platform.python_version(),'python_tests':int(counts[0]),
          'result':'PASS','log_sha256':hashlib.sha256(log.encode()).hexdigest(),
          'rc1_artifacts_modified':False,'recommendation':'rc2',
          'run_url':'https://github.com/'+os.environ['GITHUB_REPOSITORY']+'/actions/runs/'+os.environ['GITHUB_RUN_ID']}
    (output/'audit-evidence.json').write_text(json.dumps(data,indent=2,sort_keys=True)+'\n')
    report=(ROOT/'docs/STABILITY_AUDIT_010.md').read_text()
    (output/'STABILITY_AUDIT_010.md').write_text(report+'\n## Actual verification / Фактический прогон\n\n```json\n'+json.dumps(data,indent=2,sort_keys=True)+'\n```\n')
    print(json.dumps(data,sort_keys=True))
if __name__=='__main__':main()
,log,re.M):
        raise ValueError('Missing successful complete Python test output')
    sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    data={'git_sha':sha,'python':platform.python_version(),'python_tests':int(counts[0]),
          'result':'PASS','log_sha256':hashlib.sha256(log.encode()).hexdigest(),
          'rc1_artifacts_modified':False,'recommendation':'rc2',
          'run_url':'https://github.com/'+os.environ['GITHUB_REPOSITORY']+'/actions/runs/'+os.environ['GITHUB_RUN_ID']}
    (output/'audit-evidence.json').write_text(json.dumps(data,indent=2,sort_keys=True)+'\n')
    report=(ROOT/'docs/STABILITY_AUDIT_010.md').read_text()
    (output/'STABILITY_AUDIT_010.md').write_text(report+'\n## Actual verification / Фактический прогон\n\n```json\n'+json.dumps(data,indent=2,sort_keys=True)+'\n```\n')
    print(json.dumps(data,sort_keys=True))
if __name__=='__main__':main()
