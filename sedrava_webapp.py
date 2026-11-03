"""Experimental Sedrava webapp v0.11: typed app state and responsive Web UI.

The core's parser, action compiler and persistence semantics are reused; this
module does not interpret Sedrava actions. Supports bounded collection
rendering and selection alongside scalar/derived values. No HTTP, multi-view
navigation, or inline arbitrary code.
"""
from dataclasses import dataclass, field
import html
import json
import os
from pathlib import Path
import re
import tempfile

from sedrava_core import parse as parse_app, run, type_of
from sedrava_records import ListType, value_type
from sedrava_syntax import source_lines, MAX_BLOCK_DEPTH
from sedrava_site import (BREAKPOINTS, COMMON, COMPONENTS, THEME, Component,
                          Definition, Parameter, Property, Span, choice, fail,
                          identifier, properties, text, tokens, walk)
from site_codegen import CSS, declarations, digest, tree_bytes
from web_codegen import generate as generate_legacy_web, js_expr, json_script
from sedrava_version import VERSION


@dataclass(frozen=True)
class WebApp:
    name: str
    program: object
    widgets: tuple
    mode: str = "webapp"
    views: dict = field(default_factory=dict)
    services: dict = field(default_factory=dict)
    theme: dict = field(default_factory=lambda:dict(THEME))
    styles: dict = field(default_factory=dict)
    settings: dict = field(default_factory=dict)
    themes: dict = field(default_factory=dict)


UI_LAYOUT = frozenset(("container", "row", "column", "grid", "card",
                       "callout", "heading", "paragraph", "code",
                       "spacer", "divider", "link", "image", "navbar", "footer"))
UI_DYNAMIC = {
    "request": Definition("button", positional="text", required=("text","service"), parameters={"text":Parameter(text),"service":Parameter(identifier)}),
    "cancel": Definition("button", positional="text", required=("text","service"), parameters={"text":Parameter(text),"service":Parameter(identifier)}),
    "remote": Definition("section", required=("service",), parameters={"service":Parameter(identifier),"search":Parameter(identifier),"title":Parameter(identifier)}),
    "form": Definition("form", children=True, required=("action",), parameters={"action": Parameter(identifier)}),
    "submit": Definition("button", positional="text", required=("text",), parameters={"text": Parameter(text)}, defaults={"variant":"primary"}, variants=("primary","secondary","ghost")),
    "dialog": Definition("dialog", children=True, required=("id","label")),
    "open": Definition("button", positional="text", required=("text","to"), parameters={"text":Parameter(text),"to":Parameter(identifier)}),
    "close": Definition("button", positional="text", required=("text","to"), parameters={"text":Parameter(text),"to":Parameter(identifier)}),
    "select": Definition("select", children=True, required=("state","label"), parameters={"state":Parameter(identifier)}),
    "option": Definition("option", positional="text", required=("text","value"), parameters={"text":Parameter(text),"value":Parameter(lambda v:v)}),
    "navigate": Definition("button", positional="text", required=("text", "to"), parameters={"text": Parameter(text), "to": Parameter(identifier), "action": Parameter(identifier)}),
    "back": Definition("button", positional="text", required=("text",), parameters={"text": Parameter(text)}),
    "value": Definition("output", required=("state",),
                        parameters={"state": Parameter(identifier)}),
    "input": Definition("input", required=("state", "label"),
                        parameters={"state": Parameter(identifier),"kind":Parameter(choice("text","textarea","email","url"))}),
    "checkbox": Definition("input", required=("state", "label"),
                           parameters={"state": Parameter(identifier)}),
    "when": Definition("section", children=True, required=("state",),
                       parameters={"state": Parameter(identifier)}),
    "list": Definition("ul", required=("collection", "select"),
                       parameters={"collection": Parameter(identifier),
                                   "select": Parameter(identifier),
                                   "title": Parameter(identifier),
                                   "status": Parameter(identifier), "search": Parameter(identifier), "sort": Parameter(identifier), "where": Parameter(identifier), "equals": Parameter(identifier), "active": Parameter(identifier), "empty": Parameter(text)}),
    "button": Definition("button", positional="text",
                         required=("text", "action"),
                         parameters={"text": Parameter(text),
                                     "action": Parameter(identifier)},
                         defaults={"variant": "primary"},
                         variants=("primary", "secondary", "ghost")),
}

from dataclasses import replace
UI_DYNAMIC['field']=Definition('output',required=('field',),parameters={'field':Parameter(identifier)})
UI_DYNAMIC['row-when']=Definition('section',children=True,required=('field',),parameters={'field':Parameter(identifier)})
UI_DYNAMIC['pick']=Definition('button',positional='text',required=('text',),parameters={'text':Parameter(text)})
UI_DYNAMIC['each']=replace(UI_DYNAMIC['list'],tag='section',children=True)
UI_DYNAMIC['table']=replace(UI_DYNAMIC['list'],tag='div',parameters={**UI_DYNAMIC['list'].parameters,'fields':Parameter(text)})


def parse_webapp(source):
    from sedrava_modules import components
    source = components(source)
    from sedrava_web_assets import read_directives
    source, settings = read_directives(source)
    raw=source.splitlines();kept=[];presentation=[];named_themes={};pos=0
    while pos<len(raw):
        named=re.fullmatch(r'theme ([A-Za-z][A-Za-z0-9_-]*):',raw[pos])
        if named:
            if named[1] in named_themes or len(named_themes)>=8:raise ValueError('Duplicate/excessive named theme')
            theme_lines=['theme:'];kept.append('');pos+=1
            while pos<len(raw) and (not raw[pos].strip() or raw[pos].startswith(' ')):
                theme_lines.append(raw[pos]);kept.append('');pos+=1
            named_themes[named[1]]='\n'.join(theme_lines);continue
        if re.fullmatch(r'theme:|style [A-Za-z][A-Za-z0-9_-]*:',raw[pos]):
            presentation.append(raw[pos]);kept.append('');pos+=1
            while pos<len(raw) and (not raw[pos].strip() or raw[pos].startswith(' ')):
                presentation.append(raw[pos]);kept.append('');pos+=1
        else:kept.append(raw[pos]);pos+=1
    from sedrava_site import parse_site
    style_doc=parse_site('site "settings"\n'+'\n'.join(presentation)+'\npage home at "/":\n    title "settings"\n    heading "settings"\n')
    theme_palettes={name:parse_site('site "theme"\n'+text+'\npage home at "/":\n    title "theme"\n    heading "theme"\n').theme for name,text in named_themes.items()}
    source='\n'.join(kept)+'\n' 
    from sedrava_web_services import extract_services, validate_services
    source, service_blocks = extract_services(source)
    lines = source_lines(source)
    if not lines or not re.fullmatch(r'webapp\s+".+"', lines[0][1]):
        raise ValueError("Line 1: column 1: Expected webapp \"Title\"")
    view_lines = [(i, item) for i, item in enumerate(lines)
                  if item[0] == 0 and item[1].startswith("view ")]
    if not view_lines or not any(re.fullmatch(r'view main(?: at "/")?:', item[1]) for _,item in view_lines):
        fail(Span(lines[0][2], 1), "Exactly one initial view main is required")
    views={}
    for _,(_,header,n) in view_lines:
        match=re.fullmatch(r'view ([A-Za-z][A-Za-z0-9_]*)(?: at "([^"]+)")?(?: when ([A-Za-z][A-Za-z0-9_]*))?:',header)
        if not match or match[1] in views:fail(Span(n,1),"Exactly one declaration per view; invalid or duplicate view")
        name,path,guard=match.groups();path=path or ('/' if name=='main' else '/'+name)
        from sedrava_web_routes import route_parameters
        route_parameters(path)
        if path in [v['path'] for v in views.values()]:fail(Span(n,1),"Duplicate route")
        views[name]={'path':path,'guard':guard}
    if views['main']['path']!='/' or views['main']['guard']:fail(Span(1,1),"Initial main route must be unguarded /")
    ix, (_, _, view_lineno) = view_lines[0]
    if ix == len(lines) - 1:
        fail(Span(view_lineno, 1), "Empty view main")
    if not any(d > 0 for d, _, _ in lines[ix + 1:]):
        fail(Span(view_lineno, 1), "Empty view main")
    raw = source.splitlines()
    head_no = lines[0][2] - 1
    raw[head_no] = re.sub(r"^(\s*)webapp\b", r"\1app", raw[head_no], count=1)
    domain = "\n".join(raw[:view_lineno - 1]) + '\nscreen main:\n    text "WebApp placeholder"\n'
    program = parse_app(domain)
    run(program)
    if program.has_navigation:
        fail(Span(view_lineno, 1), "WebApp B1 does not support multi-view navigation")
    declared = {key: value_type(value) for key, value in program.states.items()}
    for key, expr in program.derived.items():
        declared[key] = type_of(expr, {**(program.functions or {}),**declared})
    from sedrava_web_routes import route_parameters
    for name,spec in views.items():
        for key in route_parameters(spec['path']):
            if key not in program.states or declared[key] is not int:fail(Span(view_lineno,1),"Route parameters require mutable integer state")
        if spec['guard'] and declared.get(spec['guard']) is not bool:fail(Span(view_lineno,1),"View guard requires boolean state")
    services=validate_services(service_blocks,program,declared)
    if 'theme-state' in settings:
        key=settings['theme-state']
        if key not in program.states or declared[key] is not str or program.states[key] not in theme_palettes:raise ValueError('Theme state requires a mutable text state and matching named palettes')
        from sedrava_core import parse_expr
        allowed=parse_expr(' or '.join(key+' == '+json.dumps(name) for name in theme_palettes),declared)
        program=replace(program,rules=(*program.rules,allowed))
        style_doc=replace(style_doc,theme=theme_palettes[program.states[key]])
        run(program)
    elif theme_palettes:raise ValueError('Named themes require theme-state')
    body_lines=[]
    for position,(start,(_,header,number)) in enumerate(view_lines):
        end=view_lines[position+1][0] if position+1<len(view_lines) else len(lines)
        name=re.match(r'view (\w+)',header)[1]
        content=lines[start+1:end]
        if not content:fail(Span(number,1),"Empty view")
        body_lines.extend(content)
    # Parse each view's tree separately through the same typed widget parser.
    body_lines=lines[ix+1:(view_lines[1][0] if len(view_lines)>1 else len(lines))]
    if not body_lines or body_lines[0][0] != 4:
        fail(Span(view_lineno, 1), "View content requires four-space indentation")
    lex = [(depth, tokens(line, number, depth), number)
           for depth, line, number in body_lines]
    widget_count = 0

    def body(pos, indent, nesting=0, row_fields=None):
        nonlocal widget_count
        if nesting > MAX_BLOCK_DEPTH:
            fail(Span(lex[pos][2], 1), "WebApp UI nesting limit exceeded")
        children = []
        while pos < len(lex) and lex[pos][0] >= indent:
            depth, items, number = lex[pos]
            if depth != indent:
                fail(Span(number, depth + 1), "Expected four-space UI indentation")
            kind = items[0].value
            if kind in UI_LAYOUT:
                definition = COMPONENTS[kind]
            elif kind in UI_DYNAMIC:
                definition = UI_DYNAMIC[kind]
            else:
                fail(items[0].span, "Unsupported WebApp component " + str(kind))
            is_block = items[-1].value == ":" and not items[-1].quoted
            if is_block != definition.children:
                fail(items[0].span, "Invalid component block structure")
            args = items[1:-1] if is_block else items[1:]
            given = {}
            if kind in ("value", "input", "checkbox", "when", "list", "table", "each", "field", "row-when", "select", "remote"):
                if not args or args[0].quoted or type(args[0].value) is not str:
                    fail(items[0].span, "State identifier required")
                name = args[0].value
                try:
                    identifier(name)
                except ValueError as exc:
                    fail(args[0].span, str(exc))
                given[{"list":"collection","table":"collection","each":"collection","field":"field","row-when":"field","remote":"service"}.get(kind,"state")] = Property(name, args[0].span)
                args = args[1:]
            elif args and args[0].quoted and definition.positional:
                given[definition.positional] = Property(args[0].value, args[0].span)
                args = args[1:]
            params = dict(COMMON)
            params.update(definition.parameters)
            params["variant"] = Parameter(choice(*definition.variants))
            extra = properties(args, params)
            if set(extra) & set(given):
                fail(items[0].span, "Duplicate component parameter")
            given.update(extra)
            if 'style' in given:
                from sedrava_site import parameter_for
                name=given['style'].value
                if name not in style_doc.styles:fail(items[0].span,'Unknown parameter style reference '+name)
                for key,prop in style_doc.styles[name].properties.items():
                    spec=parameter_for(key,params)
                    if spec is None:fail(items[0].span,'Style parameter not supported by component')
                    try:spec.validate(prop.value)
                    except ValueError as exc:fail(items[0].span,str(exc))
            for field in definition.required:
                if field not in given:
                    fail(items[0].span, "Missing required parameter " + field)
                try:
                    params[field].validate(given[field].value)
                except ValueError as exc:
                    fail(given[field].span, str(exc))
            if kind in ("heading", "button", "code") and not given["text"].value.strip():
                fail(items[0].span, "Accessible text must not be empty")
            if kind in ("value", "input", "checkbox", "when", "select"):
                key = given["state"].value
                if key not in declared:
                    fail(given["state"].span, "Unknown state " + key)
                actual = declared[key]
                if kind in ("input", "checkbox", "select") and key not in program.states:
                    fail(given["state"].span, "Input cannot edit derived state")
                if kind=="input" and "kind" in given and actual is not str:fail(items[0].span,"Input kind requires text state")
                if kind == "input" and actual not in (int, str):
                    fail(given["state"].span, "Input requires integer or text state")
                if kind in ("checkbox", "when") and actual is not bool:
                    fail(given["state"].span, kind + " requires boolean state")
                if kind == "value" and actual not in (int, bool, str):
                    fail(given["state"].span, "Value requires scalar or derived scalar state")
                if kind in ("input", "checkbox", "select") and not given["label"].value.strip():
                    fail(given["label"].span, "Accessible label must not be empty")
            if kind in ('field','row-when','pick'):
                if row_fields is None:fail(items[0].span,'Row field/pick requires an each template')
                if kind!='pick' and given['field'].value not in row_fields:fail(items[0].span,'Unknown row field')
                if kind=='row-when' and row_fields[given['field'].value] is not bool:fail(items[0].span,'Row condition requires bool field')
            if row_fields is not None:
                if kind in ('each','input','checkbox','select','form','submit','dialog','open','close','remote','request','cancel','navigate','back') or 'id' in given:fail(items[0].span,'Unsupported nested row control or duplicate-prone id')
            if kind in ("list", "table", "each"):
                key = given["collection"].value
                collection_type = declared.get(key)
                if not isinstance(collection_type, ListType):
                    fail(given["collection"].span, "List requires a declared collection")
                selected = given["select"].value
                if selected not in program.states or type(program.states[selected]) is not int:
                    fail(given["select"].span, "List select requires a mutable integer state")
                fields = dict(collection_type.record.fields)
                if "title" in given and fields.get(given["title"].value) is not str:
                    fail(given["title"].span, "List title requires a text record field")
                if "status" in given and fields.get(given["status"].value) is not bool:
                    fail(given["status"].span, "List status requires a boolean record field")
                if 'fields' in given and (not given['fields'].value.split() or any(f not in fields for f in given['fields'].value.split()) or len(set(given['fields'].value.split()))!=len(given['fields'].value.split())):fail(items[0].span,'Table fields must be distinct record fields')
                if 'search' in given and declared.get(given['search'].value) is not str:fail(items[0].span,'List search requires text state')
                if 'sort' in given and given['sort'].value not in fields:fail(items[0].span,'Unknown sort field')
                if 'where' in given:
                    if given['where'].value not in fields or 'equals' not in given or declared.get(given['equals'].value) is not fields[given['where'].value]:fail(items[0].span,'Filter requires matching scalar field and state')
                elif 'equals' in given or 'active' in given:fail(items[0].span,'Filter options require where')
                if 'active' in given and declared.get(given['active'].value) is not bool:fail(items[0].span,'Filter active requires bool state')
            if kind in ('request','cancel','remote'):
                service=services.get(given['service'].value)
                if service is None:fail(items[0].span,'Unknown HTTP service')
                if 'search' in given and declared.get(given['search'].value) is not str:fail(items[0].span,'Remote search requires text state')
                if 'title' in given and not any(f.name==given['title'].value and f.kind=='text' for f in service.schema.fields):fail(items[0].span,'Remote title requires schema text field')
            if kind == "navigate" and given["to"].value not in views:
                fail(items[0].span,"Unknown target view")
            if kind == "navigate" and "action" in given and given["action"].value not in program.actions:
                fail(items[0].span,"Unknown navigation action")
            if kind in ("button", "form") and given["action"].value not in program.actions:
                fail(given["action"].span, "Unknown action " + given["action"].value)
            pos += 1
            nested = ()
            if is_block:
                if pos >= len(lex) or lex[pos][0] <= indent:
                    fail(items[0].span, "Empty component block")
                nested, pos = body(pos, indent + 4, nesting + 1, ({"id":int,**fields} if kind=="each" else row_fields))
                if not nested:
                    fail(items[0].span, "Empty component block")
            if kind=='select':
                options=[n for n in nested if n.kind=='option']
                if len(options)!=len(nested) or not options:fail(items[0].span,"Select requires option children")
                if any(type(n.properties['value'].value) is not declared[given['state'].value] for n in options):fail(items[0].span,"Option type must match select state")
                values=[n.properties['value'].value for n in options]
                if len(values)!=len(set(values)):fail(items[0].span,"Duplicate option")
            if kind=='form' and any(n.kind=='form' for n in walk(nested)):fail(items[0].span,"Forms cannot nest")
            widget_count += 1
            if widget_count > 512:
                fail(items[0].span, "WebApp UI component limit (512) exceeded")
            children.append(Component(kind, given, tuple(nested), items[0].span))
        return tuple(children), pos

    all_widgets=[]
    for position,(start,(_,header,number)) in enumerate(view_lines):
        end=view_lines[position+1][0] if position+1<len(view_lines) else len(lines)
        content=lines[start+1:end]
        lex=[(depth,tokens(line,n,depth),n) for depth,line,n in content]
        if not lex or lex[0][0]!=4:fail(Span(number,1),"View content requires four-space indentation")
        nodes, consumed=body(0,4)
        if consumed!=len(lex):fail(Span(number,1),"Unexpected text after view")
        previous_level=0;h1=0
        for node in walk(nodes):
            if node.kind=='heading':
                level=node.properties['level'].value if 'level' in node.properties else (1 if previous_level==0 else 2)
                if level>previous_level+1:fail(node.span,"Heading levels must not skip a level")
                node.properties.setdefault('level',Property(level,node.span));previous_level=level;h1+=level==1
        if h1!=1:fail(Span(number,1),"WebApp requires exactly one h1 per view")
        name=re.match(r'view (\w+)',header)[1]
        views[name]['widgets']=nodes
        all_widgets.extend(nodes)
    ids={};dialog_ids=set()
    for node in walk(all_widgets):
        if 'id' in node.properties:
            key=node.properties['id'].value
            if key in ids or key in ('content','sedrava-error'):fail(node.span,'Duplicate or reserved UI id')
            ids[key]=node
            if node.kind=='dialog':dialog_ids.add(key)
    for node in walk(all_widgets):
        if node.kind in ('open','close') and node.properties['to'].value not in dialog_ids:fail(node.span,'Unknown dialog')
    return WebApp(program.name, program, tuple(all_widgets), views=views, services=services, theme=style_doc.theme, styles=style_doc.styles, settings=settings, themes=theme_palettes)


APP_CSS = r"""
.s-webapp{max-width:100%;padding:16px;min-height:100vh}
.s-webapp .s-value{display:block;font-variant-numeric:tabular-nums}
.s-webapp output{font-weight:650;white-space:pre-wrap}
.s-webapp .s-field{display:grid;gap:8px;max-width:100%;width:min(100%,40rem)}
.s-webapp label{font-weight:600}
.s-webapp input:not([type=checkbox]),.s-webapp textarea{font:inherit;display:block;width:100%;padding:12px;border-radius:10px;border:1px solid var(--border);background:var(--surface);color:var(--foreground)}
.s-webapp textarea{min-height:96px;resize:vertical}
.s-webapp input[type=checkbox]{width:20px;height:20px;accent-color:var(--accent)}
.s-webapp .s-checkbox label{display:flex;align-items:center;gap:12px}
.s-webapp button.s-button{cursor:pointer;font:inherit}
.s-webapp button:disabled{opacity:.5;cursor:not-allowed}
.s-webapp input:focus-visible,.s-webapp textarea:focus-visible,.s-webapp button:focus-visible{outline:3px solid var(--gold);outline-offset:3px}
.s-webapp [aria-invalid=true]{border-color:var(--gold)!important}
.s-webapp [role=alert]{color:var(--gold);font-size:.9rem}
.s-webapp [hidden]{display:none!important}
.s-webapp .s-list{list-style:none;display:grid;gap:12px;padding:0;margin:0;min-width:0}
.s-webapp .s-list li{min-width:0}
.s-webapp .s-list-choice{font:inherit;text-align:left;color:var(--foreground);background:var(--surface);border:1px solid var(--border);border-radius:14px;padding:14px 16px;min-height:48px;width:100%;display:grid;gap:4px;cursor:pointer}
.s-webapp .s-list-choice[aria-pressed=true]{outline:2px solid var(--accent);outline-offset:1px}
.s-webapp .s-list-title{font-weight:650;overflow-wrap:anywhere;white-space:pre-wrap}
.s-webapp .s-list-status{color:var(--muted);font-size:.85rem}
#sedrava-error{margin:16px auto;max-width:80rem;padding:12px}
"""


def generate_webapp(document, source_dir=".", _inputs=None):
    if not isinstance(document, WebApp):
        document = parse_webapp(document)
    program = document.program
    # Extract the exact validated 0.10 core runtime. No new action interpreter.
    domain_js = generate_legacy_web("", _program=program, _domain_only=True)
    from site_codegen import Assets
    assets=Assets(source_dir)
    selectors = []
    counter = 0

    def render(node):
        nonlocal counter
        counter += 1
        ident = "a" + str(counter)
        definition = UI_DYNAMIC.get(node.kind) or COMPONENTS[node.kind]
        props = dict(definition.defaults)
        if 'style' in node.properties:
            props.update({k:p.value for k,p in document.styles[node.properties['style'].value].properties.items()})
        props.update({k: p.value for k, p in node.properties.items()})
        base = {k: v for k, v in props.items()
                if not any(k.startswith(prefix + "-") for prefix in BREAKPOINTS)}
        media = {prefix: {k[len(prefix) + 1:]: v for k, v in props.items()
                          if k.startswith(prefix + "-")}
                 for prefix in BREAKPOINTS}
        if node.kind == "grid":
            columns = base.pop("columns", 3)
            base["columns"] = 1
            media["md"] = {"columns": min(2, columns), **media["md"]}
            media["lg"] = {"columns": columns, **media["lg"]}
        base_css = declarations(node.kind, base)
        if base_css:
            selectors.append(".s-node." + ident + "{" + base_css + "}")
        for prefix, width in BREAKPOINTS.items():
            responsive = declarations(node.kind, media[prefix])
            if responsive:
                selectors.append("@media(min-width:" + str(width) +
                                 "px){.s-node." + ident + "{" + responsive + "}}")
        kind = node.kind
        tag = definition.tag(props) if callable(definition.tag) else definition.tag
        if kind == "value":
            tag = "div"
        elif kind in ("input", "checkbox"):
            tag = "div"
        attrs = {"class": "s-node s-" + kind + " " + ident +
                 " v-" + props.get("variant", "default") + (" s-button" if kind in ("navigate","back","open","close","submit","request","cancel","pick") else "") + " " + props.get("class", "")}
        if "id" in props:
            attrs["id"] = props["id"]
        if "label" in props and kind not in ("input", "checkbox", "value", "list", "table", "each", "remote", "select"):
            attrs["aria-label"] = props["label"]
        attrs.update(definition.fixed_attributes)
        for prop,attribute in definition.attributes.items():
            if prop in props:attrs[attribute]=props[prop]
        if kind=='image':attrs['src']=assets.image(node,props['src'])
        if props.get('target')=='blank':attrs.update(target='_blank',rel='noopener noreferrer')
        def attr(k, v):
            return " " + k + '="' + html.escape(str(v), quote=True) + '"'
        common = "<" + tag + "".join(attr(k, v) for k, v in attrs.items()) + ">"
        if definition.void:
            return common
        if kind in ('request','cancel'):
            return common[:-1]+attr('type','button')+attr('data-request' if kind=='request' else 'data-cancel-request',props['service'])+'>'+html.escape(props['text'])+'</button>'
        if kind=='remote':
            attrs=attr('data-remote',props['service'])+attr('aria-label',props.get('label',props['service']))
            attrs+=''.join(attr('data-remote-'+k,props[k]) for k in ('search','title') if k in props)
            return common[:-1]+attrs+'><p data-remote-status role="status" aria-live="polite">idle</p><div data-remote-results class="s-remote-grid"></div></section>'
        if kind=='select':
            field_id='choice-'+ident
            choices=''.join('<option'+attr('value',json.dumps(n.properties['value'].value,ensure_ascii=False))+'>'+html.escape(n.properties['text'].value)+'</option>' for n in node.children)
            return '<div class="s-field"><label'+attr('for',field_id)+'>'+html.escape(props['label'])+'</label><select'+attr('id',field_id)+attr('data-choice',props['state'])+attr('class',attrs['class'])+'>'+choices+'</select></div>'
        if kind=='dialog':
            return common[:-1]+attr('data-dialog',props['id'])+'>'+''.join(render(child) for child in node.children)+'</dialog>'
        if kind=='form':
            return common[:-1]+attr('data-submit',props['action'])+'>'+''.join(render(child) for child in node.children)+'</form>'
        if kind in ('open','close'):
            return common[:-1]+attr('type','button')+attr('data-'+kind+'-dialog',props['to'])+'>'+html.escape(props['text'])+'</button>'
        if kind=='submit':
            return common[:-1]+attr('type','submit')+'>'+html.escape(props['text'])+'</button>'
        if kind == "value":
            key = html.escape(props["state"], quote=True)
            label = html.escape(props.get("label", props["state"]))
            return common + "<span>" + label + ': </span><output data-state="' + key + '" aria-live="polite"></output></div>'
        if kind in ("navigate", "back"):
            attrs=attr('type','button')+(' data-back="true"' if kind=='back' else attr('data-navigate',props['to']))
            if 'action' in props:attrs+=attr('data-route-action',props['action'])
            return common[:-1]+attrs+'>'+html.escape(props['text'])+'</button>'
        if kind == "button":
            key = html.escape(props["action"], quote=True)
            return common[:-1] + attr("type", "button") + attr("data-action", key) + ">" + html.escape(props["text"]) + "</button>"
        if kind in ("input", "checkbox"):
            key = html.escape(props["state"], quote=True)
            label = html.escape(props["label"])
            field_id = "webapp-field-" + ident
            error_id = field_id + "-error"
            if kind == "checkbox":
                control = '<input type="checkbox"' + attr("data-check", key) + ' aria-invalid="false">'
                return common + "<label>" + control + label + "</label><small role=\"alert\" hidden></small></div>"
            actual = type(program.states[props["state"]])
            control = ('<textarea' + attr("id", field_id) + attr("data-input", key) +
                       attr("aria-describedby", error_id) +
                       ' aria-invalid="false"></textarea>') if actual is str else (
                       '<input type="text" inputmode="numeric"' + attr("id", field_id) +
                       attr("data-input", key) + attr("aria-describedby", error_id) +
                       ' aria-invalid="false">')
            if actual is str and props.get('kind','textarea')!='textarea':
                control='<input'+attr('type',props['kind'])+attr('id',field_id)+attr('data-input',key)+attr('aria-describedby',error_id)+' aria-invalid="false">'
            return (common + '<label for="' + field_id + '">' + label + "</label>" +
                    control + '<small id="' + error_id +
                    '" role="alert" hidden>Value rejected by declared type or rules</small></div>')
        if kind == "when":
            return common[:-1] + attr("data-when", props["state"]) + " hidden>" + (
                "".join(render(child) for child in node.children)) + "</section>"
        if kind=='field':
            return common[:-1]+attr('data-row-field',props['field'])+'></output>'
        if kind=='row-when':
            return common[:-1]+attr('data-row-when',props['field'])+'>'+''.join(render(c) for c in node.children)+'</section>'
        if kind=='pick':
            return common[:-1]+' type="button" data-pick="true">'+html.escape(props['text'])+'</button>'
        if kind in ("list", "table", "each"):
            field_attrs = (
                attr("data-list", props["collection"]) +
                attr("data-select", props["select"]) +
                (attr("data-title-field", props["title"]) if "title" in props else "") +
                (attr("data-status-field", props["status"]) if "status" in props else "") +
                attr("aria-label", props.get("label", props["collection"])) +
                ''.join(attr('data-query-'+key,props[key]) for key in ('search','sort','where','equals','active','empty') if key in props)
            )
            if kind=='each':
                field_attrs=field_attrs.replace('data-list=', 'data-each=')
                return common[:-1]+field_attrs+'><template>'+''.join(render(c) for c in node.children)+'</template><div data-each-items role="list"></div></section>'
            if kind=='table':field_attrs+=attr('data-table',props.get('fields',' '.join(k for k,_ in document.program.states[props['collection']].kind.record.fields)))
            return common[:-1] + field_attrs + ('></div>' if kind=='table' else '></ul>')
        if kind == "code":
            return common + "<code>" + html.escape(props["text"]) + "</code></pre>"
        return common + html.escape(props.get("text", "")) + (
            "".join(render(child) for child in node.children)) + "</" + tag + ">"

    markup = ''.join('<section data-view="'+name+'"'+(' hidden' if name!='main' else '')+'>'+''.join(render(n) for n in spec['widgets'])+'</section>' for name,spec in document.views.items()) if len(document.views)>1 else ''.join(render(n) for n in document.widgets)
    theme_rules=''
    for name,palette in document.themes.items():
        from sedrava_web_assets import theme_styles
        scheme=theme_styles(palette,'color-scheme:dark')
        theme_rules+=':root[data-theme="'+name+'"]{'+''.join('--'+k+':'+v+';' for k,v in palette.items())+scheme+'}\n'
    theme_css = theme_rules+":root{" + "".join("--" + k + ":" + v + ";" for k, v in document.theme.items()) + "}\n"
    from sedrava_web_assets import theme_styles
    css = theme_css + theme_styles(document.theme,CSS) + "\n" + APP_CSS + "\n" + "\n".join(selectors) + "\n"
    names = {key: "values[" + json_script(key) + "]" for key in program.states}
    derived = []
    for key, expr in program.derived.items():
        derived.append("  values[" + json_script(key) + "] = " + js_expr(expr, names) + ";")
        names[key] = "values[" + json_script(key) + "]"
    ui_js = "\n".join([
        'const errorNode = document.getElementById("sedrava-error");',
        'function showError(message) { errorNode.textContent=message; errorNode.hidden=!message; }',
        'function valuesOfState() { const values = { __proto__: null, ...state };',
        *derived,
        '  return values; }',
        'function render() {',
        '  const values=valuesOfState();',
        '  document.querySelectorAll("[data-state]").forEach(el=>{el.textContent=String(values[el.dataset.state]);});',
        '  document.querySelectorAll("[data-when]").forEach(el=>{el.hidden=!values[el.dataset.when];});',
        '  document.querySelectorAll("[data-input]").forEach(el=>{if(document.activeElement!==el)el.value=String(state[el.dataset.input]);});',
        '  document.querySelectorAll("[data-check]").forEach(el=>{el.checked=state[el.dataset.check];});',
        '  document.querySelectorAll("[data-choice]").forEach(el=>el.value=JSON.stringify(state[el.dataset.choice]));',
        '  renderLists();renderEach();',
        '  if(typeof activeView!=="undefined"){if(!canView(activeView))goView("main",true);showView();}',
        '  syncButtons();',
        '  if(typeof remoteReady!=="undefined" && remoteReady)renderRemote();',
        '}',
        'function syncButtons(){',
        '  const invalid=!!document.querySelector("[data-input][aria-invalid=true]");',
        '  document.querySelectorAll("button[data-action], [data-list] button, [data-each] button, button[type=submit], [data-navigate], [data-request]").forEach(el=>{el.disabled=invalid;});',
        '}',
        'function persistAccepted(){',
        "  try{saveSnapshot();return true;}catch(_){showError('Could not save state; existing stored data retained');return false;}",
        '}',
        'function commit(next) {',
        "  if(next===state){showError('Change rejected by declared rules');return false;}",
        "  state=next;showError('');persistAccepted();render();return true;",
        '}',
        'document.querySelectorAll("button[data-action]").forEach(el=>{',
        '  el.addEventListener("click",()=>{',
        "    if(el.disabled)return;",
        "    const action=actions[el.dataset.action];",
        "    try{commit(action(state));}catch(_){showError('Action rejected: invalid value or overflow');}",
        '  });',
        '});',
        'function updateField(el) {',
        '  const key=el.dataset.input, isText=typeof initialState[key]==="string";',
        '  const raw=isText?el.value:el.value.trim();',
        '  const candidate=isText?raw:(/^-?[0-9]+$/.test(raw)?Number(raw):null);',
        '  const valid=(isText?validText(candidate):(raw!=="" && Number.isInteger(candidate) && candidate>=-2147483648 && candidate<=2147483647)) && el.checkValidity();',
        '  const next=valid?editState(state,key,candidate):state;',
        '  const rejected=next===state;',
        '  el.setAttribute("aria-invalid",String(rejected));',
        '  const error=document.getElementById(el.getAttribute("aria-describedby"));',
        '  if(error)error.hidden=!rejected;',
        "  if(!rejected){state=next;showError('');persistAccepted();render();}",
        '  syncButtons();',
        '}',
        'document.querySelectorAll("[data-input]").forEach(el=>{',
        '  el.value=String(state[el.dataset.input]);',
        '  el.addEventListener("input",()=>updateField(el));',
        '  el.addEventListener("blur",()=>{',
        '    if(el.getAttribute("aria-invalid")==="true"){el.value=String(state[el.dataset.input]);el.setAttribute("aria-invalid","false");',
        '      const error=document.getElementById(el.getAttribute("aria-describedby"));if(error)error.hidden=true;syncButtons();}',
        '  });',
        '});',
        'function renderLists() {',
        '  document.querySelectorAll("[data-list]").forEach(el => {',
        '    const collection=valuesOfState()[el.dataset.list];',
        '    const selected=state[el.dataset.select];',
        '    const titleField=el.dataset.titleField, statusField=el.dataset.statusField;',
        '    const fragment=document.createDocumentFragment();',
        '    const values=valuesOfState();',
        '    const rows=queryRows(collection.items,{title:titleField,search:el.dataset.querySearch?values[el.dataset.querySearch]:"",sort:el.dataset.querySort,where:el.dataset.queryWhere,equals:el.dataset.queryEquals?values[el.dataset.queryEquals]:false,active:el.dataset.queryActive?values[el.dataset.queryActive]:true});',
        '    if(el.dataset.table){renderTable(rows,el,selected,fragment);el.replaceChildren(fragment);return;}',
        '    if(!rows.length && el.dataset.queryEmpty){const empty=document.createElement("li");const note=document.createElement("span");note.setAttribute("role","status");note.textContent=el.dataset.queryEmpty;empty.append(note);fragment.append(empty);}',
        '    for(const row of rows){',
        '      const item=document.createElement("li");item.dataset.id=String(row.id);',
        '      const button=document.createElement("button");button.type="button";',
        '      button.className="s-list-choice";button.dataset.itemId=String(row.id);',
        '      button.setAttribute("aria-pressed", String(selected===row.id));',
        '      const label=titleField?String(row[titleField]):Object.entries(row).filter(([key])=>key!=="id").map(([key,val])=>key+": "+String(val)).join(" · ");',
        '      const title=document.createElement("span");title.className="s-list-title";title.textContent=label;button.append(title);',
        '      button.setAttribute("aria-label", "Select "+label);',
        '      if(statusField){const note=document.createElement("span");note.className="s-list-status";note.textContent=row[statusField]?"Completed":"In progress";button.setAttribute("aria-describedby", "list-status-"+el.dataset.list+"-"+row.id);note.id="list-status-"+el.dataset.list+"-"+row.id;button.append(note);}',
        '      button.addEventListener("click",()=>{',
        '        if(button.disabled)return;',
        '        const next=editState(state,el.dataset.select,row.id);',
        '        if(commit(next)){',
        '          const updated=[...document.querySelectorAll("[data-list]")].find(list=>list.dataset.list===el.dataset.list && list.dataset.select===el.dataset.select);',
        '          const focus=updated&&[...updated.querySelectorAll("button[data-item-id]")].find(b=>b.dataset.itemId===String(row.id));',
        '          if(focus)focus.focus({preventScroll:true});',
        '        }',
        '      });',
        '      item.append(button);fragment.append(item);',
        '    }',
        '    el.replaceChildren(fragment);',
        '  });',
        '}',
        'document.querySelectorAll("[data-check]").forEach(el=>{',
        '  el.addEventListener("change",()=>{const next=editState(state,el.dataset.check,el.checked);commit(next);render();});',
        '});',
        'render();',
        "if(restoreError)showError('Saved data rejected; original retained');",
        '',
    ])
    if len(document.views)>1:
        from sedrava_web_routes import ROUTER_JS
        config={name:{k:v for k,v in spec.items() if k!='widgets'} for name,spec in document.views.items()}
        # activeView must exist before render() initial invocation (no TDZ).
        ui_js='let activeView="main";let routeReady=false;\nconst viewConfig='+json_script(config)+';\n'+ui_js+ROUTER_JS.replace("let activeView='main';",'')
    from sedrava_web_queries import QUERY_JS
    ui_js=QUERY_JS+ui_js
    from sedrava_web_ui import EXTRA_JS, EXTRA_CSS
    ui_js+=EXTRA_JS
    if 'theme-state' in document.settings:
        key=document.settings['theme-state']
        ui_js=ui_js.replace('  const values=valuesOfState();','  const values=valuesOfState();document.documentElement.dataset.theme=state['+json_script(key)+'];',1)
    css+=EXTRA_CSS
    if document.services:
        from sedrava_web_services import generate_services
        from sedrava_records_codegen import STRICT_JSON
        ui_js='let remoteReady=false;\n'+('' if program.records or program.has_navigation else STRICT_JSON)+ui_js+generate_services(document.services, program)
    title = html.escape(document.name)
    index = ('<!doctype html>\n<html lang="en"><head><meta charset="utf-8">'
             '<meta name="viewport" content="width=device-width,initial-scale=1">'
             '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; '
             'script-src \'self\'; style-src \'self\'; base-uri \'none\'; '
             'img-src \'self\' https:; connect-src \'none\'; form-action \'none\'">'
             '<title>' + title + '</title><link rel="stylesheet" href="app.css">'
             '<script src="app.js" defer></script></head><body>'
             '<main id="content" class="s-webapp">' + markup + '</main>'
             '<p id="sedrava-error" role="alert" hidden></p></body></html>\n')
    if document.services:
        origins=sorted({item.origin for item in document.services.values() if item.origin})
        index=index.replace("connect-src 'none'", "connect-src 'self'"+(' '+ ' '.join(origins) if origins else ''))
    files={"index.html": index.encode("utf-8"),
            "app.css": css.encode("utf-8"),
            "app.js": (domain_js + ui_js).encode("utf-8")}
    files.update(assets.files)
    if _inputs is not None:_inputs.update(assets.paths)
    return files


MARKER = "sedrava-webapp.json"


def build_webapp(source, output, source_path):
    from sedrava_modules import expand
    expanded, modules = (None, set()) if isinstance(source, WebApp) else expand(source, source_path)
    document = source if isinstance(source, WebApp) else parse_webapp(expanded)
    source_path = Path(source_path).resolve()
    output = Path(output)
    resolved = output.resolve()
    if source_path.is_relative_to(resolved) or any(p.is_relative_to(resolved) for p in modules):
        raise ValueError("WebApp output must not contain its source")
    if output.is_symlink():
        raise ValueError("WebApp output cannot be a symlink")
    files = generate_webapp(document,source_path.parent,modules)
    from sedrava_web_assets import attach
    modules.update(attach(files,document.settings,source_path.parent))
    if any(path.is_relative_to(resolved) for path in modules):raise ValueError('Output must not contain imported modules/assets')
    if output.exists():
        saved = tree_bytes(output)
        if saved:
            if MARKER not in saved or len(saved[MARKER]) > 1024 * 1024:
                raise ValueError("Refusing to replace an unmanaged WebApp directory")
            try:
                manifest = json.loads(saved.pop(MARKER))
            except (ValueError, UnicodeError) as exc:
                raise ValueError("Invalid WebApp manifest") from exc
            if (type(manifest) is not dict or manifest.get("schema") != 1 or
                manifest.get("mode") != "webapp" or
                manifest.get("files") != {name: digest(data) for name, data in sorted(saved.items())}):
                raise ValueError("WebApp output was modified; refusing to replace it")
    files[MARKER] = (json.dumps({
        "schema": 1, "mode": "webapp", "compiler_version": VERSION,
        "source_sha256": digest(source.encode("utf-8") if isinstance(source, str)
                                else source_path.read_bytes()),
        "files": {name: digest(data) for name, data in sorted(files.items())},
    }, sort_keys=True, indent=2) + "\n").encode("utf-8")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".sedrava-webapp-", dir=output.parent) as folder:
        staging = Path(folder) / "next"
        staging.mkdir()
        backup = Path(folder) / "previous"
        for name, data in sorted(files.items()):
            target=staging / name
            target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(data)
        previous = output.exists()
        if previous:
            os.replace(output, backup)
        try:
            os.replace(staging, output)
        except OSError:
            if previous:
                os.replace(backup, output)
            raise
    return output / "index.html"
