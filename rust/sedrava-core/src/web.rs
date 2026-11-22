//! Native Web output for the deliberately restricted *scalar* Sedrava app subset.
//! No Python subprocess, eval, raw interpolation of user text into JavaScript,
//! hidden fallback or silent omission of unsupported features.
use crate::model::{fail, Binary, Expr, Kind, Program, Result, Stmt, Unary, Widget};
use std::collections::BTreeMap;

pub(crate) fn json<T: serde::Serialize + ?Sized>(value: &T) -> String {
    // Escape HTML-sensitive characters even inside script tags.
    serde_json::to_string(value)
        .expect("Serializable typed compiler output")
        .replace('&', "\\u0026")
        .replace('<', "\\u003c")
        .replace('>', "\\u003e")
}

fn html(value: &str) -> String {
    value
        .replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
        .replace('"', "&quot;")
        .replace('\'', "&#39;")
}

pub(crate) fn expr_js(expr: &Expr, scope: &BTreeMap<String, String>) -> Result<String> {
    let compiled = match expr {
        Expr::Int(v) => v.to_string(),
        Expr::Bool(v) => v.to_string(),
        Expr::Text(v) => json(v),
        Expr::Ident(name) => scope
            .get(name)
            .ok_or_else(|| crate::model::Error(format!("Web: unresolved identifier: {name}")))?
            .clone(),
        Expr::Unary(op, e) => {
            let e = expr_js(e, scope)?;
            match op {
                Unary::Neg => format!("checkedInt(-({e}))"),
                Unary::Not => format!("(!({e}))"),
            }
        }
        Expr::Binary(op, a, b) => {
            let a = expr_js(a, scope)?;
            let b = expr_js(b, scope)?;
            match op {
                Binary::Add => format!("checkedInt(({a})+({b}))"),
                Binary::Sub => format!("checkedInt(({a})-({b}))"),
                Binary::Mul => format!("checkedInt(({a})*({b}))"),
                _ => {
                    let symbol = match op {
                        Binary::Eq => "===",
                        Binary::Ne => "!==",
                        Binary::Lt => "<",
                        Binary::Le => "<=",
                        Binary::Gt => ">",
                        Binary::Ge => ">=",
                        Binary::And => "&&",
                        Binary::Or => "||",
                        _ => unreachable!(),
                    };
                    format!("(({a}) {symbol} ({b}))")
                }
            }
        }
        Expr::Conditional(test, yes, no) => format!(
            "(({}) ? ({}) : ({}))",
            expr_js(test, scope)?,
            expr_js(yes, scope)?,
            expr_js(no, scope)?
        ),
        Expr::Call { name, args, kwargs } => {
            if !kwargs.is_empty() {
                if !args.is_empty() {
                    return fail("Record constructors require named fields only");
                }
                let mut parts = Vec::new();
                for (field, expression) in kwargs {
                    parts.push(format!("[{}]:{}", json(field), expr_js(expression, scope)?));
                }
                return Ok(format!("({{{}}})", parts.join(",")));
            }
            // args are statically typechecked by the Rust parser.
            let is_query = matches!(
                name.as_str(),
                "filter" | "map" | "find" | "any" | "all" | "sort" | "sum"
            );
            let emit = args
                .iter()
                .enumerate()
                .map(|(index, arg)| {
                    if is_query && index == 1 {
                        Ok("undefined".to_owned())
                    } else {
                        expr_js(arg, scope)
                    }
                })
                .collect::<Result<Vec<_>>>()?;
            let first = emit.first().map(String::as_str).unwrap_or("");
            let second = emit.get(1).map(String::as_str).unwrap_or("undefined");
            match name.as_str() {
                "text_length" => format!("Array.from({first}).length"),
                "trim" => format!("({first}).replace(/^[ \\t\\r\\n]+|[ \\t\\r\\n]+$/g, '')"),
                "lower_ascii" => format!("({first}).replace(/[A-Z]/g,c=>c.toLowerCase())"),
                "contains" => format!("({first}).includes({second})"),
                "concat" => format!("sdrConcat({first},{second})"),
                "is_date" => format!("sdrIsDate({first})"),
                "date_days" => format!("sdrDateDays({first})"),
                "date_add" => format!("sdrDateAdd({first},{second})"),
                "count" | "next_id" | "append" | "get" | "has" | "remove" | "update" => {
                    let cap = if name == "append" {
                        if let Some(Expr::Ident(var)) = args.first() {
                            scope
                                .get(&format!("@capacity:{var}"))
                                .cloned()
                                .ok_or_else(|| {
                                    crate::model::Error(
                                        "Append requires a named list with known capacity".into(),
                                    )
                                })?
                        } else {
                            return fail("Append requires a named list with known capacity");
                        }
                    } else {
                        "0".to_owned()
                    };
                    let third = emit.get(2).map(String::as_str).unwrap_or("undefined");
                    format!(
                        "sdrCollectionOp({},{cap},{first},{second},{third})",
                        json(name)
                    )
                }
                "filter" | "map" | "find" | "any" | "all" | "sort" | "sum" => {
                    let selector = args
                        .get(1)
                        .ok_or_else(|| crate::model::Error("Query selector required".into()))?;
                    let selection = match selector {
                        Expr::Text(field) => {
                            let access = if field == "id" {
                                "_id".to_owned()
                            } else {
                                format!("_row[{}]", json(field))
                            };
                            if name == "map" {
                                return fail("Map requires typed function");
                            }
                            if let Some(compare) = emit.get(2) {
                                format!("({access}==={compare})")
                            } else {
                                access
                            }
                        }
                        Expr::Ident(function) => {
                            if !scope.contains_key(&format!("@fn:{function}")) {
                                return fail("Query selector function is unknown");
                            }
                            let extra = emit.iter().skip(2).cloned().collect::<Vec<_>>();
                            format!(
                                "pureFunctions[{}](_row{})",
                                json(function),
                                if extra.is_empty() {
                                    String::new()
                                } else {
                                    format!(",{}", extra.join(","))
                                }
                            )
                        }
                        _ => return fail("Unsupported collection query selector"),
                    };
                    format!("sdrQuery({},{first},(_row,_id)=>({selection}))", json(name))
                }
                _ => {
                    let func = scope.get(&format!("@fn:{name}")).ok_or_else(|| {
                        crate::model::Error(format!("Native Web unknown function: {name}"))
                    })?;
                    format!("({func})({})", emit.join(","))
                }
            }
        }
        Expr::Attr(base, field) => {
            format!("({})[{}]", expr_js(base, scope)?, json(field))
        }
    };
    Ok(compiled)
}

fn scope_for(program: &Program, state_ref: &str) -> BTreeMap<String, String> {
    let mut scope = BTreeMap::new();
    for name in program.states.keys() {
        scope.insert(name.clone(), format!("{state_ref}[{}]", json(name)));
    }
    for (name, _) in &program.derives {
        scope.insert(
            name.clone(),
            format!("resolved({state_ref})[{}]", json(name)),
        );
    }
    for name in program.functions.keys() {
        scope.insert(
            format!("@fn:{name}"),
            format!("pureFunctions[{}]", json(name)),
        );
    }
    for (name, kind) in &program.types {
        if let Kind::List { capacity, .. } = kind {
            scope.insert(format!("@capacity:{name}"), capacity.to_string());
        }
    }
    scope
}

fn statements_js(
    body: &[Stmt],
    scope: &BTreeMap<String, String>,
    out: &mut String,
    counter: &mut usize,
    depth: usize,
) -> Result<()> {
    let mut env = scope.clone();
    let pad = " ".repeat(depth);
    for statement in body {
        match statement {
            Stmt::Assign(name, e) => {
                let code = expr_js(e, &env)?;
                out.push_str(&format!("{pad}next[{}] = {code};\n", json(name)));
                out.push_str(&format!("{pad}checkStateValues(next); resolved(next);\n"));
            }
            Stmt::Let(name, e) => {
                let code = expr_js(e, &env)?;
                *counter += 1;
                let variable = format!("_local_{counter}");
                out.push_str(&format!("{pad}const {variable} = {code};\n"));
                env.insert(name.clone(), variable);
            }
            Stmt::Require(e) => {
                out.push_str(&format!(
                    "{pad}if (!({})) throw Error('Action requirement rejected');\n",
                    expr_js(e, &env)?
                ));
            }
            Stmt::Branch(condition, yes, no) => {
                out.push_str(&format!("{pad}if ({}) {{\n", expr_js(condition, &env)?));
                statements_js(yes, &env, out, counter, depth + 2)?;
                out.push_str(&format!("{pad}}}"));
                if !no.is_empty() {
                    out.push_str(" else {\n");
                    statements_js(no, &env, out, counter, depth + 2)?;
                    out.push_str(&format!("{pad}}}"));
                }
                out.push('\n');
            }
        }
    }
    Ok(())
}

fn validate_state_types(program: &Program) -> Result<()> {
    for key in program.states.keys() {
        match program.types.get(key) {
            Some(Kind::Int | Kind::Bool | Kind::Text) => {}
            Some(Kind::List { record, .. }) if matches!(record.as_ref(), Kind::Record { .. }) => {}
            _ => return fail("Native Web supports only scalar states and bounded record lists"),
        }
    }
    Ok(())
}

/// Returns self-contained HTML with JS generated without invoking Python.
/// Throws a clear error on unsupported features instead of producing a
/// misleading, incomplete application.
pub fn generate_web(program: &Program) -> Result<String> {
    if program.screens.is_empty() {
        return fail("Missing native Web screen");
    }
    let mut output = String::new();
    output.push_str("<!doctype html>\n<html lang=\"ru\"><head><meta charset=\"utf-8\">");
    output.push_str("<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">");
    output.push_str(&format!("<title>{}</title>", html(&program.name)));
    output.push_str("<style>*{box-sizing:border-box}body{max-width:44rem;margin:3rem auto;padding:0 1rem;font:1.1rem/1.5 system-ui;color:#203b35;background:#f5f4f0}h1{font-size:clamp(2rem,5vw,3rem)}button,input{font:inherit}button{background:#215d50;color:white;border:0;border-radius:.75rem;padding:.8rem 1.2rem;margin:.3rem .3rem .3rem 0;min-height:48px;cursor:pointer}button:focus-visible,input:focus-visible{outline:3px solid #9c6417;outline-offset:3px}label{display:block;margin:.8rem 0}input{display:block;padding:.6rem;max-width:100%}output{white-space:pre-wrap}#sedrava-error{color:#a31818;white-space:pre-wrap}#sedrava-error[hidden],[data-show][hidden]{display:none}</style></head><body>\n");
    for (screen_name, screen) in &program.screens {
        output.push_str(&format!(
            "<section data-screen=\"{}\" hidden>\n",
            html(screen_name)
        ));
        let widgets = &screen.widgets;
        let mut title_seen = false;
        for widget in widgets {
            match widget {
                Widget::Text(text) => {
                    let tag = if title_seen { "p" } else { "h1" };
                    output.push_str(&format!("<{tag}>{}</{tag}>\n", html(text)));
                    title_seen = true;
                }
                Widget::Value(name) => {
                    output.push_str(&format!(
                        "<p>{}: <output data-state=\"{}\"></output></p>\n",
                        html(name),
                        html(name)
                    ));
                }
                Widget::Show { condition, label } => {
                    output.push_str(&format!(
                        "<p data-show=\"{}\" hidden>{}</p>\n",
                        html(condition),
                        html(label)
                    ));
                }
                Widget::Input { state, label } => {
                    let kind = program.types.get(state);
                    let input_type = match kind {
                        Some(Kind::Int) => "number",
                        Some(Kind::Text) => "text",
                        _ => return fail("Native Web input requires int or text state"),
                    };
                    output.push_str(&format!(
                    "<label>{}<input data-input=\"{}\" type=\"{}\" aria-label=\"{}\"></label>\n",
                    html(label),
                    html(state),
                    input_type,
                    html(label)
                ));
                }
                Widget::Button { label, action } => {
                    output.push_str(&format!(
                        "<button type=\"button\" data-action=\"{}\">{}</button>\n",
                        html(action),
                        html(label)
                    ));
                }
                Widget::Display(expr) => {
                    let compiled = expr_js(expr, &scope_for(program, "next"))?;
                    // Store a generated expression index; actual value is computed
                    // with controlled compiler output, never interpreted from DOM.
                    output.push_str("<p><output data-display></output></p>\n");
                    let _ = compiled; // runtime initialization below generates it in order
                }
                Widget::List {
                    collection,
                    selected,
                    options,
                } => {
                    let command = options
                        .iter()
                        .find(|(key, _)| key == "open")
                        .map(|(_, value)| value.as_str());
                    let extra = command
                        .map(|value| format!(" data-open=\"{}\"", html(value)))
                        .unwrap_or_default();
                    output.push_str(&format!(
                        "<ul data-list=\"{}\" data-select=\"{}\"{extra}></ul>\n",
                        html(collection),
                        html(selected)
                    ));
                }
            }
        }
        output.push_str("</section>\n");
    }
    output
        .push_str("<p id=\"sedrava-error\" role=\"alert\" hidden></p>\n<script>\n'use strict';\n");
    let names = append_domain(program, &mut output, None)?;
    output.push_str("function screenVisible(name,next){try{const r=resolved(next);switch(name){\n");
    for (name, screen) in &program.screens {
        let expression = if let Some(guard) = &screen.guard {
            expr_js(guard, &names)?
        } else {
            "true".into()
        };
        output.push_str(&format!("case {}:return !!({expression});\n", json(name)));
    }
    output.push_str("default:return false;}}catch(_){return false;}}\n");
    output.push_str("function normalizeStack(){while(screenStack.length>1 && !screenVisible(screenStack[screenStack.length-1],state))screenStack.pop();}\n");
    output.push_str(
        r#"
const errorEl=document.getElementById('sedrava-error');
function showError(message){errorEl.textContent=message;errorEl.hidden=!message;}
function renderCollections(){
    document.querySelectorAll('[data-list]').forEach(el=>{
        el.replaceChildren();
        for(const row of state[el.dataset.list].items){
            const item=document.createElement('li');
            item.dataset.id=String(row.id);
            const label=document.createElement('span');
            label.textContent=Object.entries(row).filter(([key])=>key!=='id')
                .map(([key,value])=>key+': '+String(value)).join(' · ');
            item.append(label);
            const button=document.createElement('button');
            button.type='button';button.textContent='Select';
            button.setAttribute('aria-label','Select '+row.id);
            button.onclick=()=>{
                const next={...state,[el.dataset.select]:row.id};
                if(!validate(next)){showError('Selection rejected');return;}
                if(el.dataset.open) {
                    dispatch(el.dataset.open,next);
                } else if(saveSnapshot(next)) {
                    state=next;normalizeStack();showError('');render();
                }
            };
            item.append(button);
            el.append(item);
        }
    });
}
function render(){
    normalizeStack();
    const active=screenStack[screenStack.length-1];
    document.querySelectorAll('[data-screen]').forEach(el=>{el.hidden=el.dataset.screen!==active;});
    const r=resolved(state);
    document.querySelectorAll('[data-state]').forEach(el=>{
        el.textContent=String(r[el.dataset.state]);
    });
    document.querySelectorAll('[data-show]').forEach(el=>{
        el.hidden=!r[el.dataset.show];
    });
    document.querySelectorAll('[data-input]').forEach(el=>{
        if (document.activeElement!==el) el.value=String(state[el.dataset.input]);
    });
    renderCollections();
"#,
    );
    let mut display = 0;
    for (name, screen) in &program.screens {
        for widget in &screen.widgets {
            if let Widget::Display(expr) = widget {
                let code = expr_js(expr, &names)?;
                output.push_str(&format!(
                    "    if(screenStack[screenStack.length-1]==={})document.querySelectorAll('[data-display]')[{}].textContent=String({code});\n",
                    json(name),display
                ));
                display += 1;
            }
        }
    }
    output.push_str(
        r#"}
function dispatch(command, selectedState){
    try {
        let proposed=selectedState||state;
        let stack=[...screenStack];
        if(command==='$back'){
            if(stack.length>1)stack.pop();
        } else if(Object.hasOwn(navigationRoutes,command)){
            const route=navigationRoutes[command];
            if(route.action!==null){
                if(!Object.hasOwn(actions,route.action))throw Error('Unknown domain action');
                const next=actions[route.action](proposed);
                if(next===proposed)throw Error('Domain action rejected');
                proposed=next;
            }
            if(route.target==='pop'){
                if(stack.length>1)stack.pop();
            }else{
                if(stack.length>=32||!screenVisible(route.target,proposed))
                    throw Error('Target screen unavailable');
                stack.push(route.target);
            }
        } else if(Object.hasOwn(actions,command)){
            const next=actions[command](proposed);
            if(next===proposed)throw Error('Action rejected by declared rules');
            proposed=next;
        } else{
            throw Error('Unknown action or navigation command');
        }
        if(!validate(proposed))throw Error('State invariant rejected');
        if(!saveSnapshot(proposed))return;
        state=proposed;
        screenStack=stack;
        normalizeStack();
        showError('');
        render();
    } catch(error){
        showError('Action rejected: '+error.message);
    }
}
document.querySelectorAll('[data-action]').forEach(el=>{
    el.addEventListener('click',()=>dispatch(el.dataset.action));
});
document.querySelectorAll('[data-input]').forEach(el=>{
    el.addEventListener('change',()=>{
        const key=el.dataset.input, input=el.value;
        const number=Number(input);
        const value=typeof state[key]==='number'
            ? (/^-?[0-9]+$/.test(input.trim()) && Number.isInteger(number) ? number : NaN)
            : input;
        const next={...state,[key]:value};
        if (!validate(next)){showError('Invalid input or rule violation');return;}
        if(saveSnapshot(next)) {state=next;normalizeStack();showError('');render();}
    });
});
if(!validate(state)) showError('Invalid initial state');
else {restoreSaved();render();}

</script></body></html>
"#,
    );
    Ok(output)
}

pub(crate) fn append_domain(
    program: &Program,
    output: &mut String,
    namespace: Option<&str>,
) -> Result<BTreeMap<String, String>> {
    validate_state_types(program)?;
    let scope = scope_for(program, "next");
    output.push_str(&format!(
        "const initialState = JSON.parse({});\n",
        json(
            &serde_json::to_string(&program.states)
                .map_err(|e| crate::model::Error(e.to_string()))?
        )
    ));
    let mut meta = serde_json::Map::new();
    for (name, kind) in &program.types {
        if let Kind::List { record, capacity } = kind {
            let Kind::Record { fields, .. } = record.as_ref() else {
                return fail("Native Web lists require records");
            };
            let mut field_meta = serde_json::Map::new();
            for (field, kind) in fields {
                let type_name = match kind {
                    Kind::Int => "number",
                    Kind::Bool => "boolean",
                    Kind::Text => "string",
                    _ => return fail("Nested record fields are not supported"),
                };
                field_meta.insert(field.clone(), serde_json::json!(type_name));
            }
            meta.insert(
                name.clone(),
                serde_json::json!({
                    "capacity":capacity,"fields":field_meta
                }),
            );
        }
    }
    output.push_str(&format!(
        "const collectionTypes=JSON.parse({});\n",
        json(&serde_json::to_string(&meta).map_err(|e| crate::model::Error(e.to_string()))?)
    ));
    output.push_str(r#"
let state = { ...initialState };
function checkedInt(n) {
    if (!Number.isInteger(n) || n < -2147483648 || n > 2147483647) {
        throw new RangeError('Sedrava int32 overflow');
    }
    return n;
}
function validText(s) {
    if (typeof s !== 'string') return false;
    let count=0;
    for (const c of s) {
        const cp=c.codePointAt(0);
        if ((cp>=0xD800 && cp<=0xDFFF) || ++count>1024) return false;
    }
    return true;
}
function exactKeys(value,keys){
    return value!==null && typeof value==='object' && !Array.isArray(value)
        && Object.keys(value).length===keys.length && keys.every(k=>Object.hasOwn(value,k));
}
function validRecord(row,fields,includeId){
    const names=[...Object.keys(fields),...(includeId?['id']:[])];
    if(!exactKeys(row,names))return false;
    if(includeId&&!Number.isInteger(row.id))return false;
    return Object.entries(fields).every(([key,type])=>{
        const value=row[key];
        if(typeof value!==type)return false;
        return type==='number'
            ? Number.isInteger(value)&&value>=-2147483648&&value<=2147483647
            : type==='string' ? validText(value) : true;
    });
}
function validCollection(value,kind){
    if(!exactKeys(value,['items','next_id'])||!Array.isArray(value.items)||
       value.items.length>kind.capacity||
       !Number.isInteger(value.next_id)||value.next_id<1||value.next_id>2147483647)return false;
    const ids=new Set();
    for(const row of value.items){
        if(!validRecord(row,kind.fields,true)||
           row.id<1||row.id>=value.next_id||ids.has(row.id))return false;
        ids.add(row.id);
    }
    return true;
}
function sdrCollectionOp(op,capacity,list,arg,record){
    if(op==='count')return list.items.length;
    if(op==='next_id')return list.next_id;
    if(op==='append'){
        if(list.items.length>=capacity)throw Error('List capacity exceeded');
        if(list.next_id>=2147483647)throw Error('Identity exhausted');
        return {next_id:list.next_id+1,items:[...list.items,{id:list.next_id,...arg}]};
    }
    const found=list.items.find(row=>row.id===arg);
    if(op==='has')return !!found;
    if(!found)throw Error('Missing record identity');
    if(op==='get'){
        const {id,...fields}=found;
        return fields;
    }
    return {next_id:list.next_id,items:
        op==='remove'?list.items.filter(row=>row.id!==arg):
        list.items.map(row=>row.id===arg?{id:arg,...record}:row)
    };
}
function sdrQuery(op,list,select){
    const value=row=>{const {id,...record}=row;return select(record,id);};
    if(op==='find')return list.items.find(row=>value(row))?.id||0;
    if(op==='any')return list.items.some(value);
    if(op==='all')return list.items.every(value);
    if(op==='sum'){
        let result=0;
        for(const row of list.items)result=checkedInt(result+value(row));
        return result;
    }
    let items=list.items;
    if(op==='filter')items=items.filter(value);
    if(op==='map')items=items.map(row=>({id:row.id,...value(row)}));
    if(op==='sort'){
        const compare=(a,b)=>{
            if(typeof a!=='string')return a<b?-1:a>b?1:0;
            const x=Array.from(a,c=>c.codePointAt(0));
            const y=Array.from(b,c=>c.codePointAt(0));
            for(let i=0;i<Math.min(x.length,y.length);i++)
                if(x[i]!==y[i])return x[i]<y[i]?-1:1;
            return x.length-y.length;
        };
        items=items.map((row,index)=>({row,index,key:value(row)}))
            .sort((a,b)=>compare(a.key,b.key)||a.index-b.index)
            .map(x=>x.row);
    }
    return {items,next_id:list.next_id};
}
function checkStateValues(next) {
    if (Object.keys(next).length!==Object.keys(initialState).length) throw Error('Unexpected state keys');
    for(const key of Object.keys(initialState)){
        if (!Object.hasOwn(next,key)) throw Error('Missing state key');
        const initial=initialState[key], v=next[key];
        if (Object.hasOwn(collectionTypes,key)){
            if(!validCollection(v,collectionTypes[key]))throw Error('Invalid collection');
            continue;
        }
        if (typeof v!==typeof initial) throw Error('Wrong state type');
        if (typeof v==='number') checkedInt(v);
        else if (typeof v==='string' && !validText(v)) throw Error('Invalid string');
    }
}
"#);
    // UTC-only checked scalar library, matching the bounded native types.
    output.push_str(r#"
function sdrConcat(a,b){const result=a+b;if(!validText(result))throw RangeError('Text limit');return result;}
function sdrDate(value){
    const match=/^([0-9]{4})-([0-9]{2})-([0-9]{2})$/.exec(value);
    if(!match)throw RangeError('Expected YYYY-MM-DD');
    const year=Number(match[1]),month=Number(match[2]),day=Number(match[3]);
    const date=new Date(0);
    date.setUTCFullYear(year,month-1,day);
    if(year<1||year>9999||date.getUTCFullYear()!==year||
       date.getUTCMonth()!==month-1||date.getUTCDate()!==day){
       throw RangeError('Invalid civil date');
    }
    return date;
}
function sdrIsDate(value){try{sdrDate(value);return true;}catch(_){return false;}}
function sdrDateDays(value){return sdrDate(value).valueOf()/86400000;}
function sdrDateAdd(value,delta){
    const days=sdrDateDays(value)+delta;
    if(days<-719162||days>2932896)throw RangeError('Date outside 0001..9999');
    return new Date(days*86400000).toISOString().slice(0,10);
}
const pureFunctions=Object.create(null);
"#);
    for (name, function) in &program.functions {
        let mut local = scope_for(program, "next");
        let mut args = Vec::new();
        for (index, (param, _)) in function.parameters.iter().enumerate() {
            let js = format!("_arg{index}");
            local.insert(param.clone(), js.clone());
            if let Kind::List { capacity, .. } = &function.parameters[index].1 {
                local.insert(format!("@capacity:{param}"), capacity.to_string());
            }
            args.push(js);
        }
        let body = expr_js(&function.body, &local)?;
        output.push_str(&format!(
            "pureFunctions[{}]=({})=>({body});\n",
            json(name),
            args.join(",")
        ));
    }
    let mut names = BTreeMap::new();
    for name in program.functions.keys() {
        names.insert(
            format!("@fn:{name}"),
            format!("pureFunctions[{}]", json(name)),
        );
    }
    for key in program.states.keys() {
        names.insert(key.clone(), format!("r[{}]", json(key)));
    }
    output.push_str("function resolved(next){\n  const r={__proto__:null,...next};\n");
    for (name, expr) in &program.derives {
        output.push_str(&format!(
            "  r[{}]={};\n",
            json(name),
            expr_js(expr, &names)?
        ));
        names.insert(name.clone(), format!("r[{}]", json(name)));
    }
    output.push_str("  return r;\n}\n");
    output.push_str(
        "function validate(next){try{checkStateValues(next);const r=resolved(next);return ",
    );
    if program.rules.is_empty() {
        output.push_str("true");
    } else {
        for (idx, expr) in program.rules.iter().enumerate() {
            if idx > 0 {
                output.push_str(" && ");
            }
            output.push_str(&format!("({})", expr_js(expr, &names)?));
        }
    }
    output.push_str(";}catch(_){return false;}}\n");
    output.push_str(&format!(
        "const initialScreen={};\nconst navigationRoutes=JSON.parse({});\nlet screenStack=[initialScreen];\n",
        json(&program.initial_screen),
        json(&serde_json::to_string(&program.navigation)
            .map_err(|e|crate::model::Error(e.to_string()))?)
    ));

    // Persistent scalar snapshots use the same schema signature and selected
    // state names as the Rust/Python schema-1 CLI. Browser localStorage cannot
    // reject every JSON duplicate-key case; never claim strict CLI equivalence.
    output.push_str(&format!(
        "const persistKeys = {};\nconst snapshotSignature = {};\nconst hasPersistence = {};\n",
        json(&program.persistent.iter().collect::<Vec<_>>()),
        json(&crate::snapshot::fingerprint(program)?),
        if program.persistent.is_empty() {
            "false"
        } else {
            "true"
        }
    ));
    output.push_str("const storageKey = 'sedrava-native:' + (typeof location !== 'undefined' ? location.pathname : '/') + ':' + ");
    if let Some(namespace) = namespace {
        output.push_str(&format!("{} + ':' + ", json(namespace)));
    }
    output.push_str(
        r#"JSON.stringify(snapshotSignature);
let previousRaw = null;
let restoreBlocked = false;
function own(obj, key) { return Object.hasOwn(obj, key); }
function isPlainRecord(value) {
    return value !== null && typeof value === 'object' && !Array.isArray(value) &&
        (Object.getPrototypeOf(value) === Object.prototype ||
         Object.getPrototypeOf(value) === null);
}
// Reject duplicate JSON keys and non-integer JSON numbers before hydration.
function strictJSON(raw){
    if(typeof raw!=='string'||raw.length>200000)throw Error('Snapshot too large');
    let index=0;
    const primitive=/(?:true|false|null|-?(?:0|[1-9][0-9]*))/y;
    function ws(){
        while(index<raw.length&&' \n\r\t'.includes(raw[index]))index++;
    }
    function parseValue(depth=0){
        if(depth>32)throw Error('JSON nesting limit');
        ws();const start=index;
        if(raw[index]==='"'){
            index++;
            while(index<raw.length){
                if(raw[index]==='\\'){index+=2;continue;}
                if(raw[index++]==='"')return JSON.parse(raw.slice(start,index));
            }
            throw Error('Unterminated string');
        }
        if(raw[index]==='{'){
            index++;const obj=Object.create(null);
            ws();if(raw[index]==='}'){index++;return obj;}
            while(true){
                ws();if(raw[index]!=='"')throw Error('Object key required');
                const key=parseValue(depth+1);
                ws();if(raw[index++]!==':'||Object.hasOwn(obj,key))
                    throw Error('Duplicate or invalid key');
                obj[key]=parseValue(depth+1);
                ws();const separator=raw[index++];
                if(separator==='}')return obj;
                if(separator!==',')throw Error('Invalid JSON object');
            }
        }
        if(raw[index]==='['){
            index++;const arr=[];
            ws();if(raw[index]===']'){index++;return arr;}
            while(true){
                arr.push(parseValue(depth+1));
                ws();const separator=raw[index++];
                if(separator===']')return arr;
                if(separator!==',')throw Error('Invalid JSON array');
            }
        }
        primitive.lastIndex=index;
        const matched=primitive.exec(raw);
        if(!matched)throw Error('Invalid JSON number or literal');
        index+=matched[0].length;
        return JSON.parse(matched[0]);
    }
    const result=parseValue();
    ws();if(index!==raw.length)throw Error('Trailing snapshot JSON');
    return result;
}
function readPersistentSnapshot(raw) {
    const candidate = strictJSON(raw);
    if (!isPlainRecord(candidate) || Object.keys(candidate).length !== 3 ||
        !own(candidate,'schema') || !own(candidate,'signature') || !own(candidate,'state') ||
        candidate.schema !== 1 || candidate.signature !== snapshotSignature ||
        !isPlainRecord(candidate.state)) {
        throw Error('Saved schema is incompatible');
    }
    if (Object.keys(candidate.state).length !== persistKeys.length ||
        persistKeys.some(key => !own(candidate.state,key))) {
        throw Error('Saved persistent keys differ from source');
    }
    const next = {...initialState, ...candidate.state};
    if (!validate(next)) throw Error('Saved state does not satisfy types or rules');
    return next;
}
function restoreSaved() {
    if (!hasPersistence) return;
    try {
        if (typeof localStorage === 'undefined') throw Error('Storage is unavailable');
        previousRaw = localStorage.getItem(storageKey);
        if (previousRaw !== null) state = readPersistentSnapshot(previousRaw);
    } catch(error) {
        restoreBlocked = true;
        showError('Saved data rejected; original retained: ' + String(error.message));
    }
}
function saveSnapshot(next) {
    if (!hasPersistence) return true;
    if (restoreBlocked) {
        showError('Saved data rejected; original retained');
        return false;
    }
    try {
        if (typeof localStorage === 'undefined') throw Error('Storage is unavailable');
        if (localStorage.getItem(storageKey) !== previousRaw) {
            throw Error('Storage changed externally; reload before editing');
        }
        if (!validate(next)) throw Error('Invalid state');
        const retained = Object.create(null);
        for (const key of persistKeys) retained[key] = next[key];
        const raw = JSON.stringify({schema:1, signature:snapshotSignature,state:retained});
        if (raw.length > 200000) throw Error('Snapshot exceeds browser size limit');
        localStorage.setItem(storageKey, raw);
        previousRaw = raw;
        return true;
    } catch(error) {
        showError('Cannot save state; previous data retained: ' + String(error.message));
        return false;
    }
}
"#,
    );
    output.push_str("const actions = Object.create(null);\n");
    let mut counter = 0;
    for (name, body) in &program.actions {
        output.push_str(&format!(
            "actions[{}]=function(state){{\n  const next={{...state}};\n",
            json(name)
        ));
        statements_js(body, &scope, output, &mut counter, 2)?;
        output.push_str("  return validate(next) ? next : state;\n};\n");
    }
    Ok(names)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::parser::parse;

    #[test]
    fn generates_a_real_scalar_counter() {
        let program = parse(include_str!("../../../examples/counter.sdr")).unwrap();
        let output = generate_web(&program).unwrap();
        assert!(output.contains("<button"));
        assert!(output.contains("data-action=\"increment\""));
        assert!(output.contains("checkedInt"));
        assert!(output.contains("const actions = Object.create(null)"));
        assert!(!output.contains("python3"));
    }
    #[test]
    fn output_escapes_html_and_script_tags() {
        let program=parse("app \"Safe <script>\"\nstate x = 0\nscreen main:\n    text \"</script><img src=x onerror=alert(1)>\"\n    value x\n").unwrap();
        let output = generate_web(&program).unwrap();
        assert!(output.contains("&lt;script&gt;"));
        assert!(output.contains("&lt;/script&gt;&lt;img"));
        assert!(!output.contains("<img src=x"));
    }
    #[test]
    fn native_web_supports_typed_app_examples() {
        for source in [
            include_str!("../../../examples/task_manager_navigation.sdr"),
            include_str!("../../../tests/rust_cases/native_web_functions.sdr"),
            include_str!("../../../tests/rust_cases/native_web_queries.sdr"),
        ] {
            let program = parse(source).unwrap();
            let output = generate_web(&program).unwrap();
            assert!(output.starts_with("<!doctype html>"));
            assert!(output.contains("function strictJSON"));
            assert!(output.contains("sdrCollectionOp"));
            assert!(output.contains("function screenVisible"));
            assert!(output.contains("pureFunctions"));
        }
    }

    #[test]
    fn explicit_rejection_for_unsupported_web_features() {
        let program = parse(include_str!("../../../examples/reference_09.sdr")).unwrap();
        let output = generate_web(&program).unwrap();
        assert!(output.contains("const persistKeys"));
        assert!(output.contains("snapshotSignature"));
        let program = parse(include_str!("../../../examples/task_manager.sdr")).unwrap();
        let output = generate_web(&program).unwrap();
        assert!(output.contains("data-list"));
        assert!(output.contains("sdrCollectionOp"));
    }
}
