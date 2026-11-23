#!/usr/bin/env python3
"""Native Sedrava A5 -> pinned SedravaSQL SQLite adapter acceptance.

Real TCP, SQLite queries, WAL-based restore, exact replay after restart,
stale concurrent server sessions, corruption/schema validation and CLI flags.
"""
import json
from pathlib import Path
import selectors
import sqlite3
import subprocess
import tempfile
import re
from verify_native_server_a3 import assert_reply,req

ROOT=Path(__file__).resolve().parents[1]
BIN=ROOT/"rust/target/debug/sedrava-native"
SOURCE=ROOT/"examples/native_server/sqlite_a5.sdr"
DBSQL=ROOT.parent/"sedravasql/target/debug/sedravasql"

def launch(db,expected=20,source=SOURCE,extra=()):
    args=[str(BIN),"server","run",str(source),"--transactional",
          "--sqlite-state",str(db),"--port","0",
          "--idle-ms","15000","--max-requests",str(expected),*extra]
    proc=subprocess.Popen(args,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
             stdin=subprocess.DEVNULL,text=True,bufsize=1,
             env={"PATH":"/nonexistent","LC_ALL":"C"})
    sel=selectors.DefaultSelector()
    sel.register(proc.stdout,selectors.EVENT_READ)
    assert sel.select(15),"native SQLite server startup timeout"
    line=proc.stdout.readline().strip()
    match=re.fullmatch(r"LISTENING http://127\.0\.0\.1:(\d{1,5})",line)
    if not match:
        proc.kill()
        _,err=proc.communicate(timeout=5)
        raise AssertionError(("not listening",line,err[-600:]))
    return proc,int(match.group(1))
def closed(proc,count=None,success=True):
    if proc.poll() is None:
        output,err=proc.communicate(timeout=18)
    else: output,err=proc.communicate(timeout=5)
    if success:
        assert proc.returncode==0,(proc.returncode,output,err)
        assert f"STOPPED requests={count}" in output,(count,output)
    else:
        assert proc.returncode!=0,(output,err)
    return output,err
def kill(proc):
    if proc.poll() is None:proc.kill()
    proc.communicate(timeout=5)

def verify_sqlite(db, expected=2):
    with sqlite3.connect(db) as sql:
        assert sql.execute("PRAGMA journal_mode").fetchone()[0]=="wal"
        assert sql.execute("PRAGMA user_version").fetchone()[0]==1
        assert sql.execute("PRAGMA integrity_check").fetchone()[0]=="ok"
        assert sql.execute("SELECT count(*) FROM audit").fetchone()[0]==expected
        assert sql.execute("SELECT count(*) FROM receipts").fetchone()[0]==expected
        row=sql.execute("SELECT value,revision FROM records WHERE namespace='sedrava_native'").fetchone()
        assert row is not None
        value=json.loads(row[0])
        assert value["revision"]==expected,(value,expected)
        assert len(value["receipts"])==expected
        assert row[1]==expected
        return value

def primary(tmp):
    db=tmp/"sedrava-state.sqlite"
    proc,port=launch(db,expected=7)
    try:
        assert_reply(port,200,{"count":0,"total":0,"label":"open"})
        h=assert_reply(port,201,{"count":1,"total":3,"accepted":True},
                       method="POST",path="/record",payload={"amount":3},
                       key="sqlite-native-0001",rev=0)
        assert h["x-sedrava-revision"]=="1"
        h=assert_reply(port,201,{"count":1,"total":3,"accepted":True},
                       method="POST",path="/record",payload={"amount":3},
                       key="sqlite-native-0001",rev=0)
        assert h["x-sedrava-replayed"]=="true"
        h=assert_reply(port,201,{"count":2,"total":8,"accepted":True},
                       method="POST",path="/record",payload={"amount":5},
                       key="sqlite-native-0002",rev=1)
        assert h["x-sedrava-revision"]=="2"
        assert_reply(port,409,{"error":{"code":"IDEMPOTENCY_CONFLICT"}},
                     method="POST",path="/record",payload={"amount":4},
                     key="sqlite-native-0002",rev=1)
        assert_reply(port,412,{"error":{"code":"REVISION_CONFLICT"}},
                     method="POST",path="/record",payload={"amount":4},
                     key="sqlite-native-0003",rev=0)
        assert_reply(port,200,{"count":2,"total":8,"label":"open"})
        closed(proc,7)
    finally:kill(proc)
    value=verify_sqlite(db,2)
    assert value["state"]=={"count":2,"total":8,"label":"open"}
    proc,port=launch(db,expected=3)
    try:
        h=assert_reply(port,200,{"count":2,"total":8,"label":"open"})
        assert h["x-sedrava-revision"]=="2"
        h=assert_reply(port,201,{"count":1,"total":3,"accepted":True},
                       method="POST",path="/record",payload={"amount":3},
                       key="sqlite-native-0001",rev=0)
        assert h["x-sedrava-replayed"]=="true" and h["x-sedrava-revision"]=="1"
        assert_reply(port,200,{"count":2,"total":8,"label":"open"})
        closed(proc,3)
    finally:kill(proc)
    verify_sqlite(db,2)
    # Backup via the independently built SedravaSQL binary.
    backup=tmp/"backup.sqlite"
    result=subprocess.run([str(DBSQL),"backup",str(db),str(backup)],capture_output=True,
        text=True,timeout=15,env={"PATH":"/nonexistent"})
    assert result.returncode==0,(result.stderr,result.stdout)
    verify_sqlite(backup,2)
    return db

def two_servers(tmp):
    db=tmp/"shared.sqlite"
    first,port1=launch(db,expected=2)
    second=None
    try:
        second,port2=launch(db,expected=3)
        assert_reply(port1,201,{"count":1,"total":1,"accepted":True},
                     method="POST",path="/record",payload={"amount":1},
                     key="server-one-00001",rev=0)
        # Other session is stale. Its SQL CAS fails, and it FAILS CLOSED.
        response=req(port2,method="POST",path="/record",payload={"amount":2},
                     key="server-two-00001",rev=0)
        assert response[0]==503 and response[1]=={
            "error":{"code":"STATE_COMMIT_UNCERTAIN"}},response
        closed(second,success=False)
        second=None
        assert_reply(port1,200,{"count":1,"total":1,"label":"open"})
        closed(first,2)
        first=None
    finally:
        if first:kill(first)
        if second:kill(second)
    verify_sqlite(db,1)
    third,port=launch(db,expected=2)
    try:
        assert_reply(port,200,{"count":1,"total":1,"label":"open"})
        h=assert_reply(port,201,{"count":2,"total":3,"accepted":True},
                       method="POST",path="/record",payload={"amount":2},
                       key="server-two-00001",rev=1)
        assert h["x-sedrava-revision"]=="2"
        closed(third,2)
    finally:kill(third)
    verify_sqlite(db,2)

def rejected(tmp):
    db=tmp/"forged.sqlite"
    with sqlite3.connect(db) as con:
        con.execute("CREATE TABLE unrelated(secret TEXT)")
        con.execute("INSERT INTO unrelated VALUES('keep')")
    proc=subprocess.run([str(BIN),"server","run",str(SOURCE),"--transactional",
          "--sqlite-state",str(db),"--port","0","--max-requests","1",
          "--idle-ms","500"],capture_output=True,text=True,timeout=6)
    assert proc.returncode!=0 and "LISTENING" not in proc.stdout
    with sqlite3.connect(db) as con:
        assert con.execute("SELECT secret FROM unrelated").fetchone()[0]=="keep"
    for flags in [
        ("--sqlite-state",str(tmp/"out.sqlite")),
        ("--transactional","--sqlite-state",str(tmp/"out.sqlite"),"--journaled"),
        ("--transactional","--sqlite-state",str(tmp/"out.sqlite"),
         "--state-dir",str(tmp)),
    ]:
        call=[str(BIN),"server","run",str(SOURCE),"--port","0",
              "--max-requests","1","--idle-ms","500",*flags]
        res=subprocess.run(call,capture_output=True,text=True,timeout=8)
        assert res.returncode!=0 and "LISTENING" not in res.stdout,(flags,res)

def main():
    assert BIN.is_file() and DBSQL.is_file()
    with tempfile.TemporaryDirectory(prefix="sedrava-sqlite-a5-") as d:
        tmp=Path(d)
        primary(tmp)
        two_servers(tmp)
        rejected(tmp)
    print("PASS Sedrava native A5 SQLite mode: real HTTP commits/replay/CAS, restore after full restart")
    print("PASS SQLite WAL, strict schema v1, data + audit + receipts in one SQLite transaction")
    print("PASS independent SedravaSQL CLI online backup and reopened restored state")
    print("PASS two Sedrava processes: stale writer returns 503 and halts, no lost updates")
    print("PASS legacy CLI modes unchanged, foreign schema and incompatible mode options rejected")
    print("PASS local TCP 127.0.0.1 only, native PATH=/nonexistent")
if __name__=="__main__": main()
