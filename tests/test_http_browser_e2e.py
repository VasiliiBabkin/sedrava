"""Browser end-to-end test for the experimental API0 generated page.

Run: python -m unittest tests.test_http_browser_e2e -v
Requires: pip install playwright && python -m playwright install chromium
"""
import contextlib
import os
import shutil
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
                browser = playwright.chromium.launch(headless=True, executable_path=os.environ.get("SEDRAVA_CHROMIUM") or shutil.which("chromium"), args=["--no-sandbox"])
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

    def test_embedded_localized_cards_empty_error_and_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            app = Path("examples/task_manager_navigation.sdr").read_text(encoding="utf-8")
            display = '''    display cards:
        heading "Новости"
        loading "Загрузка"
        empty "Нет записей"
        error "Ошибка сети"
        title
'''
            source = folder / "app.sdr"
            source.write_text(app.rstrip() + "\n\n" + SOURCE + display, encoding="utf-8")
            output = folder / "public" / "index.html"
            self.assertEqual(main(["check", str(source)]), 0)
            self.assertEqual(main(["build", "web", str(source), "--output", str(output)]), 0)
            with serve(output.parent) as url, sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True, executable_path=os.environ.get("SEDRAVA_CHROMIUM") or shutil.which("chromium"), args=["--no-sandbox"])
                try:
                    page = browser.new_page()
                    state = {"code": 200, "payload": [{"id": 1, "title": "<script>alert(1)</script>"}]}
                    def route_api(route):
                        route.fulfill(status=state["code"], content_type="application/json",
                                      body=__import__("json").dumps(state["payload"]))
                    page.route("https://api.example.com/posts", route_api)
                    page.goto(url, wait_until="load")
                    panel = page.locator("#sedrava-api-panel")
                    self.assertEqual(panel.locator("h2").inner_text(), "Новости")
                    panel.locator("#sedrava-api-status").get_by_text("Loaded 1 record(s)").wait_for()
                    self.assertEqual(panel.locator("article").count(), 1)
                    self.assertEqual(panel.locator("article dt").all_inner_texts(), ["title"])
                    self.assertIn("<script>alert(1)</script>", panel.locator("article").inner_text())
                    self.assertEqual(panel.locator("article script").count(), 0)
                    state["payload"] = []
                    panel.get_by_role("button", name="Reload external data").click()
                    panel.get_by_text("Нет записей").wait_for()
                    self.assertEqual(panel.locator("article").count(), 0)
                    state["code"] = 500
                    panel.get_by_role("button", name="Reload external data").click()
                    panel.get_by_text("Ошибка сети").wait_for()
                    state["code"] = 200
                    state["payload"] = [{"id": 2, "title": "Recovered"}]
                    panel.get_by_role("button", name="Reload external data").click()
                    panel.locator("#sedrava-api-status").get_by_text("Loaded 1 record(s)").wait_for()
                    self.assertIn("Recovered", panel.locator("article").inner_text())
                finally:
                    browser.close()
