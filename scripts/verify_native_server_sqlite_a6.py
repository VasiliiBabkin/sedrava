#!/usr/bin/env python3
"""A6: real HTTP, durable SQL application receipts beyond A3's 32 cap."""
import json
import os
from pathlib import Path
import selectors
import sqlite3
import subprocess
import tempfile

from verify_native_server_a3 import assert_reply, req

ROOT = Path(__file__).resolve().parents[1]
BIN = Path(os.environ.get("SEDRAVA_A6_BIN", str(ROOT / "rust/target/debug/sedrava-native")))
SOURCE = ROOT / "examples/native_server/sqlite_a5.sdr"
NAMESPACE = "sedrava_native_a6"


def launch(db, count=70, source=SOURCE, extra=(), fault=None):
    args = [str(BIN), "server", "run", str(source), "--transactional",
            "--sqlite-v2-state", str(db), "--port", "0", "--idle-ms", "15000",
            "--max-requests", str(count), *extra]
    child_env = {"PATH": "/nonexistent", "LC_ALL": "C"}
    if fault is not None:
        child_env["SEDRAVASQL_TEST_FAULT"] = fault
    child = subprocess.Popen(args, cwd=ROOT, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True, bufsize=1, stdin=subprocess.DEVNULL,
        env=child_env)
    selector = selectors.DefaultSelector()
    selector.register(child.stdout, selectors.EVENT_READ)
    assert selector.select(15), "server did not report bound loopback TCP"
    line = child.stdout.readline().strip()
    if not line.startswith("LISTENING http://127.0.0.1:"):
        child.kill()
        _, err = child.communicate(timeout=5)
        raise AssertionError((line, err))
    return child, int(line.rsplit(":", 1)[-1])


def stop(child, count=None, successful=True):
    if child.poll() is None:
        output, errors = child.communicate(timeout=18)
    else:
        output, errors = child.communicate(timeout=5)
    if successful:
        assert child.returncode == 0, (child.returncode, errors, output)
        if count is not None:
            assert f"STOPPED requests={count}" in output, output
    else:
        assert child.returncode != 0, (output, errors)


def kill(child):
    if child.poll() is None:
        child.kill()
    child.communicate(timeout=6)


def check_sql(db, count, first_key="a6-request-00000000"):
    with sqlite3.connect(db) as sql:
        assert sql.execute("PRAGMA user_version").fetchone()[0] == 1
        assert sql.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert sql.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert sql.execute("SELECT count(*) FROM audit WHERE namespace=?", (NAMESPACE,)).fetchone()[0] == count
        assert sql.execute("SELECT count(*) FROM receipts WHERE namespace=?", (NAMESPACE,)).fetchone()[0] == count
        row = sql.execute("SELECT value, revision FROM records WHERE namespace=?", (NAMESPACE,)).fetchone()
        assert row and row[1] == count, row
        state = json.loads(row[0])
        assert state["revision"] == count
        assert "receipts" not in state, "A6 must not embed full reply history in state"
        assert state["state"] == {"count": count, "total": count, "label": "open"}
        earliest = sql.execute(
            "SELECT response_json FROM receipts WHERE namespace=? ORDER BY audit_id ASC LIMIT 1",
            (NAMESPACE,)).fetchone()[0]
        earliest = json.loads(earliest)
        assert json.loads(earliest["application_response"])["key"] == first_key
        return state


def primary(tmp):
    db = tmp / "a6.sqlite"
    child, port = launch(db, count=48)
    try:
        assert_reply(port, 200, {"count": 0, "total": 0, "label": "open"})
        for i in range(45):
            headers = assert_reply(port, 201, {"count": i + 1, "total": i + 1, "accepted": True},
                method="POST", path="/record", payload={"amount": 1},
                key=f"a6-request-{i:08d}", rev=i)
            assert headers["x-sedrava-revision"] == str(i + 1)
        h = assert_reply(port, 201, {"count": 1, "total": 1, "accepted": True},
            method="POST", path="/record", payload={"amount": 1},
            key="a6-request-00000000", rev=0)
        assert h["x-sedrava-replayed"] == "true"
        assert_reply(port, 200, {"count":45, "total":45, "label":"open"})
        stop(child,48)
    finally:
        kill(child)
    check_sql(db,45)
    child,port = launch(db, count=4)
    try:
        h = assert_reply(port,200,{"count":45,"total":45,"label":"open"})
        assert h["x-sedrava-revision"] == "45"
        h = assert_reply(port,201,{"count":1,"total":1,"accepted":True},
            method="POST",path="/record",payload={"amount":1},key="a6-request-00000000",rev=0)
        assert h["x-sedrava-replayed"] == "true"
        assert_reply(port,409,{"error":{"code":"IDEMPOTENCY_CONFLICT"}},
            method="POST",path="/record",payload={"amount":2},key="a6-request-00000000",rev=0)
        assert_reply(port,201,{"count":46,"total":46,"accepted":True},
            method="POST",path="/record",payload={"amount":1},key="a6-request-00000045",rev=45)
        stop(child,4)
    finally:
        kill(child)
    check_sql(db,46)
    return db


def conflicts(tmp):
    db = tmp/"shared.sqlite"
    first,port1 = launch(db,count=2)
    second = None
    try:
        second,port2 = launch(db,count=1)
        assert_reply(port1,201,{"count":1,"total":1,"accepted":True},
            method="POST",path="/record",payload={"amount":1},key="server-first-000001",rev=0)
        code,obj,_ = req(port2,method="POST",path="/record",payload={"amount":1},
            key="server-second-00001",rev=0)
        assert code == 503 and obj == {"error":{"code":"STATE_COMMIT_UNCERTAIN"}},(code,obj)
        stop(second,successful=False)
        second = None
        assert_reply(port1,200,{"count":1,"total":1,"label":"open"})
        stop(first,2)
        first = None
    finally:
        if first:kill(first)
        if second:kill(second)
    check_sql(db,1,"server-first-000001")


def reject_other_modes(tmp):
    db = tmp/"invalid.sqlite"
    for flags in [
        ("--sqlite-v2-state",str(db)),
        ("--transactional","--sqlite-v2-state",str(db),"--journaled"),
        ("--transactional","--sqlite-v2-state",str(db),"--sqlite-state",str(db)),
        ("--transactional","--sqlite-v2-state",str(db),"--state-dir",str(tmp)),
    ]:
        command=[str(BIN),"server","run",str(SOURCE),
            "--port","0","--idle-ms","500","--max-requests","1",*flags]
        result=subprocess.run(command,capture_output=True,text=True,timeout=8)
        assert result.returncode !=0 and "LISTENING" not in result.stdout, (flags,result)
    assert not db.exists(), "invalid option must not touch storage"


def fault_windows(tmp):
    """Debug child stops during SQL transaction: no partial audit+state."""
    for point in ("after_value_write", "after_audit_write", "before_commit", "after_commit"):
        db=tmp/f"fault-{point}.sqlite"
        child,port=launch(db,count=1,fault=point)
        try:
            try:
                req(port,method="POST",path="/record",payload={"amount":1},
                    key="a6-fault-request-0001",rev=0)
            except (OSError, AssertionError, ValueError):
                pass  # abrupt debug exit intentionally breaks the HTTP connection
            _,err=child.communicate(timeout=12)
            assert child.returncode==86,(point,child.returncode,err)
        finally:
            kill(child)
        with sqlite3.connect(db) as sql:
            audit=sql.execute("SELECT count(*) FROM audit WHERE namespace=?",(NAMESPACE,)).fetchone()[0]
            receipts=sql.execute("SELECT count(*) FROM receipts WHERE namespace=?",(NAMESPACE,)).fetchone()[0]
            row=sql.execute("SELECT revision FROM records WHERE namespace=?",(NAMESPACE,)).fetchone()
            expected=1 if point=="after_commit" else 0
            assert audit==receipts==expected,(point,audit,receipts,expected)
            assert (row[0] if row else 0)==expected,(point,row,expected)
        child,port=launch(db,count=2)
        try:
            h=assert_reply(port,201,{"count":1,"total":1,"accepted":True},
                method="POST",path="/record",payload={"amount":1},
                key="a6-fault-request-0001",rev=0)
            assert (h.get("x-sedrava-replayed")=="true")== (point=="after_commit")
            assert_reply(port,200,{"count":1,"total":1,"label":"open"})
            stop(child,2)
        finally:
            kill(child)
        check_sql(db,1,"a6-fault-request-0001")


def main():
    assert BIN.exists()
    with tempfile.TemporaryDirectory(prefix="sedrava-a6-sqlite-") as temp:
        tmp=Path(temp)
        primary(tmp)
        conflicts(tmp)
        reject_other_modes(tmp)
        fault_windows(tmp)
    print("PASS A6 46 HTTP writes, early receipt replay after >32 and restart, conflicting key 409")
    print("PASS A6 full SQL audit/receipt history survives (no receipt eviction or embedded JSON ledger)")
    print("PASS A6 two live processes: stale CAS fail closed 503 and exit, no lost state")
    print("PASS A6 exclusive CLI option, isolated temporary SQLite, loopback only")
    print("PASS four debug-only SQL crash windows: atomic recovery and original replay")
if __name__=="__main__":
    main()
