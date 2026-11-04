"""Bounded local presentation modules and typed compile-time component expansion.

No Python/JavaScript execution or network loading. Included files are author code.
"""
import json
from pathlib import Path
import re
from sedrava_syntax import MAX_SOURCE_CHARS, MAX_BLOCK_DEPTH, source_lines


def expand(source, source_path=None, _stack=(), _root=None, _files=None):
    source_lines(source)
    files = set() if _files is None else _files
    if not _stack and any(re.fullmatch(r'import "[^"\\n]+\\.sdr" as [A-Za-z][A-Za-z0-9_]*', line)
                          for depth, line, _ in source_lines(source) if depth == 0):
        from sedrava_namespaces import resolve_scoped
        source, namespaced_files = resolve_scoped(source, source_path)
        files.update(namespaced_files)
    root = Path(source_path).resolve().parent if _root is None and source_path else _root
    output = []
    for number, line in enumerate(source.splitlines(), 1):
        match = re.fullmatch(r'import "([^"\n]+\.sdr)"', line)
        if not match:
            output.append(line)
            continue
        if source_path is None:
            raise ValueError(f'Line {number}: column 1: imports require a source file path')
        value = match[1]
        if Path(value).is_absolute() or '..' in Path(value).parts or '\\' in value:
            raise ValueError(f'Line {number}: column 1: import must stay within the source directory')
        path = Path(source_path).resolve().parent / value
        current = path
        while current != root and current != current.parent:
            if current.is_symlink():
                raise ValueError(f'Line {number}: column 1: symlink modules are forbidden')
            current = current.parent
        path = path.resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError(f'Line {number}: column 1: missing or outside-root module {value}')
        if path in _stack or len(_stack) >= 16:
            raise ValueError(f'Line {number}: column 1: cyclic or excessive imports')
        if path.stat().st_size > MAX_SOURCE_CHARS * 4 or len(files) >= 32:
            raise ValueError(f'Line {number}: column 1: module resource limit')
        files.add(path)
        text = path.read_text(encoding='utf-8')
        for depth, declaration, n in source_lines(text):
            if depth == 0 and not declaration.startswith(('component ', 'style ', 'import ', 'fn ', 'record ')):
                raise ValueError(f'Line {number}: column 1: module {value}:{n} may only export components/styles/records/functions/imports')
        expanded, _ = expand(text, path, (*_stack, path), root, files)
        output.extend(expanded.splitlines())
    joined = '\n'.join(output)
    if len(joined) > MAX_SOURCE_CHARS:
        raise ValueError('Expanded imports exceed source limit')
    return (components(joined) if not _stack else joined), files


def components(source):
    source_lines(source)
    # Resolve definitions after imports. They are templates, never executable source.
    definitions = {}
    lines = source.splitlines()
    kept = []
    pos = 0
    while pos < len(lines):
        line = lines[pos]
        match = re.fullmatch(r'component ([A-Za-z][A-Za-z0-9_]*)(?:\((.*?)\))?:', line)
        if not match:
            kept.append(line); pos += 1; continue
        name, parameters = match.groups()
        if name in definitions:
            raise ValueError(f'Line {pos+1}: column 1: duplicate component {name}')
        params = {}
        for declaration in parameters.split(',') if parameters else ():
            spec = re.fullmatch(r'\s*([A-Za-z][A-Za-z0-9_]*)\s*:\s*(text|int|bool|ref)\s*', declaration)
            if not spec or spec[1] in params:
                raise ValueError(f'Line {pos+1}: column 1: invalid component parameter')
            params[spec[1]] = {'text': str, 'int': int, 'bool': bool, 'ref':'reference'}[spec[2]]
        pos += 1; body = []
        while pos < len(lines) and (not lines[pos].strip() or lines[pos].startswith(' ')):
            body.append(lines[pos]); pos += 1
        if not body or any(line.strip() and not line.startswith('    ') for line in body):
            raise ValueError('Component requires four-space-indented content')
        definitions[name] = (params, [line[4:] if line.startswith('    ') else line for line in body])
    from sedrava_site import tokens

    def instantiate(lines, stack=()):
        result = []; i = 0
        while i < len(lines):
            line = lines[i]; i += 1
            call = re.fullmatch(r'( *)use ([A-Za-z][A-Za-z0-9_]*)(.*)', line)
            if not call:
                result.append(line); continue
            prefix, name, rest = call.groups()
            if name not in definitions or name in stack or len(stack) >= MAX_BLOCK_DEPTH:
                raise ValueError(f'Line {i}: column {len(prefix)+1}: unknown/recursive component {name}')
            block = rest.rstrip().endswith(':')
            args = tokens(rest.rstrip()[:-1] if block else rest, i, len(prefix))
            params, template = definitions[name]
            if len(args) % 2:
                raise ValueError(f'Line {i}: column 1: component parameters require name/value pairs')
            values = {}
            for key, value in zip(args[::2], args[1::2]):
                if key.value in values or key.value not in params:
                    raise ValueError(f'Line {i}: column 1: invalid typed component parameter {key.value}')
                expected=params[key.value]
                reference=expected=='reference'
                if (reference and (value.quoted or type(value.value) is not str or not re.fullmatch('[A-Za-z][A-Za-z0-9_]*',value.value))) or (not reference and type(value.value) is not expected):
                    raise ValueError(f'Line {i}: column 1: invalid typed component parameter {key.value}')
                values[key.value] = value.value if reference else json.dumps(value.value, ensure_ascii=False)
            if set(values) != set(params):
                raise ValueError(f'Line {i}: column 1: component requires exact parameters')
            children = []
            if block:
                while i < len(lines) and (not lines[i].strip() or len(lines[i])-len(lines[i].lstrip(' ')) > len(prefix)):
                    children.append(lines[i][len(prefix)+4:]); i += 1
            slots = sum(line.strip() == 'slot' for line in template)
            if slots > 1 or bool(children) != bool(slots):
                raise ValueError(f'Line {i}: column 1: component slot requires matching content')
            expanded = []
            for text in template:
                if text.strip() == 'slot':
                    pad = text[:len(text)-len(text.lstrip(' '))]
                    expanded.extend(prefix+pad+child for child in children)
                else:
                    # Parameters use $name outside literals; expansion yields typed literal tokens.
                    parts = re.split(r'("(?:[^"\\]|\\.)*")', text)
                    for j in range(0, len(parts), 2):
                        def replace(m):
                            if m[1] not in values: raise ValueError('Unknown component parameter '+m[1])
                            return values[m[1]]
                        parts[j] = re.sub(r'\$([A-Za-z][A-Za-z0-9_]*)', replace, parts[j])
                    expanded.append(prefix+''.join(parts))
            result.extend(instantiate(expanded, (*stack, name)))
            if sum(map(len, result)) > MAX_SOURCE_CHARS:
                raise ValueError('Expanded components exceed source limit')
        return result
    result = '\n'.join(instantiate(kept))+'\n'
    if len(result) > MAX_SOURCE_CHARS:
        raise ValueError('Expanded components exceed source limit')
    return result
