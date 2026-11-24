"""Compile and execute native Kotlin/JVM typed Result/match generated from Rust.

Uses only the checked Rust Android generator, Gradle Kotlin/JVM and a Python
JSON-oracle comparison; no real Android device/emulator is implied.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/"examples/native_typed_errors_a1/main.sdr"
SOURCES=("Program.kt","Domain.kt","Collections.kt","Navigation.kt",
         "Snapshots.kt","Storage.kt")

def invoke(args, *, cwd=ROOT, env=None, timeout=420, expected=True):
    result=subprocess.run(
        [str(a) for a in args],cwd=cwd,env=env,
        capture_output=True,text=True,timeout=timeout,check=False
    )
    if (result.returncode==0)!=expected:
        raise AssertionError(f"UNEXPECTED EXIT {result.returncode}: {args}\n{result.stdout[-4000:]}\n{result.stderr[-8000:]}")
    return result

def oracle(native):
    steps=[(),("success",),("success","fail"),
           ("success","fail","fallback")]
    return [json.loads(invoke([native,"run",SRC,*actions]).stdout)
            for actions in steps]

def test_source():
    return '''package org.sedrava.typed

internal fun runVerification() {
    fun state(s: Session): String = encodeJson(resolve(s.state))
    var session=Session()
    println("TYPED_STATE=" + state(session))
    val error=checkNotNull((resolve(session.state).getValue("recent") as SdrResult.Failure).error)
    check(error.id=="example.ArithmeticError.IntOverflow")
    check(error.fields == mapOf("left" to 100,"right" to 1))
    check(resolve(session.state).getValue("defaulted") == -1)
    check(resolve(session.state).getValue("succeeded") == true)
    check(nominalError("ReadError","Denied",mapOf("path" to "text")).id=="example.ReadError.Denied")
    check(validated { nominalError("ReadError","Denied",mapOf("path" to 1)) } == null)
    check(validated { nominalError("ReadError","Unknown",emptyMap()) } == null)
    check(validated { nominalError("ArithmeticError","IntOverflow",mapOf("left" to 3)) } == null)
    check(validated { checkValue(SdrResult.Success("bad"),
        SdrType.Result(SdrType.Integer,SdrType.Error("ArithmeticError"))) } == null)
    check(validated { checkValue(
        SdrError("ReadError","forged.ReadError.Denied","Denied",mapOf("path" to "x")),
        SdrType.Error("ReadError")) } == null)

    session=checkNotNull(dispatch(session,"success"))
    println("TYPED_STATE=" + state(session))
    session=checkNotNull(dispatch(session,"fail"))
    println("TYPED_STATE=" + state(session))
    session=checkNotNull(dispatch(session,"fallback"))
    println("TYPED_STATE=" + state(session))
    val before=session
    check(dispatch(session,"rollback")==null)
    check(session==before)
    check(state(session)==state(before))
    val restored=restoreSnapshot(snapshot(session.state, full = true), full = true)
    check(restored==session.state)
    println("TYPED_ROLLBACK=PASS")
    println("PASS typed nominal error IDs, exact payloads, match, branches, atomicity and persistence")
}
'''

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--native",type=Path,default=ROOT/"rust/target/debug/sedrava")
    ap.add_argument("--gradle",type=Path,required=True)
    ap.add_argument("--gradle-user-home",type=Path)
    args=ap.parse_args()
    native=args.native.resolve()
    gradle=args.gradle.resolve()
    assert SRC.is_file() and native.is_file() and gradle.is_file()
    expected=oracle(native)
    with tempfile.TemporaryDirectory(prefix="native-typed-kotlin-") as td:
        work=Path(td)
        project=work/"android"
        invoke([native,"build","android",SRC,"--output",project,
                "--application-id","org.sedrava.typed"])
        manifest=project/"app/src/main/AndroidManifest.xml"
        assert manifest.is_file()
        source_root=project/"app/src/main/java/org/sedrava/typed"
        sources=work/"kotlin/src/main/kotlin"
        sources.mkdir(parents=True)
        for name in SOURCES:
            shutil.copy2(source_root/name,sources/name)
        (sources/"Verification.kt").write_text(test_source(),encoding="utf8")
        (sources/"Main.kt").write_text(
            "fun main() { org.sedrava.typed.runVerification() }\n",encoding="utf8")
        (work/"kotlin/settings.gradle.kts").write_text(
            'pluginManagement { repositories { mavenCentral(); gradlePluginPortal() } }\n'
            'rootProject.name = "TypedNativeSedravaJvm"\n',encoding="utf8")
        (work/"kotlin/build.gradle.kts").write_text(
            'plugins { kotlin("jvm") version "2.0.21"; application }\n'
            'repositories { mavenCentral() }\n'
            'application { mainClass.set("MainKt") }\n',encoding="utf8")
        env=os.environ.copy()
        if args.gradle_user_home:
            env["GRADLE_USER_HOME"]=str(args.gradle_user_home.resolve())
        env["JAVA_TOOL_OPTIONS"]="-Dfile.encoding=UTF-8"
        proc=invoke([gradle,"-p",work/"kotlin","--no-daemon","--max-workers=2",
                     "--console=plain","run"],env=env,timeout=580)
        lines=[line.removeprefix("TYPED_STATE=") for line in proc.stdout.splitlines()
               if line.startswith("TYPED_STATE=")]
        assert len(lines)==len(expected),(len(lines),proc.stdout)
        for i,(actual,reference) in enumerate(zip(lines,expected)):
            actual=json.loads(actual)
            assert actual==reference,(i,actual,reference)
        assert "TYPED_ROLLBACK=PASS" in proc.stdout
        assert "PASS typed nominal error IDs" in proc.stdout
        print("PASS: actual generated Kotlin/JVM compiled with Kotlin 2.0.21")
        print("PASS: four full-state traces == Rust (including ephemeral Result/Error JSON)")
        print("PASS: strict nominal payload/type/identity, state restore, fatal rollback")
        print("LIMIT: Kotlin/JVM is not a physical Android APK/device test")

if __name__=="__main__":
    main()
