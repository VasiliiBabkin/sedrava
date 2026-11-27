#!/usr/bin/env python3
"""A24: migration-gated startup and generated WebApp on migrated disposable DB."""
import hashlib,json,os,secrets,selectors,socket,subprocess,tempfile
from pathlib import Path
from verify_sales_web_a22 import BIN,DB,DEMO,ROOT,cmd,req
def main():
 with tempfile.TemporaryDirectory(prefix="sedrava-a24-") as t:
    root=Path(t);db=root/"sales.log";auth=root/"auth.json";ui=root/"generated";manifest=root/"migrations.json"
    plan=json.loads((DEMO/"migrations.json").read_text())
    initial={**plan,"steps":plan["steps"][:2]}
    manifest.write_text(json.dumps(initial))
    tokens={n:secrets.token_hex(32) for n in ("reader","writer")}
    auth.write_text(json.dumps([{"id":n,"sha256":hashlib.sha256(v.encode()).hexdigest(),"role":"read" if n=="reader" else "write"} for n,v in tokens.items()]));auth.chmod(0o600)
    cmd([DB,"init",db]);cmd([BIN,"build","webapp",DEMO/"native_app.sdr","--output",ui])
    base=[BIN,"database-api","run",DEMO/"sales_api.sdr","--database",db,"--trusted","--allow-write","--auth-file",auth,"--web-ui",ui,"--session-ttl",60,"--max-requests",1000,"--idle-ms",30000]
    args=[*base,"--migrations",manifest]
    before=db.read_bytes()
    for bad in [args,[*base,"--apply-migrations"],[*base,"--migrations","migrations.json"],[*[x for x in args if x!="--allow-write"],"--apply-migrations"]]:
        result=cmd(bad,fail=True);assert "LISTENING" not in result.stdout;assert db.read_bytes()==before
    with socket.socket() as s:
        s.bind(("127.0.0.1",0));s.listen()
        result=cmd([*args,"--apply-migrations","--port",s.getsockname()[1]],fail=True)
        assert "E_SQL_API_BIND" in result.stderr;assert db.read_bytes()==before
    def start(apply=False):
        p=subprocess.Popen([str(x) for x in [*args,*(["--apply-migrations"] if apply else [])]],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        try:
            with selectors.DefaultSelector() as sel:
                sel.register(p.stdout,selectors.EVENT_READ);assert sel.select(15)
                line=p.stdout.readline().strip()
            assert line.startswith("LISTENING http://127.0.0.1:"),line
            return p,line.split(" ",1)[1]
        except:
            p.kill();p.wait();raise
    def stop(p):
        p.terminate();p.wait(timeout=8)
        lock=db.with_name(db.name+".lock")
        if lock.exists():assert lock.read_text().strip()==f"pid={p.pid}";lock.unlink()
    def status():
        return json.loads(cmd([DB,"migration-status",db,manifest]).stdout)
    count=0
    def call(url,path,authorization,body,key=None,expected=200):
        nonlocal count
        raw,_=req(url,path,"POST",body,key=key,headers={"Authorization":authorization},expected=expected);count+=1
        return json.loads(raw)
    def login(url,user):return "Session "+call(url,"/session-login","Bearer "+tokens[user],{})["token"]
    p,url=start(True)
    try:
        w=login(url,"writer")
        call(url,"/add-product",w,{"id":"p1","title":"Начальный","category":"food","price":10},"a24-seed-product-01")
        call(url,"/add-order",w,{"id":"o1","product_id":"p1","amount":20},"a24-seed-order-001")
        call(url,"/session-logout",w,{})
    finally:stop(p)
    assert status()["current_version"]==2
    manifest.write_text(json.dumps(plan))
    before=db.read_bytes()
    assert status()["pending"]==[3,4,5]
    result=cmd(args,fail=True);assert "pending migrations" in result.stderr;assert db.read_bytes()==before
    p,url=start(True)
    try:
        w=login(url,"writer")
        assert call(url,"/orders",w,{})["rows"]==[["o1","Начальный",20,False]]
        call(url,"/add-order",w,{"id":"bad","product_id":"absent","amount":1},"a24-orphan-0001",expected=409)
        call(url,"/session-logout",w,{})
        for path,name in [("/","index.html"),("/app.js","app.js"),("/app.css","app.css")]:
            raw,_=req(url,path);assert raw==(ui/name).read_bytes()
        if os.environ.get("SEDRAVA_A22_DOM")=="1":
            subprocess.run(["node",str(ROOT/"scripts/verify_native_sales_a23e.cjs")],env={**os.environ,"SEDRAVA_A22_URL":url,"SEDRAVA_A22_WRITER":tokens["writer"],"SEDRAVA_A22_READER":tokens["reader"]},check=True,timeout=60)
    finally:stop(p)
    assert status()["current_version"]==5;assert status()["pending"]==[]
    before=db.read_bytes()
    for apply in [False,True]:
        p,url=start(apply)
        try:
            r=login(url,"reader")
            assert call(url,"/product-count",r,{})["rows"]==[[2 if os.environ.get("SEDRAVA_A22_DOM")=="1" else 1]]
            assert call(url,"/orders",r,{})["rows"]==[["o1","Начальный",20,False]]
            call(url,"/session-logout",r,{})
        finally:stop(p)
        assert db.read_bytes()==before
    changed=json.loads(json.dumps(plan));changed["steps"][0]["sql"]+=" "
    for bad in [initial,changed]:
        manifest.write_text(json.dumps(bad))
        result=cmd([*args,"--apply-migrations"],fail=True);assert "E_SQL_MIGRATION" in result.stderr;assert "LISTENING" not in result.stdout;assert db.read_bytes()==before
    manifest.write_text(json.dumps(plan));cmd([DB,"verify",db])
    print(f"PASS A24: {count} direct HTTP requests, 5 migration versions, pending gate, port conflict without write, explicit upgrade, data/FK, repeat with byte-identical journal, downgrade/modified manifest refusal")
if __name__=="__main__":main()
