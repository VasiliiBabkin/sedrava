"""Experimental bounded core extensions with stable Python/Web/Kotlin contracts."""
import json
import shutil
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from sedrava_core import parse, run, resolve, transition
from sedrava_diagnostics import Diagnostic, SedravaError, from_exception
from sedrava_records import ListValue
from sedrava_stdlib import SIGNATURES, JS_RUNTIME, KT_RUNTIME, apply, js_call, kt_call
from web_codegen import generate

TEXT = '''app "Unicode scalar example"
state text = "A😀Б"
state sum = 0
derive emoji = text_at(text, 1)
derive segment = text_slice(text, 1, 3)
derive found = text_index(text, "Б")
derive missing = text_index(text, "not found")
derive scalar = unicode_ord(emoji)
derive again = unicode_chr(scalar)
action tally:
    repeat i in range(0, 5):
        sum = sum + i
test initial: -> segment == "😀Б" and found == 2 and scalar == 128512
test repeated: tally -> sum == 10 and again == "😀"
screen main:
    text "Unicode scalar"
    value sum
    value emoji
'''

LIST = '''app "Indexed bounded records"
record Item:
    title: text
    checked: bool
state items: list<Item>(max=3) = []
state selected = ""
action add:
    items = append(items, Item(title="first", checked=false))
    items = append(items, Item(title="second", checked=true))
action select:
    selected = list_at(items, 1).title
action keep:
    items = list_slice(items, 1, 2)
action empty:
    items = list_clear(items)
test add: add -> count(items) == 2 and list_at(items, 0).title == "first"
test select: add, select -> selected == "second"
test slice: add, keep -> count(items) == 1 and get(items, 2).title == "second"
test clear: add, empty -> count(items) == 0 and next_id(items) == 3
screen main:
    text "Indexed records"
    value selected
'''


class BoundedTextCore(unittest.TestCase):
    def test_unicode_scalar_index_slice_roundtrip(self):
        p = parse(TEXT)
        self.assertEqual(run(p), 2)
        values = resolve(p.states,p.derived)
        self.assertEqual([values[k] for k in ("emoji","segment","found","missing","scalar","again")],
                         ["😀", "😀Б", 2, -1, 128512, "😀"])
        changed, accepted = transition(p,p.states,"tally")
        self.assertTrue(accepted)
        self.assertEqual(changed["sum"], 10)
        self.assertEqual(p.states["sum"], 0)

    def test_bracket_scalar_index_and_half_open_slice(self):
        program = parse('app "Brackets"\nstate sample = "A😀Б"\n'
                        'derive letter = sample[1]\n'
                        'derive part = sample[1:3]\n'
                        'derive cp = unicode_ord(sample[1])\n'
                        'test yes: -> letter == "😀" and part == "😀Б" and cp == 128512\n')
        self.assertEqual(run(program),1)
        values=resolve(program.states,program.derived)
        self.assertEqual(values["letter"],"😀")
        self.assertEqual(values["part"],"😀Б")
        for expr in ('"abc"[0:2:1]', '"abc"[:1]', '"abc"[0:]',
                     '"abc"[true]', '5[0]', '"abc"[-1]'):
            with self.subTest(expr=expr), self.assertRaises(ValueError):
                parse('app "Invalid"\nstate n = '+expr)

    def test_unicode_scalar_semantics_and_bounds(self):
        self.assertEqual(apply("text_at", ["e\u0301😀",2]), "😀")
        self.assertEqual(apply("text_slice", ["e\u0301😀",0,2]), "e\u0301")
        self.assertEqual(apply("text_index", ["😀A😀","A"]), 1)
        self.assertEqual(apply("unicode_ord", ["😀"]), 128512)
        self.assertEqual(apply("unicode_chr", [128512]), "😀")
        self.assertEqual(apply("text_index", ["A😀",""]), 0)
        for expr in ('text_at("😀", 1)',
                     'text_at("", 0)',
                     'text_at("😀", -1)',
                     'text_slice("A", 0, 2)',
                     'text_slice("A", 1, 0)',
                     'unicode_chr(55296)',
                     'unicode_chr(-1)',
                     'unicode_chr(1114112)',
                     'unicode_ord("")',
                     'unicode_ord("AB")'):
            with self.subTest(expr=expr), self.assertRaises(ValueError):
                parse('app "Invalid"\nstate n = ' + expr)
        for expr in ('text_at("hi", "1")', 'text_slice("abc", 0, true)',
                     'unicode_chr("65")', 'unicode_ord(66)', 'text_index("a", 1)'):
            with self.subTest(expr=expr), self.assertRaises(ValueError):
                parse('app "Invalid"\nstate n = ' + expr)

    def test_portable_backend_helpers_and_signatures(self):
        required={"text_at","text_slice","text_index","unicode_ord","unicode_chr"}
        self.assertTrue(required <= SIGNATURES.keys())
        self.assertIn("sdrTextAt", JS_RUNTIME)
        self.assertIn("sdrTextAt", KT_RUNTIME)
        for name, args in (("text_at",["text","1"]),("text_slice",["text","1","2"]),
                           ("text_index",["text","needle"]),("unicode_ord",["char"]),
                           ("unicode_chr",["point"])):
            with self.subTest(name=name):
                self.assertIn("sdr", js_call(name,args))
                self.assertIn("sdr", kt_call(name,args))
        page=generate(TEXT)
        self.assertIn("sdrTextAt", page)
        self.assertIn("sdrTextSlice", page)
        self.assertIn("for (let _sdr_repeat_i=0; _sdr_repeat_i<5;",page)

    @unittest.skipUnless(shutil.which("node"), "Node.js needed for real JS runtime parity")
    def test_python_and_javascript_scalar_differential(self):
        commands = [
            ("text_at",["A😀Б",1]),
            ("text_slice",["e\u0301😀",1,3]),
            ("text_index",["😀A😀","A"]),
            ("unicode_ord",["😀"]),
            ("unicode_chr",[128512]),
        ]
        py_values=[apply(name,args) for name,args in commands]
        script=(JS_RUNTIME + '\nconst outputs = [' +
                ','.join('('+{
                    "text_at":"sdrTextAt",
                    "text_slice":"sdrTextSlice",
                    "text_index":"sdrTextIndex",
                    "unicode_ord":"sdrUnicodeOrd",
                    "unicode_chr":"sdrUnicodeChr",
                }[name]+'('+','.join(json.dumps(arg,ensure_ascii=False) for arg in args)+'))'
                for name,args in commands) + '];\n' +
                "let bad=false;try{sdrTextAt('😀',1);}catch(e){bad=e instanceof RangeError;}outputs.push(bad);process.stdout.write(JSON.stringify(outputs));")
        result=subprocess.run(["node","-e",script],capture_output=True,text=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(json.loads(result.stdout),py_values+[True])

    def test_restricted_repeat_syntax_and_resource_cap(self):
        for loop in ('repeat i in range(0, 101):',
                     'repeat i in range(1, 10):',
                     'repeat i in range(0, sum):',
                     'repeat sum in range(0, 5):',
                     'repeat i in range(0, -1):',
                     'repeat i in range(0, 0):',
                     'repeat i in range(0, 999):',
                     'repeat i in range(0, 5):\n        let i = 3'):
            source=('app "Invalid"\nstate sum = 0\naction calc:\n    ' +
                    loop + ("" if "\n" in loop else '\n        sum = sum + 1'))
            with self.subTest(loop=loop), self.assertRaises(ValueError):
                parse(source)
        too_many = ('app "Nesting"\nstate n = 0\naction calculate:\n'
                    '    repeat i in range(0, 100):\n'
                    '        repeat j in range(0, 100):\n'
                    '            n = n + 1')
        with self.assertRaisesRegex(ValueError,"statement limit"):
            parse(too_many)

    def test_repeat_failure_is_atomic(self):
        p=parse('app "Overflow"\nstate n = 2147483646\n'
                'action fails:\n    repeat i in range(0, 3):\n        n = n + 1')
        initial=p.states.copy()
        with self.assertRaisesRegex(ValueError,"overflow"):
            transition(p,initial,"fails")
        self.assertEqual(initial,p.states)
        p=parse('app "Required"\nstate n = 0\naction fails:\n'
                '    repeat i in range(0, 2):\n        n = n + 1\n        require n < 2')
        initial=p.states.copy()
        with self.assertRaisesRegex(ValueError,"requirement"):
            transition(p,initial,"fails")
        self.assertEqual(initial,p.states)


class BoundedCollectionCore(unittest.TestCase):
    def test_index_slice_clear_and_preserve_stable_ids(self):
        p=parse(LIST)
        self.assertEqual(run(p),4)
        state,_=transition(p,p.states,"add")
        record=state["items"]
        self.assertIsInstance(record,ListValue)
        self.assertEqual(record.next_id,3)
        state,_=transition(p,state,"keep")
        self.assertEqual(state["items"].items[0][0],2)
        self.assertEqual(state["items"].next_id,3)
        state,_=transition(p,state,"empty")
        self.assertEqual(state["items"].items,())
        self.assertEqual(state["items"].next_id,3)

    def test_collection_brackets_and_stable_identity(self):
        source=LIST.replace(
            'test slice: add, keep -> count(items) == 1 and get(items, 2).title == "second"',
            'test slice: add, keep -> count(items) == 1 and items[0].title == "second"'
        ).replace(
            'test select: add, select -> selected == "second"',
            'test select: add, select -> selected == "second" and items[0:2][1].title == "second"'
        )
        program=parse(source)
        self.assertEqual(run(program),4)

    def test_collection_index_bounds_typing_and_rollback(self):
        p=parse(LIST)
        state,_=transition(p,p.states,"add")
        err='app "Bounds"\nrecord R:\n    label: text\nstate records: list<R>(max=2) = []\n'
        for operation in ('list_at(records, 0)',
                          'list_at(records, -1)',
                          'list_slice(records, 0, 1)',
                          'list_slice(records, 1, 0)'):
            with self.subTest(operation=operation), self.assertRaises(ValueError):
                parse(err+'state broken = '+operation)
        for op in ('list_at(records, "0")','list_slice(records, false, 1)',
                   'list_slice(records, 0, "1")','list_clear(0)'):
            with self.subTest(op=op), self.assertRaises(ValueError):
                parse(err+'derive invalid = '+op)


class StructuredErrors(unittest.TestCase):
    def test_typed_diagnostic_and_stable_schema(self):
        value=from_exception(ValueError("Line 4: column 7: type mismatch"),"sample.sdr","check")
        self.assertEqual(value.as_dict(),{
            "code":"SDR-E1001", "phase":"compile", "message":"type mismatch",
            "location":{"source":"sample.sdr","line":4,"column":7}})
        typed=from_exception(
            SedravaError("SDR-E1150","Invalid Unicode index",line=2,column=11),
            "sample.sdr","check")
        self.assertEqual((typed.code,typed.line,typed.column),("SDR-E1150",2,11))
        self.assertEqual(from_exception(OSError("no file"),"x","check").code,"SDR-E3001")
        self.assertEqual(from_exception(AssertionError("failed"),"x","test").phase,"test")
        self.assertEqual(from_exception(ValueError("out of range"),"x","run").phase,"execute")

    def test_runtime_json_diagnostic_phase_and_location(self):
        cli=Path(__file__).resolve().parents[1] / "sedrava_cli.py"
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"runtime.sdr"
            path.write_text('app "Runtime"\nstate title = "😀"\n'
                            'action fail:\n    title = title[1]\n',encoding="utf-8")
            result=subprocess.run([sys.executable,str(cli),"--diagnostics=json","run",
                                   str(path),"fail"],capture_output=True,text=True,timeout=15)
            self.assertEqual(result.returncode,1,result.stderr)
            info=json.loads(result.stderr)
            self.assertEqual(info["phase"],"execute")
            self.assertEqual(info["code"],"SDR-E2001")
            self.assertEqual(info["location"]["line"],4)
            self.assertNotIn("Traceback",result.stderr)

    def test_cli_json_diagnostics_and_default_human_output(self):
        cli=Path(__file__).resolve().parents[1] / "sedrava_cli.py"
        with tempfile.TemporaryDirectory() as directory:
            bad=Path(directory)/"bad.sdr"
            bad.write_text('app "Broken"\nstate number = text_at("A", 9)\n',encoding="utf-8")
            result=subprocess.run([sys.executable,str(cli),"--diagnostics=json","check",str(bad)],
                                  text=True,capture_output=True,timeout=15)
            self.assertEqual(result.returncode,1,result.stderr)
            diag=json.loads(result.stderr)
            self.assertEqual(diag["code"],"SDR-E1001")
            self.assertEqual(diag["location"]["line"],2)
            self.assertEqual(diag["location"]["source"],str(bad))
            self.assertNotIn("Traceback", result.stderr)
            classic=subprocess.run([sys.executable,str(cli),"check",str(bad)],
                                   text=True,capture_output=True,timeout=15)
            self.assertEqual(classic.returncode,1)
            self.assertIn("error:",classic.stderr)
            self.assertNotIn("Traceback",classic.stderr)


if __name__=="__main__":
    unittest.main()
