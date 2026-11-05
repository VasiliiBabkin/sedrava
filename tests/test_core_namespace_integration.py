import contextlib,io,json,shutil,tempfile,unittest,subprocess
from pathlib import Path
from hashlib import sha256
from unittest.mock import patch
from sedrava_frontend import parse_document
from sedrava_modules import expand
from sedrava_core import parse,transition
from sedrava_cli import main
from sedrava_packages import lock,verify,verified_inputs,read_module
from core_conformance import reference,javascript,kotlin
ROOT=Path(__file__).resolve().parents[1]
EXAMPLE=ROOT/'examples/modules_core_012/main.sdr'
def expanded():return expand(EXAMPLE.read_text(),EXAMPLE)[0]
def actions(program,names):return [next(k for k in program.actions if k.endswith('_'+name)) for name in names]
class Integration(unittest.TestCase):
    def test_full_python_js_kotlin_module_trace(self):
        source=expanded();program=parse(source);seq=actions(program,['scan','add','add','expected','seed','audit','break_rule','reject'])
        expected=reference(source,seq)
        self.assertEqual(expected,javascript(source,seq));self.assertEqual(expected,kotlin(source,seq))
        self.assertFalse(expected[2]['accepted']);self.assertFalse(expected[-1]['accepted'])
        self.assertEqual(expected[-1]['state'],expected[-2]['state'])
    def test_entry_names_do_not_capture_module_local_bindings(self):
        source=EXAMPLE.read_text().replace('state ready = true','state ready = true\nstate index = 0\nstate value = 0\nstate outcome = 0\nstate result = 0\nstate values = 0')
        lowered=expand(source,EXAMPLE)[0];program=parse(lowered)
        state,accepted=transition(program,program.states,actions(program,['scan'])[0])
        self.assertTrue(accepted);self.assertEqual(state['value'],0)
        state,accepted=transition(program,state,actions(program,['expected'])[0]);self.assertTrue(accepted);self.assertEqual(state['outcome'],0)
    def test_legacy_generated_looking_action_name_is_unchanged(self):
        source='app "Legacy"\nstate n = 0\naction M_123456789abc_step: n = n + 1\n'
        program=parse_document(source,self.put('main.sdr',source))
        state,accepted=transition(program,program.states,'M_123456789abc_step');self.assertTrue(accepted);self.assertEqual(state['n'],1)
    def test_imports_shared_by_cli_and_frontend(self):
        p=parse_document(EXAMPLE.read_text(),EXAMPLE)
        self.assertTrue(any(k.endswith('_numbers') for k in p.states))
        with contextlib.redirect_stdout(io.StringIO()):self.assertEqual(main(['test',str(EXAMPLE)]),0)
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
    def put(self,name,text):
        p=self.root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text);return p
    def test_exact_compile_and_runtime_original_columns(self):
        line='export fn longname(xs: list<int>(max=4)) -> int = missing(xs)'
        mod=self.put('math.sdr','module example.math\n'+line+'\n')
        source='app "Map"\nimport "math.sdr" as math\nstate n = 0\n'
        entry=self.put('main.sdr',source)
        error=io.StringIO()
        with contextlib.redirect_stderr(error):self.assertEqual(main(['--diagnostics=json','check',str(entry)]),1)
        location=json.loads(error.getvalue())['location'];self.assertEqual(location,{'source':str(mod),'line':2,'column':line.index('missing')+1})
        line='export fn longname(xs: list<int>(max=4)) -> int = list_sum(xs)'
        mod.write_text('module example.math\n'+line+'\n')
        self.put('bridge.sdr','module example.bridge\nimport \"math.sdr\" as deep\nexport fn longname(xs: list<int>(max=4)) -> int = deep.longname(xs)\n')
        entry.write_text(source.replace('import \"math.sdr\" as math','import \"bridge.sdr\" as math')+'state xs: list<int>(max=4) = [2147483647, 1]\naction fail: n = math.longname(xs)\n')
        error=io.StringIO()
        with contextlib.redirect_stderr(error):self.assertEqual(main(['--diagnostics=json','run',str(entry),'fail']),1)
        diag=json.loads(error.getvalue());self.assertEqual(diag['phase'],'execute');self.assertEqual(diag['location'],{'source':str(mod),'line':2,'column':line.index('list_sum')+1})
    def test_component_substitution_preserves_original_column(self):
        line='    paragraph $text bogus 1'
        module=self.put('ui.sdr','module example.ui\nexport component Panel(text: text):\n'+line+'\n')
        source='site "Map"\nimport "ui.sdr" as ui\npage home at "/":\n    title "Map"\n    heading "Map"\n    use ui.Panel text "A long 😀 replacement"\n'
        with self.assertRaises(ValueError) as err:parse_document(source,self.put('main.sdr',source))
        self.assertEqual(err.exception.source,str(module));self.assertEqual(err.exception.line,3);self.assertEqual(err.exception.column,line.index('bogus')+1)
    def test_import_alias_rename_preserves_snapshot_identity(self):
        from sedrava_records import fingerprint,serialize_state,restore_snapshot
        source=EXAMPLE.read_text();renamed=source.replace('as model','as renamed').replace('model.','renamed.').replace('"renamed.sdr"','"model.sdr"')
        first=parse(expand(source,EXAMPLE)[0]);second=parse(expand(renamed,EXAMPLE)[0])
        self.assertEqual(fingerprint(first),fingerprint(second))
        state,ok=transition(first,first.states,actions(first,['scan'])[0]);self.assertTrue(ok)
        self.assertEqual(restore_snapshot(second,serialize_state(first,state)),state)
    def test_cli_rejects_wrong_mode_without_output_and_reports_package_json(self):
        entry=self.put('main.sdr','app "App"\nstate n = 0\nscreen main:\n    value n\n');output=self.root/'wrong'
        for target in ('site','webapp'):
            with contextlib.redirect_stderr(io.StringIO()):self.assertEqual(main(['build',target,str(entry),'--output',str(output)]),1)
            self.assertFalse(output.exists())
        err=io.StringIO()
        with contextlib.redirect_stderr(err):self.assertEqual(main(['--diagnostics=json','verify',str(self.root)]),1)
        self.assertEqual(json.loads(err.getvalue())['location']['source'],str(self.root/'sedrava.lock'))
    def test_diagnostics_do_not_match_identifiers_inside_literals(self):
        line='export fn bad() -> text = concat("missing", missing)'
        module=self.put('m.sdr','module example.map\n'+line+'\n');source='app "Map"\nimport "m.sdr" as m\n'
        with self.assertRaises(ValueError) as err:parse_document(source,self.put('main.sdr',source))
        self.assertEqual(err.exception.source,str(module));self.assertEqual(err.exception.column,line.rindex('missing')+1)
    def test_outputs_cannot_replace_imported_source_or_its_directory(self):
        module=self.put('lib/m.sdr','module example.protected\nexport fn safe(x: int) -> int = x\n')
        entry=self.put('main.sdr','app "Safe"\nimport "lib/m.sdr" as m\nstate n = 0\nscreen main:\n    value n\n');before=module.read_bytes()
        for target,output in [('web',module),('android',module.parent)]:
            with contextlib.redirect_stderr(io.StringIO()):self.assertEqual(main(['build',target,str(entry),'--output',str(output)]),1)
            self.assertEqual(module.read_bytes(),before);self.assertEqual(sorted(p.name for p in module.parent.iterdir()),['m.sdr'])
    def test_cli_runs_qualified_exported_action(self):
        stdout=io.StringIO()
        with contextlib.redirect_stdout(stdout):self.assertEqual(main(['run',str(EXAMPLE),'model.scan']),0)
        state=json.loads(stdout.getvalue());self.assertEqual(next(v for k,v in state.items() if k.endswith('_total')),6)
        with contextlib.redirect_stderr(io.StringIO()):self.assertEqual(main(['run',str(EXAMPLE),actions(parse(expanded()),['scan'])[0]]),1)
    def test_module_scope_is_checked_before_initial_evaluation(self):
        import sedrava_unicode
        self.put('m.sdr','module example.scope\nexport derive stolen = unicode_nfc(secret)\n')
        source='app "Scope"\nimport "m.sdr" as m\nstate secret = "é"\n'
        with patch('sedrava_unicode.normalize',wraps=sedrava_unicode.normalize) as normalize_call:
            with self.assertRaisesRegex(ValueError,'cannot capture entry state'):parse_document(source,self.put('main.sdr',source))
            self.assertEqual(normalize_call.call_count,0)
    def test_module_initial_invariant_keeps_original_location(self):
        module=self.put('m.sdr','module example.rule\nexport state label = "é"\nrule unicode_nfc(label) == label\n')
        source='app "Rule"\nimport "m.sdr" as m\n'
        with self.assertRaisesRegex(ValueError,'Invalid initial state') as err:parse_document(source,self.put('main.sdr',source))
        self.assertEqual(err.exception.source,str(module));self.assertEqual(err.exception.line,3);self.assertEqual(err.exception.column,6)
    def test_legacy_import_cannot_escape_namespaced_privacy(self):
        hidden='M_'+sha256(b'example.hidden').hexdigest()[:12]+'_secret'
        self.put('m.sdr','module example.hidden\nfn secret(x: int) -> int = x+1\nexport fn safe(x: int) -> int = x\n')
        self.put('legacy.sdr','fn steal(x: int) -> int = '+hidden+'(x)\n')
        source='app "Mixed"\nimport "m.sdr" as m\nimport "legacy.sdr"\n'
        with self.assertRaisesRegex(ValueError,'Reserved generated'):parse_document(source,self.put('main.sdr',source))
    def test_module_component_can_bind_its_private_state_and_action(self):
        self.put('m.sdr','module example.private\nstate count = 0\nstate values: list<int>(max=1) = []\npersist count\naction bump: count = count + 1\nexport component Panel:\n    value count\n    button "Private" -> bump\n')
        source='app "Private"\nimport "m.sdr" as m\nscreen main:\n    use m.Panel\n';entry=self.put('main.sdr',source);lowered=expand(source,entry)[0];program=parse(lowered)
        sequence=actions(program,['bump']);expected=reference(lowered,sequence)
        self.assertEqual(expected,javascript(lowered,sequence));self.assertEqual(expected,kotlin(lowered,sequence))
        with self.assertRaisesRegex(ValueError,'not an exported'):parse_document(source.replace('use m.Panel','button "No" -> m.bump'),entry)
    def test_lock_integer_resource_bound(self):
        self.project();path=self.root/'sedrava.lock';path.write_text('{"schema":'+('9'*5000)+'}')
        with self.assertRaisesRegex(ValueError,'Invalid sedrava.lock JSON'):verify(self.root)
    def test_aggregate_module_source_budget(self):
        for name in ('a','b'):self.put(name+'.sdr','module example.'+name+'\n'+('#'+('x'*60000))+'\nexport fn safe(x: int) -> int = x\n')
        source='app "Budget"\nimport "a.sdr" as a\nimport "b.sdr" as b\n'
        with self.assertRaisesRegex(ValueError,'Combined module source resource limit'):parse_document(source,self.put('main.sdr',source))
    def test_nested_component_reference_reports_call_argument(self):
        self.put('ui.sdr','module example.arguments\ncomponent Inner(value: ref):\n    value $value\nexport component Panel(value: ref):\n    use Inner value $value\n')
        line='    use ui.Panel value missing'
        source='app "Arguments"\nimport "ui.sdr" as ui\nscreen main:\n'+line+'\n';entry=self.put('main.sdr',source)
        with self.assertRaises(ValueError) as err:parse_document(source,entry)
        self.assertEqual(err.exception.source,str(entry));self.assertEqual(err.exception.line,4);self.assertEqual(err.exception.column,line.index('missing')+1)
    def test_ui_component_cannot_inject_domain_statements(self):
        module=self.put('ui.sdr','module example.boundary\nexport component Bad:\n    n = n + 1\n')
        source='app "Boundary"\nimport "ui.sdr" as ui\nstate n = 0\naction unsafe:\n    use ui.Bad\n';entry=self.put('main.sdr',source)
        with self.assertRaisesRegex(ValueError,'UI components cannot emit domain') as err:parse_document(source,entry)
        self.assertEqual(err.exception.source,str(module));self.assertEqual(err.exception.line,3)
    def test_ui_slot_cannot_be_used_as_an_action_macro(self):
        self.put('ui.sdr','module example.slot\nexport component Identity:\n    slot\n')
        source='app "Boundary"\nimport "ui.sdr" as ui\nstate n = 0\naction unsafe:\n    use ui.Identity:\n        n = n + 1\n';entry=self.put('main.sdr',source)
        with self.assertRaisesRegex(ValueError,'UI components cannot emit domain') as err:parse_document(source,entry)
        self.assertEqual(err.exception.source,str(entry));self.assertEqual(err.exception.line,6)
    def test_module_action_cannot_capture_entry_state(self):
        self.put('m.sdr','module example.model\nexport action steal:\n    private_data = 9\n')
        source='app "Scope"\nimport "m.sdr" as m\nstate private_data = 0\n'
        with self.assertRaisesRegex(ValueError,'cannot capture entry state'):parse_document(source,self.put('main.sdr',source))
    def test_nested_import_cost_cannot_escape_budget(self):
        fns='fn f0(x: int) -> int = x + x\n'+''.join('fn f'+str(i)+'(x: int) -> int = f'+str(i-1)+'(x) + f'+str(i-1)+'(x)\n' for i in range(1,6))
        self.put('deep.sdr','module example.deep\n'+fns+'export fn costly(x: int) -> int = f5(x)\n')
        self.put('m.sdr','module example.model\nimport "deep.sdr" as d\nexport state n = 0\nexport action spend:\n    repeat i in range(0, 99):\n        repeat j in range(0, 99):\n            n = d.costly(1)\n')
        source='app "Cost"\nimport "m.sdr" as m\n'
        with self.assertRaisesRegex(ValueError,'weighted work limit'):parse_document(source,self.put('main.sdr',source))
    def test_generated_private_names_and_nfkc_bypass_reject(self):
        hidden='M_'+sha256(b'example.secret').hexdigest()[:12]+'_hidden'
        for name in (hidden,hidden.replace('M','Ｍ')):
            self.put('m.sdr','module example.attack\nexport fn attack(x: int) -> int = '+name+'(x)\n')
            source='app "Scope"\nimport "m.sdr" as m\n'
            with self.assertRaises(ValueError):parse_document(source,self.put('main.sdr',source))
    def project(self):
        self.put('sedrava.toml','[package]\nname="example.app"\nversion="1.0.0"\n[dependencies]\n"example.lib"={path="vendor/example.lib",version="1.0.0"}\n')
        self.put('vendor/example.lib/sedrava.toml','[package]\nname="example.lib"\nversion="1.0.0"\n')
        module=self.put('vendor/example.lib/lib.sdr','module example.lib\nexport fn safe(x: int) -> int = x\n');lock(self.root);return module
    def test_lock_types_and_no_partial_oversized_write(self):
        self.project();path=self.root/'sedrava.lock';original=path.read_text();path.write_text(original.replace('"schema": 1','"schema": true'))
        with self.assertRaises(ValueError):verify(self.root)
        path.write_text(original)
        with patch('sedrava_packages.snapshot',return_value={'huge':'x'*128001}),self.assertRaisesRegex(ValueError,'resource limit'):lock(self.root)
        self.assertEqual(path.read_text(),original)
    def test_unlocked_vendor_and_changed_bytes_reject(self):
        module=self.project();entry=self.put('main.sdr','app "Locked"\n');verified=verified_inputs(entry)
        module.write_text(module.read_text().replace('= x','= x + 1'))
        with self.assertRaisesRegex(ValueError,'changed after lock'):read_module(module,self.root,verified)
        other=self.put('vendor/other.sdr','module other.lib\nexport fn safe(x: int) -> int = x\n')
        with self.assertRaisesRegex(ValueError,'not covered'):read_module(other,self.root,verified)
