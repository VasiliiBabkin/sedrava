"""Pre-emulator tests for Android and reproducibility benchmark helpers."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AndroidBaselineTests(unittest.TestCase):
    def test_kotlin_scaffold_has_valid_source_and_manifest(self):
        script = load("kotlin_scaffold", "benchmarks/agent/prepare_kotlin_android_baseline.py")
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "android"
            script.prepare(output)
            source = output / "app/src/main/java/org/sedrava/benchmark/kotlin/MainActivity.kt"
            self.assertIn("Math.addExact(count, 1)", source.read_text())
            self.assertIn('button("Reset")', source.read_text())
            self.assertIn('applicationId = "org.sedrava.benchmark.kotlin"',
                          (output / "app/build.gradle.kts").read_text())
            self.assertIn('android:exported="true"',
                          (output / "app/src/main/AndroidManifest.xml").read_text())
            with self.assertRaises(ValueError):
                script.prepare(output)

    def test_device_evaluator_is_framework_neutral(self):
        script = load("device_evaluator", "benchmarks/agent/acceptance/counter_android_device.py")
        self.assertEqual(script.COUNT.fullmatch("count: -42").group(1), "-42")
        self.assertIsNone(script.COUNT.fullmatch("unrelated 42"))
        self.assertEqual(script.BOUNDS.fullmatch("[1,2][31,42]").groups(),
                         ("1", "2", "31", "42"))
        xml = ET.fromstring(
            '<hierarchy><node text="count: -1" bounds="[0,0][100,50]"/>'
            '<node text="Add" bounds="[0,50][100,100]"/></hierarchy>')
        self.assertEqual(script.observed_count(xml), -1)
        self.assertEqual(len(script.nodes_with_text(xml, "Add")), 1)

    def test_trial_bundle_records_hashes_without_claiming_agent_run(self):
        script = load("trial_bundle", "benchmarks/agent/prepare_trial_bundle.py")
        from argparse import Namespace
        with tempfile.TemporaryDirectory() as tmp:
            args = Namespace(
                task="counter-v0", target="web", language="sedrava",
                commit="a" * 40, trial_id="sedrava-web-001",
                model="test-model", agent="test-agent", seed=1,
                temperature="not exposed", toolchain="test",
                seconds=300, tokens=12000, attempts=3,
                starter=["examples/counter.sdr"],
                reference=["docs/QUICKSTART.md"],
                output=Path(tmp) / "trial")
            script.prepare(args)
            manifest = json.loads((args.output / "manifest.json").read_text())
            self.assertEqual(manifest["outcome"], "not_run")
            self.assertEqual(len(manifest["starters"][0]["sha256"]), 64)
            self.assertIn("Implement", (args.output / "prompt.md").read_text())
            with self.assertRaises(FileExistsError):
                script.prepare(args)


if __name__ == "__main__":
    unittest.main()
