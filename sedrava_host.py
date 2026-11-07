"""Explicitly opted-in local host runner, separate from browser/application targets.

Experimental v1: bounded pure scalar expressions plus capability-gated UTF-8
file reads and one atomic write. This is NOT an OS sandbox for hostile code.
"""
import ast
import keyword
import os
import re
import secrets
import stat
from dataclasses import dataclass
from pathlib import Path

from sedrava_core import checked_int, checked_text, evaluate, parse_expr, read_literal, type_of
from sedrava_syntax import source_lines
from sedrava_stdlib import SIGNATURES
from sedrava_queries import NAMES as QUERY_NAMES
from sedrava_host_json import JsonValue, loads as json_loads, dumps as json_dumps, lookup as json_lookup, count as json_count, new_object as json_object, put as json_put

_RESERVED = set(SIGNATURES) | set(QUERY_NAMES) | {
    "append", "update", "remove", "get", "has", "count", "next_id",
    "true", "false"
}

def _valid_binding(name, known):
    return (name not in known and name not in _RESERVED and
            not keyword.iskeyword(name) and not name.startswith("_"))


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
        return any(step.operation in ("read", "read_json", "try_read") for step in self.steps)

    @property
    def needs_list(self):
        return any(step.operation == "list_dir" for step in self.steps)

    @property
    def needs_mkdir(self):
        return any(step.operation == "mkdir" for step in self.steps)

    @property
    def needs_rmdir(self):
        return any(step.operation == "rmdir" for step in self.steps)

    @property
    def needs_write(self):
        return any(step.operation in ("write", "write_json", "mkdir", "rmdir") for step in self.steps)


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
    cursor = 1
    while cursor < len(lines):
        indent, line, number = lines[cursor]
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

        if m := re.fullmatch(r"arg ([A-Za-z][A-Za-z0-9_]*): (text|int|bool|json)", line):
            if steps or len(arguments) >= MAX_ARGS or not _valid_binding(m[1], types):
                raise ValueError(f"Line {number}: invalid or duplicate host argument")
            kind = {"text": str, "int": int, "bool": bool, "json": JsonValue}[m[2]]
            types[m[1]] = kind
            arguments.append((m[1], kind))
        elif m := re.fullmatch(r"let ([A-Za-z][A-Za-z0-9_]*) = (.+)", line):
            if not _valid_binding(m[1], types):
                raise ValueError(f"Line {number}: reserved or duplicate host binding")
            node = expression(m[2])
            kind = type_of(node, types)
            if kind not in (str, int, bool):
                raise ValueError(f"Line {number}: use explicit JSON statements for document values")
            types[m[1]] = kind
            steps.append(HostStep("let", m[1], node))
        elif m := re.fullmatch(r"(read_json|list_dir) ([A-Za-z][A-Za-z0-9_]*) from (.+)", line):
            reads += 1
            if reads > MAX_READS or not _valid_binding(m[2], types):
                raise ValueError(f"Line {number}: duplicate binding or read limit exceeded")
            node = expression(m[3], str)
            if isinstance(node, ast.Constant) and (m[1] != "list_dir" or node.value != "."):
                _segments(node.value)
            types[m[2]] = JsonValue
            steps.append(HostStep(m[1], m[2], node))
        elif m := re.fullmatch(r"json_get_(text|int|bool|json) ([A-Za-z][A-Za-z0-9_]*) from ([A-Za-z][A-Za-z0-9_]*) at (.+)", line):
            kind = {"text": str, "int": int, "bool": bool, "json": JsonValue}[m[1]]
            if types.get(m[3]) is not JsonValue or not _valid_binding(m[2], types):
                raise ValueError(f"Line {number}: JSON source or binding type mismatch")
            key = expression(m[4])
            if type_of(key, types) not in (str, int):
                raise ValueError(f"Line {number}: JSON lookup key must be text or int")
            types[m[2]] = kind
            steps.append(HostStep("json_get", m[2], m[3], (key, kind)))
        elif m := re.fullmatch(r"json_count ([A-Za-z][A-Za-z0-9_]*) from ([A-Za-z][A-Za-z0-9_]*)", line):
            if types.get(m[2]) is not JsonValue or not _valid_binding(m[1], types):
                raise ValueError(f"Line {number}: JSON count requires a document")
            types[m[1]] = int
            steps.append(HostStep("json_count", m[1], m[2]))
        elif m := re.fullmatch(r"json_object ([A-Za-z][A-Za-z0-9_]*)", line):
            if not _valid_binding(m[1], types):
                raise ValueError(f"Line {number}: duplicate JSON binding")
            types[m[1]] = JsonValue
            steps.append(HostStep("json_object", m[1], None))
        elif m := re.fullmatch(r"json_set ([A-Za-z][A-Za-z0-9_]*)\.([A-Za-z][A-Za-z0-9_]*) = (.+)", line):
            if types.get(m[1]) is not JsonValue:
                raise ValueError(f"Line {number}: JSON assignment requires a document")
            if types.get(m[3]) is JsonValue and re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", m[3]):
                steps.append(HostStep("json_set", m[1], m[2], (m[3], True)))
            else:
                node = expression(m[3])
                if type_of(node, types) not in (str, int, bool):
                    raise ValueError(f"Line {number}: invalid JSON field type")
                steps.append(HostStep("json_set", m[1], m[2], (node, False)))
        elif m := re.fullmatch(r"(mkdir|rmdir) (.+)", line):
            writes += 1
            if writes > 1:
                raise ValueError(f"Line {number}: host permits only one planned filesystem mutation")
            node = expression(m[2], str)
            if isinstance(node, ast.Constant):
                _segments(node.value)
            steps.append(HostStep(m[1], None, node))
        elif m := re.fullmatch(r"write_json (.+?) = ([A-Za-z][A-Za-z0-9_]*)", line):
            writes += 1
            if writes > 1 or types.get(m[2]) is not JsonValue:
                raise ValueError(f"Line {number}: host JSON write requires a document and one mutation")
            node = expression(m[1], str)
            if isinstance(node, ast.Constant):
                _segments(node.value)
            steps.append(HostStep("write_json", None, node, m[2]))
        elif m := re.fullmatch(r"emit_json ([A-Za-z][A-Za-z0-9_]*)", line):
            if types.get(m[1]) is not JsonValue:
                raise ValueError(f"Line {number}: emit_json requires JSON document")
            steps.append(HostStep("emit_json", None, m[1]))
            emitted = True
        elif m := re.fullmatch(r"try_read ([A-Za-z][A-Za-z0-9_]*) from (.+)", line):
            from sedrava_host_typed import HOST_READ_RESULT
            reads += 1
            if reads > MAX_READS or not _valid_binding(m[1], types):
                raise ValueError(f"Line {number}: duplicate binding or read limit exceeded")
            node = expression(m[2], str)
            types[m[1]] = HOST_READ_RESULT
            steps.append(HostStep("try_read", m[1], node))
        elif m := re.fullmatch(r"match ([A-Za-z][A-Za-z0-9_]*):", line):
            from sedrava_host_typed import HOST_READ_RESULT
            from sedrava_errors import MatchArm, pattern, check_arm, exhaustive
            if types.get(m[1]) != HOST_READ_RESULT:
                raise ValueError(f"Line {number}: match requires a HostReadError Result")
            arms, seen = [], set()
            scan = cursor + 1
            while scan < len(lines) and lines[scan][0] > 0:
                indent_arm, arm_source, arm_line = lines[scan]
                if indent_arm != 4:
                    raise ValueError(f"Line {arm_line}: match arm must have four-space indentation")
                try:
                    tag, pattern_entries = pattern(arm_source)
                    arm_types, bindings = check_arm(HOST_READ_RESULT, tag, pattern_entries, types, seen)
                except ValueError as exc:
                    raise ValueError(f"Line {arm_line}: {exc}") from exc
                seen.add(tag)
                scan += 1
                if scan >= len(lines) or lines[scan][0] != 8:
                    raise ValueError(f"Line {arm_line}: match arm requires an eight-space-indented emit")
                _, body_source, body_line = lines[scan]
                match_emit = re.fullmatch(r"emit (.+)", body_source)
                if not match_emit:
                    raise ValueError(f"Line {body_line}: Host A3 match arms currently support one emit")
                try:
                    node = parse_expr(match_emit[1], arm_types)
                    if type_of(node, arm_types) not in (str, int, bool):
                        raise ValueError("emit requires a scalar")
                except ValueError as exc:
                    raise ValueError(f"Line {body_line}: {exc}") from exc
                arms.append(MatchArm(tag, bindings, (HostStep("emit", None, node),)))
                scan += 1
                if scan < len(lines) and lines[scan][0] > 4:
                    raise ValueError(f"Line {lines[scan][2]}: each match arm permits one emit")
            if not arms:
                raise ValueError(f"Line {number}: match requires arms")
            exhaustive(HOST_READ_RESULT, seen)
            steps.append(HostStep("match", None, m[1], tuple(arms)))
            cursor = scan - 1
            emitted = True
        elif m := re.fullmatch(r"read ([A-Za-z][A-Za-z0-9_]*) from (.+)", line):
            reads += 1
            if reads > MAX_READS or not _valid_binding(m[1], types):
                raise ValueError(f"Line {number}: duplicate binding or read limit exceeded")
            node = expression(m[2], str)
            if isinstance(node, ast.Constant):
                _segments(node.value)
            types[m[1]] = str
            steps.append(HostStep("read", m[1], node))
        elif m := re.fullmatch(r"write (.+?) = (.+)", line):
            writes += 1
            if writes > 1:
                raise ValueError(f"Line {number}: host permits only one planned filesystem mutation")
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
        cursor += 1
    if not emitted:
        raise ValueError("Host program requires a final emit statement")
    return HostProgram(name, tuple(arguments), tuple(steps))


def _parse_args(spec, supplied):
    expected = dict(spec)
    values = {}
    if len(supplied) > MAX_ARGS:
        raise ValueError("Too many host arguments")
    for entry in supplied:
        if "=" not in entry:
            raise ValueError("Arguments require name=value")
        name, raw = entry.split("=", 1)
        if name not in expected or name in values:
            raise ValueError("Unexpected or duplicate host argument")
        kind = expected[name]
        if kind is JsonValue:
            value = json_loads(raw)
        elif kind is str:
            value = checked_text(raw)
        elif kind is bool:
            if raw not in ("true", "false"):
                raise ValueError("Boolean host argument requires true or false")
            value = raw == "true"
        else:
            if len(raw) > 11 or not re.fullmatch(r"-?(0|[1-9][0-9]*)", raw):
                raise ValueError("Integer host argument must be decimal int32")
            value = checked_int(int(raw))
        values[name] = value
    if set(values) != set(expected):
        raise ValueError("Missing host argument")
    return values


def _segments(value):
    from sedrava_host_typed import HostInvalidPath
    try:
        checked_text(value)
    except ValueError as exc:
        raise HostInvalidPath("Invalid workspace-relative path") from exc
    if not value or len(value) > 240 or "\\" in value or any(ord(char) < 32 or ord(char) == 127 for char in value):
        from sedrava_host_typed import HostInvalidPath
        raise HostInvalidPath("Invalid workspace-relative path")
    parts = value.split("/")
    if any(part in ("", ".", "..") for part in parts):
        from sedrava_host_typed import HostInvalidPath
        raise HostInvalidPath("Absolute, empty and traversal paths are forbidden")
    if value.startswith("/") or any(len(part.encode("utf-8")) > 120 for part in parts):
        raise HostInvalidPath("Invalid workspace-relative path")
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
        from sedrava_host_typed import HostPolicyViolation
        raise HostPolicyViolation("Workspace file must be a regular, single-link file")


def _read(root_fd, relative, *, raw_json=False):
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
            from sedrava_host_typed import HostResourceTooLarge
            raise HostResourceTooLarge("Host read exceeds 4096-byte limit")
        decoded = data.decode("utf-8", errors="strict")
        return decoded if raw_json else checked_text(decoded)
    finally:
        if descriptor is not None:
            os.close(descriptor)
        os.close(parent)


def _write(root_fd, relative, content, *, json_mode=False):
    if not json_mode:
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


def run_host(program, *, root, supplied=(), trusted=False, allow_read=False,
             allow_write=False, allow_list=False, allow_mkdir=False, allow_rmdir=False,
             read_scope=".", write_scope=".", list_scope=".", on_phase=None):
    """Run one trusted host document; all filesystem mutations are deferred."""
    from sedrava_host_fs import open_scope, list_dir, make_dir, remove_empty_dir
    from sedrava_host_protocol import HostSetupRejected
    if on_phase is not None:
        on_phase("setup")

    if not trusted:
        raise HostSetupRejected("Host execution requires explicit --trusted")
    if program.needs_read and not allow_read:
        raise HostSetupRejected("Host file reads require --allow-read")
    if program.needs_list and not allow_list:
        raise HostSetupRejected("Host directory listing requires --allow-list")
    if program.needs_write and not allow_write:
        raise HostSetupRejected("Host mutations require --allow-write")
    if program.needs_mkdir and not allow_mkdir:
        raise HostSetupRejected("Host directory creation requires --allow-mkdir")
    if program.needs_rmdir and not allow_rmdir:
        raise HostSetupRejected("Host directory removal requires --allow-rmdir")
    if os.name != "posix" or not all(hasattr(os, name) for name in
                                       ("O_NOFOLLOW", "O_DIRECTORY", "O_CLOEXEC")):
        raise ValueError("Host filesystem A2 supports POSIX platforms only")

    values = _parse_args(program.arguments, supplied)
    root_fd = os.open(os.fspath(root), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    rfd = wfd = lfd = None
    pending = None
    result = None
    try:
        # Establish capability-scoped directory descriptors before any statements.
        if program.needs_read:
            rfd = open_scope(root_fd, read_scope)
        if program.needs_write:
            wfd = open_scope(root_fd, write_scope)
        if program.needs_list:
            lfd = open_scope(root_fd, list_scope)
        if on_phase is not None:
            on_phase("execute")
        for step in program.steps:
            if step.operation == "let":
                values[step.target] = evaluate(step.first, values)
            elif step.operation == "read":
                values[step.target] = _read(rfd, evaluate(step.first, values))
            elif step.operation == "try_read":
                from sedrava_host_typed import read_result
                values[step.target] = read_result(rfd, evaluate(step.first, values))
            elif step.operation == "read_json":
                values[step.target] = json_loads(
                    _read(rfd, evaluate(step.first, values), raw_json=True))
            elif step.operation == "list_dir":
                relative = evaluate(step.first, values)
                values[step.target] = list_dir(lfd, relative)
            elif step.operation == "json_get":
                key, kind = step.second
                values[step.target] = json_lookup(values[step.first],
                                                   evaluate(key, values), kind)
            elif step.operation == "json_count":
                values[step.target] = json_count(values[step.first])
            elif step.operation == "json_object":
                values[step.target] = json_object()
            elif step.operation == "json_set":
                field, is_document = step.second
                value = values[field] if is_document else evaluate(field, values)
                values[step.target] = json_put(values[step.target], step.first, value)
            elif step.operation in ("write", "write_json", "mkdir", "rmdir"):
                path = evaluate(step.first, values)
                _segments(path)
                if step.operation == "write":
                    content = evaluate(step.second, values)
                    checked_text(content)
                    if len(content.encode("utf-8")) > MAX_FILE_BYTES:
                        raise ValueError("Host write exceeds 4096-byte limit")
                    pending = ("write", path, content)
                elif step.operation == "write_json":
                    pending = ("write_json", path, json_dumps(values[step.second]))
                else:
                    pending = (step.operation, path, None)
            elif step.operation == "match":
                from sedrava_host_typed import execute_match
                result = execute_match(values[step.first], step.second, values)
            elif step.operation == "emit_json":
                document = values[step.first]
                json_dumps(document)
                result = document.value
            else:
                result = evaluate(step.first, values)
        if pending is not None:
            if on_phase is not None:
                on_phase("commit")
            operation, path, payload = pending
            if operation == "write":
                _write(wfd, path, payload)
            elif operation == "write_json":
                _write(wfd, path, payload, json_mode=True)
            elif operation == "mkdir":
                make_dir(wfd, path)
            else:
                remove_empty_dir(wfd, path)
        return {"result": result, "written": pending[1] if pending else None}
    finally:
        for descriptor in (rfd, wfd, lfd, root_fd):
            if descriptor is not None:
                os.close(descriptor)
