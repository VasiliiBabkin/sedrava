#!/usr/bin/env python3
"""A19 demo: real authenticated API over native SQL, no public listener."""
import hashlib,json,os,secrets,selectors,subprocess,tempfile,urllib.request,urllib.error
from pathlib import Path
from sql_test_backend import db_command, backend_args, database_bytes
ROOT=Path(__file__).resolve().parents[1];BIN=Path(os.environ["SEDRAVA_NATIVE_BIN"]);DB=Path(os.environ["SEDRAVASQL_NATIVE_BIN"])
DEMO=ROOT/"examples/sales_demo"
def cmd(args):
    p=subprocess.run([str(x) for x in args],capture_output=True,text=True,timeout=15)
    assert p.returncode==0,(p.stdout,p.stderr)
    return p.stdout
def main():
 with tempfile.TemporaryDirectory(prefix="sedrava-sales-") as temp:
    root=Path(temp);db=root/"sales.log";auth=root/"auth.json"
    tokens={n:secrets.token_hex(32) for n in ("reader","writer")}
    auth.write_text(json.dumps([{"id":n,"sha256":hashlib.sha256(t.encode()).hexdigest(),"role":"read" if n=="reader" else "write"} for n,t in tokens.items()]));auth.chmod(0o600)
    cmd([DB,db_command("init"),db])
    for i,q in enumerate((DEMO/"schema.sql").read_text().splitlines()):cmd([DB,db_command("sql"),db,q,f"demo-schema-{i:04}"])
    cmd([BIN,"database-api","check",DEMO/"sales_api.sdr"])
    def start(n):
        p=subprocess.Popen([str(x) for x in [BIN,"database-api","run",DEMO/"sales_api.sdr",*backend_args(),"--database",db,"--trusted","--allow-write","--auth-file",auth,"--idle-ms","5000","--max-requests",n]],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        try:
            with selectors.DefaultSelector() as sel:
                sel.register(p.stdout,selectors.EVENT_READ);assert sel.select(10)
                line=p.stdout.readline().strip()
            assert line.startswith("LISTENING http://127.0.0.1:"),line
            return p,line.split(" ",1)[1]
        except:
            p.kill();p.wait();raise
    def req(url,path,body=None,key=None,role="reader",status=200):
        headers={"Content-Type":"application/json","Authorization":"Bearer "+tokens[role]}
        if key:headers["Idempotency-Key"]=key
        request=urllib.request.Request(url+path,data=json.dumps(body if body is not None else {}).encode(),headers=headers,method="POST")
        try:r=urllib.request.urlopen(request,timeout=5)
        except urllib.error.HTTPError as e:r=e
        with r:
            result=json.loads(r.read());assert r.status==status,(path,r.status,result);return result
    p,url=start(16)
    try:
        products=[{"id":"p1","title":"Молоко","category":"food","price":100},{"id":"p2","title":"Хлеб","category":"food","price":50},{"id":"p3","title":"Кружка","category":"home","price":300}]
        for i,item in enumerate(products):req(url,"/add-product",item,f"demo-product-{i:04}","writer")
        assert req(url,"/categories")["rows"]==[["food"],["home"]]
        assert len(req(url,"/category",{"category":"food"})["rows"])==2
        assert len(req(url,"/category",{"category":"food"})["rows"])==2 # warmed cache
        req(url,"/add-product",{"id":"p4","title":"Чай","category":"food","price":200},"demo-product-0004","writer")
        assert len(req(url,"/category",{"category":"food"})["rows"])==3 # invalidated cache
        a={"id":"o1","product_id":"p1","amount":200}
        receipt=req(url,"/add-order",a,"demo-order-0001","writer")
        assert req(url,"/add-order",a,"demo-order-0001","writer")=={**receipt,"replayed":True}
        req(url,"/add-order",{"id":"o2","product_id":"p2","amount":50},"demo-order-0002","writer")
        assert req(url,"/orders")["rows"]==[["o1","Молоко",200,False],["o2","Хлеб",50,False]]
        req(url,"/mark-paid",{"id":"o1"},"demo-paid-00001","reader",403)
        assert req(url,"/paid-summary")["rows"]==[[0,None]]
        req(url,"/mark-paid",{"id":"o1"},"demo-paid-00001","writer")
        assert req(url,"/paid-summary")["rows"]==[[1,200]]
        assert p.wait(timeout=8)==0,p.stderr.read()
    finally:
        if p.poll() is None:p.kill();p.wait()
    p,url=start(3)
    try:
        assert req(url,"/top-products",{"minimum":100})["rows"]==[["p1",200]]
        assert req(url,"/top-products",{"minimum":201})["rows"]==[]
        assert len(req(url,"/products")["rows"])==4
        assert p.wait(timeout=8)==0,p.stderr.read()
    finally:
        if p.poll() is None:p.kill();p.wait()
    cmd([DB,db_command("verify"),db])
 print("PASS A19 demo: 19 authenticated HTTP requests, catalog, cached index invalidation, orders, JOIN, payment flag, revenue, HAVING and restart")
if __name__=="__main__":main()
