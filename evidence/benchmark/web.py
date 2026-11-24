import json,os,sys,subprocess,time,statistics,random,shutil
from pathlib import Path
H=Path(__file__).resolve().parent;R=Path.home()/'.sedrava-dev/sedrava';B=Path(sys.argv[1])
os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
def stats(a):return {"n":len(a),"median_ms":statistics.median(a),"p95_ms":sorted(a)[(len(a)*95+99)//100-1],"samples_ms":a}
def build(k):
    d=H/('web-'+k)
    if d.exists():shutil.rmtree(d)
    t=time.perf_counter_ns()
    if k=='sedrava':subprocess.run([str(B),'build','webapp',str(R/'examples/service_journal.sdr'),'--output',str(d)],check=True,stdout=subprocess.DEVNULL)
    else:
        d.mkdir()
        subprocess.run(['node',str(H/'deps/node_modules/typescript/lib/tsc.js'),'--strict','--target','ES2020','--module','none','--outFile',str(d/'app.js'),str(H/'ts-source/app.ts')],check=True)
        for f in ['index.html','app.css']:shutil.copy2(H/'ts-source'/f,d/f)
    return (time.perf_counter_ns()-t)/1e6
runs={k:[] for k in ('sedrava','typescript')}
order=list(runs)*7;random.Random(1).shuffle(order)
for k in order:runs[k].append(build(k))
report={}
for k in runs:
    src=[R/'examples/service_journal.sdr'] if k=='sedrava' else sorted((H/'ts-source').glob('*'))
    d=H/('web-'+k);out=[p for p in d.rglob('*') if p.is_file()]
    env={**os.environ,'SEDRAVA_JSDOM_PATH':str(Path.home()/'.sedrava-dev/tooling/dom-tests/node_modules/jsdom')}
    a=json.loads(subprocess.check_output(['node',str(H/'dom-bench.js'),str(d)],env=env,text=True))
    report[k]={"source_bytes":sum(x.stat().st_size for x in src),"source_lines":sum(len(x.read_bytes().splitlines()) for x in src),"generated_bytes":sum(x.stat().st_size for x in out),"build":stats(runs[k]),"dom":stats(a)}
(H/'web.json').write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True)
