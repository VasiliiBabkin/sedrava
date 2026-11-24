#!/usr/bin/env python3
import os,json,subprocess,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
BIN=Path(os.environ["SEDRAVA_NATIVE_BIN"])
TEMPLATE=(ROOT/"examples/self_host/function_compiler_a511a.sdr").read_text()
PREFIX='state source = "fn main() -> int = 42"'
ACTIONS=("tokenize","signatures_pass","lower_source","run_ir")
def main():
 valid=[
 ("fn main() -> int:\n    let i = 1\n    let total = 0\n    while i < 6:\n        total = total+i\n        i = i+1\n    return total",15),
 ("fn main() -> int:\n    let i = 0\n    while i < 0:\n        i = 2147483647+1\n    return i",0),
 ("fn f(n: int) -> int:\n    let i = 1\n    let p = 1\n    while i < n+1:\n        p = p*i\n        i = i+1\n    return p\nfn main() -> int = f(5)",120),
 ("fn main() -> int:\n    let i = 0\n    while i < 2:\n        i = i+1\n    while i < 4:\n        i = i+1\n    return i",4),
 ("fn main() -> int:\n    let x = 1\n    x = x+4\n    return x",5),
 ("fn fact(n: int) -> int = 1 if n < 2 else n*fact(n-1)\nfn main() -> int = fact(5)",120),
 ]
 invalid=[
 "fn main() -> int:\n    let i = 0\n    while i:\n        i = i+1\n    return i",
 "fn main() -> int:\n    let i = 0\n    while i < 1:\n    return i",
 "fn main() -> int:\n    let i = 0\n        i = 1\n    return i",
 "fn main() -> int:\n    let i = 0\n    while i < 1:\n        let x = 1\n    return i",
 "fn main() -> int:\n    let i = 0\n    while i < 1:\n        return i\n    return i",
 "fn main() -> int:\n    x = 1\n    return x",
 "fn f(n: int) -> int:\n    n = 1\n    return n\nfn main() -> int = f(2)",
 ]
 with tempfile.TemporaryDirectory(prefix="sedrava-a511a-") as t:
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
    r=run("fn main() -> int:\n    let i = 0\n    while i == 0:\n        i = 0\n    return i")
    assert r.returncode==0,r.stderr
    d=json.loads(r.stdout);assert not d["finished"] and d["runtime_error"]=="STEP_BUDGET",d
 print("PASS A5.11a: 6 source programs, 7 invalid cases, infinite loop step budget")
if __name__=="__main__":main()
