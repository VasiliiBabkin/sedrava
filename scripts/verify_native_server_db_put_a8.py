#!/usr/bin/env python3
"""A8 real local HTTP -> SedravaSQL atomic managed KV PUT integration.

The server is the Rust Sedrava DSL program, not a Python proxy. The
independent SedravaSQL CLI inspects/modifies the same disposable database.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import tempfile

from verify_native_server_sqlite_a6 import launch, kill, stop
from verify_native_server_a3 import req, assert_reply

ROOT=Path(__file__).resolve().parents[1]
BIN=Path(os.environ["SEDRAVA_A8_BIN"])
CLI=Path(os.environ["SEDRAVASQL_CLI"])
SOURCE=ROOT/"examples/native_server/sqlite_a8_put.sdr"
NAMESPACE="public_notes"
KEY="welcome"

def cli(*args,expect_ok=True):
    p=subprocess.run([str(CLI),*(str(a) for a in args)],
        capture_output=True,text=True,timeout=16,
        env={"PATH":"/nonexistent","LC_ALL":"C"})
    assert (p.returncode==0)==expect_ok,(args,p.returncode,p.stdout,p.stderr)
    return json.loads(p.stdout) if expect_ok else p.stderr

def db_check(db:Path,value:str,revision:int,audit:int):
    row=cli("get",db,NAMESPACE,KEY)
    assert row["value"]==value and row["revision"]==revision,row
    cli("verify",db)
    with sqlite3.connect(db) as con:
        assert con.execute("PRAGMA integrity_check").fetchone()[0]=="ok"
        assert con.execute("SELECT count(*) FROM audit WHERE namespace=?", (NAMESPACE,)).fetchone()[0]==audit
        assert con.execute("SELECT count(*) FROM receipts WHERE namespace=?", (NAMESPACE,)).fetchone()[0]==audit
        assert con.execute("SELECT count(*) FROM records WHERE namespace='sedrava_native_a6'").fetchone()[0]==0
        stored=con.execute("SELECT response_json FROM receipts WHERE namespace=? ORDER BY audit_id",
                           (NAMESPACE,)).fetchall()
        for (body,) in stored:
            entry=json.loads(body)
            app=json.loads(entry["application_response"]) if entry.get("application_response") else None
            if app:
                assert app["schema"]=="sedrava.server.a8.kv-put.v1"
                assert app["revision"]>=1
                assert app["response"]["saved"] is True

def check_invalid(root:Path):
    bad=[
      'server "x"\nstate enabled: bool = true\nroute GET "/x":\n    db_put "public_notes/welcome" = request.value\n    respond 200 { ok: true }\n',
      'server "x"\nstate enabled: bool = true\nroute PUT "/x":\n    request value: int\n    db_put "public_notes/welcome" = request.value\n    respond 200 { ok: true }\n',
      'server "x"\nstate enabled: bool = true\nroute PUT "/x":\n    request value: text\n    db_put "sedrava_native_a6/internal" = request.value\n    respond 200 { ok: true }\n',
      'server "x"\nstate enabled: bool = true\nroute PUT "/x":\n    request value: text\n    db_put "public_notes/../../bad" = request.value\n    respond 200 { ok: true }\n',
      'server "x"\nstate enabled: bool = true\nroute PUT "/x":\n    request value: text\n    db_put request.path = request.value\n    respond 200 { ok: true }\n',
      'server "x"\nstate enabled: bool = true\nroute PUT "/x":\n    request value: text\n    set enabled = false\n    db_put "public_notes/welcome" = request.value\n    respond 200 { ok: true }\n',
      'server "x"\nstate enabled: bool = true\nroute PUT "/x":\n    request value: text\n    db_put "public_notes/welcome" = request.value\n    set enabled = true\n    respond 200 { ok: true }\n',
      'server "x"\nstate enabled: bool = true\nroute PUT "/x":\n    request value: text\n    db_put "public_notes/welcome" = request.value\n    db_put "public_notes/other" = request.value\n    respond 200 { ok: true }\n',
      'server "x"\nstate enabled: bool = true\nroute PUT "/x":\n    request value: text\n    db_put "public_notes/welcome" = request.value\n    respond 200 { old: state.enabled }\n',
      'server "x"\nstate enabled: bool = true\nroute PUT "/x":\n    request value: text\n    db_put "public_notes/welcome" = request.value\n    respond 200 { rev: db_revision("public_notes/welcome") }\n',
      'server "x"\nstate enabled: bool = true\nroute PUT "/x":\n    request value: text\n    db_put "public_notes/welcome" = request.value\n    request other: text\n    respond 200 { ok: true }\n',
    ]
    for i,source in enumerate(bad):
        file=root/f"invalid-{i}.sdr"
        file.write_text(source,encoding="utf-8")
        p=subprocess.run([str(BIN),"server","check",str(file)],
            capture_output=True,text=True,timeout=10)
        assert p.returncode!=0 and "E_SERVER_" in p.stderr,(i,p.stderr,p.stdout)
    print(f"PASS A8: {len(bad)} invalid DSL forms rejected before bind")
    invalid_db=root/"must-not-create.sqlite"
    bad_run=subprocess.run([
        str(BIN),"server","run",str(SOURCE),"--transactional",
        "--port","0","--max-requests","1","--idle-ms","500"
    ],capture_output=True,text=True,timeout=10)
    assert bad_run.returncode!=0 and "LISTENING" not in bad_run.stdout
    assert "--sqlite-v2-state" in bad_run.stderr
    assert not invalid_db.exists()
    print("PASS A8: missing explicit --sqlite-v2-state refuses to start")

def test_one(root:Path):
    db=root/"one.sqlite"
    proc,port=launch(db,count=24,source=SOURCE)
    try:
        assert_reply(port,428,{"error":{"code":"IDEMPOTENCY_KEY_REQUIRED"}},
            method="PUT",path="/note",payload={"value":"Первое"})
        assert_reply(port,428,{"error":{"code":"KV_REVISION_REQUIRED"}},
            method="PUT",path="/note",payload={"value":"Первое"},key="a8-request-first-0001")
        assert_reply(port,400,{"error":{"code":"INVALID_IDEMPOTENCY_KEY"}},
            method="PUT",path="/note",payload={"value":"Первое"},key="x",rev=0)
        h=assert_reply(port,200,{"note":"Первое","saved":True},
            method="PUT",path="/note",payload={"value":"Первое"},key="a8-request-first-0001",rev=0)
        assert h["x-sedrava-kv-revision"]=="1" and "x-sedrava-replayed" not in h
        assert "x-sedrava-revision" not in h, "KV and A6 state revisions must be distinguished"
        db_check(db,"Первое",1,1)
        assert_reply(port,200,{"note":"Первое","revision":1},path="/note")
        h=assert_reply(port,200,{"note":"Первое","saved":True},
            method="PUT",path="/note",payload={"value":"Первое"},key="a8-request-first-0001",rev=0)
        assert h["x-sedrava-replayed"]=="true" and h["x-sedrava-kv-revision"]=="1"
        assert_reply(port,409,{"error":{"code":"IDEMPOTENCY_CONFLICT"}},
            method="PUT",path="/note",payload={"value":"Другое"},key="a8-request-first-0001",rev=0)
        assert_reply(port,412,{"error":{"code":"REVISION_CONFLICT"}},
            method="PUT",path="/note",payload={"value":"Другое"},key="a8-request-stale-0002",rev=0)
        assert_reply(port,422,{"error":{"code":"REQUEST_SCHEMA_MISMATCH"}},
            method="PUT",path="/note",payload={"value":1},key="a8-invalid-payload-0003",rev=1)
        assert_reply(port,400,{"error":{"code":"INVALID_JSON"}},
            method="PUT",path="/note",payload='{"value":"x","value":"y"}',
            key="a8-duplicated-json-0004",rev=1)
        assert_reply(port,415,{"error":{"code":"JSON_CONTENT_TYPE_REQUIRED"}},
            method="PUT",path="/note",payload={"value":"test"},key="a8-wrong-type-00005",
            rev=1,ct="text/plain")
        db_check(db,"Первое",1,1)
        # Independent client uses SAME managed namespace/key and increases revision.
        cli("put",db,NAMESPACE,KEY,"Внешний клиент",
            "--expect",1,"--request-key","a8-sql-cli-changed-0004")
        assert_reply(port,200,{"note":"Внешний клиент","revision":2},path="/note")
        h=assert_reply(port,200,{"note":"Первое","saved":True},
            method="PUT",path="/note",payload={"value":"Первое"},key="a8-request-first-0001",rev=0)
        assert h["x-sedrava-replayed"]=="true" and h["x-sedrava-kv-revision"]=="1"
        h=assert_reply(port,200,{"note":"Готово 🐱","saved":True},
            method="PUT",path="/note",payload={"value":"Готово 🐱"},key="a8-request-third-00005",rev=2)
        assert h["x-sedrava-kv-revision"]=="3"
        db_check(db,"Готово 🐱",3,3)
        assert_reply(port,200,{"note":"Готово 🐱","revision":3},path="/note")
    finally:
        kill(proc)
    proc,port=launch(db,count=3,source=SOURCE)
    try:
        h=assert_reply(port,200,{"note":"Первое","saved":True},
            method="PUT",path="/note",payload={"value":"Первое"},key="a8-request-first-0001",rev=0)
        assert h["x-sedrava-replayed"]=="true" and h["x-sedrava-kv-revision"]=="1"
        h=assert_reply(port,200,{"note":"Готово 🐱","saved":True},
            method="PUT",path="/note",payload={"value":"Готово 🐱"},key="a8-request-third-00005",rev=2)
        assert h["x-sedrava-replayed"]=="true" and h["x-sedrava-kv-revision"]=="3"
        assert_reply(port,200,{"note":"Готово 🐱","revision":3},path="/note")
        stop(proc,3)
    finally:
        kill(proc)
    db_check(db,"Готово 🐱",3,3)
    print("PASS A8: PUT, CAS, stored audit+reply, exact idempotency after CLI change/restart")
    print("PASS A8: GET from SedravaSQL; independent SedravaSQL CLI sees every committed value")
    print("PASS A8: malformed/duplicate JSON, invalid type, missing conditions, conflicts rejected")

def test_two_servers(root:Path):
    db=root/"shared.sqlite"
    left,left_port=launch(db,count=3,source=SOURCE)
    right,right_port=launch(db,count=3,source=SOURCE)
    try:
        assert_reply(left_port,200,{"note":"Одно","saved":True},
            method="PUT",path="/note",payload={"value":"Одно"},
            key="a8-concurrent-000001",rev=0)
        assert_reply(right_port,412,{"error":{"code":"REVISION_CONFLICT"}},
            method="PUT",path="/note",payload={"value":"Другое"},
            key="a8-concurrent-000002",rev=0)
        h=assert_reply(right_port,200,{"note":"Одно","saved":True},
            method="PUT",path="/note",payload={"value":"Одно"},
            key="a8-concurrent-000001",rev=0)
        assert h["x-sedrava-replayed"]=="true"
        assert_reply(left_port,200,{"note":"Одно","revision":1},path="/note")
        stop(right,2)
        # left received two requests and is expected to stop after count=3,
        # so test processes are always explicitly cleaned on exit.
    finally:
        kill(left)
        kill(right)
    db_check(db,"Одно",1,1)
    print("PASS A8: two independent Sedrava servers - stale CAS 412, matching replay")

def test_abort(root:Path):
    for point in ("after_value_write","after_audit_write","before_commit","after_commit"):
        db=root/f"crash-{point}.sqlite"
        child,port=launch(db,count=1,source=SOURCE,fault=point)
        try:
            try:
                req(port,method="PUT",path="/note",payload={"value":"Атомарно"},
                    key="a8-crash-retry-000001",rev=0)
            except (OSError,AssertionError,ValueError):
                pass
            stdout,stderr=child.communicate(timeout=12)
            assert child.returncode==86,(point,child.returncode,stdout,stderr)
        finally:
            kill(child)
        expected=1 if point=="after_commit" else 0
        with sqlite3.connect(db) as con:
            a=con.execute("SELECT count(*) FROM audit WHERE namespace=?", (NAMESPACE,)).fetchone()[0]
            r=con.execute("SELECT count(*) FROM receipts WHERE namespace=?", (NAMESPACE,)).fetchone()[0]
            v=con.execute("SELECT revision FROM records WHERE namespace=? AND key=?",(NAMESPACE,KEY)).fetchone()
            assert a==r==expected and (v[0] if v else 0)==expected,(point,a,r,v,expected)
        proc,port=launch(db,count=2,source=SOURCE)
        try:
            h=assert_reply(port,200,{"note":"Атомарно","saved":True},
                method="PUT",path="/note",payload={"value":"Атомарно"},
                key="a8-crash-retry-000001",rev=0)
            assert (h.get("x-sedrava-replayed")=="true")==bool(expected),point
            assert_reply(port,200,{"note":"Атомарно","revision":1},path="/note")
            stop(proc,2)
        finally:
            kill(proc)
        db_check(db,"Атомарно",1,1)
    print("PASS A8: 4 injected SQL crash windows - atomic audit/value/receipt, replay after commit")

def main():
    assert CLI.is_file() and BIN.is_file()
    with tempfile.TemporaryDirectory(prefix="sedrava-a8-atomic-put-") as temp:
        root=Path(temp)
        root.chmod(0o700)
        check_invalid(root)
        test_one(root)
        test_two_servers(root)
        test_abort(root)
    print("PASS A8: temporary data only, loopback only; no production service touched")

if __name__=="__main__":
    main()
