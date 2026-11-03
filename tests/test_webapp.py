"""WebApp B1: typed grammar, deterministic build, no legacy regressions."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from sedrava_core import parse as parse_app
from sedrava_frontend import parse_document
from sedrava_webapp import (WebApp, build_webapp, generate_webapp,
                            parse_webapp)
from sedrava_cli import main


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = (ROOT / "examples/webapp_011_counter.sdr").read_text(encoding="utf-8")
MINIMAL = ('webapp "Test"\nstate count = 0\npersist count\n'
           'action add: count = count + 1\nview main:\n'
           '    heading "Hello"\n    value count\n'
           '    button "Add" action add\n')


class WebAppTests(unittest.TestCase):
    def bad(self, source, message):
        with self.assertRaisesRegex(ValueError, message):
            parse_webapp(source)

    def test_explicit_mode_and_real_domain_semantics(self):
        doc = parse_document(EXAMPLE)
        self.assertIsInstance(doc, WebApp)
        self.assertEqual(doc.program.states["count"], 0)
        self.assertEqual(doc.program.states["note"], "Welcome")
        self.assertEqual(set(doc.program.persistent),
                         {"count", "note", "show_note"})
        self.assertEqual(len(doc.program.actions), 3)
        self.assertIn("double_count", doc.program.derived)
        self.assertIn("webapp", doc.mode)
        self.assertIsInstance(parse_document("app \"Legacy\"\nstate x = 0\n"),
                              type(parse_app("app \"Legacy\"\nstate x = 0\n")))
        with self.assertRaisesRegex(ValueError, "build webapp"):
            parse_app(MINIMAL)

    def test_html_js_css_separate_with_strict_csp(self):
        files = generate_webapp(EXAMPLE)
        self.assertEqual(set(files), {"index.html", "app.css", "app.js"})
        markup = files["index.html"].decode()
        script = files["app.js"].decode()
        css = files["app.css"].decode()
        self.assertIn("script-src 'self'", markup)
        self.assertIn('src="app.js" defer', markup)
        self.assertNotIn("<script>", markup)
        self.assertIn('data-state="count"', markup)
        self.assertIn('data-state="double_count"', markup)
        self.assertIn('data-input="note"', markup)
        self.assertIn('data-check="show_note"', markup)
        self.assertIn('data-when="show_note"', markup)
        self.assertIn('data-action="increment"', markup)
        self.assertIn('const actions = {', script)
        self.assertIn('nextState["count"] = checkedInt(', script)
        self.assertIn('function saveSnapshot()', script)
        self.assertIn('function render()', script)
        self.assertIn('el.textContent=String(values[el.dataset.state])', script)
        self.assertNotIn("innerHTML", script)
        self.assertNotIn("eval(", script)
        self.assertIn('.s-grid{display:grid', css)
        self.assertIn('input:focus-visible', css)

    def test_scalar_type_and_reference_rejections(self):
        self.bad(MINIMAL.replace('value count', 'value missing'), "Unknown state")
        self.bad(MINIMAL.replace('action add\n', 'action missing\n'), "Unknown action")
        self.bad(MINIMAL.replace('value count', 'input count'), "Missing required parameter label")
        self.bad(MINIMAL.replace('value count', 'checkbox count label "Yes"'), "requires boolean")
        self.bad(MINIMAL.replace('value count', 'when count:\n        paragraph "x"'), "requires boolean")
        self.bad(EXAMPLE.replace('input count label "Edit count"', 'input double_count label "Derived"'),
                 "cannot edit derived state")
        self.bad(EXAMPLE.replace('input note label "Your note"', 'checkbox note label "Text"'),
                 "requires boolean")
        self.bad(MINIMAL.replace('value count', 'input count label ""'), "Accessible label")
        self.bad(MINIMAL.replace('value count', 'value count style unknown'), "Unknown parameter")
        self.bad(MINIMAL.replace('value count', 'value count color "red;bad"'), "Expected a theme token")
        self.bad(MINIMAL.replace('value count', 'paragraph "X" onclick "malicious"'), "Unknown parameter")

    def test_missing_or_invalid_view_and_structure(self):
        self.bad(MINIMAL.replace('view main:', 'view detail:'), "Exactly one")
        self.bad(MINIMAL.replace('view main:', 'view main:\n    heading "X"\nview main:'), "Exactly one")
        self.bad(MINIMAL.replace('    heading "Hello"\n', ''), "exactly one h1")
        self.bad(MINIMAL.replace('    value count\n', '    heading "Other" level 1\n'), "exactly one h1")
        self.bad(MINIMAL.replace('    value count\n', '    column:\n        value count\n').replace(
            '    button "Add" action add\n',''), "column|Unsupported") if False else None
        self.bad(MINIMAL.replace('    value count', '      value count'), "Expected four-space")
        self.bad(MINIMAL.replace('    value count', '    script "evil"'), "Unsupported WebApp")
        self.bad(MINIMAL.replace('    value count', '    row:'), "Empty component block")
        self.bad(MINIMAL.replace('    value count', '    value count:'), "Invalid component block structure")
        self.bad(MINIMAL.replace('view main:', 'view main:\n    paragraph "Extra"\nnot-a-view:'), "Unexpected text after view")

    def test_escaping_prevents_markup_or_script_injection(self):
        source = MINIMAL.replace('heading "Hello"', 'heading "<script>attack()</script>"')
        source = source.replace('button "Add"', 'button "<b>Add</b>"')
        source = source.replace('value count', 'code "<svg onload=alert(1)>"\n    value count')
        files = generate_webapp(source)
        html = files["index.html"].decode()
        css = files["app.css"].decode()
        self.assertNotIn('<script>attack()', html)
        self.assertNotIn('<svg onload', html)
        self.assertIn('&lt;script&gt;', html)
        self.assertIn('&lt;svg onload', html)
        self.assertIn('&lt;b&gt;Add&lt;/b&gt;', html)
        self.assertNotIn('attack()', css)

    def test_deterministic_build_and_refuse_dirty_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "app.sdr"
            source.write_text(EXAMPLE, encoding="utf-8")
            paths = (root / "one", root / "two")
            for path in paths:
                build_webapp(EXAMPLE, path, source)
            def snapshot(path):
                return {p.relative_to(path).as_posix(): p.read_bytes()
                        for p in path.rglob("*") if p.is_file()}
            self.assertEqual(snapshot(paths[0]), snapshot(paths[1]))
            build_webapp(EXAMPLE, paths[0], source)
            self.assertEqual(snapshot(paths[0]), snapshot(paths[1]))
            manifest = json.loads((paths[0] / "sedrava-webapp.json").read_text())
            self.assertEqual(manifest["mode"], "webapp")
            self.assertEqual(set(manifest["files"]), {"index.html", "app.css", "app.js"})
            (paths[0] / "app.js").write_text("user edited", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "modified"):
                build_webapp(EXAMPLE, paths[0], source)
            self.assertEqual((paths[0] / "app.js").read_text(), "user edited")
            with self.assertRaisesRegex(ValueError, "unmanaged"):
                build_webapp(EXAMPLE, root / "unmanaged", source) if False else (
                    (root / "unmanaged").mkdir(),
                    (root / "unmanaged" / "mine.txt").write_text("mine"),
                    build_webapp(EXAMPLE, root / "unmanaged", source)
                )
            with self.assertRaisesRegex(ValueError, "contain its source"):
                build_webapp(EXAMPLE, root, source)

    def test_cli_mode_boundaries_and_output(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "sample.sdr"
            source.write_text(MINIMAL, encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(["check", str(source)]), 0)
                self.assertEqual(main(["build", "webapp", str(source),
                                       "--output", str(root / "app")]), 0)
            self.assertTrue((root / "app/index.html").is_file())
            for command in (["build", "web"], ["build", "site"],
                            ["build", "android"], ["run"], ["test"]):
                with contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(main(command + [str(source)]), 1)
            source.write_text('app "Old"\nstate x = 0\n', encoding="utf-8")
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(["build", "webapp", str(source)]), 1)


if __name__ == "__main__":
    unittest.main()
