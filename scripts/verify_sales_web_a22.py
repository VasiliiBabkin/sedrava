#!/usr/bin/env python3
"""A22 real loopback HTTP and optional DOM acceptance; temporary data only."""
import hashlib,json,os,secrets,selectors,subprocess,tempfile,urllib.request,urllib.error,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];BIN=Path(os.environ["SEDRAVA_NATIVE_BIN"]);DB=Path(os.environ["SEDRAVASQL_NATIVE_BIN"])
DEMO=ROOT/"examples/sales_demo"; UI=DEMO/"ui"
def cmd(args,fail=False):
    p=subprocess.run([str(x) for x in args],capture_output=True,text=True,timeout=20)
    assert (p.returncode!=0)==fail,(p.stdout,p.stderr)
    return p
def req(url,path,method="GET",data=None,token=None,key=None,headers=None,expected=200):
    h=dict(headers or {})
    if data is not None:h["Content-Type"]="application/json";data=json.dumps(data).encode()
    if token:h["Authorization"]="Bearer "+token
    if key:h["Idempotency-Key"]=key
    q=urllib.request.Request(url+path,data=data,headers=h,method=method)
    try:r=urllib.request.urlopen(q,timeout=8)
    except urllib.error.HTTPError as e:r=e
    with r:
        body=r.read();assert r.status==expected,(path,r.status,body)
        return body,r.headers
def main():
 with tempfile.TemporaryDirectory(prefix="sedrava-a22-") as t:
    root=Path(t);db=root/"sales.log";auth=root/"auth.json"
    tokens={n:secrets.token_hex(32) for n in ("reader","writer")}
    auth.write_text(json.dumps([{"id":n,"sha256":hashlib.sha256(v.encode()).hexdigest(),"role":"read" if n=="reader" else "write"} for n,v in tokens.items()]));auth.chmod(0o600)
    cmd([DB,"init",db])
    for i,q in enumerate((DEMO/"schema.sql").read_text().splitlines()):cmd([DB,"sql",db,q,f"demo-schema-{i:04}"])
    base=[BIN,"database-api","run",DEMO/"sales_api.sdr","--database",db,"--trusted","--allow-write","--web-ui",UI]
    cmd(base,fail=True) # UI requires authentication
    base += ["--auth-file",auth,"--idle-ms","120000","--max-requests","1000"]
    cmd([*base,"--web-ui",UI],fail=True) # duplicate
    bad=root/"bad";shutil.copytree(UI,bad);(bad/"app.js").unlink();(bad/"app.js").symlink_to(auth)
    cmd([BIN,"database-api","run",DEMO/"sales_api.sdr","--database",db,"--trusted","--allow-write","--auth-file",auth,"--web-ui",bad],fail=True)
    def start():
        p=subprocess.Popen([str(x) for x in base],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
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
        # Terminating the native preview leaves its exclusive lock; inspect
        # exact PID and clear only in this private test directory.
        lock=db.with_name(db.name+".lock")
        if lock.exists():
            assert lock.read_text().strip()==f"pid={p.pid}"
            lock.unlink()
    p,url=start()
    try:
        for path,file,mime in [("/","index.html","text/html"),("/ui-script","app.js","text/javascript"),("/ui-style","app.css","text/css")]:
            body,h=req(url,path);assert body==(UI/file).read_bytes()
            assert h["Content-Type"].startswith(mime);assert h["Cache-Control"]=="no-store"
            assert "connect-src 'self'" in h["Content-Security-Policy"] and "frame-ancestors 'none'" in h["Content-Security-Policy"]
            assert h["X-Content-Type-Options"]=="nosniff" and h["Referrer-Policy"]=="no-referrer"
            assert not h.get("Access-Control-Allow-Origin")
        req(url,"/","POST",{},expected=405)
        req(url,"/ui-script",headers={"Host":"evil.example"},expected=400)
        req(url,"/../auth",expected=400)
        req(url,"/auth",expected=401)
        req(url,"/products","POST",{},expected=401)
        if os.environ.get("SEDRAVA_A22_DOM")=="1":
            env={**os.environ,"SEDRAVA_A22_URL":url,"SEDRAVA_A22_WRITER":tokens["writer"],"SEDRAVA_A22_READER":tokens["reader"]}
            subprocess.run(["node",str(ROOT/"scripts/verify_sales_web_a22.cjs")],env=env,check=True,timeout=45)
            expect_products=2;expect_revenue=175
        else:
            item={"id":"p1","title":"Чай","category":"food","price":100}
            req(url,"/add-product","POST",item,tokens["reader"],"a22-product-0001",expected=403)
            req(url,"/add-product","POST",item,tokens["writer"],"a22-product-0001")
            req(url,"/add-order","POST",{"id":"o1","product_id":"p1","amount":175},tokens["writer"],"a22-order-00001")
            req(url,"/mark-paid","POST",{"id":"o1"},tokens["writer"],"a22-payment-001")
            expect_products=1;expect_revenue=175
    finally:stop(p)
    p,url=start()
    try:
        data,_=req(url,"/products","POST",{},tokens["reader"]);assert len(json.loads(data)["rows"])==expect_products
        data,_=req(url,"/paid-summary","POST",{},tokens["reader"]);assert json.loads(data)["rows"]==[[1,expect_revenue]]
    finally:stop(p)
    cmd([DB,"verify",db])
 print("PASS A22 HTTP: exact static assets, CSP, loopback Host, route guard, auth required, symlink refusal, real database restart and verification")
if __name__=="__main__":main()
