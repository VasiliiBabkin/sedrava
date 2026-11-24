#!/usr/bin/env python3
"""Run the actual Sedrava-authored IR interpreter, compare independent scalar outputs."""
import json,tempfile
from pathlib import Path
import verify_selfhost_parser_a51 as base
base.PROGRAM=base.ROOT/"examples/self_host/executor_a59a.sdr"
FULL=("scan","scan_layout","merge_tokens","load_declarations","validate_blocks","parse_expression_program","analyze","lower_expressions","execute_flat")
def main():
    valid=[
        ("state a = 2\nstate b = 3\nstate flag = false\naction go:\n    a=(a+b)*4\n    b=a-1\n    flag=b>=19",{"a":20,"b":19,"flag":True}),
        ("state x = 7\nstate y = 0\naction go:\n    y=-x*3\n    x=y+2",{"x":-19,"y":-21}),
        ("state flag = true\nstate ok = false\naction go:\n    ok=not flag\n    flag=ok==false",{"flag":True,"ok":False}),
        ("state x = 2147483647\naction go:\n    x=x-2147483647",{"x":0}),
        ("state x = 0\naction go:\n    x=2+3*4\n    x=x*x",{"x":196}),
    ]
    invalid=[
        "state x = 2147483647\naction go:\n    x=x+1",
        "state x = 0\naction go:\n    x=2147483648",
        "state x = 0\naction go:\n    x=50000*50000",
        "state x = 0\nextern fn f() -> int\naction go:\n    x=f()",
        "state x = 0\naction go:\n    if true:\n        x=1",
        "state flag = false\naction go:\n    flag=true or false",
        "state x = 0\naction a:\n    x=1\naction b:\n    x=2",
    ]
    with tempfile.TemporaryDirectory(prefix="sedrava-a59a-") as t:
        folder=Path(t)
        for src,want in valid:
            p=base.run(src,folder,FULL);assert p.returncode==0,(src,p.stderr)
            d=json.loads(p.stdout);assert d["execution_done"]
            got={s["name"]:s["current_int"] if s["result"]=="i" else s["current_bool"] for s in d["symbols"]["items"] if s["kind"]=="v"}
            assert got==want,(src,got,want)
        for src in invalid:
            p=base.run(src,folder,FULL);assert p.returncode!=0,(src,p.stdout)
        assert base.run(valid[0][0],folder,FULL[:-2]+("execute_flat",)).returncode!=0
        assert base.run(valid[0][0],folder,FULL+("execute_flat",)).returncode!=0
    print("PASS A5.9a: 5 executing programs, 7 overflow/unsupported rejections, 2 execution guards")
if __name__=="__main__":main()
