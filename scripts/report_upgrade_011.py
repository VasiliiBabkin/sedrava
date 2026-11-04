"""Aggregate actual installation/browser/device receipts; no inferred successes."""
import argparse,json,os
from pathlib import Path

def report(root,sha,jobs,run_url):
    root=Path(root);issues=[];data={}
    if not all(jobs.get(name,{}).get('result')=='success' for name in ('packages','browser','android')):issues.append('One or more required upgrade jobs failed or did not run')
    for key,filename in [('packages','upgrade-install.json'),('android','android-upgrade.json')]:
        matches=list(root.rglob(filename))
        if len(matches)!=1:issues.append('Missing/ambiguous receipt '+filename);continue
        value=json.loads(matches[0].read_text());data[key]=value
        if value.get('candidate_sha')!=sha or value.get('status')!='PASS':issues.append('Wrong SHA or failed receipt '+filename)
    browsers={}
    for path in root.rglob('web-upgrade.json'):
        value=json.loads(path.read_text());engine=value.get('engine')
        if engine in browsers:issues.append('Duplicate browser receipt')
        browsers[engine]=value
        if value.get('candidate_sha')!=sha or value.get('status')!='PASS' or value.get('tests')!=4:issues.append('Incomplete/failed/wrong-SHA browser '+str(engine))
    if set(browsers)!={'chromium','firefox','webkit'}:issues.append('All three real browser receipts required')
    data['browsers']=browsers
    return {'upgrade_gate':'NO-GO' if issues else 'GO','candidate_sha':sha,'ci_url':run_url,'publication_authorized':False,'issues':issues,'results':data,'limits':['Physical Android device not tested','Debug APK -d downgrade is not a production rollback mechanism','No schema migration or cross-origin/path storage transfer','Same user application ID, signing key and compatible schema are required']}
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('--sha',required=True);p.add_argument('--jobs',required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    value=report(args.root,args.sha,json.loads(args.jobs),'https://github.com/'+os.environ['GITHUB_REPOSITORY']+'/actions/runs/'+os.environ['GITHUB_RUN_ID'])
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
    args.output.with_suffix('.md').write_text('# Published 0.10 → candidate → rollback\n\nUpgrade gate: **'+value['upgrade_gate']+'**. Publication authorized: **false**.\n\nSHA: `'+args.sha+'`\n\nCI: '+value['ci_url']+'\n\n'+''.join('- '+item+'\n' for item in value['issues']+value['limits']))
    print(value['upgrade_gate']);raise SystemExit(0 if value['upgrade_gate']=='GO' else 1)
