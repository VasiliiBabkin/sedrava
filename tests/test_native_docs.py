import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from site_codegen import build_site
from sedrava_site import parse_site

SOURCE='''site "Native docs"
clean-urls true
page home at "/":
    title "Native docs"
    heading "Native docs"
    search label "Search"
    markdown "guide.md"
    demo "counter.sdr" at "/live/counter/" label "Counter"
page ru at "/ru/":
    title "Русский"
    lang "ru"
    heading "Русский"
    markdown "guide.md"
    demo "counter.sdr" at "/live/counter/" label "Счётчик"
'''
COUNTER='webapp "Counter"\nstate n=0\npersist n\naction add: n=n+1\nview main:\n    heading "Counter"\n    value n label "Count"\n    button "Add" action add\n    navigate "Details" to details action add\nview details at "/details":\n    heading "Details"\n    value n label "Count"\n    back "Home"\n'
import importlib.util
@unittest.skipUnless(importlib.util.find_spec('markdown_it') and importlib.util.find_spec('pygments'),'Optional docs extra unavailable; native-docs CI installs and tests it explicitly')
class NativeDocs(unittest.TestCase):
    def fixture(self,root,text='## Привет World\n\nSafe **text** and [Russian](/ru/).\n\n~~~sdr\nstate n=0\n~~~\n\n| A | B |\n|---|---|\n| 1 | 2 |\n'):
        (root/'guide.md').write_text(text);(root/'counter.sdr').write_text(COUNTER);(root/'site.sdr').write_text(SOURCE)
    def test_native_markdown_live_bundle_source_hashes_csp_and_determinism(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.fixture(root);out=root/'out';build_site(SOURCE,out,root/'site.sdr')
            index=(out/'index.html').read_text();self.assertIn('<iframe',index);self.assertIn("frame-src 'self'",index);self.assertIn('docs.js',index);self.assertNotIn('sandbox=',index)
            self.assertIn('href="ru/"',index)
            self.assertIn('id="привет-world"',index);self.assertIn('<table>',index)
            digest=hashlib.sha256(COUNTER.encode()).hexdigest();self.assertEqual((out/'sources'/f'{digest}.sdr').read_text(),COUNTER)
            demos=json.loads((out/'docs-demos.json').read_text());self.assertEqual(len(demos),1);self.assertEqual(demos['/live/counter/']['source_sha256'],digest)
            self.assertEqual(json.loads((out/'docs-index.json').read_text())[0]['url'],'/')
            first={p.relative_to(out):p.read_bytes() for p in out.rglob('*') if p.is_file()};build_site(SOURCE,out,root/'site.sdr');self.assertEqual(first,{p.relative_to(out):p.read_bytes() for p in out.rglob('*') if p.is_file()})
            self.assertIn('guide.md',json.loads((out/'sedrava-site.json').read_text())['inputs'])
            # The site renderer must never rewrite a separately generated WebApp.
            from sedrava_webapp import build_webapp
            build_webapp(COUNTER,root/'standalone',root/'counter.sdr')
            for name in ('index.html','app.js','app.css'):self.assertEqual((out/'live/counter'/name).read_bytes(),(root/'standalone'/name).read_bytes())
    def test_reject_html_unsafe_links_traversal_and_collisions_without_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.fixture(root)
            for text in ['<script>alert(1)</script>','Text <img src=x onerror=alert(1)>','[bad](javascript:alert(1))','[bad](/missing/)']:
                self.fixture(root,text)
                with self.subTest(text=text),self.assertRaises(ValueError):build_site(SOURCE,root/'out',root/'site.sdr')
                self.assertFalse((root/'out').exists())
            self.fixture(root)
            for old,new in [('"guide.md"','"../secret.md"'),('at "/live/counter/"','at "/ru/"'),('at "/live/counter/"','at "https://evil.example/"')]:
                with self.subTest(new=new),self.assertRaises(ValueError):build_site(SOURCE.replace(old,new),root/'out',root/'site.sdr')
    def test_highlighter_preserves_exact_source_and_never_interprets_html(self):
        from sedrava_docs import code_panel
        source='print("<script> & 😀")\n# exact source\n'
        rendered=code_panel(source,'python');self.assertNotIn('<script>',rendered)
        self.assertIn(hashlib.sha256(source.encode()).hexdigest(),rendered)
        self.assertIn('class="code-lines" aria-hidden="true"',rendered)
