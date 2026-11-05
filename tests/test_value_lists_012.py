import json,unittest
from sedrava_core import parse,transition,run
from sedrava_records import plain,serialize_state,restore_snapshot,fingerprint
from core_conformance import reference,javascript,kotlin
SOURCE='''app "Bounded values"
record Row:
    name: text
fn doubled(x: int) -> int = x * 2
fn raised(xs: list<int>(max=4)) -> list<int>(max=4) = append(xs, 9)
state values: list<int>(max=4) = [3, 1, 2]
state words: list<text>(max=4) = ["😀", "é", "Б", "𐀀"]
state flags: list<bool>(max=3) = [true, false]
state rows: list<Row>(max=3) = []
state total = 0
state found = -1
state text = ""
persist values
persist words
persist flags
persist rows
persist total
action scan:
    total = 0
    for index, value in values:
        total = total + value
        values = list_replace_at(values, index, doubled(value))
    for char in "A😀Б":
        text = concat(text, char)
action order:
    values = list_sort(values)
    words = list_sort(words)
    found = list_index(words, "😀")
    flags = list_replace_at(flags, 1, true)
action remove:
    values = list_remove_at(values, 1)
    values = values[0:2]
action add:
    values = raised(values)
action fail_bounds:
    total = 100
    values = list_remove_at(values, 99)
action fail_sum:
    values = [2147483647, 1]
    total = list_sum(values)
action seed_rows:
    rows = append(rows, Row(name="same"))
    rows = append(rows, Row(name="same"))
    rows = list_replace_at(rows, 0, Row(name="new"))
action delete_rows:
    let snapshot = rows
    for index, row in snapshot:
        rows = remove(rows, list_identity(snapshot, index))
action clear:
    values = list_clear(values)
    words = list_clear(words)
screen main:
    value total
    value found
    value text
    button "Scan" -> scan
'''
SEQUENCE=['scan','order','fail_bounds','fail_sum','remove','add','add','seed_rows','delete_rows','clear','scan']
class ValueLists(unittest.TestCase):
    def test_seeded_bounded_sequences_all_targets(self):
        import random
        rng=random.Random(1202)
        seq=[rng.choice(SEQUENCE) for _ in range(64)]
        expected=reference(SOURCE,seq)
        self.assertEqual(expected,javascript(SOURCE,seq))
        self.assertEqual(expected,kotlin(SOURCE,seq))
    def test_python_bounds_identity_snapshot_iteration_and_persistence(self):
        p=parse(SOURCE);states=reference(SOURCE,SEQUENCE)
        self.assertEqual(states[0]['state']['values'],[6,2,4]);self.assertEqual(states[0]['state']['total'],6)
        self.assertEqual(states[0]['state']['text'],'A😀Б')
        self.assertEqual(states[2]['state'],states[1]['state']);self.assertFalse(states[2]['accepted']);self.assertFalse(states[3]['accepted'])
        self.assertEqual(states[7]['state']['rows'],{'next_id':3,'items':[{'id':1,'name':'new'},{'id':2,'name':'same'}]})
        self.assertEqual(states[8]['state']['rows'],{'next_id':3,'items':[]})
        state,_=transition(p,p.states,'scan');self.assertEqual(restore_snapshot(p,serialize_state(p,state))['values'],state['values'])
        saved=json.loads(serialize_state(p,state))
        for values in ([True],[1.0],[1,2,3,4,5],{'items':[]}):
            bad={**saved,'state':{**saved['state'],'values':values}}
            with self.subTest(values=values),self.assertRaises(ValueError):restore_snapshot(p,json.dumps(bad))
    def test_javascript_full_trace(self):self.assertEqual(javascript(SOURCE,SEQUENCE),reference(SOURCE,SEQUENCE))
    def test_kotlin_full_trace(self):self.assertEqual(kotlin(SOURCE,SEQUENCE),reference(SOURCE,SEQUENCE))
    def test_strict_type_and_capacity_contract(self):
        for source in ('state a: list<int>(max=2) = [true]','state a: list<text>(max=2) = [1]','state a: list<int>(max=0) = []','state a: list<int>(max=2) = [1,2,3]','state a: list<list>(max=2) = []'):
            with self.subTest(source=source),self.assertRaises(ValueError):parse('app "Invalid"\n'+source)
        for expr in ('append(values, true)','list_sum(words)','get(values, 1)','list_identity(values, 0)','list_replace_at(values, 0, "bad")'):
            with self.subTest(expr=expr),self.assertRaises(ValueError):parse(SOURCE.replace('total = list_sum(values)','total = '+expr))
