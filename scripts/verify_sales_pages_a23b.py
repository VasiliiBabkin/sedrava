#!/usr/bin/env python3
"""A23b: prove pagination beyond the original 100-row limit over real HTTP."""
import hashlib,json,os,secrets,selectors,subprocess,tempfile
from pathlib import Path
from verify_sales_web_a22 import BIN,DB,DEMO,UI,ROOT,cmd,req
def main():
 with tempfile.TemporaryDirectory(prefix="sedrava-a23b-") as t:
    root=Path(t);db=root/"sales.log";auth=root/"auth.json";token=secrets.token_hex(32)
    auth.write_text(json.dumps([{"id":"writer","sha256":hashlib.sha256(token.encode()).hexdigest(),"role":"write"}]));auth.chmod(0o600)
    cmd([DB,"init",db])
    for i,q in enumerate((DEMO/"schema.sql").read_text().splitlines()):cmd([DB,"sql",db,q,f"demo-schema-{i:04}"])
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
    def post(path,body,key=None,status=200):
        nonlocal count
        raw,_=req(url,path,"POST",body,token,key,expected=status);count+=1;return json.loads(raw)
    def traverse(path,prefix,total):
        cursor=""; seen=[];sizes=[]
        while True:
            rows=post(path,{"after":cursor})["rows"]
            assert len(rows)<=26
            batch=rows[:25];sizes.append(len(batch))
            ids=[r[0] for r in batch]
            assert ids==sorted(ids) and all(k>cursor for k in ids)
            seen+=ids
            if len(rows)<=25:break
            cursor=ids[-1]
        assert seen==[f"{prefix}{i:03}" for i in range(total)],seen
        return sizes
    try:
        # Reverse insertion order to test ordered traversal, not insertion order.
        for i in reversed(range(105)):
            body={"product_id":f"p{i:03}","title":f"Товар {i}","category":"food","price":i,"order_id":f"o{i:03}","amount":i}
            post("/new-product-order",body,f"a23-page-seed-{i:03}")
        before=db.read_bytes()
        assert len(post("/products",{})["rows"])==100
        assert len(post("/orders",{})["rows"])==100
        assert post("/product-count",{})["rows"]==[[105]]
        assert traverse("/products-page","p",105)==[25,25,25,25,5]
        assert traverse("/orders-page","o",105)==[25,25,25,25,5]
        assert post("/products-page",{"after":"p104"})["rows"]==[]
        assert post("/orders-page",{"after":"o104"})["rows"]==[]
        assert post("/products-page",{"after":"p001a"})["rows"][0][0]=="p002"
        assert post("/products-page",{"after":"x"*129},status=422)=={"error":{"code":"REQUEST_REQUIREMENT_FAILED"}}
        assert post("/orders-page",{"after":10},status=422)=={"error":{"code":"REQUEST_SCHEMA_MISMATCH"}}
        assert db.read_bytes()==before
        if os.environ.get("SEDRAVA_A22_DOM")=="1":
            subprocess.run(["node",str(ROOT/"scripts/verify_sales_pages_a23b.cjs")],env={**os.environ,"SEDRAVA_A22_URL":url,"SEDRAVA_A22_WRITER":token},check=True,timeout=60)
            total=106
        else:total=105
    finally:stop(p)
    p,url=start()
    try:
        assert post("/product-count",{})["rows"]==[[105]]
        assert traverse("/orders-page","o",total)==[25,25,25,25,total-100]
    finally:stop(p)
    cmd([DB,"verify",db])
    print(f"PASS A23b: {count} direct HTTP requests, 105 products and {total} orders, ordered five-page traversal, lookahead, invalid cursor, no-write reads, restart")
if __name__=="__main__":main()
