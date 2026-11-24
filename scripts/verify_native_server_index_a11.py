#!/usr/bin/env python3
"""A11 real loopback HTTP over a digest-approved native immutable index."""
import hashlib,json,os,selectors,subprocess,tempfile
from pathlib import Path
from verify_native_server_a3 import assert_reply
ROOT=Path(__file__).resolve().parents[1]
BIN=Path(os.environ["SEDRAVA_NATIVE_BIN"])
DB=Path(os.environ["SEDRAVASQL_NATIVE_BIN"])
SOURCE=ROOT/"examples/native_server/native_a11_index.sdr"
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def cli(*args):
    p=subprocess.run([str(DB),*map(str,args)],capture_output=True,text=True,timeout=15)
    assert p.returncode==0,(args,p.stderr,p.stdout)
    return json.loads(p.stdout)
def args(source,index,sha,extra=()):
    return [str(BIN),"server","run",str(source),"--native-index",str(index),"--native-index-sha256",sha,"--port","0","--max-requests","20","--idle-ms","5000",*extra]
def rejected(source,index,sha,extra=()):
    p=subprocess.run(args(source,index,sha,extra),capture_output=True,text=True,timeout=10)
    assert p.returncode!=0 and "LISTENING" not in p.stdout,(p.stdout,p.stderr)
    assert ("E_SERVER_NATIVE_INDEX" in p.stderr or (extra and "E_SERVER_" in p.stderr)),(p.stdout,p.stderr)
def launch(source,index,sha):
    p=subprocess.Popen(args(source,index,sha),stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,stdin=subprocess.DEVNULL,env={"PATH":"/nonexistent","LC_ALL":"C"})
    with selectors.DefaultSelector() as watcher:
        watcher.register(p.stdout,selectors.EVENT_READ)
        if not watcher.select(10):
            p.kill();p.communicate();raise AssertionError("no startup")
        line=p.stdout.readline().strip()
    if not line.startswith("LISTENING http://127.0.0.1:"):
        p.kill();_,err=p.communicate();raise AssertionError((line,err))
    return p,int(line.rsplit(":",1)[1])
def kill(p):
    if p.poll() is None:p.kill()
    p.communicate(timeout=5)
def main():
    with tempfile.TemporaryDirectory(prefix="sedrava-a11-") as t:
        root=Path(t);log=root/"log";snap=root/"snap";idx=root/"idx";ops=root/"ops.json"
        cli("init",log)
        ops.write_text(json.dumps([dict(namespace="public_notes",key=k,expected_revision=0,change={"kind":"Put","value":v}) for k,v in [("left","левый"),("right","правый"),("deleted","remove"),("oversize","x"*1025)]]))
        cli("batch",log,"a11-cli-initial",ops)
        ops.write_text(json.dumps([dict(namespace="public_notes",key="deleted",expected_revision=1,change={"kind":"Delete"})]))
        cli("batch",log,"a11-cli-delete1",ops)
        before=digest(log);cli("snapshot-create",log,snap,before)
        sd=digest(snap);cli("index-create",snap,idx,sd);approved=digest(idx)
        rejected(SOURCE,idx,"0"*64)
        rejected(SOURCE,idx,"bad")
        rejected(SOURCE,idx,approved,("--transactional",))
        rejected(SOURCE,idx,approved,("--state-dir",str(root)))
        rejected(SOURCE,idx,approved,("--sqlite-v2-state",str(root/"forbidden.sqlite")))
        rejected(ROOT/"examples/native_server/sqlite_a10_snapshot.sdr",idx,approved)
        assert not (root/"forbidden.sqlite").exists()
        child,port=launch(SOURCE,idx,approved)
        pair={"left":"левый","right":"правый","left_revision":1,"right_revision":1}
        try:
            for _ in range(5):assert_reply(port,200,pair,path="/pair")
            assert_reply(port,404,{"error":{"code":"DB_KEY_NOT_FOUND"}},path="/missing")
            assert_reply(port,404,{"error":{"code":"DB_KEY_NOT_FOUND"}},path="/deleted")
            assert_reply(port,405,{"error":{"code":"METHOD_NOT_ALLOWED"}},path="/pair",method="POST")
            # New journal generation does not alter already approved index.
            ops.write_text(json.dumps([dict(namespace="public_notes",key="left",expected_revision=1,change={"kind":"Put","value":"new"})]))
            cli("batch",log,"a11-cli-change1",ops)
            assert_reply(port,200,pair,path="/pair")
            assert digest(idx)==approved and digest(snap)==sd
            assert_reply(port,503,{"error":{"code":"DB_READ_FAILED"}},path="/oversize")
        finally:kill(child)
        child,port=launch(SOURCE,idx,approved)
        try:
            assert_reply(port,200,pair,path="/pair")
            raw=idx.read_bytes();idx.write_bytes(raw[:-1])
            assert_reply(port,503,{"error":{"code":"DB_READ_FAILED"}},path="/pair")
        finally:kill(child)
        rejected(SOURCE,idx,approved)
        assert digest(snap)==sd
        print("PASS A11: verified native index HTTP GETs, multi-key values/revisions, missing/deleted, oversized, read-only startup guards, fixed snapshot, corruption fail-closed")
if __name__=="__main__":main()
