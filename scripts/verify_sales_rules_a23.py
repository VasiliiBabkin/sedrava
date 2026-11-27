#!/usr/bin/env python3
"""A23: direct HTTP and CLI (no browser validation); byte-for-byte no-write checks."""
import hashlib,json,os,secrets,selectors,subprocess,tempfile
from pathlib import Path
from verify_sales_web_a22 import BIN,DB,DEMO,cmd,req
def main():
 with tempfile.TemporaryDirectory(prefix="sedrava-a23-") as t:
    root=Path(t);db=root/"sales.log";auth=root/"auth.json"; token=secrets.token_hex(32)
    auth.write_text(json.dumps([{"id":"writer","sha256":hashlib.sha256(token.encode()).hexdigest(),"role":"write"}]));auth.chmod(0o600)
    cmd([DB,"init",db])
    for i,q in enumerate((DEMO/"schema.sql").read_text().splitlines()):cmd([DB,"sql",db,q,f"demo-schema-{i:04}"])
    cmd([BIN,"database-api","check",DEMO/"sales_api.sdr"])
    source=root/"invalid.sdr";source.write_text('database Invalid\n    param id: text\n    require id range 0 10\n    query "SELECT id FROM Products WHERE id=?"\n')
    cmd([BIN,"database","check",source],fail=True)
    source.write_text('database Guarded\n    param amount: int\n    require amount range 0 100\n    execute "UPDATE Products SET price=? WHERE id=\'p1\'"\n')
    cmd([BIN,"database","check",source])
    before=db.read_bytes()
    result=cmd([BIN,"database","run",source,"--database",db,"--trusted","--allow-write","--request-key","a23-cli-000001","--arg","amount=-1"],fail=True)
    assert "E_DATABASE_RULE" in result.stderr,(result.stdout,result.stderr)
    assert db.read_bytes()==before
    p=subprocess.Popen([str(v) for v in [BIN,"database-api","run",DEMO/"sales_api.sdr","--database",db,"--trusted","--allow-write","--auth-file",auth,"--max-requests",100,"--idle-ms",30000]],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    count=0
    def post(path,body,key=None,status=200):
        nonlocal count
        raw,_=req(url,path,"POST",body,token,key,expected=status);count+=1;return json.loads(raw)
    def reject(path,body,key,code="REQUEST_REQUIREMENT_FAILED"):
        old=db.read_bytes()
        assert post(path,body,key,422)=={"error":{"code":code}}
        assert db.read_bytes()==old,(path,body)
    try:
        with selectors.DefaultSelector() as sel:
            sel.register(p.stdout,selectors.EVENT_READ);assert sel.select(12)
            line=p.stdout.readline().strip()
        assert line.startswith("LISTENING http://127.0.0.1:"),line;url=line.split(" ",1)[1]
        item={"id":"p1","title":"Чай","category":"food","price":0}
        for i,patch in enumerate([{"price":-1},{"id":""},{"id":"a/b"},{"id":"я"},{"id":"x"*129},{"title":""},{"title":"\u2003"},{"title":"я"*129},{"category":" "},{"category":"x"*129}]):
            reject("/add-product",{**item,**patch},"a23-product-0001")
        reject("/add-product",{**item,"price":2147483648},"a23-product-0001","REQUEST_SCHEMA_MISMATCH")
        first=post("/add-product",item,"a23-product-0001");assert not first["replayed"]
        assert post("/add-product",item,"a23-product-0001")=={**first,"replayed":True}
        assert post("/products",{})["rows"]==[["p1","Чай","food",0]]
        order={"id":"o1","product_id":"p1","amount":10}
        reject("/add-order",{**order,"amount":-1},"a23-order-00001")
        reject("/add-order",{**order,"product_id":"p/1"},"a23-order-00001")
        post("/add-order",order,"a23-order-00001")
        correction={"id":"o1","old_amount":10,"new_amount":0}
        reject("/correct-order",{**correction,"old_amount":-1},"a23-correct-001")
        reject("/correct-order",{**correction,"new_amount":-1},"a23-correct-001")
        post("/correct-order",correction,"a23-correct-001")
        atomic={"product_id":"p2","title":"я"*128,"category":"food","price":2147483647,"order_id":"o2","amount":0}
        reject("/new-product-order",{**atomic,"amount":-1},"a23-atomic-0001")
        reject("/new-product-order",{**atomic,"price":-1},"a23-atomic-0001")
        assert len(post("/products",{})["rows"])==1
        post("/new-product-order",atomic,"a23-atomic-0001")
        reject("/mark-paid",{"id":"o/1"},"a23-paid-000001")
        post("/mark-paid",{"id":"o1"},"a23-paid-000001")
        reject("/top-products",{"minimum":-1},None)
        reject("/category",{"category":"\u2003"},None)
        assert post("/paid-summary",{})["rows"]==[[1,0]]
        assert len(post("/products",{})["rows"])==2
    finally:
        p.terminate();p.wait(timeout=8)
        lock=db.with_name(db.name+".lock")
        if lock.exists():assert lock.read_text().strip()==f"pid={p.pid}";lock.unlink()
    cmd([DB,"verify",db])
    print(f"PASS A23: {count} real HTTP requests, guards, Unicode limits, invalid declaration, CLI denial, unchanged journal, retry key reuse, atomic and sequential writes")
if __name__=="__main__":main()
