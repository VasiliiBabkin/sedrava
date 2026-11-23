#!/usr/bin/env python3
"""A5.1 merge lexer and layout token streams entirely in Sedrava source.

Independent Python oracles ONLY check outcomes; the actual merge runs
in the Sedrava native interpreter via action sequence scan/scan_layout/
merge_tokens on a fresh source each time.
"""
from __future__ import annotations
import json,os,random,subprocess,tempfile
from pathlib import Path
from verify_selfhost_lexer_a3 import expect_tokens
from verify_selfhost_parser_a4 import layout_oracle

ROOT=Path(__file__).resolve().parents[1]
PROGRAM=ROOT/"examples/self_host/parser_a51.sdr"
BIN=Path(os.environ.get("SEDRAVA_NATIVE_BIN",ROOT/"rust/target/debug/sedrava-native"))
PREFIX='state source = "sum==42 # comment"'

def oracle(source:str):
    lexical=[{**item,"level":0} for item in expect_tokens(source)]
    layout=[
        {"kind":item["kind"],"lexeme":"","offset":item["offset"],
         "end":item["offset"],"line":item["line"],"column":item["column"],
         "level":item["level"]}
        for item in layout_oracle(source)
    ]
    combined=[(item["offset"],1,i,item) for i,item in enumerate(lexical)]
    combined.extend((item["offset"],0,i,item) for i,item in enumerate(layout))
    combined.sort(key=lambda x:x[:3])
    if len(combined)>100:raise ValueError("A5.1 token budget 100")
    return [entry[3] for entry in combined]

def run(source:str,work:Path,actions:tuple[str,...]):
    template=PROGRAM.read_text("utf-8")
    assert template.count(PREFIX)==1
    app=work/"a51-case.sdr"
    app.write_text(template.replace(PREFIX,"state source = "+json.dumps(source,ensure_ascii=False)),encoding="utf-8")
    return subprocess.run([str(BIN),"run",str(app),*actions],capture_output=True,text=True,
                          encoding="utf-8",timeout=30,env={"PATH":"/nonexistent","LC_ALL":"C"})

def main():
    assert BIN.is_file(),BIN
    accepted=[
        "a=1", "a=1\n", "a=1\n    b=2", "a=1\n    b=2\nc=3",
        "top=0\n    left=1\n        nested=2\n    right=3\nend=4",
        "\n\nstart=1\n    inside=2\n\nend=3",
        "# only comment", "# only comment\n\n", "a=1 # trailing",
        "a=1\n    # ignored\n    b=2\n    # also ignored\nc=3",
        "a=1\n    b=2\n        c=3", "  # comment\nx==42", "x<=5",
        "x=1\n    y=2\n        z=3\n    c=4\nend=5",
        "a=2+3*4", "(a=1)", "   # comment\nx=1",
        " \n", "\n\n", "", " " * 22,
    ]
    rejected=[
        "a=1\n  b=2", "a=1\n     b=2", "a=1\n\tb=2",
        'a="text"', "a=1\r\nx=2", "а=1", "x?y",
        "a=1\n       b=2", " " * 33+"z=2",
        "a"*257,
    ]
    rng=random.Random(0xA51)
    for _ in range(70):
        lines=[]
        for j in range(rng.randint(1,6)):
            depth=rng.randrange(0,5)
            if rng.random()<.2:
                lines.append(" "*(depth*4)+"# comment")
            else:
                lines.append(" "*(depth*4)+f"k{j}={rng.randrange(1,10)}")
        candidate="\n".join(lines)
        try:oracle(candidate)
        except ValueError:rejected.append(candidate)
        else:accepted.append(candidate)
    with tempfile.TemporaryDirectory(prefix="sedrava-a51-merge-") as folder:
        work=Path(folder)
        for idx,source in enumerate(accepted):
            expected=oracle(source)
            executed=run(source,work,("scan","scan_layout","merge_tokens"))
            assert executed.returncode==0,(idx,repr(source),executed.stdout,executed.stderr)
            state=json.loads(executed.stdout)
            actual=[{k:t[k] for k in ("kind","lexeme","offset","end","line","column","level")}
                    for t in state["unified_tokens"]["items"]]
            assert actual==expected,(idx,repr(source),actual,expected)
            assert [item["id"] for item in state["unified_tokens"]["items"]]==list(range(1,len(actual)+1))
            assert state["merge_i"]==len(state["tokens"]["items"])+1
            assert state["merge_j"]==len(state["layout_tokens"]["items"])+1
            assert json.loads(run(source,work,("scan","scan_layout","merge_tokens")).stdout)==state
        for idx,source in enumerate(rejected):
            try:oracle(source)
            except ValueError:pass
            else:raise AssertionError(f"Wrong negative fixture: {source!r}")
            executed=run(source,work,("scan","scan_layout","merge_tokens"))
            assert executed.returncode!=0,(idx,repr(source),executed.stdout,executed.stderr)
        incomplete=run("a=1",work,("merge_tokens",))
        assert incomplete.returncode!=0,"Merge must require both scans"
    print(f"PASS Sedrava A5.1: {len(accepted)} accepted and {len(rejected)} rejected multi-line sources")
    print("PASS ordered unified source spans, operator kinds, NEWLINE/INDENT/DEDENT, stable IDs")
    print("PASS independent oracle and deterministic fresh execution; refuse skipped scans")
    print("LIMIT: three actions, strict subset only, <=100 tokens, no general AST parser")
if __name__=="__main__":
    main()
