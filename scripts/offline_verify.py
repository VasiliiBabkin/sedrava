#!/usr/bin/env python3
"""Run Sedrava checks without invoking GitHub Actions or installing dependencies."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent.parent
QUICK_TESTS = (
    'test_bounded_core_012.py',
    'test_core_conformance_timeout.py',
    'test_core_namespace_integration.py',
    'test_effects_targets_012.py',
    'test_typed_errors_match_012.py',
    'test_host_a3_typed_protocol.py',
    'test_host_a4_json_result.py',
)


def run_step(label: str, command: list[str], env: dict[str, str]) -> dict[str, object]:
    print(f'\n=== {label} ===', flush=True)
    started = time.monotonic()
    try:
        code = subprocess.run(command, cwd=ROOT, env=env, check=False).returncode
    except OSError as exc:
        print(f'Cannot execute {command[0]}: {exc}', file=sys.stderr)
        code = 127
    return {'name': label, 'command': command, 'exit_code': code,
            'seconds': round(time.monotonic() - started, 3),
            'status': 'PASS' if code == 0 else 'FAIL'}


def source_sha() -> str | None:
    try:
        result = subprocess.run(['git', 'rev-parse', '--verify', 'HEAD'], cwd=ROOT,
                                text=True, capture_output=True, check=False)
        if result.returncode == 0:
            return result.stdout.strip()
    except OSError:
        pass
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description='Check Sedrava locally without CI minutes.')
    parser.add_argument('scope', nargs='?', choices=('quick', 'full'), default='quick',
                        help='quick: focused 0.12 regressions; full: all Python tests plus audits')
    parser.add_argument('--report', type=Path, default=Path('build/offline-verify.json'),
                        help='JSON report path relative to the repository (default: build/offline-verify.json)')
    args = parser.parse_args()
    env = os.environ.copy()
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    env['PIP_NO_INDEX'] = '1'
    env['PIP_DISABLE_PIP_VERSION_CHECK'] = '1'
    steps = []
    if args.scope == 'quick':
        steps.extend((name, [sys.executable, '-m', 'unittest', 'discover', '-s', 'tests',
                             '-p', name, '-v']) for name in QUICK_TESTS)
    else:
        steps.extend([
            ('all Python tests', [sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-v']),
            ('documentation audit', [sys.executable, 'scripts/check_docs.py']),
            ('release security audit', [sys.executable, 'scripts/audit_release_security.py']),
        ])
    started_at = dt.datetime.now(dt.timezone.utc).isoformat()
    results = []
    for label, command in steps:
        result = run_step(label, command, env)
        results.append(result)
        if result['exit_code'] != 0:
            print('Stopping on failed step; later checks are NOT RUN.', file=sys.stderr)
            break
    status = 'PASS' if len(results) == len(steps) and all(r['exit_code'] == 0 for r in results) else 'FAIL'
    report = {'tool': 'sedrava-offline-verify', 'scope': args.scope, 'status': status,
              'source_sha': source_sha(), 'started_at_utc': started_at,
              'steps_planned': len(steps), 'steps_executed': len(results), 'steps': results,
              'notes': 'No package installation or GitHub Actions invoked. Browser/Android/release checks not covered.'}
    output = args.report if args.report.is_absolute() else ROOT / args.report
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'\n{status}: {len(results)}/{len(steps)} steps executed; report: {output}', flush=True)
    return 0 if status == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
