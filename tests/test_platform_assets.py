from pathlib import Path
import tempfile
import unittest
from site_codegen import build_site
from sedrava_webapp import parse_webapp,build_webapp
from sedrava_web_assets import collect
ROOT=Path(__file__).resolve().parents[1]
class Assets(unittest.TestCase):
    def test_site_includes_checked_css_font_and_seo(self):
        source=ROOT/'examples/platform_site.sdr'
        with tempfile.TemporaryDirectory() as tmp:
            output=Path(tmp)/'site';build_site(source.read_text(),output,source)
            self.assertTrue((output/'sitemap.xml').is_file())
            self.assertEqual(len(list((output/'assets').glob('*.woff2'))),1)
            self.assertIn('canonical',(output/'guide/index.html').read_text())
            css=next((output/'assets').glob('*.css')).read_text()
            self.assertNotIn('url("platform-inter.woff2")',css)
            self.assertIn('.woff2',css)
    def test_css_references_cannot_escape_root_or_load_remote(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);css=root/'style.css'
            for text in ['@import "remote.css";','p{background:url(https://evil.example/x)}','p{background:url(../secret.png)}','p{background:u\\72l(x)}']:
                css.write_text(text)
                with self.assertRaises(ValueError):collect({'stylesheets':['style.css']},root)
    def test_theme_is_a_core_invariant_and_typed(self):
        from sedrava_core import edit_state
        from sedrava_frontend import parse_document
        path=ROOT/'examples/platform_crm.sdr'
        doc=parse_document(path.read_text(),path)
        state=doc.program.states.copy()
        rejected,ok=edit_state(doc.program,state,'theme_mode','unregistered')
        self.assertFalse(ok);self.assertEqual(state,rejected)
        accepted,ok=edit_state(doc.program,state,'theme_mode','dark')
        self.assertTrue(ok);self.assertEqual(accepted['theme_mode'],'dark')

    def test_wrong_mode_metadata_is_not_silently_ignored(self):
        from sedrava_site import parse_site
        with self.assertRaisesRegex(ValueError,'theme-state'):parse_site('site "x"\ntheme-state mode\n')
        with self.assertRaisesRegex(ValueError,'robots'):parse_site('site "x"\nrobots false\n')
        with self.assertRaisesRegex(ValueError,'site mode'):parse_webapp('webapp "x"\norigin "https://example.com"\n')
