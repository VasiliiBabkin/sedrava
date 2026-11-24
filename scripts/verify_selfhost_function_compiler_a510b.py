#!/usr/bin/env python3
import os,json,subprocess,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
BIN=Path(os.environ["SEDRAVA_NATIVE_BIN"])
TEMPLATE=(ROOT/"examples/self_host/function_compiler_a510b.sdr").read_text()
PREFIX='state source = "fn main() -> int = 42"'
ACTIONS=("tokenize","signatures_pass","lower_source","run_ir")
def main():
 valid=[
    ("fn main() -> int = 2+3*4",14,1),
    ("fn add(a: int,b: int) -> int = a+b\nfn main() -> int = add(5,7)",12,2),
    ("fn main() -> int = twice(add(2,3))*2\nfn twice(x: int) -> int = x*2\nfn add(x: int,y: int) -> int = x+y",20,2),
    ("fn f(a: int,b: int) -> int = (a-b)*b\nfn main() -> int = f(7,3)+f(5,-2)",-2,2),
    ("fn main() -> int = one()+one()\nfn one() -> int = 1",2,2),
    ("fn main() -> int = 20-3-2",15,1),
 ]
 # (7-3)*3 + (5-(-2))*(-2) = -2.
 invalid=["fn main() -> int = f(1)\nfn f(a: int,b: int) -> int = a+b",
 "fn main() -> int = missing(1)","fn main() -> int = x","fn main() -> int = (1,2)",
 "fn main() -> int = 1+","fn main() -> int = 1 2",
 "fn f(a: int,a: int) -> int = a\nfn main() -> int = 0",
 "fn main(a: int) -> int = a","fn main() -> bool = 1",
 "fn main() -> int = 2147483647+1","fn main() -> int = main()",
 "fn main() -> int = f(1,)\nfn f(a: int) -> int = a"]
 with tempfile.TemporaryDirectory(prefix="sedrava-a510b-") as t:
    p=Path(t)/"case.sdr"
    def run(src,actions=ACTIONS):
        assert TEMPLATE.count(PREFIX)==1
        p.write_text(TEMPLATE.replace(PREFIX,"state source = "+json.dumps(src)))
        return subprocess.run([str(BIN),"run",str(p),*actions],capture_output=True,text=True,timeout=30)
    for src,want,depth in valid:
        r=run(src);assert r.returncode==0,(src,r.stderr)
        result=json.loads(r.stdout);assert result["finished"] and result["answer"]==want and result["peak_frames"]==depth,(src,result["answer"],result["peak_frames"])
    for src in invalid:
        r=run(src);assert r.returncode!=0,(src,r.stdout)
    assert run(valid[0][0],("lower_source","run_ir")).returncode!=0
 print("PASS A5.10b: 6 source programs compiled and executed, 12 invalid/overflow/depth rejections, 1 sequencing guard")
if __name__=="__main__":main()
