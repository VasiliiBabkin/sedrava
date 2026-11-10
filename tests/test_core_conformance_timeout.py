"""Compiler timeout defaults and bounded test-only override."""
import os
import unittest
from unittest.mock import patch
from core_conformance import kotlin_compile_timeout

SETTING = 'SEDRAVA_KOTLIN_COMPILE_TIMEOUT_SEC'


class TimeoutPolicyTests(unittest.TestCase):
    def test_default_preserves_90_seconds(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(kotlin_compile_timeout(), 90)

    def test_valid_override_for_resource_limited_host(self):
        for seconds in ('90', '180', '240', '300'):
            with self.subTest(seconds=seconds), patch.dict(os.environ, {SETTING: seconds}):
                self.assertEqual(kotlin_compile_timeout(), int(seconds))

    def test_invalid_override_does_not_silently_disable_timeout(self):
        for seconds in ('', '0', '-1', '89', '301', '9999', '1.5', 'abc', ' 180 ', '１８０'):
            with self.subTest(seconds=seconds), patch.dict(os.environ, {SETTING: seconds}):
                with self.assertRaises(ValueError):
                    kotlin_compile_timeout()


if __name__ == '__main__':
    unittest.main()
