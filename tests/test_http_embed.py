"""Regression tests for schema-driven HTTP panel rendering."""
import unittest

from sedrava_http_embed import embed_api_panel


class HttpEmbedTests(unittest.TestCase):
    def test_explicit_schema_fields_are_embedded(self):
        page = embed_api_panel("<html><body></body></html>", "Articles", ["id", "title"])
        self.assertIn('const visibleFields = ["id", "title"];', page)
        self.assertIn("!visibleFields.includes(key)", page)
        self.assertIn("textContent = String(value)", page)
        self.assertNotIn("innerHTML", page)

    def test_heading_is_escaped(self):
        page = embed_api_panel("<body></body>", "<script>alert(1)</script>", ["title"])
        self.assertIn("&lt;script&gt;", page)
        self.assertNotIn("<h2><script>", page)

    def test_missing_body_rejected(self):
        with self.assertRaises(ValueError):
            embed_api_panel("<html></html>", "Articles", ["title"])


if __name__ == "__main__":
    unittest.main()
