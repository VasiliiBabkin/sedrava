#!/usr/bin/env python3
"""Standalone native alias/import conformance and fail-closed corpus.

This checks Rust native behaviour, not Python 0.12 alias compatibility.
No CI/Actions and no network; temporary inputs are removed after each run.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
ENTRY=ROOT/"examples/native_aliases/main.sdr"
EXPECTED={
    "total":25,"summary":"example.alias.ParseFault.Invalid",
}

def run(args,ok=True):
    res=subprocess.run(
        [str(x) for x in args],capture_output=True,text=True,timeout=60,
        cwd=ROOT,check=False,
    )
    if (res.returncode==0)!=ok:
        raise AssertionError(f"{args}: exit={res.returncode}; stdout={res.stdout}; stderr={res.stderr}")
    return res

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--native",type=Path,default=ROOT/"rust/target/debug/sedrava")
    args=ap.parse_args()
    native=args.native.resolve()
    assert native.is_file()
    run([native,"check",ENTRY])
    run([native,"test",ENTRY])
    original=json.loads(run([native,"run",ENTRY,"calculate","populate"]).stdout)
    assert original["total"]==EXPECTED["total"],original
    assert original["summary"]==EXPECTED["summary"],original
    assert original["left_items"]["items"][0]["label"]=="left"
    assert original["right_items"]["items"][0]["label"]=="right"
    expanded=run([native,"expand",ENTRY]).stdout
    assert 'fn __sdns_left_increment' in expanded
    assert 'fn __sdns_right_increment' in expanded
    assert 'error closed __sdns_faults_ParseFault id "example.alias.ParseFault"' in expanded
    assert '"left.increment is a string, not a call"' in expanded

    with tempfile.TemporaryDirectory(prefix="native-aliases-") as temp:
        tmp=Path(temp)
        for p in ENTRY.parent.glob("*.sdr"):
            shutil.copy2(p,tmp/p.name)
        src=tmp/"main.sdr"
        flattened=tmp/"flattened.sdr"
        flattened.write_text(expanded,encoding="utf-8")
        run([native,"check",flattened])
        run([native,"test",flattened])
        assert json.loads(run([native,"run",flattened,"calculate","populate"]).stdout)==original
        manifest=json.loads(run([native,"effects",src,"--target","app"]).stdout)
        assert manifest["schema"]=="sedrava.effects.v1"
        app=tmp/"android"
        run([native,"build","android",src,"--output",app,
             "--application-id","org.sedrava.aliases"])
        assert (app/"app/src/main/java/org/sedrava/aliases/Program.kt").is_file()
        web=tmp/"site.html"
        run([native,"build","web",src,"--output",web])
        assert web.is_file()

        initial=src.read_text(encoding="utf-8")
        cases={
            "duplicate alias":initial.replace(
                'import "right.sdr" as right',
                'import "right.sdr" as left',1),
            "missing export":initial.replace(
                'left.twice(1)','left.nonexistent(1)',1),
            "bare alias":initial.replace(
                'left.twice(1)','left',1),
            "reserved alias":initial.replace(
                'import "left.sdr" as left','import "left.sdr" as int',1),
            "alias traversal":initial.replace(
                'import "left.sdr" as left','import "../left.sdr" as left',1),
            "alias invalid":initial.replace(
                'import "left.sdr" as left','import "left.sdr" as left.foo',1),
            "illegal generated name":initial.replace(
                'state total = 0','state __sdns_hidden = 0',1),
            "missing quoted path":initial.replace(
                'import "left.sdr" as left','import left.sdr as left',1),
        }
        for name,data in cases.items():
            assert data!=initial,name
            src.write_text(data,encoding="utf8")
            run([native,"check",src],ok=False)
        src.write_text(initial,encoding="utf8")

        mod=tmp/"faults.sdr"
        initial_mod=mod.read_text(encoding="utf8")
        tamper={
            "missing stable nominal id":initial_mod.replace(
                ' id "example.alias.ParseFault"','',1),
            "nested import in aliased file":'import "left.sdr"\n'+initial_mod,
            "module exports runtime state":initial_mod+'\nstate extra = 0\n',
            "shadowed function parameter":initial_mod.replace(
                'fn parse_positive(value: int)',
                'fn parse_positive(ParseFault: int)',1),
        }
        for name,data in tamper.items():
            assert data!=initial_mod,name
            mod.write_text(data,encoding="utf8")
            run([native,"check",src],ok=False)
        mod.write_text(initial_mod,encoding="utf8")

        # Nested flat modules cannot accidentally reuse a namespace owned
        # by a different file in the same compilation.
        (tmp/"wrapper.sdr").write_text(
            'import "left.sdr" as left\n',encoding="utf8")
        src.write_text(initial.replace(
            'import "left.sdr" as left','import "wrapper.sdr"'),encoding="utf8")
        run([native,"check",src],ok=False)
        src.write_text(initial,encoding="utf8")

        # Compiler-generated identifiers may not be forged by flat imports.
        (tmp/"forged.sdr").write_text(
            'fn __sdns_left_twice(n: int) -> int = 99\n',encoding="utf8")
        src.write_text(initial.replace(
            'import "right.sdr" as right','import "forged.sdr"'),encoding="utf8")
        run([native,"check",src],ok=False)
        src.write_text(initial,encoding="utf8")

        # No following of symlink imports.
        (tmp/"link.sdr").symlink_to(tmp/"left.sdr")
        src.write_text(initial.replace('import "left.sdr" as left',
                                       'import "link.sdr" as left'),encoding="utf8")
        run([native,"check",src],ok=False)

    print("PASS: two overlapping fn/record libraries, explicit-ID nominal errors")
    print("PASS: check/test/run/expand/Web/Android/Effects native, no Python runtime")
    print("PASS: flattened and namespace source give identical actions and state")
    print(f"PASS: {len(cases)+len(tamper)+3} malformed/traversal/symlink/collision negative cases")
    print("LIMIT: intentionally no nested aliases, namespace package resolver, or full source spans")

if __name__=="__main__":
    main()
