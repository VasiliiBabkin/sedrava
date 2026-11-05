import unittest
from sedrava_core import parse
from core_conformance import reference,javascript,kotlin
SOURCE='''app "Expected errors"
fn safe(x: int, y: int) -> Result<int, Error> = try_add(x, y)
fn fallback(r: Result<int, Error>, value: int) -> int = result_or(r, value)
state values: list<int>(max=2) = [9]
state number = 0
state text = ""
state code = ""
state success = false
action overflow:
    let result = safe(2147483647, 1)
    success = result_ok(result)
    code = result_code(result)
    number = fallback(result, 42)
action index:
    let result = try_at(values, 3)
    number = result_or(result, 7)
    code = result_code(result)
action scalar:
    let result = try_chr(55296)
    text = result_or(result, "invalid")
    code = result_code(result)
action good:
    let result = try_at("A😀Б", 1)
    text = result_or(result, "missing")
    success = result_ok(result)
    code = result_code(result)
action engine_failure:
    number = 99
    let result = try_add(1, 2147483647 + 1)
    number = result_or(result, 0)
screen main:
    value number
    value text
    value code
    button "Try" -> overflow
'''
class Results012(unittest.TestCase):
    def test_full_state_all_platforms(self):
        seq=['overflow','index','scalar','good','engine_failure'];expected=reference(SOURCE,seq)
        self.assertEqual(expected,javascript(SOURCE,seq));self.assertEqual(expected,kotlin(SOURCE,seq))
        self.assertEqual([x['state']['code'] for x in expected],['INT_OVERFLOW','INDEX_BOUNDS','INVALID_SCALAR','',''])
        self.assertFalse(expected[-1]['accepted']);self.assertEqual(expected[-1]['state']['number'],7)
    def test_no_implicit_unwrap_or_persisted_result(self):
        for old,new in [('number = fallback(result, 42)','number = result'),('number = fallback(result, 42)','number = result_or(result, true)'),('state number = 0','state number = try_add(1, 2)')]:
            with self.subTest(new=new),self.assertRaises(ValueError):parse(SOURCE.replace(old,new))
