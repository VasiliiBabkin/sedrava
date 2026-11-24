import json,os,sys,subprocess,random,statistics,shutil
from pathlib import Path
H=Path(__file__).resolve().parent
R=Path(sys.argv[1]).resolve();B=Path(sys.argv[2]).resolve()
os.chdir(R);os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
P=[sys.executable,str(R/"sedrava_cli.py")];S=[str(B)];N=shutil.which("node")
rng=random.Random(42);report={}
def test(name,commands,n=12):
    samples={k:[] for k in commands}
    order=[k for k in commands for _ in range(n)];rng.shuffle(order)
    for k in order:
        v=subprocess.check_output([str(H/"measure"),*commands[k]],text=True,timeout=30)
        wall,rss,cpu=v.split();samples[k].append([float(wall),int(rss),float(cpu)])
    report[name]={"samples":samples,"medians":{k:{"wall_ms":round(statistics.median(v[0] for v in a),4),"rss_kib":statistics.median(v[1] for v in a),"cpu_ms":round(statistics.median(v[2] for v in a),4)} for k,a in samples.items()}}
    print(name, json.dumps(report[name]["medians"]),flush=True)
for name,src,actions in [
("reference","examples/reference_09.sdr",["add","add"]),
("records","tests/rust_cases/records_lists.sdr",["add","finish"]),
("functions","tests/rust_cases/functions_queries.sdr",["add"])]:
    test(name,{"python_sedrava":P+["run",src,*actions],"rust_sedrava":S+["run",src,*actions]})
a=["increment"]*5000
test("counter-5000",{"python_sedrava":P+["run","examples/counter.sdr",*a],"rust_sedrava":S+["run","examples/counter.sdr",*a],"plain_python":[sys.executable,str(H/"counter.py"),*a],"plain_js":[N,str(H/"counter.js"),*a],"plain_rust":[str(H/"counter-rust"),*a]})
(H/"memory.json").write_text(json.dumps(report,indent=2)+"\n")
