#!/usr/bin/env python3
import sys,os,json,subprocess,statistics,time,random,hashlib,platform,shutil
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(sys.argv[1]).resolve()
NATIVE=Path(sys.argv[2]).resolve()
HERE=Path(__file__).resolve().parent
PY=sys.executable
NODE=shutil.which("node")
RUSTC=shutil.which("rustc")
rng=random.Random(20261124)
os.chdir(ROOT)
aff=sorted(os.sched_getaffinity(0))
os.sched_setaffinity(0,{aff[0]})
def cmd(*argv):
    return subprocess.check_output([str(x) for x in argv],text=True,stderr=subprocess.PIPE,timeout=40)
def metric(x):
    return {"median":round(statistics.median(x),4),"p95":round(sorted(x)[(len(x)*95+99)//100-1],4),"min":round(min(x),4),"max":round(max(x),4)}
def once(argv):
    argv=list(map(str,argv))
    start=time.perf_counter_ns()
    pid=os.posix_spawn(argv[0],argv,os.environ,file_actions=[(os.POSIX_SPAWN_OPEN,1,"/dev/null",os.O_WRONLY,0),(os.POSIX_SPAWN_OPEN,2,"/dev/null",os.O_WRONLY,0)])
    _,status,usage=os.wait4(pid,0)
    elapsed=(time.perf_counter_ns()-start)/1e6
    assert os.waitstatus_to_exitcode(status)==0,(argv[:4],status)
    return [elapsed,usage.ru_maxrss,(usage.ru_utime+usage.ru_stime)*1000]
def bench(name,commands,n=25,check_json=False):
    outputs={k:cmd(*v).strip() for k,v in commands.items()}
    if check_json:
        vals=[json.loads(v) for v in outputs.values()]
        assert all(x==vals[0] for x in vals),(name,outputs)
    for _ in range(3):
        for argv in commands.values():once(argv)
    values={k:[] for k in commands}
    order=[k for k in commands for _ in range(n)];rng.shuffle(order)
    for k in order:values[k].append(once(commands[k]))
    result={"name":name,"n_each":n,"outputs":outputs,"engines":{k:{"wall_ms":metric([x[0] for x in v]),"peak_rss_kib":metric([x[1] for x in v]),"cpu_ms":metric([x[2] for x in v]),"samples":v} for k,v in values.items()}}
    print(json.dumps({"name":name,"summary":{k:{"ms":v["wall_ms"]["median"],"rss":v["peak_rss_kib"]["median"],"p95":v["wall_ms"]["p95"]} for k,v in result["engines"].items()}},ensure_ascii=False),flush=True)
    return result
P=[PY,str(ROOT/"sedrava_cli.py")]
R=[str(NATIVE)]
cases=[
 ("check-reference","check","examples/reference_09.sdr",[]),
 ("run-reference","run","examples/reference_09.sdr",["add","add"]),
 ("run-unicode","run","examples/text_profile.sdr",["rename"]),
 ("test-reference","test","examples/reference_09.sdr",[]),
 ("run-records","run","tests/rust_cases/records_lists.sdr",["add","finish"]),
 ("run-functions","run","tests/rust_cases/functions_queries.sdr",["add"]),
 ("run-navigation","run","tests/rust_cases/navigation.sdr",["open","$back"]),
]
results=[]
for name,op,source,args in cases:
    results.append(bench(name,{"python_sedrava":P+[op,source,*args],"rust_sedrava":R+[op,source,*args]},check_json=op=="run"))
# Direct baselines: same operation and output contract, no generic DSL parsing, UI or persistence.
(HERE/"counter.py").write_text("""import json,sys
count=0
for action in sys.argv[1:]:
    candidate=count+(1 if action=="increment" else -1 if action=="decrement" else 0)
    if action=="reset":candidate=0
    if action not in ("increment","decrement","reset") or not 0<=candidate<=2147483647:raise ValueError("invalid action")
    count=candidate
print(json.dumps({"count":count}))
""")
(HERE/"counter.js").write_text("""let count=0;
for(const action of process.argv.slice(2)){
  if(!["increment","decrement","reset"].includes(action)) throw Error("invalid action");
  const candidate=action==="reset"?0:count+(action==="increment"?1:-1);
  if(!Number.isInteger(candidate)||candidate<0||candidate>2147483647) throw Error("invalid state");
  count=candidate;
}
console.log(JSON.stringify({count}));
""")
(HERE/"counter.rs").write_text("""fn main() {
    let mut count=0i32;
    for a in std::env::args().skip(1) {
        let candidate=match a.as_str(){"increment"=>count.checked_add(1),"decrement"=>count.checked_sub(1),"reset"=>Some(0),_=>None}.expect("invalid");
        assert!(candidate>=0);count=candidate;
    }
    println!("{{\\"count\\":{count}}}");
}
""")
cmd(RUSTC,"-O",HERE/"counter.rs","-o",HERE/"counter-rust")
for n in (1,100,1000,5000):
    actions=["increment"]*n
    results.append(bench(f"counter-{n}",{"python_sedrava":P+["run","examples/counter.sdr",*actions],"rust_sedrava":R+["run","examples/counter.sdr",*actions],"plain_python":[PY,str(HERE/"counter.py"),*actions],"plain_js":[NODE,str(HERE/"counter.js"),*actions],"plain_rust":[str(HERE/"counter-rust"),*actions]},n=20,check_json=True))
# Generated WebApp build: time for a complete fresh output directory; exclude deletion.
build={}
for example in ["webapp_011_tasks","platform_crm","service_journal"]:
    source=ROOT/"examples"/(example+".sdr")
    folder=HERE/("generated-"+example)
    samples=[]
    for _ in range(10):
        if folder.exists():shutil.rmtree(folder)
        samples.append(once(R+["build","webapp",str(source),"--output",str(folder)]))
    files=[p for p in folder.rglob("*") if p.is_file()]
    src=source.read_bytes()
    sizes={str(p.relative_to(folder)):p.stat().st_size for p in files}
    build[example]={"source_lines":len(src.splitlines()),"source_bytes":len(src),"generated_files":sizes,"generated_bytes":sum(sizes.values()),"build_wall_ms":metric([x[0] for x in samples]),"samples":samples}
    print(json.dumps({"webapp":example,**build[example]},ensure_ascii=False),flush=True)
    shutil.rmtree(folder)
report={"utc":datetime.now(timezone.utc).isoformat(),"git":cmd("git","rev-parse","HEAD").strip(),"cpu":next(x.split(":",1)[1].strip() for x in Path("/proc/cpuinfo").read_text().splitlines() if x.startswith("model name")),"pinned_cpu":aff[0],"platform":platform.platform(),"versions":{"python":cmd(PY,"--version").strip(),"node":cmd(NODE,"--version").strip(),"native":cmd(NATIVE,"--version").strip(),"rustc":cmd(RUSTC,"--version").strip()},"binary_sha256":hashlib.sha256(NATIVE.read_bytes()).hexdigest(),"results":results,"webapp":build,"notes":["CLI process start+parse/check+execute+serialize. Warm-cache interleaved order. Linux wait4 child peak RSS and CPU time; RSS includes process startup.","Plain baselines only implement counter semantics, not language runtime, UI or persistence. No claims about human development time or pure compute speed.","Web build size is generated output including shared runtime/assets; source size not a manual implementation comparison."] }
(HERE/"report.json").write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n")
print("COMPLETE",HERE/"report.json",flush=True)
