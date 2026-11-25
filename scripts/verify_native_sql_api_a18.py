#!/usr/bin/env python3
"""A18 private digest file, read/write authorization, principal-scoped durable replay."""
import hashlib,json,os,secrets,selectors,subprocess,tempfile,urllib.request,urllib.error
from pathlib import Path
from sql_test_backend import db_command, backend_args, database_bytes
ROOT=Path(__file__).resolve().parents[1]
BIN=Path(os.environ["SEDRAVA_NATIVE_BIN"]);DB=Path(os.environ["SEDRAVASQL_NATIVE_BIN"])
API=ROOT/"examples/database/orders_api.sdr"
def cmd(args,fail=False):
    p=subprocess.run([str(x) for x in args],capture_output=True,text=True,timeout=15)
    assert (p.returncode!=0)==fail,(p.stdout,p.stderr)
def main():
 with tempfile.TemporaryDirectory(prefix="sedrava-a18-") as t:
    db=Path(t)/"db";auth=Path(t)/"auth.json"
    tokens={n:secrets.token_hex(32) for n in ("reader","writer","other")}
    records=[{"id":n,"sha256":hashlib.sha256(token.encode()).hexdigest(),"role":"read" if n=="reader" else "write"} for n,token in tokens.items()]
    auth.write_text(json.dumps(records));auth.chmod(0o600)
    cmd([DB,db_command("init"),db]);cmd([DB,db_command("sql"),db,"CREATE TABLE Orders (id TEXT PRIMARY KEY, amount INT, paid BOOL, note TEXT)","create-orders-001"])
    base=[BIN,"database-api","run",API,*backend_args(),"--database",db,"--trusted","--allow-write","--auth-file",auth,"--idle-ms","5000"]
    auth.chmod(0o644);cmd(base,fail=True);auth.chmod(0o600)
    auth.write_text(json.dumps(records+[records[0]]));cmd(base,fail=True);auth.write_text(json.dumps(records))
    def start(n):
        p=subprocess.Popen([str(x) for x in [*base,"--max-requests",n]],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        try:
            with selectors.DefaultSelector() as sel:
                sel.register(p.stdout,selectors.EVENT_READ);assert sel.select(10)
                line=p.stdout.readline().strip()
            assert line.startswith("LISTENING http://127.0.0.1:"),line
            return p,line.split(" ",1)[1]
        except:
            p.kill();p.wait();raise
    def req(url,path,body,token=None,key=None):
        h={"Content-Type":"application/json"}
        if token:h["Authorization"]="Bearer "+token
        if key:h["Idempotency-Key"]=key
        q=urllib.request.Request(url+path,data=json.dumps(body).encode(),headers=h,method="POST")
        try:r=urllib.request.urlopen(q,timeout=5)
        except urllib.error.HTTPError as e:r=e
        with r:return r.status,json.loads(r.read()),dict(r.headers)
    payload={"id":"o1","amount":42,"note":"test"}
    key="same-request-001"
    before=database_bytes(db)
    p,url=start(9)
    try:
        assert req(url,"/summary",{})[0]==401
        assert req(url,"/summary",{},"0"*64)[0]==401
        assert req(url,"/insert",payload,tokens["reader"],key)[0]==403
        assert database_bytes(db)==before
        assert req(url,"/summary",{},tokens["reader"])[1]["rows"]==[[0,None]]
        code,first,_=req(url,"/insert",payload,tokens["writer"],key);assert code==200 and first["affected"]==1
        assert req(url,"/insert",payload,tokens["writer"],key)[1]["replayed"]
        assert req(url,"/insert",{**payload,"id":"o2"},tokens["other"],key)[0]==200
        assert req(url,"/summary",{},tokens["reader"])[1]["rows"]==[[2,84]]
        assert req(url,"/paid",{"id":"o1"},tokens["reader"],key)[0]==403
        assert p.wait(timeout=8)==0,p.stderr.read()
    finally:
        if p.poll() is None:p.kill();p.wait()
    before=database_bytes(db)
    p,url=start(2)
    try:
        assert req(url,"/insert",payload,tokens["writer"],key)[1]=={**first,"replayed":True}
        assert req(url,"/insert",{**payload,"amount":43},tokens["writer"],key)[0]==409
        assert p.wait(timeout=8)==0,p.stderr.read()
        assert database_bytes(db)==before
    finally:
        if p.poll() is None:p.kill();p.wait()
    cmd([DB,db_command("verify"),db])
 print("PASS A18: 11 HTTP requests, missing/wrong credential denied, role authorization, principal-scoped replay, private/duplicate credential guards, restart and unchanged journal")
if __name__=="__main__":main()
