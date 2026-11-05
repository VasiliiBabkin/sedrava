"""Bounded local presentation modules and typed compile-time component expansion.

No Python/JavaScript execution or network loading. Included files are author code.
"""
import json
from pathlib import Path
import re
from sedrava_syntax import MAX_SOURCE_CHARS, MAX_BLOCK_DEPTH, source_lines


def _expand(source, source_path=None, _stack=(), _root=None, _files=None, *, with_origins=False, _verified=None, _scoped=False):
    source_lines(source)
    from sedrava_source_map import locations, ExpandedSource, MappedLine, origin_for, mapped_lines, replace_span
    scoped=_scoped or getattr(source,"scoped",False)
    files = set() if _files is None else _files
    source_map = getattr(source,"origins",None) or locations(source, source_path)
    if _stack and scoped:
        from sedrava_namespaces import _tokens,_RESERVED
        import tokenize
        from sedrava_source_map import LocatedError
        for no,line in enumerate(source.splitlines(),1):
            try:tokens=_tokens(line)
            except ValueError as exc:raise LocatedError(str(exc),source_path,no,1) from exc
            if any(t.type==tokenize.NAME and _RESERVED.fullmatch(t.string) for t in tokens):raise LocatedError("Reserved generated symbol in scoped legacy import",source_path,no,1)
    if not _stack and source_path is not None:
        from sedrava_packages import verified_inputs
        _verified=verified_inputs(source_path)
        from sedrava_packages import verify_if_project
        package_files = verify_if_project(source_path)
        if package_files:
            files.update(package_files)
    if not _stack:
        from sedrava_namespaces import _IMPORT, resolve_scoped
        if any(_IMPORT.fullmatch(line) for depth, line, _ in source_lines(source) if depth == 0):
            scoped=True
            source, namespaced_files, source_map = resolve_scoped(source, source_path, with_origins=True, verified=_verified)
            files.update(namespaced_files)
    root = Path(source_path).resolve().parent if _root is None and source_path else _root
    output, origins = [], []
    try:
        for number, line in enumerate(source.splitlines(), 1):
            match = re.fullmatch(r'import "([^"\n]+\.sdr)"', line)
            if not match:
                output.append(line)
                origins.append(source_map[number - 1])
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
            from sedrava_packages import read_module
            text=read_module(path,root,_verified)
            for depth, declaration, n in source_lines(text):
                if depth == 0 and not declaration.startswith(('component ', 'style ', 'import ', 'fn ', 'record ')):
                    raise ValueError(f'Line {number}: column 1: module {value}:{n} may only export components/styles/records/functions/imports')
            expanded, _, child_origins = expand(text, path, (*_stack, path), root, files, with_origins=True,_verified=_verified,_scoped=scoped)
            output.extend(expanded.splitlines())
            origins.extend(child_origins)
    except ValueError as exc:
        from sedrava_source_map import source_error
        mapped=source_error(exc,source_map)
        if mapped is exc:raise
        raise mapped from exc
    joined = '\n'.join(output)
    if len(joined) > MAX_SOURCE_CHARS:
        raise ValueError('Expanded imports exceed source limit')
    if not _stack:
        try:joined, origins = components(joined, origins)
        except ValueError as exc:
            from sedrava_source_map import source_error
            mapped=source_error(exc,origins)
            if mapped is exc:raise
            raise mapped from exc
    joined=ExpandedSource(joined,origins,source);joined.scoped=scoped;joined.entry=Path(source_path).resolve() if source_path else None
    return (joined, files, tuple(origins)) if with_origins else (joined, files)


def expand(source,source_path=None,*args,**kwargs):
    from sedrava_source_map import source_error,locations
    try:return _expand(source,source_path,*args,**kwargs)
    except ValueError as exc:
        mapped=source_error(exc,locations(source,source_path))
        if mapped is exc:raise
        raise mapped from exc


def components(source, origins=None):
    source_lines(source)
    traced = origins is not None
    if origins is None:
        origins = [(None, i) for i in range(1, len(source.splitlines()) + 1)]
    if len(origins) != len(source.splitlines()):
        raise ValueError('Source map does not match source lines')
    # Resolve definitions after imports. They are templates, never executable source.
    definitions = {}
    from sedrava_source_map import mapped_lines,origin_for,replace_span,ExpandedSource
    lines = mapped_lines(source,origins)
    kept = []
    kept_origins = []
    pos = 0
    while pos < len(lines):
        line = lines[pos]
        match = re.fullmatch(r'component ([A-Za-z][A-Za-z0-9_]*)(?:\((.*?)\))?:', line)
        if not match:
            kept.append(line); kept_origins.append(origins[pos]); pos += 1; continue
        name, parameters = match.groups()
        if name in definitions:
            raise ValueError(f'Line {pos+1}: column 1: duplicate component {name}')
        params = {}
        for declaration in parameters.split(',') if parameters else ():
            spec = re.fullmatch(r'\s*([A-Za-z][A-Za-z0-9_]*)\s*:\s*(text|int|bool|ref)\s*', declaration)
            if not spec or spec[1] in params:
                raise ValueError(f'Line {pos+1}: column 1: invalid component parameter')
            params[spec[1]] = {'text': str, 'int': int, 'bool': bool, 'ref':'reference'}[spec[2]]
        pos += 1; body = []; body_origins = []
        while pos < len(lines) and (not lines[pos].strip() or lines[pos].startswith(' ')):
            body.append(lines[pos]); body_origins.append(origins[pos]); pos += 1
        if not body or any(line.strip() and not line.startswith('    ') for line in body):
            raise ValueError('Component requires four-space-indented content')
        definitions[name] = (params, [line[4:] if line.startswith('    ') else line for line in body], body_origins)
    from sedrava_site import tokens
    from sedrava_source_map import LocatedError,Origin,source_error
    def fail_component(message,origin,col):
        path,line,column=origin.point(col) if isinstance(origin,Origin) else (*origin,col)
        if path is None:raise ValueError(f"Line {line}: column {column}: {message}")
        raise LocatedError(message,path,line,column)
    def validate_ui_line(line,origin):
        first=line.lstrip().split(maxsplit=1)
        if not first:return
        word=first[0].rstrip(':')
        if word in {"app","site","webapp","module","import","export","state","derive","action","record","fn","persist","rule","test","screen","view","navigation","require","for","repeat","if","else","while","return","let"} or re.match(r"\s*[A-Za-z_][A-Za-z_0-9]*\s*=(?!=)",line):
            fail_component("UI components cannot emit domain declarations or action statements",origin,len(line)-len(line.lstrip())+1)

    def instantiate(lines, line_origins, stack=()):
        result, result_origins = [], []
        i = 0
        while i < len(lines):
            line = lines[i]; origin = origin_for(line,line_origins[i]); i += 1
            call = re.fullmatch(r'( *)use ([A-Za-z][A-Za-z0-9_]*)(.*)', line)
            if not call:
                if stack:validate_ui_line(line,origin)
                result.append(line); result_origins.append(origin); continue
            prefix, name, rest = call.groups()
            if name not in definitions or name in stack or len(stack) >= MAX_BLOCK_DEPTH:
                fail_component(f"unknown/recursive component {name}",origin,len(prefix)+1)
            block = rest.rstrip().endswith(':')
            try:args = tokens(rest.rstrip()[:-1] if block else rest,1,call.start(3))
            except ValueError as exc:raise source_error(exc,(origin,)) from exc
            params, template, template_origins = definitions[name]
            if len(args) % 2:
                fail_component('component parameters require name/value pairs',origin,call.start(3)+1)
            values = {}
            value_origins={}
            for key, value in zip(args[::2], args[1::2]):
                if key.value in values or key.value not in params:
                    fail_component(f'invalid typed component parameter {key.value}',origin,value.span.column)
                expected=params[key.value]
                reference=expected=='reference'
                if (reference and (value.quoted or type(value.value) is not str or not re.fullmatch('[A-Za-z][A-Za-z0-9_]*',value.value))) or (not reference and type(value.value) is not expected):
                    fail_component(f'invalid typed component parameter {key.value}',origin,value.span.column)
                values[key.value] = value.value if reference else json.dumps(value.value, ensure_ascii=False)
                value_origins[key.value]=origin.point(value.span.column) if isinstance(origin,Origin) else (*origin,value.span.column)
            if set(values) != set(params):
                fail_component('component requires exact parameters',origin,call.start(3)+1)
            children, children_origins = [], []
            if block:
                while i < len(lines) and (not lines[i].strip() or len(lines[i])-len(lines[i].lstrip(' ')) > len(prefix)):
                    children.append(lines[i][len(prefix)+4:]); children_origins.append(line_origins[i]); i += 1
            slots = sum(line.strip() == 'slot' for line in template)
            if slots > 1 or bool(children) != bool(slots):
                fail_component('component slot requires matching content',origin,len(prefix)+1)
            expanded, expanded_origins = [], []
            for text, template_origin in zip(template, template_origins):
                if text.strip() == 'slot':
                    pad = text[:len(text)-len(text.lstrip(' '))]
                    expanded.extend(prefix+pad+child for child in children)
                    expanded_origins.extend(children_origins)
                else:
                    # Parameters use $name outside literals; expansion yields typed literal tokens.
                    edits=[];offset=0
                    for j,part in enumerate(re.split(r'("(?:[^"\\]|\\.)*")',text)):
                        if j%2==0:
                            for match in re.finditer(r'\$([A-Za-z][A-Za-z0-9_]*)',part):
                                if match[1] not in values:raise ValueError('Unknown component parameter '+match[1])
                                edits.append((offset+match.start(),offset+match.end(),values[match[1]],value_origins[match[1]]))
                        offset+=len(part)
                    for start,end,value,point in reversed(edits):text=replace_span(text,start,end,value,point)
                    expanded.append(prefix+text)
                    expanded_origins.append(template_origin)
            child_lines, child_locations = instantiate(expanded, expanded_origins, (*stack, name))
            result.extend(child_lines)
            result_origins.extend(child_locations)
            if sum(map(len, result)) > MAX_SOURCE_CHARS:
                raise ValueError('Expanded components exceed source limit')
        return result, result_origins
    result_lines, result_origins = instantiate(kept, kept_origins)
    result_origins=[origin_for(line,origin) for line,origin in zip(result_lines,result_origins)]
    result = ExpandedSource('\n'.join(result_lines)+'\n',result_origins)
    if len(result) > MAX_SOURCE_CHARS:
        raise ValueError('Expanded components exceed source limit')
    return (result, result_origins) if traced else result
