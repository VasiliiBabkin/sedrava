#!/usr/bin/env python3
"""Independent corpus for the *Sedrava-written* A2 bounded lexer.

The Python oracle runs outside the Sedrava process; it does not parse for
the application. Every accepted sample invokes exactly one native scan.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import random
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/"examples/self_host/lexer_a2.sdr"
BIN=Path(os.environ.get("SEDRAVA_NATIVE_BIN",ROOT/"rust/target/debug/sedrava"))
PREFIX='state source = "sum==42 # comment"'
LETTERS="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_"
DIGITS="0123456789"
PUNCT="(){}[],:.+-*/=<>!"
COMPOUND={"==","!=","<=",">=","->"}
ESCAPES=set('ntr"\\')


def oracle(source:str)->list[dict]:
    if len(source)>256:
        raise ValueError("source budget")
    out=[]
    position=0
    def token(kind, lexeme, offset):
        out.append({"kind":kind,"lexeme":lexeme,"offset":offset})
        if len(out)>100:
            raise ValueError("token budget")
    while position<len(source):
        ch=source[position]
        if ch in (" ", "\t", "\r", "\n"):
            position+=1;continue
        if ch=="#":
            newline=source.find("\n",position)
            position=len(source) if newline<0 else newline+1
            continue
        if ch=='"':
            start=position
            position+=1
            while True:
                if position>=len(source):
                    raise ValueError("unterminated string")
                next_char=source[position]
                if next_char=="\\":
                    position+=1
                    if position>=len(source) or source[position] not in ESCAPES:
                        raise ValueError("invalid escape")
                elif next_char=='"':
                    position+=1
                    token("string",source[start:position],start)
                    break
                position+=1
            continue
        if ch in PUNCT:
            op=source[position:position+2]
            if op in COMPOUND:
                token("punct",op,position);position+=2
            else:
                token("punct",ch,position);position+=1
            continue
        if ch in LETTERS or ch in DIGITS:
            start=position
            kind="integer" if ch in DIGITS else "identifier"
            position+=1
            while position<len(source) and source[position] in LETTERS+DIGITS:
                if kind=="integer" and source[position] not in DIGITS:
                    raise ValueError("invalid numeric suffix")
                position+=1
            token(kind,source[start:position],start)
            continue
        raise ValueError("unsupported character")
    return out


def execute(source:str,tmp:Path):
    content=SOURCE.read_text(encoding="utf-8")
    assert content.count(PREFIX)==1
    fixture=tmp/"case.sdr"
    fixture.write_text(content.replace(PREFIX,'state source = '+json.dumps(source,ensure_ascii=False)),encoding="utf-8")
    return subprocess.run(
        [str(BIN),"run",str(fixture),"scan"],
        capture_output=True,text=True,encoding="utf-8",timeout=30,
        env={"PATH":"/nonexistent","LC_ALL":"C"},
    )


def main():
    assert BIN.is_file(),BIN
    accepted=[
        "", "abc", "42", "x==42 # comment", "sum==42 # comment",
        "x != 5", "a<=1 b>=2 c->d", "(foo,[bar]){}:",
        "x = \"hello world\"", 'msg="Привет, мир!"',
        'face="🐱 и 🦊"', 'a = "a\\\\nb"',
        'a="slash \\\\ and quote \\""', # backslash and escaped quote as source
        "a\t=\r\nb", "x=1#comment\nx=2",
        "# only comment", 's=""', 'a=12#one\nb=42',
        'foo123_abc!=002', 'x<=3\n# line2\nb->"ok"',
        "[1,2,3]+a", "10 / 2", 'name="a#not-comment"'
    ]
    rejected=[
        "12a", "x?y", "А=1", "😀", "x$y", 's="unterminated',
        'a="bad\\q"', 'a="bad\\', 'x="oops\n', "a=@",
        "a"*257, " " * 257, ". " * 110,
    ]
    seed=random.Random(12012)
    for i in range(48):
        symbols=["a","b","q7","0","123"," ","\t", "\n","(",")","==","!=",">=",
                 "->",'""','"Привет"','#ignore\n',"<=",":","="]
        text="".join(seed.choices(symbols,k=seed.randint(0,9)))
        try:oracle(text)
        except ValueError:rejected.append(text)
        else:accepted.append(text)
    with tempfile.TemporaryDirectory(prefix="sedrava-lexer-a2-") as root:
        temp=Path(root)
        for idx,source in enumerate(accepted):
            expected=oracle(source)
            r=execute(source,temp)
            assert r.returncode==0,(idx,repr(source),r.stdout,r.stderr)
            state=json.loads(r.stdout)
            actual=[{k:x[k] for k in ("kind","lexeme","offset")} for x in state["tokens"]["items"]]
            assert actual==expected,(idx,repr(source),actual,expected)
            assert state["cursor"]==len(source),(idx,state["cursor"],len(source))
            assert not state["in_string"] and not state["escaped"]
            assert state["fragment"]==""
            assert json.loads(execute(source,temp).stdout)==state,"Non-deterministic replay"
        for idx,source in enumerate(rejected):
            try:oracle(source)
            except ValueError: pass
            else: raise AssertionError(f"invalid test fixture accepted by oracle: {source!r}")
            r=execute(source,temp)
            assert r.returncode!=0,(idx,repr(source),r.stdout,r.stderr)
    print(f"PASS A2 Sedrava-written lexer: {len(accepted)} accepted / {len(rejected)} rejected")
    print("PASS one-action scan, exact token kind/lexeme/Unicode scalar offset, repeatability")
    print("PASS escaped strings, comments, whitespace, compound operators, full-action rejection")
    print("NO CLAIM: not the complete Rust compiler lexer, no self-hosted parser/IR")


if __name__=="__main__":
    main()
