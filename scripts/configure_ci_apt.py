"""Select the official Ubuntu archive on disposable GitHub-hosted CI runners.

Azure mirror downloads were measured at 33 kB/s for browser dependencies.
This changes only matching Ubuntu URIs, never keys or signature settings.
"""
import os
from pathlib import Path
import re

_AZURE = re.compile(r'https?://azure\.archive\.ubuntu\.com(?=/ubuntu(?:/|\s|$))')
SOURCES = (Path('/etc/apt/sources.list'), Path('/etc/apt/sources.list.d/ubuntu.sources'))


def rewrite_sources(text):
    lines = []
    for line in text.splitlines(keepends=True):
        if line.lstrip().startswith(('URIs:', 'deb ', 'deb-src ')):
            line = _AZURE.sub(lambda match:match[0].replace('azure.archive.ubuntu.com','archive.ubuntu.com'), line)
        lines.append(line)
    return ''.join(lines)


def configure(paths=SOURCES):
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        raise ValueError('APT mirror configuration is only for disposable GitHub CI')
    changed = 0
    for path in paths:
        if not path.is_file():
            continue
        original = path.read_text(encoding='utf-8')
        replacement = rewrite_sources(original)
        if replacement != original:
            path.write_text(replacement, encoding='utf-8')
            changed += 1
    print(f'Ubuntu archive mirror configured in {changed} source files; no signature settings changed')


if __name__ == '__main__':
    configure()
