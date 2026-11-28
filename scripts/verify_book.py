"""Check published alpha.4 book examples against the exact release CLI."""
import json,os,shutil,subprocess,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
BIN=Path(os.environ["SEDRAVA_NATIVE_BIN"]).resolve()
def run(*args,cwd=ROOT,ok=True):
    p=subprocess.run([str(BIN),*map(str,args)],cwd=cwd,capture_output=True,text=True,timeout=30)
    assert (p.returncode==0)==ok,(args,p.stdout,p.stderr)
    return p.stdout
assert run("--version").strip()=="sedrava 0.12.0-alpha.4 (Rust alpha)"
with tempfile.TemporaryDirectory(prefix="sedrava-book-") as t:
    d=Path(t)
    shutil.copy2(ROOT/"book/examples/counter/counter.sdr",d/"counter.sdr")
    run("check","counter.sdr",cwd=d);run("test","counter.sdr",cwd=d)
    assert json.loads(run("run","counter.sdr","increment","increment",cwd=d))["count"]==2
    assert json.loads(run("run","counter.sdr","increment","decrement",cwd=d))["count"]==0
    run("run","counter.sdr","decrement",cwd=d,ok=False)
    run("build","web","counter.sdr","--output","counter.html",cwd=d);assert (d/"counter.html").is_file()
    for source,n in [(ROOT/"book/examples/contacts",1),(ROOT/"examples/service_complete",13)]:
        project=d/source.name
        project.mkdir()
        for f in ("domain.sdr","sedrava-project.json"):shutil.copy2(source/f,project/f)
        assert f"{n} migration version" in run("test",cwd=project)
        build=Path(run("build",cwd=project).strip())
        assert len(json.loads((build/"migrations.json").read_text())["steps"])==n
        package=d/(source.name+"-package")
        run("package","--output",package,cwd=project);run("project","verify-package",package,cwd=project)
print("PASS book alpha.4: counter check/test/run/negative/web; contacts and service journal test/build/package/verify")
