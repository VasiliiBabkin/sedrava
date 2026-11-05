"""Version identity, monotonic Android metadata, pinned release and docs."""
import unittest
from pathlib import Path
from sedrava_version import VERSION, ANDROID_VERSION_CODE
from scripts.check_rc_to_stable_011 import RC, FINAL, PUBLISHED

ROOT = Path(__file__).resolve().parents[1]
class StableRelease011Tests(unittest.TestCase):
    def test_identity_and_strict_android_upgrade_order(self):
        if VERSION == "0.12.0a1":
            self.assertEqual(ANDROID_VERSION_CODE, 12001)
        else:
            self.assertEqual((VERSION, ANDROID_VERSION_CODE), ("0.11.0", 11002))
        self.assertEqual((RC, FINAL), ("0.11.0rc1", "0.11.0"))
        self.assertTrue(10003 < 11001 < ANDROID_VERSION_CODE)
    def test_original_rc_artifacts_are_pinned(self):
        self.assertEqual(len(PUBLISHED), 2)
        for name, sha in PUBLISHED.items():
            self.assertIn("0.11.0rc1", name)
            self.assertRegex(sha, r"^[a-f0-9]{64}$")
    def test_stable_gates_and_bilingual_notes(self):
        for filename in ("docs/RELEASE_TRACK_011.md",
                         "docs/STABLE_RELEASE_GATES_011.md",
                         "docs/RELEASE_NOTES_0_11_0.en.md",
                         "docs/RELEASE_NOTES_0_11_0.ru.md"):
            content = (ROOT / filename).read_text(encoding="utf-8")
            for version in ("0.10.0","0.11.0rc1","0.11.0"):
                self.assertIn(version, content)
if __name__ == "__main__":
    unittest.main()
