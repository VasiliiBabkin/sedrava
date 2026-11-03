"""Canonical documentation guard for the published Sedrava 0.10.0 release.

Historical release-candidate audit reports are intentionally not scanned:
they record the status *at the time of their creation*.
"""
from pathlib import Path
import re
import unittest
from sedrava_version import VERSION, ANDROID_VERSION_CODE

ROOT = Path(__file__).resolve().parents[1]
CANONICAL = [
    "README.md",
    "docs/QUICKSTART.md",
    "docs/README.en.md",
    "docs/README.ru.md",
    "docs/FAQ.md",
    "docs/ROADMAP.md",
    "docs/RELEASE_NOTES_0_10_0.md",
]
NO_STALE = [
    "Sedrava has not been published on PyPI",
    "not yet published on PyPI",
    "no Sedrava package has been published",
    "0.10 remains unreleased",
    "0.10 не выпущена",
    "Пакета Sedrava на PyPI пока нет",
    "0.10.0.dev0",
]


class PublishedDocumentationTests(unittest.TestCase):
    def test_version_and_published_links(self):
        self.assertEqual(VERSION, "0.10.0")
        self.assertEqual(ANDROID_VERSION_CODE, 10003)
        for name in CANONICAL:
            with self.subTest(path=name):
                doc = (ROOT / name).read_text(encoding="utf-8")
                self.assertIn("0.10.0", doc)
                self.assertIn("https://pypi.org/project/sedrava/0.10.0/", doc)
                self.assertIn("https://github.com/VasiliiBabkin/sedrava/releases/tag/v0.10.0", doc)
                for phrase in NO_STALE:
                    self.assertNotIn(phrase.casefold(), doc.casefold())

    def test_relative_references_exist_in_canonical_docs(self):
        # Only inline Markdown links (not URLs, fenced code, or image references).
        for name in CANONICAL:
            path = ROOT / name
            doc = path.read_text(encoding="utf-8")
            for target in re.findall(r"(?<!!)\[[^\]]+\]\(([^)]+)\)", doc):
                target = target.split("#", 1)[0]
                if not target or target.startswith(("https://", "http://", "mailto:", "#")):
                    continue
                with self.subTest(page=name, target=target):
                    self.assertTrue((path.parent / target).exists(), target)


if __name__ == "__main__":
    unittest.main()
