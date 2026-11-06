"""Real typed error programs, exhaustive checking and cross-target full traces."""
import dataclasses
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from sedrava_core import parse,run,transition
from sedrava_errors import ErrorType,ErrorValue,validate
from sedrava_results import ResultType,ResultValue,validate as validate_result
from sedrava_frontend import parse_document
from sedrava_modules import expand
from sedrava_effects import manifest_for_program
from core_conformance import reference,javascript,kotlin

ROOT=Path(__file__).resolve().parents[1]
EXAMPLE=(ROOT/'examples/typed_errors_012.sdr').read_text()
BASE='''app "Errors"
error closed E:
    First:
        n: int
    Second:
        value: text
fn outcome(x: int) -> Result<int, E> effects pure = Ok(x) if x < 2 else Err(E.First(n=x))
state total = 0
action go:
    match outcome(2):
        Ok(value):
            total = value
        Err(First { n }):
            total = n
        Err(Second { value }):
            total = text_length(value)
screen main:
    value total
test result: go -> total == 2
'''

class TypedErrors(unittest.TestCase):
    def reject(self,source,message=None):
        with self.assertRaisesRegex(ValueError,message or '.'):
            parse(source)

    def test_closed_match_and_immutable_values(self):
        p=parse(BASE);self.assertEqual(run(p),1)
        e=ErrorValue(p.errors['E'],'First',(2,));self.assertEqual(validate(e),e)
        with self.assertRaises(dataclasses.FrozenInstanceError):e.variant='Second'
        self.assertEqual(validate_result(ResultValue(ResultType(int,e.kind),error=e)).error,e)
        for bad in (ErrorValue(e.kind,'First',(True,)),ErrorValue(e.kind,'First',()),ErrorValue(e.kind,'Unknown',())):
            with self.subTest(bad=bad),self.assertRaises(ValueError):validate(bad)
        for bad in (ResultValue(ResultType(int,e.kind),code='INT_OVERFLOW'),ResultValue(ResultType(int,e.kind),1,error=e),ResultValue(ResultType(int),error=e),ResultValue(ResultType(int),1,code=0)):
            with self.subTest(bad=bad),self.assertRaises(ValueError):validate_result(bad)

    def test_scalar_successes_error_fields_and_rollback(self):
        p=parse(EXAMPLE);self.assertEqual(run(p),4)
        rows=reference(EXAMPLE,['success','failure','rejected','success'])
        self.assertEqual(rows[1]['state'],{'total':101,'message':'/offline.txt','ready':True,'entries':{'next_id':3,'items':[{'id':1,'title':'😀 café'},{'id':2,'title':'/offline.txt'}]}})
        self.assertFalse(rows[2]['accepted']);self.assertEqual(rows[1]['state'],rows[2]['state'])
        self.assertEqual(rows[0]['state']['message'],'😀 café')

    def test_javascript_complete_state(self):
        seq=['success','failure','details','adapt','rejected','success'];self.assertEqual(javascript(EXAMPLE,seq),reference(EXAMPLE,seq))

    def test_kotlin_complete_state(self):
        seq=['success','failure','details','adapt','rejected','success'];self.assertEqual(kotlin(EXAMPLE,seq),reference(EXAMPLE,seq))

    def test_missing_closed_variant(self):
        self.reject(BASE.replace('        Err(Second { value }):\n            total = text_length(value)\n',''),'non-exhaustive')

    def test_new_closed_variant_invalidates_match(self):
        self.reject(BASE.replace('fn outcome','    Added:\nfn outcome'),'non-exhaustive')

    def test_open_requires_final_wildcard(self):
        self.reject(BASE.replace('error closed E','error open E'),'open/legacy')

    def test_open_growth_dispatches_to_wildcard(self):
        source=BASE.replace('error closed E','error open E').replace('fn outcome','    Added:\nfn outcome').replace('Err(E.First(n=x))','Err(E.Added())').replace('        Err(Second { value }):\n            total = text_length(value)','        Err(error):\n            total = text_length(error_id(error))').replace('total == 2','total == 13')
        # entry.E.Added has 13 scalar characters.
        self.assertEqual(run(parse(source)),1)
        self.assertEqual(javascript(source,['go']),reference(source,['go']))

    def test_duplicate_and_unreachable_arms(self):
        self.reject(BASE.replace('Err(Second { value })','Err(First { n: value })'),'duplicate|unreachable')
        self.reject(BASE.replace('Err(First { n })','Err(error)').replace('total = n','total = 2'),'unreachable')
        self.reject(BASE.replace('Err(Second { value }):\n            total = text_length(value)','Err(error):\n            total = 1\n        Ok(another):\n            total = another'),'unreachable')
        self.reject(BASE.replace('screen main:','        Err(error):\n            total = 1\nscreen main:'),'unreachable wildcard')

    def test_ok_must_be_handled(self):
        self.reject(BASE.replace('        Ok(value):\n            total = value\n',''),'missing Ok')

    def test_unknown_variant_and_engine_fault(self):
        self.reject(BASE.replace('Err(First { n })','Err(NoSuchVariant { n })'),'unknown error variant')
        self.reject(BASE.replace('Err(First { n })','Err(BudgetExceeded { n })'),'unknown error variant')
        for fault in ('BudgetExceeded','CapabilityDenied','PolicyViolation','CompilerError','InternalError'):
            self.reject(BASE.replace('First',fault),'reserved')

    def test_payload_names_types_and_duplicates(self):
        for expr in ('E.First(n=true)','E.First(n="x")','E.First()','E.First(n=x, extra=2)','E.Unknown(n=x)','E.First(n=x, n=x)','E.First(x)'):
            self.reject(BASE.replace('E.First(n=x)',expr),'E_ERROR_TYPE')
        for declaration in ('    First:\n        n: int\n        n: int','    First:\n        n: list<int>(max=2)','    First:\n    First:','    Ok:'):
            self.reject(BASE.replace('    First:\n        n: int',declaration),'E_ERROR_TYPE')

    def test_field_scope_names_and_immutability(self):
        self.reject(BASE.replace('Err(First { n })','Err(First { absent })'),'unknown')
        self.reject(BASE.replace('Err(First { n })','Err(First { n, n: other })'),'duplicate field')
        self.reject(BASE.replace('total = value\n        Err(First','total = n\n        Err(First'),'Unknown identifier')
        self.reject(BASE.replace('screen main:', '    total = n\nscreen main:'),'Unknown identifier')
        self.reject(BASE.replace('total = n','n = 8'),'invalid assignment')
        self.reject(BASE.replace('Err(First { n })','Err(First { n: total })'),'shadowing')
        self.reject(BASE.replace('total = n','total = text_length(n)'),'type/count')

    def test_result_type_safety_and_no_string_forgery(self):
        self.reject(BASE.replace('Err(E.First(n=x))','Err("INT_OVERFLOW")'),'payload type mismatch')
        self.reject(BASE.replace('Ok(x)','Ok(true)'),'payload type mismatch')
        self.reject(BASE.replace('fn outcome','error closed Other:\n    Different:\nfn outcome').replace('Err(E.First(n=x))','Err(Other.Different())'),'payload type mismatch')
        self.reject(BASE.replace('fn outcome','error closed Other:\n    First:\n        n: int\nfn outcome').replace('Err(E.First(n=x))','Err(Other.First(n=x))'),'payload type mismatch')
        self.reject(BASE.replace('match outcome(2)','match 2'),'match requires Result')
        self.reject(BASE.replace('state total = 0','state total = 0\nderive untyped = Ok(3)'),'contextual')
        self.reject(BASE.replace('total = n','total = text_length(result_code(outcome(n)))'),'legacy-only')
        self.reject(BASE.replace('Result<int, E>','Result<list<E>(max=2), E>'),'return type')

    def test_empty_variants_and_subset_renaming(self):
        source=BASE.replace('    First:\n        n: int','    First:').replace('E.First(n=x)','E.First()').replace('Err(First { n })','Err(First {})').replace('total = n','total = 2')
        self.assertEqual(run(parse(source)),1)
        source=BASE.replace('        n: int','        n: int\n        extra: bool').replace('E.First(n=x)','E.First(n=x, extra=true)').replace('Err(First { n })','Err(First { n: renamed })').replace('total = n','total = renamed')
        self.assertEqual(run(parse(source)),1)

    def test_contextual_parameter_result_and_pure_effects(self):
        source=BASE.replace('state total = 0','fn accept(r: Result<int, E>) -> int effects pure = result_or(r, 3)\nstate total = 0').replace('match outcome(2)','match outcome(accept(Ok(2)))')
        self.assertEqual(run(parse(source)),1)
        self.assertEqual(manifest_for_program(parse(source),source,'web')['effective'],[])
        self.assertEqual(javascript(source,['go']),reference(source,['go']))

    def test_legacy_adapter_only_expected_operations(self):
        source=BASE.replace('    match outcome(2):','    match try_add(2147483647, 1):').replace('        Err(First { n }):\n            total = n\n        Err(Second { value }):\n            total = text_length(value)','        Err(error):\n            match outcome(2):\n                Ok(value):\n                    total = value\n                Err(First { n }):\n                    total = n\n                Err(Second {}):\n                    total = 0')
        self.assertEqual(run(parse(source)),1)
        self.assertEqual(javascript(source,['go']),reference(source,['go']))

    def test_limits_variants_fields_types_text_and_ast(self):
        self.reject(BASE.replace('    First:\n        n: int',''.join('    V'+str(i)+':\n' for i in range(17))),'variant resource')
        self.reject(BASE.replace('        n: int',''.join('        f'+str(i)+': int\n' for i in range(17)).rstrip()),'field resource')
        self.reject(BASE.replace('fn outcome',''.join('error closed X'+str(i)+':\n    V:\n' for i in range(16))+'fn outcome'),'error type resource')
        self.reject(BASE.replace('E.First(n=x)','E.Second(value="'+('x'*1025)+'")'),'1024')
        self.reject(BASE.replace('E.First(n=x)','E.First(n='+('not '*140)+'true)'),'complexity')

    def test_module_execution_positions_privacy_and_identity(self):
        path=ROOT/'examples/typed_errors_modules_012/main.sdr';source=path.read_text();expanded,_=expand(source,path)
        program=parse_document(source,path);self.assertEqual(run(program),2)
        key=expanded.public_symbols['arithmetic.inspect'];seq=['inspect',key]
        self.assertEqual(javascript(expanded,seq,program),reference(expanded,seq))
        ids={x.identity for x in program.errors.values()};self.assertEqual(ids,{'example.ArithmeticError'})
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'errors.sdr').write_text((path.parent/'errors.sdr').read_text().replace('total = left + addend','total = limit_bytes'))
            (root/'main.sdr').write_text(source)
            with self.assertRaisesRegex(ValueError,r'errors.sdr:16:[0-9]+:.*limit_bytes'):
                parse_document(source,root/'main.sdr')
            (root/'errors.sdr').write_text((path.parent/'errors.sdr').read_text().replace('Err(ArithmeticError.IntOverflow(', 'Err(ArithmeticError.Unknown('))
            result=subprocess.run([sys.executable,str(ROOT/'sedrava_cli.py'),'--diagnostics','json','check',str(root/'main.sdr')],capture_output=True,text=True,timeout=20)
            self.assertEqual(result.returncode,1);diagnostic=json.loads(result.stderr)
            self.assertEqual(diagnostic['code'],'SDR-E1201')
            self.assertEqual(diagnostic['location']['source'],str(root/'errors.sdr'))
            self.assertEqual(diagnostic['location']['line'],8)
            self.assertGreater(diagnostic['location']['column'],1)

    def test_module_kotlin_full_states(self):
        path=ROOT/'examples/typed_errors_modules_012/main.sdr';source,_=expand(path.read_text(),path)
        seq=['inspect',source.public_symbols['arithmetic.inspect']]
        self.assertEqual(kotlin(source,seq),reference(source,seq))

    def test_default_ids_are_alias_and_path_independent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/'e.sdr').write_text('module stable.errors\nexport error closed E:\n    V:\nexport fn make(x: int) -> Result<int, E> = Err(E.V())\n')
            for alias in ('first','renamed'):
                source='app "X"\nimport "e.sdr" as '+alias+'\nstate n = 0\nscreen main:\n    value n\n'
                p=parse_document(source,root/'main.sdr');self.assertEqual(next(iter(p.errors.values())).identity,'stable.errors.E')

    def test_engine_overflow_in_error_payload_is_not_caught(self):
        source=BASE.replace('E.First(n=x)','E.First(n=x + 1)').replace('match outcome(2)','match outcome(2147483647)').replace('test result: go -> total == 2','test initial: -> total == 0')
        p=parse(source)
        with self.assertRaisesRegex(ValueError,'overflow'):transition(p,p.states,'go')
        rows=reference(source,['go']);self.assertEqual(rows,[{'accepted':False,'state':{'total':0}}])
        self.assertEqual(javascript(source,['go']),rows)
        self.assertEqual(kotlin(source,['go']),rows)

    def test_unicode_operations_in_arms_are_included_in_work_budget(self):
        source=BASE.replace('state total = 0','fn expensive(x: text) -> text effects pure = unicode_nfd(x)\nstate total = 0')
        source=source.replace('            total = n','            repeat i in range(0, 100):\n                let normalized = expensive("é")\n                total = text_length(normalized)')
        self.reject(source,'weighted work limit')

    def test_open_growth_kotlin_uses_general_branch(self):
        source=BASE.replace('error closed E','error open E').replace('fn outcome','    Added:\nfn outcome').replace('Err(E.First(n=x))','Err(E.Added())').replace('        Err(Second { value }):\n            total = text_length(value)','        Err(error):\n            total = text_length(error_id(error))').replace('total == 2','total == 13')
        self.assertEqual(kotlin(source,['go']),reference(source,['go']))

    def test_duplicate_stable_ids_and_long_variant_are_rejected(self):
        self.reject(BASE.replace('error closed E:', 'error closed Other id "same.id":\n    V:\nerror closed E id "same.id":'),'duplicate stable')
        self.reject(BASE.replace('    First:', '    '+('V'*65)+':'),'variant')
        self.reject(BASE.replace('        n: int', '        '+('f'*65)+': int'),'field')

    def test_module_reserved_error_names_cannot_hide_behind_hygiene(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for name in ('Error','Ok','Err','BudgetExceeded','CapabilityDenied'):
                (root/'m.sdr').write_text('module denied.errors\nexport error closed '+name+':\n    V:\n')
                source='app "X"\nimport "m.sdr" as m\nstate n = 0\nscreen main:\n    value n\n'
                with self.subTest(name=name),self.assertRaisesRegex(ValueError,'error type'):
                    parse_document(source,root/'main.sdr')

    def test_imported_unicode_cost_cannot_escape_via_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            module='module costly.errors\nexport error closed E:\n    V:\nexport fn heavy(x: text) -> text effects pure = unicode_nfd(x)\nexport fn outcome(x: int) -> Result<int, E> = Err(E.V())\nexport state total = 0\nexport action go:\n    repeat i in range(0, 100):\n        match outcome(i):\n            Ok(value):\n                total = value\n            Err(error):\n                let text_value = heavy("é")\n                total = text_length(text_value)\n'
            (root/'m.sdr').write_text(module)
            source='app "X"\nimport "m.sdr" as m\nscreen main:\n    value m.total\n'
            with self.assertRaisesRegex(ValueError,r'm.sdr:7:.*weighted work limit'):
                parse_document(source,root/'main.sdr')

    def test_match_nesting_is_bounded(self):
        body='total = 1'
        for i in range(34):
            body='match outcome(2):\n    Ok(value'+str(i)+'):\n'+''.join('        '+line+'\n' for line in body.splitlines())+'    Err(error'+str(i)+'):\n        total = 0'
        start=BASE.index('    match outcome(2):');end=BASE.index('screen main:')
        self.reject(BASE[:start]+''.join('    '+line+'\n' for line in body.splitlines())+BASE[end:],'nesting limit')

    def test_json_codes_and_imported_source_positions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            source=BASE.replace('Err(Second { value }):\n            total = text_length(value)','Err(Unknown {}):\n            total = 0')
            path=root/'main.sdr';path.write_text(source)
            result=subprocess.run([sys.executable,str(ROOT/'sedrava_cli.py'),'--diagnostics','json','check',str(path)],capture_output=True,text=True,timeout=20)
            self.assertEqual(result.returncode,1);data=json.loads(result.stderr)
            self.assertEqual(data['code'],'SDR-E1203');self.assertEqual(data['phase'],'compile')
            self.assertEqual(data['location']['source'],str(path));self.assertIsInstance(data['location']['line'],int)
            source=BASE.replace('E.First(n=x)','E.First(n=true)');path.write_text(source)
            result=subprocess.run([sys.executable,str(ROOT/'sedrava_cli.py'),'--diagnostics','json','check',str(path)],capture_output=True,text=True,timeout=20)
            self.assertEqual(json.loads(result.stderr)['code'],'SDR-E1201')
            source=BASE.replace('Ok(x)','Ok(true)');path.write_text(source)
            result=subprocess.run([sys.executable,str(ROOT/'sedrava_cli.py'),'--diagnostics','json','check',str(path)],capture_output=True,text=True,timeout=20)
            self.assertEqual(json.loads(result.stderr)['code'],'SDR-E1202')
            # The independent path/column checks for imports run above as well.

    def test_invalid_match_leaves_no_partial_projects(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);path=root/'main.sdr';path.write_text(BASE.replace('Err(First { n })','Err(Missing { n })'))
            for target in ('web','android'):
                output=root/target
                result=subprocess.run([sys.executable,str(ROOT/'sedrava_cli.py'),'build',target,str(path),'--output',str(output)],capture_output=True,text=True,timeout=20)
                self.assertNotEqual(result.returncode,0);self.assertFalse(output.exists())

    def test_int32_minimum_and_scalar_payloads_cross_targets(self):
        for expr,value in [('E.First(n=-2147483648)',-2147483648),('E.Second(value="a😀z"[1:2])',1)]:
            source=BASE.replace('E.First(n=x)',expr).replace('total == 2','total == '+str(value))
            self.assertEqual(run(parse(source)),1)
            rows=reference(source,['go']);self.assertEqual(rows[0]['state']['total'],value)
            self.assertEqual(javascript(source,['go']),rows)
            self.assertEqual(kotlin(source,['go']),rows)

    def test_values_are_not_dynamic_constructor_type_symbols(self):
        self.reject(BASE.replace('    match outcome(2):','    let instance = E.First(n=1)\n    let invalid = instance.First(n=2)\n    match outcome(2):'),'type symbol')
        self.reject(BASE.replace('fn outcome','fn invalid(e: E) -> E effects pure = e.First(n=2)\nfn outcome'),'type symbol')

    def test_untyped_effect_metadata_cannot_claim_an_error_constructor(self):
        import ast
        from sedrava_effects import infer_function_effects
        from sedrava_functions import FunctionType
        kind=parse(BASE).errors['E']
        call=ast.Call(func=ast.Name(id='open',ctx=ast.Load()),args=[],keywords=[])
        call.error_type=kind;call.error_variant='First';call.error_fields=(('n',int),)
        with self.assertRaisesRegex(ValueError,'constructor metadata'):
            infer_function_effects({'forged':FunctionType('forged',(),int,call,1)})

    def test_legacy_record_result_keeps_record_identity(self):
        source="""app "Legacy record Result"
record Entry:
    title: text
state entries: list<Entry>(max=2) = []
state message = ""
action add:
    entries = append(entries, Entry(title="😀"))
action inspect:
    match try_at(entries, 0):
        Ok(record):
            message = record.title
        Err(error):
            message = "empty"
action remove_first:
    entries = list_remove_at(entries, 0)
screen main:
    value message
test scalar: inspect -> message == "empty"
"""
        sequence=['inspect','add','inspect','remove_first','inspect','add','inspect']
        expected=reference(source,sequence)
        self.assertEqual(expected[-1]['state']['entries']['items'][0]['id'],2)
        self.assertEqual(javascript(source,sequence),expected)
        self.assertEqual(kotlin(source,sequence),expected)

    def test_nested_budget_and_scope_remain_checked(self):
        # 100 iterations, each match selects a 100-iteration branch: above 10k steps.
        body='    repeat i in range(0, 100):\n        match outcome(2):\n            Ok(value):\n                total = value\n            Err(error):\n                repeat j in range(0, 100):\n                    total = total + 1\n'
        start=BASE.index('    match outcome(2):');end=BASE.index('screen main:')
        self.reject(BASE[:start]+body+BASE[end:],'statement limit')

if __name__=='__main__':unittest.main()
