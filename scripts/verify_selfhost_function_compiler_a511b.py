#!/usr/bin/env python3
import os,json,subprocess,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
BIN=Path(os.environ["SEDRAVA_NATIVE_BIN"])
TEMPLATE=(ROOT/"examples/self_host/function_compiler_a511b.sdr").read_text()
PREFIX='state source = "fn main() -> int = 42"'
ACTIONS=("tokenize","signatures_pass","lower_source","run_ir")
def main():
 valid=[
 ("fn main() -> int:\n    let i = 0\n    let j = 0\n    let n = 0\n    while i < 2:\n        j = 0\n        while j < 3:\n            n = n+1\n            j = j+1\n        i = i+1\n    return n",6),
 ("fn main() -> int:\n    let i = 0\n    let n = 0\n    while i < 4:\n        if i < 2:\n            n = n+1\n        i = i+1\n    return n",2),
 ("fn main() -> int:\n    let n = 0\n    if 1 == 0:\n        while n < 3:\n            n = 2147483647+1\n    return n",0),
 ("fn main() -> int:\n    let n = 0\n    if 1 == 1:\n        if 2 < 3:\n            n = 7\n    return n",7),
 ("fn main() -> int:\n    let i = 0\n    while i < 2:\n        i = i+1\n    while i < 4:\n        i = i+1\n    return i",4),
 ("fn fact(n: int) -> int = 1 if n < 2 else n*fact(n-1)\nfn main() -> int = fact(5)",120)]
 invalid=[
 "fn main() -> int:\n    let n = 0\n    if 1 == 1:\n    return n",
 "fn main() -> int:\n    let n = 0\n    while n < 2:\n        if n < 1:\n        n = n+1\n    return n",
 "fn main() -> int:\n    let n = 0\n            n = 1\n    return n",
 "fn main() -> int:\n    let n = 0\n    if 1 < 2:\n        let x = 1\n    return n",
 "fn main() -> int:\n    let n = 0\n    if 1 < 2:\n        if 2 < 3:\n            if 3 < 4:\n                n = 1\n    return n"]
 with tempfile.TemporaryDirectory(prefix="sedrava-a511b-") as t:
    p=Path(t)/"case.sdr"
    def run(src):
        assert TEMPLATE.count(PREFIX)==1
        p.write_text(TEMPLATE.replace(PREFIX,"state source = "+json.dumps(src)))
        return subprocess.run([str(BIN),"run",str(p),*ACTIONS],capture_output=True,text=True,timeout=30)
    for src,want in valid:
        r=run(src);assert r.returncode==0,(src,r.stderr)
        d=json.loads(r.stdout);assert d["finished"] and d["answer"]==want,(src,d["answer"],want,d["runtime_error"])
    for src in invalid:
        r=run(src);assert r.returncode!=0,(src,r.stdout)
    r=run("fn main() -> int:\n    let n = 0\n    if 1 < 2:\n        while n == 0:\n            n = 0\n    return n")
    assert r.returncode==0,r.stderr
    d=json.loads(r.stdout);assert not d["finished"] and d["runtime_error"]=="STEP_BUDGET"
 print("PASS A5.11b: 6 programs, nested while/if, 5 invalid inputs, nested infinite-loop budget")
if __name__=="__main__":main()
