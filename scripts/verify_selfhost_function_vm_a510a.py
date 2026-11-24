#!/usr/bin/env python3
import os,json,subprocess,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
BIN=Path(os.environ["SEDRAVA_NATIVE_BIN"])
TEMPLATE=(ROOT/"examples/self_host/function_vm_a510a.sdr").read_text()
PREFIX='state source = "fn main 0 0\\nconst 42\\nreturn\\nend"'
def main():
    valid=[
        ("fn add 2 2\nload 0\nload 1\nadd\nreturn\nend\nfn main 0 0\nconst 5\nconst 7\ncall add\nreturn\nend",12,2),
        ("fn square 1 2\nload 0\nload 0\nmul\nstore 1\nload 1\nreturn\nend\nfn main 0 1\nconst 3\nstore 0\nconst 4\ncall square\nload 0\nadd\nreturn\nend",19,2),
        ("fn fact 1 1\nload 0\nconst 2\nlt\njz 7\nconst 1\nreturn\nload 0\nload 0\nconst 1\nsub\ncall fact\nmul\nreturn\nend\nfn main 0 0\nconst 5\ncall fact\nreturn\nend",120,6),
        ("fn main 0 0\nconst 2\ncall inc\ncall inc\nreturn\nend\nfn inc 1 1\nload 0\nconst 1\nadd\nreturn\nend",4,2),
    ]
    invalid=[
        "fn main 0 1\nload 0\nreturn\nend", # uninitialized
        "fn main 0 0\ncall absent\nreturn\nend",
        "fn main 0 0\ncall main\nreturn\nend", # depth
        "fn main 0 0\njump 1\nreturn\nend", # step budget
        "fn main 0 0\nconst 1\nconst 2\nreturn\nend", # stack shape
        "fn main 0 0\nconst 2147483647\nconst 1\nadd\nreturn\nend",
        "fn main 0 0\njump 99\nreturn\nend",
        "fn main 0 0\nconst 1\ncall f\nreturn\nend\nfn f 2 2\nload 0\nreturn\nend",
        "fn main 0 0\nload 0\nreturn\nend",
    ]
    with tempfile.TemporaryDirectory(prefix="sedrava-a510a-") as t:
        p=Path(t)/"vm.sdr"
        def run(src,actions=("compile_ir","run_ir")):
            assert TEMPLATE.count(PREFIX)==1
            p.write_text(TEMPLATE.replace(PREFIX,"state source = "+json.dumps(src)))
            return subprocess.run([str(BIN),"run",str(p),*actions],capture_output=True,text=True,timeout=30)
        for src,answer,peak in valid:
            r=run(src);assert r.returncode==0,(src,r.stderr)
            d=json.loads(r.stdout);assert d["finished"] and d["answer"]==answer and d["peak_frames"]==peak,(d["answer"],d["peak_frames"],answer,peak)
        for src in invalid:
            r=run(src);assert r.returncode!=0,(src,r.stdout)
        assert run(valid[0][0],("run_ir",)).returncode!=0
        assert run(valid[0][0],("compile_ir","run_ir","run_ir")).returncode!=0
    print("PASS A5.10a: 4 function IR programs incl. recursion, 9 invalid/limit cases, 2 guards")
if __name__=="__main__":main()
