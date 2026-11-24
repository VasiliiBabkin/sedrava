#!/usr/bin/env python3
"""Check Rust Android project generation and identity safety (not APK build).

APK and JVM tests run separately in verify_native_android_kotlin.py.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[1]
from legacy_reference import legacy_root
sys.path.insert(0,str(legacy_root()))
from sedrava_android_identity import project_identity

def run(binary,src,out,app_id,success=True):
    result=subprocess.run([str(binary),"build","android",str(src),"--output",
                           str(out),"--application-id",app_id],
                          cwd=ROOT,capture_output=True,text=True,timeout=35)
    if (result.returncode==0)!=success:
        raise AssertionError(f"Unexpected Android generator exit {result.returncode}: {result.stderr}")
    return result

def main()->int:
    p=argparse.ArgumentParser()
    p.add_argument("--native",type=Path,default=ROOT/"rust/target/debug/sedrava")
    args=p.parse_args()
    binary=args.native.resolve()
    cases=[
        (ROOT/"examples/counter.sdr","org.sedrava.testcounter"),
        (ROOT/"tests/rust_cases/native_android_scalar.sdr","org.sedrava.demo"),
        (ROOT/"examples/task_manager_navigation.sdr","org.sedrava.tasks"),
        (ROOT/"tests/rust_cases/native_web_queries.sdr","org.sedrava.queries"),
    ]
    with tempfile.TemporaryDirectory(prefix="sdr-native-android-") as temp:
        for source,app_id in cases:
            root=Path(temp)/app_id
            one=root/"a";two=root/"b"
            run(binary,source,one,app_id)
            run(binary,source,two,app_id)
            names={p.relative_to(one) for p in one.rglob("*") if p.is_file()}
            assert names=={p.relative_to(two) for p in two.rglob("*") if p.is_file()}
            for file in names:
                assert (one/file).read_bytes()==(two/file).read_bytes()
            assert project_identity(one)==app_id
            meta=json.loads((one/"sedrava-android.json").read_text("utf8"))
            assert set(meta)=={"schema","application_id","namespace","title"}
            manifest=ET.parse(one/"app/src/main/AndroidManifest.xml")
            assert manifest.getroot().tag=="manifest"
            resource=ET.parse(one/"app/src/main/res/values/strings.xml")
            assert resource.getroot().tag=="resources"
            main=list(one.rglob("MainActivity.kt"))
            assert len(main)==1
            kotlin = {p.name: p.read_text("utf8") for p in main[0].parent.glob("*.kt")}
            assert set(kotlin) == {"MainActivity.kt", "Domain.kt", "Program.kt", "Snapshots.kt", "Storage.kt", "Collections.kt", "Navigation.kt"}
            assert all(text.startswith(f"package {app_id}\n") for text in kotlin.values())
            assert "setContent" in kotlin["MainActivity.kt"]
            assert not manifest.getroot().findall("uses-permission")
            if "native_android_scalar" in source.name:
                assert "Android Rust · Демо" in meta["title"]
                assert "\\@" in (one/"app/src/main/res/values/strings.xml").read_text()
                assert "OutlinedTextField" in kotlin["MainActivity.kt"]
            run(binary,source,one,app_id,success=False)
            assert project_identity(one)==app_id
            print(f"PASS: deterministic native Android preview, {source.name}, identity={app_id}")
        for invalid in ("bad","com..bad","org.class","org.Bad","../escape"):
            output=Path(temp)/("bad-"+str(len(invalid))) / invalid.replace("/","_")
            run(binary,cases[0][0],output,invalid,success=False)
            assert not output.exists()
        dangling=Path(temp)/"dangling"
        dangling.symlink_to(Path(temp)/"target-missing",target_is_directory=True)
        run(binary,cases[0][0],dangling,"org.sedrava.dangling",success=False)
        assert dangling.is_symlink()
        unsupported=Path(temp)/"unsupported"
        run(binary,ROOT/"examples/platform_catalog.sdr",
            unsupported,"org.sedrava.catalog",success=False)
        assert not unsupported.exists()
        print("PASS: invalid identifiers and unsupported WebApp are rejected without project creation")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
