#!/usr/bin/env python3
"""A5.4b restricted block syntax and first-error diagnostics on Sedrava."""
import json,tempfile
from pathlib import Path
import verify_selfhost_parser_a54 as arithmetic
from verify_selfhost_parser_a51 import oracle as token_oracle
previous=arithmetic.previous
previous.PROGRAM=previous.ROOT/"examples/self_host/parser_a54b.sdr"
VALIDATE=("scan","scan_layout","merge_tokens","validate_blocks")
PARSE=VALIDATE+("parse_expression_program",)

def shift(tree,offset):
    if tree[0]=="group":
        return ("group",tree[1]+offset,tree[2]+offset,shift(tree[3],offset))
    if tree[0]=="binary":
        return (tree[0],tree[1],tree[2]+offset,tree[3]+offset,shift(tree[4],offset),shift(tree[5],offset))
    return (tree[0],tree[1],tree[2]+offset,tree[3]+offset)

def independent(source):
    headers=[]; assignments=[]; offset=0
    for ln,line in enumerate(source.splitlines(keepends=True),1):
        raw=line.rstrip("\n"); content=raw.lstrip(" "); spaces=len(raw)-len(content)
        if not content or content.startswith("#"):
            offset+=len(line);continue
        text=content.split("#")[0].rstrip()
        if text.startswith(("action ","if ")):
            kind,subject=text[:-1].split()
            headers.append((kind,subject,spaces//4,ln,offset+spaces,offset+spaces+len(text)))
        else:
            stmt=arithmetic.oracle(text)[0]
            assignments.append((stmt[0],spaces//4,ln,offset+spaces+stmt[3],offset+spaces+stmt[4],shift(stmt[5],offset+spaces)))
        offset+=len(line)
    return headers,assignments

def main():
    positives=[
        "action go:\n    a=1",
        "action go:\n    a=(2+3)*4\n    if true:\n        b=7-2\n    c=9",
        "action go:\n    if false:\n        if true:\n            a=((1))",
        "action one:\n    a=1\naction two:\n    b=2",
        "# привет\naction go: # заголовок\n    # comment\n\n    if false: # c\n        b=1+2*3",
        "action a:\n    if true:\n        x=2\n    if false:\n        y=3\n    z=4",
    ]
    negatives=[
        ("","expected_action",0),
        ("a=1","expected_action",0),
        ("if true:\n    a=1","invalid_header_context",0),
        ("action go","invalid_header",0),
        ("action go:","expected_indented_body",10),
        ("action go:\naction next:\n    a=1","expected_indented_body",11),
        ("action go:\n        a=1","unexpected_indent",19),
        ("action go:\n    a=1\n        b=2","unexpected_indent",27),
        ("action go:\n    action inner:\n        a=1","invalid_header_context",15),
        ("action go:\n    if x:\n        a=1","unsupported_condition",15),
        ("action go:\n    if true:\n    a=1","expected_indented_body",28),
        ("action go:\n    while true:\n        a=1","unsupported_statement",15),
        ("action go:\n    a+1","expected_assignment",15),
        ("action go:\n    a=1+","expected_operand",19),
        ("action go:\n    a=(1","unclosed_group",19),
        ("action go:\n    a=1)","unexpected_close",18),
        ("action go:\n    a=1 2","expected_operator",19),
        ("action go:\n    a=()","expected_operand",18),
    ]
    # Generated small valid programs with different layout and arithmetic forms.
    for i in range(5):
        positives.append(f"action run{i}:\n    if true:\n        x=({i}+2)*3\n    y=7/{i+1}")
    with tempfile.TemporaryDirectory(prefix="sedrava-a54b-") as tmp:
        folder=Path(tmp)
        for source in positives:
            p=previous.run(source,folder,PARSE)
            assert p.returncode==0,(source,p.stderr,p.stdout[:200])
            data=json.loads(p.stdout)
            assert data["validation_done"] and not data["diagnostics"]["items"]
            hs,stmts=independent(source)
            assert [(h["kind"],h["subject"],h["depth"],h["line"],h["start"],h["end"]) for h in data["headers"]["items"]]==hs
            assert arithmetic.actual(data)==stmts,(source,arithmetic.actual(data),stmts)
        for source,code,offset in negatives:
            p=previous.run(source,folder,VALIDATE)
            assert p.returncode==0,(source,p.stderr)
            data=json.loads(p.stdout)
            diag=data["diagnostics"]["items"]
            assert len(diag)==1 and diag[0]["code"]==code and diag[0]["start"]==offset,(source,diag,code,offset)
            d=diag[0]
            assert 0<=d["start"]<=d["end"]<=len(source) and d["line"]>=1 and d["column"]>=1
            assert previous.run(source,folder,PARSE).returncode!=0
        source=positives[0]
        assert previous.run(source,folder,("validate_blocks",)).returncode!=0
        assert previous.run(source,folder,VALIDATE[:-1]+("parse_expression_program",)).returncode!=0
        assert previous.run(source,folder,VALIDATE+("validate_blocks",)).returncode!=0
        assert previous.run(source,folder,PARSE+("parse_expression_program",)).returncode!=0
    print(f"PASS A5.4b: {len(positives)} accepted, {len(negatives)} structured syntax errors, 4 sequencing guards")
if __name__=="__main__":main()
