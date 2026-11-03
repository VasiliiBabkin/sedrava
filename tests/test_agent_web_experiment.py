"""Experiment preparation tests; synthetic unit fixtures are not agent trials."""
from argparse import Namespace
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT/'benchmarks/agent'
sys.path.insert(0, str(HERE))
SPEC = importlib.util.spec_from_file_location('web_experiment', HERE/'prepare_web_experiment.py')
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


class WebExperimentTests(unittest.TestCase):
    def args(self, output):
        return Namespace(commit='a'*40, model='unit-fixture-not-a-model-run', agent='unit fixture',
                         toolchain='unit fixture', seconds=600, tokens=20000, attempts=3, output=output)

    def test_ten_disjoint_bundles_not_ten_claimed_trials(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)/'experiment'
            with patch.object(module.subprocess, 'check_output', side_effect=['a'*40, b'', b'']):
                plan = module.create(self.args(output))
            self.assertEqual(plan['completed_trials'], 0)
            self.assertEqual(plan['status'], 'prepared_not_run')
            self.assertFalse(plan['model_verified'])
            self.assertEqual(len(set(t['workspace'] for t in plan['trials'])), 10)
            self.assertEqual(sum(t['language']=='sedrava' for t in plan['trials']), 5)
            self.assertEqual(sum(t['language']=='typescript' for t in plan['trials']), 5)
            for trial in plan['trials']:
                root = output/trial['workspace']
                self.assertEqual(trial['outcome'], 'not_run')
                for relative, sha in trial['input_sha256'].items():
                    self.assertEqual(hashlib.sha256((root/relative).read_bytes()).hexdigest(), sha)
                    self.assertNotIn('/baselines/', relative)
                self.assertFalse((root/'candidate').exists())
                manifest = json.loads((root/'manifest.json').read_text())
                self.assertIsNone(manifest['reference_tokens'])
                self.assertFalse(manifest['model_seed_exposed'])
                self.assertIn('replicate label only', (root/'prompt.md').read_text())
            self.assertEqual(plan['trials'][0]['order'], 1)

    def test_fake_sha_and_dirty_benchmark_rejected_before_creating_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)/'experiment'
            for responses in (['b'*40], ['a'*40, b'dirty'], ['a'*40, b'', b'untracked.py']):
                with patch.object(module.subprocess,'check_output',side_effect=responses), self.assertRaises(ValueError):
                    module.create(self.args(output))
                self.assertFalse(output.exists())

    def test_nonpositive_budget_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = self.args(Path(tmp)/'experiment')
            args.tokens = 0
            with patch.object(module.subprocess,'check_output',side_effect=['a'*40,b'',b'']), self.assertRaises(ValueError):
                module.create(args)

    def test_local_urls_cannot_disguise_remote_hosts(self):
        spec = importlib.util.spec_from_file_location('counter_acceptance', HERE/'acceptance/counter_web_browser.py')
        evaluator = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(evaluator)
        for url in ('http://localhost:8000/index.html', 'http://127.0.0.1:1234/'):
            self.assertEqual(evaluator.validate_local_url(url), url)
        for url in ('http://localhost:80@evil.example/', 'http://127.0.0.1:80@evil.example/',
                    'https://localhost:80/', 'http://remote.example:80/', 'http://localhost:bad/'):
            with self.assertRaises(ValueError):
                evaluator.validate_local_url(url)

    def test_baseline_files_are_rejected_as_starters(self):
        from prepare_trial_bundle import relative_file
        with self.assertRaisesRegex(ValueError,'reference solutions'):
            relative_file('benchmarks/agent/baselines/sedrava/counter.sdr')


if __name__ == '__main__':
    unittest.main()
