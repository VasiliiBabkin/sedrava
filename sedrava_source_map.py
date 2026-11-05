"""Source provenance for namespace/legacy-module expansion and diagnostics.

No globals: every build carries its own immutable (path, line) provenance.
This is compile-time developer metadata, not executable generated code.
"""
from pathlib import Path
import re

_ERROR = re.compile(r"^Line ([1-9][0-9]*):(?: column ([1-9][0-9]*):)?[ ]*(.*)", re.S)


def locations(source, source_path):
    path = Path(source_path).resolve() if source_path else None
    return tuple((path, number) for number, _ in enumerate(source.splitlines(), 1))


def source_error(exc, source_map):
    """Map an actual parser line onto a checked original file; never guess."""
    message = str(exc)
    match = _ERROR.match(message)
    if match is None:
        return exc
    number = int(match[1])
    if number > len(source_map):
        return exc
    path, original = source_map[number - 1]
    if path is None:
        return exc
    column = f":{match[2]}" if match[2] else ""
    return ValueError(f"{path}:{original}{column}: {match[3]} (expanded line {number})")
