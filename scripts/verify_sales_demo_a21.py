#!/usr/bin/env python3
"""A21: sequential transactional HTTP route and durable read observations."""
import hashlib,json,os,secrets,selectors,subprocess,tempfile,urllib.request,urllib.error
from pathlib import Path
from verify_sales_demo_a19 import BIN,DB,DEMO,cmd
def main():
 with tempfile.TemporaryDirectory(prefix="sedrava-a21-") as t:
    root=Path(t);db=root/"db";auth=root/"auth.json";token=secrets.token_hex(32)
    auth.write_text(json.dumps([{"id":"writer","sha256":hashlib.sha256(token.encode()).hexdigest(),"role":"write"}]));auth.chmod(0o600)
    cmd([DB,"init",db])
    for i,q in enumerate((DEMO/"schema.sql").read_text().splitlines()):cmd([DB,"sql",db,q,f"demo-schema-{i:04}"])
    cmd([BIN,"database-api","check",DEMO/"sales_api.sdr"])
    def start(n):
        p=subprocess.Popen([str(x) for x in [BIN,"database-api","run",DEMO/"sales_api.sdr","--database",db,"--trusted","--allow-write","--auth-file",auth,"--idle-ms","5000","--max-requests",n]],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
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
    def digest():return hashlib.sha256(db.read_bytes()).hexdigest()
    data={"product_id":"p1","title":"Молоко","category":"food","price":100,"order_id":"o1","amount":200}
    p,url=start(8)
    try:
        req(url,"/new-product-order",data,"demo-transaction-001")
        change={"id":"o1","old_amount":200,"new_amount":250}
        first=req(url,"/correct-order",change,"demo-sequential-001")
        assert first["kind"]=="transaction" and first["affected"]==1 and [r["rows"] for r in first["reads"]]==[[[200,False]],[[250,False]]]
        before=digest()
        assert req(url,"/correct-order",change,"demo-sequential-001")=={**first,"replayed":True}
        req(url,"/correct-order",change,"demo-sequential-002",409)
        assert digest()==before
        req(url,"/mark-paid",{"id":"o1"},"demo-paid-000001")
        before=digest()
        req(url,"/correct-order",{"id":"o1","old_amount":250,"new_amount":300},"demo-sequential-003",409)
        assert req(url,"/orders",{})["rows"]==[["o1","Молоко",250,True]]
        assert req(url,"/paid-summary",{})["rows"]==[[1,250]]
        assert p.wait(timeout=8)==0,p.stderr.read()
        assert digest()==before
    finally:
        if p.poll() is None:p.kill();p.wait()
    p,url=start(2)
    try:
        assert req(url,"/correct-order",change,"demo-sequential-001")=={**first,"replayed":True}
        assert req(url,"/orders",{})["rows"]==[["o1","Молоко",250,True]]
        assert p.wait(timeout=8)==0,p.stderr.read()
        assert digest()==before
    finally:
        if p.poll() is None:p.kill();p.wait()
    cmd([DB,"verify",db])
 print("PASS A21: 10 authenticated HTTP requests, sequential before/after reads, paid-order refusal, atomic rollback and historical replay")
if __name__=="__main__":main()
