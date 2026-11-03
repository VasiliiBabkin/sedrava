from pathlib import Path
import unittest
from sedrava_webapp import parse_webapp, generate_webapp
from sedrava_web_services import validate_services
ROOT=Path(__file__).resolve().parents[1]
SOURCE=(ROOT/'examples/platform_catalog.sdr').read_text()
class Services(unittest.TestCase):
    def test_methods_schema_and_csp(self):
        doc=parse_webapp(SOURCE)
        self.assertEqual({s.method for s in doc.services.values()},{'GET','POST','PUT','PATCH','DELETE'})
        files=generate_webapp(doc)
        self.assertIn(b"connect-src 'self'",files['index.html'])
        self.assertIn(b'credentials:\'omit\'',files['app.js'])
        self.assertNotIn(b'eval(',files['app.js'])
        self.assertIn(b'function strictJSON',files['app.js'])
    def test_invalid_capabilities_and_types(self):
        for old,new in [('method POST','method TRACE'),('origin self','origin "http://evil.example"'),
                        ('Product(title=product_title','Product(title=selected_id'),('max-bytes 16384','max-bytes 999999'),
                        ('method GET','method POST'),('id int32','id unknown'),('service catalog','service missing')]:
            with self.subTest(new=new), self.assertRaises(ValueError):parse_webapp(SOURCE.replace(old,new))
    def test_public_get_connector_is_isolated(self):
        doc=parse_webapp(SOURCE.replace('origin self','origin "https://api.example.com"'))
        self.assertIn(b"connect-src 'self' https://api.example.com",generate_webapp(doc)['index.html'])

    def test_origin_is_normalized_for_browser_capability_comparison(self):
        doc=parse_webapp(SOURCE.replace('origin self','origin "https://API.EXAMPLE.COM:443/"'))
        self.assertEqual(doc.services['catalog'].origin,'https://api.example.com')
