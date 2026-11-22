"""Run native trusted Host tests. Optionally compare exact A3 outcomes with Python."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / "rust/target/debug/sedrava-native"
SOURCE = '''host "Report"
arg input: text
arg output: text
read original from input
let report = concat("Report: ", original)
write output = report
emit report
'''


def execute(command, source, root, args, grants):
    proc = subprocess.run(
        [*command, "host", "run", str(source), "--root", str(root), *grants,
         "--read-scope", "inbox", "--write-scope", "outbox",
         "--result-protocol", "v1", *args],
        capture_output=True, text=True, timeout=5, check=False,
        env={**os.environ, **({"PATH": "/nonexistent"} if command == [str(NATIVE)] else {})},
    )
    result = json.loads(proc.stdout)
    assert (proc.returncode == 0) == (result["status"] == "success"), proc.stderr
    assert result["protocol"] == "sedrava.host.execution.v1"
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--python-host", type=Path, help="path to A3 sedrava_cli.py")
    options = parser.parse_args()
    native = [str(NATIVE)]
    python = [sys.executable, str(options.python_host.resolve())] if options.python_host else None
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        source = root / "host.sdr"
        source.write_text(SOURCE, encoding="utf-8")
        (root / "inbox").mkdir()
        (root / "outbox").mkdir()
        inbox, outbox = root / "inbox", root / "outbox"
        (inbox / "ok").write_text("hello", encoding="utf-8")
        (inbox / "bad-encoding").write_bytes(b"\xff")
        (inbox / "too-big").write_bytes(b"a" * 4097)
        (inbox / "too-many-scalars").write_bytes(b"a" * 1025)
        (inbox / "linked").symlink_to(inbox / "ok")
        (inbox / "subdir").symlink_to(inbox, target_is_directory=True)
        os.link(inbox / "ok", inbox / "hardlinked")
        # Use a separate normal inode, so the success path still has one link.
        (inbox / "ok").unlink()
        (inbox / "ok").write_text("hello", encoding="utf-8")
        os.link(inbox / "hardlinked", root / "second-hardlink")
        os.mkfifo(inbox / "pipe")
        grants = ["--trusted", "--allow-read", "--allow-write"]
        fixtures = [
            ("ok", "success", "commit", "committed", None),
            ("missing", "failed", "execute", "not_started", "FILE_NOT_FOUND"),
            ("../inbox/ok", "failed", "execute", "not_started", "INVALID_PATH"),
            ("bad-encoding", "failed", "execute", "not_started", "INVALID_ENCODING"),
            ("too-big", "failed", "execute", "not_started", "RESOURCE_TOO_LARGE"),
            ("too-many-scalars", "failed", "execute", "not_started", "TEXT_TOO_LONG"),
            ("linked", "fault", "execute", "not_started", "POLICY_VIOLATION"),
            ("subdir/ok", "fault", "execute", "not_started", "POLICY_VIOLATION"),
            ("hardlinked", "fault", "execute", "not_started", "POLICY_VIOLATION"),
            ("pipe", "fault", "execute", "not_started", "POLICY_VIOLATION"),
        ]
        for name, status, phase, commit, code in fixtures:
            args = ["--arg", "input=" + name, "--arg", "output=report"]
            result = execute(native, source, root, args, grants)
            assert [result[k] for k in ("status", "phase", "commit_state")] == [status, phase, commit], result
            if code:
                assert result["result"] is None
                assert result["error"] == {"code": code, "retryable": False}, result
                assert not (outbox / "report").exists()
            else:
                assert result["result"] == {"result": "Report: hello", "written": "report"}
                assert (outbox / "report").read_text(encoding="utf-8") == "Report: hello"
                assert (outbox / "report").stat().st_mode & 0o777 == 0o600
                (outbox / "report").unlink()
            if python:
                assert execute(python, source, root, args, grants) == result, name
                if (outbox / "report").exists():
                    (outbox / "report").unlink()

        args = ["--arg", "input=ok", "--arg", "output=report"]
        for missing in grants:
            remaining = [grant for grant in grants if grant != missing]
            result = execute(native, source, root, args, remaining)
            assert (result["status"], result["phase"]) == ("rejected", "setup")
            assert not (outbox / "report").exists()
            if python:
                assert execute(python, source, root, args, remaining) == result

        (outbox / "report").write_bytes(b"original")
        result = execute(native, source, root, args, grants)
        assert result["status"] == "failed" and result["commit_state"] == "unknown"
        assert result["error"] == {"code": "FILE_EXISTS", "retryable": False}
        assert (outbox / "report").read_bytes() == b"original"
        (outbox / "symlink").symlink_to(outbox / "report")
        result = execute(native, source, root, [*args[:2], "--arg", "output=symlink"], grants)
        assert result["status"] == "fault" and result["error"]["code"] == "POLICY_VIOLATION"
        assert (outbox / "report").read_bytes() == b"original"

        race_args = ["--arg", "input=ok", "--arg", "output=race"]
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: execute(native, source, root, race_args, grants), range(2)))
        assert sorted(result["status"] for result in results) == ["failed", "success"]
        assert (outbox / "race").read_text(encoding="utf-8") == "Report: hello"
        (outbox / "race").unlink()

        source.write_text('host "Read only"\nread content from "ok"\nemit content\n')
        result = execute(native, source, root, [], ["--trusted", "--allow-read"])
        assert result["commit_state"] == "not_applicable" and result["phase"] == "execute"
        assert result["result"] == {"result": "hello", "written": None}
        if python:
            assert execute(python, source, root, [], ["--trusted", "--allow-read"]) == result

        source.write_text('host "Rollback"\nwrite "pending" = "content"\nemit 2147483647 + 1\n')
        result = execute(native, source, root, [], grants)
        assert result["status"] == "fault" and result["phase"] == "execute"
        assert not (outbox / "pending").exists()
        assert sorted(p.name for p in outbox.iterdir()) == ["report", "symlink"]

        for unsupported in (
            'read x from "../input"\nemit x', 'read_json x from "data"\nemit 0',
            'fetch x from "https://example.com"\nemit 0', ''.join(f'let x{i} = 1\n' for i in range(64)) + 'emit x0',
            ''.join(f'read read{i} from "ok"\n' for i in range(9)) + 'emit 0',
        ):
            source.write_text('host "Reject"\n' + unsupported + '\n')
            result = subprocess.run([*native, "host", "check", str(source)], capture_output=True, timeout=5)
            assert result.returncode != 0, unsupported
    print("PASS: scoped Host text effects, four outcomes, resource and rollback checks")
    if python:
        print(f"PASS: {len(fixtures) + len(grants) + 1} exact Python A3/Rust outcomes")


if __name__ == "__main__":
    main()
