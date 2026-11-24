#!/usr/bin/env python3
"""Independent Python AST shape oracle for Sedrava call syntax subset."""
import ast,json,tempfile
from pathlib import Path
import verify_selfhost_parser_a56b as prev
runner=prev.runner
runner.PROGRAM=runner.ROOT/"examples/self_host/parser_a56c.sdr"
def shape(t):
    if isinstance(t,ast.Name):return ("identifier",t.id)
    if isinstance(t,ast.Constant):return ("boolean",str(t.value).lower()) if isinstance(t.value,bool) else ("integer",str(t.value))
    if isinstance(t,ast.Call):return ("call",t.func.id,tuple(shape(a) for a in t.args))
    if isinstance(t,ast.BinOp):return ("binary",{ast.Add:"+",ast.Sub:"-",ast.Mult:"*",ast.Div:"/"}[type(t.op)],shape(t.left),shape(t.right))
    if isinstance(t,ast.UnaryOp):return ("unary",{ast.USub:"-",ast.Not:"not"}[type(t.op)],shape(t.operand))
    if isinstance(t,ast.Compare):return ("binary",{ast.Gt:">",ast.Lt:"<",ast.GtE:">=",ast.LtE:"<=",ast.Eq:"==",ast.NotEq:"!="}[type(t.ops[0])],shape(t.left),shape(t.comparators[0]))
    if isinstance(t,ast.BoolOp):
        op="and" if isinstance(t.op,ast.And) else "or"
        a=shape(t.values[0])
        for v in t.values[1:]:a=("binary",op,a,shape(v))
        return a
    raise AssertionError(ast.dump(t))
def actual(data,source):
    ns=data["program_expr_nodes"]["items"];used=set()
    def node(i):
        assert 0<i<=len(ns) and i not in used
        n=ns[i-1];used.add(i);assert n["id"]==i
        assert 0<=n["start"]<n["end"]<=len(source)
        for child in (n["left_id"],n["right_id"]):
            assert child<i
            if child:
                c=ns[child-1];assert n["start"]<=c["start"]<c["end"]<=n["end"]
        return n
    def args(i):
        if not i:return ()
        if ns[i-1]["kind"]=="arguments":
            n=node(i);return args(n["left_id"])+(tree(n["right_id"]),)
        return (tree(i),)
    def tree(i):
        n=node(i);k=n["kind"];a,b=n["left_id"],n["right_id"]
        if k=="call":
            assert b==0 and source[n["start"]:n["end"]].startswith(n["lexeme"]) and source[n["end"]-1]==")"
            return (k,n["lexeme"],args(a))
        if k=="group":return tree(a)
        if k in ("integer","identifier","boolean"):return (k,n["lexeme"].lower() if k=="boolean" else n["lexeme"])
        if k=="unary":return (k,n["operator"],tree(a))
        assert k=="binary";return (k,n["operator"],tree(a),tree(b))
    conditions=[tree(x["expression_id"]) for x in data["condition_exprs"]["items"]]
    statements=[tree(x["expression_id"]) for x in data["program_expr_statements"]["items"]]
    assert len(used)==len(ns)
    return conditions,statements
def main():
    exprs=["f()","f(x)","f(a,b,c)","f(1+2,g(3),h())","f(g(),h(x,y))","-f(x)*g(y+1)","not ready(x) and f(a,b)>0","f(a<b,c<d)","f((a+b),-c)","neg(x)","a+f()+b","f ( 1 , 2 )","f(not x, y and z)","f(1,2)+g(3,4)","(f(x))","f(g(h(1)))"]
    invalid=["f(,x)","f(x,)","f(x,,y)","f(x y)","f(x","f(x))","(x,y)","x,y","true()","1()","f()()","f(x=1)","f(a<b<c)","f(a,(b,c))"]
    with tempfile.TemporaryDirectory(prefix="sedrava-a56c-") as t:
        folder=Path(t)
        for expr in exprs:
            src="action go:\n    r="+expr
            p=runner.run(src,folder,prev.PARSE);assert p.returncode==0,(expr,p.stderr)
            d=json.loads(p.stdout);assert not d["diagnostics"]["items"]
            assert actual(d,src)==([],[shape(ast.parse(expr,mode="eval").body)]),(expr,actual(d,src))
        src="action go:\n    if ready(x) and f(1,2)>0:\n        r=g()\n    else:\n        r=h(x)"
        p=runner.run(src,folder,prev.PARSE);assert p.returncode==0,p.stderr
        d=json.loads(p.stdout);assert actual(d,src)==([shape(ast.parse("ready(x) and f(1,2)>0",mode="eval").body)],[("call","g",()),("call","h",(("identifier","x"),))])
        assert len(d["else_branches"]["items"])==1
        for expr in invalid:
            src="action go:\n    r="+expr
            p=runner.run(src,folder,prev.VALIDATE);assert p.returncode==0,(expr,p.stderr)
            assert len(json.loads(p.stdout)["diagnostics"]["items"])==1,(expr,p.stdout)
            assert runner.run(src,folder,prev.PARSE).returncode!=0
    print(f"PASS A5.6c: {len(exprs)+1} accepted call programs / {len(invalid)} rejected / AST and source spans")
if __name__=="__main__":main()
