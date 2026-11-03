import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from sedrava_core import parse_expr,evaluate,parse,transition
from web_codegen import js_expr
from sedrava_stdlib import JS_RUNTIME,KT_RUNTIME
from android_codegen_v03 import kt

CASES=[
 'text_length("a😀é")','trim("  x\\t\\n")','lower_ascii("İABCΣ😀")',
 'contains("é😀", "😀")','concat("Hello ", "😀")','is_date("2024-02-29")',
 'is_date("2023-02-29")','is_date("2024-01-01\\n")','date_days("2024-01-01\\n")','date_days("1970-01-01")','date_days("0001-01-01")',
 'date_add("2024-02-28", 2)','date_add("0099-12-31", 1)','date_add("9999-12-31", 1)',
 'date_days("2026-13-01")','1 if true else 2147483647 + 1',
 'concat("'+'x'*1024+'", "y")',
]
class Standard(unittest.TestCase):
    def test_python_javascript_all_results_and_errors(self):
        expected=[];expressions=[]
        for text in CASES:
            node=parse_expr(text,{})
            try:expected.append({'value':evaluate(node,{})})
            except ValueError:expected.append({'error':True})
            expressions.append('()=>'+js_expr(node,{}))
        code=JS_RUNTIME+'\nfunction validText(v){return typeof v==="string"&&Array.from(v).length<=1024&&!/[\\uD800-\\uDFFF]/u.test(v.replace(/[\\uD800-\\uDBFF][\\uDC00-\\uDFFF]/g,""));}\nconsole.log(JSON.stringify(['+','.join(expressions)+'].map(fn=>{try{return {value:fn()}}catch(_){return {error:true}}})));'
        out=subprocess.run(['node','-e',code],capture_output=True,text=True,check=True)
        self.assertEqual(json.loads(out.stdout),expected)
    def test_kotlin_matches_date_unicode_and_conditional_values(self):
        import shutil
        compiler=shutil.which('kotlinc') or '/workspace/toolchains/kotlinc/bin/kotlinc'
        if not Path(compiler).exists():self.skipTest('Kotlin compiler unavailable')
        expected=[];expressions=[]
        for text in CASES:
            node=parse_expr(text,{})
            try:
                value=evaluate(node,{});expected.append(str(value).lower() if type(value) is bool else str(value))
            except ValueError:expected.append('ERROR')
            expressions.append('try{println('+kt(node,{})+')}catch(_:Exception){println("ERROR")}')
        code=KT_RUNTIME+'\nfun checkedText(value:String):String{require(value.codePointCount(0,value.length)<=1024);return value}\nfun main(){\n'+'\n'.join(expressions)+'\n}'
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);path=root/'Run.kt';path.write_text(code);jar=root/'run.jar'
            result=subprocess.run([compiler,str(path),'-include-runtime','-d',str(jar)],capture_output=True,text=True,timeout=90)
            self.assertEqual(result.returncode,0,result.stderr)
            result=subprocess.run(['java','-jar',str(jar)],capture_output=True,text=True,check=True,timeout=30)
            self.assertEqual(result.stdout.splitlines(),expected)
    def test_type_errors_and_atomic_date_failure(self):
        for text in ['trim(1)','concat("x",false)','date_add("2026-01-01",true)','"yes" if 1 else "no"','1 if true else "no"']:
            with self.assertRaises(ValueError):parse_expr(text,{})
        source='app "dates"\nstate n=0\nstate day="9999-12-31"\naction bad:\n    n=1\n    day=date_add(day,1)\n'
        program=parse(source)
        with self.assertRaises(ValueError):transition(program,program.states,'bad')
        self.assertEqual(program.states,{'n':0,'day':'9999-12-31'})
