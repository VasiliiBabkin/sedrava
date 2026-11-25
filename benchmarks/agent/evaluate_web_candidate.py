"""Serve a built candidate and invoke the unchanged C01-C08 contract externally.

This is an evaluator, not an agent runner or an agent-performance result.
Supply UI mapping observed independently, not application-internal state hooks.
"""
import argparse
import functools
import http.server
import json
from pathlib import Path
import subprocess
import sys
import threading
from urllib.parse import quote

HERE = Path(__file__).resolve().parent


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--entry', default='index.html')
    parser.add_argument('--value-selector', required=True)
    parser.add_argument('--increment-label', required=True)
    parser.add_argument('--decrement-label', required=True)
    parser.add_argument('--reset-label', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--chromium')
    args = parser.parse_args(argv)
    if args.directory.is_symlink():
        parser.error('Candidate root must not be a symlink')
    root = args.directory.resolve()
    entry = (root / args.entry).resolve()
    if not root.is_dir() or not entry.is_relative_to(root) or not entry.is_file():
        parser.error('Entry must be an existing file within the built candidate directory')
    # Keep all evaluator evidence outside the served application tree.
    if args.output.resolve().is_relative_to(root):
        parser.error('Evaluator output must be outside the candidate directory')
    if any(p.is_symlink() for p in root.rglob('*')):
        parser.error('Candidate directory must not contain symlinks')
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0),
        functools.partial(QuietHandler, directory=str(root)))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    command = [sys.executable, str(HERE / 'acceptance/counter_web_browser.py'),
               '--url', f'http://127.0.0.1:{server.server_port}/'+quote(entry.relative_to(root).as_posix()),
               '--value-selector', args.value_selector, '--increment-label', args.increment_label,
               '--decrement-label', args.decrement_label, '--reset-label', args.reset_label,
               '--output', str(args.output.resolve())]
    if args.chromium:
        command += ['--chromium', args.chromium]
    try:
        result = subprocess.run(command, timeout=120, check=False)
        if result.returncode:
            return result.returncode
        report = json.loads(args.output.read_text())
        if report.get('passed') is not True or [x['case'] for x in report['observations']] != [f'C0{i}' for i in range(1, 9)]:
            raise ValueError('Incomplete acceptance evidence')
        return 0
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


if __name__ == '__main__':
    sys.exit(main())
