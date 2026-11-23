#!/usr/bin/env python3
"""A7 direct managed SedravaSQL text/revision via actual Sedrava HTTP server.

Independent SedravaSQL CLI controls the stored values on a disposable
SQLite database. Public HTTP or production data is never used.
"""
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import tempfile

from verify_native_server_sqlite_a6 import launch, stop, kill
from verify_native_server_a3 import assert_reply

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/"examples/native_server/sqlite_a7_metadata.sdr"
CLI=Path(os.environ["SEDRAVASQL_CLI"])
BIN=Path(os.environ["SEDRAVA_A6_BIN"])

def cli(*args):
    run=subprocess.run([str(CLI),*(str(a) for a in args)],capture_output=True,
                       text=True,timeout=15,env={"PATH":"/nonexistent","LC_ALL":"C"})
    assert run.returncode==0,(args,run.stdout,run.stderr)
    return json.loads(run.stdout)

def invalid(source:str,temp:Path,index:int):
    file=temp/f"invalid-{index}.sdr"
    file.write_text(source,encoding="utf-8")
    check=subprocess.run([str(BIN),"server","check",str(file)],
                         capture_output=True,text=True,timeout=12)
    assert check.returncode!=0,(index,check.stdout,check.stderr)
    assert "E_SERVER_" in check.stderr,(index,check.stderr)

def main():
    assert CLI.is_file() and BIN.is_file()
    with tempfile.TemporaryDirectory(prefix="sedrava-a7-db-revision-") as folder:
        root=Path(folder)
        os.chmod(root,0o700)
        db=root/"managed.sqlite"
        cli("init",db)
        cli("put",db,"public_notes","welcome","Привет",
            "--expect",0,"--request-key","a7-first-write-000001")
        server,port=launch(db,count=5,source=SOURCE)
        try:
            assert_reply(port,200,{"note":"Привет","revision":1,"enabled":True},path="/note")
            assert_reply(port,200,{"revision":1},path="/revision")
            # A second process changes data while the A7 Sedrava server is alive.
            cli("put",db,"public_notes","welcome","Данные обновлены",
                "--expect",1,"--request-key","a7-next-write-000002")
            assert_reply(port,200,{"note":"Данные обновлены","revision":2,"enabled":True},path="/note")
            cli("delete",db,"public_notes","welcome",
                "--expect",2,"--request-key","a7-delete-000000003","--confirm")
            assert_reply(port,404,{"error":{"code":"DB_KEY_NOT_FOUND"}},path="/note")
            assert_reply(port,404,{"error":{"code":"DB_KEY_NOT_FOUND"}},path="/revision")
            stop(server,5)
        finally:
            kill(server)
        cli("verify",db)
        rows=cli("audit",db)
        assert len(rows)==3 and all(item["namespace"]=="public_notes" for item in rows)
        print("PASS A7: live SedravaSQL CLI put/update/delete reflected in Sedrava GET metadata")
        print("PASS A7: value and revision from one SQL row per reply; tombstone -> 404")
        # Explicit no-DB option must fail before listening.
        invalid_run=subprocess.run(
            [str(BIN),"server","run",str(SOURCE),"--port","0",
             "--max-requests","1","--idle-ms","500"],
            capture_output=True,text=True,timeout=12)
        assert invalid_run.returncode!=0 and "LISTENING" not in invalid_run.stdout
        assert "sqlite-v2-state" in invalid_run.stderr

        bad_cases=[
          'server "x"\nstate ok: bool = true\nroute POST "/x":\n    request a: text\n    respond 201 { revision: db_revision("public_notes/welcome") }\n',
          'server "x"\nstate ok: bool = true\nroute GET "/x":\n    set ok = true\n    respond 200 { revision: db_revision("public_notes/welcome") }\n',
          'server "x"\nstate ok: bool = true\nroute GET "/x":\n    respond 200 { revision: db_revision("sedrava_native_a6/secret") }\n',
          'server "x"\nstate ok: bool = true\nroute GET "/x":\n    respond 200 { revision: db_revision("public_notes/../../secret") }\n',
          'server "x"\nstate ok: bool = true\nroute GET "/x":\n    respond 200 { revision: db_revision(request.a) }\n',
          'server "x"\nstate ok: bool = true\nroute GET "/x":\n    respond 200 { revision: db_revision("public_notes/missing" + "x") }\n',
          'server "x"\nstate ok: bool = true\nroute GET "/x":\n    respond 200 { revision: db_revision("public_notes/welcome" } }\n',
        ]
        for index,source in enumerate(bad_cases):
            invalid(source,root,index)
        print(f"PASS A7: {len(bad_cases)} invalid/reserved/dynamic/write cases rejected before bind")

        # Unrepresentable SQLite 64-bit revision is not truncated to int32.
        range_db=root/"range.sqlite"
        cli("init",range_db)
        cli("put",range_db,"public_notes","welcome","value",
            "--expect",0,"--request-key","a7-range-seed-00001")
        with sqlite3.connect(range_db) as con:
            con.execute("UPDATE records SET revision=? WHERE namespace=? AND key=?",
                        (2**31,"public_notes","welcome"))
        server,port=launch(range_db,count=2,source=SOURCE)
        try:
            assert_reply(port,503,{"error":{"code":"DB_REVISION_RANGE"}},path="/revision")
            assert_reply(port,503,{"error":{"code":"DB_REVISION_RANGE"}},path="/note")
            stop(server,2)
        finally:
            kill(server)
        print("PASS A7: out-of-int32 revision fails closed (503), never truncates")
        print("LIMIT: no atomic multi-key snapshot, no general SQL or write DSL, loopback only")

if __name__=="__main__":
    main()
