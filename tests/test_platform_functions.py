import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from sedrava_core import parse,transition
from web_codegen import generate

SOURCE='''app "Functions"
fn twice(x: int) -> int = x * 2
fn zero(x: int) -> int = 0
fn identity(value: text) -> text = value
state n=1
state other=0
state label="ok"
derive double_n=twice(n)
action increment:
    let previous=n
    n=n+1
    other=previous
action twice: n=twice(n)
action overflow:
    other=99
    n=zero(2147483647+1)
action label_action: label=identity(label)
screen main:
    value n
'''
class Functions(unittest.TestCase):
    def test_python_js_full_states_eager_overflow_and_locals(self):
        program=parse(SOURCE);sequence=['increment','twice','overflow','label_action']*5
        state=program.states.copy();expected=[]
        for action in sequence:
            try:state,_=transition(program,state,action)
            except ValueError:pass
            expected.append(state.copy())
        js=generate(SOURCE,_program=program,_domain_only=True)
        runner='const vm=require("node:vm");const c=vm.createContext({});vm.runInContext('+json.dumps(js)+',c);console.log(JSON.stringify(vm.runInContext('+json.dumps('(()=>{let s={...initialState};return '+json.dumps(sequence)+'.map(a=>{try{s=actions[a](s);}catch(_){}return s;});})()')+',c)));'
        result=subprocess.run(['node','-e',runner],capture_output=True,text=True,check=True)
        self.assertEqual(json.loads(result.stdout),expected)
        self.assertEqual(expected[2],expected[1])
    def test_types_scope_recursion_and_cost(self):
        for old,new in [('twice(n)','twice(label)'),('fn twice(x: int) -> int = x * 2','fn twice(x: int) -> int = twice(x)'),('let previous=n','let n=1'),('identity(value: text) -> text = value','identity(value: text) -> bool = value')]:
            with self.subTest(new=new),self.assertRaises(ValueError):parse(SOURCE.replace(old,new))
        branch='app "x"\nstate n=0\naction bad:\n    if true:\n        let local=1\n    n=local\n'
        with self.assertRaises(ValueError):parse(branch)
    def test_kotlin_pure_adapter_matches_complete_python_trace(self):
        from android_codegen_v03 import generate as android
        import shutil,os
        compiler=shutil.which('kotlinc') or '/workspace/toolchains/kotlinc/bin/kotlinc'
        if not Path(compiler).exists():self.skipTest('Kotlin compiler unavailable; CI Android remains required')
        program=parse(SOURCE);sequence=['increment','twice','overflow','label_action']*3
        state=program.states.copy();expected=[]
        for action in sequence:
            try:state,_=transition(program,state,action)
            except ValueError:pass
            expected.append(str(state['n'])+','+str(state['other'])+','+state['label'])
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);file=android(SOURCE,root/'android',_domain_only=True)
            code='\n'.join(line for line in file.read_text().splitlines() if not line.startswith(('package ','import ')))
            code+='\nfun main(){var s=SedravaState();\n'+''.join('s=transitionState(s,"'+a+'");println("${s.sdr_n},${s.sdr_other},${s.sdr_label}");\n' for a in sequence)+'}\n'
            kt=root/'Run.kt';kt.write_text(code);jar=root/'run.jar'
            result=subprocess.run([compiler,str(kt),'-include-runtime','-d',str(jar)],capture_output=True,text=True,timeout=90)
            self.assertEqual(result.returncode,0,result.stderr)
            result=subprocess.run(['java','-jar',str(jar)],capture_output=True,text=True,check=True,timeout=30)
            self.assertEqual(result.stdout.splitlines(),expected)
