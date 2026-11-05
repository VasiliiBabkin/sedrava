"""Run real generated domain adapters; compare acceptance AND every state field."""
import json,shutil,subprocess,tempfile
from pathlib import Path
from sedrava_core import parse,transition
from sedrava_records import plain

def reference(source,sequence):
    p=parse(source);state=p.states.copy();out=[]
    for action in sequence:
        try:state,accepted=transition(p,state,action)
        except ValueError:accepted=False
        out.append({'accepted':accepted,'state':{k:plain(v) for k,v in state.items()}})
    return out

def javascript(source,sequence,program=None):
    from web_codegen import generate
    js=generate(source,_program=program or parse(source),_domain_only=True)
    code='const vm=require("node:vm"),c=vm.createContext({});vm.runInContext('+json.dumps(js)+',c);process.stdout.write(JSON.stringify(vm.runInContext('+json.dumps('(()=>{let s={...initialState};return '+json.dumps(sequence)+'.map(a=>{const before=s;try{s=actions[a](s)}catch(_){}return {accepted:s!==before,state:s};});})()')+',c)));'
    with tempfile.TemporaryDirectory() as tmp:
        path=Path(tmp)/'trace.js';path.write_text(code)
        return json.loads(subprocess.check_output(['node',str(path)],text=True,timeout=30))

def kotlin(source,sequence,program=None):
    from android_codegen_v03 import generate,quoted
    compiler=shutil.which('kotlinc') or '/workspace/toolchains/kotlinc/bin/kotlinc'
    if not Path(compiler).exists():raise RuntimeError('Kotlin compiler required; do not count as verified')
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp);path=generate(source,root/'android',_program=program or parse(source),_domain_only=True)
        code='\n'.join(line for line in path.read_text().splitlines() if not line.startswith(('package ','import ')))
        code+='\nfun main(){var s=SedravaState();\n'
        for action in sequence:code+='run {val before=s;s=transitionState(s,'+quoted(action)+');println("{\\\"accepted\\\":"+(s!==before)+",\\\"snapshot\\\":"+snapshotState(s,true)+"}")}\n'
        code+='}\n';file=root/'Run.kt';file.write_text(code);jar=root/'run.jar'
        result=subprocess.run([compiler,str(file),'-include-runtime','-d',str(jar)],capture_output=True,text=True,timeout=90)
        if result.returncode:raise AssertionError(result.stderr)
        result=subprocess.check_output(['java','-jar',str(jar)],text=True,timeout=30)
        return [{'accepted':(row:=json.loads(line))['accepted'],'state':row['snapshot']['state']} for line in result.splitlines()]
