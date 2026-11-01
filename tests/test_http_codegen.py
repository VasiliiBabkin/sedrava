"""Generated browser HTTP connector smoke and safety tests."""
import unittest
from sedrava_http import ApiService, JsonField, JsonResponse
from sedrava_http_codegen import generate_fetch_module


class FetchModuleTests(unittest.TestCase):
    def test_generates_read_only_bounded_connector(self):
        service = ApiService("articles", "https://api.example.com", "/v1/articles", 1200, 4096)
        schema = JsonResponse((JsonField("title", "text"), JsonField("id", "int32")), many=True)
        js = generate_fetch_module(service, schema)
        self.assertIn("https://api.example.com/v1/articles", js)
        self.assertIn("export async function load", js)
        self.assertIn("method: 'GET'", js)
        self.assertIn("credentials: 'omit'", js)
        self.assertIn("redirect: 'error'", js)
        self.assertIn("new AbortController()", js)
        self.assertIn("length > CONFIG.maxBytes", js)
        self.assertIn("Object.prototype.hasOwnProperty.call", js)
        self.assertNotIn("eval(", js)
        self.assertEqual(js, generate_fetch_module(service, schema))

    def test_rejects_unvalidated_arguments(self):
        schema = JsonResponse((JsonField("title", "text"),))
        with self.assertRaises(ValueError):
            generate_fetch_module("https://api.example.com", schema)
        with self.assertRaises(ValueError):
            generate_fetch_module(ApiService("x", "https://api.example.com", "/"), {})
