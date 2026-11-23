#!/usr/bin/env python3
"""Validate a native-Sedrava Android debug APK against expected public properties.

Does not install on a real phone. Requires a locally installed Android SDK.
"""
from __future__ import annotations

import argparse
import hashlib
import re
import subprocess
import sys
from pathlib import Path
from zipfile import ZipFile

EXPECTED_PACKAGE="ru.ladokod.sedrava.native012test"
EXPECTED_LABEL="Проверка Sedrava"


def run(*parts:str) -> str:
    proc=subprocess.run(parts,capture_output=True,text=True,timeout=30)
    if proc.returncode:
        raise RuntimeError(f"{parts[0]} failed (exit {proc.returncode}): {proc.stderr[-1200:]}")
    return proc.stdout


def main() -> int:
    parser=argparse.ArgumentParser()
    parser.add_argument("--apk",type=Path,required=True)
    parser.add_argument("--sdk",type=Path,required=True)
    opts=parser.parse_args()
    sdk=opts.sdk.resolve()
    apk=opts.apk.resolve()
    assert apk.is_file() and apk.stat().st_size>100_000
    build=sdk/"build-tools/35.0.0"
    info=run(str(build/"aapt"),"dump","badging",str(apk))
    sig=run(str(build/"apksigner"),"verify","--verbose","--print-certs",str(apk))
    assert f"name='{EXPECTED_PACKAGE}'" in info, "Unexpected package ID"
    assert f"application-label:'{EXPECTED_LABEL}'" in info, "Unexpected app label"
    assert "sdkVersion:'26'" in info, "Unexpected minimum Android API"
    assert "targetSdkVersion:'35'" in info, "Unexpected target Android API"
    assert "launchable-activity:" in info and "MainActivity" in info
    permissions=[s.strip() for s in info.splitlines() if s.startswith("uses-permission:")]
    assert all(EXPECTED_PACKAGE+".DYNAMIC_RECEIVER_NOT_EXPORTED_PERMISSION" in s for s in permissions), permissions
    assert "Verifies" in sig
    assert "Verified using v2 scheme (APK Signature Scheme v2): true" in sig
    assert "CN=Android Debug" in sig
    with ZipFile(apk) as archive:
        assert archive.testzip() is None, "Corrupt APK archive"
        names=set(archive.namelist())
        assert "AndroidManifest.xml" in names and "resources.arsc" in names
        assert any(re.fullmatch(r"classes(?:[0-9]+)?\.dex",s) for s in names)
    digest=hashlib.sha256(apk.read_bytes()).hexdigest()
    print("PASS: valid Android APK archive, classes.dex, resources and manifest")
    print("PASS: Android debug v2 signature")
    print("PASS: package, label, minSdk=26, targetSdk=35")
    print("PASS: no dangerous system permissions in the manifest")
    print(f"APK_SHA256={digest}")
    print(f"APK_SIZE={apk.stat().st_size}")
    print("DEVICE_INSTALL_NOT_VERIFIED")
    return 0


if __name__=="__main__":
    sys.exit(main())
