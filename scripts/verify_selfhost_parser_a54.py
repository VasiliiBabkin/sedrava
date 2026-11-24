#!/usr/bin/env python3
"""Independent recursive-descent tree oracle for the Sedrava stack parser."""
import json, random, tempfile
from pathlib import Path
import verify_selfhost_parser_a53 as previous
from verify_selfhost_parser_a51 import oracle as token_oracle
previous.PROGRAM = previous.ROOT / "examples/self_host/parser_a54.sdr"

def oracle(source):
    ts=token_oracle(source)
    i=0; depth=0; statements=[]
    def take():
        nonlocal i
        if i>=len(ts): raise ValueError("unexpected eof")
        t=ts[i]; i+=1; return t
    def peek():
        return ts[i] if i<len(ts) else {"kind":"EOF","lexeme":""}
    def atom():
        t=take()
        if t["kind"]=="integer": return ("integer",t["lexeme"],t["offset"],t["end"])
        if t["lexeme"]!="(": raise ValueError("expected operand")
        expr=expression(0)
        close=take()
        if close["lexeme"]!=")": raise ValueError("expected closing parenthesis")
        return ("group",t["offset"],close["end"],expr)
    def expression(minimum):
        left=atom()
        priorities={"+":1,"-":1,"*":2,"/":2}
        while (priority:=priorities.get(peek()["lexeme"],0))>minimum:
            op=take()["lexeme"]
            right=expression(priority)
            left=("binary",op,span(left)[0],span(right)[1],left,right)
        return left
    while i<len(ts):
        t=take()
        if t["kind"]=="INDENT":
            if not statements or t["level"]!=depth+1: raise ValueError("indent")
            depth+=1;continue
        if t["kind"]=="DEDENT":
            depth-=1;continue
        if t["kind"]!="identifier" or take()["lexeme"]!="=": raise ValueError("assignment")
        tree=expression(0)
        if take()["kind"]!="NEWLINE": raise ValueError("newline")
        statements.append((t["lexeme"],depth,t["line"],t["offset"],span(tree)[1],tree))
    if not statements: raise ValueError("empty")
    return statements

def span(t): return (t[1],t[2]) if t[0]=="group" else (t[2],t[3])

def actual(data):
    nodes=data["program_expr_nodes"]["items"]
    assert [n["id"] for n in nodes]==list(range(1,len(nodes)+1))
    used=set()
    def tree(i):
        assert i not in used and 1<=i<=len(nodes)
        used.add(i); n=nodes[i-1]; k=n["kind"]; a=n["start"]; b=n["end"]
        if k=="integer":
            assert n["left_id"]==n["right_id"]==0
            return (k,n["lexeme"],a,b)
        assert 0<n["left_id"]<i
        if k=="group":
            assert n["right_id"]==0
            return (k,a,b,tree(n["left_id"]))
        assert k=="binary" and 0<n["right_id"]<i
        return (k,n["operator"],a,b,tree(n["left_id"]),tree(n["right_id"]))
    result=[(s["name"],s["depth"],s["line"],s["start"],s["end"],tree(s["expression_id"])) for s in data["program_expr_statements"]["items"]]
    assert len(used)==len(nodes)
    assert data["program_expr_cursor"]==len(data["unified_tokens"]["items"])+1
    return result

def main():
    positive=["a=1","a=1+2*3-4/5+6","a=(1+2)*3","a=((1))","a=1-(2-3)",
        "a=8/4/2","a=1+(2*3+(4-5))*6","a=001+(2) # comment",
        "a=1\n    b=(2+3)*4\nc=9","a="+ "+".join(["1"]*40),
        "a="+"("*35+"1"+")"*35,"# привет\na=(2+3)"]
    negative=["","a=()","a=(1","a=1)","a=1+(2*)","a=1 2","a=1(2)",
        "a=(1)(2)","a=1+","a=+1","a=1**2","a=1+(2\n)","a=1+x",
        "a=1;","a=(1+2))","a=1\n  b=2","a="+"1+"*60+"1"]
    rng=random.Random(0xA54)
    def expr(d):
        if d==0 or rng.random()<.3: return str(rng.randrange(100))
        l=expr(d-1);r=expr(d-1)
        return "("+l+rng.choice("+-*/")+r+")" if rng.random()<.65 else l+rng.choice("+-*/")+r
    positive += ["r="+expr(4) for _ in range(30)]
    with tempfile.TemporaryDirectory(prefix="sedrava-a54-") as tmp:
        for source in positive:
            print("CASE",source[:120],flush=True)
            run=previous.run(source,Path(tmp))
            assert run.returncode==0,(source,run.stderr)
            data=json.loads(run.stdout)
            assert actual(data)==oracle(source),(source,actual(data),oracle(source))
        for source in negative:
            run=previous.run(source,Path(tmp))
            assert run.returncode!=0,(source,run.stdout[:100])
        assert previous.run("a=1",Path(tmp),("parse_expression_program",)).returncode!=0
        assert previous.run("a=1",Path(tmp),previous.ACTIONS+("parse_expression_program",)).returncode!=0
    print(f"PASS A5.4: {len(positive)} accepted / {len(negative)} rejected + 2 sequencing guards")
if __name__=="__main__":main()
