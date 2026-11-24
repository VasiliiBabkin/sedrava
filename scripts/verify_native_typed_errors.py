"""Verify native Rust Core/Web typed errors against experimental Python 0.12 PR #56.

All sources and outputs live in a TemporaryDirectory; no Actions or production data.
The scope is closed/open nominal errors, scalar Result and action match. Not legacy
try_* adapters, imported error declarations or Android typed Result code generation.
"""
import argparse
import json
import os
import shutil
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
NATIVE=ROOT/"rust/target/debug/sedrava"
SOURCE=ROOT/"examples/native_typed_errors_a1/main.sdr"


def run(binary,*args,ok):
    command=[*map(str,binary),*map(str,args)]
    result=subprocess.run(
        command,capture_output=True,text=True,check=False,timeout=30,
        env={**os.environ,"PATH":"/nonexistent"}
    )
    assert (result.returncode==0)==ok,(command,result.returncode,result.stdout,result.stderr)
    return result


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--python-reference",type=Path)
    args=parser.parse_args()
    assert NATIVE.is_file() and SOURCE.is_file()
    py=([sys.executable,args.python_reference/"sedrava_cli.py"]
        if args.python_reference else None)
    if py:
        assert Path(py[1]).is_file()

    with tempfile.TemporaryDirectory(prefix="native-typed-a1-") as temporary:
        folder=Path(temporary)
        src=folder/"main.sdr"
        original=SOURCE.read_text(encoding="utf-8")
        src.write_text(original,encoding="utf-8")
        for binary in ([NATIVE],py) if py else ([NATIVE],):
            run(binary,"check",src,ok=True)
            run(binary,"test",src,ok=True)

        # Effects A1 must still identify typed user constructors as pure.
        manifest=run([NATIVE],"effects",src,"--target","web",ok=True).stdout.strip()
        assert json.loads(manifest)["schema"]=="sedrava.effects.v1"
        if py:
            reference=run(py,"effects",src,"--target","web",ok=True).stdout.strip()
            assert manifest==reference,(manifest,reference)

        # Deterministic full-state parity including ephemeral derived Result JSON.
        sequences=[(),("success",),("fail",),("fallback",),
                   ("success","fail"),("success","fail","fallback")]
        expected={}
        for actions in sequences:
            native=json.loads(run([NATIVE],"run",src,*actions,ok=True).stdout)
            if py:
                reference=json.loads(run(py,"run",src,*actions,ok=True).stdout)
                assert native==reference,(actions,native,reference)
            expected[actions]=native
        assert expected[()]["recent"]["error"]["id"]=="example.ArithmeticError.IntOverflow"
        assert expected[("success",)]["flag"] is True
        assert expected[("fail",)]["total"]==101
        assert expected[("fallback",)]["message"]=="example.ReadError.Denied"

        # Rejected engine overflow remains fatal, not catchable as an Err.
        for binary in ([NATIVE],py) if py else ([NATIVE],):
            run(binary,"run",src,"rollback",ok=False)

        # Compile-time reject corpus. Both engines must fail-closed.
        source=original
        cases={
            "open_missing_fallback":
                source.replace('''        Err(error):
            message = error_id(error)
action fallback:''','''action fallback:''',1),
            "wrong_result_success_type":
                source.replace('Ok(x) if x < 100','Ok("wrong") if x < 100',1),
            "wrong_result_error_type":
                source.replace('Err(ArithmeticError.IntOverflow(left=x, right=1))',
                    'Err(ReadError.NotFound(path="x"))',1),
            "duplicate_payload":
                source.replace('left=x, right=1','left=x, left=x, right=1',1),
            "missing_payload":
                source.replace('left=x, right=1','left=x',1),
            "wrong_payload_type":
                source.replace('left=x, right=1','left="x", right=1',1),
            "missing_variant":
                source.replace('ArithmeticError.IntOverflow','ArithmeticError.Unknown',1),
            "missing_error_family":
                source.replace('ArithmeticError.IntOverflow','MissingError.IntOverflow',1),
            "missing_closed_arm":
                source.replace('''        Err(InvalidScalar { scalar }):
            total = scalar
    match ready''','''    match ready''',1),
            "unreachable_fallback":
                source.replace('''        Err(InvalidScalar { scalar }):
            total = scalar
    match ready''','''        Err(InvalidScalar { scalar }):
            total = scalar
        Err(error):
            total = 0
    match ready''',1),
            "duplicate_ok":
                source.replace('''        Ok(value):
            total = value
        Err(IntOverflow''','''        Ok(value):
            total = value
        Ok(other):
            total = other
        Err(IntOverflow''',1),
            "wrong_match_target":
                source.replace('match checked(4):','match total:',1),
            "unknown_arm_field":
                source.replace('Err(IntOverflow { left, right }):',
                    'Err(IntOverflow { missing, right }):',1),
            "bare_variant_fallback":
                source.replace('Err(IntOverflow { left, right }):','Err(IntOverflow):',1),
            "binder_leaks":
                source.replace('''action fail:
    match checked(100):''','''action fail:
    total = left
    match checked(100):''',1),
            "immutable_binder_assignment":
                source.replace('''        Ok(value):
            total = value''','''        Ok(value):
            value = 999
            total = value''',1),
            "duplicate_nominal_id":
                source.replace('id "example.ReadError"','id "example.ArithmeticError"',1),
            "reserved_error_family":
                source.replace('error closed ArithmeticError','error closed Error',1),
            "unknown_error_field_type":
                source.replace('        left: int','        left: float',1),
            "duplicate_variant":
                source.replace('''    InvalidScalar:
        scalar: int''','''    InvalidScalar:
        scalar: int
    InvalidScalar:
        scalar: int''',1),
            "duplicate_error_field":
                source.replace('''        left: int
        right: int''','''        left: int
        left: int
        right: int''',1),
            "unbounded_nested_result":
                source.replace('Result<int, ArithmeticError>',
                    'Result<Result<int, ArithmeticError>, ArithmeticError>',1),
        }
        for name,altered in cases.items():
            assert altered != source,name
            src.write_text(altered,encoding="utf-8")
            run([NATIVE],"check",src,ok=False)
            if py:
                run(py,"check",src,ok=False)
        src.write_text(source,encoding="utf-8")

        # Browser/Web app test: Node mock DOM mirrors full Python/Rust state
        # after each action. Real browser compatibility is a separate gate.
        web=folder/"index.html"
        run([NATIVE],"build","web",src,"--output",web,ok=True)
        node=shutil.which("node")
        assert node, "Node.js is required for JS mock DOM conformance"
        lines=run([node],ROOT/"scripts/verify_native_typed_errors_node.js",
                  web,ok=True).stdout.splitlines()
        actual={}
        for line in lines:
            if line.startswith("RESULT_STATE "):
                _,name,raw=line.split(" ",2)
                actual[name]=json.loads(raw)
        assert actual["initial"]==expected[()]
        assert actual["success"]==expected[("success",)]
        assert actual["success_fail"]==expected[("success","fail")]
        assert actual["success_fail_fallback"]==expected[("success","fail","fallback")]
        assert actual["rollback_rejected"]==actual["success_fail_fallback"]

        # HTML/script literal must remain data and cannot close a generated script.
        hostile='</script><img src=x onerror=alert(1)>'
        src.write_text(source.replace('missing("/foo")',
                      'missing("'+hostile+'")'),encoding="utf-8")
        adversarial=folder/"hostile.html"
        run([NATIVE],"build","web",src,"--output",adversarial,ok=True)
        html=adversarial.read_text(encoding="utf-8")
        assert html.count("</script>")==1, "Unescaped author text broke the script"
        assert hostile not in html, "Raw untrusted markup inserted into HTML"
        src.write_text(source,encoding="utf-8")

        # Flat imports can carry nominal user errors, but require an explicit
        # stable ID instead of implicitly assigning the entry app identity.
        imported=ROOT/"examples/native_typed_errors_modules/main.sdr"
        for compiler in ([NATIVE],):
            run(compiler,"check",imported,ok=True)
            run(compiler,"test",imported,ok=True)
        imported_out=folder/"imported-android"
        run([NATIVE],"build","android",imported,"--output",imported_out,
            "--application-id","org.sedrava.importedresult",ok=True)
        imported_program=(imported_out/
            "app/src/main/java/org/sedrava/importedresult/Program.kt")
        assert "example.parse.ParseFault" in imported_program.read_text(encoding="utf8")
        (folder/"errors.sdr").write_text(
            'error closed ErrorWithoutStableId:\n    Invalid:\n',encoding="utf8")
        (folder/"bad-import.sdr").write_text(
            'app "Negative"\nimport "errors.sdr"\nstate count = 0\n',encoding="utf8")
        run([NATIVE],"check",folder/"bad-import.sdr",ok=False)

        # Native Kotlin codegen now supports typed Result and action match.
        # Full Android compilation and execution are covered separately.
        output=folder/"android"
        run([NATIVE],"build","android",src,"--output",output,
            "--application-id","org.sedrava.typederrors",ok=True)
        kotlin=output/"app/src/main/java/org/sedrava/typederrors/Program.kt"
        assert kotlin.is_file()
        raw=kotlin.read_text(encoding="utf-8")
        for token in ("SdrResult.Success","SdrResult.Failure",
                      "nominalError(","match_","SdrType.Result("):
            assert token in raw,token

    print("PASS: native Core typed-error Result/match + Web Node execution")
    print("PASS: 6 accepted action sequences and 22 negative source cases")
    print("PASS: overload/field/variant/exhaustiveness and overflow rejection")
    if py:
        print("PASS: same acceptance/full state vs Python 0.12 PR #56")
    print("PASS: Android typed Result/match Kotlin generation (compiled JVM separately)")
    print("PASS: flat nominal-error imports require explicit IDs and compile to Android")
    print("LIMIT: legacy try_* and namespace aliases remain separate work")


if __name__=="__main__":
    main()
