"""Sedrava web backend: generate self-contained HTML + JS from the shared AST."""
import argparse
import ast
import html
import json
from pathlib import Path
from sedrava_records import plain,structured
from sedrava_sequences import ValueListType,JS_RUNTIME as VECTOR_RUNTIME
from sedrava_records_codegen import js_runtime
from sedrava_core import Assign, If, Require, Let, Repeat, ForEach, parse, run

def json_script(value, **kwargs):
    # HTML parses script end tags before JavaScript parses quoted strings.
    return json.dumps(value, **kwargs).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")

def js_expr(node, names):
    if isinstance(node,ast.List) and hasattr(node,'literal_kind'):return '['+','.join(js_expr(item,names) for item in node.elts)+']'
    if isinstance(node, ast.Subscript):
        base=js_expr(node.value,names)
        kind=node.subscript_kind
        if isinstance(node.slice,ast.Slice):
            start=js_expr(node.slice.lower,names)
            end=js_expr(node.slice.upper,names)
            if kind is str:
                return 'sdrTextSlice('+','.join((base,start,end))+')'
            return ('vectorOp' if isinstance(kind,ValueListType) else 'collectionOp')+'("list_slice",'+str(kind.capacity)+','+','.join((base,start,end))+')'
        index=js_expr(node.slice,names)
        if kind is str:
            return 'sdrTextAt('+','.join((base,index))+')'
        return ('vectorOp' if isinstance(kind,ValueListType) else 'collectionOp')+'("list_at",'+str(kind.capacity)+','+','.join((base,index))+')'
    if isinstance(node, ast.Attribute): return '(' + js_expr(node.value, names) + ')[' + json_script(node.attr) + ']'
    if isinstance(node, ast.Call):
        if hasattr(node,"result_operation"):
            from sedrava_results import js as result_emit
            return result_emit(node,[js_expr(arg,names) for arg in node.args])
        if hasattr(node,"collection_query"):
            from sedrava_queries import js_query
            return js_query(node,js_expr,names)
        if hasattr(node,"pure_builtin"):
            from sedrava_stdlib import js_call
            return js_call(node.pure_builtin,[js_expr(arg,names) for arg in node.args])
        if hasattr(node,'pure_function'):
            function=node.pure_function
            params={key:'_sdr_arg'+str(i) for i,(key,_) in enumerate(function.parameters)}
            return '(('+','.join(params.values())+')=>'+js_expr(function.body,params)+')('+','.join(js_expr(arg,names) for arg in node.args)+')'

        if hasattr(node, 'record_type'):
            fields = {k.arg: k.value for k in node.keywords}
            return '({' + ','.join('[' + json_script(k) + ']:' + js_expr(fields[k], names) for k, _ in node.record_type.fields) + '})'
        return ('vectorOp(' if isinstance(node.collection_type,ValueListType) else 'collectionOp(') + json_script(node.func.id) + ',' + str(node.collection_type.capacity) + ',' + ','.join(js_expr(a, names) for a in node.args) + ')'
    if isinstance(node,ast.IfExp):return "("+js_expr(node.test,names)+" ? "+js_expr(node.body,names)+" : "+js_expr(node.orelse,names)+")"
    if isinstance(node, ast.Constant):
        return json_script(node.value)
    if isinstance(node, ast.Name):
        return names[node.id]
    if isinstance(node, ast.UnaryOp):
        operator = "!" if isinstance(node.op, ast.Not) else "-"
        return (f"checkedInt(-({js_expr(node.operand, names)}))" if isinstance(node.op, ast.USub) else f"(!{js_expr(node.operand, names)})")
    if isinstance(node, ast.BinOp):
        op = {ast.Add: "+", ast.Sub: "-", ast.Mult: "*"}[type(node.op)]
        return f"checkedInt({js_expr(node.left, names)} {op} {js_expr(node.right, names)})"
    if isinstance(node, ast.BoolOp):
        op = " && " if isinstance(node.op, ast.And) else " || "
        return "(" + op.join(js_expr(v, names) for v in node.values) + ")"
    if isinstance(node, ast.Compare):
        op = {ast.Eq: "===", ast.NotEq: "!==", ast.Lt: "<", ast.LtE: "<=",
              ast.Gt: ">", ast.GtE: ">="}[type(node.ops[0])]
        return f"({js_expr(node.left, names)} {op} {js_expr(node.comparators[0], names)})"
    raise ValueError("Unsupported expression")

def statements(body, names, depth=4, derived=None):
    names=dict(names)
    result = []
    pad = " " * depth
    for stmt in body:
        from sedrava_cost import statement_work
        result.append(pad+"_sdr_spend("+str(statement_work(stmt,derived))+");")
        if isinstance(stmt, Let):
            local="_sdr_local_"+stmt.name
            result.append(pad+"const "+local+" = "+js_expr(stmt.expr,names)+";")
            names[stmt.name]=local
        elif isinstance(stmt, Require):
            result.append(pad + 'if (!(' + js_expr(stmt.condition, names) + ")) throw Error('Action requirement rejected');")
        elif isinstance(stmt, Assign):
            result.append(f"{pad}{names[stmt.name]} = {js_expr(stmt.expr, names)};")
            result.append(f"{pad}checkDerivedState(nextState);")
        elif isinstance(stmt,ForEach):
            source=js_expr(stmt.collection,names)
            snapshot='Array.from('+source+')' if stmt.kind is str else '('+source+').slice()' if isinstance(stmt.kind,ValueListType) else '('+source+').items.slice()'
            result.extend([pad+'{',pad+'  const _sdr_eachValues='+snapshot+';',pad+'  for(let _sdr_eachIndex=0;_sdr_eachIndex<_sdr_eachValues.length;_sdr_eachIndex++){'])
            item='_sdr_eachValues[_sdr_eachIndex]'
            if stmt.kind is not str and not isinstance(stmt.kind,ValueListType):item='(({id,...record})=>record)('+item+')'
            result.append(pad+'    const _sdr_eachValue='+item+';')
            scope={**names,stmt.name:'_sdr_eachValue'}
            if stmt.index:scope[stmt.index]='_sdr_eachIndex'
            result.extend(statements(stmt.body,scope,depth+4,derived));result.extend([pad+'  }',pad+'}'])
        elif isinstance(stmt, Repeat):
            local="_sdr_repeat_"+stmt.name
            if stmt.start==0 and stmt.step==1:
                result.append(f"{pad}for (let {local}=0; {local}<{stmt.count}; {local}++) {{")
            else:
                ordinal=local+"_ordinal"
                result.append(f"{pad}for (let {ordinal}=0; {ordinal}<{stmt.count}; {ordinal}++) {{")
                result.append(f"{pad}  const {local}=checkedInt({stmt.start}+{ordinal}*({stmt.step}));")
            result.extend(statements(stmt.body,{**names,stmt.name:local},depth+2,derived))
            result.append(f"{pad}}}")
        elif isinstance(stmt, If):
            result.append(f"{pad}if ({js_expr(stmt.condition, names)}) {{")
            result.extend(statements(stmt.yes, names, depth + 2,derived))
            if stmt.no:
                result.append(f"{pad}}} else {{")
                result.extend(statements(stmt.no, names, depth + 2,derived))
            result.append(f"{pad}}}")
        else:
            raise ValueError("Unsupported statement")
    return result

def generate(source, _program=None, _domain_only=False):
    program = _program or parse(source)
    if program.has_navigation and _program is None:
        from sedrava_navigation_web import generate_navigation
        return generate_navigation(source, program)
    run(program)
    if not program.widgets:
        raise ValueError("Missing screen main")
    from sedrava_stdlib import JS_RUNTIME
    from sedrava_results import JS_RUNTIME as RESULT_RUNTIME
    JS_RUNTIME+=RESULT_RUNTIME
    from sedrava_unicode import required as unicode_required,runtime as unicode_runtime
    if unicode_required(program):JS_RUNTIME+=unicode_runtime('js')
    from sedrava_queries import JS_RUNTIME as QUERY_RUNTIME
    initial = json_script({k: plain(v) for k, v in program.states.items()}, ensure_ascii=False)
    names = {key: "nextState[" + json_script(key) + "]" for key in program.states}
    for key, expr in (program.derived or {}).items():
        names[key] = js_expr(expr, names)
    rules = " && ".join(js_expr(rule, names) for rule in program.rules) or "true"
    from sedrava_cost import MAX_ACTION_WORK,base_work
    actions = []
    for name, body in program.actions.items():
        actions.extend([
            f"  [{json_script(name)}]: (state) => {{",
            "    const nextState = { ...state };",
            f"    let _sdr_workLeft={MAX_ACTION_WORK-base_work(program.derived,program.rules)};",
            "    const _sdr_spend=n=>{_sdr_workLeft-=n;if(_sdr_workLeft<0)throw Error('Action exceeds execution work limit');};",
            *statements(body, names,derived=program.derived),
            f"    return validateState(nextState) && ({rules}) ? nextState : state;",
            "  },",
        ])
    render_names = {key: "derivedState[" + json_script(key) + "]" for key in program.states}
    derived_lines = []
    for key, expr in (program.derived or {}).items():
        derived_lines.append("  derivedState[" + json_script(key) + "] = " + js_expr(expr, render_names) + ";")
        render_names[key] = "derivedState[" + json_script(key) + "]"
    widgets = []
    title_seen = False
    input_seen = set()
    for widget_index, widget in enumerate(program.widgets):
        if widget[0] == "list":
            widgets.append('<ul data-list="' + html.escape(widget[1], quote=True) + '" data-select="' + html.escape(widget[2], quote=True) + '"></ul>')
        elif widget[0] == "text":
            tag = 'p' if title_seen else 'h1'
            widgets.append(f'<{tag} class="intro-text">{html.escape(widget[1])}</{tag}>')
            title_seen = True
        elif widget[0] == "value":
            key = html.escape(widget[1], quote=True)
            widgets.append(f'<p>{key}: <output data-state="{key}"></output></p>')
        elif widget[0] == "input_text":
            key = html.escape(widget[1], quote=True)
            error_id = "error-" + key + ("-" + str(widget_index) if key in input_seen else "")
            input_seen.add(key)
            widgets.append(f'<label>{key}: <textarea data-input="{key}" aria-describedby="{error_id}" aria-invalid="false"></textarea></label><small id="{error_id}" role="alert" hidden>Text must contain at most 1024 Unicode scalar values and satisfy the declared rules</small>')
        elif widget[0] == "input_int":
            key = html.escape(widget[1], quote=True)
            error_id = "error-" + key + ("-" + str(widget_index) if key in input_seen else "")
            input_seen.add(key)
            widgets.append(f'<label>{key}: <input type="number" step="1" min="-2147483648" max="2147483647" data-input="{key}" aria-describedby="{error_id}"></label><small id="{error_id}" role="alert" hidden>Value does not satisfy the declared rules</small>')
        elif widget[0] == "show_text":
            key = html.escape(widget[1], quote=True)
            widgets.append(f'<p data-show="{key}" hidden>{html.escape(widget[2])}</p>')
        else:
            label, action = widget[1:]
            widgets.append(f'<button type="button" data-action="{html.escape(action, quote=True)}">{html.escape(label)}</button>')
    # No user-supplied text is inserted into executable JS without JSON encoding.
    parts = [
        "<!doctype html>",
        '<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>{html.escape(program.name)}</title>",
        '<style>*{box-sizing:border-box}body{font:1.125rem/1.6 system-ui;color:#203b35;background:#f4f3ee;max-width:42rem;margin:2rem auto;padding:0 1rem}button,input,textarea{font:inherit}button{padding:.7rem 1rem;margin:.25rem 0;border:1px solid #245d4e;border-radius:.75rem;cursor:pointer;color:white;background:#245d4e;min-height:48px;max-width:100%;white-space:normal;overflow-wrap:anywhere}button:hover{background:#194638}button:disabled{opacity:.55;cursor:not-allowed}button:focus-visible,input:focus-visible,textarea:focus-visible{outline:3px solid #a45115;outline-offset:3px}h1{font-family:Georgia,serif;font-size:clamp(2rem,6vw,3rem);line-height:1.15;font-weight:500}output,h1,p,[data-show]{white-space:pre-wrap;overflow-wrap:anywhere}label{display:block;margin:1rem 0;font-weight:600}input,textarea{display:block;width:100%;padding:.75rem;border:1px solid #a7b7a9;border-radius:.75rem;color:#203b35;background:white}textarea{min-height:6rem;resize:vertical}input[aria-invalid="true"],textarea[aria-invalid="true"]{outline:2px solid #b42318}small[role="alert"],#sedrava-error{display:block;color:#982c26}ul{padding-left:1.5rem;overflow-wrap:anywhere}li{margin:1rem 0}small[hidden],#sedrava-error[hidden]{display:none}</style>',

        "</head><body>",
        *widgets,
        '<p id="sedrava-error" role="alert" hidden></p>',
        "<script>",
        f"const initialState = JSON.parse({json_script(initial)});",
        "const storageKey = 'sedrava:' + (typeof location !== 'undefined' ? location.pathname : '/') + ':' + " + json_script(program.name) + ";",
        "const persistentKeys = " + json_script(list(program.persistent)) + ";",
        JS_RUNTIME, QUERY_RUNTIME, VECTOR_RUNTIME,
        js_runtime(program, json_script) if (structured(program)) else "const collectionTypes = {}; function legacySnapshotValid(saved) { return saved !== null && typeof saved === 'object' && !Array.isArray(saved) && Object.keys(saved).every(k => persistentKeys.includes(k) && validValue(saved[k],initialState[k])) && validateState({...initialState,...saved}); } function saveSnapshot() { if(restoreError) throw Error('Rejected saved data retained'); const previous=localStorage.getItem(storageKey); if(previous!==null && !legacySnapshotValid(JSON.parse(previous))) throw Error('Rejected saved data retained'); localStorage.setItem(storageKey,JSON.stringify(Object.fromEntries(persistentKeys.map(k=>[k,state[k]])))); }",
        "let restoreError = false;",
        "let state = { ...initialState };",
        ("try { const raw = localStorage.getItem(storageKey); if (raw !== null) state = restoreSnapshot(raw); } catch (_) { restoreError = true; }" if (structured(program)) else "try { const raw=typeof localStorage !== 'undefined' ? localStorage.getItem(storageKey) : null; if(raw!==null){ const saved=JSON.parse(raw); state=restoreState(saved); restoreError=!legacySnapshotValid(saved); } } catch (_) { restoreError=true; }"),
        "function checkedInt(n) { if (!Number.isInteger(n) || n < -2147483648 || n > 2147483647) throw new RangeError('Sedrava integer overflow'); return n; }",
        "function validText(value) { if (typeof value !== 'string') return false; let count = 0; for (const char of value) { const cp = char.codePointAt(0); if ((cp >= 0xD800 && cp <= 0xDFFF) || ++count > 1024) return false; } return true; }",
        "function validValue(value, initial) { return typeof value === typeof initial && (typeof value === 'string' ? validText(value) : typeof value === 'number' ? Number.isInteger(value) && value >= -2147483648 && value <= 2147483647 : typeof value === 'boolean'); }",
        "function checkResources(nextState) { if (JSON.stringify({schema:1,signature,state:nextState}).length > 200000) throw Error('State exceeds resource limit'); }" if (structured(program)) else "function checkResources(_) {}",
        "function checkStateValues(nextState) { if (Object.keys(nextState).length !== Object.keys(initialState).length) throw Error('Invalid keys'); for (const key of Object.keys(initialState)) { if (!Object.hasOwn(nextState, key) || !(Object.hasOwn(collectionTypes, key) ? validCollection(nextState[key], collectionTypes[key]) : validValue(nextState[key], initialState[key]))) throw new RangeError('Invalid Sedrava value'); } }",
        "function restoreState(saved) { try { return restoreSnapshot(saved); } catch (_) { return { ...initialState }; } }" if (structured(program)) else "function restoreState(saved) { const restored = { ...initialState }; if (saved && typeof saved === 'object' && !Array.isArray(saved)) { for (const key of persistentKeys) { if (Object.hasOwn(saved, key) && validValue(saved[key], initialState[key])) restored[key] = saved[key]; } } return validateState(restored) ? restored : { ...initialState }; }",
        "function editState(current, key, value) { if (!Object.hasOwn(initialState, key)) return current; const next = { ...current, [key]: value }; return validateState(next) ? next : current; }",
        "const actions = {",
        *actions,
        "};",
        "function checkDerivedState(nextState) { checkStateValues(nextState); const derivedState = { __proto__: null, ...nextState };",
        *derived_lines,
        "}",
        "function validateState(nextState) {",
        "  try { checkResources(nextState); checkStateValues(nextState); const derivedState = { __proto__: null, ...nextState };",
        *derived_lines,
        "    return " + rules + "; } catch (_) { return false; }",
        "}",
        "if (!validateState(state)) state = { ...initialState };",
        "function showError(message) { const el = document.getElementById('sedrava-error'); if (el) { el.textContent = message; el.hidden = !message; } }",
        "function render(resetInputs = false) {",
        "  const derivedState = { __proto__: null, ...state };",
        *derived_lines,
        '  document.querySelectorAll("[data-state]").forEach(el => { el.textContent = String(derivedState[el.dataset.state]); });',
        '  document.querySelectorAll("[data-show]").forEach(el => { el.hidden = !derivedState[el.dataset.show]; });',
        '  document.querySelectorAll("[data-input]").forEach(el => { if (resetInputs || document.activeElement !== el) el.value = String(state[el.dataset.input]); });',
        "  renderCollections();" if (structured(program)) else "",
        "}",
        'document.querySelectorAll("[data-action]").forEach(el => {',
        "  el.addEventListener('click', () => {",
        "    const action = actions[el.dataset.action];",
        "    if (!action) throw new Error('Unknown action');",
        "    try { const next = action(state); showError(next === state ? 'Action rejected by declared rules' : ''); state = next; }",
        "    catch (error) { showError('Action rejected: ' + error.message); return; }" if (structured(program)) else "    catch (_) { showError('Action rejected: integer overflow or invalid value'); return; }",
        "    try { saveSnapshot(); } catch (_) { showError('Could not save state; previous data retained'); }",
        "    render(true);",
        "  });",
        "});",
        "function validateInput(el) {",
        "  const key = el.dataset.input; const isText = typeof initialState[key] === 'string'; const raw = isText ? el.value : el.value.trim();",
        "  const parsed = Number(raw);",
        "  let accepted = false;",
        "  if (isText ? validText(raw) : (raw !== '' && /^-?[0-9]+$/.test(raw) && Number.isInteger(parsed) && parsed >= -2147483648 && parsed <= 2147483647)) {",
        "    const nextState = { ...state, [key]: isText ? raw : parsed };",
        "    accepted = validateState(nextState);",
        "    if (accepted) { state = nextState; try { saveSnapshot(); } catch (_) { showError('Could not save state; previous data retained'); } render(); }",
        "  }",
        "  const invalid = (isText || raw !== '') && !accepted;",
        "  el.setAttribute('aria-invalid', String(invalid));",
        "  const error = document.getElementById(el.getAttribute('aria-describedby'));",
        "  if (error) error.hidden = !invalid;",
        "}",
        "document.querySelectorAll('[data-input]').forEach(el => {",
        "  el.addEventListener('input', () => validateInput(el));",
        "  el.addEventListener('blur', () => { if (typeof initialState[el.dataset.input] !== 'string' && el.value.trim() === '') el.value = String(state[el.dataset.input]); validateInput(el); });",
        "});",
        "render();",
        "if (restoreError) showError('Saved data rejected; original retained');",
        "</script></body></html>",
    ]
    if _domain_only:
        start=parts.index("<script>")+1
        stop=next(i for i,line in enumerate(parts) if line.startswith("function showError(message)"))
        return "\n".join(parts[start:stop])+"\n"
    return "\n".join(parts)+"\n"

if __name__ == "__main__":
    cli = argparse.ArgumentParser()
    cli.add_argument("source")
    cli.add_argument("--output", default="build/web/index.html")
    args = cli.parse_args()
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(generate(Path(args.source).read_text(encoding="utf-8")), encoding="utf-8")
    print(target)
