"""API page generation and CLI integration tests."""
import tempfile
import unittest
from pathlib import Path
from sedrava_cli import main
from sedrava_http import ApiService, JsonField, JsonResponse
from sedrava_http_page import generate_api_page

SOURCE = '''service posts:
    origin "https://jsonplaceholder.typicode.com"
    path "/posts/1"
    response one:
        userId int32
        id int32
        title text
        body text
'''


class ApiPageTests(unittest.TestCase):
    def test_page_escapes_heading_and_uses_safe_text_nodes(self):
        service = ApiService("posts", "https://api.example.com", "/posts")
        schema = JsonResponse((JsonField("title", "text"),))
        page = generate_api_page(service, schema)
        self.assertIn('role="status"', page)
        self.assertIn("retry.addEventListener('click', refresh)", page)
        self.assertIn("detail.textContent = String(value)", page)
        self.assertNotIn("innerHTML", page)
        self.assertIn("import {load} from './service.mjs'", page)

    def test_cli_build_page(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "service.sdr"
            destination = Path(temp) / "site"
            source.write_text(SOURCE, encoding="utf-8")
            self.assertEqual(main(["build", "api-page", str(source), "--output", str(destination)]), 0)
            self.assertTrue((destination / "index.html").is_file())
            self.assertTrue((destination / "service.mjs").is_file())
            self.assertIn("jsonplaceholder.typicode.com/posts/1", (destination / "service.mjs").read_text(encoding="utf-8"))
