#!/usr/bin/env python3
"""Independent recursive-descent oracle for bounded compound expressions."""
import json,tempfile
from pathlib import Path
import verify_selfhost_parser_a54b as blocks
from verify_selfhost_parser_a51 import oracle as token_oracle
previous=blocks.previous
previous.PROGRAM=previous.ROOT/"examples/self_host/parser_a55.sdr"
VALIDATE=blocks.VALIDATE
PARSE=blocks.PARSE
def expected(src):
    tokens=token_oracle(src)
    ts=[t for t in tokens if t["line"]==2 and t["kind"] not in ("INDENT","DEDENT","NEWLINE")][2:]
    i=0
    def peek():return ts[i]["lexeme"] if i<len(ts) else ""
    def pop():
        nonlocal i
        t=ts[i];i+=1;return t
    def span(t):return t[-2:]
    def binary(l,op,r):return ("binary",op,l,r,span(l)[0],span(r)[1])
    def chain(inner,ops):
        left=inner()
        while peek() in ops:
            op=pop()["lexeme"];left=binary(left,op,inner())
        return left
    def parse_or():return chain(parse_and,("or",))
    def parse_and():return chain(parse_not,("and",))
    def parse_not():
        if peek()=="not":
            t=pop();r=parse_not();return ("unary","not",r,t["offset"],span(r)[1])
        return parse_compare()
    def parse_compare():
        l=parse_add()
        if peek() in ("==","!=","<",">","<=",">="):return binary(l,pop()["lexeme"],parse_add())
        return l
    def parse_add():return chain(parse_mul,("+","-"))
    def parse_mul():return chain(parse_neg,("*","/"))
    def parse_neg():
        if peek()=="-":
            t=pop();r=parse_neg();return ("unary","-",r,t["offset"],span(r)[1])
        return atom()
    def atom():
        t=pop()
        if t["lexeme"]=="(":
            r=parse_or();end=pop();assert end["lexeme"]==")"
            return ("group",r,t["offset"],end["end"])
        k="integer" if t["kind"]=="integer" else "boolean" if t["lexeme"] in ("true","false","True","False") else "identifier"
        return (k,t["lexeme"],t["offset"],t["end"])
    tree=parse_or();assert i==len(ts),(src,i,ts)
    return tree
def actual(data):
    nodes=data["program_expr_nodes"]["items"]; used=set()
    assert [n["id"] for n in nodes]==list(range(1,len(nodes)+1))
    def tree(i):
        assert i not in used and 1<=i<=len(nodes);used.add(i)
        n=nodes[i-1];k=n["kind"];span=(n["start"],n["end"])
        if k in ("integer","identifier","boolean"):
            assert n["left_id"]==n["right_id"]==0
            return (k,n["lexeme"],*span)
        assert 0<n["left_id"]<i
        l=tree(n["left_id"])
        if k=="group":
            assert n["right_id"]==0
            return (k,l,*span)
        if k=="unary":
            assert n["right_id"]==0
            return (k,n["operator"],l,*span)
        assert k=="binary" and 0<n["right_id"]<i
        return (k,n["operator"],l,tree(n["right_id"]),*span)
    statements=data["program_expr_statements"]["items"]
    assert len(statements)==1 and statements[0]["name"]=="r"
    t=tree(statements[0]["expression_id"])
    assert len(used)==len(nodes)
    return t
def main():
    valid=["a","true","False","-a","--a","not not ready","not a == b","a and not b or c",
           "a + -b * c","-(a+b)","a < b and c >= d","a != b","a <= b","a > b",
           "(a < b) == true","a == (b < c)","a / -b","not (a or b)","-(-2)",
           "a - b - c","not a+b*c>=-d and x or y","a and b and c","(not a) == b",
           "a + (not b)","a>=b or c<d","not -x","x1+foo_2","neg + 1"]
    invalid={"a < b < c":"chained_comparison","a == b != c":"chained_comparison",
        "a < (b) < c":"chained_comparison","a + not b":"expected_operand",
        "-not b":"expected_operand","a == not b":"expected_operand",
        "a not b":"expected_operator","a and":"expected_operand",
        "not":"expected_operand","a + +b":"expected_operand","(not)":"expected_operand",
        "a = b":"expected_operator","a or or b":"expected_operand","a (b)":"expected_operator",
        "a + (b":"unclosed_group","a)":"unexpected_close"}
    with tempfile.TemporaryDirectory(prefix="sedrava-a55-") as tmp:
        folder=Path(tmp)
        for expr in valid:
            src="action go:\n    r="+expr
            p=previous.run(src,folder,PARSE)
            assert p.returncode==0,(expr,p.stderr)
            data=json.loads(p.stdout)
            assert not data["diagnostics"]["items"]
            assert actual(data)==expected(src),(expr,actual(data),expected(src))
        for expr,code in invalid.items():
            src="action go:\n    r="+expr
            p=previous.run(src,folder,VALIDATE)
            assert p.returncode==0,(expr,p.stderr)
            d=json.loads(p.stdout)["diagnostics"]["items"]
            assert len(d)==1 and d[0]["code"]==code,(expr,d,code)
            assert previous.run(src,folder,PARSE).returncode!=0
        assert previous.run("action go:\n    r=1",folder,VALIDATE[:-1]+("parse_expression_program",)).returncode!=0
    print(f"PASS A5.5: {len(valid)} accepted ASTs / {len(invalid)} rejected with diagnostics / 1 sequencing guard")
if __name__=="__main__":main()
