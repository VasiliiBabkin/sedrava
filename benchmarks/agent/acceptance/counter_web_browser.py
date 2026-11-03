"""Independent browser acceptance evaluator for counter-v0.

Run against an already served candidate URL. Requires Playwright and Chromium.
No framework-specific storage keys or application source are inspected.
"""
import argparse
import json
import pathlib
import sys
import time


def evaluate(page, url, value_selector, buttons):
    observations = []

    def expect(expected, case):
        locator = page.locator(value_selector)
        if locator.count() != 1:
            raise AssertionError(f"{case}: expected one count display, got {locator.count()}")
        actual = locator.inner_text().strip()
        if actual != str(expected):
            raise AssertionError(f"{case}: expected {expected}, got {actual!r}")
        observations.append({"case": case, "expected": expected, "actual": actual})

    def press(action):
        page.get_by_role("button", name=buttons[action], exact=True).click()

    page.goto(url, wait_until="domcontentloaded")
    expect(0, "C01")
    press("increment")
    expect(1, "C02")
    press("decrement")
    press("decrement")
    expect(-1, "C03")
    press("reset")
    expect(0, "C04")
    for _ in range(3):
        press("increment")
    press("decrement")
    expect(2, "C05")
    page.reload(wait_until="domcontentloaded")
    expect(2, "C06")
    page.close()
    page = page.context.new_page()
    page.set_default_timeout(5000)
    page.goto(url, wait_until="domcontentloaded")
    expect(2, "C07")
    press("reset")
    page.reload(wait_until="domcontentloaded")
    expect(0, "C08")
    return observations


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True, help="Locally served candidate URL")
    parser.add_argument("--value-selector", required=True,
                        help="CSS selector for the single visible count")
    parser.add_argument("--increment-label", required=True)
    parser.add_argument("--decrement-label", required=True)
    parser.add_argument("--reset-label", required=True)
    parser.add_argument("--output", required=True, type=pathlib.Path)
    parser.add_argument("--chromium", default=None, help="Optional Chromium executable path")
    args = parser.parse_args(argv)
    if not args.url.startswith(("http://127.0.0.1:", "http://localhost:")):
        parser.error("Only local HTTP candidates are supported")
    try:
        from playwright.sync_api import sync_playwright
        import importlib.metadata
    except ImportError:
        print("Install playwright and its Chromium browser first", file=sys.stderr)
        return 2
    report = {"contract": "counter-web-v0", "url": args.url, "passed": False,
              "observations": [], "error": None, "browser_version": None,
              "playwright_version": importlib.metadata.version("playwright")}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                executable_path=args.chromium, args=["--no-sandbox"])
            report["browser_version"] = browser.version
            context = browser.new_context()
            page = context.new_page()
            page.set_default_timeout(5000)
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            report["observations"] = evaluate(
                page, args.url, args.value_selector,
                {"increment": args.increment_label, "decrement": args.decrement_label,
                 "reset": args.reset_label})
            if errors:
                raise AssertionError("Browser exceptions: " + "; ".join(errors))
            report["passed"] = True
            context.close()
            browser.close()
    except Exception as exc:
        report["error"] = type(exc).__name__ + ": " + str(exc)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "error": report["error"],
                      "cases": len(report["observations"])}, ensure_ascii=False))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
