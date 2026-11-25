#!/usr/bin/env python3
"""A20: actual authenticated multi-statement SQL routes + FK integrity."""
import hashlib,json,os,secrets,selectors,subprocess,tempfile,urllib.request,urllib.error
from pathlib import Path
from sql_test_backend import db_command, backend_args, database_bytes
from verify_sales_demo_a19 import BIN,DB,DEMO,cmd
def main():
 with tempfile.TemporaryDirectory(prefix="sedrava-a20-") as t:
    root=Path(t);db=root/"db";auth=root/"auth.json";token=secrets.token_hex(32)
    auth.write_text(json.dumps([{"id":"writer","sha256":hashlib.sha256(token.encode()).hexdigest(),"role":"write"}]));auth.chmod(0o600)
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
    def req(url,path,body,key=None,status=200):
        h={"Content-Type":"application/json","Authorization":"Bearer "+token}
        if key:h["Idempotency-Key"]=key
        q=urllib.request.Request(url+path,data=json.dumps(body).encode(),headers=h,method="POST")
        try:r=urllib.request.urlopen(q,timeout=5)
        except urllib.error.HTTPError as e:r=e
        with r:
            result=json.loads(r.read());assert r.status==status,(path,r.status,result);return result
    def digest():return hashlib.sha256(database_bytes(db)).hexdigest()
    data={"product_id":"p1","title":"Молоко","category":"food","price":100,"order_id":"o1","amount":200}
    p,url=start(7)
    try:
        first=req(url,"/new-product-order",data,"demo-transaction-001");assert first["affected"]==2
        before=digest()
        assert req(url,"/new-product-order",data,"demo-transaction-001")=={**first,"replayed":True}
        req(url,"/new-product-order",{**data,"product_id":"p2"},"demo-transaction-002",409)
        req(url,"/add-order",{"id":"o2","product_id":"missing","amount":100},"demo-transaction-003",409)
        assert req(url,"/products",{})["rows"]==[["p1","Молоко","food",100]]
        assert req(url,"/orders",{})["rows"]==[["o1","Молоко",200,False]]
        req(url,"/new-product-order",{**data,"amount":"bad"},"demo-transaction-004",422)
        assert p.wait(timeout=8)==0,p.stderr.read()
        assert digest()==before
    finally:
        if p.poll() is None:p.kill();p.wait()
    p,url=start(2)
    try:
        assert req(url,"/new-product-order",data,"demo-transaction-001")=={**first,"replayed":True}
        assert req(url,"/orders",{})["rows"]==[["o1","Молоко",200,False]]
        assert p.wait(timeout=8)==0,p.stderr.read()
        assert digest()==before
    finally:
        if p.poll() is None:p.kill();p.wait()
    cmd([DB,db_command("verify"),db])
 print("PASS A20: 9 authenticated HTTP requests, atomic product+order, FK rejection, no partial writes, typed input and restart replay")
if __name__=="__main__":main()
