#!/usr/bin/env python3
import json,tempfile
from pathlib import Path
import verify_selfhost_parser_a51 as base
base.PROGRAM=base.ROOT/"examples/self_host/executor_a59b.sdr"
FULL=("scan","scan_layout","merge_tokens","load_declarations","validate_blocks","parse_expression_program","analyze","lower_expressions","execute_branches")
def main():
 valid=[
 ("state x = 2\naction go:\n    if x>1:\n        x=x+3\n    else:\n        x=9\n    x=x*2",10),
 ("state x = 0\naction go:\n    if x>1:\n        x=2147483647+1\n    else:\n        x=8",8),
 ("state x = 1\naction go:\n    if x==1:\n        if false:\n            x=99\n        else:\n            x=3\n    else:\n        x=9\n    x=x+1",4),
 ("state x = 0\naction go:\n    if false:\n        if true:\n            x=3\n        else:\n            x=4\n    else:\n        x=5\n    if x==5:\n        x=6",6),
 ("state x = 1\naction go:\n    if true:\n        x=2\n    if x==2:\n        x=4\n    else:\n        x=8",4),
 ("state x = 0\naction go:\n    if false:\n        if 2147483647+1>0:\n            x=9\n    x=1",1),
 ("state x = 1\naction go:\n    x=x+2\n    if x==3:\n        x=x*2",6)]
 invalid=["state x = 0\naction go:\n    if true:\n        x=2147483647+1",
 "state x = 0\naction go:\n    if false:\n        x=missing",
 "state x = 0\naction go:\n    if x:\n        x=1",
 "state x = 0\naction a:\n    x=1\naction b:\n    x=2"]
 with tempfile.TemporaryDirectory(prefix="sedrava-a59b-") as t:
    folder=Path(t)
    for src,want in valid:
        p=base.run(src,folder,FULL);assert p.returncode==0,(src,p.stderr)
        d=json.loads(p.stdout);assert d["execution_done"] and d["symbols"]["items"][0]["current_int"]==want,(src,d["symbols"])
    for src in invalid:
        p=base.run(src,folder,FULL);assert p.returncode!=0,(src,p.stdout)
    assert base.run(valid[0][0],folder,FULL+("execute_branches",)).returncode!=0
 print("PASS A5.9b: 7 branch programs, 4 invalid/overflow rejections, repeated execution guard")
if __name__=="__main__":main()
