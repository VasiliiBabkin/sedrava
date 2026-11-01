"""Integration tests for a normal Web app with an optional read-only API0 panel."""
import tempfile
import unittest
from pathlib import Path

from sedrava_cli import main
from sedrava_http_embed import embed_api_panel


class ApiWebIntegrationTests(unittest.TestCase):
    def test_panel_uses_text_nodes_and_is_isolated(self):
        result = embed_api_panel("<html><body><main>Local state</main></body></html>", "articles")
        self.assertIn("Local state", result)
        self.assertIn("import {load} from './service.mjs'", result)
        self.assertIn("detail.textContent = String(value)", result)
        self.assertNotIn("innerHTML", result)
        self.assertIn("controller?.abort()", result)

    def test_invalid_document_rejected(self):
        with self.assertRaises(ValueError):
            embed_api_panel("not an HTML page", "articles")

    def test_build_existing_app_with_service(self):
        source = Path("examples/task_manager_navigation.sdr")
        self.assertTrue(source.is_file())
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            service = folder / "articles.sdr"
            service.write_text('''service articles:
    origin "https://api.example.com"
    path "/posts"
    response many:
        id int32
        title text
''', encoding="utf-8")
            output = folder / "site" / "index.html"
            self.assertEqual(main(["build", "web", str(source), "--service", str(service),
                                   "--output", str(output)]), 0)
            html = output.read_text(encoding="utf-8")
            module = (output.parent / "service.mjs").read_text(encoding="utf-8")
            self.assertIn('id="sedrava-api-panel"', html)
            self.assertIn("https://api.example.com/posts", module)
            self.assertIn("service.mjs", html)

    def test_service_flag_not_allowed_for_android(self):
        with self.assertRaises(SystemExit) as context:
            main(["build", "android", "examples/task_manager.sdr", "--service", "api.sdr"])
        self.assertEqual(context.exception.code, 2)
