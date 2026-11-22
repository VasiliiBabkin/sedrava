#!/usr/bin/env python3
"""Golden + isolated web IR conformance checks."""
import argparse
import json
import subprocess
import shutil
import tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

def call(binary, *args, success=True):
    p = subprocess.run([str(binary), *map(str,args)], cwd=ROOT,
                       text=True, capture_output=True, timeout=30)
    assert (p.returncode == 0) == success, (args, p.stderr)
    return p

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--binary",type=Path,required=True)
    binary=ap.parse_args().binary.resolve()
    source=ROOT/"examples/counter.sdr"
    ir=json.loads(call(binary,"ir-candidate",source).stdout)
    expected=json.loads((ROOT/"tests/ir_candidate/counter.json").read_text())
    assert ir == expected, "golden IR regression"
    assert json.loads(call(binary,"ir-candidate",source).stdout) == ir
    guard=ROOT/"tests/ir_candidate/guard.sdr"
    guard_ir=json.loads(call(binary,"ir-candidate",guard).stdout)
    assert guard_ir == json.loads((ROOT/"tests/ir_candidate/guard.json").read_text())
    assert json.loads(call(binary,"ir-candidate",guard).stdout) == guard_ir
    try:
        import jsonschema
    except ImportError:
        print("SKIP optional jsonschema validation")
    else:
        schema=json.loads((ROOT/"schemas/ir/app-1.0-candidate.1.schema.json").read_text())
        validator=jsonschema.Draft202012Validator(schema)
        validator.check_schema(schema)
        validator.validate(ir)
        validator.validate(guard_ir)
        assert not validator.is_valid(dict(ir,version="wrong"))
        print("PASS JSON Schema")
    with tempfile.TemporaryDirectory(prefix="sdr-ir-") as tmp:
        dest=Path(tmp)/"index.html"
        call(binary,"build","web-ir",source,"--output",dest)
        html=dest.read_text()
        assert "function runAction(name)" in html
        assert '"coverage":"app-scalar-single-screen"' in html
        assert "eval(" not in html and "innerHTML" not in html
        guard_dest=Path(tmp)/"guard.html"
        call(binary,"build","web-ir",guard,"--output",guard_dest)
        guard_html=guard_dest.read_text()
        assert "<img src=x" not in guard_html
        assert "\\u003cimg" in guard_html
        bad=ROOT/"examples/task_manager_navigation.sdr"
        assert "E_IR_CANDIDATE_UNSUPPORTED" in call(binary,"ir-candidate",bad,success=False).stderr
        call(binary,"build","web-ir",bad,"--output",Path(tmp)/"bad.html",success=False)
        assert not (Path(tmp)/"bad.html").exists()
        if shutil.which("node"):
            subprocess.run(["node", str(ROOT/"scripts/verify_ir_web_node.cjs"), str(dest)], check=True)
        else:
            print("SKIP optional Node mock-DOM runtime")
    print("PASS IR candidate golden + web build + fail-closed")
if __name__=="__main__":
    main()

