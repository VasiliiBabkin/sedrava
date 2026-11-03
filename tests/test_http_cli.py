"""End-to-end CLI service compilation smoke tests."""
import tempfile
import unittest
from pathlib import Path
from sedrava_cli import main

SOURCE = '''service article:
    origin "https://jsonplaceholder.typicode.com"
    path "/posts/1"
    response one:
        userId int32
        id int32
        title text
        body text
'''


class ApiCliTests(unittest.TestCase):
    def test_check_and_build(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "article.sdr"
            output = Path(folder) / "article.mjs"
            source.write_text(SOURCE, encoding="utf-8")
            self.assertEqual(main(["check", str(source)]), 0)
            self.assertEqual(main(["build", "api-web", str(source), "--output", str(output)]), 0)
            js = output.read_text(encoding="utf-8")
            self.assertIn("export async function load", js)
            self.assertIn("jsonplaceholder.typicode.com/posts/1", js)

    def test_reject_invalid_source_without_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "invalid.sdr"
            output = Path(folder) / "article.mjs"
            source.write_text(SOURCE.replace("https://", "http://"), encoding="utf-8")
            output.write_text("existing", encoding="utf-8")
            self.assertEqual(main(["build", "api-web", str(source), "--output", str(output)]), 1)
            self.assertEqual(output.read_text(encoding="utf-8"), "existing")
