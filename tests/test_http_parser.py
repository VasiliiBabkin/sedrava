"""Service declaration parser contract tests."""
import unittest
from sedrava_http_parser import parse_service
from sedrava_http_codegen import generate_fetch_module

SOURCE = '''service articles:
    origin "https://api.example.com"
    path "/v1/articles"
    timeout 5000
    max-bytes 4096
    response many:
        title text
        id int32
        published bool
'''


class ServiceParserTests(unittest.TestCase):
    def test_parse_and_generate(self):
        service, schema = parse_service(SOURCE)
        self.assertEqual(service.url, "https://api.example.com/v1/articles")
        self.assertEqual(service.timeout_ms, 5000)
        self.assertTrue(schema.many)
        self.assertEqual(len(schema.fields), 3)
        js = generate_fetch_module(service, schema)
        self.assertIn('"maxBytes":4096', js)
        self.assertIn('"name":"published","kind":"bool"', js)

    def test_invalid_declarations(self):
        for source in (
            SOURCE.replace('https://api.example.com', 'http://api.example.com'),
            SOURCE.replace('        id int32', '        id float'),
            SOURCE.replace('        id int32', '        title int32'),
            SOURCE.replace('    timeout 5000', '    timeout -1'),
            SOURCE.replace('    response many:', '    response unknown:'),
            SOURCE.replace('    path "/v1/articles"', '    path "/../private"'),
            SOURCE.replace('    origin "https://api.example.com"', ''),
            SOURCE.replace('        published bool', '      published bool'),
            SOURCE + '    origin "https://other.example.com"\n',
        ):
            with self.subTest(source=source), self.assertRaises(ValueError):
                parse_service(source)
