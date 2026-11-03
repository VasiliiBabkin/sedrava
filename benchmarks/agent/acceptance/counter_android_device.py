"""Framework-neutral Android device acceptance for counter-v0 (ADB/UIAutomator).

The test inspects the visible screen hierarchy, not application source,
preferences, generated state classes, or framework-specific test hooks.
Requires exactly one attached booted emulator/device and an existing APK.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time
import xml.etree.ElementTree as ET


COUNT = re.compile(r"^count:\s*(-?[0-9]+)$")
BOUNDS = re.compile(r"^\[(\d+),(\d+)\]\[(\d+),(\d+)\]$")
DUMP_PATH = "/sdcard/agent-benchmark-ui.xml"


def adb(*args, timeout=35):
    result = subprocess.run(["adb", *args], capture_output=True, text=True,
                            encoding="utf-8", errors="replace", timeout=timeout)
    if result.returncode:
        raise RuntimeError("adb " + " ".join(args) + ": " +
                           (result.stderr or result.stdout).strip()[:1000])
    return result.stdout.strip()


def hierarchy():
    adb("shell", "uiautomator", "dump", DUMP_PATH, timeout=45)
    return ET.fromstring(adb("shell", "cat", DUMP_PATH))


def nodes_with_text(root, text):
    return [node for node in root.iter("node")
            if node.get("text") == text or node.get("content-desc") == text]


def observed_count(root):
    values = []
    for node in root.iter("node"):
        match = COUNT.fullmatch(node.get("text", ""))
        if match:
            values.append(int(match.group(1)))
    if len(values) != 1:
        raise AssertionError("Expected one visible 'count: N', found " + repr(values))
    return values[0]


def wait_for_count(expected, case, observations):
    deadline = time.monotonic() + 20
    last = "not observed"
    while time.monotonic() < deadline:
        try:
            actual = observed_count(hierarchy())
            last = str(actual)
            if actual == expected:
                observations.append({"case": case, "expected": expected, "actual": actual})
                return
        except (RuntimeError, ET.ParseError, AssertionError) as exc:
            last = str(exc)
        time.sleep(0.3)
    raise AssertionError(case + ": expected " + str(expected) + ", got " + last)


def press(label):
    root = hierarchy()
    matches = nodes_with_text(root, label)
    if len(matches) != 1:
        raise AssertionError("Expected one control labelled " + repr(label) +
                             ", found " + str(len(matches)))
    match = BOUNDS.fullmatch(matches[0].get("bounds", ""))
    if not match:
        raise AssertionError("Invalid UI bounds for " + label)
    x1, y1, x2, y2 = map(int, match.groups())
    if x2 <= x1 or y2 <= y1:
        raise AssertionError("Empty UI bounds for " + label)
    adb("shell", "input", "tap", str((x1 + x2) // 2), str((y1 + y2) // 2))


def launch(package, activity):
    adb("shell", "am", "start", "-W", "-n", package + "/" + activity)


def exercise(package, activity, observations):
    adb("shell", "pm", "clear", package)
    launch(package, activity)
    wait_for_count(0, "A01", observations)
    press("Add")
    wait_for_count(1, "A02", observations)
    press("Subtract")
    press("Subtract")
    wait_for_count(-1, "A03", observations)
    press("Reset")
    wait_for_count(0, "A04", observations)
    for _ in range(3):
        press("Add")
    press("Subtract")
    wait_for_count(2, "A05", observations)
    adb("shell", "am", "force-stop", package)
    launch(package, activity)
    wait_for_count(2, "A06", observations)
    adb("shell", "input", "keyevent", "KEYCODE_HOME")
    launch(package, activity)
    wait_for_count(2, "A07", observations)
    press("Reset")
    adb("shell", "am", "force-stop", package)
    launch(package, activity)
    wait_for_count(0, "A08", observations)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apk", required=True, type=Path)
    parser.add_argument("--package", required=True)
    parser.add_argument("--activity", default=".MainActivity")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    report = {"contract": "counter-android-v0", "package": args.package,
              "passed": False, "observations": [], "error": None,
              "apk_sha256": None, "api_level": None, "build_fingerprint": None}
    try:
        if not args.apk.is_file():
            raise FileNotFoundError(str(args.apk))
        report["apk_sha256"] = hashlib.sha256(args.apk.read_bytes()).hexdigest()
        report["api_level"] = adb("shell", "getprop", "ro.build.version.sdk")
        report["build_fingerprint"] = adb("shell", "getprop", "ro.build.fingerprint")
        adb("install", "-r", str(args.apk.resolve()), timeout=120)
        exercise(args.package, args.activity, report["observations"])
        if len(report["observations"]) != 8:
            raise AssertionError("Incomplete acceptance evidence")
        report["passed"] = True
    except Exception as exc:
        report["error"] = type(exc).__name__ + ": " + str(exc)
        try:
            screenshot = args.output.with_suffix(".png")
            with screenshot.open("wb") as handle:
                subprocess.run(["adb", "exec-out", "screencap", "-p"], stdout=handle,
                               stderr=subprocess.DEVNULL, timeout=20)
        except Exception:
            pass
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "cases": len(report["observations"]),
                      "error": report["error"]}, ensure_ascii=False), flush=True)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
