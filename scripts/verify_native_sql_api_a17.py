#!/usr/bin/env python3
"""Real loopback HTTP SQL API: static queries, explicit policy, scoped durable receipts."""
import hashlib,json,os,selectors,subprocess,tempfile,urllib.request,urllib.error
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
BIN=Path(os.environ["SEDRAVA_NATIVE_BIN"]);DB=Path(os.environ["SEDRAVASQL_NATIVE_BIN"])
API=ROOT/"examples/database/orders_api.sdr"
def cmd(args,fail=False):
    p=subprocess.run([str(x) for x in args],capture_output=True,text=True,timeout=15)
    assert (p.returncode!=0)==fail,(args,p.stdout,p.stderr)
    return p.stdout
def main():
    with tempfile.TemporaryDirectory(prefix="sedrava-a17-") as t:
        db=Path(t)/"journal"
        cmd([DB,"init",db]);cmd([DB,"sql",db,"CREATE TABLE Orders (id TEXT PRIMARY KEY, amount INT, paid BOOL, note TEXT)","create-orders-001"])
        cmd([BIN,"database-api","check",API])
        base=[BIN,"database-api","run",API,"--database",db,"--trusted","--idle-ms","5000"]
        cmd(base,fail=True)
        def start(n,cap=65536):
            p=subprocess.Popen([str(x) for x in [*base,"--allow-write","--max-requests",n,"--native-max-transactions",cap]],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            with selectors.DefaultSelector() as sel:
                sel.register(p.stdout,selectors.EVENT_READ);assert sel.select(10),"startup timeout"
                line=p.stdout.readline().strip()
            assert line.startswith("LISTENING http://127.0.0.1:"),line
            return p,line.split(" ",1)[1]
        def request(url,path,body,key=None,method="POST",raw=None,ctype="application/json"):
            headers={"Content-Type":ctype}
            if key:headers["Idempotency-Key"]=key
            data=raw if raw is not None else json.dumps(body).encode()
            q=urllib.request.Request(url+path,data=data,headers=headers,method=method)
            try:r=urllib.request.urlopen(q,timeout=5)
            except urllib.error.HTTPError as e:r=e
            with r:return r.status,json.loads(r.read()),dict(r.headers)
        def digest():return hashlib.sha256(db.read_bytes()).hexdigest()
        payload={"id":"o1","amount":42,"note":"x'); DELETE FROM Orders WHERE id='o1'; --"}
        p,url=start(10,2)
        try:
            assert request(url,"/insert",payload)[0]==428
            code,first,_=request(url,"/insert",payload,"insert-order-001");assert code==200 and first["affected"]==1
            before=digest()
            code,again,h=request(url,"/insert",payload,"insert-order-001");assert code==200 and again=={**first,"replayed":True} and h["X-Sedrava-Replayed"]=="true"
            assert request(url,"/insert",{**payload,"amount":43},"insert-order-001")[0]==409
            assert request(url,"/paid",{"id":"o1"},"paid-order-0001")[0]==507
            assert request(url,"/order",{"id":"o1"})[1]["rows"]==[["o1",42,False,payload["note"]]]
            assert request(url,"/summary",{})[1]["rows"]==[[1,42]]
            assert request(url,"/order",{},raw=b'{"id":"o1","id":"o2"}')[0]==400
            assert request(url,"/order",{"id":1})[0]==422
            assert request(url,"/summary",{"sql":"DELETE FROM Orders"})[0]==422
            assert p.wait(timeout=8)==0,p.stderr.read()
            assert digest()==before
        finally:
            if p.poll() is None:p.kill();p.wait()
        p,url=start(4)
        try:
            assert request(url,"/insert",payload,"insert-order-001")[1]["replayed"]
            assert request(url,"/paid",{"id":"o1"},"insert-order-001")[0]==200 # distinct route scope
            assert request(url,"/order",{"id":"o1"})[1]["rows"]==[["o1",42,True,payload["note"]]]
            assert request(url,"/summary",{})[1]["rows"]==[[1,42]]
            assert p.wait(timeout=8)==0,p.stderr.read()
        finally:
            if p.poll() is None:p.kill();p.wait()
        cmd([DB,"verify",db])
    print("PASS A17: 14 HTTP requests, static SQL, typed parameters, aggregate response, scoped replay/restart, capacity, unchanged journal on refusal")
if __name__=="__main__":main()
