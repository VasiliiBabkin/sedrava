#!/usr/bin/env python3
"""A3 span + first AST node: independent token oracle, real Sedrava execution.

Tokenization is executed by the Sedrava-authored lexer_a3.sdr. Python only
checks results against the prior independently implemented A2 lexical oracle
plus independently derived positions and a deliberately tiny AST grammar.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import random
import subprocess
import tempfile
from verify_selfhost_lexer_a2 import oracle as a2_oracle

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/"examples/self_host/lexer_a3.sdr"
BIN=Path(os.environ.get("SEDRAVA_NATIVE_BIN",ROOT/"rust/target/debug/sedrava-native"))
PREFIX='state source = "sum==42 # comment"'
OPS=set("+-*/=<>!")


def expect_tokens(source:str)->list[dict]:
    tokens=[]
    for tok in a2_oracle(source):
        start=tok["offset"]
        lexeme=tok["lexeme"]
        assert source[start:start+len(lexeme)]==lexeme
        last_newline=source.rfind("\n",0,start)
        tokens.append({
            "kind":"operator" if tok["kind"]=="punct" and lexeme[0] in OPS else tok["kind"],
            "lexeme":lexeme,
            "offset":start,"end":start+len(lexeme),
            "line":source.count("\n",0,start)+1,
            "column":start-last_newline,
        })
    return tokens


def execute(source:str,tmp:Path,*actions:str):
    base=SOURCE.read_text(encoding="utf-8")
    assert base.count(PREFIX)==1
    path=tmp/"case.sdr"
    path.write_text(base.replace(PREFIX,"state source = "+json.dumps(source,ensure_ascii=False)),encoding="utf-8")
    return subprocess.run([str(BIN),"run",str(path),*actions],
        capture_output=True,text=True,encoding="utf-8",timeout=25,
        env={"PATH":"/nonexistent","LC_ALL":"C"})


def main():
    assert BIN.is_file(),BIN
    accepted=[
        "", "a", "a=12", "count = 005", "a==2", "x>=10", "foo->bar",
        's="Привет"', 'face="🐱🦊"', 'a="one\\n two"', 'a="slash \\\\ and quote \\""',
        "# only comment", "x=1# comment", "x=1 #comment\n  b=2",
        "\n \n a=12", "x<=1\n  y>=2", "\t  alpha = 42", "a=\"hello\"\n",
        's="multi\nline"', 's="a#literal"\n# comment',
        "\r\nx=1", "0", "a=0", "(x+2)"," " * 40,
        ". " * 45, "x=42 # last \n", "a=\t1", "x=7\nz!=8",
    ]
    rejected=[
        "12x", "x?y", "А=1", "😀", 'a="unterminated',
        'a="\\q"', 'a="backslash\\', "a" * 257, " " * 257,
        ". " * 110, "a@b", "x$y",
    ]
    rnd=random.Random(12013)
    symbols=["a","b","some_12","1","37"," ","\t","\n","(","==","!=",">=",
             "<=","->",'"текст"','"🐱"',":","=","#foo\n"]
    for i in range(90):
        sample="".join(rnd.choices(symbols,k=rnd.randint(0,12)))
        try:expect_tokens(sample)
        except ValueError:rejected.append(sample)
        else:accepted.append(sample)
    parse_ok=[
        "a=12","count = 005"," \n foo=42","x\t=\n7",
        "id=0# one comment", "# comment\nvalue=214",
    ]
    parse_fail=[
        "1=2","a==12","x=y","x=1+2","a",
        'name="string"',"a=2 b=3","a>=10","a=5,3",
    ]
    with tempfile.TemporaryDirectory(prefix="sedrava-a3-spans-") as directory:
        tmp=Path(directory)
        for i,sample in enumerate(accepted):
            expected=expect_tokens(sample)
            r=execute(sample,tmp,"scan")
            assert r.returncode==0,(i,repr(sample),r.stdout,r.stderr)
            result=json.loads(r.stdout)
            found=[{k:x[k] for k in ("kind","lexeme","offset","end","line","column")}
                   for x in result["tokens"]["items"]]
            assert found==expected,(i,repr(sample),found,expected)
            assert result["cursor"]==len(sample),i
            assert result["line"]==1+sample.count("\n"),i
            last=sample.rfind("\n")
            assert result["column"]==len(sample)-last,i
            assert json.loads(execute(sample,tmp,"scan").stdout)==result,i
        for i,sample in enumerate(rejected):
            try:expect_tokens(sample)
            except ValueError:pass
            else:raise AssertionError(f"Invalid oracle fixture accepted: {sample!r}")
            r=execute(sample,tmp,"scan")
            assert r.returncode!=0,(i,repr(sample),r.stdout,r.stderr)
        for sample in parse_ok:
            expected=expect_tokens(sample)
            assert len(expected)==3
            r=execute(sample,tmp,"scan","parse_assignment")
            assert r.returncode==0,(sample,r.stdout,r.stderr)
            state=json.loads(r.stdout)
            ast=state["assignments"]["items"]
            assert len(ast)==1,(sample,ast)
            assert {k:ast[0][k] for k in ("name","literal","start","end")}=={
                "name":expected[0]["lexeme"],"literal":expected[2]["lexeme"],
                "start":expected[0]["offset"],"end":expected[2]["end"]
            },(sample,ast)
        for sample in parse_fail:
            r=execute(sample,tmp,"scan","parse_assignment")
            assert r.returncode!=0,(repr(sample),r.stdout,r.stderr)
    print(f"PASS A3 scanner: {len(accepted)} accepted, {len(rejected)} rejected")
    print(f"PASS A3 tiny assignment AST: {len(parse_ok)} accepted, {len(parse_fail)} rejected")
    print("PASS exact Unicode-scalar start/end offsets and line/column including newlines")
    print("PASS stable-record ID lookup, token-kind distinctions, repeatability, full-action rejection")
    print("LIMITS: one fresh scan, IDs 1..3, no general parser or stable compiler equivalence")


if __name__=="__main__":
    main()
