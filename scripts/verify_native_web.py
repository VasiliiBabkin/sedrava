#!/usr/bin/env python3
"""Build native Web UI without Python codegen and verify generated JS using Node.

This verifies only the supported scalar subset and mock DOM semantics,
not Chromium/Firefox/Android browser compatibility.
"""
import argparse
from pathlib import Path
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--native", type=Path,
                    default=ROOT/"rust/target/debug/sedrava-native")
    args=ap.parse_args()
    binary=args.native.resolve()
    with tempfile.TemporaryDirectory(prefix="sdr-native-web-") as directory:
        output=Path(directory)/"index.html"
        source=ROOT/"tests/rust_cases/native_web_ui.sdr"
        subprocess.run([str(binary),"build","web",str(source),"--output",str(output)],
                       cwd=ROOT,check=True,timeout=40)
        assert "<script>" in output.read_text(encoding="utf8")
        subprocess.run(["node",str(ROOT/"scripts/verify_native_web_node.js"),str(output)],
                       cwd=ROOT,check=True,timeout=20)
        invalid=ROOT/"examples/reference_09.sdr"
        reject=subprocess.run([str(binary),"build","web",str(invalid),
                               "--output",str(output)],
                              cwd=ROOT,text=True,capture_output=True,timeout=30)
        assert reject.returncode!=0
        assert "persistence" in reject.stderr.lower() or "persist" in reject.stderr.lower()
    print("PASS: native scalar Web generation (without Python subprocess)")

if __name__=="__main__":
    main()
