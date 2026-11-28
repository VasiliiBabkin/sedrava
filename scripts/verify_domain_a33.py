#!/usr/bin/env python3
"""A33 single-source directory app; no handwritten app/API/migration files."""
import hashlib,json,os,secrets,selectors,shutil,subprocess,tempfile
from pathlib import Path
from verify_sales_web_a22 import BIN,DB,ROOT,req
DEMO=ROOT/"examples/service_directory"
def main():
 with tempfile.TemporaryDirectory(prefix="sedrava-a33-") as t:
    root=Path(t);src=root/"source";bundle=root/"package";data=root/"data";auth=root/"auth.json"
    data.mkdir(mode=0o700);src.mkdir()
    for f in ("sedrava-project.json","domain.sdr"):shutil.copyfile(DEMO/f,src/f)
    domain=src/"domain.sdr";original=domain.read_text()
    tokens={n:secrets.token_hex(32) for n in ("reader","writer")}
    auth.write_text(json.dumps([{"id":n,"sha256":hashlib.sha256(v.encode()).hexdigest(),"role":"read" if n=="reader" else "write"} for n,v in tokens.items()]));auth.chmod(0o600)
    def run(*args,cwd=src,fail=False):
        p=subprocess.run([str(BIN),*map(str,args)],cwd=cwd,capture_output=True,text=True,timeout=30)
        assert (p.returncode!=0)==fail,(args,p.returncode,p.stderr,p.stdout);return p.stdout
    assert "7 migration versions" in run("test")
    b=Path(run("build").strip());assert b==Path(run("build").strip())
    assert set(p.name for p in src.iterdir())=={"sedrava-project.json","domain.sdr","build"}
    run("package","--output",bundle);run("project","verify-package",bundle)
    snap={str(p.relative_to(bundle)):p.read_bytes() for p in bundle.rglob("*") if p.is_file()}
    assert len(snap)==9
    assert snap["domain.sdr"]==domain.read_bytes()
    for n in ("app.sdr","api.sdr","migrations.json"):
        (src/n).write_bytes(snap[n]);run("build",fail=True);(src/n).unlink()
        f=bundle/n;f.write_bytes(snap[n]+b"\n");run("project","verify-package",bundle,fail=True);f.write_bytes(snap[n])
    for invalid in (original.replace("ref client","ref missing"),original.replace("text 1 128","text 128 1"),original.replace("access session read write","access public"),original.replace("name:","id:"),original.replace("entity asset","entity site")):
        domain.write_text(invalid);run("build",fail=True)
    domain.write_text(original)
    m=["--data",data,"--trusted"]
    assert json.loads(run("migrate",*m,"--apply",cwd=bundle))["current_version"]==7
    db=data/"app.log";before=db.read_bytes()
    run("migrate",*m,"--apply",cwd=bundle);assert db.read_bytes()==before
    args=["serve",*m,"--auth-file",auth,"--port","0","--max-requests","1000","--idle-ms","120000","--allow-write"]
    def start(cwd):
        p=subprocess.Popen([str(BIN),*map(str,args)],cwd=cwd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        try:
            with selectors.DefaultSelector() as sel:
                sel.register(p.stdout,selectors.EVENT_READ);assert sel.select(15)
                line=p.stdout.readline().strip()
            assert line.startswith("LISTENING http://127.0.0.1:"),(line,p.poll());return p,line.split(" ",1)[1]
        except:
            p.kill();p.wait();raise
    def stop(p):
        p.terminate();p.wait(timeout=8)
        lock=data/"app.log.lock"
        if lock.exists():assert lock.read_text().strip()==f"pid={p.pid}";lock.unlink()
    calls=0
    def call(path,body,session=None,key=None,expected=200):
        nonlocal calls
        h={"Authorization":session} if session else {}
        raw,_=req(url,"/"+path,"POST",body,key=key,headers=h,expected=expected);calls+=1;return json.loads(raw)
    def login(who):return "Session "+call("session-login",{},"Bearer "+tokens[who])["token"]
    p,url=start(bundle)
    try:
        for path,file in [("/","index.html"),("/app.js","app.js"),("/app.css","app.css")]:
            raw,h=req(url,path);assert raw==snap["ui/"+file];assert "connect-src 'self'" in h["Content-Security-Policy"]
        call("domain-client-list",{"after":""},expected=401)
        writer=login("writer");reader=login("reader")
        def w(n,body,k,expected=200,session=writer):return call("domain-"+n+"-create",body,session,k,expected)
        def q(n,after=""):return call("domain-"+n+"-list",{"after":after},reader)["rows"]
        c={"id":"c01","f_name":"Клиент","f_contact":""}
        s={"id":"s01","f_client":"c01","f_name":"Склад","f_address":"Адрес"}
        a={"id":"a01","f_site":"s01","f_name":"Контроллер","f_serial":"DEMO"}
        w("client",c,"a33-denied-0001",403,reader)
        w("client",{**c,"f_name":" "},"a33-blank-00001",422)
        w("site",s,"a33-orphan-0001",409)
        assert db.read_bytes()==before
        receipt=w("client",c,"a33-client-0001")
        assert receipt["affected"]==1
        assert w("client",c,"a33-client-0001")=={**receipt,"replayed":True}
        saved=db.read_bytes()
        w("client",{**c,"f_name":"New"},"a33-client-0001",409)
        w("client",c,"a33-duplicate-1",409)
        w("client",{**c,"id":"bad/id"},"a33-badkey-0001",422)
        w("client",{**c,"f_name":"X"*129},"a33-overflow-01",422)
        w("asset",a,"a33-orphan-0002",409)
        assert db.read_bytes()==saved
        w("site",s,"a33-site-000001");w("asset",a,"a33-asset-00001")
        assert q("client")==[["c01","Клиент",""]]
        assert q("site")==[["s01","c01","Склад","Адрес"]]
        assert q("asset")==[["a01","s01","Контроллер","DEMO"]]
        for i in range(2,23):w("client",{"id":f"c{i:02}","f_name":f"Client {i}","f_contact":""},f"a33-page-{i:04}")
        one=q("client");two=q("client",one[-1][0]);assert len(one)==20 and len(two)==2
        if os.environ.get("SEDRAVA_A22_DOM")=="1":
            subprocess.run(["node",str(ROOT/"scripts/verify_domain_a33.cjs")],env={**os.environ,"A33_URL":url,"A33_WRITER":tokens["writer"],"A33_READER":tokens["reader"]},check=True,timeout=90)
        call("session-logout",{},reader);call("domain-client-list",{"after":""},reader,expected=401)
    finally:stop(p)
    # Schema drift denied before any modification; append-only entity upgrades keep rows.
    saved=db.read_bytes()
    domain.write_text(original.replace('contact: text 0 128 label "Контакт"','contact: int 0 100 label "Контакт"'))
    run("migrate",*m,"--apply",fail=True);assert db.read_bytes()==saved
    domain.write_text(original+'\nentity inspection "Осмотры":\n    asset: ref asset label "Оборудование"\n    score: int 1 5 label "Оценка"\n    passed: bool label "Пройден"\n')
    assert "10 migration versions" in run("test")
    assert json.loads(run("migrate",*m))["pending"]==[8,9,10]
    run(*args,fail=True);assert db.read_bytes()==saved
    assert json.loads(run("migrate",*m,"--apply"))["current_version"]==10
    p,url=start(src)
    try:
        reader=login("reader");writer=login("writer")
        assert call("domain-asset-list",{"after":""},reader)["rows"][0]==["a01","s01","Контроллер","DEMO"]
        good={"id":"i01","f_asset":"a01","f_score":5,"f_passed":True}
        call("domain-inspection-create",{**good,"f_score":6},writer,"a33-invalid-int",422)
        call("domain-inspection-create",{**good,"f_passed":"true"},writer,"a33-invalid-bool",422)
        call("domain-inspection-create",good,writer,"a33-inspect-0001")
        assert call("domain-inspection-list",{"after":""},reader)["rows"]==[["i01","a01",5,True]]
    finally:stop(p)
    domain.write_text(original);saved=db.read_bytes()
    run("migrate",*m,"--apply",fail=True);assert db.read_bytes()==saved
    assert snap=={str(p.relative_to(bundle)):p.read_bytes() for p in bundle.rglob("*") if p.is_file()}
    assert json.loads(subprocess.check_output([str(DB),"verify",str(db)]))["verified"]
    print("PASS A33",calls,"direct HTTP; one domain source, generated API/UI/schema, 7->10 additive migrations, drift/downgrade refusal, FK/roles/replay/pagination/restart, immutable bundle")
if __name__=="__main__":main()
