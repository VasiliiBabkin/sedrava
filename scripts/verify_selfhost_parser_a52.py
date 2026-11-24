#!/usr/bin/env python3
"""A5.2 independently checked Sedrava-authored narrow program AST.

The actual parser, lexer, layout scanner and merge are Sedrava actions
executed through native Rust. Python only constructs oracle expectations.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import random
import re
import subprocess
import tempfile

from verify_selfhost_parser_a51 import oracle as unified_oracle

ROOT=Path(__file__).resolve().parents[1]
PROGRAM=ROOT/"examples/self_host/parser_a52.sdr"
BIN=Path(os.environ.get("SEDRAVA_NATIVE_BIN",ROOT/"rust/target/debug/sedrava-native"))
PREFIX='state source = "sum==42 # comment"'
ACTIONS=("scan","scan_layout","merge_tokens","parse_program")
EXPR=re.compile(r"^([ ]*)([A-Za-z_][A-Za-z_0-9]*) *=( *)?([0-9]+) *(?:#.*)?$")

def expected_ast(source:str):
    if len(source)>256:raise ValueError("256 scalar budget")
    unified=unified_oracle(source)
    if len(unified)>100:raise ValueError("100 tokens limit")
    result=[]
    offset=0
    for i,line in enumerate(source.splitlines(keepends=True),1):
        original=line.rstrip("\n")
        stripped=original.lstrip(" ")
        if not stripped or stripped.startswith("#"):
            offset+=len(line)
            continue
        if "\t" in original or "\r" in original:raise ValueError("no tab/cr")
        match=EXPR.fullmatch(original)
        if match is None:raise ValueError("not narrow assignment grammar")
        space,name,spacing,literal=match.group(1,2,3,4)
        if len(space)%4 or len(space)>32:raise ValueError("indent is multiple of 4 up to 32")
        depth=len(space)//4
        if not result and depth>0:raise ValueError("cannot indent before first statement")
        start=offset+len(space)
        number_start=original.index(literal,original.index("=")+1)
        end=offset+number_start+len(literal)
        result.append(dict(name=name,literal=literal,depth=depth,line=i,start=start,end=end))
        offset+=len(line)
    if not result or len(result)>32:raise ValueError("1..32 statements")
    return result,unified

def run(source:str,folder:Path,actions=ACTIONS):
    source_path=folder/"case.sdr"
    template=PROGRAM.read_text(encoding="utf-8")
    assert template.count(PREFIX)==1
    source_path.write_text(template.replace(PREFIX,
        "state source = "+json.dumps(source,ensure_ascii=False)),encoding="utf-8")
    return subprocess.run([str(BIN),"run",str(source_path),*actions],
        capture_output=True,text=True,timeout=30,
        env={"PATH":"/nonexistent","LC_ALL":"C"})

def main():
    positives=[
        "a=1","a = 234","x=0\n","first=1\nsecond=22",
        "a=1\n    b=2\nc=3",
        "a=1\n        b=2\n    c=3\nd=4",
        "a=1\n    b=2\n        c=3\n    d=4\ne=5",
        "a=1 # inline\nb=2",
        "# пометка\nx=21",
        "x=1\n\n    # комментарий\n    y=2\n\nz=3",
        "a=1\n    b=2 # ñ🍀\n    c=3\n# end",
        "top=1\n    k1 = 22\n    k2=3\nend=7",
    ]
    negatives=[
        "", "  # only comment", "a", "a=", "a==1", "a=1+2",
        "a=1 x=2","a=1\nb", " a=1", "    a=1",
        "a=1\n  b=2", "a=1\n\tb=2",
        "a=1\n b=2", "a=1\n    b=\"text\"",
        "a=1\n    b=2\n c=3",
        "a=1\n    b=2+3",
        "a=1\n    b=2\n    c:3",
        "a=1\n    b=2\n    3=4",
        "a=1\n    b=2\n    c=3*4",
        "а=1", "a=1\n      b=2",
        "a"*257+"=1",
    ]
    rng=random.Random(0xA52)
    for _ in range(18):
        count=rng.randint(1,6)
        depth=0
        lines=[]
        for i in range(count):
            if i:
                depth=rng.randrange(0,5)
                if rng.random()<.16:
                    lines.append("    # пропуск строки")
            name=f"v{i}"
            literal=str(rng.randrange(0,1_000_000))
            if rng.random()<.27:
                lines.append(" "* (depth*4) +f"{name} = {literal} # ok")
            else:
                lines.append(" "* (depth*4) +f"{name}={literal}")
            if rng.random()<.20:lines.append("")
        candidate="\n".join(lines)
        try:expected_ast(candidate)
        except ValueError:negatives.append(candidate)
        else:positives.append(candidate)
    with tempfile.TemporaryDirectory(prefix="sedrava-a52-parser-") as temp:
        work=Path(temp)
        for idx,source in enumerate(positives):
            ast,expected_tokens=expected_ast(source)
            finished=run(source,work)
            assert finished.returncode==0,(idx,source,finished.stderr,finished.stdout[:500])
            state=json.loads(finished.stdout)
            actual=[{k:node[k] for k in ("name","literal","depth","line","start","end")}
                    for node in state["program_assignments"]["items"]]
            assert actual==ast,(idx,repr(source),actual,ast)
            assert [x["id"] for x in state["program_assignments"]["items"]]==list(range(1,len(ast)+1))
            actual_tokens=[{k:t[k] for k in ("kind","lexeme","offset","end","line","column","level")}
                           for t in state["unified_tokens"]["items"]]
            assert actual_tokens==expected_tokens,(idx,repr(source),"mismatched token stream")
            assert state["parse_depth"]==0
            assert state["parse_cursor"]==len(actual_tokens)+1
            if idx in (0,2,10):
                assert run(source,work).stdout==finished.stdout,(idx,"non-deterministic AST")
        for idx,source in enumerate(negatives):
            try: expected_ast(source)
            except ValueError: pass
            else: raise AssertionError(("bad rejected fixture",idx,repr(source)))
            result=run(source,work)
            assert result.returncode!=0,(idx,repr(source),result.stdout,result.stderr)
        incomplete=run("a=1",work,("parse_program",))
        assert incomplete.returncode!=0
        duplicate=run("a=1",work,ACTIONS+("parse_program",))
        assert duplicate.returncode!=0
    print(f"PASS A5.2: {len(positives)} valid and {len(negatives)} rejected programs")
    print("PASS A5.2: independent AST/spans/depth/line oracle and A5.1 unified token parity")
    print("PASS A5.2: pre-merge / double parse rejected, fresh IDs and deterministic output")
    print("LIMIT: narrow assignment+indent grammar only, not a self-hosted compiler")

if __name__=="__main__":main()
