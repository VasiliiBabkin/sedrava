"""Run real generated domain adapters; compare acceptance AND every state field."""
import base64,json,shutil,subprocess,tempfile
from pathlib import Path
from sedrava_core import parse,transition
from sedrava_syntax import physical_lines
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
    from sedrava_records import structured
    program=program or parse(source)
    compiler=shutil.which('kotlinc') or '/workspace/toolchains/kotlinc/bin/kotlinc'
    if not Path(compiler).exists():raise RuntimeError('Kotlin compiler required; do not count as verified')
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp);path=generate(source,root/'android',_program=program or parse(source),_domain_only=True)
        code='\n'.join(line for line in physical_lines(path.read_text()) if not line.startswith(('package ','import ')))
        scalar_trace=not structured(program)
        if scalar_trace:
            # Older scalar-only apps intentionally have no structured snapshot
            # runtime. Encode every real field instead of modifying the fixture.
            parts=[]
            for key in program.states:
                encoded='java.util.Base64.getEncoder().encodeToString(s.sdr_'+key+'.toString().toByteArray(Charsets.UTF_8))'
                parts.append(quoted(json.dumps(key)+':"')+'+'+encoded+'+'+quoted('"'))
            snapshot=quoted('{"state":{')+'+'+('+'+quoted(',')+'+').join(parts)+'+'+quoted('}}')
            code+='\ninternal fun snapshotState(s:SedravaState,full:Boolean):String = '+snapshot+'\n'
        code+='\nfun main(){var s=SedravaState();\n'
        for action in sequence:code+='run {val before=s;s=transitionState(s,'+quoted(action)+');println("{\\\"accepted\\\":"+(s!==before)+",\\\"snapshot\\\":"+snapshotState(s,true)+"}")}\n'
        code+='}\n';file=root/'Run.kt';file.write_text(code);jar=root/'run.jar'
        result=subprocess.run([compiler,str(file),'-include-runtime','-d',str(jar)],capture_output=True,text=True,timeout=90)
        if result.returncode:raise AssertionError(result.stderr)
        result=subprocess.check_output(['java','-jar',str(jar)],text=True,timeout=30)
        rows=[{'accepted':(row:=json.loads(line))['accepted'],'state':row['snapshot']['state']} for line in physical_lines(result)]
        if scalar_trace:
            for row in rows:
                for key,initial in program.states.items():
                    value=base64.b64decode(row['state'][key]).decode('utf-8')
                    row['state'][key]=int(value) if type(initial) is int else value=='true' if type(initial) is bool else value
        return rows
