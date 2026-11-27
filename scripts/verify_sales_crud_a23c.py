#!/usr/bin/env python3
"""A23c: temporary database only; explicit value guards, FK, replay, role and restart."""
import hashlib,json,os,secrets,selectors,subprocess,tempfile
from pathlib import Path
from verify_sales_web_a22 import BIN,DB,DEMO,UI,ROOT,cmd,req
def main():
 with tempfile.TemporaryDirectory(prefix="sedrava-a23c-") as t:
    root=Path(t);db=root/"sales.log";auth=root/"auth.json"
    tokens={n:secrets.token_hex(32) for n in ("reader","writer")}
    auth.write_text(json.dumps([{"id":n,"sha256":hashlib.sha256(v.encode()).hexdigest(),"role":"read" if n=="reader" else "write"} for n,v in tokens.items()]));auth.chmod(0o600)
    cmd([DB,"init",db])
    for i,q in enumerate((DEMO/"schema.sql").read_text().splitlines()):cmd([DB,"sql",db,q,f"demo-schema-{i:04}"])
    for n in (24,25):
        source=root/"limit.sdr";source.write_text("database-api Limit\n"+"".join(f'route POST "/r{i}":\n    query "SELECT id FROM Products"\n' for i in range(n)))
        cmd([BIN,"database-api","check",source],fail=n==25)
    args=[BIN,"database-api","run",DEMO/"sales_api.sdr","--database",db,"--trusted","--allow-write","--auth-file",auth,"--web-ui",UI,"--max-requests",1000,"--idle-ms",30000]
    def start():
        p=subprocess.Popen([str(x) for x in args],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
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
    p,url=start();count=0
    def post(path,body,key=None,status=200,role="writer"):
        nonlocal count
        raw,_=req(url,path,"POST",body,tokens[role],key,expected=status);count+=1;return json.loads(raw)
    def reject(path,body,key,status=409,role="writer",code="SQL_CONFLICT"):
        before=db.read_bytes()
        assert post(path,body,key,status,role)=={"error":{"code":code}}
        assert before==db.read_bytes()
    try:
        for i in range(1,5):
            post("/add-product",{"id":f"p{i}","title":f"Товар {i}","category":"food","price":100},f"a23c-product-{i:03}")
        for i in range(1,4):
            post("/add-order",{"id":f"o{i}","product_id":"p1","amount":100},f"a23c-order-{i:03}")
        post("/mark-paid",{"id":"o1"},"a23c-paid-00001")
        old={"id":"p2","old_title":"Товар 2","old_category":"food","old_price":100}
        edit={**old,"title":"Новый товар","category":"home","price":120}
        reject("/edit-product",edit,"a23c-edit-00001",403,"reader","WRITE_FORBIDDEN")
        reject("/edit-product",{**edit,"price":-1},"a23c-edit-00001",422,code="REQUEST_REQUIREMENT_FAILED")
        first=post("/edit-product",edit,"a23c-edit-00001")
        assert first["affected"]==1
        assert post("/edit-product",edit,"a23c-edit-00001")=={**first,"replayed":True}
        reject("/edit-product",edit,"a23c-edit-00002")
        reject("/edit-product",{**edit,"price":121},"a23c-edit-00001")
        assert post("/category",{"category":"home"})["rows"]==[["p2","Новый товар",120]]
        reject("/delete-product",old,"a23c-del-product-1")
        reject("/delete-product",{"id":"p1","old_title":"Товар 1","old_category":"food","old_price":100},"a23c-fk-000001")
        reject("/delete-order",{"id":"o1","old_amount":100},"a23c-del-paid-1")
        reject("/delete-order",{"id":"o2","old_amount":99},"a23c-del-order-1")
        reject("/delete-order",{"id":"o2","old_amount":100},"a23c-del-order-1",403,"reader","WRITE_FORBIDDEN")
        d=post("/delete-order",{"id":"o2","old_amount":100},"a23c-del-order-1")
        assert d["affected"]==1
        assert post("/delete-order",{"id":"o2","old_amount":100},"a23c-del-order-1")=={**d,"replayed":True}
        reject("/delete-order",{"id":"o2","old_amount":100},"a23c-del-order-2")
        delete={"id":"p2","old_title":"Новый товар","old_category":"home","old_price":120}
        result=post("/delete-product",delete,"a23c-del-product-1");assert result["affected"]==1
        assert post("/delete-product",delete,"a23c-del-product-1")=={**result,"replayed":True}
        reject("/add-product",{"id":"p2","title":"Повтор","category":"food","price":1},"a23c-reinsert-1")
        assert post("/product-count",{})["rows"]==[[3]]
        assert post("/paid-summary",{})["rows"]==[[1,100]]
        if os.environ.get("SEDRAVA_A22_DOM")=="1":
            subprocess.run(["node",str(ROOT/"scripts/verify_sales_crud_a23c.cjs")],env={**os.environ,"SEDRAVA_A22_URL":url,"SEDRAVA_A22_WRITER":tokens["writer"]},check=True,timeout=50)
            expected=2;orders=1
        else:expected=3;orders=2
    finally:stop(p)
    p,url=start()
    try:
        before=db.read_bytes()
        assert post("/delete-product",delete,"a23c-del-product-1")=={**result,"replayed":True}
        assert post("/edit-product",edit,"a23c-edit-00001")=={**first,"replayed":True}
        assert post("/product-count",{})["rows"]==[[expected]]
        assert len(post("/orders",{})["rows"])==orders
        assert post("/paid-summary",{})["rows"]==[[1,100]]
        assert before==db.read_bytes()
    finally:stop(p)
    cmd([DB,"verify",db])
    print(f"PASS A23c: {count} direct HTTP requests, 24/25 route cap, value comparison, role checks, FK restrict, paid-order refusal, durable receipt, tombstone, restart")
if __name__=="__main__":main()
