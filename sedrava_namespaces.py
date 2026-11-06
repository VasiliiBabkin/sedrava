"""Experimental lexical namespaces for checked local .sdr modules.

This performs symbol-table based resolution before existing typed IR parsing.
It never evaluates imported source. Qualified references are resolved with
lexical tokens, not substring substitution inside strings or comments.
"""
from collections import ChainMap
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import re
import tokenize
from io import StringIO

from sedrava_syntax import MAX_SOURCE_CHARS, source_lines, is_reserved_identifier, physical_lines
from sedrava_source_map import MappedLine,Origin,replace_span,replace_spans,origin_for,LocatedError,ExpandedSource

_IDENT = r'[A-Za-z][A-Za-z0-9_]*'
_MODULE = re.compile(rf'module ({_IDENT}(?:\.{_IDENT})*)\Z')
_IMPORT = re.compile(rf'import "([^"\n]+\.sdr)" as ({_IDENT})\Z')
_DECL = re.compile(rf'(export )?(component|style|record|fn|state|derive|action|error (?:closed|open)) ({_IDENT})(?=[(: \t])')
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


def _rewrite(line, local=None, aliases=None, *, line_no=1, filename='<source>', excluded=(), type_context=False, protected=()):
    """Resolve qualified and local identifiers using canonical Symbol objects.

    Changes only lexical NAME and NAME.DOT.NAME spans; the typed domain parser
    subsequently builds and checks the expression AST. Host code never runs.
    """
    local = local or {}
    aliases = aliases or {}
    excluded = set(excluded)
    protected = set(protected)
    line=line if isinstance(line,MappedLine) else MappedLine(line)
    try:toks = _tokens(line)
    except ValueError as exc:raise LocatedError(str(exc),filename,line_no,1) from exc
    ops = []
    i = 0
    while i < len(toks):
        t = toks[i]
        if t.type != tokenize.NAME or t.start[1] in protected:
            i += 1
            continue
        if i+1<len(toks) and toks[i+1].string=="=" and i>0 and toks[i-1].string in ("(",","):
            i+=1;continue
        alias = t.string
        if type_context and ((alias in ('Result','list') and i+1<len(toks) and toks[i+1].string=='<') or (alias=='Error' and i>0 and i+1<len(toks) and toks[i-1].string==',' and toks[i+1].string=='>')):
            i+=1;continue
        if alias in aliases and i + 2 < len(toks) and toks[i+1].string == '.' and toks[i+2].type == tokenize.NAME:
            symbol_name = toks[i+2].string
            sym = aliases[alias].visible.get(symbol_name)
            if sym is None:
                raise LocatedError(f'{alias}.{symbol_name} is not an exported symbol',*origin_for(line,(filename,line_no)).point(t.start[1]+1))
            ops.append((t.start[1], toks[i+2].end[1], sym.emitted))
            i += 3
            continue
        if alias in aliases:
            pass
        elif alias in local and alias not in excluded and (i == 0 or toks[i-1].string != '.'):
            ops.append((t.start[1], t.end[1], local[alias].emitted))
        i += 1
    if len(line)+sum(len(value)-(end-start) for start,end,value in ops)>MAX_SOURCE_CHARS:
        raise LocatedError("Expanded module source resource limit",*origin_for(line,(filename,line_no)).point(1))
    return replace_spans(line,ops)


def _valid_import(source_path, value, root, line):
    path = Path(value)
    if path.is_absolute() or '..' in path.parts or '\\' in value or ':' in value or not value.endswith('.sdr'):
        raise LocatedError(f'import must stay within the source directory',source_path,line,1)
    candidate = source_path.parent / path
    cursor = candidate
    while cursor != root and cursor != cursor.parent:
        if cursor.is_symlink():
            raise LocatedError(f'symlink modules are forbidden',source_path,line,1)
        cursor = cursor.parent
    path = candidate.resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise LocatedError(f'missing/outside-root module {value}',source_path,line,1)
    if path.stat().st_size > MAX_SOURCE_CHARS * 4:
        raise LocatedError(f'module resource limit',source_path,line,1)
    return path


def _replace_regions(line, regions):
    for start, end, replacement in sorted(regions, key=lambda item:item[0], reverse=True):
        line = line[:start] + replacement + line[end:]
    return line


def _lower_function(line, symbols, aliases, module, name, path, number):
    from sedrava_functions import FUNCTION_DECLARATION, PARAMETER_DECLARATION, split_parameters, MAX_FUNCTION_PARAMETERS
    declaration = FUNCTION_DECLARATION.fullmatch(line)
    if not declaration:
        return line  # The common parser diagnoses malformed declarations.
    parameters, regions, cursor = {}, [], declaration.start(2)
    records = {key:value for key,value in symbols.items() if value.kind in ('record','error')}
    try:
        parameter_sources=split_parameters(declaration[2])
    except ValueError as exc:
        raise LocatedError(str(exc),*origin_for(line,(path,number)).point(declaration.start(2)+1)) from exc
    if len(parameter_sources)>MAX_FUNCTION_PARAMETERS:
        raise LocatedError("function parameter resource limit",*origin_for(line,(path,number)).point(declaration.start(2)+1))
    for raw in parameter_sources:
        start = line.find(raw, cursor)
        cursor = start + len(raw) + 1
        parameter = PARAMETER_DECLARATION.fullmatch(raw)
        if not parameter:
            return line
        key = parameter[1]
        position = origin_for(line,(path,number)).point(start+parameter.start(1)+1)
        if is_reserved_identifier(key):
            raise LocatedError('reserved function parameter '+key,*position)
        if key in symbols or key in aliases:
            raise LocatedError('function parameter conflicts with module symbol/import alias',*position)
        binding = Symbol(module,key,'binding','L_'+sha256((module+':'+name).encode()).hexdigest()[:12]+'_'+key,False,path,number)
        parameters[key] = binding
        first, last = start+parameter.start(1), start+parameter.end(1)
        regions.append((first,last,replace_span(line[first:last],0,last-first,binding.emitted)))
        first, last = start+parameter.start(2), start+parameter.end(2)
        regions.append((first,last,_rewrite(line[first:last],records,aliases,line_no=number,filename=str(path),type_context=True)))
    for group, local, typed in [(3,records,True),(4,{**symbols,**parameters},False)]:
        first,last = declaration.start(group),declaration.end(group)
        regions.append((first,last,_rewrite(line[first:last],local,aliases,line_no=number,filename=str(path),type_context=typed)))
    return _replace_regions(line,regions)


def _lower_value_declaration(line, symbols, aliases, path, number):
    depth = 0
    equal = None
    for token in _tokens(line):
        if token.string in ('(','[','<'):depth+=1
        elif token.string in (')',']','>'):depth-=1
        elif token.string=='=' and depth==0:
            equal=token.start[1]
            break
    if equal is None:
        return line
    regions = [(equal+1,len(line),_rewrite(line[equal+1:],symbols,aliases,line_no=number,filename=str(path)))]
    colon = line.find(':',0,equal)
    if colon>=0:
        records={key:value for key,value in symbols.items() if value.kind in ('record','error')}
        regions.append((colon+1,equal,_rewrite(line[colon+1:equal],records,aliases,line_no=number,filename=str(path),type_context=True)))
    return _replace_regions(line,regions)


def _lower_action_line(line, symbols, aliases, scopes, module, action, path, number):
    depth=len(line)-len(line.lstrip(' '))
    while len(scopes)>1 and scopes[-1][0]>depth:scopes.pop()
    if scopes[-1][0]<depth:scopes.append((depth,{}))
    # Match patterns carry both field labels and scoped value binders. Lower only
    # binder spans, preserving variant/field identities for the common checker.
    stripped=line.lstrip(' ')
    if stripped.startswith(('Ok(', 'Err(')):
        from sedrava_errors import pattern,valid_name
        try:tag,entries=pattern(stripped)
        except ValueError:return line  # The core reports malformed patterns.
        fresh={};edits=[]
        for field,key,start,end in entries:
            start+=depth;end+=depth
            if not valid_name(key) or key in symbols or key in aliases:
                raise LocatedError('invalid/shadowing match binding '+key,*origin_for(line,(path,number)).point(start+1))
            emitted='L_'+sha256((module+':'+action+':'+str(number)).encode()).hexdigest()[:12]+'_'+key
            fresh[key]=Symbol(module,key,'binding',emitted,False,path,number)
            shorthand=bool(field) and line[:start].rstrip().endswith(('{',','))
            edits.append((start,end,field+': '+emitted if shorthand else emitted))
        scopes.append((depth+4,fresh))
        return replace_spans(line,edits)
    bound=re.match(r'\s*(let|repeat|for) ([A-Za-z][A-Za-z0-9_]*)(?:, ([A-Za-z][A-Za-z0-9_]*))?',line)
    fresh={}
    if bound:
        names=[key for key in bound.groups()[1:] if key]
        for group in (2,3):
            if bound[group] and is_reserved_identifier(bound[group]):
                raise LocatedError('reserved action binding '+bound[group],*origin_for(line,(path,number)).point(bound.start(group)+1))
        if any(key in symbols or key in aliases for key in names):
            raise LocatedError('action binding conflicts with module symbol/import alias',path,number,1)
        fresh={key:Symbol(module,key,'binding','L_'+sha256((module+':'+action).encode()).hexdigest()[:12]+'_'+key,False,path,number) for key in names}
    # Statement keywords are syntax; the same words remain usable in expressions.
    protected=set()
    head=re.match(r'\s*([A-Za-z][A-Za-z0-9_]*)',line)
    assignment=re.match(r'\s*[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)?\s*=(?!=)',line)
    if head and not assignment:
        protected.add(head.start(1))
        if head[1]=='repeat':
            constructor=re.match(r'\s*repeat [A-Za-z][A-Za-z0-9_]* in (range)\(',line)
            if constructor:protected.add(constructor.start(1))
    lowered=_rewrite(line,ChainMap(fresh,*(scope for _,scope in reversed(scopes)),symbols),aliases,line_no=number,filename=str(path),protected=protected)
    if bound:
        if bound[1]=='let':scopes[-1][1].update(fresh)
        else:scopes.append((depth+4,fresh))
    return lowered


def _local_decl(line, module, path, n):
    m = _DECL.match(line)
    if not m:
        return None
    _, kind, name = m.groups()
    if kind.startswith('error '):
        from sedrava_errors import valid_error_name
        if not valid_error_name(name):raise LocatedError('invalid/reserved error type '+name,path,n,m.start(3)+1)
        kind='error'
    if is_reserved_identifier(name) or name.startswith(('M_','L_')):
        raise LocatedError(f'reserved declaration name {name}',path,n,m.start(3)+1)
    digest = sha256(module.encode('utf-8')).hexdigest()[:12]
    return Symbol(module, name, kind, f'M_{digest}_{name}', bool(m[1]), path, n)


def _check_entry_binders(line, aliases, path, number):
    from sedrava_functions import FUNCTION_DECLARATION, PARAMETER_DECLARATION, split_parameters
    function=FUNCTION_DECLARATION.fullmatch(line)
    if function:
        try:parameters=split_parameters(function[2])
        except ValueError:return  # Common parser retains responsibility for syntax.
        cursor=function.start(2)
        for raw in parameters:
            start=line.find(raw,cursor);cursor=start+len(raw)+1
            parameter=PARAMETER_DECLARATION.fullmatch(raw)
            if parameter and parameter[1] in aliases:
                raise LocatedError('function parameter conflicts with import alias',*origin_for(line,(path,number)).point(start+parameter.start(1)+1))
    stripped=line.lstrip(' ')
    if stripped.startswith(('Ok(', 'Err(')):
        from sedrava_errors import pattern
        try:_,entries=pattern(stripped)
        except ValueError:return
        for _,key,start,_ in entries:
            if key in aliases:raise LocatedError('match binding conflicts with import alias',*origin_for(line,(path,number)).point(len(line)-len(stripped)+start+1))
        return
    offset=0
    action=re.match(r'action [A-Za-z][A-Za-z0-9_]*:\s*',line)
    if action:offset=action.end()
    bound=re.match(r'\s*(let|repeat|for) ([A-Za-z][A-Za-z0-9_]*)(?:, ([A-Za-z][A-Za-z0-9_]*))?',line[offset:])
    if bound:
        for group in (2,3):
            if bound[group] in aliases:
                raise LocatedError('action binding conflicts with import alias',*origin_for(line,(path,number)).point(offset+bound.start(group)+1))


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

    def load(path,at=None):
        nonlocal total_chars
        if path in cache:
            return cache[path]
        if path in loading or len(loading) >= 16:
            raise LocatedError('cyclic/excessive aliased module imports',*(at or (path,1)),1)
        if len(cache) + len(loading) >= 32:
            raise LocatedError('Aliased module resource limit',*(at or (path,1)),1)
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
                raise LocatedError('namespaced import requires module org.name',path,entries[0][2] if entries else 1,1)
            module_id = head[1]
            if module_id in module_names and module_names[module_id] != path:
                raise LocatedError(f'duplicate module identity {module_id}',path,entries[0][2],1)
            module_names[module_id] = path
            lines = [MappedLine(line) for line in physical_lines(text)]
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
                    if alias in aliases or is_reserved_identifier(alias):
                        raise LocatedError(f'duplicate/reserved import alias {alias}',path,no,import_match.start(2)+1)
                    dep = _valid_import(path, value, root, no)
                    aliases[alias] = load(dep,(path,no))
                    nested.append(dep)
                    continue
                if re.fullmatch(r'persist '+_IDENT,raw) or raw.startswith('rule '):continue
                if raw.startswith('import '):
                    raise LocatedError(f'namespaced modules require explicit import aliases',path,no,1)
                sym = _local_decl(raw, module_id, path, no)
                if sym:
                    if sym.name in symbols or sym.name in aliases:
                        raise LocatedError(f'duplicate declaration {sym.name}',path,no,1)
                    symbols[sym.name] = sym
                    continue
                raise LocatedError(f'namespaces allow module/import and typed declarations only',path,no,1)
            if not symbols:
                raise LocatedError('module has no declarations',path,entries[0][2],1)
            for alias in aliases:
                if alias in symbols:
                    raise ValueError(f'{path}: ambiguous local symbol/import alias {alias}')
            result = []
            result_origins = []
            action_scopes=[]
            owner=None
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
                    owner = sym
                    line=replace_span(line,m.start(3),m.end(3),sym.emitted)
                    if m[1]:line=replace_span(line,0,len('export '),'')
                    if sym.kind=='error' and ' id ' not in line:
                        colon=line.rfind(':');line=replace_span(line,colon,colon,' id '+__import__('json').dumps(module_id+'.'+sym.name))
                    if sym.kind == 'fn':
                        line = _lower_function(line, symbols, aliases, module_id, sym.name, path, no)
                    elif sym.kind in ('state','derive'):
                        line = _lower_value_declaration(line, symbols, aliases, path, no)
                    elif sym.kind=='action':
                        action_scopes=[(4,{})]
                        colon=line.index(':')
                        if line[colon+1:].strip():
                            result.append(line[:colon+1])
                            result_origins.append(origin_for(result[-1],(path,no)))
                            begin=colon+1
                            while begin<len(line) and line[begin]==' ':begin+=1
                            line=_lower_action_line('    '+line[begin:],symbols,aliases,action_scopes,module_id,sym.name,path,no)
                    result.append(line)
                    result_origins.append(origin_for(line,(path,no)))
                    continue
                if re.fullmatch(r'persist '+_IDENT,line) or line.startswith('rule '):
                    prefix=line.index(' ')+1
                    result.append(line[:prefix]+_rewrite(line[prefix:],symbols,aliases,line_no=no,filename=str(path)));result_origins.append(origin_for(result[-1],(path,no)));continue
                if not line.startswith(' '):
                    raise LocatedError(f'invalid top-level module construct',path,no,1)
                if owner and owner.kind=='error':
                    result.append(line);result_origins.append(origin_for(line,(path,no)));continue
                if owner and owner.kind=='record':
                    colon=line.find(':')
                    if colon<0:
                        use=re.match(r'\s*use\s+',line)
                        if use:line=line[:use.end()]+_rewrite(line[use.end():],{key:value for key,value in symbols.items() if value.kind=='component'},aliases,line_no=no,filename=str(path))
                    else:
                        records={key:value for key,value in symbols.items() if value.kind in ('record','error')}
                        line=line[:colon+1]+_rewrite(line[colon+1:],records,aliases,line_no=no,filename=str(path),type_context=True)
                    result.append(line)
                    result_origins.append(origin_for(line,(path,no)))
                    continue
                if owner and owner.kind=='action':
                    line=_lower_action_line(line,symbols,aliases,action_scopes,module_id,owner.name,path,no)
                elif use:=re.match(r'^\s*use\s+', line):
                    line = line[:use.end()]+_rewrite(line[use.end():], {n:s for n,s in symbols.items() if s.kind=='component'}, aliases, line_no=no, filename=str(path))
                elif style:=re.search(r'\bstyle\s+([A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)?)',line):
                    line = line[:style.start(1)]+_rewrite(line[style.start(1):style.end(1)],{n:s for n,s in symbols.items() if s.kind=='style'},aliases,line_no=no,filename=str(path))+line[style.end(1):]
                elif re.match(r'^\s*\w+\s*:\s*', line):
                    colon=line.index(':')
                    line=line[:colon+1]+_rewrite(line[colon+1:], {n:s for n,s in symbols.items() if s.kind=='record'}, aliases, line_no=no, filename=str(path),type_context=True)
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
        if alias in aliases or is_reserved_identifier(alias):
            raise LocatedError(f'duplicate/reserved import alias {alias}',entry,no,m.start(2)+1)
        path = _valid_import(entry, value, root, no)
        aliases[alias] = load(path,(entry,no))
    if not aliases:
        if with_origins:
            from sedrava_source_map import locations
            return source, dependencies, locations(source, entry)
        return source, dependencies
    for depth, raw, no in source_lines(source):
        if any(t.type == tokenize.NAME and _RESERVED.fullmatch(t.string) for t in _tokens(raw)):
            raise LocatedError(f'reserved generated symbol identifier',entry,no,1)
    for alias in aliases:
        if re.search(rf'^(?:state|derive|fn|record|error (?:closed|open)|action|component|style|view|service) {re.escape(alias)}(?:\s|\(|:|=)', source, re.M):
            raise ValueError(f'{entry}: local declaration collides with import alias {alias}')
    emitted = set()
    def append_dependency(path, out, source_map):
        if path in emitted:
            return
        for child in cache[path].dependencies:
            append_dependency(child, out, source_map)
        emitted.add(path)
        lines = physical_lines(cache[path].text)
        out.extend(lines)
        source_map.extend(cache[path].origins)
    out = []
    source_map = []
    entry_record=False
    for no, line in enumerate(physical_lines(source), 1):
        line=MappedLine(line)
        if line.strip() and not line.startswith(' ') and not line.startswith('#'):
            entry_record=bool(re.match(r'(?:record |error (?:closed|open) )',line))
        m = _IMPORT.fullmatch(line)
        if m:
            path = _valid_import(entry, m[1], root, no)
            append_dependency(path, out, source_map)
        elif line.startswith('import "') and ' as ' in line and not m:
            raise LocatedError(f'invalid namespaced import',entry,no,1)
        else:
            if entry_record and line.startswith(' '):
                colon=line.find(':')
                lowered=_rewrite(line,aliases=aliases,filename=str(entry),line_no=no) if colon<0 else line[:colon+1]+_rewrite(line[colon+1:],aliases=aliases,filename=str(entry),line_no=no,type_context=True)
            else:
                _check_entry_binders(line,aliases,entry,no)
                lowered=_rewrite(line, aliases=aliases, filename=str(entry), line_no=no)
            out.append(lowered)
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
        assert len(source_map) == len(physical_lines(output))
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
