#!/usr/bin/env python3
"""Native 0.12 alpha: reproducible smoke/negative acceptance on disposable data.

This is a *scope-limited release candidate* check, not a stable acceptance.
Python runs subprocesses only. Generated programs are native-Rust products.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
import re
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.12.0-alpha.1"


def invoke(binary: Path, *args: object, ok: bool = True, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [str(binary), *map(str, args)], cwd=ROOT,
        capture_output=True, text=True, encoding="utf-8",
        check=False, timeout=timeout,
    )
    if (result.returncode == 0) != ok:
        raise AssertionError(f"Unexpected exit={result.returncode} for {args}\nstdout={result.stdout[:1200]}\nstderr={result.stderr[:1700]}")
    return result


def parse_outputs(directory: Path) -> dict[str, bytes]:
    return {
        str(p.relative_to(directory)): p.read_bytes()
        for p in sorted(directory.rglob("*"))
        if p.is_file()
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--native", type=Path, required=True)
    ap.add_argument("--report", type=Path, default=None)
    opts = ap.parse_args()
    binary = opts.native.resolve()
    assert binary.is_file(), binary
    cargo_text = (ROOT / "rust/sedrava-core/Cargo.toml").read_text()
    assert re.findall(r'(?m)^version = "([^"]+)"$', cargo_text) == [VERSION]

    version = invoke(binary, "--version").stdout.strip()
    assert version == f"sedrava-native {VERSION} (experimental native preview; not stable)", version
    checks: list[dict[str, object]] = []
    def pass_gate(name: str, detail: str):
        checks.append({"gate": name, "outcome": "PASS", "detail": detail})
        print(f"PASS {name}: {detail}", flush=True)

    invoke(binary, "check", ROOT / "examples/reference_09.sdr")
    invoke(binary, "test", ROOT / "examples/reference_09.sdr")
    state = json.loads(invoke(binary, "run", ROOT / "examples/reference_09.sdr", "add", "add").stdout)
    assert state["progress"] == 2 and state["sessions"] == 2, state
    pass_gate("native-app", "check, tests and two state transitions without Python")

    state = json.loads(invoke(binary, "run", ROOT / "examples/self_host/lexer_a1.sdr", "scan").stdout)
    tokens = state["tokens"]["items"]
    assert [(t["kind"], t["lexeme"], t["offset"]) for t in tokens] == [
        ("identifier", "sum", 0), ("punct", "=", 3),
        ("integer", "42", 4), ("punct", "(", 7),
        ("identifier", "next", 8), ("punct", ")", 12),
    ], tokens
    pass_gate("native-alpha-only", "single Sedrava action with internal bounded while and six correct tokens")

    with tempfile.TemporaryDirectory(prefix="sedrava-native-012-check-") as name:
        root = Path(name)
        invalid = root / "bad.sdr"
        invalid.write_text('app "Bad"\nstate value = 0\naction mutate:\n    while true limit 0:\n        value = value + 1\n')
        invoke(binary, "check", invalid, ok=False)
        invoke(binary, "run", invalid, "mutate", ok=False)
        pass_gate("negative-parse", "invalid bounded loop rejected before execution")

        site_source = ROOT / "examples/site_native_preview.sdr"
        results = []
        for n in (1, 2):
            output = root / f"site-{n}"
            invoke(binary, "build", "site", site_source, "--output", output)
            assert (output / "index.html").is_file()
            assert (output / "guide/index.html").is_file()
            results.append(parse_outputs(output))
        assert results[0] == results[1]
        invoke(binary, "build", "site", site_source, "--output", root / "site-1", ok=False)
        pass_gate("native-site", "two deterministic Site builds; refusing overwrite")

        web_source = ROOT / "examples/webapp_011_counter.sdr"
        results = []
        for n in (1, 2):
            output = root / f"webapp-{n}"
            invoke(binary, "build", "webapp", web_source, "--output", output)
            assert (output / "index.html").is_file()
            assert any(p.suffix == ".js" for p in output.rglob("*.js"))
            results.append(parse_outputs(output))
        assert results[0] == results[1]
        pass_gate("native-webapp", "two deterministic WebApp builds with JS and HTML")

        android_source = ROOT / "examples/counter.sdr"
        output = root / "android"
        invoke(binary, "build", "android", android_source, "--output", output,
               "--application-id", "org.sedrava.alpha012")
        manifest = output / "app/src/main/AndroidManifest.xml"
        assert manifest.is_file()
        assert ET.parse(manifest).getroot().tag == "manifest"
        assert list(output.rglob("MainActivity.kt"))
        pass_gate("android-source", "Android Kotlin project emitted, NOT an APK or device test")

        server_source = ROOT / "examples/native_server/sqlite_a5.sdr"
        invoke(binary, "server", "check", server_source)
        pass_gate("native-server", "loopback server DSL static check; no network listener started")

        # A stdout/stderr error alone cannot be treated as full rejection;
        # inspect process exit code, used throughout this test.
    result = {
        "schema": "sedrava.native.alpha012.acceptance.v1",
        "version": VERSION,
        "source_sha": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "dirty_source": bool(subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=ROOT, text=True
        ).strip()),
        "binary_sha256": __import__("hashlib").sha256(binary.read_bytes()).hexdigest(),
        "scope": "Linux native CLI smoke; not full compatibility or stable",
        "checks": checks,
        "result": "PASS",
        "excluded": [
            "full Python 0.11 parity",
            "Android APK installation and device testing",
            "Windows/macOS binary builds",
            "full host security review and production threat model",
            "physical power-loss durability and production SQL",
            "signature and GitHub Releases publication",
        ],
    }
    if opts.report is not None:
        opts.report.parent.mkdir(parents=True, exist_ok=True)
        opts.report.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(f"PASS {len(checks)} scoped native alpha acceptance gates", flush=True)


if __name__ == "__main__":
    main()
