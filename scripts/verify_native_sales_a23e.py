#!/usr/bin/env python3
"""Generate WebApp from Sedrava; exercise actual SQL server with temporary data."""
import hashlib,json,os,secrets,selectors,subprocess,tempfile
from pathlib import Path
from verify_sales_web_a22 import BIN,DB,DEMO,ROOT,cmd,req
def main():
 with tempfile.TemporaryDirectory(prefix="sedrava-a23e-") as t:
    root=Path(t);db=root/"sales.log";auth=root/"auth.json";ui=root/"generated"
    tokens={n:secrets.token_hex(32) for n in ("reader","writer")}
    auth.write_text(json.dumps([{"id":n,"sha256":hashlib.sha256(v.encode()).hexdigest(),"role":"read" if n=="reader" else "write"} for n,v in tokens.items()]));auth.chmod(0o600)
    cmd([BIN,"build","webapp",DEMO/"native_app.sdr","--output",ui])
    assert {p.name for p in ui.iterdir()}=={"index.html","app.css","app.js"}
    source=(DEMO/"native_app.sdr").read_text()
    for i,(old,new) in enumerate([
        ("auth session","auth bearer"),
        ("auth session","auth session\n    cache true"),
        ('path "/products-page"','path "//example.invalid/data"'),
        ('body-field after cursor','body-field after cursor\n    body-field after cursor'),
        ('body-field after cursor','body-field after missing'),
        ('session "Ключ доступа"','paragraph "No session control"'),
        ('session "Ключ доступа"','session "Ключ доступа"\n            session "Duplicate"'),
    ]):
        bad=root/f"bad{i}.sdr";bad.write_text(source.replace(old,new,1))
        cmd([BIN,"build","webapp",bad,"--output",root/f"bad{i}"],fail=True)
    cmd([DB,"init",db])
    for i,q in enumerate((DEMO/"schema.sql").read_text().splitlines()):cmd([DB,"sql",db,q,f"demo-schema-{i:04}"])
    args=[BIN,"database-api","run",DEMO/"sales_api.sdr","--database",db,"--trusted","--allow-write","--auth-file",auth,"--web-ui",ui,"--session-ttl",60,"--max-requests",1000,"--idle-ms",30000]
    p=subprocess.Popen([str(x) for x in args],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    def call(url,path,authorization,body,key=None,status=200):
        raw,h=req(url,path,"POST",body,key=key,headers={"Authorization":authorization},expected=status)
        return json.loads(raw)
    try:
        with selectors.DefaultSelector() as sel:
            sel.register(p.stdout,selectors.EVENT_READ);assert sel.select(12)
            line=p.stdout.readline().strip()
        assert line.startswith("LISTENING http://127.0.0.1:"),line;url=line.split(" ",1)[1]
        for path,name,mime in [("/","index.html","text/html"),("/app.js","app.js","text/javascript"),("/app.css","app.css","text/css")]:
            raw,h=req(url,path);assert raw==(ui/name).read_bytes()
            assert h["Content-Type"].startswith(mime) and "connect-src 'self'" in h["Content-Security-Policy"]
        def login(user):return "Session "+call(url,"/session-login","Bearer "+tokens[user],{})["token"]
        w=login("writer");r=login("reader")
        item={"id":"p1","title":"Начальный","category":"food","price":10}
        call(url,"/add-product",w,item,"a23e-initial-001")
        rows=call(url,"/products-page",r,{"after":""})
        assert rows=={"kind":"rows","columns":["id","title","category","price"],"rows":[["p1","Начальный","food",10]]}
        call(url,"/session-logout",w,{});call(url,"/session-logout",r,{})
        if os.environ.get("SEDRAVA_A22_DOM")=="1":
            subprocess.run(["node",str(ROOT/"scripts/verify_native_sales_a23e.cjs")],env={**os.environ,"SEDRAVA_A22_URL":url,"SEDRAVA_A22_WRITER":tokens["writer"],"SEDRAVA_A22_READER":tokens["reader"]},check=True,timeout=60)
            r=login("reader");assert call(url,"/product-count",r,{})["rows"]==[[2]]
            call(url,"/session-logout",r,{})
    finally:
        p.terminate();p.wait(timeout=8)
        lock=db.with_name(db.name+".lock")
        if lock.exists():assert lock.read_text().strip()==f"pid={p.pid}";lock.unlink()
    cmd([DB,"verify",db])
    print("PASS A23e: native .sdr build, 7 compiler rejections, generated asset delivery, real session API, database verification")
if __name__=="__main__":main()
