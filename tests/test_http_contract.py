"""Initial contract tests for external HTTP API declarations."""
import unittest
from sedrava_http import ApiService


class ApiContractTests(unittest.TestCase):
    def test_public_https_service(self):
        service = ApiService("articles", "https://api.example.com", "/v1/articles")
        self.assertEqual(service.url, "https://api.example.com/v1/articles")
        self.assertEqual(service.timeout_ms, 10000)

    def test_reject_unsafe_origins(self):
        for origin in (
            "http://api.example.com", "https://localhost", "https://127.0.0.1",
            "https://10.0.0.1", "https://192.168.1.1", "https://user:pass@example.com",
            "https://api.example.com/path", "https://api.example.com?token=x",
            "https://api.example.com:8443", "https://api.example.com.",
            "https://-bad.example.com", "https://example.com#fragment",
        ):
            with self.subTest(origin=origin), self.assertRaises(ValueError):
                ApiService("x", origin, "/")

    def test_reject_unsafe_paths(self):
        for path in ("https://evil.test/", "//evil.test", "/../x", "/./x",
                     "/%2e%2e/x", "/%2Fsecret", "/a?secret=x", "/x#hash",
                     "/a\\b", "/a\nb"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                ApiService("x", "https://api.example.com", path)

    def test_reject_invalid_limits_and_names(self):
        for name in ("", "1bad", "a-b", "a"*65):
            with self.assertRaises(ValueError):ApiService(name,"https://api.example.com","/")
        for timeout in (0, 99, 30001, True):
            with self.assertRaises(ValueError):ApiService("x","https://api.example.com","/",timeout_ms=timeout)
        for size in (0, 1048577, False):
            with self.assertRaises(ValueError):ApiService("x","https://api.example.com","/",max_bytes=size)


if __name__ == "__main__":
    unittest.main()
