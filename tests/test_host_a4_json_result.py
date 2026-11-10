"""A4 typed JSON lookup: Host Result/Match integration and offline safeguards."""
import json
import os
import tempfile
import unittest

from sedrava_host import parse_host, run_host
from sedrava_host_effects import infer_host_effects
from sedrava_host_json import HostJsonLookupFailure, loads, lookup
from sedrava_host_json_typed import (
    HOST_JSON_LOOKUP_ERROR, HOST_JSON_LOOKUP_RESULT, lookup_text_result,
)
from sedrava_host_protocol import execute_protocol, PROTOCOL


PROGRAM = '''host "Typed JSON field"
arg config: json
try_json_get_text title from config at "title"
match title:
    Ok(text):
        emit text
    Err(MissingKey {}):
        emit "missing"
    Err(InvalidIndex {}):
        emit "invalid_index"
    Err(UnexpectedType {}):
        emit "wrong_type"
'''

ARRAY_PROGRAM = '''host "Typed JSON array"
arg items: json
arg index: int
try_json_get_text picked from items at index
match picked:
    Ok(text):
        emit text
    Err(MissingKey {}):
        emit "missing"
    Err(InvalidIndex {}):
        emit "invalid_index"
    Err(UnexpectedType {}):
        emit "wrong_type"
'''


class JsonResultPureChecks(unittest.TestCase):
    def test_nominal_identity_and_expected_variants(self):
        self.assertEqual(HOST_JSON_LOOKUP_ERROR.identity, "sedrava.host.json.lookup.v1")
        self.assertFalse(HOST_JSON_LOOKUP_ERROR.opened)
        self.assertEqual(
            tuple(dict(HOST_JSON_LOOKUP_ERROR.variants)),
            ("MissingKey", "InvalidIndex", "UnexpectedType"),
        )
        cases = [
            ('{"title":"ready"}', "title", None, "ready"),
            ('{"no-title":"ready"}', "title", "MissingKey", None),
            ('["first"]', 3, "InvalidIndex", None),
            ('["first"]', "0", "InvalidIndex", None),
            ('{"title":42}', "title", "UnexpectedType", None),
            ('{"title":null}', "title", "UnexpectedType", None),
            ('{"title":true}', "title", "UnexpectedType", None),
            ('42', "title", "UnexpectedType", None),
            ('{"title":"ok"}', 0, "UnexpectedType", None),
        ]
        for raw, key, error, value in cases:
            with self.subTest(raw=raw, key=key):
                outcome = lookup_text_result(loads(raw), key)
                self.assertEqual(outcome.kind, HOST_JSON_LOOKUP_RESULT)
                self.assertEqual(outcome.error.variant if outcome.error else None, error)
                self.assertEqual(outcome.value, value)
                if outcome.error:
                    self.assertEqual(outcome.error.values, ())
                    self.assertEqual(outcome.error.kind.identity, HOST_JSON_LOOKUP_ERROR.identity)

    def test_bad_operands_remain_engine_errors(self):
        with self.assertRaises(ValueError):
            lookup_text_result({"title": "unsafe"}, "title")
        with self.assertRaises(ValueError):
            lookup_text_result(loads('{"title":"ok"}'), True)

    def test_original_json_get_is_unchanged(self):
        self.assertEqual(lookup(loads('{"title":"ok"}'), "title", str), "ok")
        with self.assertRaises(HostJsonLookupFailure):
            lookup(loads('{"title":9}'), "title", str)


@unittest.skipUnless(os.name == "posix", "trusted Host runtime requires POSIX")
class HostJsonA4Integration(unittest.TestCase):
    def run_case(self, source, *args, expected):
        with tempfile.TemporaryDirectory() as root:
            program = parse_host(source)
            self.assertFalse(program.needs_read)
            self.assertFalse(program.needs_write)
            self.assertEqual(infer_host_effects(program), frozenset())
            output = run_host(program, root=root, supplied=args, trusted=True)
            self.assertEqual(output["result"], expected)
            self.assertIsNone(output["written"])

    def test_success_and_expected_errors(self):
        for raw, expected in [
            ('{"title":"Hello"}', "Hello"),
            ('{"title":3}', "wrong_type"),
            ('{"other":"Hello"}', "missing"),
            ('[]', "wrong_type"),
        ]:
            with self.subTest(raw=raw):
                self.run_case(PROGRAM, "config="+raw, expected=expected)

    def test_array_and_index(self):
        self.run_case(ARRAY_PROGRAM, 'items=["one","two"]', 'index=1', expected="two")
        self.run_case(ARRAY_PROGRAM, 'items=["one"]', 'index=1', expected="invalid_index")
        self.run_case(ARRAY_PROGRAM, 'items=["one"]', 'index=-1', expected="invalid_index")
        self.run_case(ARRAY_PROGRAM, 'items=["one"]', 'index=0', expected="one")

    def test_match_patterns_are_checked_statically(self):
        cases = (
            PROGRAM.replace("Err(InvalidIndex {}):", "Err(MissingKey {}):"),
            PROGRAM.replace('    Err(UnexpectedType {}):\n        emit "wrong_type"\n', ''),
            PROGRAM.replace("Err(UnexpectedType {}):", "Err(NotDeclared {}):"),
            PROGRAM.replace("Err(MissingKey {}):", "Err(MissingKey { unknown }):"),
            PROGRAM.replace('emit "Hello"', 'emit "Hello"'),
            PROGRAM.replace("try_json_get_text title from config", "try_json_get_text config from config"),
            PROGRAM.replace("try_json_get_text title from config", "try_json_get_text title from missing"),
        )
        for value in cases:
            if value == PROGRAM:
                continue
            with self.subTest(source=value), self.assertRaises(ValueError):
                parse_host(value)
        with self.assertRaises(ValueError):
            parse_host(PROGRAM + "emit 1\n")

    def test_malformed_json_and_budget_remain_rejected_not_expected(self):
        with tempfile.TemporaryDirectory() as root:
            program = parse_host(PROGRAM)
            outcome = execute_protocol(program, root=root, supplied=('config={"title":1,"title":2}',),
                                       trusted=True)
            self.assertEqual(outcome["protocol"], PROTOCOL)
            self.assertEqual(outcome["status"], "rejected")
            self.assertEqual(outcome["error"]["code"], "CONFIGURATION_REJECTED")
            huge = 'x' * 5000
            outcome = execute_protocol(program, root=root, supplied=('config='+json.dumps({"title": huge}),),
                                       trusted=True)
            self.assertEqual(outcome["status"], "rejected")

    def test_protocol_is_successful_on_caught_error_without_leaking_json(self):
        with tempfile.TemporaryDirectory() as root:
            outcome = execute_protocol(parse_host(PROGRAM), root=root,
                                       supplied=('config={"private":"do-not-print"}',), trusted=True)
            self.assertEqual(outcome["status"], "success")
            self.assertEqual(outcome["result"]["result"], "missing")
            self.assertNotIn("do-not-print", json.dumps(outcome))

    def test_permission_gate_and_legacy_behavior(self):
        with tempfile.TemporaryDirectory() as root:
            outcome = execute_protocol(parse_host(PROGRAM), root=root, supplied=('config={"title":"ok"}',),
                                       trusted=False)
            self.assertEqual(outcome["status"], "rejected")
            old = '''host "Legacy JSON"
arg config: json
json_get_text title from config at "title"
emit title
'''
            self.assertEqual(run_host(parse_host(old), root=root, supplied=('config={"title":"old"}',),
                                      trusted=True)["result"], "old")

    def test_invalid_arg_and_result_names(self):
        for source in (
            PROGRAM.replace('at "title"', 'at true'),
            PROGRAM.replace('arg config: json', 'arg config: text'),
            PROGRAM.replace('try_json_get_text title from config at "title"',
                            'json_get_text title from config at "title"'),
        ):
            with self.subTest(source=source), self.assertRaises(ValueError):
                parse_host(source)


if __name__ == "__main__":
    unittest.main()
