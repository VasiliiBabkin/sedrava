"""Original file and line provenance across checked 0.12 module expansions."""
import tempfile
import unittest
from pathlib import Path

from sedrava_frontend import parse_document
from sedrava_modules import expand
from sedrava_source_map import source_error
from sedrava_webapp import build_webapp
from site_codegen import build_site


class SourceMapTests(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.root = Path(t.name)

    def put(self, name, content):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def test_exported_function_error_locates_original_file(self):
        origin = self.put("math.sdr", "module sample.math\nexport fn compute(x: int) -> int = missing(x)\n")
        source = ('webapp "Math"\nimport "math.sdr" as math\n'
                  'state value = 1\nderive computed = math.compute(value)\n'
                  'view main:\n    heading "Math"\n    value computed\n')
        main = self.put("main.sdr", source)
        with self.assertRaises(ValueError) as err:
            parse_document(source, main)
        self.assertIn(f"{origin}:2:", str(err.exception))
        self.assertIn("Unknown identifier: missing", str(err.exception))
        with self.assertRaises(ValueError) as built:
            build_webapp(source, self.root / "out", main)
        self.assertIn(f"{origin}:2:", str(built.exception))

    def test_nested_aliased_origin(self):
        deep = self.put("sub/deep.sdr", "module sub.deep\nexport fn fail(x: int) -> int = not_found(x)\n")
        self.put("bridge.sdr", "module sub.bridge\nimport \"sub/deep.sdr\" as deep\nexport fn run(x: int) -> int = deep.fail(x)\n")
        source = ('webapp "Multi"\nimport "bridge.sdr" as bridge\n'
                  'state value = 1\nderive result = bridge.run(value)\n'
                  'view main:\n    heading "Multi"\n    value result\n')
        with self.assertRaises(ValueError) as err:
            parse_document(source, self.put("main.sdr", source))
        self.assertIn(f"{deep}:2:", str(err.exception))

    def test_component_template_error_through_two_build_paths(self):
        component = self.put("ui.sdr", "module ui.panel\nexport component Panel:\n    imaginary \"Invalid component\"\n")
        source = ('site "Sample"\nimport "ui.sdr" as ui\n'
                  'page home at "/":\n    title "Sample"\n    heading "Sample"\n    use ui.Panel\n')
        main = self.put("main.sdr", source)
        with self.assertRaises(ValueError) as err:
            parse_document(source, main)
        self.assertIn(f"{component}:3:", str(err.exception))
        self.assertIn("Unknown site component imaginary", str(err.exception))
        with self.assertRaises(ValueError) as built:
            build_site(source, self.root / "out", main)
        self.assertIn(f"{component}:3:", str(built.exception))

    def test_legacy_import(self):
        old = self.put("legacy.sdr", "fn unknown(x: int) -> int = invalid(x)\n")
        source = ('webapp "Old"\nimport "legacy.sdr"\nstate n=1\n'
                  'derive result=unknown(n)\nview main:\n'
                  '    heading "Old"\n    value result\n')
        with self.assertRaises(ValueError) as err:
            parse_document(source, self.put("main.sdr", source))
        self.assertIn(f"{old}:1:", str(err.exception))

    def test_caller_line_after_expansion(self):
        self.put("math.sdr", "module m.math\nexport fn inc(x: int) -> int = x+1\n")
        source = ('webapp "Caller"\nimport "math.sdr" as math\n'
                  'state n=1\nderive result=math.inc(nope)\n'
                  'view main:\n    heading "Caller"\n    value result\n')
        main = self.put("main.sdr", source)
        with self.assertRaises(ValueError) as err:
            parse_document(source, main)
        self.assertIn(f"{main}:4:", str(err.exception))
        self.assertIn("nope", str(err.exception))

    def test_exact_map_and_unchanged_expansion_output(self):
        ui = self.put("ui.sdr", "module ui.panel\nexport component Panel:\n    card:\n        paragraph \"x\"\n")
        source = ('site "Map"\nimport "ui.sdr" as ui\n'
                  'page home at "/":\n    title "Map"\n'
                  '    heading "Map"\n    use ui.Panel\n')
        parsed, paths, origins = expand(source, self.put("main.sdr", source), with_origins=True)
        self.assertEqual(len(origins), len(parsed.splitlines()))
        self.assertEqual(len(paths), 1)
        self.assertIn(ui, paths)
        idx = parsed.splitlines().index('        paragraph "x"')
        self.assertEqual(origins[idx], (ui, 4))
        self.assertTrue(parsed.endswith('\n'))
        self.assertEqual(parsed, expand(source, self.root / "main.sdr")[0])

    def test_refuse_guessed_locations(self):
        origins = ((Path("/root/a.sdr"), 100),)
        for message in ("Unknown state", "Line 2: column 3: Unknown", "Line 0: wrong"):
            err = ValueError(message)
            self.assertIs(source_error(err, origins), err)


if __name__ == "__main__":
    unittest.main()
