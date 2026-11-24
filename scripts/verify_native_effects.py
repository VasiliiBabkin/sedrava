"""Independent Rust Effects & Targets A1 checks with optional Python 0.12 reference.

The manifest is *not* an OS permission grant or a complete UI/Host manifest.
Does not invoke GitHub Actions, browsers, network or production files.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / "rust/target/debug/sedrava"
SOURCE = '''app "Effects A1"
fn increase(x: int) -> int effects pure = x + 1
fn twice(y: int) -> int = increase(increase(y))
state total = 4
action update: total = twice(total)
screen main:
    value total
test updated: update -> total == 6
'''


def run(command, *, expected_success: bool):
    result = subprocess.run(
        command, capture_output=True, text=True, check=False, timeout=12,
        env={**os.environ, "PATH": "/nonexistent"},
    )
    assert (result.returncode == 0) == expected_success, (
        command, result.returncode, result.stdout, result.stderr
    )
    return result


def manifest(source, target="app"):
    out = run([str(NATIVE), "effects", str(source), "--target", target],
              expected_success=True).stdout.strip()
    parsed = json.loads(out)
    assert out == json.dumps(parsed, ensure_ascii=False, sort_keys=True, separators=(",", ":")), out
    assert parsed["schema"] == "sedrava.effects.v1" and parsed["kind"] == "app-domain", parsed
    return out, parsed


def main():
    options = argparse.ArgumentParser()
    options.add_argument("--python-reference", type=Path)
    args = options.parse_args()
    assert NATIVE.is_file()
    with tempfile.TemporaryDirectory(prefix="native-effects-a1-") as tmp:
        project = Path(tmp)
        src = project / "main.sdr"
        src.write_text(SOURCE, encoding="utf-8")

        # No Python code or interpreter required to produce the native manifest.
        app_bytes, app = manifest(src)
        _, web = manifest(src, "web")
        _, android = manifest(src, "android")
        assert app["effective"] == [] and android["effective"] == web["effective"] == []
        assert app["target"] == "app" and web["target"] == "web" and android["target"] == "android"
        assert app["functions"] == [
            {"name": "increase", "effective": [], "declared": []},
            {"name": "twice", "effective": [], "declared": None},
        ], app
        assert app_bytes == manifest(src)[0]
        assert app["source_sha256"] == hashlib.sha256(SOURCE.encode()).hexdigest()
        run([str(NATIVE), "check", str(src)], expected_success=True)
        run([str(NATIVE), "test", str(src)], expected_success=True)

        for bad_target in ("host", "server", "webapp", "site", "windows-os"):
            run([str(NATIVE), "effects", str(src), "--target", bad_target],
                expected_success=False)
        for invalid in (
            "effects { host.fs.read }",
            "effects host.fs.read",
            "effects all",
            "effects pure extra",
            "effects pure effects pure",
        ):
            src.write_text(SOURCE.replace("effects pure", invalid, 1), encoding="utf-8")
            run([str(NATIVE), "check", str(src)], expected_success=False)
            run([str(NATIVE), "effects", str(src)], expected_success=False)
        src.write_text(SOURCE)

        # The manifest must describe only an app, not an unsupported Site/Host document.
        src.write_text('host "Not an app"\nemit "x"\n')
        run([str(NATIVE), "effects", str(src)], expected_success=False)
        src.write_text(SOURCE)

        # Every imported function must be part of the hashed, checked source;
        # modifying an imported body changes hash while keeping it valid.
        module = project / "lib.sdr"
        module.write_text("fn plus(x: int) -> int effects pure = x + 1\n")
        src.write_text('app "Imported"\nimport "lib.sdr"\n'
                       'state n = 1\n'
                       'derive result = plus(n)\n'
                       'screen main:\n    value result\n')
        imported_manifest = manifest(src)[1]
        module.write_text("fn plus(x: int) -> int effects pure = x + 2\n")
        modified_manifest = manifest(src)[1]
        assert imported_manifest["source_sha256"] != modified_manifest["source_sha256"]
        assert imported_manifest["functions"] == modified_manifest["functions"]
        if args.python_reference is not None:
            py_cli = args.python_reference / "sedrava_cli.py"
            reference = run([sys.executable, str(py_cli), "effects", str(src)],
                            expected_success=True)
            native = manifest(src)[0]
            assert native == reference.stdout.strip(), (
                "Imported source hash/manifest differs from Python 0.12",
                native, reference.stdout,
            )
        module.write_text('fn plus(x: int) -> int effects { host.fs.read } = x\n')
        run([str(NATIVE), "effects", str(src)], expected_success=False)

        # Typed selector functions can be called indirectly through bounded queries.
        selector = ROOT / "tests/rust_cases/functions_queries.sdr"
        run([str(NATIVE), "effects", str(selector)], expected_success=True)

        if args.python_reference is not None:
            py_cli = args.python_reference / "sedrava_cli.py"
            assert py_cli.is_file(), py_cli
            src.write_text(SOURCE)
            py_result = run([sys.executable, str(py_cli), "effects",
                             str(src), "--target", "web"], expected_success=True)
            raw_native, _ = manifest(src, "web")
            assert raw_native == py_result.stdout.strip(), (
                "Python 0.12 and Rust Effects A1 differ",
                raw_native, py_result.stdout,
            )
            print("PASS: byte-identical canonical Effects A1 manifest vs Python 0.12 reference")

    print("PASS: pure annotations, inferred effects, known targets, deterministic manifest")
    print("PASS: imported function hash changes, unsupported signature and bad target rejection")
    print("PASS: no browser, OS Host/network grants or Python required for native execution")


if __name__ == "__main__":
    main()
