#!/usr/bin/env python3
"""Package a locally compiled, experimental Sedrava native binary.

No publishing or signing. The archive is explicitly a preview, not a release.
"""
from __future__ import annotations
import argparse
import gzip
import hashlib
import io
import json
import re
import subprocess
import tarfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--binary", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    rustc = subprocess.run(["rustc", "-vV"], check=True, capture_output=True, text=True)
    host = next(line.split(": ", 1)[1] for line in rustc.stdout.splitlines()
                if line.startswith("host: "))
    binary = args.binary.resolve()
    data = binary.read_bytes()
    # Do not label an older binary as a new release merely because Cargo.toml
    # was edited. The binary itself is the authority for its identity.
    cargo_text = (ROOT / "rust/sedrava-core/Cargo.toml").read_text(encoding="utf-8")
    versions = re.findall(r'(?m)^version = "([^"]+)"$', cargo_text)
    if len(versions) != 1:
        raise ValueError("Ambiguous Rust package version in Cargo.toml")
    declared_version = versions[0]
    version_reply = subprocess.run(
        [str(binary), "--version"], check=True, capture_output=True,
        text=True, timeout=10,
    ).stdout.strip()
    expected_prefix = f"sedrava-native {declared_version} (experimental native preview;"
    if not version_reply.startswith(expected_prefix):
        raise ValueError(
            f"Stale or wrong binary version: {version_reply!r}; Cargo expects {declared_version}"
        )
    if not re.fullmatch(r"0\.12\.0-alpha\.[1-9][0-9]*", declared_version):
        raise ValueError("Only explicitly versioned 0.12.0 alpha candidates may use this packaging path")
    if len(data) < 1000:
        raise ValueError("Native binary unexpectedly small")
    name = "sedrava-native.exe" if "windows" in host else "sedrava-native"
    if binary.name != name:
        raise ValueError("Binary filename does not match host OS")
    gitsha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                            check=True, capture_output=True, text=True).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain"], cwd=ROOT,
                                check=True, capture_output=True, text=True).stdout.strip())
    manifest = {
        "schema": "sedrava-native-preview-v1",
        "version": declared_version, "channel": "alpha",
        "host": host, "source_sha": gitsha, "dirty_source": dirty,
        "binary_sha256": sha256(data),
        "binary_version": version_reply,
        "status": "EXPERIMENTAL; partial language only; not a stable release"
    }
    files = {
        f"sedrava-native/{name}": data,
        "sedrava-native/LICENSE": (ROOT / "LICENSE").read_bytes(),
        "sedrava-native/README.txt": (
            f"EXPERIMENTAL Sedrava Native {declared_version} for {host}.\n"
            "Not yet the complete compiler.\n"
            "Do not replace the stable Python CLI or use production state files.\n"
            "Run sedrava-native --version or sedrava-native --help.\n"
            "Verify the SHA256 before execution.\n"
        ).encode(),
        "sedrava-native/manifest.json":
            (json.dumps(manifest, sort_keys=True, indent=2) + "\n").encode(),
    }
    files["sedrava-native/SHA256SUMS.txt"] = "".join(
        f"{sha256(data)}  {path}\n" for path, data in sorted(files.items())
    ).encode("ascii")
    args.output.mkdir(parents=True, exist_ok=True)
    suffix = ".zip" if "windows" in host else ".tar.gz"
    output = args.output / f"sedrava-native-{declared_version}-{host}{suffix}"
    if suffix == ".zip":
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as z:
            for path, data in sorted(files.items()):
                info = zipfile.ZipInfo(path, date_time=(1980, 1, 1, 0, 0, 0))
                info.external_attr = ((0o755 if path.endswith(name) else 0o644) << 16)
                info.compress_type = zipfile.ZIP_DEFLATED
                z.writestr(info, data, compress_type=zipfile.ZIP_DEFLATED)
    else:
        with output.open("wb") as handle:
            with gzip.GzipFile(fileobj=handle, mode="wb", mtime=0, filename="") as gz:
                with tarfile.open(fileobj=gz, mode="w") as tar:
                    for path, data in sorted(files.items()):
                        entry = tarfile.TarInfo(path)
                        entry.size = len(data)
                        entry.mtime = 0
                        entry.mode = 0o755 if path.endswith(name) else 0o644
                        tar.addfile(entry, io.BytesIO(data))
    print(json.dumps({**manifest, "archive": str(output),
                      "archive_sha256": sha256(output.read_bytes())}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
