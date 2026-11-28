#!/usr/bin/env python3
"""A34 declarative workflow acceptance."""
import hashlib,json,os,secrets,selectors,shutil,subprocess,tempfile
from pathlib import Path
from verify_sales_web_a22 import BIN,DB,ROOT,req
DEMO=ROOT/"examples/service_views"
def main():
 with tempfile.TemporaryDirectory(prefix="sedrava-a36-") as t:
    root=Path(t);src=root/"source";bundle=root/"package";data=root/"data";auth=root/"auth.json"
    data.mkdir(mode=0o700);src.mkdir()
    for f in ("sedrava-project.json","domain.sdr"):shutil.copyfile(DEMO/f,src/f)
    domain=src/"domain.sdr";original=domain.read_text()
    tokens={n:secrets.token_hex(32) for n in ("reader","writer")}
    auth.write_text(json.dumps([{"id":n,"sha256":hashlib.sha256(v.encode()).hexdigest(),"role":"read" if n=="reader" else "write"} for n,v in tokens.items()]));auth.chmod(0o600)
    def run(*args,cwd=src,fail=False):
        p=subprocess.run([str(BIN),*map(str,args)],cwd=cwd,capture_output=True,text=True,timeout=30)
        assert (p.returncode!=0)==fail,(args,p.returncode,p.stderr,p.stdout);return p.stdout
    assert "13 migration versions" in run("test")
    b=Path(run("build").strip());assert b==Path(run("build").strip())
    assert set(p.name for p in src.iterdir())=={"sedrava-project.json","domain.sdr","build"}
    run("package","--output",bundle);run("project","verify-package",bundle)
    snap={str(p.relative_to(bundle)):p.read_bytes() for p in bundle.rglob("*") if p.is_file()}
    assert len(snap)==9
    assert snap["domain.sdr"]==domain.read_bytes()
    for n in ("app.sdr","api.sdr","migrations.json"):
        (src/n).write_bytes(snap[n]);run("build",fail=True);(src/n).unlink()
        f=bundle/n;f.write_bytes(snap[n]+b"\n");run("project","verify-package",bundle,fail=True);f.write_bytes(snap[n])
    for invalid in (original.replace("ref client","ref missing"),original.replace("text 1 128","text 128 1"),original.replace("access session read write","access public"),original.replace("name:","id:"),original.replace("entity asset","entity site"),original.replace("workflow ticket:","workflow missing:"),original.replace("initial open","initial unknown"),original.replace("transition reopen","transition close"),original.replace("from closed to open","from unreachable to open"),original.replace("where status = open","where status = missing"),original.replace("filter asset","filter missing"),original.replace("group priority count","group issue count"),original.replace("report priorities","report statuses"),original.replace("from ticket group status","from asset group status")):
        domain.write_text(invalid);run("build",fail=True)
    domain.write_text(original)
    m=["--data",data,"--trusted"]
    assert json.loads(run("migrate",*m,"--apply",cwd=bundle))["current_version"]==13
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
        assert call("view-statuses",{"after":""},reader)["rows"]==[]
        assert call("view-priorities",{"after":""},reader)["rows"]==[]
        ticket={"id":"t01","f_asset":"a01","f_issue":"Неисправность","f_priority":3}
        saved=db.read_bytes()
        w("ticket",{**ticket,"f_asset":"missing"},"a34-orphan-0001",409)
        assert db.read_bytes()==saved
        receipt=w("ticket",ticket,"a34-ticket-0001")
        assert receipt["affected"]==2
        assert w("ticket",ticket,"a34-ticket-0001")=={**receipt,"replayed":True}
        assert q("ticket")==[["t01","a01","Неисправность",3,"open","t01"]]
        def history():
            return call("workflow-history",{"subject":"t01","after":""},reader)["rows"]
        assert history()==[["t01","created","","open",""]]
        body={"subject":"t01","expected":"t01","event":"w01","note":"Диагностика"}
        saved=db.read_bytes()
        call("workflow-work",body,reader,"a34-role-0001",403)
        call("workflow-reopen",body,writer,"a34-edge-0001",409)
        call("workflow-work",{**body,"note":" "},writer,"a34-note-0001",422)
        assert db.read_bytes()==saved
        receipt=call("workflow-work",body,writer,"a34-work-0001")
        assert receipt["affected"]==2
        assert call("workflow-work",body,writer,"a34-work-0001")=={**receipt,"replayed":True}
        assert q("ticket")[0][-2:]==["open","w01"]
        saved=db.read_bytes()
        call("workflow-work",{**body,"event":"w02"},writer,"a34-stale-0001",409)
        call("workflow-close",{**body,"expected":"w01"},writer,"a34-dupe-0001",409)
        assert db.read_bytes()==saved
        call("workflow-close",{**body,"expected":"w01","event":"w02"},writer,"a34-close-0001")
        assert q("ticket")[0][-2:]==["closed","w02"]
        assert call("view-statuses",{"after":""},reader)["rows"]==[["closed",1]]
        assert call("view-open",{"after":""},reader)["rows"]==[]
        saved=db.read_bytes()
        call("workflow-work",{**body,"expected":"w02","event":"w03"},writer,"a34-closed-0001",409)
        assert db.read_bytes()==saved
        call("workflow-reopen",{**body,"expected":"w02","event":"w03"},writer,"a34-reopen-0001")
        assert q("ticket")[0][-2:]==["open","w03"]
        assert [r[1] for r in history()]==["created","work","close","reopen"]
        # Reports reflect the full matching relation, not one visible page.
        def report(n):return call("view-"+n,{"after":""},reader)["rows"]
        assert report("statuses")==[["open",1]]
        assert report("priorities")==[[3,1]]
        assert call("view-open",{"after":""},reader)["rows"]==q("ticket")
        assert call("view-equipment",{"after":"","value":"a01"},reader)["rows"]==q("ticket")
        assert call("view-equipment",{"after":"","value":"missing"},reader)["rows"]==[]
        saved=db.read_bytes()
        call("view-statuses",{"after":""},expected=401)
        call("view-statuses",{"after":"t01"},reader,expected=422)
        call("view-equipment",{"after":"","value":3},reader,expected=422)
        call("view-equipment",{"after":"","value":"bad/id"},reader,expected=422)
        call("view-open",{"after":""},reader,"a36-read-key-001",400)
        assert db.read_bytes()==saved
        w("asset",{"id":"a02","f_site":"s01","f_name":"Камера","f_serial":"S2"},"a36-asset-0002")
        for i in range(2,24):
            w("ticket",{"id":f"t{i:02}","f_asset":"a01" if i%2 else "a02","f_issue":f"Заявка {i}","f_priority":1 if i%2 else 2},f"a36-ticket-{i:04}")
        saved=db.read_bytes()
        assert report("statuses")==[["open",23]]
        assert report("priorities")==[[1,11],[2,11],[3,1]]
        page=call("view-open",{"after":""},reader)["rows"]
        rest=call("view-open",{"after":page[-1][0]},reader)["rows"]
        assert len(page)==20 and len(rest)==3
        assert [r[0] for r in page+rest]==[f"t{i:02}" for i in range(1,24)]
        assert len(call("view-equipment",{"after":"","value":"a02"},reader)["rows"])==11
        assert db.read_bytes()==saved
        if os.environ.get("SEDRAVA_A22_DOM")=="1":
            subprocess.run(["node",str(ROOT/"scripts/verify_views_a36.cjs")],env={**os.environ,"A34_URL":url,"A34_WRITER":tokens["writer"]},check=True,timeout=90)
    finally:stop(p)
    p,url=start(bundle)
    try:
        reader=login("reader")
        assert call("domain-ticket-list",{"after":""},reader)["rows"][0][-2:]==["open","w03"]
        assert len(call("workflow-history",{"subject":"t01","after":""},reader)["rows"])==4
        dom=os.environ.get("SEDRAVA_A22_DOM")=="1"
        assert call("view-statuses",{"after":""},reader)["rows"]==([["closed",1],["open",23]] if dom else [["open",23]])
        assert call("view-priorities",{"after":""},reader)["rows"]==[[1,12 if dom else 11],[2,11],[3,1]]
    finally:stop(p)
    assert snap=={str(p.relative_to(bundle)):p.read_bytes() for p in bundle.rglob("*") if p.is_file()}
    assert json.loads(subprocess.check_output([str(DB),"verify",str(db)]))["verified"]
    print("PASS A36",calls,"direct HTTP; typed filters, paged views, full grouped counts, roles, read-only journal, restart and immutable package")
if __name__=="__main__":main()
