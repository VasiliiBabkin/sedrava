"""Browser end-to-end test for the experimental API0 generated page.

Run: python -m unittest tests.test_http_browser_e2e -v
Requires: pip install playwright && python -m playwright install chromium
"""
import contextlib
import functools
import http.server
import tempfile
import threading
import unittest
from pathlib import Path
from sedrava_cli import main

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None


SOURCE = '''service posts:
    origin "https://api.example.com"
    path "/posts"
    timeout 2000
    max-bytes 4096
    response many:
        id int32
        title text
'''


@contextlib.contextmanager
def serve(folder):
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(folder))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@unittest.skipUnless(sync_playwright is not None, "Playwright Python package unavailable")
class HttpBrowserE2E(unittest.TestCase):
    def test_loading_success_error_retry_and_safe_render(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            source = folder / "posts.sdr"
            output = folder / "public"
            source.write_text(SOURCE, encoding="utf-8")
            self.assertEqual(main(["build", "api-page", str(source), "--output", str(output)]), 0)
            with serve(output) as url, sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                try:
                    page = browser.new_page()
                    state = {"code": 200, "payload": [{"id": 1, "title": "<img src=x onerror=alert(1)>"}]}
                    def route_api(route):
                        route.fulfill(status=state["code"], content_type="application/json",
                                      body=__import__("json").dumps(state["payload"]))
                    page.route("https://api.example.com/posts", route_api)
                    page.goto(url, wait_until="load")
                    page.wait_for_function("document.querySelector('#status').textContent === 'Loaded 1 record(s)'")
                    self.assertEqual(page.locator("article").count(), 1)
                    self.assertIn("<img src=x", page.locator("article").inner_text())
                    self.assertEqual(page.locator("article img").count(), 0)
                    state["code"] = 500
                    page.get_by_role("button", name="Reload data").click()
                    page.wait_for_function("document.querySelector('#status').textContent.startsWith('Unable to load data')")
                    self.assertEqual(page.locator("article").count(), 0)
                    state["code"] = 200
                    state["payload"] = [{"id": 2, "title": "Recovered"}]
                    page.get_by_role("button", name="Reload data").click()
                    page.wait_for_function("document.querySelector('#status').textContent === 'Loaded 1 record(s)'")
                    self.assertIn("Recovered", page.locator("article").inner_text())
                    state["payload"] = [{"id": True, "title": "Invalid"}]
                    page.get_by_role("button", name="Reload data").click()
                    page.wait_for_function("document.querySelector('#status').textContent.startsWith('Unable to load data')")
                    self.assertEqual(page.locator("article").count(), 0)
                finally:
                    browser.close()
