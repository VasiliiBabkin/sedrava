#!/usr/bin/env python3
"""Real A6 DSL db_get against external SedravaSQL CLI mutations."""
import os
from pathlib import Path
import subprocess
import tempfile
from verify_native_server_sqlite_a6 import launch, stop, kill
from verify_native_server_a3 import assert_reply

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "examples/native_server/sqlite_a6_read.sdr"
CLI = Path(os.environ.get("SEDRAVASQL_CLI", str(ROOT.parent / "sedravasql/target/debug/sedravasql")))
BIN = Path(os.environ.get("SEDRAVA_A6_BIN", str(ROOT/"rust/target/debug/sedrava-native")))


def cli(*args):
    run = subprocess.run([str(CLI), *map(str,args)],capture_output=True,text=True,
                         env={"PATH":"/nonexistent"},timeout=15)
    assert run.returncode==0, (args,run.stdout,run.stderr)
    return run.stdout


def main():
    assert CLI.is_file() and BIN.is_file()
    with tempfile.TemporaryDirectory(prefix="sedrava-db-get-") as directory:
        root=Path(directory)
        db=root/"storage.sqlite"
        cli("init",db)
        cli("put",db,"public_notes","welcome","Привет",
            "--expect","0","--request-key","db-read-request-0001")
        child,port=launch(db,count=4,source=SRC)
        try:
            assert_reply(port,200,{"note":"Привет","enabled":True},path="/note")
            cli("put",db,"public_notes","welcome","Новый текст",
                "--expect","1","--request-key","db-read-request-0002")
            assert_reply(port,200,{"note":"Новый текст","enabled":True},path="/note")
            assert_reply(port,404,{"error":{"code":"NOT_FOUND"}},path="/missing")
            assert_reply(port,200,{"note":"Новый текст","enabled":True},path="/note")
            stop(child,4)
        finally:
            kill(child)
        invalid = subprocess.run(
            [str(BIN),"server","run",str(SRC),"--port","0",
             "--max-requests","1","--idle-ms","500"],
            capture_output=True,text=True,timeout=10)
        assert invalid.returncode!=0 and "LISTENING" not in invalid.stdout
        assert "db_get requires" in invalid.stderr,invalid.stderr
        examples = [
            'server "bad"\nstate ok: bool = true\nroute GET "/x":\n    respond 200 { val: db_get("bad/../../key") }\n',
            'server "bad"\nstate ok: bool = true\nroute GET "/x":\n    respond 200 { val: db_get("sedrava_native_a6/internal") }\n',
            'server "bad"\nstate ok: bool = true\nroute POST "/x":\n    respond 201 { val: db_get("public_notes/welcome") }\n',
            'server "bad"\nstate ok: bool = true\nroute GET "/x":\n    set ok = true\n    respond 200 { val: db_get("public_notes/welcome") }\n',
        ]
        for i,source in enumerate(examples):
            path=root/f"bad-{i}.sdr"
            path.write_text(source)
            check=subprocess.run([str(BIN),"server","check",str(path)],
                capture_output=True,text=True,timeout=10)
            assert check.returncode!=0,(source,check.stdout,check.stderr)
    print("PASS A6 Sedrava db_get(): live KV read and refreshed value via independent SedravaSQL CLI")
    print("PASS db_get is read-only, GET only, requires explicit --sqlite-v2-state")
    print("PASS invalid namespace/key and write-route/step usage rejected before network bind")


if __name__ == "__main__":
    main()
