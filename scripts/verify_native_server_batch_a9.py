#!/usr/bin/env python3
"""A9 real two-key+state atomic Sedrava DSL -> SedravaSQL SQLite on VDS.

No production files. Independent CLI, real TCP loopback, debug-only
transaction faults and two server processes. Temporary storage only.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import selectors
import sqlite3
import subprocess
import tempfile

from verify_native_server_a3 import req, assert_reply
from verify_native_server_sqlite_a6 import kill, stop

ROOT=Path(__file__).resolve().parents[1]
BIN=Path(os.environ["SEDRAVA_A9_BIN"])
SQL=Path(os.environ["SEDRAVASQL_CLI"])
SOURCE=ROOT/"examples/native_server/sqlite_a9_batch.sdr"
NS="public_notes"

def launch(db:Path,max_requests:int=50,fault:str|None=None):
    args=[str(BIN),"server","run",str(SOURCE),"--transactional",
          "--sqlite-v2-state",str(db),"--port","0",
          "--idle-ms","16000","--max-requests",str(max_requests)]
    env={"PATH":"/nonexistent","LC_ALL":"C"}
    if fault:env["SEDRAVASQL_MANAGED_BATCH_TEST_FAULT"]=fault
    child=subprocess.Popen(args,cwd=ROOT,stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,bufsize=1,env=env)
    selector=selectors.DefaultSelector()
    selector.register(child.stdout,selectors.EVENT_READ)
    assert selector.select(15),(fault,child.poll())
    line=child.stdout.readline().strip()
    assert line.startswith("LISTENING http://127.0.0.1:"),(fault,line,child.poll())
    return child,int(line.rsplit(":",1)[-1])

def cli(*args):
    proc=subprocess.run([str(SQL),*(str(a) for a in args)],
        capture_output=True,text=True,timeout=18,env={"PATH":"/nonexistent","LC_ALL":"C"})
    assert proc.returncode==0,(args,proc.stdout,proc.stderr)
    return json.loads(proc.stdout)

def payload(left,right,lrev,rrev):
    return {"left":left,"right":right,"left_rev":lrev,"right_rev":rrev}

def send(port,value,request_key,state_rev,expect=200):
    l,r,lv,rv=value
    code,obj,headers=req(port,method="PUT",path="/pair",
        payload=payload(l,r,lv,rv),key=request_key,rev=state_rev)
    assert code==expect,(request_key,code,obj,headers,expect)
    if expect==200:
        assert obj=={"left":l,"right":r,"counter":state_rev+1},(obj,state_rev)
    return obj,headers

def inspect(db:Path,nstate:int, left:tuple[str,int]|None=None,
            right:tuple[str,int]|None=None):
    with sqlite3.connect(db) as sql:
        assert sql.execute("PRAGMA integrity_check").fetchone()[0]=="ok"
        assert sql.execute("PRAGMA user_version").fetchone()[0]==1
        assert sql.execute("SELECT count(*) FROM managed_batch_receipts").fetchone()[0]==nstate
        assert sql.execute("SELECT count(*) FROM audit").fetchone()[0]==nstate*3
        assert sql.execute("SELECT count(*) FROM receipts").fetchone()[0]==nstate*3
        def stored(key):
            return sql.execute("SELECT value,revision FROM records WHERE namespace=? AND key=?",
                 (NS,key)).fetchone()
        assert stored("left")==left,(stored("left"),left)
        assert stored("right")==right,(stored("right"),right)
        state=sql.execute("SELECT value,revision FROM records WHERE namespace='sedrava_native_a6'").fetchone()
        if nstate:
            assert state is not None and state[1]==nstate
            parsed=json.loads(state[0])
            assert parsed["revision"]==nstate and parsed["state"]=={"counter":nstate}
            assert parsed["schema"]=="sedrava.server.sqlite.v2"
        else:
            assert state is None
    cli("verify",db)

def invalid_dsl(root:Path):
    template=SOURCE.read_text()
    bad=[
       template.replace('request left_rev: int','request left_rev: text'),
       template.replace('"public_notes/right"','"public_notes/left"'),
       template.replace('"public_notes/left"','"sedrava_native_a6/state"'),
       template.replace('"public_notes/left"','request.key'),
       template.replace('    set counter = state.counter + 1\n',''),
       template.replace('    set counter = state.counter + 1\n','    set counter = state.counter + 1\n    set counter = state.counter + 1\n'),
       template.replace('    request right_rev: int\n',''),
       template.replace('    request right_rev: int\n','    request right_rev: int\n    request extra: int\n'),
       template.replace('    set counter = state.counter + 1','    require state.counter == 0'),
       template.replace('db_batch_put "public_notes/right" = request.right expect request.right_rev',
           'db_put "public_notes/right" = request.right'),
       template.replace('db_batch_put "public_notes/right" = request.right expect request.right_rev',''),
       template.replace('route PUT "/pair":','route POST "/pair":'),
    ]
    # The replacement affects one GET route too in a few cases; that still must reject.
    for i,source in enumerate(bad):
        file=root/f"invalid-{i}.sdr"
        file.write_text(source)
        r=subprocess.run([str(BIN),"server","check",str(file)],
            capture_output=True,text=True,timeout=14)
        assert r.returncode!=0 and "E_SERVER_" in r.stderr,(i,r.stdout,r.stderr)
    print(f"PASS A9: {len(bad)} malformed batch DSL programs rejected before binding")

def atomic_roundtrip(root:Path):
    db=root/"live.sqlite"
    child,port=launch(db,50)
    try:
        assert_reply(port,200,{"counter":0},path="/snapshot")
        assert_reply(port,428,{"error":{"code":"IDEMPOTENCY_KEY_REQUIRED"}},
            method="PUT",path="/pair",payload=payload("a","b",0,0),rev=0)
        assert_reply(port,428,{"error":{"code":"STATE_REVISION_REQUIRED"}},
            method="PUT",path="/pair",payload=payload("a","b",0,0),key="a9-first-request-000001")
        obj,h=send(port,("A 🐱","B 🍀",0,0),"a9-first-request-000001",0)
        assert h["x-sedrava-revision"]=="1" and h["x-sedrava-batch-kv-revisions"]=="1,1"
        inspect(db,1,("A 🐱",1),("B 🍀",1))
        assert_reply(port,200,{"counter":1},path="/snapshot")
        assert_reply(port,200,{"value":"A 🐱","revision":1},path="/left")
        assert_reply(port,200,{"value":"B 🍀","revision":1},path="/right")
        obj,repeat_h=send(port,("A 🐱","B 🍀",0,0),"a9-first-request-000001",0)
        assert repeat_h["x-sedrava-replayed"]=="true"
        assert repeat_h["x-sedrava-revision"]=="1"
        assert repeat_h["x-sedrava-batch-kv-revisions"]=="1,1"
        inspect(db,1,("A 🐱",1),("B 🍀",1))
        bad,_=send(port,("changed","B 🍀",0,0),"a9-first-request-000001",0,expect=409)
        assert bad=={"error":{"code":"IDEMPOTENCY_CONFLICT"}}
        bad,_=send(port,("X","Y",1,1),"a9-conflict-state-0002",0,expect=412)
        assert bad=={"error":{"code":"STATE_REVISION_CONFLICT"}}
        bad,_=send(port,("X","Y",0,1),"a9-conflict-key-00003",1,expect=412)
        assert bad=={"error":{"code":"BATCH_REVISION_CONFLICT"}}
        inspect(db,1,("A 🐱",1),("B 🍀",1))
        # Separate SedravaSQL CLI writer updates one key without touching state.
        cli("put",db,NS,"left","external","--expect",1,"--request-key","a9-external-sql-0001")
        bad,_=send(port,("X","Y",1,1),"a9-conflict-external-004",1,expect=412)
        assert bad=={"error":{"code":"BATCH_REVISION_CONFLICT"}}
        with sqlite3.connect(db) as sql:
            assert sql.execute("SELECT count(*) FROM managed_batch_receipts").fetchone()[0]==1
            assert sql.execute("SELECT value FROM records WHERE namespace=? AND key='right'",(NS,)).fetchone()[0]=="B 🍀"
            assert json.loads(sql.execute("SELECT value FROM records WHERE namespace='sedrava_native_a6'").fetchone()[0])["state"]["counter"]==1
        obj,h=send(port,("X","Y",2,1),"a9-second-request-00001",1)
        assert h["x-sedrava-batch-kv-revisions"]=="3,2"
        assert h["x-sedrava-revision"]=="2"
        with sqlite3.connect(db) as sql:
            assert sql.execute("SELECT count(*) FROM managed_batch_receipts").fetchone()[0]==2
            assert sql.execute("SELECT count(*) FROM audit").fetchone()[0]==7
            assert sql.execute("SELECT count(*) FROM receipts").fetchone()[0]==7
            state=sql.execute("SELECT value,revision FROM records WHERE namespace='sedrava_native_a6'").fetchone()
            assert state[1]==2 and json.loads(state[0])["state"]["counter"]==2
        assert_reply(port,200,{"counter":2},path="/snapshot")
        assert_reply(port,200,{"value":"X","revision":3},path="/left")
        assert_reply(port,200,{"value":"Y","revision":2},path="/right")
    finally:
        kill(child)
    child,port=launch(db,3)
    try:
        obj,h=send(port,("A 🐱","B 🍀",0,0),"a9-first-request-000001",0)
        assert h["x-sedrava-replayed"]=="true"
        assert_reply(port,200,{"counter":2},path="/snapshot")
        assert_reply(port,200,{"value":"X","revision":3},path="/left")
        stop(child,3)
    finally:
        kill(child)
    print("PASS A9: atomic two keys+server state, independent external CLI conflict, restart replay")
    print("PASS A9: legacy audit and receipts intact, full original reply persisted")

def two_servers(root:Path):
    db=root/"two.sqlite"
    first,p1=launch(db,3)
    second,p2=launch(db,3)
    try:
        send(p1,("one","two",0,0),"a9-two-server-first01",0)
        code,result,_=req(p2,method="PUT",path="/pair",
            payload=payload("three","four",0,0),key="a9-two-server-second",rev=0)
        assert code==503 and result=={"error":{"code":"DB_BATCH_UNCERTAIN"}},(code,result)
        # The stale session must stop. A new process must load state=1.
        # Another instance with the same request can still replay the
        # originally persisted complete response safely.
        third,p3=launch(db,1)
        try:
            code,result,headers=req(p3,method="PUT",path="/pair",
                payload=payload("one","two",0,0),key="a9-two-server-first01",rev=0)
            assert code==200 and headers.get("x-sedrava-replayed")=="true",(code,result,headers)
            assert headers["x-sedrava-revision"]=="1"
            stop(third,1)
        finally:kill(third)
    finally:
        kill(first);kill(second)
    inspect(db,1,("one",1),("two",1))
    print("PASS A9: two independent server instances, conflicting CAS fails, exact replay")

def crash_window(root:Path):
    points=["after_first_value","after_all_rows","before_commit","after_commit"]
    for point in points:
        db=root/f"fault-{point}.sqlite"
        child,port=launch(db,1,fault=point)
        try:
            try:
                req(port,method="PUT",path="/pair",payload=payload("one","two",0,0),
                    key="a9-crash-replay-00001",rev=0)
            except (ConnectionError,TimeoutError,ValueError,AssertionError,OSError):
                pass
            stdout,stderr=child.communicate(timeout=12)
            assert child.returncode==86,(point,child.returncode,stdout,stderr)
            assert f"SEDRAVASQL_MANAGED_BATCH_TEST_FAULT:{point}" in stderr
        finally:
            kill(child)
        expected=1 if point=="after_commit" else 0
        if expected:
            inspect(db,1,("one",1),("two",1))
        else:
            inspect(db,0)
        child,port=launch(db,2)
        try:
            obj,h=send(port,("one","two",0,0),"a9-crash-replay-00001",0)
            assert (h.get("x-sedrava-replayed")=="true")==bool(expected)
            assert_reply(port,200,{"counter":1},path="/snapshot")
            stop(child,2)
        finally:kill(child)
        inspect(db,1,("one",1),("two",1))
    print("PASS A9: four controlled child-process crashes, all-or-none records/audit/receipts")

def main():
    assert BIN.is_file() and SQL.is_file()
    with tempfile.TemporaryDirectory(prefix="sedrava-a9-transaction-") as folder:
        root=Path(folder);root.chmod(0o700)
        invalid_dsl(root)
        atomic_roundtrip(root)
        two_servers(root)
        crash_window(root)
    print("PASS A9: VDS loopback/local only; no live site or production DB")
if __name__=="__main__":
    main()
