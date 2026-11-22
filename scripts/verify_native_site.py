#!/usr/bin/env python3
"""Independent CLI smoke check for the experimental native Site subset.

Requires a prebuilt Rust binary. This file is a test harness, not a Site
runtime. It does not use the Python Sedrava compiler.
"""
from __future__ import annotations

import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
CLI = ROOT / "rust" / "target" / "debug" / "sedrava-native"
SOURCE = ROOT / "examples" / "site_native_preview.sdr"


def run(*args: str, ok: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [str(CLI), *args], capture_output=True, text=True, cwd=ROOT, check=False
    )
    if (result.returncode == 0) != ok:
        raise AssertionError(
            f"Unexpected exit code {result.returncode} for {args}:\n"
            f"stdout={result.stdout}\nstderr={result.stderr}"
        )
    return result


def main() -> None:
    if not CLI.is_file():
        raise SystemExit(
            "Build first: cargo build --manifest-path rust/Cargo.toml "
            "--locked --bin sedrava-native"
        )
    run("check", str(SOURCE))
    with tempfile.TemporaryDirectory(prefix="sedrava-native-site-") as root:
        folder = pathlib.Path(root)
        for number in (1, 2):
            output = folder / f"site-{number}"
            run("build", "site", str(SOURCE), "--output", str(output))
            assert (output / "index.html").exists()
            assert (output / "guide" / "index.html").exists()
            html = (output / "index.html").read_text(encoding="utf-8")
            assert 'href="/guide/"' in html
            assert "without calling Python" in html
        assert (folder / "site-1" / "index.html").read_bytes() == (
            folder / "site-2" / "index.html"
        ).read_bytes()
        run("build", "site", str(SOURCE), "--output", str(folder / "site-1"), ok=False)
        assert (folder / "site-1" / "index.html").is_file()
        evil = folder / "evil.sdr"
        evil.write_text(
            'site "Demo"\npage home at "/":\n    title "T"\n'
            '    link "bad" to "javascript:alert(1)"\n',
            encoding="utf-8",
        )
        rejected = folder / "rejected"
        run("build", "site", str(evil), "--output", str(rejected), ok=False)
        assert not rejected.exists()
    print("PASS: native Site CLI, two pages, deterministic output, fail-closed cases")


if __name__ == "__main__":
    try:
        main()
    except (AssertionError, OSError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        raise SystemExit(1) from error
