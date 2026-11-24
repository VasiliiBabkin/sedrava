#!/usr/bin/env python3
import os,json,subprocess,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
BIN=Path(os.environ["SEDRAVA_NATIVE_BIN"])
TEMPLATE=(ROOT/"examples/self_host/function_compiler_a510c.sdr").read_text()
PREFIX='state source = "fn main() -> int = 42"'
ACTIONS=("tokenize","signatures_pass","lower_source","run_ir")
def main():
 valid=[
 ("fn main() -> int:\n    let a = 2+3\n    let b = a*4\n    return b+a",25),
 ("fn f(a: int) -> int:\n    let b = a+1\n    return b*b\nfn main() -> int = f(3)+f(4)",41),
 ("fn main() -> int:\n    let x = f(3)\n    return x*2\nfn f(x: int) -> int:\n    let y = x+1\n    return y",8),
 ("fn main() -> int:\n    return 42",42),
 ("fn main() -> int = 20-3-2",15),
 ]
 invalid=[
 "fn main() -> int:\n    let a = a+1\n    return a",
 "fn main() -> int:\n    let a = b\n    let b = 2\n    return a",
 "fn main() -> int:\n    let a = 1\n    let a = 2\n    return a",
 "fn f(x: int) -> int:\n    let x = 2\n    return x\nfn main() -> int = f(1)",
 "fn main() -> int:\n    let x = 1",
 "fn main() -> int:\n    return 1\n    let x = 2",
 "fn main() -> int:\n  return 1",
 "fn main() -> int:\n    let a = 2147483647+1\n    return a",
 "fn f() -> int:\n    let a = 1\n    return a\nfn main() -> int = a",
 "fn main() -> int:\n    return",
 ]
 with tempfile.TemporaryDirectory(prefix="sedrava-a510c-") as t:
    p=Path(t)/"case.sdr"
    def run(src,actions=ACTIONS):
        assert TEMPLATE.count(PREFIX)==1
        p.write_text(TEMPLATE.replace(PREFIX,"state source = "+json.dumps(src)))
        return subprocess.run([str(BIN),"run",str(p),*actions],capture_output=True,text=True,timeout=30)
    for src,want in valid:
        r=run(src);assert r.returncode==0,(src,r.stderr)
        d=json.loads(r.stdout);assert d["finished"] and d["answer"]==want,(src,d["answer"],want)
    for src in invalid:
        r=run(src);assert r.returncode!=0,(src,r.stdout)
    assert run(valid[0][0],("lower_source","run_ir")).returncode!=0
 print("PASS A5.10c: 5 source programs, 10 invalid/overflow cases, 1 guard; scoped locals and sequential initialization")
if __name__=="__main__":main()
