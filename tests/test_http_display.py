"""Declarative HTTP display contract tests."""
import unittest
from sedrava_http_display import parse_display_service

BASE = '''service articles:
    origin "https://api.example.com"
    path "/posts"
    response many:
        id int32
        title text
'''

class DisplayTests(unittest.TestCase):
    def test_explicit_order_and_subset(self):
        service, schema, fields = parse_display_service(BASE + '''    display cards:
        title
        id
''')
        self.assertEqual(fields, ["title", "id"])
        self.assertEqual(service.name, "articles")
        self.assertEqual(len(schema.fields), 2)

    def test_implicit_schema_order(self):
        _, _, fields = parse_display_service(BASE)
        self.assertEqual(fields, ["id", "title"])

    def test_unknown_and_duplicate_rejected(self):
        for extra in ('''    display cards:
        missing
''', '''    display cards:
        title
        title
''', '''    display cards:
        title
    origin "https://evil.example"
''', '''    display cards:
'''):
            with self.subTest(extra=extra):
                with self.assertRaises(ValueError):
                    parse_display_service(BASE + extra)

if __name__ == "__main__":
    unittest.main()
