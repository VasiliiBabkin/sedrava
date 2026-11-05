import json
from pathlib import Path
import subprocess
import unittest
from sedrava_webapp import parse_webapp
from sedrava_web_routes import resolve_route
from sedrava_web_queries import query_rows, QUERY_JS

ROOT=Path(__file__).resolve().parents[1]
class Routes(unittest.TestCase):
    def test_missing_record_does_not_apply_route_parameter(self):
        doc=parse_webapp((ROOT/'examples/platform_tasks.sdr').read_text())
        before=doc.program.states.copy()
        self.assertIsNone(resolve_route(doc,'/tasks/99',before))
        self.assertEqual(before,doc.program.states)
        self.assertEqual(resolve_route(doc,'/',before)[0],'main')

    def test_invalid_targets_and_parameter_types(self):
        source=(ROOT/'examples/platform_tasks.sdr').read_text()
        for old,new in [('to details','to unknown'),(':selected',':new_title'),('when chosen:','when task_count:')]:
            with self.assertRaises(ValueError):parse_webapp(source.replace(old,new))

    def test_python_javascript_query_full_identity_and_order(self):
        rows=[{'id':1,'title':'😀','done':True},{'id':2,'title':'Zoo','done':False},{'id':3,'title':'apple','done':True},{'id':4,'title':'\uffff','done':True}]
        cases=[{'search':'','title':'title','sort':'title','where':None,'equals':False,'active':True},
               {'search':'APP','title':'title','sort':'title','where':'done','equals':True,'active':True},
               {'search':'','title':'title','sort':None,'where':'done','equals':False,'active':False}]
        expected=[query_rows(rows,**case) for case in cases]
        script=QUERY_JS+'\nconsole.log(JSON.stringify('+json.dumps(cases)+'.map(c=>queryRows('+json.dumps(rows)+',c))));'
        result=subprocess.run(['node','-e',script],capture_output=True,text=True,check=True)
        self.assertEqual(json.loads(result.stdout),expected)

    def test_each_templates_have_checked_fields_and_row_scopes(self):
        source=(ROOT/'examples/platform_tasks.sdr').read_text()
        for old,new in [('field title','field missing'),('row-when done','row-when title'),('pick "Select"','input new_title label "Nested"')]:
            with self.assertRaises(ValueError):parse_webapp(source.replace(old,new))

    def test_select_types_and_dialog_targets(self):
        source=(ROOT/'examples/platform_tasks.sdr').read_text()
        for old,new in [('value false','value "false"'),('to confirm_delete','to missing')]:
            with self.assertRaises(ValueError):parse_webapp(source.replace(old,new))

    def test_route_parameters_are_atomic_and_patterns_unambiguous(self):
        source='webapp "Pairs"\nstate a=0\nstate b=0\nrule a==b\nview main:\n    heading "Home"\nview pair at "/pair/:a/:b":\n    heading "Pair"\n    value a label "A"\n    value b label "B"\n'
        doc=parse_webapp(source);before=doc.program.states.copy()
        self.assertEqual(resolve_route(doc,'/pair/3/3',before)[1],{'a':3,'b':3})
        self.assertIsNone(resolve_route(doc,'/pair/3/4',before));self.assertEqual(before,{'a':0,'b':0})
        for suffix in ['view other at "/pair/:b/:a":\n    heading "Other"\n','view other at "/pair/3/3":\n    heading "Other"\n']:
            with self.assertRaisesRegex(ValueError,'overlapping'):parse_webapp(source+suffix)
