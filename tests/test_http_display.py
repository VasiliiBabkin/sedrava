"""Declarative HTTP display contract tests."""
import unittest
from sedrava_http_display import parse_display_service, parse_display_options

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

    def test_custom_heading_and_messages(self):
        extra = '''    display cards:
        title
        heading "Latest articles"
        loading "Fetching articles"
        empty "Nothing published"
        error "Could not retrieve articles"
'''
        _, _, fields = parse_display_service(BASE + extra)
        self.assertEqual(fields, ["title"])
        self.assertEqual(parse_display_options(BASE + extra), {
            "title": "Latest articles",
            "loading": "Fetching articles",
            "empty": "Nothing published",
            "error": "Could not retrieve articles",
        })

    def test_duplicate_option_rejected(self):
        extra = '''    display cards:
        title
        heading "One"
        heading "Two"
'''
        with self.assertRaises(ValueError):
            parse_display_options(BASE + extra)

    def test_custom_text_and_unicode(self):
        source = BASE + '''    display cards:
        heading "Новости"
        loading "Загрузка…"
        empty "Нет записей"
        error "Ошибка загрузки"
        title
'''
        self.assertEqual(parse_display_service(source)[2], ["title"])
        self.assertEqual(parse_display_options(source), {
            "title": "Новости", "loading": "Загрузка…",
            "empty": "Нет записей", "error": "Ошибка загрузки"})

    def test_invalid_text_rejected(self):
        for option in ('heading ""', 'heading "bad" extra', 'loading "x" extra'):
            with self.subTest(option=option):
                source = BASE + '    display cards:\n        title\n        ' + option + '\n'
                with self.assertRaises(ValueError):
                    parse_display_service(source)

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
