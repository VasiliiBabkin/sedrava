"""One-file application and HTTP API0 integration tests."""
import tempfile
import unittest
from pathlib import Path

from sedrava_cli import main
from sedrava_http_inline import split_app_service

SERVICE = '''service articles:
    origin "https://api.example.com"
    path "/posts"
    response many:
        id int32
        title text
'''


class InlineApiTests(unittest.TestCase):
    def test_split_preserves_app_and_service(self):
        app, service = split_app_service("app demo:\n    state count int32 = 0\n\n" + SERVICE)
        self.assertIn("app demo:", app)
        self.assertEqual(service, SERVICE)

    def test_duplicate_service_rejected(self):
        with self.assertRaises(ValueError):
            split_app_service("app demo:\n" + SERVICE + SERVICE)

    def test_one_file_build_and_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            original = Path("examples/task_manager_navigation.sdr").read_text(encoding="utf-8")
            source = folder / "combined.sdr"
            source.write_text(original.rstrip() + "\n\n" + SERVICE, encoding="utf-8")
            output = folder / "site" / "index.html"
            self.assertEqual(main(["check", str(source)]), 0)
            self.assertEqual(main(["build", "web", str(source), "--output", str(output)]), 0)
            self.assertIn('id="sedrava-api-panel"', output.read_text(encoding="utf-8"))
            self.assertIn("https://api.example.com/posts",
                          (output.parent / "service.mjs").read_text(encoding="utf-8"))

    def test_one_file_declarative_card_projection(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            original = Path("examples/task_manager_navigation.sdr").read_text(encoding="utf-8")
            source = folder / "cards.sdr"
            source.write_text(original.rstrip() + "\n\n" + SERVICE +
                              "    display cards:\n        title\n", encoding="utf-8")
            output = folder / "site" / "index.html"
            self.assertEqual(main(["check", str(source)]), 0)
            self.assertEqual(main(["build", "web", str(source), "--output", str(output)]), 0)
            html = output.read_text(encoding="utf-8")
            self.assertIn('const visibleFields = ["title"];', html)

    def test_conflicting_inline_and_external_service_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            source = folder / "combined.sdr"
            original = Path("examples/task_manager_navigation.sdr").read_text(encoding="utf-8")
            source.write_text(original.rstrip() + "\n\n" + SERVICE, encoding="utf-8")
            external = folder / "external.sdr"
            external.write_text(SERVICE, encoding="utf-8")
            self.assertEqual(main(["build", "web", str(source), "--service", str(external),
                                   "--output", str(folder / "site" / "index.html")]), 1)
