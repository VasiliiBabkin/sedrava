#!/usr/bin/env python3
"""Independent indentation oracle and AST regression for linked if/else."""
import json,tempfile
from pathlib import Path
import verify_selfhost_parser_a56a as prev
runner=prev.previous
runner.PROGRAM=runner.ROOT/"examples/self_host/parser_a56b.sdr"
VALIDATE=prev.VALIDATE
PARSE=prev.PARSE
def oracle(source):
    headers=[];branches=[];last={};offset=0
    for line,raw in enumerate(source.splitlines(keepends=True),1):
        text=raw.rstrip("\n");content=text.lstrip(" ");depth=(len(text)-len(content))//4
        active=content.split("#")[0].rstrip()
        if not active:offset+=len(raw);continue
        for d in list(last):
            if d>depth:del last[d]
        if active.startswith("action ") or active.startswith("if ") or active=="else:":
            kind=active.split()[0].rstrip(":")
            headers.append((kind,depth,line,offset+depth*4,offset+depth*4+len(active)))
            if kind=="else":
                match=last[depth];assert headers[match-1][0]=="if"
                branches.append((match,len(headers),depth))
            last[depth]=len(headers)
        else:last[depth]=0
        offset+=len(raw)
    return headers,branches
def main():
    valid=[
        "action go:\n    if x:\n        a=1\n    else:\n        a=2",
        "action go:\n    if x:\n        if y:\n            a=1\n        else:\n            a=2\n    else:\n        a=3",
        "action go:\n    if x:\n        if y:\n            a=1\n    else:\n        a=2",
        "action go:\n    if x:\n        a=1\n    # comment\n\n    else: # привет\n        a=-b",
        "action go:\n    if x:\n        a=1\n    else:\n        if y:\n            a=2\n        else:\n            a=3",
        "action go:\n    if x:\n        a=1\n    else:\n        a=2\n    if y:\n        a=3\n    else:\n        a=4",
        "action a:\n    if x:\n        a=1\naction b:\n    if y:\n        b=2\n    else:\n        b=3",
        "action go:\n    if x>=1 and not y:\n        a=1\n    else:\n        a=2\n    b=a+1",
        "action go:\n    r=2+3",
    ]
    invalid=[
        ("action go:\n    else:\n        a=1","orphan_else"),
        ("action go:\n    if x:\n        a=1\n    b=2\n    else:\n        a=3","orphan_else"),
        ("action go:\n    if x:\n        a=1\n    else:\n        a=2\n    else:\n        a=3","orphan_else"),
        ("action a:\n    if x:\n        a=1\naction b:\n    else:\n        b=2","orphan_else"),
        ("action go:\n    if x:\n        a=1\n        else:\n            a=2","orphan_else"),
        ("action go:\n    if x:\n        a=1\n    else x:\n        a=2","invalid_else_header"),
        ("action go:\n    if x:\n        a=1\n    else: a=2","invalid_else_header"),
        ("action go:\n    if x:\n        a=1\n    else:","expected_indented_body"),
        ("action go:\n    if x:\n        a=1\n    else:\n    b=2","expected_indented_body"),
        ("action go:\n    if x:\n        a=1\nelse:\n    a=2","orphan_else"),
        ("action go:\n    if x:\n        if y:\n            a=1\n    if z:\n        else:\n            a=2","orphan_else"),
    ]
    with tempfile.TemporaryDirectory(prefix="sedrava-a56b-") as tmp:
        f=Path(tmp)
        for src in valid:
            p=runner.run(src,f,PARSE);assert p.returncode==0,(src,p.stderr)
            data=json.loads(p.stdout);assert not data["diagnostics"]["items"],(src,data["diagnostics"])
            hs,bs=oracle(src)
            assert [(h["kind"],h["depth"],h["line"],h["start"],h["end"]) for h in data["headers"]["items"]]==hs
            assert [(b["if_header_id"],b["else_header_id"],b["depth"]) for b in data["else_branches"]["items"]]==bs
            # Replace only else headers with equal-length whitespace for the
            # prior expression oracle, preserving offsets and indentation of bodies.
            masked="".join((" "*len(l.rstrip("\n"))+("\n" if l.endswith("\n") else "")) if l.strip().startswith("else:") else l for l in src.splitlines(keepends=True))
            assert prev.actual(data)==prev.expected(masked),(src,prev.actual(data),prev.expected(masked))
        for src,code in invalid:
            p=runner.run(src,f,VALIDATE);assert p.returncode==0,(src,p.stderr)
            ds=json.loads(p.stdout)["diagnostics"]["items"]
            assert len(ds)==1 and ds[0]["code"]==code,(src,ds,code)
            assert runner.run(src,f,PARSE).returncode!=0
        assert runner.run(valid[0],f,VALIDATE[:-1]+("parse_expression_program",)).returncode!=0
    print(f"PASS A5.6b: {len(valid)} valid programs / {len(invalid)} structured else errors / 1 sequencing guard")
if __name__=="__main__":main()
