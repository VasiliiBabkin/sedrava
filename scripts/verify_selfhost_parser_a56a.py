#!/usr/bin/env python3
"""Independent A5.5 expression oracle for A5.6a compound condition AST."""
import json,tempfile
from pathlib import Path
import verify_selfhost_parser_a55 as oracle
previous=oracle.previous
previous.PROGRAM=previous.ROOT/"examples/self_host/parser_a56a.sdr"
VALIDATE=oracle.VALIDATE
PARSE=oracle.PARSE
def shift(t,delta):
    k=t[0]
    if k=="binary":return (k,t[1],shift(t[2],delta),shift(t[3],delta),t[-2]+delta,t[-1]+delta)
    if k=="unary":return (k,t[1],shift(t[2],delta),t[-2]+delta,t[-1]+delta)
    if k=="group":return (k,shift(t[1],delta),t[-2]+delta,t[-1]+delta)
    return (*t[:-2],t[-2]+delta,t[-1]+delta)
def expected(source):
    cond=[];assign=[];offset=0
    for line,raw in enumerate(source.splitlines(keepends=True),1):
        text=raw.rstrip("\n");content=text.lstrip(" ");indent=len(text)-len(content)
        active=content.split("#")[0].rstrip()
        if active.startswith("if "):
            expr=active[3:-1].strip()
            start=offset+indent+active.index(expr,3)
            tree=shift(oracle.expected("action go:\n    r="+expr),start-len("action go:\n    r="))
            cond.append((indent//4,line,offset+indent,offset+indent+len(active),tree))
        elif active and not active.startswith("action "):
            name,tail=active.split("=",1);expr=tail.strip()
            start=offset+indent+len(name)+1+len(tail)-len(tail.lstrip())
            tree=shift(oracle.expected("action go:\n    r="+expr),start-len("action go:\n    r="))
            assign.append((name.strip(),indent//4,line,offset+indent,tree[-1],tree))
        offset+=len(raw)
    return cond,assign
def actual(d):
    ns=d["program_expr_nodes"]["items"];used=set()
    assert [n["id"] for n in ns]==list(range(1,len(ns)+1))
    def tree(i):
        assert 0<i<=len(ns) and i not in used;used.add(i);n=ns[i-1];k=n["kind"];span=n["start"],n["end"]
        if k in ("integer","identifier","boolean"):
            assert n["left_id"]==n["right_id"]==0
            return (k,n["lexeme"],*span)
        assert 0<n["left_id"]<i;l=tree(n["left_id"])
        if k=="group":
            assert n["right_id"]==0;return (k,l,*span)
        if k=="unary":
            assert n["right_id"]==0;return (k,n["operator"],l,*span)
        assert k=="binary" and 0<n["right_id"]<i
        return (k,n["operator"],l,tree(n["right_id"]),*span)
    cond=[(x["depth"],x["line"],x["start"],x["end"],tree(x["expression_id"])) for x in d["condition_exprs"]["items"]]
    assign=[(x["name"],x["depth"],x["line"],x["start"],x["end"],tree(x["expression_id"])) for x in d["program_expr_statements"]["items"]]
    assert len(used)==len(ns)
    assert d["program_expr_cursor"]==len(d["unified_tokens"]["items"])+1
    assert [(h["depth"],h["line"],h["start"],h["end"]) for h in d["headers"]["items"] if h["kind"]=="if"]==[x[:4] for x in cond]
    return cond,assign
def main():
    valid=["action go:\n    if x >= 1 and not blocked:\n        a=2",
           "action go:\n    if not (a==b or c):\n        if x:\n            a=-y\n    b=7",
           "action go:\n    if true:\n        a=1\n    if false:\n        b=2",
           "action go:\n    a=1\naction two:\n    if (a < b) == true:\n        b=a+1",
           "# привет\naction go:\n    if x: # условие\n        a=3",
           "action go:\n    r=2+3"]
    invalid=["action go:\n    if :\n        a=1","action go:\n    if x\n        a=1",
             "action go:\n    if x+: \n        a=1","action go:\n    if (x:\n        a=1",
             "action go:\n    if x < y < z:\n        a=1","action go:\n    if x: a=1",
             "action go:\n    if x:\n    a=1","if x:\n    a=1",
             "action go:\n    if x + not y:\n        a=1","action go:\n    if x:\n        a=1\n    else:\n        a=2"]
    with tempfile.TemporaryDirectory(prefix="sedrava-a56a-") as tmp:
        f=Path(tmp)
        for src in valid:
            p=previous.run(src,f,PARSE);assert p.returncode==0,(src,p.stderr)
            data=json.loads(p.stdout)
            assert not data["diagnostics"]["items"]
            assert actual(data)==expected(src),(src,actual(data),expected(src))
        for src in invalid:
            p=previous.run(src,f,VALIDATE);assert p.returncode==0,(src,p.stderr)
            ds=json.loads(p.stdout)["diagnostics"]["items"]
            assert len(ds)==1 and ds[0]["code"],(src,ds)
            assert previous.run(src,f,PARSE).returncode!=0
        assert previous.run(valid[0],f,VALIDATE[:-1]+("parse_expression_program",)).returncode!=0
    print(f"PASS A5.6a: {len(valid)} valid programs / {len(invalid)} structured errors / 1 sequencing guard")
if __name__=="__main__":main()
