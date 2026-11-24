"""Offline native 0.12-style vendored package lock conformance and tamper cases.

Must not use the network or GitHub Actions. All mutations confined to TemporaryDirectory.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
BIN = ROOT / "rust/target/debug/sedrava"
SAMPLE = ROOT / "examples/native_locked_app"


def invoke(*args, ok):
    process = subprocess.run(
        [str(BIN), *map(str, args)],
        text=True, capture_output=True, check=False, timeout=15,
        env={**os.environ, "PATH": "/nonexistent"},
    )
    assert (process.returncode == 0) == ok, (
        f"expected ok={ok} for {args}:\n{process.stdout}\n{process.stderr}"
    )
    return process


def main():
    with tempfile.TemporaryDirectory(prefix="native-packages-check-") as tmp:
        project = Path(tmp) / "project"
        shutil.copytree(SAMPLE, project)
        source = project / "main.sdr"
        lock = project / "sedrava.lock"
        vendor = project / "vendor/example.math/math.sdr"
        manifest = project / "sedrava.toml"
        original = lock.read_bytes()
        original_vendor = vendor.read_bytes()
        original_manifest = manifest.read_bytes()

        invoke("verify", project, ok=True)
        invoke("check", source, ok=True)
        invoke("test", source, ok=True)
        invoke("lock", project, ok=True)
        assert lock.read_bytes() == original, "Native lockfile changed unexpectedly"

        # A vendored import must be pinned to exact content bytes.
        vendor.write_text("fn twice(n: int) -> int = n * 3\n")
        invoke("check", source, ok=False)
        invoke("verify", project, ok=False)
        vendor.write_bytes(original_vendor)
        invoke("check", source, ok=True)

        # Modification of root manifest invalidates lock even if content stays valid.
        manifest.write_text(original_manifest.decode().replace("0.1.0", "0.2.0"))
        invoke("check", source, ok=False)
        manifest.write_bytes(original_manifest)
        invoke("verify", project, ok=True)

        # All duplicate keys must reject before semantic comparison, even if equal.
        data = original.decode()
        assert '"schema": 1' in data
        lock.write_text(data.replace('"schema": 1', '"schema": 1,\n  "schema": 1'))
        invoke("verify", project, ok=False)
        lock.write_bytes(original)

        # Resource and file-type checks on lock operations.
        hidden = project / "vendor/example.math/.unreviewed"
        hidden.write_bytes(b"hidden")
        invoke("lock", project, ok=False)
        assert lock.read_bytes() == original
        hidden.unlink()
        if hasattr(os, "symlink"):
            symlink = project / "vendor/example.math/symlink.sdr"
            symlink.symlink_to(vendor)
            invoke("lock", project, ok=False)
            assert lock.read_bytes() == original
            symlink.unlink()
        if hasattr(os, "link"):
            link = project / "vendor/example.math/hardlinked.sdr"
            os.link(vendor, link)
            invoke("lock", project, ok=False)
            assert lock.read_bytes() == original
            link.unlink()

        # Incorrect reviewed vendor path is not silently accepted.
        manifest.write_text(
            original_manifest.decode().replace(
                'path = "vendor/example.math"',
                'path = "../elsewhere"'
            )
        )
        invoke("lock", project, ok=False)
        assert lock.read_bytes() == original
        manifest.write_bytes(original_manifest)

        # Existing lock removed => fail-closed for builds; no implicit lock creation.
        lock.unlink()
        invoke("verify", project, ok=False)
        invoke("check", source, ok=False)
        invoke("lock", project, ok=True)
        invoke("check", source, ok=True)
        assert lock.read_bytes() == original

        # A symlink replacement to another lockfile must not be read or replaced.
        lock.unlink()
        lock.symlink_to(project / "elsewhere")
        invoke("lock", project, ok=False)
        invoke("verify", project, ok=False)
        lock.unlink()
        lock.write_bytes(original)

        # No project manifest/lock: ordinary legacy imports continue working.
        bare = Path(tmp) / "legacy"
        bare.mkdir()
        (bare / "app.sdr").write_text('app "Legacy"\nstate count = 0\n')
        invoke("check", bare / "app.sdr", ok=True)

        # An unreviewed 'vendor' import is not implicitly trusted.
        standalone = Path(tmp) / "unreviewed"
        (standalone / "vendor").mkdir(parents=True)
        (standalone / "vendor" / "math.sdr").write_bytes(original_vendor)
        (standalone / "app.sdr").write_text(
            'app "Unreviewed"\nimport "vendor/math.sdr"\nstate count = 0\n'
        )
        invoke("check", standalone / "app.sdr", ok=False)

        assert json.loads(original)["schema"] == 1
        print("PASS: native package locks, Python 0.12-compatible schema and deterministic bytes")
        print("PASS: modified/hidden/symlink/hardlink/stale/duplicate/missing-lock cases fail closed")
        print("PASS: legacy imports remain supported, unreviewed vendored code rejected")


if __name__ == "__main__":
    main()
