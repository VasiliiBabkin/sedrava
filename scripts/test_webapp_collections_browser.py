"""Real Chromium acceptance for Sedrava WebApp 0.11 record/list CRUD."""
import functools
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import unittest

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sedrava_webapp import build_webapp

SOURCE = ROOT / "examples/webapp_011_tasks.sdr"


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


class WebAppCollectionsBrowser(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory(prefix="sedrava-webapp-records-")
        source = SOURCE.read_text(encoding="utf-8")
        build_webapp(source, Path(cls.folder.name) / "tasks", SOURCE)
        build_webapp(source.replace("max=100", "max=2"),
                     Path(cls.folder.name) / "capacity", SOURCE)
        handler = functools.partial(QuietHandler, directory=cls.folder.name)
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(
            executable_path=os.environ.get("SEDRAVA_CHROMIUM") or shutil.which("chromium"),
            args=["--no-sandbox"])
        cls.base = f"http://127.0.0.1:{cls.server.server_port}/"
        cls.evidence = ROOT / "build/webapp-evidence"
        cls.evidence.mkdir(parents=True, exist_ok=True)
        (cls.evidence / "collections-tools.json").write_text(json.dumps(
            {"browser": cls.browser.version, "source": str(SOURCE.relative_to(ROOT))},
            sort_keys=True, indent=2) + "\n", encoding="utf-8")

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
        self.page.goto(self.base + "tasks/index.html", wait_until="domcontentloaded")
        self.assertTrue(self.page.get_by_role("heading", name="Tasks on Sedrava").is_visible())

    def tearDown(self):
        self.page.screenshot(path=str(self.evidence / (self._testMethodName + ".png")), full_page=True)
        self.context.close()
        self.assertEqual(self.errors, [], "Unhandled browser exceptions")

    def add(self, title):
        self.page.get_by_label("New task").fill(title)
        self.page.get_by_role("button", name="Add task").click()

    def test_crud_and_persistence(self):
        p = self.page
        self.assertEqual(p.locator('output[data-state="task_count"]').inner_text(), "0")
        self.assertTrue(p.get_by_text("No tasks yet. Create your first task.").is_visible())
        self.assertTrue(p.locator('[data-when="chosen"]').is_hidden())
        self.add("First task")
        self.assertEqual(p.locator('[data-list="tasks"] li').count(), 1)
        self.assertEqual(p.locator('output[data-state="task_count"]').inner_text(), "1")
        self.assertTrue(p.get_by_text("In progress", exact=True).is_visible())
        self.assertTrue(p.get_by_text("No tasks yet. Create your first task.").is_hidden())
        p.get_by_role("button", name="Select First task").click()
        self.assertEqual(p.locator('[data-list="tasks"] button[aria-pressed=true]').count(), 1)
        self.assertTrue(p.locator('[data-when="chosen"]').is_visible())
        p.get_by_label("Rename selected task").fill("Renamed task")
        p.get_by_role("button", name="Rename task").click()
        self.assertTrue(p.get_by_role("button", name="Select Renamed task").is_visible())
        p.get_by_role("button", name="Toggle completion").click()
        self.assertTrue(p.get_by_text("Completed", exact=True).is_visible())
        p.reload()
        self.assertEqual(p.locator('output[data-state="task_count"]').inner_text(), "1")
        self.assertTrue(p.get_by_role("button", name="Select Renamed task").is_visible())
        self.assertTrue(p.get_by_text("Completed", exact=True).is_visible())
        self.assertTrue(p.locator('[data-when="chosen"]').is_hidden())
        p.get_by_role("button", name="Select Renamed task").click()
        p.get_by_role("button", name="Delete task").click()
        self.assertEqual(p.locator('[data-list="tasks"] li').count(), 0)
        self.assertEqual(p.locator('output[data-state="task_count"]').inner_text(), "0")
        p.reload()
        self.assertEqual(p.locator('[data-list="tasks"] li').count(), 0)

    def test_capacity_guard_and_atomic_rollback(self):
        self.page.goto(self.base + "capacity/index.html", wait_until="domcontentloaded")
        self.add("One")
        self.add("Two")
        self.assertEqual(self.page.locator('[data-list="tasks"] li').count(), 2)
        self.add("Overflow")
        self.assertEqual(self.page.locator('[data-list="tasks"] li').count(), 2)
        self.assertTrue(self.page.locator("#sedrava-error").is_visible())
        self.assertEqual(self.page.get_by_role("button", name="Select Overflow").count(), 0)
        self.page.reload()
        self.assertEqual(self.page.locator('[data-list="tasks"] li').count(), 2)

    def test_xss_and_rejected_draft(self):
        p = self.page
        field = p.get_by_label("New task")
        field.fill("😀" * 1025)
        self.assertEqual(field.get_attribute("aria-invalid"), "true")
        self.assertTrue(p.get_by_role("button", name="Add task").is_disabled())
        self.assertEqual(p.locator('[data-list="tasks"] li').count(), 0)
        field.blur()
        self.assertEqual(field.get_attribute("aria-invalid"), "false")
        payload = '<img src=x onerror="alert(1)">'
        self.add(payload)
        self.assertEqual(p.locator('[data-list="tasks"] .s-list-title').inner_text(), payload)
        self.assertEqual(p.locator("img").count(), 0)
        p.reload()
        self.assertEqual(p.locator('[data-list="tasks"] .s-list-title').inner_text(), payload)
        self.assertEqual(p.locator("img").count(), 0)

    def test_keyboard_focus_and_responsive_width(self):
        self.add("Keyboard")
        p = self.page
        for width in (360, 768, 1440):
            p.set_viewport_size({"width": width, "height": 800})
            p.reload()
            self.assertLessEqual(p.evaluate("document.documentElement.scrollWidth"), width + 1)
            self.assertEqual(p.locator("h1").count(), 1)
            self.assertEqual(p.locator("[data-list] button").count(), 1)
        row = p.get_by_role("button", name="Select Keyboard")
        row.focus()
        p.keyboard.press("Enter")
        self.assertEqual(row.get_attribute("aria-pressed"), "true")
        self.assertTrue(row.evaluate("(el)=>document.activeElement===el"))
        self.assertTrue(p.locator('[data-when="chosen"]').is_visible())

    def test_corrupted_storage_is_retained(self):
        self.add("Original")
        p = self.page
        saved = p.evaluate("localStorage.getItem(storageKey)")
        self.assertIsNotNone(saved)
        p.evaluate("localStorage.setItem(storageKey,'{broken')")
        p.reload()
        self.assertTrue(p.locator("#sedrava-error").is_visible())
        self.add("New")
        self.assertEqual(p.evaluate("localStorage.getItem(storageKey)"), "{broken")
        self.assertIn("retained", p.locator("#sedrava-error").inner_text())
        self.assertIn('"Original"', saved)


if __name__ == "__main__":
    unittest.main()
