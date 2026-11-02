"""Unit tests for the agent benchmark's reporting contract."""
import copy
import importlib.util
import json
import pathlib
import tempfile
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("agent_analyze", ROOT / "benchmarks/agent/analyze.py")
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)
SAMPLE = ROOT / "benchmarks/agent/sample-result.json"


class BenchmarkReportingTests(unittest.TestCase):
    def sample(self):
        return json.loads(SAMPLE.read_text(encoding="utf-8"))

    def test_example_validates(self):
        self.assertEqual(module.validate(self.sample())["outcome"], "unsupported")

    def test_invalid_claims_rejected(self):
        for changes in (
            {"outcome": "passed"},
            {"attempts": True},
            {"cost_usd": -1},
            {"input_tokens": -3},
            {"outcome": "failed", "behavior_passed": True},
            {"outcome": "infrastructure_error", "build_passed": False},
        ):
            with self.subTest(changes=changes):
                record = self.sample()
                record.update(changes)
                with self.assertRaises(ValueError):
                    module.validate(record)

    def test_pass_rate_excludes_unsupported_and_infrastructure(self):
        template = self.sample()
        records = []
        for i, outcome in enumerate(("passed", "failed", "unsupported", "infrastructure_error")):
            r = copy.deepcopy(template)
            r["trial_id"] = str(i)
            r["outcome"] = outcome
            r["build_passed"] = True if outcome == "passed" else False if outcome == "failed" else None
            r["behavior_passed"] = True if outcome == "passed" else False if outcome == "failed" else None
            records.append(module.validate(r))
        group = module.summarize(records)[0]
        self.assertEqual(group["trials"], 4)
        self.assertEqual(group["evaluated"], 2)
        self.assertEqual(group["passed"], 1)
        self.assertEqual(group["pass_rate"], 0.5)

    def test_candidate_runner_records_real_success_and_failure(self):
        runner = ROOT / "benchmarks/agent/run_candidate.py"
        with tempfile.TemporaryDirectory() as tmp:
            folder = pathlib.Path(tmp)
            for expected, test_code in ((True, "0"), (False, "1")):
                output = folder / ("pass.json" if expected else "fail.json")
                import subprocess
                build_script = folder / "build.py"
                test_script = folder / "behavior.py"
                build_script.write_text("raise SystemExit(0)\\n")
                test_script.write_text("raise SystemExit(" + test_code + ")\\n")
                command = [
                    sys.executable, str(runner),
                    "--task", "counter-v0", "--language", "sedrava",
                    "--target", "web", "--model", "manual-baseline",
                    "--commit", "a" * 40, "--cwd", str(folder),
                    "--build", sys.executable, str(build_script),
                    "--test", sys.executable, str(test_script),
                    "--output", str(output),
                ]
                result = subprocess.run(command, capture_output=True, text=True)
                self.assertEqual(result.returncode == 0, expected, result.stdout + result.stderr + (output.with_suffix(".build.log").read_text() if output.with_suffix(".build.log").exists() else ""))
                trial = module.validate(json.loads(output.read_text()))
                self.assertEqual(trial["outcome"] == "passed", expected)
                self.assertTrue(output.with_suffix(".build.log").exists())
                self.assertTrue(output.with_suffix(".test.log").exists())

    def test_cli_writes_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = pathlib.Path(tmp) / "summary.json"
            self.assertEqual(module.main([str(SAMPLE), "--output", str(output)]), 0)
            self.assertEqual(json.loads(output.read_text())["total_trials"], 1)


if __name__ == "__main__":
    unittest.main()
