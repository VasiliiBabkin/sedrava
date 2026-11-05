"""Explicitly opted-in local host runner, separate from browser/application targets.

Experimental v1: bounded pure scalar expressions plus capability-gated UTF-8
file reads and one atomic write. This is NOT an OS sandbox for hostile code.
"""
import ast
import os
import re
import secrets
import stat
from dataclasses import dataclass
from pathlib import Path

from sedrava_core import checked_int, checked_text, evaluate, parse_expr, read_literal, type_of
from sedrava_syntax import source_lines

MAX_STEPS = 64
MAX_ARGS = 16
MAX_FILE_BYTES = 4096
MAX_READS = 8


@dataclass(frozen=True)
class HostStep:
    operation: str
    target: str | None
    first: object
    second: object = None


@dataclass(frozen=True)
class HostProgram:
    name: str
    arguments: tuple
    steps: tuple

    @property
    def needs_read(self):
        return any(step.operation == "read" for step in self.steps)

    @property
    def needs_write(self):
        return any(step.operation == "write" for step in self.steps)


def parse_host(source):
    """Parse a deliberately separate host document. Effects are statements, not functions."""
    lines = source_lines(source)
    if not lines or lines[0][0] != 0 or not lines[0][1].startswith('host "'):
        raise ValueError("Host source must begin with host \"Name\"")
    try:
        name, offset = read_literal(lines[0][1][5:])
    except ValueError as exc:
        raise ValueError(f"Line {lines[0][2]}: column 6: {exc}") from exc
    if lines[0][1][5 + offset:].strip():
        raise ValueError("Host header must contain only a name")
    if len(lines) - 1 > MAX_STEPS:
        raise ValueError("Host statement limit exceeded")
    arguments, steps, types = [], [], {}
    reads = writes = 0
    emitted = False
    for indent, line, number in lines[1:]:
        if indent != 0:
            raise ValueError(f"Line {number}: host statements must not be indented")
        if emitted:
            raise ValueError(f"Line {number}: emit must be the final statement")

        def expression(raw, expected=None):
            try:
                node = parse_expr(raw, types)
                found = type_of(node, types)
                if expected is not None and found is not expected:
                    raise ValueError("Host expression type mismatch")
                node.source_line = number
                node.source_column = line.find(raw) + 1
                return node
            except ValueError as exc:
                raise ValueError(f"Line {number}: {exc}") from exc

        if m := re.fullmatch(r"arg ([A-Za-z][A-Za-z0-9_]*): (text|int|bool)", line):
            if steps or len(arguments) >= MAX_ARGS or m[1] in types:
                raise ValueError(f"Line {number}: invalid or duplicate host argument")
            kind = {"text": str, "int": int, "bool": bool}[m[2]]
            types[m[1]] = kind
            arguments.append((m[1], kind))
        elif m := re.fullmatch(r"let ([A-Za-z][A-Za-z0-9_]*) = (.+)", line):
            if m[1] in types:
                raise ValueError(f"Line {number}: duplicate host binding")
            node = expression(m[2])
            types[m[1]] = type_of(node, types)
            steps.append(HostStep("let", m[1], node))
        elif m := re.fullmatch(r"read ([A-Za-z][A-Za-z0-9_]*) from (.+)", line):
            reads += 1
            if reads > MAX_READS or m[1] in types:
                raise ValueError(f"Line {number}: duplicate binding or read limit exceeded")
            node = expression(m[2], str)
            if isinstance(node, ast.Constant):
                _segments(node.value)
            types[m[1]] = str
            steps.append(HostStep("read", m[1], node))
        elif m := re.fullmatch(r"write (.+?) = (.+)", line):
            writes += 1
            if writes > 1:
                raise ValueError(f"Line {number}: host A1 permits one output file")
            path_node = expression(m[1], str)
            content_node = expression(m[2], str)
            if isinstance(path_node, ast.Constant):
                _segments(path_node.value)
            steps.append(HostStep("write", None, path_node, content_node))
        elif m := re.fullmatch(r"emit (.+)", line):
            node = expression(m[1])
            if type_of(node, types) not in (str, int, bool):
                raise ValueError(f"Line {number}: emitted value must be scalar")
            steps.append(HostStep("emit", None, node))
            emitted = True
        else:
            raise ValueError(f"Line {number}: unsupported host statement")
    if not emitted:
        raise ValueError("Host program requires a final emit statement")
    return HostProgram(name, tuple(arguments), tuple(steps))


def _parse_args(spec, supplied):
    expected = dict(spec)
    values = {}
    for entry in supplied:
        if "=" not in entry:
            raise ValueError("Arguments require name=value")
        name, raw = entry.split("=", 1)
        if name not in expected or name in values:
            raise ValueError("Unexpected or duplicate host argument")
        kind = expected[name]
        if kind is str:
            value = checked_text(raw)
        elif kind is bool:
            if raw not in ("true", "false"):
                raise ValueError("Boolean host argument requires true or false")
            value = raw == "true"
        else:
            if not re.fullmatch(r"-?(0|[1-9][0-9]*)", raw):
                raise ValueError("Integer host argument must be decimal int32")
            value = checked_int(int(raw))
        values[name] = value
    if set(values) != set(expected):
        raise ValueError("Missing host argument")
    return values


def _segments(value):
    checked_text(value)
    if not value or len(value) > 240 or "\\" in value or "\x00" in value:
        raise ValueError("Invalid workspace-relative path")
    parts = value.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise ValueError("Absolute, empty and traversal paths are forbidden")
    if value.startswith("/") or any(len(part.encode("utf-8")) > 120 for part in parts):
        raise ValueError("Invalid workspace-relative path")
    return parts


def _parent(root_fd, parts):
    descriptor = os.dup(root_fd)
    try:
        for name in parts[:-1]:
            child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        return descriptor, parts[-1]
    except BaseException:
        os.close(descriptor)
        raise


def _regular(st):
    if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1:
        raise ValueError("Workspace file must be a regular, single-link file")


def _read(root_fd, relative):
    parent, name = _parent(root_fd, _segments(relative))
    descriptor = None
    try:
        descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=parent)
        _regular(os.fstat(descriptor))
        data = bytearray()
        while len(data) <= MAX_FILE_BYTES:
            chunk = os.read(descriptor, MAX_FILE_BYTES + 1 - len(data))
            if not chunk:
                break
            data.extend(chunk)
        if len(data) > MAX_FILE_BYTES:
            raise ValueError("Host read exceeds 4096-byte limit")
        return checked_text(data.decode("utf-8", errors="strict"))
    finally:
        if descriptor is not None:
            os.close(descriptor)
        os.close(parent)


def _write(root_fd, relative, content):
    checked_text(content)
    data = content.encode("utf-8")
    if len(data) > MAX_FILE_BYTES:
        raise ValueError("Host write exceeds 4096-byte limit")
    parent, name = _parent(root_fd, _segments(relative))
    temp = None
    descriptor = None
    try:
        # Existing symlinks, devices, hard links and directories are not writable.
        try:
            _regular(os.stat(name, dir_fd=parent, follow_symlinks=False))
        except FileNotFoundError:
            pass
        temp = ".sedrava-" + secrets.token_hex(16) + ".tmp"
        descriptor = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                             0o600, dir_fd=parent)
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = None
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        # Atomic replacement of ONE file. This is not a multi-file transaction.
        os.replace(temp, name, src_dir_fd=parent, dst_dir_fd=parent)
        temp = None
        os.fsync(parent)
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if temp is not None:
            try:
                os.unlink(temp, dir_fd=parent)
            except FileNotFoundError:
                pass
        os.close(parent)


def run_host(program, *, root, supplied=(), trusted=False, allow_read=False, allow_write=False):
    """Execute the verified host-only AST, never Python source, shell or browser code."""
    if not trusted:
        raise ValueError("Host execution requires explicit --trusted")
    if program.needs_read and not allow_read:
        raise ValueError("Host file reads require --allow-read")
    if program.needs_write and not allow_write:
        raise ValueError("Host file writes require --allow-write")
    if os.name != "posix" or not all(hasattr(os, name) for name in ("O_NOFOLLOW", "O_DIRECTORY", "O_CLOEXEC")):
        raise ValueError("Host filesystem A1 supports POSIX platforms only")
    values = _parse_args(program.arguments, supplied)
    root_fd = os.open(os.fspath(root), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    pending = None
    result = None
    try:
        for step in program.steps:
            if step.operation == "let":
                values[step.target] = evaluate(step.first, values)
            elif step.operation == "read":
                values[step.target] = _read(root_fd, evaluate(step.first, values))
            elif step.operation == "write":
                path = evaluate(step.first, values)
                content = evaluate(step.second, values)
                checked_text(path)
                checked_text(content)
                _segments(path)
                if len(content.encode("utf-8")) > MAX_FILE_BYTES:
                    raise ValueError("Host write exceeds 4096-byte limit")
                pending = (path, content)
            else:
                result = evaluate(step.first, values)
        if pending is not None:
            _write(root_fd, *pending)
        return {"result": result, "written": pending[0] if pending else None}
    finally:
        os.close(root_fd)
