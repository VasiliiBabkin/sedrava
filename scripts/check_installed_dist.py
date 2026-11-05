"""Install both archives in isolated venvs; exercise bundled apps outside checkout."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import venv

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from sedrava_version import VERSION

def check(archive, folder):
    venv.EnvBuilder(with_pip=True).create(folder)
    bindir=folder/('Scripts' if os.name=='nt' else 'bin')
    python=bindir/('python.exe' if os.name=='nt' else 'python')
    cli=bindir/('sedrava.exe' if os.name=='nt' else 'sedrava')
    env=os.environ.copy();env.pop('PYTHONPATH',None)
    def run(*args):
        subprocess.run(list(map(str,args)),cwd=folder,env=env,check=True)
    run(python,'-m','pip','install','--no-cache-dir',archive)
    run(python,'-c',"import pathlib,sys,sedrava_core,sedrava_android_identity;assert pathlib.Path(sedrava_core.__file__).is_relative_to(sys.prefix);assert (pathlib.Path(sys.prefix)/'share/sedrava/docs/BUILD.md').is_file();assert (pathlib.Path(sys.prefix)/'share/sedrava/LICENSE').is_file();assert (pathlib.Path(sys.prefix)/'share/sedrava/DEDICATION.md').is_file()")
    run(cli,'--version')
    result=subprocess.run([str(cli),'--version'],cwd=folder,env=env,capture_output=True,text=True,check=True)
    assert result.stdout.strip()=='sedrava '+VERSION
    for name in ('reference_09','text_profile','task_manager','task_manager_navigation','bounded_core_012','bounded_values_012'):
        source=folder/'share/sedrava/examples'/f'{name}.sdr'
        run(cli,'check',source);run(cli,'test',source);run(cli,'run',source)
        web=folder/'generated with spaces'/name/'index.html'
        run(cli,'build','web',source,'--output',web)
        before=web.read_bytes()
        run(cli,'build','web',source,'--output',web)
        assert before==web.read_bytes()
        run(cli,'build','android',source,'--output',folder/'generated with spaces'/name/'android')
    run(cli,'build','android',source,'--application-id','com.example.installed','--output',folder/'explicit android')
    site_source=folder/'share/sedrava/examples/web_ui_011_landing.sdr'
    site_output=folder/'site with spaces'
    run(cli,'check',site_source)
    run(cli,'build','site',site_source,'--output',site_output)
    first={p.relative_to(site_output):p.read_bytes() for p in site_output.rglob('*') if p.is_file()}
    run(cli,'build','site',site_source,'--output',site_output)
    assert first=={p.relative_to(site_output):p.read_bytes() for p in site_output.rglob('*') if p.is_file()}
    assert (site_output/'site.css').is_file() and list((site_output/'assets').glob('*.svg'))
    for name in ('site','tasks','catalog','crm'):
        source=folder/'share/sedrava/examples'/f'platform_{name}.sdr'
        output=folder/'platform output'/name
        run(cli,'check',source)
        mode='site' if name=='site' else 'webapp'
        run(cli,'build',mode,source,'--output',output)
        first={p.relative_to(output):p.read_bytes() for p in output.rglob('*') if p.is_file()}
        run(cli,'build',mode,source,'--output',output)
        assert first=={p.relative_to(output):p.read_bytes() for p in output.rglob('*') if p.is_file()}
    print(f'PASS: clean {archive.name}, bundled docs/examples/license, check/test/run/Web/Android and deterministic Web',flush=True)

if __name__=='__main__':
    dist=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else ROOT/'dist'
    archives=[*sorted(dist.glob('*.whl')),*sorted(dist.glob('*.tar.gz'))]
    assert len(archives)==2,'Build exactly one wheel and sdist first'
    with tempfile.TemporaryDirectory(prefix='sedrava installed ') as tmp:
        for index,archive in enumerate(archives):check(archive,Path(tmp)/str(index))
