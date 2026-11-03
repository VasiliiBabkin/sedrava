"""Experimental Sedrava webapp v0.11: typed app state and responsive Web UI.

The core's parser, action compiler and persistence semantics are reused; this
module does not interpret Sedrava actions. Supports bounded collection
rendering and selection alongside scalar/derived values. No HTTP, multi-view
navigation, or inline arbitrary code.
"""
from dataclasses import dataclass
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


UI_LAYOUT = frozenset(("container", "row", "column", "grid", "card",
                       "callout", "heading", "paragraph", "code",
                       "spacer", "divider"))
UI_DYNAMIC = {
    "value": Definition("output", required=("state",),
                        parameters={"state": Parameter(identifier)}),
    "input": Definition("input", required=("state", "label"),
                        parameters={"state": Parameter(identifier)}),
    "checkbox": Definition("input", required=("state", "label"),
                           parameters={"state": Parameter(identifier)}),
    "when": Definition("section", children=True, required=("state",),
                       parameters={"state": Parameter(identifier)}),
    "list": Definition("ul", required=("collection", "select"),
                       parameters={"collection": Parameter(identifier),
                                   "select": Parameter(identifier),
                                   "title": Parameter(identifier),
                                   "status": Parameter(identifier)}),
    "button": Definition("button", positional="text",
                         required=("text", "action"),
                         parameters={"text": Parameter(text),
                                     "action": Parameter(identifier)},
                         defaults={"variant": "primary"},
                         variants=("primary", "secondary", "ghost")),
}


def parse_webapp(source):
    from sedrava_modules import components
    source = components(source)
    lines = source_lines(source)
    if not lines or not re.fullmatch(r'webapp\s+".+"', lines[0][1]):
        raise ValueError("Line 1: column 1: Expected webapp \"Title\"")
    view_lines = [(i, item) for i, item in enumerate(lines)
                  if item[0] == 0 and item[1].startswith("view ")]
    if len(view_lines) != 1 or view_lines[0][1][1] != "view main:":
        fail(Span(lines[0][2], 1), "Exactly one 'view main:' is required")
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
        declared[key] = type_of(expr, declared)
    body_lines = lines[ix + 1:]
    if not body_lines or body_lines[0][0] != 4:
        fail(Span(view_lineno, 1), "View content requires four-space indentation")
    lex = [(depth, tokens(line, number, depth), number)
           for depth, line, number in body_lines]
    widget_count = 0

    def body(pos, indent, nesting=0):
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
            if kind in ("value", "input", "checkbox", "when", "list"):
                if not args or args[0].quoted or type(args[0].value) is not str:
                    fail(items[0].span, "State identifier required")
                name = args[0].value
                try:
                    identifier(name)
                except ValueError as exc:
                    fail(args[0].span, str(exc))
                given["collection" if kind == "list" else "state"] = Property(name, args[0].span)
                args = args[1:]
            elif args and args[0].quoted and definition.positional:
                given[definition.positional] = Property(args[0].value, args[0].span)
                args = args[1:]
            params = {k: v for k, v in COMMON.items() if k != "style"}
            params.update(definition.parameters)
            params["variant"] = Parameter(choice(*definition.variants))
            extra = properties(args, params)
            if set(extra) & set(given):
                fail(items[0].span, "Duplicate component parameter")
            given.update(extra)
            for field in definition.required:
                if field not in given:
                    fail(items[0].span, "Missing required parameter " + field)
                try:
                    params[field].validate(given[field].value)
                except ValueError as exc:
                    fail(given[field].span, str(exc))
            if kind in ("heading", "button", "code") and not given["text"].value.strip():
                fail(items[0].span, "Accessible text must not be empty")
            if kind in ("value", "input", "checkbox", "when"):
                key = given["state"].value
                if key not in declared:
                    fail(given["state"].span, "Unknown state " + key)
                actual = declared[key]
                if kind in ("input", "checkbox") and key not in program.states:
                    fail(given["state"].span, "Input cannot edit derived state")
                if kind == "input" and actual not in (int, str):
                    fail(given["state"].span, "Input requires integer or text state")
                if kind in ("checkbox", "when") and actual is not bool:
                    fail(given["state"].span, kind + " requires boolean state")
                if kind == "value" and actual not in (int, bool, str):
                    fail(given["state"].span, "Value requires scalar or derived scalar state")
                if kind in ("input", "checkbox") and not given["label"].value.strip():
                    fail(given["label"].span, "Accessible label must not be empty")
            if kind == "list":
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
            if kind == "button" and given["action"].value not in program.actions:
                fail(given["action"].span, "Unknown action " + given["action"].value)
            pos += 1
            nested = ()
            if is_block:
                if pos >= len(lex) or lex[pos][0] <= indent:
                    fail(items[0].span, "Empty component block")
                nested, pos = body(pos, indent + 4, nesting + 1)
                if not nested:
                    fail(items[0].span, "Empty component block")
            widget_count += 1
            if widget_count > 512:
                fail(items[0].span, "WebApp UI component limit (512) exceeded")
            children.append(Component(kind, given, tuple(nested), items[0].span))
        return tuple(children), pos

    widgets, end = body(0, 4)
    if end != len(lex):
        fail(Span(view_lineno, 1), "Unexpected text after view")
    previous_level = 0
    h1 = 0
    for node in walk(widgets):
        if node.kind == "heading":
            level = node.properties["level"].value if "level" in node.properties else (
                1 if previous_level == 0 else 2)
            if level > previous_level + 1:
                fail(node.span, "Heading levels must not skip a level")
            node.properties.setdefault("level", Property(level, node.span))
            previous_level = level
            h1 += level == 1
    if h1 != 1:
        fail(Span(view_lineno, 1), "WebApp requires exactly one h1")
    return WebApp(program.name, program, widgets)


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


def generate_webapp(document):
    if not isinstance(document, WebApp):
        document = parse_webapp(document)
    program = document.program
    # Extract the exact validated 0.10 core runtime. No new action interpreter.
    domain_js = generate_legacy_web("", _program=program, _domain_only=True)
    selectors = []
    counter = 0

    def render(node):
        nonlocal counter
        counter += 1
        ident = "a" + str(counter)
        definition = UI_DYNAMIC.get(node.kind) or COMPONENTS[node.kind]
        props = dict(definition.defaults)
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
                 " v-" + props.get("variant", "default")}
        if "id" in props:
            attrs["id"] = props["id"]
        if "label" in props and kind not in ("input", "checkbox", "value"):
            attrs["aria-label"] = props["label"]
        def attr(k, v):
            return " " + k + '="' + html.escape(str(v), quote=True) + '"'
        common = "<" + tag + "".join(attr(k, v) for k, v in attrs.items()) + ">"
        if definition.void:
            return common
        if kind == "value":
            key = html.escape(props["state"], quote=True)
            label = html.escape(props.get("label", props["state"]))
            return common + "<span>" + label + ': </span><output data-state="' + key + '" aria-live="polite"></output></div>'
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
            return (common + '<label for="' + field_id + '">' + label + "</label>" +
                    control + '<small id="' + error_id +
                    '" role="alert" hidden>Value rejected by declared type or rules</small></div>')
        if kind == "when":
            return common[:-1] + attr("data-when", props["state"]) + " hidden>" + (
                "".join(render(child) for child in node.children)) + "</section>"
        if kind == "list":
            field_attrs = (
                attr("data-list", props["collection"]) +
                attr("data-select", props["select"]) +
                (attr("data-title-field", props["title"]) if "title" in props else "") +
                (attr("data-status-field", props["status"]) if "status" in props else "") +
                attr("aria-label", props.get("label", props["collection"]))
            )
            return common[:-1] + field_attrs + "></ul>"
        if kind == "code":
            return common + "<code>" + html.escape(props["text"]) + "</code></pre>"
        return common + html.escape(props.get("text", "")) + (
            "".join(render(child) for child in node.children)) + "</" + tag + ">"

    markup = "".join(render(n) for n in document.widgets)
    theme_css = ":root{" + "".join("--" + k + ":" + v + ";" for k, v in THEME.items()) + "}\n"
    css = theme_css + CSS + "\n" + APP_CSS + "\n" + "\n".join(selectors) + "\n"
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
        '  renderLists();',
        '  syncButtons();',
        '}',
        'function syncButtons(){',
        '  const invalid=!!document.querySelector("[data-input][aria-invalid=true]");',
        '  document.querySelectorAll("button[data-action], [data-list] button").forEach(el=>{el.disabled=invalid;});',
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
        '  const valid=isText?validText(candidate):(raw!=="" && Number.isInteger(candidate) && candidate>=-2147483648 && candidate<=2147483647);',
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
        '    const collection=state[el.dataset.list];',
        '    const selected=state[el.dataset.select];',
        '    const titleField=el.dataset.titleField, statusField=el.dataset.statusField;',
        '    const fragment=document.createDocumentFragment();',
        '    for(const row of collection.items){',
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
    title = html.escape(document.name)
    index = ('<!doctype html>\n<html lang="en"><head><meta charset="utf-8">'
             '<meta name="viewport" content="width=device-width,initial-scale=1">'
             '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; '
             'script-src \'self\'; style-src \'self\'; base-uri \'none\'; '
             'img-src \'self\'; connect-src \'none\'; form-action \'none\'">'
             '<title>' + title + '</title><link rel="stylesheet" href="app.css">'
             '<script src="app.js" defer></script></head><body>'
             '<main id="content" class="s-webapp">' + markup + '</main>'
             '<p id="sedrava-error" role="alert" hidden></p></body></html>\n')
    return {"index.html": index.encode("utf-8"),
            "app.css": css.encode("utf-8"),
            "app.js": (domain_js + ui_js).encode("utf-8")}


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
    files = generate_webapp(document)
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
            (staging / name).write_bytes(data)
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
