"""Experimental lexical namespaces for checked local .sdr modules.

This performs symbol-table based resolution before existing typed IR parsing.
It never evaluates imported source. Qualified references are resolved with
lexical tokens, not substring substitution inside strings or comments.
"""
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import keyword
import re
import tokenize
from io import StringIO

from sedrava_syntax import MAX_SOURCE_CHARS, source_lines
from sedrava_source_map import MappedLine,Origin,replace_span,origin_for,LocatedError,ExpandedSource

_IDENT = r'[A-Za-z][A-Za-z0-9_]*'
_MODULE = re.compile(rf'module ({_IDENT}(?:\.{_IDENT})*)\Z')
_IMPORT = re.compile(rf'import "([^"\n]+\.sdr)" as ({_IDENT})\Z')
_DECL = re.compile(rf'(export )?(component|style|record|fn|state|derive|action) ({_IDENT})(?=[(: \t])')
_RESERVED = re.compile(r'(?:M|L)_[0-9a-f]{12}_[A-Za-z][A-Za-z0-9_]*')


@dataclass(frozen=True)
class Symbol:
    module: str
    name: str
    kind: str
    emitted: str
    public: bool
    path: Path
    line: int


@dataclass(frozen=True)
class CompiledModule:
    module: str
    symbols: dict
    visible: dict
    text: str
    dependencies: tuple
    origins: tuple


def _tokens(line):
    """Identifiers and dots outside quoted literals and comments."""
    try:
        tokens=[t for t in tokenize.generate_tokens(StringIO(line + '\n').readline)
                if t.type not in (tokenize.NL, tokenize.NEWLINE, tokenize.ENDMARKER, tokenize.ENCODING)]
        if any(t.type==tokenize.NAME and not t.string.isascii() for t in tokens):raise ValueError('Namespace identifiers must be ASCII; implicit identifier normalization is forbidden')
        return tokens
    except (tokenize.TokenError, IndentationError) as exc:
        raise ValueError(f'Invalid lexical syntax: {exc}') from exc


def _rewrite(line, local=None, aliases=None, *, line_no=1, filename='<source>', excluded=()):
    """Resolve qualified and local identifiers using canonical Symbol objects.

    Changes only lexical NAME and NAME.DOT.NAME spans; the typed domain parser
    subsequently builds and checks the expression AST. Host code never runs.
    """
    local = local or {}
    aliases = aliases or {}
    excluded = set(excluded)
    line=line if isinstance(line,MappedLine) else MappedLine(line)
    try:toks = _tokens(line)
    except ValueError as exc:raise LocatedError(str(exc),filename,line_no,1) from exc
    ops = []
    i = 0
    while i < len(toks):
        t = toks[i]
        if t.type != tokenize.NAME:
            i += 1
            continue
        if i+1<len(toks) and toks[i+1].string=="=" and i>0 and toks[i-1].string in ("(",","):
            i+=1;continue
        alias = t.string
        if (alias in ('Result','list') and i+1<len(toks) and toks[i+1].string=='<') or (alias=='Error' and i>0 and i+1<len(toks) and toks[i-1].string==',' and toks[i+1].string=='>'):
            i+=1;continue
        if alias in aliases and i + 2 < len(toks) and toks[i+1].string == '.' and toks[i+2].type == tokenize.NAME:
            symbol_name = toks[i+2].string
            sym = aliases[alias].visible.get(symbol_name)
            if sym is None:
                raise LocatedError(f'{alias}.{symbol_name} is not an exported symbol',filename,line_no,t.start[1]+1)
            ops.append((t.start[1], toks[i+2].end[1], sym.emitted))
            i += 3
            continue
        if alias in aliases:
            pass
        elif alias in local and alias not in excluded and (i == 0 or toks[i-1].string != '.'):
            ops.append((t.start[1], t.end[1], local[alias].emitted))
        i += 1
    for start, end, value in reversed(ops):
        line = replace_span(line,start,end,value)
    return line


def _valid_import(source_path, value, root, line):
    path = Path(value)
    if path.is_absolute() or '..' in path.parts or '\\' in value or ':' in value or not value.endswith('.sdr'):
        raise ValueError(f'{source_path}:{line}: import must stay within the source directory')
    candidate = source_path.parent / path
    cursor = candidate
    while cursor != root and cursor != cursor.parent:
        if cursor.is_symlink():
            raise ValueError(f'{source_path}:{line}: symlink modules are forbidden')
        cursor = cursor.parent
    path = candidate.resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise ValueError(f'{source_path}:{line}: missing/outside-root module {value}')
    if path.stat().st_size > MAX_SOURCE_CHARS * 4:
        raise ValueError(f'{source_path}:{line}: module resource limit')
    return path


def _local_decl(line, module, path, n):
    m = _DECL.match(line)
    if not m:
        return None
    _, kind, name = m.groups()
    if keyword.iskeyword(name) or name.startswith(('M_','L_')):
        raise ValueError(f'{path}:{n}: reserved declaration name {name}')
    digest = sha256(module.encode('utf-8')).hexdigest()[:12]
    return Symbol(module, name, kind, f'M_{digest}_{name}', bool(m[1]), path, n)


def resolve_scoped(source, source_path, *, with_origins=False, verified=None):
    """Lower aliased imports while retaining legacy unqualified import support.

    Returns source text and checked dependency paths for manifests. Invoked
    only for the new explicit import-as syntax. Ordinary files are unchanged.
    """
    if source_path is None:
        raise ValueError('Aliased imports require a source file path')
    entry = Path(source_path).resolve()
    root = entry.parent
    cache = {}
    module_names = {}
    dependencies = set()
    loading = []
    total_chars=len(source)

    def load(path):
        nonlocal total_chars
        if path in cache:
            return cache[path]
        if path in loading or len(loading) >= 16:
            raise ValueError(f'{path}: cyclic/excessive aliased module imports')
        if len(cache) + len(loading) >= 32:
            raise ValueError('Aliased module resource limit')
        loading.append(path)
        try:
            from sedrava_packages import read_module
            text=read_module(path,root,verified)
            total_chars+=len(text)
            if total_chars>MAX_SOURCE_CHARS:raise ValueError("Combined module source resource limit")
            from sedrava_source_map import source_error,locations
            try:entries = source_lines(text)
            except ValueError as exc:raise source_error(exc,locations(text,path)) from exc
            if not entries or not (head := _MODULE.fullmatch(entries[0][1])) or entries[0][0] != 0:
                raise ValueError(f'{path}: line 1: namespaced import requires module org.name')
            module_id = head[1]
            if module_id in module_names and module_names[module_id] != path:
                raise ValueError(f'{path}: duplicate module identity {module_id}')
            module_names[module_id] = path
            lines = [MappedLine(line) for line in text.splitlines()]
            for no,raw in enumerate(lines,1):
                try:tokens_here=_tokens(raw)
                except ValueError as exc:raise LocatedError(str(exc),path,no,1) from exc
                if any(t.type==tokenize.NAME and _RESERVED.fullmatch(t.string) for t in tokens_here):
                    raise ValueError(f"{path}:{no}: reserved generated symbol identifier")
            symbols = {}
            aliases = {}
            nested = []
            for depth, raw, no in entries[1:]:
                if depth != 0:
                    continue
                import_match = _IMPORT.fullmatch(raw)
                if import_match:
                    value, alias = import_match.groups()
                    if alias in aliases or keyword.iskeyword(alias):
                        raise ValueError(f'{path}:{no}: duplicate/reserved import alias {alias}')
                    dep = _valid_import(path, value, root, no)
                    aliases[alias] = load(dep)
                    nested.append(dep)
                    continue
                if re.fullmatch(r'persist '+_IDENT,raw) or raw.startswith('rule '):continue
                if raw.startswith('import '):
                    raise ValueError(f'{path}:{no}: namespaced modules require explicit import aliases')
                sym = _local_decl(raw, module_id, path, no)
                if sym:
                    if sym.name in symbols or sym.name in aliases:
                        raise ValueError(f'{path}:{no}: duplicate declaration {sym.name}')
                    symbols[sym.name] = sym
                    continue
                raise ValueError(f'{path}:{no}: namespaces allow module/import and typed declarations only')
            if not symbols:
                raise ValueError(f'{path}: module has no declarations')
            for alias in aliases:
                if alias in symbols:
                    raise ValueError(f'{path}: ambiguous local symbol/import alias {alias}')
            result = []
            result_origins = []
            action_scopes=[]
            for no, line in enumerate(lines, 1):
                stripped = line.strip()
                if no == entries[0][2] or (not line.startswith(' ') and _IMPORT.fullmatch(stripped)):
                    continue
                if not line.strip() or stripped.startswith('#'):
                    result.append(line)
                    result_origins.append(origin_for(line,(path,no)))
                    continue
                m = _DECL.match(line) if not line.startswith(' ') else None
                if m:
                    sym = symbols[m[3]]
                    line=replace_span(line,m.start(3),m.end(3),sym.emitted)
                    if m[1]:line=replace_span(line,0,len('export '),'')
                    if sym.kind == 'fn':
                        signature = re.match(r'fn \w+\((.*?)\) ->', line)
                        bound = tuple(re.findall(rf'({_IDENT})\s*:', signature[1])) if signature else ()
                        if any(v in symbols or v in aliases for v in bound):
                            raise ValueError(f'{path}:{no}: function parameter conflicts with module symbol/import alias')
                        parameters={name:Symbol(module_id,name,'binding','L_'+sha256((module_id+':'+sym.name).encode()).hexdigest()[:12]+'_'+name,False,path,no) for name in bound}
                        line = _rewrite(line, {**symbols,**parameters}, aliases, line_no=no, filename=str(path))
                    elif sym.kind in ('record','state','derive','action'):
                        if sym.kind=='action':action_scopes=[(4,{})]
                        line = _rewrite(line, symbols if sym.kind!='record' else {}, aliases, line_no=no, filename=str(path))
                    result.append(line)
                    result_origins.append(origin_for(line,(path,no)))
                    continue
                if re.fullmatch(r'persist '+_IDENT,line) or line.startswith('rule '):
                    result.append(_rewrite(line,symbols,aliases,line_no=no,filename=str(path)));result_origins.append(origin_for(result[-1],(path,no)));continue
                if not line.startswith(' '):
                    raise ValueError(f'{path}:{no}: invalid top-level module construct')
                owner=next((symbols[m[3]] for earlier in reversed(lines[:no-1]) if (m:=_DECL.match(earlier))),None)
                if owner and owner.kind=='action':
                    depth=len(line)-len(line.lstrip(' '))
                    while len(action_scopes)>1 and action_scopes[-1][0]>depth:action_scopes.pop()
                    if action_scopes[-1][0]<depth:action_scopes.append((depth,{}))
                    visible={name:value for _,scope in action_scopes for name,value in scope.items()}
                    bound=re.match(r'\s*(let|repeat|for) ([A-Za-z][A-Za-z0-9_]*)(?:, ([A-Za-z][A-Za-z0-9_]*))?',line)
                    fresh={}
                    if bound:
                        names=[name for name in bound.groups()[1:] if name]
                        if any(name in symbols or name in aliases for name in names):raise ValueError(f'{path}:{no}: action binding conflicts with module symbol/import alias')
                        fresh={name:Symbol(module_id,name,'binding','L_'+sha256((module_id+':'+owner.name).encode()).hexdigest()[:12]+'_'+name,False,path,no) for name in names}
                    line=_rewrite(line,{**symbols,**visible,**fresh},aliases,line_no=no,filename=str(path))
                    if bound:
                        if bound[1]=='let':action_scopes[-1][1].update(fresh)
                        else:action_scopes.append((depth+4,fresh))
                elif re.match(r'^\s*use\s+', line):
                    line = _rewrite(line, {n:s for n,s in symbols.items() if s.kind=='component'}, aliases, line_no=no, filename=str(path))
                elif re.search(r'\bstyle\s+(?:[A-Za-z][A-Za-z0-9_]*)(?![A-Za-z0-9_])', line):
                    line = _rewrite(line, {n:s for n,s in symbols.items() if s.kind=='style'}, aliases, line_no=no, filename=str(path))
                elif re.match(r'^\s*\w+\s*:\s*', line):
                    colon=line.index(':')
                    line=line[:colon+1]+_rewrite(line[colon+1:], {n:s for n,s in symbols.items() if s.kind=='record'}, aliases, line_no=no, filename=str(path))
                line=_rewrite(line,{},aliases,line_no=no,filename=str(path))
                if owner and owner.kind=='component':line=_rewrite_ui_references(line,symbols)
                result.append(line)
                result_origins.append(origin_for(line,(path,no)))
            built = CompiledModule(module_id, symbols, {n:s for n,s in symbols.items() if s.public}, '\n'.join(result), tuple(nested), tuple(result_origins))
            cache[path] = built
            dependencies.add(path)
            return built
        finally:
            loading.pop()

    aliases = {}
    for depth, raw, no in source_lines(source):
        if depth != 0:
            continue
        m = _IMPORT.fullmatch(raw)
        if not m:
            continue
        value, alias = m.groups()
        if alias in aliases or keyword.iskeyword(alias):
            raise ValueError(f'{entry}:{no}: duplicate/reserved import alias {alias}')
        path = _valid_import(entry, value, root, no)
        aliases[alias] = load(path)
    if not aliases:
        if with_origins:
            from sedrava_source_map import locations
            return source, dependencies, locations(source, entry)
        return source, dependencies
    for depth, raw, no in source_lines(source):
        if any(t.type == tokenize.NAME and _RESERVED.fullmatch(t.string) for t in _tokens(raw)):
            raise ValueError(f'{entry}:{no}: reserved generated symbol identifier')
    for alias in aliases:
        if re.search(rf'^(?:state|derive|fn|record|action|component|style|view|service) {re.escape(alias)}(?:\s|\(|:|=)', source, re.M):
            raise ValueError(f'{entry}: local declaration collides with import alias {alias}')
    emitted = set()
    def append_dependency(path, out, source_map):
        if path in emitted:
            return
        for child in cache[path].dependencies:
            append_dependency(child, out, source_map)
        emitted.add(path)
        lines = cache[path].text.splitlines()
        out.extend(lines)
        source_map.extend(cache[path].origins)
    out = []
    source_map = []
    for no, line in enumerate(source.splitlines(), 1):
        m = _IMPORT.fullmatch(line)
        if m:
            path = _valid_import(entry, m[1], root, no)
            append_dependency(path, out, source_map)
        elif line.startswith('import "') and ' as ' in line and not m:
            raise ValueError(f'{entry}:{no}: invalid namespaced import')
        else:
            out.append(_rewrite(line, aliases=aliases, filename=str(entry), line_no=no))
            source_map.append(origin_for(out[-1],(entry,no)))
    out,source_map=_schedule_domain(out,source_map,entry)
    output = '\n'.join(out) + '\n'
    if len(output) > MAX_SOURCE_CHARS:
        raise ValueError('Expanded imports exceed source limit')
    output=ExpandedSource(output,source_map)
    output.public_symbols={alias+'.'+name:symbol.emitted for alias,module in aliases.items() for name,symbol in module.visible.items()}
    output.display_names={symbol.emitted:symbol.name for module in cache.values() for symbol in module.symbols.values()}
    for public,emitted_name in reversed(list(output.public_symbols.items())):output.display_names[emitted_name]=public
    if with_origins:
        assert len(source_map) == len(output.splitlines())
        return output, dependencies, tuple(source_map)
    return output, dependencies


def _schedule_domain(lines,origins,entry):
    """Hoist only imported state/derive/action blocks; entry order stays checked."""
    pending={k:[] for k in ('state','derive','action','rule')};kept=[];where=[];i=0
    while i<len(lines):
        match=re.match(r'(state|persist|derive|action) M_[0-9a-f]{12}_',lines[i])
        is_rule=lines[i].startswith('rule ')
        if (match or is_rule) and origins[i][0]!=entry:
            kind='rule' if is_rule else 'state' if match[1]=='persist' else match[1];block=[]
            block.append((lines[i],origins[i]));i+=1
            while i<len(lines) and (not lines[i].strip() or lines[i].startswith(' ')):
                block.append((lines[i],origins[i]));i+=1
            pending[kind].extend(block)
        else:kept.append(lines[i]);where.append(origins[i]);i+=1
    for kind,trigger in [('state',r'^(?:state|persist|derive|action|rule|test|screen|view|navigation) '),('derive',r'^(?:derive|action|rule|test|screen|view|navigation) '),('action',r'^(?:action|rule|test|screen|view|navigation) '),('rule',r'^(?:rule|test|screen|view|navigation) ')]:
        if not pending[kind]:continue
        position=next((i for i,line in enumerate(kept) if re.match(trigger,line)),len(kept))
        kept[position:position]=[x[0] for x in pending[kind]];where[position:position]=[x[1] for x in pending[kind]]
    return kept,where


def _rewrite_ui_references(line,symbols):
    """Rewrite typed binding positions, never property names or literal labels."""
    toks=_tokens(line);edits={}
    kinds={'state':{'state','derive'},'action':{'action'},'collection':{'state'},'select':{'state'},'search':{'state'},'equals':{'state','derive'},'active':{'state','derive'}}
    for index,token in enumerate(toks[:-1]):
        value=toks[index+1]
        if token.type==tokenize.NAME and token.string in kinds and value.type==tokenize.NAME and value.string in symbols and symbols[value.string].kind in kinds[token.string]:edits[value.start[1]]=(value.end[1],symbols[value.string].emitted)
        if token.string in ('>','->') and value.type==tokenize.NAME and value.string in symbols and symbols[value.string].kind=='action':edits[value.start[1]]=(value.end[1],symbols[value.string].emitted)
    positional=re.match(r'\s*(?:value|when|input_text|input_int|show_text) ([A-Za-z][A-Za-z0-9_]*)',line)
    if positional and positional[1] in symbols and symbols[positional[1]].kind in ('state','derive'):edits[positional.start(1)]=(positional.end(1),symbols[positional[1]].emitted)
    for start,(end,value) in sorted(edits.items(),reverse=True):line=replace_span(line,start,end,value)
    return line
