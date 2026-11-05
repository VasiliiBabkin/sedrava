"""Cross-target A1 audit and A2 resource/range regressions, no emulation of adapters."""
import unittest
from unittest.mock import patch
from sedrava_core import parse,run,transition
from core_conformance import reference,javascript,kotlin
SOURCE='''app "Core audit"
record Row:
    title: text
state rows: list<Row>(max=3) = []
state total = 0
state text = "A😀éБ"
persist rows
persist text
persist total
action seed:
    rows = append(rows, Row(title="first"))
    rows = append(rows, Row(title="second"))
action inspect:
    text = text[1:4]
    total = unicode_ord(text[0])
action retain:
    rows = rows[1:2]
action clear:
    rows = list_clear(rows)
action range_edges:
    repeat i in range(-2147483648, 2147483647, 2147483647):
        total = i
action reverse:
    repeat i in range(4, -1, -2):
        total = total + i
action empty:
    repeat i in range(0, -1):
        total = 99
action fail_index:
    total = total + 1
    text = text[1024]
action fail_overflow:
    total = 2147483647
    repeat i in range(1, 3):
        total = total + i
screen main:
    value total
    value text
    button "Seed" -> seed
    button "Inspect" -> inspect
'''
SEQUENCE=['fail_index','seed','inspect','range_edges','fail_overflow','retain','reverse','empty','clear','retain']
class BoundedAudit(unittest.TestCase):
    def test_expanded_unicode_derived_work_is_bounded(self):
        source='app "Cost"\nstate text = "é"\nderive a = unicode_nfc(text)\n'
        for i in range(1,6):source+='derive a'+str(i)+' = concat('+('a' if i==1 else 'a'+str(i-1))+', '+('a' if i==1 else 'a'+str(i-1))+')\n'
        source+='screen main:\n    value text\n'
        with self.assertRaisesRegex(ValueError,'work limit'):parse(source)
    def test_actual_javascript_complete_state_trace(self):self.assertEqual(javascript(SOURCE,SEQUENCE),reference(SOURCE,SEQUENCE))
    def test_actual_kotlin_complete_state_trace(self):self.assertEqual(kotlin(SOURCE,SEQUENCE),reference(SOURCE,SEQUENCE))
    def test_weighted_calls_inside_nested_loops_are_rejected(self):
        functions='fn f0(x: int) -> int = x + x\n'+''.join('fn f'+str(i)+'(x: int) -> int = f'+str(i-1)+'(x) + f'+str(i-1)+'(x)\n' for i in range(1,6))
        source='app "Work"\n'+functions+'state n = 0\naction calculate:\n    repeat i in range(0, 99):\n        repeat j in range(0, 99):\n            n = f5(1)\n'
        with self.assertRaisesRegex(ValueError,'weighted work limit'):parse(source)
    def test_runtime_fuel_cannot_partially_commit_on_any_backend(self):
        p=parse(SOURCE)
        with patch('sedrava_cost.MAX_ACTION_WORK',1):
            with self.assertRaisesRegex(ValueError,'execution work limit'):transition(p,p.states,'seed')
            expected=[{'accepted':False,'state':{'rows':{'next_id':1,'items':[]},'total':0,'text':'A😀éБ'}}]
            self.assertEqual(javascript(SOURCE,['seed'],p),expected)
            self.assertEqual(kotlin(SOURCE,['seed'],p),expected)
    def test_expanded_literal_ranges_are_strict_and_bounded(self):
        for expression in ('range(0, 3, 0)','range(0, 1000)','range(-2147483649, 0)','range(0, 3, true)','range(0, total)'):
            with self.subTest(expression=expression),self.assertRaises(ValueError):parse(SOURCE.replace('range(4, -1, -2)',expression))
        self.assertEqual(reference(SOURCE,['empty'])[0]['state']['total'],0)
