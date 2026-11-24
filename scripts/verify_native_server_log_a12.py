#!/usr/bin/env python3
"""A12/A13: real loopback HTTP, native atomic commits, restart, fail-closed faults."""
import hashlib,json,os,selectors,subprocess,tempfile
from pathlib import Path
from verify_native_server_a3 import req,assert_reply
ROOT=Path(__file__).resolve().parents[1]
BIN=Path(os.environ["SEDRAVA_NATIVE_BIN"])
DB=Path(os.environ["SEDRAVASQL_NATIVE_BIN"])
SOURCE=ROOT/"examples/native_server/native_a12_log.sdr"
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def cli(*args,ok=True):
    p=subprocess.run([str(DB),*map(str,args)],capture_output=True,text=True,timeout=15)
    assert (p.returncode==0)==ok,(args,p.stderr,p.stdout)
    return json.loads(p.stdout) if ok else p.stderr
def args(log,count=20,source=SOURCE,extra=(),transactional=True):
    return [str(BIN),"server","run",str(source),"--native-log",str(log),"--port","0","--max-requests",str(count),"--idle-ms","3000",*(["--transactional"] if transactional else []),*extra]
def rejected(log,source=SOURCE,extra=(),transactional=True):
    p=subprocess.run(args(log,source=source,extra=extra,transactional=transactional),capture_output=True,text=True,timeout=8)
    assert p.returncode!=0 and "LISTENING" not in p.stdout,(p.stdout,p.stderr)
    assert "E_SERVER_" in p.stderr,(p.stdout,p.stderr)
def launch(log,count,source=SOURCE,fault=None):
    env={"PATH":"/nonexistent","LC_ALL":"C"}
    if fault:env["SEDRAVASQL_NATIVE_TEST_FAULT"]=fault
    p=subprocess.Popen(args(log,count,source),stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,stdin=subprocess.DEVNULL,env=env)
    with selectors.DefaultSelector() as watcher:
        watcher.register(p.stdout,selectors.EVENT_READ)
        if not watcher.select(10):
            p.kill();p.communicate();raise AssertionError("no startup")
        line=p.stdout.readline().strip()
    if not line.startswith("LISTENING http://127.0.0.1:"):
        p.kill();_,err=p.communicate();raise AssertionError((line,err))
    return p,int(line.rsplit(":",1)[1])
def stop(p,ok=True):
    try:out,err=p.communicate(timeout=8)
    except subprocess.TimeoutExpired:
        p.kill();p.communicate();raise
    assert (p.returncode==0)==ok,(p.returncode,out,err)
def kill(p):
    if p.poll() is None:p.kill()
    p.communicate(timeout=5)
def payload(n):
    return {"left":f"левый-{n}","right":f"правый-{n}","left_rev":n-1,"right_rev":n-1}
def key(n):return f"a12-http-request-{n:06}"
def send(port,n,**kw):
    return req(port,method="PUT",path="/update",payload=kw.get("payload",payload(n)),key=kw.get("key",key(n)),rev=kw.get("rev",n-1))
def write(port,n,replay=False):
    code,out,h=send(port,n)
    assert (code,out)==(200,{"left":f"левый-{n}","right":f"правый-{n}","counter":n}),(code,out,h)
    assert h["x-sedrava-revision"]==str(n) and h["x-sedrava-batch-kv-revisions"]==f"{n},{n}"
    assert (h.get("x-sedrava-replayed")=="true")==replay
def pair(port,n):
    assert_reply(port,200,{"left":f"левый-{n}","right":f"правый-{n}","left_revision":n,"right_revision":n,"counter":n},path="/pair")
def error(result,status,code):
    assert result[:2]==(status,{"error":{"code":code}}),result
def check_journal(log,n):
    assert cli("verify",log)["sequence"]==n
    q=log.parent/"queries.json"
    q.write_text(json.dumps([["public_notes","left"],["public_notes","right"],["sedrava_native_a12","state"]]))
    snap=cli("read-many",log,q)
    assert snap["sequence"]==n and [r["revision"] for r in snap["rows"]]==[n,n,n]
    state=json.loads(snap["rows"][2]["value"])
    assert state["revision"]==n and state["state"]=={"counter":n}
    assert snap["rows"][0]["value"]==f"левый-{n}" and snap["rows"][1]["value"]==f"правый-{n}"
def main():
    with tempfile.TemporaryDirectory(prefix="sedrava-a12-a13-") as temp:
        root=Path(temp);log=root/"native.slog"; lock=root/"native.slog.lock"
        rejected(log); assert not log.exists()
        cli("init",log)
        rejected(log,transactional=False)
        rejected(log,extra=("--sqlite-v2-state",str(root/"forbidden.sqlite")))
        assert not (root/"forbidden.sqlite").exists()
        # Unsupported pure GET / non-batch PUT programs rejected at startup.
        rejected(log,source=ROOT/"examples/native_server/native_a11_index.sdr")
        assert not lock.exists()
        child,port=launch(log,20)
        try:
            rejected(log) # exclusive owner
            assert_reply(port,404,{"error":{"code":"DB_KEY_NOT_FOUND"}},path="/pair")
            assert_reply(port,200,{"counter":0},path="/counter")
            write(port,1);pair(port,1)
            before=digest(log)
            write(port,1,replay=True)
            error(send(port,1,payload=payload(2)),409,"IDEMPOTENCY_CONFLICT")
            error(send(port,2,rev=0),412,"STATE_REVISION_CONFLICT")
            wrong=payload(2);wrong["right_rev"]=0
            error(send(port,2,payload=wrong),412,"BATCH_REVISION_CONFLICT")
            invalid=payload(2);invalid["left_rev"]=-1
            error(send(port,2,payload=invalid),422,"BATCH_INVALID_REVISION")
            assert digest(log)==before
            pair(port,1)
            write(port,2);pair(port,2)
            stop(child)
        finally:kill(child)
        assert not lock.exists()
        check_journal(log,2)
        # New processes use same source and durable historic response.
        child,port=launch(log,4)
        try:
            pair(port,2);before=digest(log);write(port,1,replay=True)
            assert digest(log)==before
            write(port,3);pair(port,3);stop(child)
        finally:kill(child)
        check_journal(log,3)
        modified=root/"changed.sdr";modified.write_text(SOURCE.read_text()+"\n# change source signature\n")
        rejected(log,source=modified)
        assert not lock.exists()
        print("PASS A12/A13: atomic two KV + state + receipt; stale CAS, idempotency conflict, original response after restart; source binding; exclusive lock",flush=True)
        # Debug-only simulated process exit after sync, before HTTP response.
        child,port=launch(log,1,fault="after_sync")
        try:
            try:send(port,4)
            except (AssertionError,ConnectionError,OSError):pass
            else:raise AssertionError("expected lost response")
            out,err=child.communicate(timeout=8)
            assert child.returncode==86 and "SEDRAVASQL_NATIVE_TEST_FAULT:after_sync" in err,(out,err)
        finally:kill(child)
        assert lock.exists() and lock.read_text()==f"pid={child.pid}\n"
        rejected(log)
        # Explicit review only for disposable test-owned journal. Child was
        # waited/reaped; no production lock is automatically removed.
        lock.unlink()
        check_journal(log,4)
        child,port=launch(log,2)
        try:
            before=digest(log);write(port,4,replay=True);pair(port,4);stop(child)
            assert digest(log)==before
        finally:kill(child)
        print("PASS A13: simulated lost HTTP response after sync; stale lock rejected; reviewed test lock removed; exact replay after restart",flush=True)
        # Separate torn frame case: no auto-truncation, original untouched.
        child,port=launch(log,1,fault="after_payload")
        try:
            try:send(port,5)
            except (AssertionError,ConnectionError,OSError):pass
            else:raise AssertionError("expected lost response")
            out,err=child.communicate(timeout=8)
            assert child.returncode==86 and "SEDRAVASQL_NATIVE_TEST_FAULT:after_payload" in err,(out,err)
        finally:kill(child)
        assert lock.exists() and lock.read_text()==f"pid={child.pid}\n"
        rejected(log);lock.unlink();before=digest(log)
        rejected(log);assert digest(log)==before and not lock.exists()
        cli("verify",log,ok=False);assert digest(log)==before
        print("PASS A13: torn frame rejects restart and verify without auto-repair; original digest unchanged",flush=True)
if __name__=="__main__":main()
