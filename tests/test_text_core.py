"""First-class text grammar, scalar semantics, transitions, persistence and CLI."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from sedrava_core import (checked_text, edit_state, evaluate, parse, parse_expr,
                          resolve, restore_state, run, transition, valid_state)

ROOT = Path(__file__).resolve().parents[1]
PROFILE = (ROOT / 'examples/text_profile.sdr').read_text(encoding='utf-8')


def literal(value):
    return json.dumps(value, ensure_ascii=False)


class TextCore(unittest.TestCase):
    def test_profile_is_typed_and_executable(self):
        p = parse(PROFILE)
        self.assertEqual(run(p), 3)
        self.assertEqual(p.states['name'], 'Guest')
        self.assertIn(('input_text', 'name'), p.widgets)
        self.assertEqual(transition(p, p.states, 'rename')[0], {'name': 'Алиса 😀', 'visits': 1, 'saved': True})

    def test_literal_values_and_escapes(self):
        values = ['', 'true false True False', '"quotes" \\ slash /', '\n\r\t',
                  'Русский 中文 😀', 'e\u0301', 'é', '</script>', '${context} $name',
                  'line\u2028separator\u2029value', '\x00\x08\x0c']
        for value in values:
            # The language deliberately does not adopt JSON's \u/\b/\f escapes.
            source = '"' + value.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t') + '"'
            with self.subTest(value=repr(value)):
                self.assertEqual(evaluate(parse_expr(source, {}), {}), value)

    def test_exact_scalar_equality_without_normalization(self):
        for expr, expected in [ ('"é" == "é"', False), ('"é" != "é"', True),
                               ('"😀" == "😀"', True), ('"A" == "a"', False),
                               ('" name " == "name"', False) ]:
            self.assertIs(evaluate(parse_expr(expr, {}), {}), expected)

    def test_invalid_string_syntax_and_locations(self):
        invalid = ['"bad\\q"', '"bad\\u0041"', '"bad\\x41"', '"bad\\/"',
                   '"unterminated', "'single'", 'r"raw"', 'f"interpolate"',
                   '"one" "two"', '"one""two"', '"\\b"', '"\\f"', '"bad\\']
        for expression in invalid:
            with self.subTest(expression=expression), self.assertRaisesRegex(ValueError, r'Line 2: column \d+:'):
                parse('app "Bad"\nstate title = ' + expression)
        with self.assertRaisesRegex(ValueError, r'Line 2: column 19: Invalid text escape'):
            parse('app "Bad"\nstate title = "bad\\q"')

    def test_source_labels_share_escape_aware_grammar(self):
        p = parse(r'''app "A \"title\" \\ true"
state visible = true
action noop: visible = true
screen main:
    text "A \"quote\" \n true"
    show visible : text "\\path\t😀"
    button "Use \"this\" -> label" -> noop
''')
        self.assertEqual(p.name, 'A "title" \\ true')
        self.assertIn(('text', 'A "quote" \n true'), p.widgets)
        self.assertIn(('show_text', 'visible', '\\path\t😀'), p.widgets)
        self.assertIn(('button', 'Use "this" -> label', 'noop'), p.widgets)
        for declaration in ['app "bad\\q"', 'screen main:\n    text "bad\\q"',
                            'screen main:\n    show visible : text "bad\\q"',
                            'screen main:\n    button "bad\\q" -> noop']:
            source = ('state visible = true\naction noop: visible = true\n' + declaration)
            with self.subTest(declaration=declaration), self.assertRaisesRegex(ValueError, 'Line .*column .*Invalid text escape'):
                parse(source)

    def test_text_limits_are_scalars_not_utf16_units(self):
        for char in ('a', '😀'):
            self.assertEqual(checked_text(char * 1024), char * 1024)
            parse('app "Bound"\nstate title = ' + literal(char * 1024))
            with self.assertRaisesRegex(ValueError, '1024'):
                checked_text(char * 1025)
            with self.assertRaisesRegex(ValueError, 'Line 2: column .*1024'):
                parse('app "Bound"\nstate title = ' + literal(char * 1025))
        for value in ('\ud800', '\udfff', 'a\ud800b', '\ud83d\ude00'):
            with self.subTest(value=repr(value)), self.assertRaisesRegex(ValueError, 'surrogate'):
                checked_text(value)
        with self.assertRaisesRegex(ValueError, 'Line 2: column .*surrogate'):
            parse('app "Bad"\nstate title = "\ud800"')

        with self.assertRaisesRegex(ValueError, 'Line 2: column .*surrogate'):
            parse('app "Bad"\n# comment \ud800')

    def test_text_only_operations_are_equality_and_assignment(self):
        for expr in ('"a" + "b"', '"a" * 2', '"a" < "b"', 'not "a"',
                     '"a" == 1', '"a" == true', '"a" and true', '-"a"'):
            with self.subTest(expr=expr), self.assertRaises(ValueError):
                parse_expr(expr, {})
        for assignment in ('name = 1', 'name = true', 'visits = "1"', 'saved = "true"', 'named = "x"'):
            with self.subTest(assignment=assignment), self.assertRaises(ValueError):
                parse(PROFILE.replace('name = "Алиса 😀"', assignment))

        # From experimental bounded core A1 onwards, Unicode scalar indexing
        # is a permitted, strictly typed text operation.
        self.assertEqual(evaluate(parse_expr('"a"[0]', {}), {}), "a")

    def test_mixed_action_rejection_is_atomic(self):
        p = parse(PROFILE)
        original = p.states.copy()
        changed, accepted = transition(p, original, 'reject_blank')
        self.assertFalse(accepted)
        self.assertEqual(changed, original)
        self.assertEqual(original, p.states)

    def test_temporary_text_rule_failure_can_be_repaired_in_one_action(self):
        p = parse(PROFILE.replace('name = "Алиса 😀"', 'name = ""\n    name = "Final"'))
        state, accepted = transition(p, p.states, 'rename')
        self.assertTrue(accepted)
        self.assertEqual(state['name'], 'Final')
        self.assertEqual(state['visits'], 1)

    def test_input_empty_whitespace_unicode_and_types(self):
        p = parse(PROFILE)
        for value in ('', '😀' * 1025, '\ud800', None, 1, True, [], {}):
            with self.subTest(value=repr(value)):
                state, accepted = edit_state(p, p.states, 'name', value)
                self.assertFalse(accepted)
                self.assertEqual(state, p.states)
        for value in ('  ', 'é', 'é', '😀' * 1024, 'a\rb\nc\t'):
            state, accepted = edit_state(p, p.states, 'name', value)
            self.assertTrue(accepted)
            self.assertEqual(state['name'], value)
        empty = parse('app "Empty"\nstate title = "seed"\npersist title')
        self.assertEqual(edit_state(empty, empty.states, 'title', ''), ({'title': ''}, True))
        self.assertFalse(valid_state(p, {**p.states, 'visits': True}))
        self.assertFalse(valid_state(p, {**p.states, 'saved': 0}))

    def test_restore_fields_and_whole_snapshot_fallback(self):
        p = parse(PROFILE)
        for value in (None, 1, True, [], {}, '😀' * 1025, '\udfff'):
            actual = restore_state(p, {'name': value, 'visits': 4, 'saved': True})
            self.assertEqual(actual, {'name': 'Guest', 'visits': 4, 'saved': True})
        self.assertEqual(restore_state(p, {'name': '', 'visits': 4, 'saved': True}), p.states)
        self.assertEqual(restore_state(p, {'name': '😀' * 1024}), {**p.states, 'name': '😀' * 1024})
        for saved in (None, [], 'broken', True):
            self.assertEqual(restore_state(p, saved), p.states)
        q = parse('app "Transient"\nstate title = "seed"')
        self.assertEqual(restore_state(q, {'title': 'changed'}), q.states)

    def test_cli_json_and_malformed_utf8(self):
        cli = ROOT / 'sedrava_cli.py'
        result = subprocess.run([sys.executable, str(cli), 'run', str(ROOT / 'examples/text_profile.sdr'), 'rename'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['name'], 'Алиса 😀')
        with tempfile.TemporaryDirectory(prefix='text source ') as directory:
            source = Path(directory) / 'bad.sdr'
            source.write_bytes(b'app "Bad"\nstate title = "\xff"')
            for command in ('check', 'run', 'test'):
                result = subprocess.run([sys.executable, str(cli), command, str(source)], capture_output=True, text=True)
                self.assertEqual(result.returncode, 1)
                self.assertNotIn('Traceback', result.stderr)

    def test_legacy_label_backslash_migration_is_explicit(self):
        # 0.10 adopts one escaped grammar for labels and values. A literal backslash
        # in a legacy label must now be escaped; all published examples are unchanged.
        p = parse(r'app "Paths"' + '\n' + r'screen main:' + '\n' + r'    text "C:\\temp"')
        self.assertEqual(p.widgets, (('text', 'C:\\temp'),))
