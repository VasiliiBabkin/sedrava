#!/usr/bin/env python3
"""Stage-0 self-hosting lexical experiment; Sedrava implements scanner logic.

Python is exclusively a golden-corpus oracle and subprocess test runner.
It never tokenizes on behalf of the .sdr program.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
TEMPLATE=ROOT/"examples/self_host/lexer_a0.sdr"
BIN=Path(os.environ.get("SEDRAVA_NATIVE_BIN",str(ROOT/"rust/target/debug/sedrava-native")))
PREFIX='state source = "sum=42 (next)"'
LETTERS="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_"
DIGITS="0123456789"
PUNCT="()=+,-"


def oracle(source: str):
    output=[]
    fragment=""
    kind=""
    start=0
    def flush():
        nonlocal fragment,kind
        if fragment:
            output.append({"kind":kind,"lexeme":fragment,"offset":start})
            fragment=""
            kind=""
    for cursor,ch in enumerate(source):
        if ch==" ":
            flush()
        elif ch in PUNCT:
            flush()
            output.append({"kind":"punct","lexeme":ch,"offset":cursor})
        elif ch in LETTERS or ch in DIGITS:
            if not fragment:
                start=cursor
                kind="integer" if ch in DIGITS else "identifier"
            elif kind=="integer" and ch not in DIGITS:
                raise ValueError("letters after digits unsupported in A0")
            fragment+=ch
        else:
            raise ValueError("unsupported character in A0")
    flush()
    return output


def run(source: str, tmp: Path):
    content=TEMPLATE.read_text(encoding="utf-8")
    assert content.count(PREFIX)==1
    content=content.replace(PREFIX,"state source = "+json.dumps(source,ensure_ascii=False))
    path=tmp/"case.sdr"
    path.write_text(content,encoding="utf-8")
    actions=["step"]*len(source)+["finish"]
    return subprocess.run(
        [str(BIN),"run",str(path),*actions],
        text=True,capture_output=True,timeout=25,
        env={"PATH":"/nonexistent","LC_ALL":"C"},
    )


def main():
    assert BIN.is_file(), BIN
    accepted=[
        "", "a", "42", "x=42", "sum=42 (next)", "x+y",
        "A12_2 = 045", "_x,2", "(x) - y", "001",
        "a a", "x+y,z=3", "hello123 (code_77)",
    ]
    rejected=["12a","x?y","А=1","😀","a\tx", "abc#def", "7_", "x/y"]
    with tempfile.TemporaryDirectory(prefix="sedrava-lexer-a0-") as folder:
        tmp=Path(folder)
        for source in accepted:
            expected=oracle(source)
            result=run(source,tmp)
            assert result.returncode==0,(source,result.stdout,result.stderr)
            state=json.loads(result.stdout)
            actual=[
                {field:item[field] for field in ("kind","lexeme","offset")}
                for item in state["tokens"]["items"]
            ]
            assert actual==expected,(source,actual,expected)
            assert state["cursor"]==len(source)
            assert state["fragment"]==""
            assert json.loads(run(source,tmp).stdout)==state,source
        for source in rejected:
            try:
                oracle(source)
            except ValueError:
                pass
            else:raise AssertionError("oracle unexpectedly accepted "+repr(source))
            result=run(source,tmp)
            assert result.returncode!=0,(source,result.stdout,result.stderr)
        # Empty or invalid input never grants hidden Python tokenization.
        # Rust runs a genuine Sedrava program one step per Unicode scalar.
    print(f"PASS Sedrava A0 lexical golden corpus: {len(accepted)} accepted, {len(rejected)} rejected")
    print("PASS exact token kinds/lexemes/offsets and deterministic repeated Rust CLI execution")
    print("PASS logic lives in .sdr action; Python only checks the result; no public ports")


if __name__=="__main__":
    main()
