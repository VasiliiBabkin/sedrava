#!/usr/bin/env python3
"""Compile native Rust-generated Kotlin with JVM mocks (NOT Android SDK/APK).

Uses real Kotlin Gradle plugin, but replaces Android and Compose imports
with intentionally small test stubs. A PASS only proves JVM Kotlin compilation
and selected domain semantics, not Compose production compatibility.
"""
import argparse
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
STUBS=ROOT/"tests/native_android_jvm_stubs"
SAMPLE=ROOT/"tests/rust_cases/native_android_scalar.sdr"

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--native",type=Path,default=ROOT/"rust/target/debug/sedrava-native")
    p.add_argument("--gradle",type=Path,required=True)
    p.add_argument("--gradle-user-home",type=Path)
    opts=p.parse_args()
    binary=opts.native.resolve()
    gradle=opts.gradle.resolve()
    if not binary.is_file() or not gradle.is_file():
        p.error("Need compiled Rust binary and installed Gradle CLI")
    with tempfile.TemporaryDirectory(prefix="sdr-native-kt-") as temp:
        folder=Path(temp)
        generated=folder/"project"
        subprocess.run([str(binary),"build","android",str(SAMPLE),"--output",
                        str(generated),"--application-id","org.sedrava.demo"],
                       cwd=ROOT,check=True,timeout=45)
        sources=folder/"src/main/kotlin"
        sources.mkdir(parents=True)
        for source in STUBS.glob("*.kt"):
            shutil.copy2(source,sources/source.name)
        dest=sources/"MainActivity.kt"
        matching=list(generated.rglob("MainActivity.kt"))
        assert len(matching)==1
        shutil.copy2(matching[0],dest)
        (folder/"settings.gradle.kts").write_text(
            'pluginManagement { repositories { gradlePluginPortal(); mavenCentral() } }\n'
            'rootProject.name = "NativeSedravaKotlinSmoke"\n',encoding="utf8")
        (folder/"build.gradle.kts").write_text(
            'plugins { kotlin("jvm") version "2.0.21"; application }\n'
            'repositories { mavenCentral() }\n'
            'application { mainClass.set("SmokeKt") }\n'
            'kotlin { jvmToolchain(17) }\n',encoding="utf8")
        command=[str(gradle),"-p",str(folder),"--no-daemon","--console=plain","run"]
        env=__import__("os").environ.copy()
        if opts.gradle_user_home:
            env["GRADLE_USER_HOME"]=str(opts.gradle_user_home.resolve())
        proc=subprocess.run(command,cwd=ROOT,env=env,text=True,
                            capture_output=True,timeout=420)
        if proc.returncode:
            raise AssertionError("Kotlin verification failed:\n"+proc.stdout[-4000:]+"\n"+proc.stderr[-4000:])
        assert "PASS: Rust-generated Kotlin compiled" in proc.stdout,proc.stdout[-1500:]
        print("PASS: real Kotlin JVM compiler and domain smoke test using Android/Compose test stubs")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
