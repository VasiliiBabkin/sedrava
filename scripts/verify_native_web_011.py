"""Compare Python 0.11 and native builds in real Chromium over loopback HTTP."""
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import shutil
import subprocess
import sys
from urllib.parse import urljoin
from tempfile import TemporaryDirectory
from threading import Thread

from playwright.sync_api import expect, sync_playwright


ROOT = Path(__file__).resolve().parents[1]
from legacy_reference import legacy_root
COMPILERS = {
    "python": None,  # resolve only when rebuilding historical sources
    "rust": [str(ROOT / "rust/target/debug/sedrava")],
}
CASES = {
    "platform_site": "site",
    "web_ui_011_landing": "site",
    "webapp_011_counter": "webapp",
    "webapp_011_tasks": "webapp",
    "platform_tasks": "webapp",
    "platform_crm": "webapp",
}
TEXT = '<img src="missing.png" onerror="void(0)">'


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_):
        pass


def invoke(engine, *args, reject=False):
    compiler = COMPILERS[engine] or [sys.executable, str(legacy_root() / "sedrava_cli.py")]
    result = subprocess.run(
        [*compiler, *map(str, args)],
        cwd=ROOT, capture_output=True, text=True, timeout=20,
    )
    assert (result.returncode != 0) == reject, (engine, args, result.stdout, result.stderr)
    return result.stderr


def build(root, engine, name, mode):
    source = ROOT / "examples" / (name + ".sdr")
    output = root / engine / name
    invoke(engine, "check", source)
    invoke(engine, "build", mode, source, "--output", output)
    return output


def verify_reproducible_builds(root):
    for case, mode in CASES.items():
        source = ROOT / "examples" / (case + ".sdr")
        original = root / "rust" / case
        repeated = root / "repeated" / case
        invoke("rust", "build", mode, source, "--output", repeated)
        expected = {p.relative_to(original): p.read_bytes()
                    for p in original.rglob("*") if p.is_file()}
        actual = {p.relative_to(repeated): p.read_bytes()
                  for p in repeated.rglob("*") if p.is_file()}
        assert actual == expected, case
        invoke("rust", "build", mode, source, "--output", original, reject=True)
        assert {p.relative_to(original): p.read_bytes()
                for p in original.rglob("*") if p.is_file()} == expected, case
    print(f"PASS: {len(CASES)} deterministic native output trees and overwrite rejections")


def site_view(page, platform):
    if platform:
        assert page.locator('link[rel="canonical"]').get_attribute("href") == "https://preview.example.com/"
        assert page.locator('meta[name="color-scheme"]').get_attribute("content") == "light"
        assert page.evaluate("document.fonts.check('16px PlatformInter')")
        assert page.get_by_role("heading", name="Sites", exact=True).is_visible()
        assert page.locator("img").evaluate("(img) => img.naturalWidth") > 0
        assert page.request.get(urljoin(page.url, "robots.txt")).text().startswith("User-agent: *\nDisallow: /")
        assert "https://preview.example.com/journal/" in page.request.get(urljoin(page.url, "sitemap.xml")).text()
        link = "Read the guide"
    else:
        assert page.locator('meta[name="color-scheme"]').get_attribute("content") == "dark"
        link = "Components"
    sizes = []
    for width in (360, 800, 1200):
        page.set_viewport_size({"width": width, "height": 850})
        sizes.append(page.locator(".s-grid").first.evaluate(
            "(el) => getComputedStyle(el).gridTemplateColumns.split(' ').length"
        ))
        assert page.evaluate("document.documentElement.scrollWidth") <= width + 1
    assert sizes == ([1, 2, 3] if platform else [1, 1, 2])
    page.get_by_role("link", name=link, exact=True).click()
    expect(page.locator("main h1")).to_be_visible()
    assert page.url.endswith(("/guide/index.html", "/components/index.html"))
    assert page.locator("script").count() == 0


def value(page, name, expected):
    expect(page.locator(f'output[data-state="{name}"]')).to_have_text(str(expected))


def counter(page):
    value(page, "count", 0)
    page.get_by_role("button", name="Add", exact=True).press("Enter")
    value(page, "count", 1)
    value(page, "double_count", 2)
    field = page.get_by_label("Edit count")
    field.fill("101")
    expect(field).to_have_attribute("aria-invalid", "true")
    expect(page.get_by_role("button", name="Reset")).to_be_disabled()
    value(page, "count", 1)
    field.blur()
    expect(field).to_have_value("1")
    field.fill("-100")
    page.get_by_role("button", name="Subtract").click()
    value(page, "count", -100)
    expect(page.locator("#sedrava-error")).to_be_visible()
    page.get_by_label("Your note").fill(TEXT)
    value(page, "note", TEXT)
    assert page.locator("img").count() == 0
    page.get_by_role("checkbox", name="Show note").uncheck()
    page.reload()
    value(page, "count", -100)
    expect(page.locator("[data-when=show_note]")).to_be_hidden()
    page.get_by_role("checkbox", name="Show note").check()
    value(page, "note", TEXT)
    page.evaluate("localStorage.setItem(storageKey, '{broken')")
    page.reload()
    expect(page.locator("#sedrava-error")).to_be_visible()
    page.get_by_role("button", name="Add", exact=True).click()
    assert page.evaluate("localStorage.getItem(storageKey)") == "{broken"


def tasks(page):
    value(page, "task_count", 0)
    page.get_by_label("New task").fill(TEXT)
    page.get_by_role("button", name="Add task").click()
    value(page, "task_count", 1)
    row = page.get_by_role("button", name="Select " + TEXT, exact=True)
    row.press("Enter")
    expect(row).to_have_attribute("aria-pressed", "true")
    expect(row).to_be_focused()
    assert page.locator("img").count() == 0
    page.get_by_label("Rename selected task").fill("Updated")
    page.get_by_role("button", name="Rename task").click()
    page.get_by_role("button", name="Toggle completion").click()
    page.reload()
    expect(page.get_by_text("Completed", exact=True)).to_be_visible()
    value(page, "task_count", 1)
    page.get_by_role("button", name="Select Updated").click()
    page.get_by_role("button", name="Delete task").click()
    page.reload()
    value(page, "task_count", 0)


def routed_tasks(page):
    for title in ("Zebra", "Ada"):
        page.get_by_label("New task").fill(title)
        page.get_by_role("button", name="Add task").click()
    assert page.locator("[data-row-field=title]").all_text_contents() == ["Ada", "Zebra"]
    page.get_by_label("Search tasks").fill("ADA")
    expect(page.locator("[data-row-field=title]")).to_have_text("Ada")
    page.get_by_role("button", name="Toggle Ada", exact=True).click()
    expect(page.get_by_text("Completed", exact=True).filter(visible=True)).to_be_visible()
    page.get_by_role("button", name="Open selected task").click()
    page.wait_for_url("**#/tasks/2")
    page.reload()
    expect(page.get_by_role("heading", name="Task details")).to_be_visible()
    page.get_by_role("button", name="Delete task", exact=True).click()
    expect(page.get_by_role("dialog")).to_be_visible()
    page.keyboard.press("Escape")
    expect(page.get_by_role("dialog")).to_be_hidden()
    page.get_by_role("button", name="Delete task", exact=True).click()
    page.get_by_role("button", name="Confirm delete").click()
    page.wait_for_url("**#/")
    value(page, "task_count", 1)
    page.goto(page.url.replace("#/", "#/tasks/2"))
    page.wait_for_url("**#/")
    expect(page.locator("#sedrava-error")).to_be_visible()


def crm(page):
    page.get_by_role("button", name="Companies", exact=True).click()
    page.get_by_label("Company name", exact=True).fill("Cooper")
    page.get_by_label("Industry").fill("Design")
    page.get_by_role("button", name="Add company").click()
    table = page.get_by_role("table", name="Company directory")
    expect(table.get_by_role("columnheader")).to_have_text(["name", "industry"])
    table.get_by_role("button", name="Select Cooper").click()
    page.get_by_role("button", name="Rename company", exact=True).click()
    dialog = page.get_by_role("dialog", name="Rename selected company")
    dialog.get_by_label("New company name").fill("Cooper Studio")
    dialog.get_by_role("button", name="Save company name").click()
    dialog.get_by_role("button", name="Close company editor").click()
    expect(table.get_by_role("button", name="Select Cooper Studio")).to_be_visible()
    page.get_by_role("button", name="Back to dashboard").click()
    page.wait_for_url("**#/")
    page.get_by_role("button", name="Settings", exact=True).click()
    selector = page.locator("select[data-choice=theme_mode]")
    selector.select_option(label="Dark")
    expect(page.locator("html")).to_have_attribute("data-theme", "dark")
    page.reload()
    expect(page.locator("html")).to_have_attribute("data-theme", "dark")


def negative(root):
    folder = root / "negative"
    folder.mkdir()
    (folder / "unsafe.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg"><foreignObject/></svg>',
        encoding="utf-8",
    )
    (folder / "unsafe.css").write_text('body{background:url("https://example.invalid/a.png")}', encoding="utf-8")
    (folder / "a.sdr").write_text('import "b.sdr"\n', encoding="utf-8")
    (folder / "b.sdr").write_text('import "a.sdr"\n', encoding="utf-8")
    (folder / "linked.sdr").symlink_to(folder / "b.sdr")
    base = 'site "Negative"\npage main at "/":\n    title "Test"\n    heading "Test"\n'
    cases = [
        ("site", base + '    link "Bad" to "//example.invalid/"\n'),
        ("site", base + '    link "Bad" to "/%252e%252e/"\n'),
        ("site", base + '    link "Bad" to "/#missing"\n'),
        ("site", base + '    image "unsafe.svg" alt "Unsafe"\n'),
        ("site", base + '    image "../unsafe.svg" alt "Unsafe"\n'),
        ("site", base + 'stylesheet "unsafe.css"\n'),
        ("site", base + 'import "a.sdr"\n'),
        ("site", base + 'import "linked.sdr"\n'),
        ("site", base + 'component Rec:\n    use Rec\npage other at "/other/":\n    title "T"\n    use Rec\n'),
        ("site", base + '    paragraph "Unsafe" color "#abc;display:none"\n'),
        ("webapp", 'webapp "Route"\nstate id = 0\nview main:\n    heading "T"\n'
                   'view first at "/item/:id":\n    heading "T"\nview second at "/item/1":\n    heading "T"\n'),
        ("webapp", 'webapp "Form"\nstate n = 0\naction add: n = n + 1\nview main:\n'
                   '    heading "T"\n    form action add:\n        form action add:\n            submit "Go"\n'),
        ("webapp", 'webapp "Dialog"\nview main:\n    heading "T"\n    open "Go" to missing\n'),
    ]
    for index, (mode, source) in enumerate(cases):
        path = folder / f"case-{index}.sdr"
        path.write_text(source, encoding="utf-8")
        output = folder / f"output-{index}"
        for engine in COMPILERS:
            invoke(engine, "build", mode, path, "--output", output, reject=True)
            assert not output.exists(), (engine, index)

    print(f"PASS: {len(cases)} shared rejections")


def main():
    with TemporaryDirectory(prefix="sedrava-native-web-") as temporary:
        root = Path(temporary)
        with ThreadPoolExecutor(max_workers=4) as pool:
            jobs = [pool.submit(build, root, engine, case, mode)
                    for engine in COMPILERS for case, mode in CASES.items()]
            for job in jobs:
                job.result()
        verify_reproducible_builds(root)
        for name in ("platform_site", "web_ui_011_landing"):
            for file in (root / "python" / name / "assets").iterdir():
                assert (root / "rust" / name / "assets" / file.name).read_bytes() == file.read_bytes()
        server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=temporary))
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            origin = f"http://127.0.0.1:{server.server_port}"
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(
                    executable_path=os.environ.get("SEDRAVA_CHROMIUM") or shutil.which("chromium"),
                    args=["--no-sandbox"],
                )
                try:
                    for engine in COMPILERS:
                        for case, mode in CASES.items():
                            with browser.new_context() as ctx:
                                page = ctx.new_page()
                                errors = []
                                requests = []
                                page.on("pageerror", lambda error: errors.append(str(error)))
                                page.on("request", lambda request: requests.append(request.url))
                                page.goto(f"{origin}/{engine}/{case}/index.html", wait_until="load")
                                if mode == "site":
                                    site_view(page, case == "platform_site")
                                else:
                                    assert page.locator("script[src='app.js']").count() == 1
                                    assert page.locator("script:not([src])").count() == 0
                                    {
                                        "webapp_011_counter": counter, "webapp_011_tasks": tasks,
                                        "platform_tasks": routed_tasks, "platform_crm": crm,
                                    }[case](page)
                                assert errors == [], (engine, case, errors)
                                assert all(url.startswith(origin + "/") for url in requests), requests
                                print(f"PASS: Chromium {browser.version}, {engine}, {case}")
                finally:
                    browser.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
        negative(root)


if __name__ == "__main__":
    main()
