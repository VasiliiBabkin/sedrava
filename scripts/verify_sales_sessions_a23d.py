#!/usr/bin/env python3
"""A23d native session acceptance on disposable data, synthetic credentials."""
import hashlib,json,os,secrets,selectors,subprocess,tempfile,time
from pathlib import Path
from verify_sales_web_a22 import BIN,DB,DEMO,UI,ROOT,cmd,req
def main():
 with tempfile.TemporaryDirectory(prefix="sedrava-a23d-") as t:
    root=Path(t);db=root/"sales.log";auth=root/"auth.json"
    tokens={n:secrets.token_hex(32) for n in ("reader","writer","writer2")}
    auth.write_text(json.dumps([{"id":n,"sha256":hashlib.sha256(v.encode()).hexdigest(),"role":"read" if n=="reader" else "write"} for n,v in tokens.items()]));auth.chmod(0o600)
    cmd([DB,"init",db])
    for i,q in enumerate((DEMO/"schema.sql").read_text().splitlines()):cmd([DB,"sql",db,q,f"demo-schema-{i:04}"])
    base=[BIN,"database-api","run",DEMO/"sales_api.sdr","--database",db,"--trusted","--allow-write"]
    cmd([*base,"--session-ttl",60],fail=True)
    base += ["--auth-file",auth,"--web-ui",UI,"--max-requests",1000,"--idle-ms",30000]
    cmd([*base,"--session-ttl",0],fail=True)
    cmd([*base,"--session-ttl",3601],fail=True)
    collision=root/"collision.sdr";collision.write_text('database-api Collision\nroute POST "/session-login":\n    query "SELECT id FROM Products"\n')
    cmd([BIN,"database-api","run",collision,"--database",db,"--trusted","--auth-file",auth,"--session-ttl",60],fail=True)
    def start(ttl):
        p=subprocess.Popen([str(x) for x in [*base,"--session-ttl",ttl]],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        try:
            with selectors.DefaultSelector() as sel:
                sel.register(p.stdout,selectors.EVENT_READ);assert sel.select(12)
                line=p.stdout.readline().strip()
            assert line.startswith("LISTENING http://127.0.0.1:"),line
            return p,line.split(" ",1)[1]
        except:
            p.kill();p.wait();raise
    def stop(p):
        p.terminate();p.wait(timeout=8)
        lock=db.with_name(db.name+".lock")
        if lock.exists():assert lock.read_text().strip()==f"pid={p.pid}";lock.unlink()
    count=0
    def call(path,authorization=None,data=None,status=200,key=None,method="POST"):
        nonlocal count
        headers={"Authorization":authorization} if authorization else {}
        raw,h=req(url,path,method,({} if data is None else data) if method=="POST" else None,key=key,headers=headers,expected=status)
        count+=1;assert h["Cache-Control"]=="no-store"
        return json.loads(raw),h
    def login(user,ttl=60):
        r,_=call("/session-login","Bearer "+tokens[user])
        assert r["principal"]==user and r["role"]==("read" if user=="reader" else "write") and r["expires_in"]==ttl
        assert len(r["token"])==64 and all(c in "0123456789abcdef" for c in r["token"])
        assert r["token"] not in tokens.values()
        return "Session "+r["token"]
    def denied(path,authz,status=401,code="AUTH_REQUIRED",**kwargs):
        old=db.read_bytes();r,h=call(path,authz,status=status,**kwargs)
        assert r=={"error":{"code":code}},r
        assert db.read_bytes()==old
        return h
    item={"id":"p1","title":"Чай","category":"food","price":15}
    p,url=start(60)
    try:
        assert call("/session-policy",method="GET")[0]=={"sessions":True}
        before=db.read_bytes()
        denied("/session-login","Bearer "+secrets.token_hex(32))
        denied("/session-login",None)
        denied("/session-login","Bearer "+tokens["writer"],status=400,code="SESSION_EMPTY_OBJECT_REQUIRED",data={"x":1})
        denied("/session-login","Bearer "+tokens["writer"],status=400,code="SESSION_HEADERS_UNSUPPORTED",key="a23d-invalid-1")
        assert denied("/products","Bearer "+tokens["writer"])["WWW-Authenticate"]=="Session"
        r=login("reader");w=login("writer")
        assert r!=w
        denied("/session-login",w)
        denied("/products","Bearer "+w.split(" ",1)[1])
        assert call("/products",r)[0]["rows"]==[]
        assert db.read_bytes()==before
        denied("/add-product",r,status=403,code="WRITE_FORBIDDEN",data=item,key="a23d-product-001")
        receipt,_=call("/add-product",w,item,key="a23d-product-001");assert receipt["affected"]==1 and not receipt["replayed"]
        assert call("/session-logout",w)[0]=={"revoked":True}
        denied("/products",w)
        denied("/session-logout",w)
        denied("/session-logout","Bearer "+tokens["writer"])
        w=login("writer")
        assert call("/add-product",w,item,key="a23d-product-001")[0]=={**receipt,"replayed":True}
        other=login("writer2")
        denied("/add-product",other,status=409,code="SQL_CONFLICT",data=item,key="a23d-product-001")
        more=[login("writer") for _ in range(3)]
        assert len(set([w,*more]))==4
        denied("/session-login","Bearer "+tokens["writer"],status=429,code="SESSION_CAPACITY")
        call("/session-logout",more.pop())
        new=login("writer")
        for s in [r,w,other,*more,new]:call("/session-logout",s)
        if os.environ.get("SEDRAVA_A22_DOM")=="1":
            subprocess.run(["node",str(ROOT/"scripts/verify_sales_sessions_a23d.cjs")],env={**os.environ,"SEDRAVA_A22_URL":url,"SEDRAVA_A22_WRITER":tokens["writer"],"SEDRAVA_A22_READER":tokens["reader"]},check=True,timeout=50)
        alive=login("writer")
    finally:stop(p)
    p,url=start(1)
    try:
        denied("/products",alive)
        short=login("writer",1)
        assert call("/products",short)[0]["rows"]
        time.sleep(1.25)
        denied("/products",short)
        denied("/session-logout",short)
        again=login("writer",1)
        assert call("/add-product",again,item,key="a23d-product-001")[0]=={**receipt,"replayed":True}
    finally:stop(p)
    cmd([DB,"verify",db])
    print(f"PASS A23d: {count} direct HTTP requests, mode validation, session-only auth, role, per-user capacity, revocation, TTL, restart, principal-scoped receipts")
if __name__=="__main__":main()
