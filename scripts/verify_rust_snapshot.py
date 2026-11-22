#!/usr/bin/env python3
"""Check Python 0.11 <-> Rust schema-1 persistence and failure atomicity.

Only disposable temporary JSON files are used. Must run after native build.
This is protocol conformance for tested samples, not crash-consistency proof.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/rust_cases/persistent_records.sdr"


def command(binary: list[str], file: Path, *actions: str, state: Path | None = None,
            success: bool = True) -> dict | None:
    args = [*binary, "run", str(file), *actions]
    if state is not None:
        args += ["--state-file", str(state)]
    r = subprocess.run(args, cwd=ROOT, text=True, encoding="utf-8",
                       capture_output=True, timeout=25, check=False)
    if (r.returncode == 0) != success:
        raise AssertionError(f"unexpected CLI status: {args} -> {r.returncode}; stderr={r.stderr[:600]}")
    return json.loads(r.stdout) if success else None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--native", type=Path,
                        default=ROOT / "rust/target/debug/sedrava-native")
    parser.add_argument("--report", type=Path)
    opts = parser.parse_args()
    native = opts.native.resolve()
    if not native.is_file():
        parser.error(f"Missing native binary {native}")
    python = [sys.executable, str(ROOT / "sedrava_cli.py")]
    rust = [str(native)]
    checks: list[str] = []

    with tempfile.TemporaryDirectory(prefix="sedrava-native-persist-") as scratch:
        folder = Path(scratch)
        from_python = folder / "from-python.json"
        from_rust = folder / "from-rust.json"

        py1 = command(python, FIXTURE, "add", state=from_python)
        saved_py = json.loads(from_python.read_text("utf-8"))
        assert py1["total"] == 1
        assert saved_py["state"]["tasks"]["items"][0]["id"] == 1
        checks.append("Python produced a valid schema-1 snapshot")

        rust1 = command(rust, FIXTURE, "complete", state=from_python)
        py_check = command(python, FIXTURE, state=from_python)
        assert rust1 == py_check
        assert rust1["completed"] == 1
        assert json.loads(from_python.read_text("utf-8"))["signature"] == saved_py["signature"]
        checks.append("Rust loaded Python snapshot, changed records, Python restored identical state")

        rust2 = command(rust, FIXTURE, state=from_rust)
        py2 = command(python, FIXTURE, state=from_rust)
        assert rust2 == py2
        rust_saved = json.loads(from_rust.read_text("utf-8"))
        assert rust_saved == json.loads(command_json(python, FIXTURE, folder / "test-py.json"))
        checks.append("Python read Rust snapshot and schema signature matched")

        py3 = command(python, FIXTURE, "add", state=from_rust)
        rust3 = command(rust, FIXTURE, state=from_rust)
        assert py3 == rust3
        checks.append("Python updated Rust snapshot; Rust restored it")

        before = from_rust.read_bytes()
        command(rust, FIXTURE, "reject", state=from_rust, success=False)
        assert from_rust.read_bytes() == before
        checks.append("Rust rejected require violation without modifying snapshot")

        for name, change in {
            "duplicate-key": lambda d: from_python.read_text("utf-8").replace(
                '"schema":1', '"schema":1,"schema":1', 1),
            "bad-signature": lambda d: json.dumps({**d, "signature": "incorrect"}),
            "bad-schema": lambda d: json.dumps({**d, "schema": 2}),
            "floating-point-number": lambda d: json.dumps({**d, "schema": 1.0}),
            "bad-record-id": lambda d: json.dumps({**d, "state": {
                **d["state"], "tasks": {**d["state"]["tasks"], "items": [
                    {**d["state"]["tasks"]["items"][0], "id": True}]}}}),
            "out-of-range-int": lambda d: json.dumps({**d, "state": {
                **d["state"], "tasks": {**d["state"]["tasks"], "next_id": 2147483648}}}),
            "unknown-state-key": lambda d: json.dumps({**d, "state": {**d["state"], "unknown": 1}}),
        }.items():
            current = json.loads(from_python.read_text("utf-8"))
            payload = change(current)
            bad = folder / f"invalid-{name}.json"
            bad.write_text(payload, "utf-8")
            original = bad.read_bytes()
            command(rust, FIXTURE, state=bad, success=False)
            assert bad.read_bytes() == original
            command(python, FIXTURE, state=bad, success=False)
            assert bad.read_bytes() == original
            checks.append(f"Both engines reject {name} without modifying snapshot")

        nav_source = ROOT / "examples/task_manager_navigation.sdr"
        nav_file = folder / "navigation.json"
        py_nav = command(python, nav_source, state=nav_file)
        rust_nav = command(rust, nav_source, "$back", state=nav_file)
        assert py_nav == rust_nav
        assert command(python, nav_source, state=nav_file) == rust_nav
        checks.append("Navigation snapshots keep only canonical state, not derived fields")

        src_before = FIXTURE.read_bytes()
        command(rust, FIXTURE, state=FIXTURE, success=False)
        assert FIXTURE.read_bytes() == src_before
        checks.append("The source file cannot be used as the snapshot destination")

    report = {
        "schema": "sedrava-native-snapshot-conformance-v1",
        "fixture": "tests/rust_cases/persistent_records.sdr",
        "checks": len(checks),
        "passed": checks,
        "scope": "Python/Rust portable schema-1 JSON, typed records, failure non-modification on local filesystem",
        "not_verified": ["Power-loss durability", "Concurrent writers", "Windows/macOS atomic rename", "All user programs"]
    }
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if opts.report:
        opts.report.parent.mkdir(parents=True, exist_ok=True)
        opts.report.write_text(rendered, encoding="utf-8")
    print(rendered)
    return 0


def command_json(binary: list[str], source: Path, output: Path) -> str:
    command(binary, source, state=output)
    return output.read_text("utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
