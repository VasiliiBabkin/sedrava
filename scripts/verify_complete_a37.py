#!/usr/bin/env python3
"""A34 declarative workflow acceptance."""
import concurrent.futures,hashlib,json,os,secrets,selectors,shutil,subprocess,tempfile,urllib.request,urllib.error
from pathlib import Path
from verify_sales_web_a22 import BIN,DB,ROOT,req
DEMO=ROOT/"examples/service_complete"
def main():
 with tempfile.TemporaryDirectory(prefix="sedrava-a37-") as t:
    root=Path(t);src=root/"source";bundle=root/"package";data=root/"data";auth=root/"auth.json"
    data.mkdir(mode=0o700);src.mkdir()
    for f in ("sedrava-project.json","domain.sdr"):shutil.copyfile(DEMO/f,src/f)
    domain=src/"domain.sdr";original=domain.read_text()
    tokens={n:secrets.token_hex(32) for n in ("reader","writer","engineer")}
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
    for invalid in (original.replace("ref client","ref missing"),original.replace("text 1 128","text 128 1"),original.replace("access session read write","access public"),original.replace("name:","id:"),original.replace("entity asset","entity site"),original.replace("workflow ticket:","workflow missing:"),original.replace("initial open","initial unknown"),original.replace("transition reopen","transition close"),original.replace("from closed to open","from unreachable to open"),original.replace("capture minutes cost","capture unknown"),original.replace("capture minutes cost","capture minutes minutes"),original.replace("history sum minutes cost","history sum day"),original.replace("otherwise 0 label","otherwise 500001 label",1)):
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
        ticket={"id":"t01","f_asset":"a01","f_issue":"Неисправность","f_priority":3,"ev_day":"2026-11-28"}
        saved=db.read_bytes()
        w("ticket",{**ticket,"f_asset":"missing"},"a34-orphan-0001",409)
        assert db.read_bytes()==saved
        w("ticket",{**ticket,"ev_day":"2026-02-29"},"a37-invalid-date",422)
        assert db.read_bytes()==saved
        receipt=w("ticket",ticket,"a34-ticket-0001")
        assert receipt["affected"]==2
        assert w("ticket",ticket,"a34-ticket-0001")=={**receipt,"replayed":True}
        assert q("ticket")==[["t01","a01","Неисправность",3,"open","t01"]]
        def history():
            return call("workflow-history",{"subject":"t01","after":""},reader)["rows"]
        assert history()==[["t01","created","","open","","2026-11-28",0,0]]
        def totals(subject="t01"):return call("view-totals",{"subject":subject},reader)["rows"]
        assert totals()==[["t01",1,0,0]] and totals("missing")==[]
        base={"subject":"t01","expected":"t01","event":"w01","note":"Диагностика","ev_day":"2026-11-28"}
        body={**base,"ev_minutes":45,"ev_cost":1500}
        saved=db.read_bytes()
        call("workflow-work",body,reader,"a34-role-0001",403)
        call("workflow-reopen",base,writer,"a34-edge-0001",409)
        call("workflow-work",{**body,"note":" "},writer,"a34-note-0001",422)
        call("workflow-work",{**body,"ev_minutes":0},writer,"a37-minutes-0001",422)
        call("workflow-work",{**body,"ev_cost":100001},writer,"a37-cost-0001",422)
        call("workflow-work",{**body,"ev_day":"2026-04-31"},writer,"a37-date-0001",422)
        assert db.read_bytes()==saved
        engineer=login("engineer")
        def race(item):
            payload,session,key=item
            request=urllib.request.Request(url+"/workflow-work",data=json.dumps(payload).encode(),headers={"Authorization":session,"Idempotency-Key":key,"Content-Type":"application/json"},method="POST")
            try:r=urllib.request.urlopen(request,timeout=8)
            except urllib.error.HTTPError as e:r=e
            with r:return r.status,json.loads(r.read())
        contenders=[(body,writer,"a37-race-writer"),(body,engineer,"a37-race-engineer")]
        with concurrent.futures.ThreadPoolExecutor(2) as pool:out=list(pool.map(race,contenders))
        calls+=2
        assert sorted(r[0] for r in out)==[200,409],out
        win=next(i for i,r in enumerate(out) if r[0]==200)
        payload,owner,key=contenders[win]
        receipt=out[win][1];assert receipt["affected"]==2
        assert call("workflow-work",payload,owner,key)=={**receipt,"replayed":True}
        assert q("ticket")[0][-2:]==["open","w01"]
        saved=db.read_bytes()
        call("workflow-work",{**body,"event":"w02"},writer,"a34-stale-0001",409)
        call("workflow-close",{**base,"expected":"w01"},writer,"a34-dupe-0001",409)
        assert db.read_bytes()==saved
        call("workflow-close",{**base,"expected":"w01","event":"w02"},writer,"a34-close-0001")
        assert q("ticket")[0][-2:]==["closed","w02"]
        saved=db.read_bytes()
        call("workflow-work",{**body,"expected":"w02","event":"w03"},writer,"a34-closed-0001",409)
        assert db.read_bytes()==saved
        call("workflow-reopen",{**base,"expected":"w02","event":"w03"},writer,"a34-reopen-0001")
        assert q("ticket")[0][-2:]==["open","w03"]
        assert [r[1] for r in history()]==["created","work","close","reopen"]
        assert totals()==[["t01",4,45,1500]]
        saved=db.read_bytes()
        call("workflow-close",{**body,"expected":"w03","event":"w04"},writer,"a37-payload-denied",422)
        assert db.read_bytes()==saved
        call("workflow-work",{**body,"expected":"w03","event":"w04","ev_minutes":60,"ev_cost":2500,"ev_day":"2026-11-29"},writer,"a37-work-0002")
        assert totals()==[["t01",5,105,4000]]
        rows=history()
        assert rows[-1][-3:]==["2026-11-29",60,2500]
        assert all(r[-2:]==[0,0] for r in rows if r[1]!="work")
        assert call("view-tickets",{"after":"","value":"open"},reader)["rows"]==q("ticket")
        assert call("view-tickets",{"after":"","value":"closed"},reader)["rows"]==[]
        assert call("view-equipment",{"after":"","value":"a01"},reader)["rows"]==q("ticket")
        assert call("view-statuses",{"after":""},reader)["rows"]==[["open",1]]
        saved=db.read_bytes()
        call("view-totals",{"subject":"t01"},expected=401)
        call("view-totals",{"subject":"bad/id"},reader,expected=422)
        call("workflow-history-create",{"id":"fake"},writer,"a37-history-bypass",404)
        assert db.read_bytes()==saved
        w("ticket",{**ticket,"id":"t02"},"a37-ticket-0002")
        previous="t02"
        for i in range(1,23):
            event=f"x{i:02}"
            call("workflow-work",{"subject":"t02","expected":previous,"event":event,"note":"Проверка","ev_day":"2024-02-29","ev_minutes":2,"ev_cost":3},writer,f"a37-long-{i:04}")
            previous=event
        assert totals("t02")==[["t02",23,44,66]]
        page=call("workflow-history",{"subject":"t02","after":""},reader)["rows"]
        tail=call("workflow-history",{"subject":"t02","after":page[-1][0]},reader)["rows"]
        assert len(page)==20 and len(tail)==3
        assert totals()==[["t01",5,105,4000]]
        if os.environ.get("SEDRAVA_A22_DOM")=="1":
            subprocess.run(["node",str(ROOT/"scripts/verify_complete_a37.cjs")],env={**os.environ,"A34_URL":url,"A34_WRITER":tokens["writer"]},check=True,timeout=90)
    finally:stop(p)
    p,url=start(bundle)
    try:
        reader=login("reader")
        assert call("domain-ticket-list",{"after":""},reader)["rows"][0][-2:]==["open","w04"]
        assert len(call("workflow-history",{"subject":"t01","after":""},reader)["rows"])==5
        assert call("view-totals",{"subject":"t01"},reader)["rows"]==[["t01",5,105,4000]]
    finally:stop(p)
    assert snap=={str(p.relative_to(bundle)):p.read_bytes() for p in bundle.rglob("*") if p.is_file()}
    assert json.loads(subprocess.check_output([str(DB),"verify",str(db)]))["verified"]
    print("PASS A37",calls,"direct HTTP; calendar validation, typed event payload, defaults, atomic history, 105 minutes / 4000 RUB, reports, filters, replay, restart, immutable package")
if __name__=="__main__":main()
