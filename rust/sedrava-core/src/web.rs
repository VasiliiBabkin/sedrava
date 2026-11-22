//! Native Web output for the deliberately restricted *scalar* Sedrava app subset.
//! No Python subprocess, eval, raw interpolation of user text into JavaScript,
//! hidden fallback or silent omission of unsupported features.
use crate::model::{fail, Binary, Expr, Kind, Program, Result, Stmt, Unary, Widget};
use std::collections::BTreeMap;

fn json<T: serde::Serialize>(value: &T) -> String {
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

fn expr_js(expr: &Expr, scope: &BTreeMap<String, String>) -> Result<String> {
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
        Expr::Call { .. } | Expr::Attr(..) => return fail(
            "Native Web scalar subset does not yet support function calls, records or collections",
        ),
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

fn scalar_only(program: &Program) -> Result<()> {
    if program.has_navigation || program.screens.len() != 1 || !program.screens.contains_key("main")
    {
        return fail("Native Web generation does not yet support navigation or multiple screens");
    }
    if !program.persistent.is_empty() {
        return fail(
            "Native Web persistence not implemented: refusing to omit persist declarations",
        );
    }
    if !program.functions.is_empty() {
        return fail("Native Web pure function translation not implemented");
    }
    for key in program.states.keys() {
        if !matches!(
            program.types.get(key),
            Some(Kind::Int | Kind::Bool | Kind::Text)
        ) {
            return fail(
                "Native Web only supports scalar states; record/list generation is pending",
            );
        }
    }
    for widget in &program.screens["main"].widgets {
        if matches!(widget, Widget::List { .. }) {
            return fail("Native Web list widgets are not yet implemented");
        }
    }
    Ok(())
}

/// Returns self-contained HTML with JS generated without invoking Python.
/// Throws a clear error on unsupported features instead of producing a
/// misleading, incomplete application.
pub fn generate_web(program: &Program) -> Result<String> {
    scalar_only(program)?;
    let scope = scope_for(program, "next");
    let mut output = String::new();
    output.push_str("<!doctype html>\n<html lang=\"ru\"><head><meta charset=\"utf-8\">");
    output.push_str("<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">");
    output.push_str(&format!("<title>{}</title>", html(&program.name)));
    output.push_str("<style>*{box-sizing:border-box}body{max-width:44rem;margin:3rem auto;padding:0 1rem;font:1.1rem/1.5 system-ui;color:#203b35;background:#f5f4f0}h1{font-size:clamp(2rem,5vw,3rem)}button,input{font:inherit}button{background:#215d50;color:white;border:0;border-radius:.75rem;padding:.8rem 1.2rem;margin:.3rem .3rem .3rem 0;min-height:48px;cursor:pointer}button:focus-visible,input:focus-visible{outline:3px solid #9c6417;outline-offset:3px}label{display:block;margin:.8rem 0}input{display:block;padding:.6rem;max-width:100%}output{white-space:pre-wrap}#sedrava-error{color:#a31818;white-space:pre-wrap}#sedrava-error[hidden],[data-show][hidden]{display:none}</style></head><body>\n");
    let widgets = &program.screens["main"].widgets;
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
            Widget::List { .. } => return fail("Unsupported native Web list widget"),
        }
    }
    output
        .push_str("<p id=\"sedrava-error\" role=\"alert\" hidden></p>\n<script>\n'use strict';\n");
    output.push_str(&format!(
        "const initialState = JSON.parse({});\n",
        json(
            &serde_json::to_string(&program.states)
                .map_err(|e| crate::model::Error(e.to_string()))?
        )
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
function checkStateValues(next) {
    if (Object.keys(next).length!==Object.keys(initialState).length) throw Error('Unexpected state keys');
    for(const key of Object.keys(initialState)){
        if (!Object.hasOwn(next,key)) throw Error('Missing state key');
        const initial=initialState[key], v=next[key];
        if (typeof v!==typeof initial) throw Error('Wrong state type');
        if (typeof v==='number') checkedInt(v);
        else if (typeof v==='string' && !validText(v)) throw Error('Invalid string');
    }
}
"#);
    let mut names = BTreeMap::new();
    for key in program.states.keys() {
        names.insert(key.clone(), format!("r[{}]", json(key)));
    }
    output.push_str("function resolved(next){\n  const r={...next};\n");
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
    output.push_str("const actions = Object.create(null);\n");
    let mut counter = 0;
    for (name, body) in &program.actions {
        output.push_str(&format!(
            "actions[{}]=function(state){{\n  const next={{...state}};\n",
            json(name)
        ));
        statements_js(body, &scope, &mut output, &mut counter, 2)?;
        output.push_str("  return validate(next) ? next : state;\n};\n");
    }
    output.push_str(
        r#"
const errorEl=document.getElementById('sedrava-error');
function showError(message){errorEl.textContent=message;errorEl.hidden=!message;}
function render(){
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
"#,
    );
    let mut display = 0;
    for widget in widgets {
        if let Widget::Display(expr) = widget {
            let code = expr_js(expr, &names)?;
            output.push_str(&format!(
                "    document.querySelectorAll('[data-display]')[{}].textContent=String({code});\n",
                display
            ));
            display += 1;
        }
    }
    output.push_str(
        r#"}
document.querySelectorAll('[data-action]').forEach(el=>{
    el.addEventListener('click',()=>{
        try {
            const fn=actions[el.dataset.action];
            if (!Object.hasOwn(actions,el.dataset.action)) throw Error('Unknown action');
            const next=fn(state);
            if (next===state) showError('Action rejected by declared rules');
            else {state=next;showError('');}
            render();
        } catch(e) {showError('Action rejected: '+e.message);}
    });
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
        state=next;showError('');render();
    });
});
if(!validate(state)) showError('Invalid initial state');
else render();
</script></body></html>
"#,
    );
    Ok(output)
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
    fn explicit_rejection_for_unsupported_web_features() {
        let program = parse(include_str!("../../../examples/reference_09.sdr")).unwrap();
        assert!(generate_web(&program).is_err()); // persistent states not yet supported
        let program = parse(include_str!("../../../examples/task_manager.sdr")).unwrap();
        assert!(generate_web(&program).is_err()); // collections unsupported
    }
}
