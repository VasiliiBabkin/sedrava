"""Sedrava 0.11 B1 collections: type-safe list UI and CRUD parity with core."""
from pathlib import Path
import tempfile
import unittest

from sedrava_core import edit_state, transition
from sedrava_records import ListValue
from sedrava_webapp import build_webapp, generate_webapp, parse_webapp

ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATH = ROOT / "examples/webapp_011_tasks.sdr"
SOURCE = SOURCE_PATH.read_text(encoding="utf-8")
LIST_LINE = 'list tasks select selected title title status done label "Task list"'


class WebAppCollectionTests(unittest.TestCase):
    def invalid(self, replacement, expected):
        with self.assertRaisesRegex(ValueError, expected):
            parse_webapp(SOURCE.replace(LIST_LINE, replacement))

    def test_parses_existing_records_and_derivations(self):
        doc = parse_webapp(SOURCE)
        program = doc.program
        self.assertEqual(list(program.records), ["Task"])
        self.assertIsInstance(program.states["tasks"], ListValue)
        self.assertEqual(program.states["tasks"].kind.capacity, 100)
        self.assertIn("tasks", program.persistent)
        self.assertEqual(set(program.actions), {"add", "rename", "toggle", "delete"})
        self.assertEqual(len([w for w in doc.widgets if w.kind == "container"]), 1)

    def test_list_binding_is_compiler_checked(self):
        self.invalid(LIST_LINE.replace("tasks select", "unknown select"), "List requires a declared collection")
        self.invalid(LIST_LINE.replace("selected title", "new_title title"), "mutable integer state")
        self.invalid(LIST_LINE.replace("title title", "title done"), "text record field")
        self.invalid(LIST_LINE.replace("status done", "status title"), "boolean record field")
        self.invalid("list tasks title title", "Missing required parameter select")
        self.invalid(LIST_LINE.replace("title title", "title missing"), "text record field")
        self.invalid("value tasks", "Value requires scalar")
        self.invalid('input tasks label "Not scalar"', "Input requires integer or text state")
        self.invalid("list selected select selected", "List requires a declared collection")

    def test_emits_validated_persistence_and_safe_dom(self):
        bundle = generate_webapp(SOURCE)
        markup = bundle["index.html"].decode()
        js = bundle["app.js"].decode()
        css = bundle["app.css"].decode()
        self.assertIn('data-list="tasks"', markup)
        self.assertIn('data-select="selected"', markup)
        self.assertIn('data-title-field="title"', markup)
        self.assertIn('data-status-field="done"', markup)
        self.assertIn('aria-label="Task list"', markup)
        self.assertIn("const collectionTypes", js)
        self.assertIn("function collectionOp(", js)
        self.assertIn("function restoreSnapshot(", js)
        self.assertIn("function renderLists()", js)
        self.assertIn("document.createElement", js)
        self.assertIn("title.textContent=label", js)
        self.assertIn("button.setAttribute(\"aria-pressed\"", js)
        self.assertNotIn("innerHTML", js)
        self.assertNotIn("eval(", js)
        self.assertIn(".s-list-choice", css)
        self.assertIn("script-src 'self'", markup)

    def test_crud_uses_exact_existing_core_invariants(self):
        p = parse_webapp(SOURCE).program
        state = p.states.copy()
        with self.assertRaisesRegex(ValueError, "requirement"):
            transition(p, state, "add")
        state, ok = edit_state(p, state, "new_title", "Original")
        self.assertTrue(ok)
        state, ok = transition(p, state, "add")
        self.assertTrue(ok)
        self.assertEqual(len(state["tasks"].items), 1)
        self.assertEqual(state["tasks"].items[0][0], 1)
        self.assertEqual(state["tasks"].items[0][1].values, ("Original", False))
        self.assertEqual(state["new_title"], "")
        state, ok = edit_state(p, state, "selected", 1)
        self.assertTrue(ok)
        state, ok = transition(p, state, "toggle")
        self.assertTrue(ok)
        self.assertEqual(state["tasks"].items[0][1].values, ("Original", True))
        state, ok = edit_state(p, state, "rename_to", "Renamed")
        self.assertTrue(ok)
        state, ok = transition(p, state, "rename")
        self.assertTrue(ok)
        self.assertEqual(state["tasks"].items[0][1].values, ("Renamed", True))
        state, ok = transition(p, state, "delete")
        self.assertTrue(ok)
        self.assertEqual(state["tasks"].items, ())
        self.assertEqual(state["selected"], 0)
        self.assertEqual(state["tasks"].next_id, 2)
        with self.assertRaisesRegex(ValueError, "Missing record|requirement"):
            transition(p, state, "toggle")

    def test_deterministic_bundle_across_fresh_builds(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            a, b = root / "a", root / "b"
            build_webapp(SOURCE, a, SOURCE_PATH)
            build_webapp(SOURCE, b, SOURCE_PATH)
            self.assertEqual(sorted(p.name for p in a.iterdir()),
                             sorted(p.name for p in b.iterdir()))
            for path in a.iterdir():
                self.assertEqual(path.read_bytes(), (b / path.name).read_bytes())


if __name__ == "__main__":
    unittest.main()
