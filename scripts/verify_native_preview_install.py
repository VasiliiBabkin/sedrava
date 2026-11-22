#!/usr/bin/env python3
"""Reproducible native preview TAR and offline SHA-pinned installer conformance.

Python is used only by the maintainer/test harness. The installed binary
and sh installer run without a Python interpreter on PATH.
"""
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile

ROOT=Path(__file__).resolve().parents[1]
EXEC=ROOT/"rust/target/release/sedrava-native"
INSTALL=ROOT/"scripts/install_native_preview.sh"

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def execute(args,env=None,expect=True):
    proc=subprocess.run(
        list(map(str,args)),env=env,text=True,capture_output=True,
        timeout=90,check=False
    )
    assert (proc.returncode==0)==expect, (args,proc.returncode,proc.stdout,proc.stderr)
    return proc

def main():
    assert EXEC.is_file() and INSTALL.is_file()
    with tempfile.TemporaryDirectory(prefix="sdr-native-install-") as td:
        tmp=Path(td)
        archive_dir=tmp/"archives"
        command=["python3",ROOT/"scripts/package_native_preview.py",
                 "--binary",EXEC,"--output",archive_dir]
        first=json.loads(execute(command).stdout)
        archive=Path(first["archive"])
        assert archive.is_file()
        checksum=sha(archive)
        assert first["archive_sha256"]==checksum
        assert first["dirty_source"] in (True,False)
        second=json.loads(execute(command).stdout)
        assert checksum==sha(archive)==second["archive_sha256"]
        assert first["binary_sha256"]==sha(EXEC)

        # Strict PATH: no Python, pip, rustc or cargo installed in tool bin.
        tools=tmp/"tools"
        tools.mkdir()
        for name in ("sha256sum","shasum","cut","tr","wc","mkdir","mktemp",
                     "cmp","tar","awk","chmod","ln","rm","gzip","cat"):
            path=shutil.which(name)
            if path:
                (tools/name).symlink_to(path)
        assert not (tools/"python3").exists()
        env={"PATH":str(tools),"HOME":str(tmp),"LC_ALL":"C"}
        prefix=tmp/"install"
        command=["/bin/sh",INSTALL,archive,checksum,prefix]
        execute(command,env=env)
        installed=prefix/"bin/sedrava-native"
        assert installed.is_file() and os.access(installed,os.X_OK)
        assert sha(installed)==sha(EXEC)
        execute([installed,"--version"],env=env)
        execute([installed,"check",ROOT/"examples/native_aliases/main.sdr"],env=env)
        execute([installed,"test",ROOT/"examples/native_aliases/main.sdr"],env=env)
        execute(command,env=env,expect=False)  # No accidental overwrite.
        assert sha(installed)==sha(EXEC)
        bad=tmp/"bad-prefix"
        execute(["/bin/sh",INSTALL,archive,"0"*64,bad],env=env,expect=False)
        assert not (bad/"bin/sedrava-native").exists()

        # A separately SHA-pinned but malformed archive must also be rejected.
        tampered=tmp/"extra.tar.gz"
        with tarfile.open(archive,"r:gz") as source, tarfile.open(
            tampered,"w:gz") as dest:
            for original in source:
                dest.addfile(original,source.extractfile(original))
            item=tarfile.TarInfo("untrusted/extra")
            payload=b"unexpected\n"
            item.size=len(payload)
            dest.addfile(item,io.BytesIO(payload))
        execute(["/bin/sh",INSTALL,tampered,sha(tampered),bad],env=env,expect=False)
        assert not (bad/"bin/sedrava-native").exists()

        # Reject symlinked publication directory and preserve its target.
        dest=tmp/"symlink-prefix"
        dest.mkdir()
        (dest/"bin").symlink_to(prefix/"bin",target_is_directory=True)
        execute(["/bin/sh",INSTALL,archive,checksum,dest],env=env,expect=False)
        assert sha(installed)==sha(EXEC)

        print("PASS: two reproducible SHA256-identical native tar.gz preview archives")
        print("PASS: no-Python/no-Rust-on-PATH installer + native app check/test")
        print("PASS: existing binary, corrupt hash, extra entries and symlink bin rejected")
        print(f"ARCHIVE_SHA256={checksum}")
        print(f"BINARY_SHA256={sha(EXEC)}")
        print(f"ARCHIVE_BYTES={archive.stat().st_size}")
        print(f"ARCHIVE_SOURCE_SHA={first['source_sha']}")
        print(f"ARCHIVE_DIRTY_SOURCE={first['dirty_source']}")

if __name__=="__main__":
    main()
