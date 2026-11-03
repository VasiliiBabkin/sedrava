"""Cross-collection invariants also protect restored offline application data."""
import json
from pathlib import Path
import unittest
from sedrava_core import edit_state,transition,parse
from sedrava_frontend import parse_document
from sedrava_records import serialize_state,restore_snapshot
ROOT=Path(__file__).resolve().parents[1]
class Relations(unittest.TestCase):
    def test_dangling_foreign_record_rejects_restore_without_partial_apply(self):
        path=ROOT/'examples/platform_crm.sdr';program=parse_document(path.read_text(),path).program
        state=program.states.copy()
        for key,value in [('company_name','Acme')]:state,ok=edit_state(program,state,key,value);self.assertTrue(ok)
        state,ok=transition(program,state,'add_company');self.assertTrue(ok)
        for key,value in [('company_id',1),('contact_name','Ada'),('email','ada@example.com')]:state,ok=edit_state(program,state,key,value);self.assertTrue(ok)
        state,ok=transition(program,state,'add_contact');self.assertTrue(ok)
        raw=serialize_state(program,state);saved=json.loads(raw);saved['state']['contacts']['items'][0]['company']=99
        with self.assertRaises(ValueError):restore_snapshot(program,json.dumps(saved))
        self.assertEqual(serialize_state(program,state),raw)
        self.assertEqual(restore_snapshot(program,raw)['contacts'],state['contacts'])
        with self.assertRaises(ValueError):transition(program,state,'delete_company')
    def test_function_collection_capacities_and_record_types_are_exact(self):
        source=(ROOT/'tests/fixtures/platform_logic.sdr').read_text()
        for old,new in [('pool: list<Item>(max=8)','pool: list<Item>(max=7)'),('pool: list<Item>(max=8)','pool: list<Item>'),('pool: list<Item>(max=8)','pool: list<Label>(max=8)'),('-> list<Item>(max=8)','-> list<Item>(max=0)')]:
            with self.subTest(new=new),self.assertRaises(ValueError):parse(source.replace(old,new))
