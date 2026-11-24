#!/usr/bin/env python3
"""Independent bounded A4 layout/AST smoke, native Sedrava actions own parsing.

Python oracle computes expected tokens and AST structures only for testing.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import random
import re
import subprocess
import tempfile

from verify_selfhost_lexer_a3 import expect_tokens as a3_tokens

ROOT=Path(__file__).resolve().parents[1]
PROGRAM=ROOT/"examples/self_host/parser_a4.sdr"
BIN=Path(os.environ.get("SEDRAVA_NATIVE_BIN",ROOT/"rust/target/debug/sedrava"))
SOURCE_PREFIX='state source = "sum==42 # comment"'


def execute(source:str,dir:Path,*actions:str):
    template=PROGRAM.read_text()
    assert template.count(SOURCE_PREFIX)==1
    f=dir/"case.sdr"
    f.write_text(template.replace(SOURCE_PREFIX,"state source = "+json.dumps(source,ensure_ascii=False)))
    return subprocess.run([str(BIN),"run",str(f),*actions],capture_output=True,
        text=True,encoding="utf-8",timeout=25,
        env={"PATH":"/nonexistent","LC_ALL":"C"})


def layout_oracle(source:str):
    if len(source)>256:
        raise ValueError("length")
    output=[]
    level=0
    offset=0
    line_number=1
    for raw in source.split("\n"):
        # A4's layout subset rejects TAB, CR or double quotes in code;
        # comments can have quotes/tabs but never CR.
        before_comment=raw.split("#",1)[0]
        if "\r" in raw:
            raise ValueError("CR unsupported")
        if "\t" in before_comment or '"' in before_comment:
            raise ValueError("string or TAB in layout unsupported")
        stripped=before_comment.lstrip(" ")
        if stripped:
            spaces=len(before_comment)-len(stripped)
            if spaces>32 or spaces%4:
                raise ValueError("indentation must use 4 spaces")
            want=spaces//4
            point=offset+spaces
            while level<want:
                level+=1
                output.append({"kind":"INDENT","offset":point,
                               "line":line_number,"column":spaces+1,"level":level})
            while level>want:
                level-=1
                output.append({"kind":"DEDENT","offset":point,
                               "line":line_number,"column":spaces+1,"level":level})
            # A4 emits NEWLINE after every line with actual code, including
            # EOF if no trailing physical newline.
            output.append({"kind":"NEWLINE","offset":offset+len(raw),
                           "line":line_number,"column":len(raw)+1,"level":level})
        offset+=len(raw)+1
        line_number+=1
    offset=len(source)
    final_line=source.count("\n")+1
    final_col=offset-source.rfind("\n")
    while level>0:
        level-=1
        output.append({"kind":"DEDENT","offset":offset,
                       "line":final_line,"column":final_col,"level":level})
    if len(output)>100:
        raise ValueError("layout tokens limit")
    return output


def assert_run_actions(source:str,dir:Path,actions:tuple[str,...]):
    return execute(source,dir,*actions)


def main():
    assert BIN.is_file(),BIN
    accepted=[
        "", "root=1", "root=1\n", "a=1\n    b=2", "a=1\n    b=2\n",
        "a=1\n    b=2\n        c=3\n    d=4\ne=5",
        "# only comment", "# comment\n", "\n  # indented blank comment\n\n",
        "a=1 # comment\n    # another comment\n    b=2\n",
        "\n\n\nx=0", "x=0\n\n\n    y=1", "    a=1", "        a=1\n    b=2\nc=3",
        "a=1\n    b=2\n        c=3\n            d=4\n        e=5\nf=6",
        "a=1\n#comment\n    b=2\n#ignored\nc=3", "a=1\n    b=2 # trailing\n\n    c=3",
        " " * 32 + "x=0", "      # comment only\n",
        "ключ=значение\n    а=2", "    🐱 = 🍀\n    x=1",
    ]
    rejected=[
        "\ta=1", "a=1\n  b=2", "a=1\n     b=2", "a=1\n \tb=2",
        'a="str"', "a=1\r\nb=2", "x"*257, " " * 36+"x=3",
        "a=1\n     # blank comment\n   b=2",
        " " * 33+"x=1",
    ]
    rng=random.Random(14720)
    for i in range(85):
        pieces=[]
        for j in range(rng.randint(1,8)):
            if rng.random()<.22:
                pieces.append(" " * rng.randrange(0,16)+"# ignore "+str(j))
            elif rng.random()<.14:
                pieces.append(" "*rng.randrange(0,12))
            else:
                pieces.append(" "*(4*rng.randrange(0,5))+f"k{j}={rng.randrange(1,10)}")
        source="\n".join(pieces)
        try:layout_oracle(source)
        except ValueError:rejected.append(source)
        else:accepted.append(source)
    binary_ok=[
        "a=2+3", "b=7*10", "z=42-1", "n=100/2",
        "v = 2 + 3", "x=007+42", "long_name=3+5*7",
        "a=2+3*4", "b=8-6/3", "z=1+2*7", "c=3-4*9",
        "a=2 + 03 / 4"
    ]
    binary_bad=[
        "1=2+3", "a==2+3", "x=y+2", "x=1+2+3",
        "x=1*2+3", "x=1/2-3", 'a="x"+2', "a=1",
        "a=1+", "a=1+2*3+4", "a=1?2", "x=1+2/3*4",
        "a=1++2", "a = 2.5+3", "z=1+2==3",
    ]
    with tempfile.TemporaryDirectory(prefix="sedrava-a4-") as temp:
        t=Path(temp)
        for i,source in enumerate(accepted):
            expected=layout_oracle(source)
            r=execute(source,t,"scan_layout")
            assert r.returncode==0,(i,repr(source),r.stderr,r.stdout)
            data=json.loads(r.stdout)
            actual=[{k:item[k] for k in ("kind","offset","line","column","level")}
                    for item in data["layout_tokens"]["items"]]
            assert actual==expected,(i,repr(source),actual,expected)
            assert data["layout_level"]==0
            assert data["layout_cursor"]==len(source)
            assert json.loads(execute(source,t,"scan_layout").stdout)==data
        for i,source in enumerate(rejected):
            try:layout_oracle(source)
            except ValueError:pass
            else: raise AssertionError(f"Rejected corpus accepted by oracle: {source!r}")
            r=execute(source,t,"scan_layout")
            assert r.returncode!=0,(i,repr(source),r.stdout,r.stderr)
        for source in binary_ok:
            toks=a3_tokens(source)
            assert len(toks) in (5,7),(source,toks)
            r=execute(source,t,"scan","parse_binary")
            assert r.returncode==0,(repr(source),r.stdout,r.stderr)
            data=json.loads(r.stdout)
            exprs=data["expressions"]["items"]
            assignment=data["expression_assignments"]["items"]
            assert len(assignment)==1
            assert len(exprs)==(3 if len(toks)==5 else 5)
            assert [x["id"] for x in exprs]==list(range(1,len(exprs)+1))
            assert assignment[0]["name"]==toks[0]["lexeme"]
            assert assignment[0]["start"]==toks[0]["offset"]
            assert assignment[0]["end"]==toks[-1]["end"]
            assert assignment[0]["expression_id"]==len(exprs)
            root=exprs[-1]
            assert root["left_id"]==1
            assert root["operator"]==toks[3]["lexeme"]
            assert root["end"]==toks[-1]["end"]
            if len(toks)==7:
                assert root["right_id"]==4
                assert exprs[3]["operator"]==toks[5]["lexeme"]
                assert (exprs[3]["left_id"],exprs[3]["right_id"])==(2,3)
            else:
                assert root["right_id"]==2
            assert json.loads(execute(source,t,"scan","parse_binary").stdout)==data
        for source in binary_bad:
            r=execute(source,t,"scan","parse_binary")
            assert r.returncode!=0,(source,r.stdout,r.stderr)
    print(f"PASS A4 source layout tokens: {len(accepted)} accepted / {len(rejected)} rejected")
    print(f"PASS A4 small arithmetic assignment AST: {len(binary_ok)} accepted / {len(binary_bad)} rejected")
    print("PASS 4-space indentation <=8 levels, NEWLINE/INDENT/DEDENT, comments, blanks, EOF dedent")
    print("PASS two-operand binary and fixed three-operand * / precedence subset with stable IDs")
    print("LIMIT: separate layout action, not full compiler lexer, no general precedence parser")


if __name__=="__main__":
    main()
