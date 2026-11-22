#!/usr/bin/env python3
"""Native local-import parsing compared with Python expanded source semantics."""
import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--native",type=Path,
                    default=ROOT/"rust/target/debug/sedrava-native")
    args=ap.parse_args()
    native=args.native.resolve()
    fixture=ROOT/"tests/rust_cases/native_imports.sdr"
    rust=subprocess.run([str(native),"run",str(fixture),"increase"],
                        capture_output=True,text=True,timeout=30)
    assert rust.returncode==0,rust.stderr
    rust_state=json.loads(rust.stdout)

    from sedrava_modules import expand
    from sedrava_core import parse,transition,resolve
    from sedrava_records import plain
    source,_=expand(fixture.read_text(encoding="utf8"),fixture)
    program=parse(source)
    state,accepted=transition(program,program.states,"increase")
    assert accepted
    python_state={key:plain(value) for key,value in resolve(state,program.derived).items()}
    assert rust_state==python_state,(rust_state,python_state)

    expanded=subprocess.run([str(native),"expand",str(fixture)],
                            capture_output=True,text=True,timeout=30)
    assert expanded.returncode==0,expanded.stderr
    assert expanded.stdout.strip()==source.strip()
    assert "fn double" in expanded.stdout

    check=subprocess.run([str(native),"test",str(fixture)],
                         capture_output=True,text=True,timeout=30)
    assert check.returncode==0,check.stderr
    print("PASS: Rust/Python local import expansion and action result")
    return 0


if __name__=="__main__":
    raise SystemExit(main())
