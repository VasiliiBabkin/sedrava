"""Every supported example has executable tests; every UI builds deterministically."""
from pathlib import Path
import tempfile
import unittest
from sedrava_core import parse, run
from sedrava_frontend import parse_document
from sedrava_site import Site
from sedrava_webapp import WebApp, generate_webapp
from site_codegen import generate_site
from web_codegen import generate
from android_codegen_v03 import generate as android

ROOT = Path(__file__).resolve().parents[1]

class ExamplesAlpha(unittest.TestCase):
    def test_all_examples(self):
        for path in sorted((ROOT / 'examples').glob('*.sdr')):
            with self.subTest(example=path.name):
                source = path.read_text(encoding='utf-8')
                program = parse_document(source,path)
                if isinstance(program, dict) and program.get("format") == 1 and "migrations" in program:
                    from sedrava_server_schema import parse_server, build_server
                    self.assertEqual(program, parse_server(source))
                    with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
                        build_server(source, Path(a), path)
                        build_server(source, Path(b), path)
                        first = {p.relative_to(a): p.read_bytes() for p in Path(a).rglob('*') if p.is_file()}
                        second = {p.relative_to(b): p.read_bytes() for p in Path(b).rglob('*') if p.is_file()}
                        self.assertEqual(first, second)
                        self.assertIn(Path('schema.json'), first)
                    continue
                if isinstance(program,WebApp):
                    first=generate_webapp(program)
                    second=generate_webapp(parse_document(source,path))
                    self.assertEqual(first,second)
                    self.assertIn("index.html",first)
                    self.assertIn("app.js",first)
                    continue
                if isinstance(program,Site):
                    first,_=generate_site(program,path.parent)
                    second,_=generate_site(parse_document(source,path),path.parent)
                    self.assertEqual(first,second)
                    self.assertIn('index.html',first)
                    continue
                self.assertGreater(run(program), 0)
                if program.widgets:
                    self.assertEqual(generate(source), generate(source))
                    with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
                        android(source, a)
                        android(source, b)
                        files = sorted(p.relative_to(a) for p in Path(a).rglob('*') if p.is_file())
                        for file in files:
                            self.assertEqual((Path(a) / file).read_bytes(), (Path(b) / file).read_bytes())
                        self.assertNotIn('uses-permission', (Path(a) / 'app/src/main/AndroidManifest.xml').read_text())
