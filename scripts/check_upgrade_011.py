"""Real published 0.10 -> candidate -> 0.10 installs, never importing checkout code.

Inputs are wheel/sdist files, not source directories. Evidence retains all CLI logs,
outputs and exact archive hashes. No publication or user environments are touched.
"""
import argparse,hashlib,json,os,subprocess,sys,venv
from pathlib import Path
from urllib.request import urlopen
ROOT=Path(__file__).resolve().parents[1]
BASELINE='0.10.0'
PINS={'sedrava-0.10.0-py3-none-any.whl':'97063ea99d823017d57f41cefdcf45ba289370661b68e4f8c15a6531abbab219','sedrava-0.10.0.tar.gz':'92d9de3705cbba30124370b014d4da12ab8076cf6a31e6bc33cff326678e24c3'}
def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def download_baseline(folder):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    with urlopen('https://pypi.org/pypi/sedrava/0.10.0/json',timeout=30) as stream:meta=json.load(stream)
    for name,expected in PINS.items():
        entry=next(f for f in meta['urls'] if f['filename']==name)
        if entry['digests']['sha256']!=expected or not entry['url'].startswith('https://files.pythonhosted.org/'):raise ValueError('Published baseline identity changed')
        with urlopen(entry['url'],timeout=30) as stream:data=stream.read(8*1024*1024+1)
        if len(data)>8*1024*1024 or hashlib.sha256(data).hexdigest()!=expected:raise ValueError('Published baseline bytes changed')
        (folder/name).write_bytes(data)
    return {'published_tag':'v0.10.0','published_source_sha':'688a320025a0d38235eb90c780362ec26b0708e2','index':'https://pypi.org/pypi/sedrava/0.10.0/json','files':{name:{'sha256':sha,'url':next(f['url'] for f in meta['urls'] if f['filename']==name)} for name,sha in PINS.items()}}
def check(candidate_dist,work,sha,candidate="0.11.0rc1"):
    work=Path(work).resolve();candidate_dist=Path(candidate_dist).resolve()
    if work.is_relative_to(ROOT) or work.exists():raise ValueError('Use a new work directory outside the source checkout')
    if len(sha)!=40 or any(c not in '0123456789abcdef' for c in sha):raise ValueError('Exact candidate source SHA required')
    work.mkdir(parents=True);baseline=download_baseline(work/'published')
    archives=[candidate_dist/f'sedrava-{candidate}-py3-none-any.whl',candidate_dist/f'sedrava-{candidate}.tar.gz']
    if not all(p.is_file() for p in archives):raise ValueError('Candidate wheel and sdist required')
    env=os.environ.copy()
    for key in ('PYTHONPATH','PYTHONHOME'):env.pop(key,None)
    env['PYTHONNOUSERSITE']='1';events=[];source=work/'projects';source.mkdir();outputs={};versions={}
    log=(work/'commands.log').open('w')
    def run(*args):
        result=subprocess.run(list(map(str,args)),cwd=work,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        log.write('$ '+repr(list(map(str,args)))+'\n'+result.stdout+'\n');log.flush()
        if result.returncode:raise RuntimeError(f'Command failed ({result.returncode}); see {log.name}: {args[:3]}')
        return result.stdout
    def tools(folder):
        bindir=folder/('Scripts' if os.name=='nt' else 'bin');return bindir/('python.exe' if os.name=='nt' else 'python'),bindir/('sedrava.exe' if os.name=='nt' else 'sedrava')
    def create(label,archive):
        folder=work/label;venv.EnvBuilder(with_pip=True).create(folder);install(folder,archive);return folder
    def install(folder,archive):
        python,_=tools(folder);run(python,'-m','pip','install','--no-cache-dir','--force-reinstall',archive)
        run(python,'-m','pip','check')
    def exercise(label,folder,version):
        python,cli=tools(folder);actual=run(cli,'--version').strip()
        if actual!='sedrava '+version:raise ValueError('Wrong installed CLI version: '+actual)
        run(python,'-I','-c',"import importlib.metadata,pathlib,sys,sedrava_core;assert pathlib.Path(sedrava_core.__file__).is_relative_to(pathlib.Path(sys.prefix));assert importlib.metadata.version('sedrava')=="+repr(version))
        share=folder/'share/sedrava';assert (share/'LICENSE').is_file() and (share/'docs/BUILD.md').is_file()
        if not list(source.glob('*.sdr')):
            for name in ('reference_09','text_profile','task_manager','task_manager_navigation'):(source/(name+'.sdr')).write_bytes((share/'examples'/(name+'.sdr')).read_bytes())
        snapshot={};out=work/'generated'/label;out.mkdir(parents=True)
        for project in sorted(source.glob('*.sdr')):
            for verb in ('check','test'):run(cli,verb,project)
            snapshot[project.stem]=json.loads(run(cli,'run',project))
            web=out/project.stem/'index.html';run(cli,'build','web',project,'--output',web);before=web.read_bytes();run(cli,'build','web',project,'--output',web);assert before==web.read_bytes()
            android=out/(project.stem+'-android');run(cli,'build','android',project,'--output',android)
        if version==candidate:
            for name in ('site','tasks','catalog','crm'):
                project=share/'examples'/('platform_'+name+'.sdr');run(cli,'check',project);target=out/('platform_'+name);mode='site' if name=='site' else 'webapp'
                run(cli,'build',mode,project,'--output',target);before={p.relative_to(target).as_posix():digest(p) for p in target.rglob('*') if p.is_file()}
                run(cli,'build',mode,project,'--output',target);assert before=={p.relative_to(target).as_posix():digest(p) for p in target.rglob('*') if p.is_file()}
        outputs[label]=snapshot;versions[label]=actual;events.append({'phase':label,'version':version,'result':'PASS'})
    oldwheel=work/'published'/'sedrava-0.10.0-py3-none-any.whl';oldsdist=work/'published'/'sedrava-0.10.0.tar.gz'
    for label,archive,version in [('clean-old-wheel',oldwheel,BASELINE),('clean-old-sdist',oldsdist,BASELINE),('clean-rc-wheel',archives[0],candidate),('clean-rc-sdist',archives[1],candidate)]:exercise(label,create(label,archive),version)
    project_hashes={p.name:digest(p) for p in source.glob('*.sdr')}
    inplace=create('in-place',oldwheel);exercise('in-place-before',inplace,BASELINE)
    _,cli=tools(inplace);state=work/'user-state.json';run(cli,'run',source/'text_profile.sdr','rename','--state-file',state);saved=state.read_bytes()
    install(inplace,archives[0]);exercise('in-place-upgrade',inplace,candidate)
    assert json.loads(run(cli,'run',source/'text_profile.sdr','--state-file',state))['name']=='Алиса 😀' and state.read_bytes()==saved
    run(cli,'run',source/'text_profile.sdr','rename','--state-file',state);upgraded=state.read_bytes()
    install(inplace,oldwheel);exercise('in-place-rollback',inplace,BASELINE)
    assert json.loads(run(cli,'run',source/'text_profile.sdr','--state-file',state))['visits']==2 and state.read_bytes()==upgraded
    python,_=tools(inplace)
    run(python,'-I','-c',"import importlib.util;assert importlib.util.find_spec('sedrava_webapp') is None")
    assert all(value==outputs['clean-old-wheel'] for value in outputs.values())
    assert project_hashes=={p.name:digest(p) for p in source.glob('*.sdr')}
    def tree(label):return {p.relative_to(work/'generated'/label).as_posix():digest(p) for p in (work/'generated'/label).rglob('*') if p.is_file()}
    assert tree('clean-old-wheel')==tree('clean-old-sdist')==tree('in-place-before')==tree('in-place-rollback')
    assert tree('clean-rc-wheel')==tree('clean-rc-sdist')==tree('in-place-upgrade')
    incompatible_source=work/'incompatible-capacity.sdr'
    original=(source/'task_manager_navigation.sdr').read_text();changed=original.replace('(max=100)','(max=99)');assert changed!=original
    incompatible_source.write_text(changed);_,candidate_cli=tools(work/'clean-rc-wheel')
    run(candidate_cli,'check',incompatible_source);run(candidate_cli,'build','web',incompatible_source,'--output',work/'generated/incompatible-schema/task_manager_navigation/index.html')
    result={'incompatible_source_sha256':digest(incompatible_source),'status':'PASS','candidate_sha':sha,'candidate_version':candidate,'baseline':baseline,'candidate_files':{p.name:digest(p) for p in archives},'python':sys.version,'phases':events,'installed_versions':versions,'observed_states':outputs,'project_hashes':project_hashes,'cli_state_before_sha256':hashlib.sha256(saved).hexdigest(),'cli_state_after_rc_sha256':hashlib.sha256(upgraded).hexdigest(),'user_sources_unchanged':True,'same_environment_upgrade_and_rollback':True,'wheel_sdist_generated_bytes_equal':True}
    (work/'upgrade-install.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');log.close();print('PASS: four clean installs and same-venv 0.10 -> 0.11rc1 -> 0.10; exact output/state parity');return result
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--candidate-dist',type=Path,required=True);parser.add_argument('--work',type=Path,required=True);parser.add_argument('--candidate-sha',required=True);parser.add_argument('--candidate-version',default='0.11.0rc1');args=parser.parse_args();check(args.candidate_dist,args.work,args.candidate_sha,args.candidate_version)
