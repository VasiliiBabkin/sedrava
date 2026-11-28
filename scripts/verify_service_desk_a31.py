#!/usr/bin/env python3
"""A31 acceptance of the actual published compiler, generated UI and NativeLog."""
import concurrent.futures,hashlib,json,os,secrets,selectors,shutil,subprocess,tempfile
from pathlib import Path
from verify_sales_web_a22 import BIN,DB,ROOT,req
DEMO=ROOT/"examples/service_desk"
def main():
 with tempfile.TemporaryDirectory(prefix="sedrava-a31-") as t:
    root=Path(t);src=root/"service-desk";bundle=root/"package";data=root/"data";auth=root/"auth.json"
    data.mkdir(mode=0o700);src.mkdir()
    for name in ["sedrava-project.json","app.sdr","api.sdr","migrations.json"]:shutil.copyfile(DEMO/name,src/name)
    tokens={n:secrets.token_hex(32) for n in ("reader","writer","engineer")}
    auth.write_text(json.dumps([{"id":n,"sha256":hashlib.sha256(v.encode()).hexdigest(),"role":"read" if n=="reader" else "write"} for n,v in tokens.items()]));auth.chmod(0o600)
    def run(*args,cwd=src,fail=False):
        p=subprocess.run([str(BIN),*map(str,args)],cwd=cwd,capture_output=True,text=True,timeout=30)
        assert (p.returncode!=0)==fail,(args,p.returncode,p.stderr,p.stdout);return p.stdout
    assert "14 migration versions" in run("test")
    build=run("build").strip();assert build==run("build").strip()
    run("package","--output",bundle);run("project","verify-package",bundle)
    snapshot={str(p.relative_to(bundle)):p.read_bytes() for p in bundle.rglob("*") if p.is_file()}
    migrate=["--data",data,"--trusted"]
    assert json.loads(run("migrate",*migrate,"--apply",cwd=bundle))["current_version"]==14
    db=data/"app.log";before=db.read_bytes()
    run("migrate",*migrate,"--apply",cwd=bundle);assert db.read_bytes()==before
    args=["serve",*migrate,"--auth-file",auth,"--port","0","--max-requests","1000","--idle-ms","120000","--allow-write"]
    def start():
        p=subprocess.Popen([str(BIN),*map(str,args)],cwd=bundle,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        try:
            with selectors.DefaultSelector() as sel:
                sel.register(p.stdout,selectors.EVENT_READ);assert sel.select(15)
                line=p.stdout.readline().strip()
            assert line.startswith("LISTENING http://127.0.0.1:"),line;return p,line.split(" ",1)[1]
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
        raw,_=req(url,"/"+path,"POST",body,key=key,headers=h,expected=expected);calls+=1
        return json.loads(raw)
    def login(who):return "Session "+call("session-login",{},"Bearer "+tokens[who])["token"]
    p,url=start()
    try:
        for path,file in [("/","index.html"),("/app.js","app.js"),("/app.css","app.css")]:
            raw,h=req(url,path);assert raw==snapshot["ui/"+file];assert "connect-src 'self'" in h["Content-Security-Policy"]
        call("clients",{"after":""},expected=401)
        writer=login("writer");reader=login("reader");engineer=login("engineer")
        def w(path,body,key,expected=200,session=writer):
            return call(path,body,session,key,expected)
        def q(path,body,expected=200):return call(path,body,reader,expected=expected)["rows"]
        client={"id":"c01","name":"Тестовый заказчик","contact":"Диспетчер"}
        site={"id":"s01","client_id":"c01","name":"Склад","address":"Тестовая улица"}
        asset={"id":"a01","site_id":"s01","name":"ОПС · Контроллер","serial":"DEMO-01"}
        ticket={"id":"t01","asset_id":"a01","issue":"Неисправность шлейфа","priority":3,"work_day":"2026-11-28"}
        w("add-client",client,"a31-denied-001",403,reader)
        w("add-client",{**client,"name":" "},"a31-bad-name-001",422)
        w("add-site",site,"a31-missing-fk-1",409)
        assert db.read_bytes()==before
        r=w("add-client",client,"a31-client-0001");assert r["affected"]==1
        assert w("add-client",client,"a31-client-0001")=={**r,"replayed":True}
        saved=db.read_bytes()
        w("add-client",{**client,"name":"Изменено"},"a31-client-0001",409);assert db.read_bytes()==saved
        w("add-site",site,"a31-site-000001")
        w("add-asset",asset,"a31-asset-00001")
        assert q("sites",{"client_id":"c01","after":""})==[["s01","Склад","Тестовая улица"]]
        assert q("assets",{"site_id":"s01","after":""})==[["a01",asset["name"],"DEMO-01"]]
        saved=db.read_bytes()
        w("add-ticket",{**ticket,"asset_id":"missing"},"a31-missing-asset",409)
        w("add-ticket",{**ticket,"priority":4},"a31-bad-priority",422)
        assert db.read_bytes()==saved
        r=w("add-ticket",ticket,"a31-ticket-0001");assert r["affected"]==2
        assert q("tickets",{"closed":False,"after":""})==[["t01","a01",ticket["issue"],3,False,"t01"]]
        assert q("asset-tickets",{"asset_id":"a01","after":""})==[["t01","a01",ticket["issue"],3,False,"t01"]]
        assert q("events",{"ticket_id":"t01","after":""})==[["t01","created","2026-11-28",ticket["issue"],0,0]]
        assert q("ticket-totals",{"ticket_id":"t01"})==[["t01",1,0,0]]
        assert q("dashboard",{"closed":False})==[[False,1]]
        base={"id":"w01","ticket_id":"t01","expected_event":"t01","work_day":"2026-11-28","note":"Диагностика","minutes":45,"cost":1500}
        saved=db.read_bytes()
        w("add-work",{**base,"minutes":0},"a31-bad-minutes",422)
        w("add-work",{**base,"cost":100001},"a31-bad-cost-01",422)
        assert db.read_bytes()==saved
        # Two writers act on the same state. Exactly one wins, other must leave no event.
        def race(args):
            item,session,key=args
            # req assertion gives exact status; use real HTTP response directly to permit either race order.
            import urllib.request,urllib.error
            request=urllib.request.Request(url+"/add-work",data=json.dumps(item).encode(),headers={"Authorization":session,"Idempotency-Key":key,"Content-Type":"application/json"},method="POST")
            try:r=urllib.request.urlopen(request,timeout=8)
            except urllib.error.HTTPError as e:r=e
            with r:return r.status,json.loads(r.read())
        contenders=[(base,writer,"a31-race-writer"),({**base,"id":"w02"},engineer,"a31-race-eng001")]
        with concurrent.futures.ThreadPoolExecutor(2) as pool:out=list(pool.map(race,contenders))
        calls+=2
        assert sorted(x[0] for x in out)==[200,409],out
        win=next(i for i,x in enumerate(out) if x[0]==200);item,owner,k=contenders[win];current=item["id"]
        assert out[win][1]["affected"]==2
        assert w("add-work",item,k,session=owner)=={**out[win][1],"replayed":True}
        assert q("ticket-totals",{"ticket_id":"t01"})==[["t01",2,45,1500]]
        # Reusing an event ID must rollback the status change, not silently skip history.
        close={"id":current,"ticket_id":"t01","expected_event":current,"work_day":"2026-11-28","note":"Готово"}
        saved=db.read_bytes()
        w("close-ticket",close,"a31-duplicate-event",409);assert db.read_bytes()==saved
        close["id"]="w03";w("close-ticket",close,"a31-close-00001")
        assert q("tickets",{"closed":False,"after":""})==[]
        assert q("dashboard",{"closed":True})==[[True,1]]
        saved=db.read_bytes()
        w("add-work",{**base,"id":"w04","expected_event":"w03"},"a31-closed-work",409)
        w("close-ticket",{**close,"id":"w04","expected_event":"w03"},"a31-close-again",409)
        assert db.read_bytes()==saved
        reopen={**close,"id":"w04","expected_event":"w03","note":"Повторная неисправность"}
        w("reopen-ticket",reopen,"a31-reopen-0001")
        w("add-work",{**base,"id":"w05","expected_event":"w04","note":"Замена датчика","minutes":60,"cost":2500},"a31-work-000002")
        assert q("ticket-totals",{"ticket_id":"t01"})==[["t01",5,105,4000]]
        assert q("tickets",{"closed":False,"after":""})[0][-1]=="w05"
        # Bounded pagination, distinct parent filtering, HTML-looking text is inert in UI.
        for i in range(2,23):
            w("add-client",{"id":f"c{i:02}","name":f"Клиент {i}","contact":""},f"a31-page-{i:04}")
        a=q("clients",{"after":""});b=q("clients",{"after":a[-1][0]})
        assert len(a)==20 and len(b)==2 and [r[0] for r in a+b]==[f"c{i:02}" for i in range(1,23)]
        assert q("sites",{"client_id":"c02","after":""})==[]
        if os.environ.get("SEDRAVA_A22_DOM")=="1":
            subprocess.run(["node",str(ROOT/"scripts/verify_service_desk_a31.cjs")],env={**os.environ,"A31_URL":url,"A31_WRITER":tokens["writer"],"A31_READER":tokens["reader"]},check=True,timeout=90)
        call("session-logout",{},reader)
        call("clients",{"after":""},reader,expected=401)
    finally:stop(p)
    p,url=start()
    try:
        reader=login("reader")
        assert q("ticket-totals",{"ticket_id":"t01"})==[["t01",5,105,4000]]
        assert q("tickets",{"closed":False,"after":""})[0][-1]=="w05"
        rows=q("events",{"ticket_id":"t01","after":""});assert len(rows)==5
        assert {r[1] for r in rows}=={"created","work","closed","reopened"}
    finally:stop(p)
    assert json.loads(run("migrate",*migrate,cwd=bundle))["current_version"]==14
    run("project","verify-package",bundle)
    assert snapshot=={str(p.relative_to(bundle)):p.read_bytes() for p in bundle.rglob("*") if p.is_file()}
    r=subprocess.run([str(DB),"verify",str(db)],check=True,capture_output=True,text=True)
    assert json.loads(r.stdout)["verified"]
    print("PASS A31",calls,"direct HTTP requests; 14 migrations; 5 linked tables; atomic workflow and two-writer conflict; history 105 minutes / 4000 RUB; pagination, restart, package integrity")
if __name__=="__main__":main()
