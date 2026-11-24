"""Independent native Host A2 JSON/directory capabilities + A3 outcome regression.

Test trusted, isolated temporary directories only. No production IO or network.
"""
import json
import os
from pathlib import Path
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor

ROOT = Path(__file__).resolve().parents[1]
BIN = ROOT / "rust/target/debug/sedrava"


def execute(source: str, root: Path, *, grants=(), args=(), scopes=()):
    path = root / "host-program.sdr"
    path.write_text(source, encoding="utf-8")
    cmd = [str(BIN), "host", "run", str(path), "--root", str(root),
           "--result-protocol", "v1", *grants, *scopes]
    for arg in args:
        cmd += ["--arg", arg]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=10,
                          env={**os.environ, "PATH": "/nonexistent"}, check=False)
    assert proc.stdout, (proc.stderr, source)
    outcome = json.loads(proc.stdout)
    assert outcome["protocol"] == "sedrava.host.execution.v1"
    assert (proc.returncode == 0) == (outcome["status"] == "success"), outcome
    return outcome


def check_status(outcome, status, code=None):
    assert outcome["status"] == status, outcome
    if code:
        assert outcome["error"]["code"] == code, outcome
        assert outcome["result"] is None
    else:
        assert outcome["error"] is None, outcome


def main():
    with tempfile.TemporaryDirectory(prefix="sedrava-host-a2-") as tmp:
        root = Path(tmp)
        inbox, outbox, listings = (root / name for name in ("inbox", "outbox", "listings"))
        for p in [inbox, outbox, listings]:
            p.mkdir()
        (inbox / "config.json").write_text(
            '{"title":"Inventory","count":3,"active":true,"nested":{"id":12}}',
            encoding="utf-8",
        )
        (listings / "one").write_text("file", encoding="utf-8")
        (listings / "sub").mkdir()
        scopes = ["--read-scope", "inbox", "--write-scope", "outbox",
                  "--list-scope", "listings"]
        grants = ["--trusted", "--allow-read", "--allow-list", "--allow-write"]
        program = '''host "Inventory"
arg input: text
read_json config from input
json_get_text title from config at "title"
json_get_int amount from config at "count"
json_get_bool enabled from config at "active"
json_get_json nested from config at "nested"
json_get_int ident from nested at "id"
list_dir entries from "."
json_count size from entries
json_object output
json_set output.title = title
json_set output.amount = amount
json_set output.enabled = enabled
json_set output.items = entries
json_set output.size = size
json_set output.ident = ident
write_json "report.json" = output
emit_json output
'''
        result = execute(program, root, grants=grants, args=("input=config.json",), scopes=scopes)
        check_status(result, "success")
        assert (result["phase"], result["commit_state"]) == ("commit", "committed")
        output = result["result"]["result"]
        assert output == {
            "title": "Inventory", "amount": 3, "enabled": True,
            "items": [{"kind": "file", "name": "one"},
                      {"kind": "directory", "name": "sub"}],
            "size": 2, "ident": 12,
        }, output
        written = outbox / "report.json"
        assert json.loads(written.read_text()) == output
        assert written.stat().st_mode & 0o777 == 0o600

        # Explicit capabilities are not inferred from source.
        for grant in grants:
            remaining = [g for g in grants if g != grant]
            result = execute(program, root, grants=remaining,
                             args=("input=config.json",), scopes=scopes)
            check_status(result, "rejected", "CONFIGURATION_REJECTED")
        existing = written.read_bytes()
        result = execute(program, root, grants=grants,
                         args=("input=config.json",), scopes=scopes)
        check_status(result, "failed", "FILE_EXISTS")
        assert result["phase"] == "commit" and result["commit_state"] == "unknown"
        assert written.read_bytes() == existing

        # Strict JSON, typed field access and bounded reads; no output committed.
        readonly = '''host "Read"
arg path: text
read_json doc from path
json_get_text title from doc at "title"
emit title
'''
        for raw in (
            '{"title":"first","title":"last"}',
            '{"title":1.2}',
            '{"title":2147483648}',
            '{"title":"\\ud800"}',
            '{"title":"x",' + '"a":[' * 9 + '0' + ']}' * 9,
        ):
            (inbox / "bad.json").write_text(raw)
            result = execute(readonly, root, grants=["--trusted", "--allow-read"],
                             args=("path=bad.json",), scopes=scopes)
            check_status(result, "failed", "INVALID_JSON")
            assert result["phase"] == "execute"
        (inbox / "bad.json").write_bytes(b"\xff")
        check_status(execute(readonly, root,
                     grants=["--trusted", "--allow-read"],
                     args=("path=bad.json",), scopes=scopes),
                     "failed", "INVALID_ENCODING")
        (inbox / "bad.json").write_text('{"title":42}')
        check_status(execute(readonly, root, grants=["--trusted", "--allow-read"],
                     args=("path=bad.json",), scopes=scopes),
                     "failed", "INVALID_JSON")

        # Directory enumeration fails closed on symlinks, special and hardlinked entries.
        list_source = 'host "List"\nlist_dir result from "."\nemit_json result\n'
        (listings / "bad-link").symlink_to(listings / "one")
        check_status(execute(list_source, root, grants=["--trusted", "--allow-list"],
                             scopes=scopes), "fault", "POLICY_VIOLATION")
        (listings / "bad-link").unlink()
        os.link(listings / "one", listings / "hardlink")
        check_status(execute(list_source, root, grants=["--trusted", "--allow-list"],
                             scopes=scopes), "fault", "POLICY_VIOLATION")
        (listings / "hardlink").unlink()
        os.mkfifo(listings / "fifo")
        check_status(execute(list_source, root, grants=["--trusted", "--allow-list"],
                             scopes=scopes), "fault", "POLICY_VIOLATION")
        (listings / "fifo").unlink()
        for i in range(31):
            (listings / f"other-{i:02d}").touch()
        check_status(execute(list_source, root, grants=["--trusted", "--allow-list"],
                             scopes=scopes), "failed", "RESOURCE_TOO_LARGE")
        for i in range(31):
            (listings / f"other-{i:02d}").unlink()

        # Independently scoped directory changes, no recursive mutation.
        mkdir_source = 'host "Create"\nmkdir "newdir"\nemit true\n'
        rmdir_source = 'host "Remove"\nrmdir "newdir"\nemit true\n'
        for src, required in ((mkdir_source, "--allow-mkdir"),
                              (rmdir_source, "--allow-rmdir")):
            check_status(execute(src, root, grants=["--trusted", "--allow-write"],
                                 scopes=scopes), "rejected", "CONFIGURATION_REJECTED")
        check_status(execute(mkdir_source, root,
                             grants=["--trusted", "--allow-write", "--allow-mkdir"],
                             scopes=scopes), "success")
        assert (outbox / "newdir").is_dir()
        assert (outbox / "newdir").stat().st_mode & 0o777 == 0o700
        (outbox / "newdir" / "file").write_text("keep")
        check_status(execute(rmdir_source, root,
                             grants=["--trusted", "--allow-write", "--allow-rmdir"],
                             scopes=scopes), "failed", "DIRECTORY_NOT_EMPTY")
        (outbox / "newdir" / "file").unlink()
        check_status(execute(rmdir_source, root,
                             grants=["--trusted", "--allow-write", "--allow-rmdir"],
                             scopes=scopes), "success")
        assert not (outbox / "newdir").exists()

        # JSON as an explicit Host argument; arrays accept integer indexing.
        array = '''host "Array"
arg config: json
json_get_json arr from config at "arr"
json_get_int first from arr at 0
emit first
'''
        result = execute(array, root, grants=["--trusted"],
                         args=('config={"arr":[42]}',))
        check_status(result, "success")
        assert result["result"]["result"] == 42
        for raw in ('{"arr":[42],"arr":[23]}', '{"arr":[1.5]}', '{"arr":[2147483648]}'):
            check_status(execute(array, root, grants=["--trusted"],
                         args=("config=" + raw,)), "rejected", "CONFIGURATION_REJECTED")

        # JSON field cannot be replaced; action rejection prevents planned mutation.
        rollback = '''host "Rollback"
json_object report
json_set report.title = "ok"
write_json "rollback.json" = report
json_set report.title = "again"
emit_json report
'''
        check_status(execute(rollback, root,
                             grants=["--trusted", "--allow-write"],
                             scopes=scopes), "failed", "INVALID_JSON")
        assert not (outbox / "rollback.json").exists()

        # Source contract: only one mutation, no undeclared JSON values.
        for invalid in (
            'host "X"\nmkdir "x"\nrmdir "x"\nemit true\n',
            'host "X"\njson_get_int n from missing at "x"\nemit n\n',
            'host "X"\njson_object doc\njson_set doc.x = doc\n'
            'json_set doc.x = doc\nemit_json doc\n',  # runtime failure if run, not source failure
        )[:2]:
            src = root / "bad-host.sdr"
            src.write_text(invalid)
            checked = subprocess.run([str(BIN), "host", "check", str(src)],
                                     capture_output=True, text=True, timeout=5)
            assert checked.returncode != 0, invalid

    print("PASS: native Host A2 JSON/dir grants, strict parsing, bounds, rollback, no overwrite, A3 statuses")
    print("PASS: native Host A2 execution without Python in PATH")


if __name__ == "__main__":
    main()
