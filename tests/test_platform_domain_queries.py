"""Complete-state differential checks of bounded collection algebra, including failures."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from sedrava_core import parse,transition
from sedrava_records import plain
from web_codegen import generate

SOURCE=(Path(__file__).parent/'fixtures/platform_logic.sdr').read_text()
SEQUENCE=['query','seed','query','unicode_sort','transform','query','overflow','sum_overflow','remove_first','query','remove_first','transform','query']

def reference():
    program=parse(SOURCE);state=program.states.copy();out=[]
    for action in SEQUENCE:
        try:state,_=transition(program,state,action)
        except ValueError:pass
        out.append({key:plain(value) for key,value in state.items()})
    return out

class Queries(unittest.TestCase):
    def test_full_states_javascript_and_atomicity(self):
        p=parse(SOURCE);js=generate(SOURCE,_program=p,_domain_only=True)
        script='const vm=require("node:vm"),c=vm.createContext({});vm.runInContext('+json.dumps(js)+',c);console.log(JSON.stringify(vm.runInContext('+json.dumps('(()=>{let s={...initialState};return '+json.dumps(SEQUENCE)+'.map(a=>{try{s=actions[a](s)}catch(_){}return s;});})()')+',c)));'
        result=subprocess.run(['node','-e',script],capture_output=True,text=True,check=True)
        expected=reference();self.assertEqual(json.loads(result.stdout),expected)
        self.assertEqual([r['id'] for r in expected[3]['projected']['items']],[3,2,1])
        self.assertEqual(expected[6],expected[5]);self.assertEqual(expected[7],expected[6])
        self.assertEqual(expected[-1]['rows']['next_id'],4)
    def test_kotlin_generated_adapter_full_states(self):
        from android_codegen_v03 import generate as android
        compiler=shutil.which('kotlinc') or '/workspace/toolchains/kotlinc/bin/kotlinc'
        if not Path(compiler).exists():self.skipTest('Kotlin unavailable; Android CI still required')
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);file=android(SOURCE,root/'android',_domain_only=True)
            code='\n'.join(line for line in file.read_text().splitlines() if not line.startswith(('package ','import ')))
            code+='\nfun main(){var s=SedravaState();\n'+''.join('s=transitionState(s,"'+action+'");println(snapshotState(s,true));\n' for action in SEQUENCE)+'}\n'
            path=root/'Run.kt';path.write_text(code);jar=root/'run.jar'
            result=subprocess.run([compiler,str(path),'-include-runtime','-d',str(jar)],capture_output=True,text=True,timeout=90)
            self.assertEqual(result.returncode,0,result.stderr)
            result=subprocess.run(['java','-jar',str(jar)],capture_output=True,text=True,check=True,timeout=30)
            self.assertEqual([json.loads(line)['state'] for line in result.stdout.splitlines()],reference())
    def test_static_types_selectors_and_resources(self):
        for expression in ['filter(rows,"score",true)','sort(rows,"missing")','sum(rows,"title")','map(rows,matches,"a")','filter(rows,raised,1)','find(rows,matches,1)','sort(rows,"title",true)','filter(rows,"done",1)']:
            with self.subTest(expression=expression),self.assertRaises(ValueError):parse(SOURCE.replace('total=sum(rows,"score")','total=count('+expression+')'))
        self.assertEqual(reference()[0]['every'],True)
        expensive=SOURCE.replace('max=8','max=100').replace('projected=sort(filter(rows,"done",true),"title")','projected=map(map(map(map(rows,raised,1),raised,1),raised,1),raised,1)')
        # Weighted collection work is rejected above the explicit expression budget.
        with self.assertRaisesRegex(ValueError,"complexity limit"):parse(expensive)
