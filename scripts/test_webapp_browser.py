"""Real Chromium B1 acceptance: state, forms, actions, persistence and safety."""
import functools
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import shutil
import tempfile
import threading
import unittest
import os

from playwright.sync_api import sync_playwright
from sedrava_webapp import build_webapp


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "examples/webapp_011_counter.sdr"


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


class WebAppBrowser(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory(prefix="sedrava-webapp-")
        cls.out = Path(cls.folder.name) / "app"
        build_webapp(SOURCE.read_text(encoding="utf-8"), cls.out, SOURCE)
        cls.server = ThreadingHTTPServer(
            ("127.0.0.1", 0),
            functools.partial(QuietHandler, directory=cls.folder.name))
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(
            executable_path=os.environ.get("SEDRAVA_CHROMIUM") or shutil.which("chromium"),
            args=["--no-sandbox"])
        cls.url = f"http://127.0.0.1:{cls.server.server_port}/app/index.html"
        cls.evidence = ROOT / "build/webapp-evidence"
        cls.evidence.mkdir(parents=True, exist_ok=True)
        (cls.evidence / "tools.json").write_text(
            json.dumps({"browser": cls.browser.version, "target": "webapp",
                        "source": str(SOURCE.relative_to(ROOT))}, indent=2) + "\n")

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        cls.folder.cleanup()

    def setUp(self):
        self.context = self.browser.new_context()
        self.page = self.context.new_page()
        self.errors = []
        self.page.on("pageerror", lambda e: self.errors.append(str(e)))
        self.page.goto(self.url, wait_until="domcontentloaded")

    def tearDown(self):
        screenshot = self.evidence / (self._testMethodName + ".png")
        self.page.screenshot(path=str(screenshot), full_page=True)
        self.context.close()
        self.assertEqual(self.errors, [], "Unhandled browser exceptions")

    def counter(self):
        return self.page.locator('output[data-state="count"]').inner_text()

    def test_action_derived_state_and_persistence(self):
        page = self.page
        self.assertEqual(self.counter(), "0")
        self.assertEqual(page.locator('output[data-state="double_count"]').inner_text(), "0")
        page.get_by_role("button", name="Add").click()
        page.get_by_role("button", name="Add").click()
        self.assertEqual(self.counter(), "2")
        self.assertEqual(page.locator('output[data-state="double_count"]').inner_text(), "4")
        page.reload()
        self.assertEqual(self.counter(), "2")
        page.get_by_role("button", name="Subtract").click()
        self.assertEqual(self.counter(), "1")
        other = self.context.new_page()
        other.goto(self.url)
        self.assertEqual(other.locator('output[data-state="count"]').inner_text(), "1")
        other.close()
        page.get_by_role("button", name="Reset").click()
        page.reload()
        self.assertEqual(self.counter(), "0")

    def test_invalid_value_rejected_and_preserves_state(self):
        page = self.page
        page.get_by_role("button", name="Add").click()
        field = page.get_by_label("Edit count")
        field.fill("101")
        self.assertEqual(self.counter(), "1")
        self.assertEqual(field.get_attribute("aria-invalid"), "true")
        self.assertTrue(page.get_by_role("button", name="Reset").is_disabled())
        self.assertTrue(page.get_by_role("alert").filter(has_text="Value rejected").is_visible())
        field.blur()
        self.assertEqual(field.input_value(), "1")
        self.assertTrue(page.get_by_role("button", name="Reset").is_enabled())
        field.fill("-100")
        self.assertEqual(self.counter(), "-100")
        page.get_by_role("button", name="Subtract").click()
        self.assertEqual(self.counter(), "-100")
        self.assertTrue(page.get_by_role("alert").is_visible())
        page.reload()
        self.assertEqual(self.counter(), "-100")

    def test_checkbox_conditional_and_untrusted_user_text(self):
        page = self.page
        checkbox = page.get_by_role("checkbox", name="Show note")
        field = page.get_by_label("Your note")
        markup = '<img src=x onerror="alert(1)">'
        field.fill(markup)
        self.assertEqual(page.locator('output[data-state="note"]').inner_text(), markup)
        self.assertEqual(page.locator("img").count(), 0)
        checkbox.uncheck()
        self.assertTrue(page.locator("[data-when=show_note]").is_hidden())
        page.reload()
        self.assertFalse(checkbox.is_checked())
        self.assertTrue(page.locator("[data-when=show_note]").is_hidden())
        checkbox.check()
        self.assertTrue(page.locator("[data-when=show_note]").is_visible())
        self.assertEqual(page.locator('output[data-state="note"]').inner_text(), markup)

    def test_corrupt_storage_is_preserved_not_overwritten(self):
        page = self.page
        page.evaluate("localStorage.setItem(storageKey,'{broken')")
        page.reload()
        self.assertTrue(page.locator("#sedrava-error").is_visible())
        page.get_by_role("button", name="Add").click()
        self.assertEqual(page.evaluate("localStorage.getItem(storageKey)"), "{broken")
        self.assertIn("stored data retained", page.locator("#sedrava-error").inner_text())

    def test_responsive_keyboard_and_local_scripts(self):
        page = self.page
        requests = []
        page.on("request", lambda r: requests.append(r.url))
        for width in (360, 768, 1440):
            page.set_viewport_size({"width": width, "height": 800})
            page.reload()
            self.assertLessEqual(
                page.evaluate("document.documentElement.scrollWidth"), width + 1)
            self.assertEqual(page.locator("h1").count(), 1)
            self.assertEqual(page.locator("script[src='app.js']").count(), 1)
            self.assertEqual(page.locator("script:not([src])").count(), 0)
            self.assertTrue(page.get_by_role("button", name="Add").is_enabled())
        page.get_by_role("button", name="Add").focus()
        page.keyboard.press("Enter")
        self.assertEqual(self.counter(), "1")
        self.assertTrue(all(url.startswith(
            f"http://127.0.0.1:{self.server.server_port}/") for url in requests))


if __name__ == "__main__":
    unittest.main()
