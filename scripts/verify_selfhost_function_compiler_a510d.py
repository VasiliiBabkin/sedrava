#!/usr/bin/env python3
import os,json,subprocess,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
BIN=Path(os.environ["SEDRAVA_NATIVE_BIN"])
TEMPLATE=(ROOT/"examples/self_host/function_compiler_a510d.sdr").read_text()
PREFIX='state source = "fn main() -> int = 42"'
ACTIONS=("tokenize","signatures_pass","lower_source","run_ir")
def main():
 valid=[
 ("fn fact(n: int) -> int = 1 if n < 2 else n*fact(n-1)\nfn main() -> int = fact(5)",120,6),
 ("fn main() -> int = 7 if 2+3 == 5 else 2147483647+1",7,1),
 ("fn main() -> int = 2147483647+1 if 1 < 0 else 9",9,1),
 ("fn f(a: int) -> int:\n    let b = a+1\n    return b*2 if b < 5 else b\nfn main() -> int = f(3)+f(7)",16,2),
 ("fn main() -> int = 8-2*3",2,1),
 ]
 errors=[
 ("fn main() -> int = 2147483647+1","INTEGER_OVERFLOW"),
 ("fn main() -> int = -2147483647-2","INTEGER_OVERFLOW"),
 ("fn main() -> int = main()","CALL_DEPTH"),
 ]
 invalid=[
 "fn main() -> int = 1 if 2 else 3",
 "fn main() -> int = 1 if 1<2<3 else 0",
 "fn main() -> int = 1 if 1<2",
 "fn main() -> int = 1 else 2",
 "fn main() -> int = 1<2",
 "fn main() -> int:\n    let a = 1 if 1<2 else 3\n    return a",
 "fn main() -> int = missing() if 1<2 else 3",
 ]
 with tempfile.TemporaryDirectory(prefix="sedrava-a510d-") as t:
    p=Path(t)/"case.sdr"
    def run(src):
        assert TEMPLATE.count(PREFIX)==1
        p.write_text(TEMPLATE.replace(PREFIX,"state source = "+json.dumps(src)))
        return subprocess.run([str(BIN),"run",str(p),*ACTIONS],capture_output=True,text=True,timeout=30)
    for src,want,depth in valid:
        r=run(src);assert r.returncode==0,(src,r.stderr)
        d=json.loads(r.stdout);assert d["finished"] and d["runtime_error"]=="" and d["answer"]==want and d["peak_frames"]==depth,(src,d["answer"],d["peak_frames"])
    for src,code in errors:
        r=run(src);assert r.returncode==0,(src,r.stderr)
        d=json.loads(r.stdout);assert not d["finished"] and d["runtime_error"]==code and d["runtime_error_pc"]>0 and d["runtime_error_function"]=="main",(src,d)
    for src in invalid:
        r=run(src);assert r.returncode!=0,(src,r.stdout)
 print("PASS A5.10d: 5 conditional/recursive source programs, 3 structured runtime faults, 7 invalid sources")
if __name__=="__main__":main()
