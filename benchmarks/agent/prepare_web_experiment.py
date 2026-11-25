"""Prepare ten independent counter-v0 input bundles; never invoke/simulate an agent."""
import argparse
import contextlib
import hashlib
import io
import json
from pathlib import Path
import random
import subprocess
import sys
from argparse import Namespace

from prepare_trial_bundle import prepare

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def create(args):
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    if args.commit != commit:
        raise ValueError('Use the actual checkout HEAD; an arbitrary SHA is not provenance')
    if subprocess.check_output(['git', 'diff', 'HEAD', '--', 'benchmarks/agent'], cwd=ROOT):
        raise ValueError('Commit benchmark changes before freezing trial inputs')
    if subprocess.check_output(['git', 'ls-files', '--others', '--exclude-standard', '--', 'benchmarks/agent'], cwd=ROOT):
        raise ValueError('Commit untracked benchmark inputs before freezing trial inputs')
    if not args.model.strip() or not args.agent.strip() or not args.toolchain.strip():
        raise ValueError('Model, agent and toolchain descriptions must be nonempty')
    if args.seconds < 1 or args.tokens < 1 or args.attempts < 1:
        raise ValueError('Budgets must be positive')
    args.output.mkdir(parents=True, exist_ok=False)
    order = [(language, index) for index in range(1, 6)
             for language in ('sedrava', 'typescript')]
    random.Random(20261103).shuffle(order)
    trials = []
    for position, (language, index) in enumerate(order, 1):
        trial_id = f'{language}-web-{index:03d}'
        folder = args.output / trial_id
        with contextlib.redirect_stdout(io.StringIO()):
            prepare(Namespace(task='counter-v0', target='web', language=language,
                              commit=commit, trial_id=trial_id, model=args.model,
                              agent=args.agent, seed=index, temperature='not exposed',
                              toolchain=args.toolchain, seconds=args.seconds,
                              tokens=args.tokens, attempts=args.attempts,
                              starter=['benchmarks/agent/starters/empty-v0.md'],
                              reference=[f'benchmarks/agent/references/{language}-web-v0.md'],
                              output=folder))
        # These are scheduling labels, not claims that the provider exposes random seeds.
        trial = json.loads((folder / 'manifest.json').read_text())
        trial.update(model_seed_exposed=False, seed_role='replicate identifier only',
                     agent_settings={'reasoning_effort': 'medium'},
                     reference_tokens=None, starter_tokens=None,
                     token_measurement='unavailable until provider tokenizer/usage is recorded')
        (folder / 'manifest.json').write_text(json.dumps(trial, indent=2, sort_keys=True)+'\n')
        with (folder / 'prompt.md').open('a') as prompt:
            prompt.write('\nThe seed is a replicate label only; model seed/temperature controls are not exposed.\nReasoning effort: medium.\n')
        inventory = {p.relative_to(folder).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                     for p in sorted(folder.rglob('*')) if p.is_file()}
        trials.append({'order': position, 'trial_id': trial_id, 'language': language,
                       'outcome': 'not_run', 'input_sha256': inventory,
                       'workspace': trial_id})
    plan = {'schema': 1, 'task': 'counter-v0', 'target': 'web', 'repository_commit': commit,
            'model_requested': args.model, 'model_verified': False, 'agent': args.agent,
            'settings': {'reasoning_effort': 'medium', 'temperature': 'not exposed',
                         'model_seed': 'not exposed', 'order_seed': 20261103},
            'budgets': {'seconds': args.seconds, 'tokens': args.tokens, 'attempts': args.attempts},
            'budget_scope': 'per trial; tokens=input+output including reasoning if charged; adapter must enforce',
            'planned_trials': 10, 'completed_trials': 0, 'trials': trials,
            'harness_sha256': {name: hashlib.sha256((HERE/name).read_bytes()).hexdigest()
                               for name in ('acceptance/counter_web_browser.py', 'evaluate_web_candidate.py')},
            'status': 'prepared_not_run',
            'requirements': ['authorized reachable model endpoint and verified model ID',
                             'agent adapter with hard aggregate token/time/attempt enforcement',
                             'one fresh isolated filesystem per trial; expose only its bundle and toolchain',
                             'no repository/baselines/evaluator/prior outputs in coding environment',
                             'external immutable acceptance evaluator after source capture']}
    comparison = {'schema': 1, 'task': 'counter-v0', 'target': 'web',
                  'repository_commit': commit, 'status': 'not_run',
                  'agent_trials_completed': 0,
                  'reason': 'Input preparation only; no model invocation or coding trial',
                  'groups': [{'language': language, 'planned': 5, 'completed': 0,
                              'passed': 0, 'evaluated': 0, 'pass_rate': None,
                              'median_attempts': None, 'median_wall_seconds': None,
                              'input_tokens': None, 'output_tokens': None, 'cost_usd': None}
                             for language in ('sedrava', 'typescript')]}
    (args.output / 'comparison.json').write_text(json.dumps(comparison, indent=2, sort_keys=True)+'\n')
    (args.output / 'experiment.json').write_text(json.dumps(plan, indent=2, sort_keys=True)+'\n')
    return plan


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--commit', required=True)
    parser.add_argument('--model', required=True)
    parser.add_argument('--agent', required=True)
    parser.add_argument('--toolchain', required=True)
    parser.add_argument('--seconds', type=int, default=600)
    parser.add_argument('--tokens', type=int, default=20000)
    parser.add_argument('--attempts', type=int, default=3)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        plan = create(args)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    print(json.dumps({'status': plan['status'], 'planned': 10, 'completed': 0}))
    return 0


if __name__ == '__main__':
    sys.exit(main())
