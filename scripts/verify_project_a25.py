#!/usr/bin/env python3
"""A25 end-to-end lifecycle. All project/data/auth files are disposable."""
import hashlib,json,os,secrets,selectors,subprocess,tempfile
from pathlib import Path
from verify_sales_web_a22 import BIN,DB,ROOT,req
def main():
 with tempfile.TemporaryDirectory(prefix="sedrava-a25-") as t:
    root=Path(t);src=root/"demo-shop";data=root/"private-data";bundle=root/"release";auth=root/"auth.json"
    data.mkdir(mode=0o700)
    tokens={n:secrets.token_hex(32) for n in ("reader","writer")}
    auth.write_text(json.dumps([{"id":n,"sha256":hashlib.sha256(v.encode()).hexdigest(),"role":"read" if n=="reader" else "write"} for n,v in tokens.items()]));auth.chmod(0o600)
    def run(*args,cwd=root,fail=False):
        p=subprocess.run([str(BIN),*map(str,args)],cwd=cwd,capture_output=True,text=True,timeout=25)
        assert (p.returncode!=0)==fail,(args,p.returncode,p.stderr,p.stdout)
        return p
    run("new","../escape",fail=True);run("new","Demo",fail=True)
    run("new",src.name);assert src.is_dir()
    sources={p.name:p.read_bytes() for p in src.iterdir()}
    run("new",src.name,fail=True);assert sources=={p.name:p.read_bytes() for p in src.iterdir()}
    assert "PASS project" in run("test",cwd=src).stdout
    assert not (data/"app.log").exists()
    first=Path(run("build",cwd=src).stdout.strip());assert first.is_dir()
    assert Path(run("build",cwd=src).stdout.strip())==first
    original=(first/"ui/app.js").read_bytes()
    (first/"ui/app.js").write_bytes(original+b"\n// changed")
    run("build",cwd=src,fail=True)
    (first/"ui/app.js").write_bytes(original)
    app=src/"app.sdr";app_original=app.read_bytes()
    app.write_bytes(app_original.replace("Управление каталогом".encode(),"Новый каталог".encode(),1))
    second=Path(run("build",cwd=src).stdout.strip());assert first!=second and first.is_dir()
    app.write_bytes(app_original);assert Path(run("build",cwd=src).stdout.strip())==first
    # Extra secrets and untracked data must never be included by recursive copying.
    (src/"auth.json").write_bytes(b"DO_NOT_PACKAGE_TEST_SECRET")
    (src/"local.txt").write_bytes(b"DO_NOT_PACKAGE_TEST_DATA")
    run("package","--output",bundle,cwd=src)
    run("package","--output",bundle,cwd=src,fail=True)
    expected={"sedrava-project.json","app.sdr","api.sdr","migrations.json","checksums.json","ui/app.js","ui/app.css","ui/index.html"}
    assert {str(p.relative_to(bundle)) for p in bundle.rglob("*") if p.is_file()}==expected
    assert all(b"DO_NOT_PACKAGE_TEST" not in (bundle/p).read_bytes() for p in expected)
    run("project","verify-package",bundle)
    checks=json.loads((bundle/"checksums.json").read_text())
    assert all(hashlib.sha256((bundle/p).read_bytes()).hexdigest()==h for p,h in checks["files"].items())
    snapshot={p:(bundle/p).read_bytes() for p in expected}
    extra=bundle/"unexpected";extra.write_text("unexpected")
    run("project","verify-package",bundle,fail=True);extra.unlink()
    (bundle/"ui/index.html").write_bytes(snapshot["ui/index.html"]+b"x")
    run("project","verify-package",bundle,fail=True)
    (bundle/"ui/index.html").write_bytes(snapshot["ui/index.html"])
    # Manifest symlink/unknown properties and private data policy.
    manifest=src/"sedrava-project.json";saved=manifest.read_bytes()
    manifest.write_text('{"format":1,"name":"demo-shop","version":"0.1.0","other":1}')
    run("test",cwd=src,fail=True);manifest.write_bytes(saved)
    app.unlink();app.symlink_to(bundle/"app.sdr");run("test",cwd=src,fail=True);app.unlink();app.write_bytes(app_original)
    run("migrate","--data",data,"--apply",cwd=src,fail=True)
    run("migrate","--data",data,"--trusted",cwd=src,fail=True)
    run("migrate","--data","private-data","--trusted","--apply",cwd=src,fail=True)
    public=root/"public";public.mkdir(mode=0o755)
    run("migrate","--data",public,"--trusted","--apply",cwd=src,fail=True)
    assert not (public/"app.log").exists()
    assert not (data/"app.log").exists()
    args=["--data",data,"--trusted"]
    report=json.loads(run("migrate",*args,"--apply",cwd=bundle).stdout)
    assert report["current_version"]==5 and not report["pending"]
    db=data/"app.log";before=db.read_bytes()
    assert json.loads(run("migrate",*args,cwd=src).stdout)["current_version"]==5
    run("migrate",*args,"--apply",cwd=bundle);assert db.read_bytes()==before
    run("new","other-shop")
    other=root/"other-shop"
    run("migrate",*args,cwd=other,fail=True)
    run("migrate",*args,"--apply",cwd=other,fail=True)
    assert db.read_bytes()==before
    unmanaged=root/"unmanaged";unmanaged.mkdir(mode=0o700)
    subprocess.run([str(DB),"init",str(unmanaged/"app.log")],check=True,capture_output=True)
    subprocess.run([str(DB),"sql",str(unmanaged/"app.log"),"CREATE TABLE Old (id TEXT PRIMARY KEY)","a26-manual-0001"],check=True,capture_output=True)
    unmanaged_before=(unmanaged/"app.log").read_bytes()
    run("migrate","--data",unmanaged,"--trusted","--apply",cwd=src,fail=True)
    assert (unmanaged/"app.log").read_bytes()==unmanaged_before

    serve=["serve",*args,"--auth-file",auth,"--port","0","--max-requests","1000","--idle-ms","30000"]
    run(*serve,cwd=bundle,fail=True);assert db.read_bytes()==before
    run(*serve,"--allow-write",cwd=other,fail=True);assert db.read_bytes()==before
    p=subprocess.Popen([str(BIN),*map(str,serve),"--allow-write"],cwd=bundle,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    count=0
    try:
        with selectors.DefaultSelector() as sel:
            sel.register(p.stdout,selectors.EVENT_READ);assert sel.select(15)
            line=p.stdout.readline().strip()
        assert line.startswith("LISTENING http://127.0.0.1:"),line;url=line.split(" ",1)[1]
        def call(path,authorization,body,key=None,expected=200):
            nonlocal count
            raw,_=req(url,path,"POST",body,key=key,headers={"Authorization":authorization},expected=expected);count+=1
            return json.loads(raw)
        def login(user):return "Session "+call("/session-login","Bearer "+tokens[user],{})["token"]
        writer=login("writer")
        item={"id":"p1","title":"Начальный","category":"food","price":10}
        first_write=call("/add-product",writer,item,"a25-product-0001");assert first_write["affected"]==1
        assert call("/add-product",writer,item,"a25-product-0001")=={**first_write,"replayed":True}
        call("/session-logout",writer,{})
        for path,name in [("/","index.html"),("/app.js","app.js"),("/app.css","app.css")]:
            raw,_=req(url,path);assert raw==snapshot["ui/"+name]
        if os.environ.get("SEDRAVA_A22_DOM")=="1":
            subprocess.run(["node",str(ROOT/"scripts/verify_native_sales_a23e.cjs")],env={**os.environ,"SEDRAVA_A22_URL":url,"SEDRAVA_A22_WRITER":tokens["writer"],"SEDRAVA_A22_READER":tokens["reader"]},check=True,timeout=60)
        reader=login("reader")
        assert call("/product-count",reader,{})["rows"]==[[2 if os.environ.get("SEDRAVA_A22_DOM")=="1" else 1]]
        call("/session-logout",reader,{})
    finally:
        p.terminate();p.wait(timeout=8)
        lock=data/"app.log.lock"
        if lock.exists():assert lock.read_text().strip()==f"pid={p.pid}";lock.unlink()
    assert {str(p.relative_to(bundle)) for p in bundle.rglob("*") if p.is_file()}==expected
    assert snapshot=={p:(bundle/p).read_bytes() for p in expected}
    run("project","verify-package",bundle)
    assert json.loads(run("migrate",*args,cwd=bundle).stdout)["current_version"]==5
    subprocess.run([str(DB),"verify",str(db)],check=True,capture_output=True)
    print(f"PASS A25: scaffold, no-overwrite, deterministic build, immutable package, manifest/symlink/data guards, migrations, serve from bundle, {count} direct HTTP requests, real generated DOM")
if __name__=="__main__":main()
