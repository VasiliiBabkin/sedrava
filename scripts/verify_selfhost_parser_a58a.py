#!/usr/bin/env python3
"""A5.8a inline declarations, signatures and typed action bodies."""
import json,tempfile
from pathlib import Path
import verify_selfhost_parser_a51 as base
base.PROGRAM=base.ROOT/"examples/self_host/parser_a58a.sdr"
PREFIX=("scan","scan_layout","merge_tokens","load_declarations")
FULL=PREFIX+("validate_blocks","parse_expression_program","analyze")
LOWER=FULL+("lower_expressions",)
def main():
    ctx='state x = 1\nstate flag = true\nstate result = 0\nstate label = "текст"\nextern fn add(int,int) -> int\nextern fn ready(int) -> bool\nextern fn zero() -> int\n'
    valid=[("result=add(x,zero())","i"),("flag=ready(x) and not flag","b"),("if ready(x):\n        result=add(x,2)\n    else:\n        result=zero()","i"),("flag=label==label","b")]
    invalid=[("result=add(x)","argument_signature"),("result=flag","assignment_type"),("flag=ready(label)","argument_signature"),("result=missing","unknown_symbol"),("result=label()","not_callable")]
    malformed=[("state x = 1\nstate x = true\n","duplicate_symbol"),("state x = unknown\n","invalid_initializer"),("extern fn f(int,) -> int\n","invalid_signature"),("extern fn f() -> float\n","invalid_signature"),("extern fn f(int) int\n","invalid_signature"),("state if = 1\n","invalid_symbol_name"),("state x = 1+2\n","invalid_declaration")]
    with tempfile.TemporaryDirectory(prefix="sedrava-a58a-") as t:
        folder=Path(t)
        for body,kind in valid:
            source=ctx+"action go:\n    "+body
            p=base.run(source,folder,LOWER);assert p.returncode==0,(source,p.stderr)
            d=json.loads(p.stdout);assert d["context_done"] and d["semantic_done"] and not d["semantic_error"],(source,d["semantic_error"])
            assert len(d["symbols"]["items"])==7
            assert d["symbols"]["items"][4]["parameters"]=="ii"
            ns=d["node_types"]["items"]
            assert all(ns[r["expression_id"]-1]["kind"]==kind for r in d["program_expr_statements"]["items"])
            ops=d["instructions"]["items"];nodes=d["program_expr_nodes"]["items"]
            assert d["lowering_done"] and len(ops)==len(ns)==len(nodes)
            mapping={"integer":"const_int","boolean":"const_bool","identifier":"load","call":"call","arguments":"pack_args","group":"alias","unary":"unary","binary":"binary"}
            for n,t,op in zip(nodes,ns,ops):
                assert op["dst"]==n["id"] and op["opcode"]==mapping[n["kind"]]
                assert op["arg1"]==n["left_id"] and op["arg2"]==n["right_id"] and op["kind"]==t["kind"]
                assert op["symbol_id"]==t["symbol_id"] and (op["start"],op["end"])==(n["start"],n["end"])
                assert 0<=op["arg1"]<op["dst"] and 0<=op["arg2"]<op["dst"]
            if body=="result=add(x,zero())":
                assert [o["opcode"] for o in ops]==["load","call","pack_args","call"]
                assert [o["symbol_id"] for o in ops]==[1,7,0,5]
        for body,code in invalid:
            p=base.run(ctx+"action go:\n    "+body,folder,FULL);assert p.returncode==0,p.stderr
            assert json.loads(p.stdout)["semantic_error"]==code,(body,p.stdout)
        for declaration,code in malformed:
            p=base.run(declaration+"action go:\n    x=1",folder,PREFIX);assert p.returncode==0,(declaration,p.stderr)
            assert json.loads(p.stdout)["semantic_error"]==code,(declaration,p.stdout)
            assert base.run(declaration+"action go:\n    x=1",folder,FULL).returncode!=0
        assert base.run(ctx+"action go:\n    result=1",folder,PREFIX[:-1]+("validate_blocks",)).returncode!=0
        assert base.run(ctx+"action go:\n    result=flag",folder,LOWER).returncode!=0
        assert base.run(ctx+"action go:\n    result=1",folder,LOWER+("lower_expressions",)).returncode!=0
    print("PASS A5.8a/b: 4 typed inline programs, 5 semantic errors, 7 declaration errors, typed IR, 3 sequencing/error guards")
if __name__=="__main__":main()
