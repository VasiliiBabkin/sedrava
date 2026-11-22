//! Independent proof that a Web target can consume only the candidate JSON IR.
//! This is NOT the production/legacy Web generator; the supported slice is intentionally small.
use crate::model::{fail, Result};
use serde_json::Value as Json;

const TEMPLATE: &str = r#"<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Sedrava IR candidate preview</title></head>
<body><main><h1 id="title"></h1><div id="app"></div><p id="error" role="alert"></p></main>
<script>
"use strict";
const doc = __SEDJAVA_JSON__;
const program = doc.program;
let state = Object.create(null);
for (const entry of program.state) state[entry.name] = entry.initial;
const actions = new Map(program.actions.map(a => [a.name, a.statements]));
const INT_MIN = -2147483648, INT_MAX = 2147483647;
function checkedInt(value) {
  if (!Number.isSafeInteger(value) || value < INT_MIN || value > INT_MAX) throw Error("int32 overflow");
  return value;
}
function evaluate(node, env) {
  switch (node.node) {
    case "literal": return node.value;
    case "reference":
      if (!Object.hasOwn(env, node.name)) throw Error("unknown reference");
      return env[node.name];
    case "unary": {
      const arg = evaluate(node.argument, env);
      if (node.operator === "neg") return checkedInt(-arg);
      if (node.operator === "not") return !arg;
      throw Error("unknown unary operator");
    }
    case "conditional":
      return evaluate(node.test, env) ? evaluate(node.then, env) : evaluate(node.else, env);
    case "binary": {
      const a = evaluate(node.left, env);
      if (node.operator === "and" && !a) return false;
      if (node.operator === "or" && a) return true;
      const b = evaluate(node.right, env);
      switch (node.operator) {
        case "add": return checkedInt(a + b);
        case "sub": return checkedInt(a - b);
        case "mul": return checkedInt(a * b);
        case "eq": return a === b;
        case "ne": return a !== b;
        case "lt": return a < b;
        case "le": return a <= b;
        case "gt": return a > b;
        case "ge": return a >= b;
        case "and": return Boolean(a && b);
        case "or": return Boolean(a || b);
        default: throw Error("unknown binary operator");
      }
    }
    default: throw Error("unknown expression node");
  }
}
function assertType(key, value) {
  const declaration = program.state.find(e => e.name === key);
  if (!declaration) throw Error("undeclared state");
  const kind = declaration.type;
  if (kind === "int") checkedInt(value);
  else if (kind === "bool" && typeof value !== "boolean") throw Error("bool expected");
  else if (kind === "text" && (typeof value !== "string" || [...value].length > 1024)) throw Error("text expected");
  else if (!["int", "bool", "text"].includes(kind)) throw Error("unknown type");
}
function runAction(name) {
  try {
    if (!actions.has(name)) throw Error("unknown action");
    const candidate = Object.assign(Object.create(null), state);
    for (const stmt of actions.get(name)) {
      if (stmt.op === "require") {
        if (evaluate(stmt.expression, candidate) !== true) throw Error("require rejected");
      } else if (stmt.op === "set") {
        const value = evaluate(stmt.expression, candidate);
        assertType(stmt.target, value);
        candidate[stmt.target] = value;
      } else throw Error("unknown statement");
    }
    for (const rule of program.rules) {
      if (evaluate(rule, candidate) !== true) throw Error("rule rejected");
    }
    state = candidate;
    document.getElementById("error").textContent = "";
    render();
  } catch (error) {
    document.getElementById("error").textContent = String(error.message || error);
  }
}
function render() {
  const root = document.getElementById("app");
  root.replaceChildren();
  for (const widget of program.screen.widgets) {
    let element;
    if (widget.kind === "text") {
      element = document.createElement("p");
      element.textContent = widget.text;
    } else if (widget.kind === "value") {
      element = document.createElement("p");
      element.textContent = String(state[widget.name]);
    } else if (widget.kind === "button") {
      element = document.createElement("button");
      element.type = "button";
      element.textContent = widget.label;
      element.addEventListener("click", () => runAction(widget.action));
    } else throw Error("unknown widget");
    root.appendChild(element);
  }
}
document.getElementById("title").textContent = program.name;
render();
</script></body></html>
"#;

/// Rejects malformed or out-of-slice IR instead of executing arbitrary input.
pub fn generate(ir: &Json) -> Result<String> {
    if ir.get("schema").and_then(Json::as_str) != Some(crate::ir_candidate::SCHEMA)
        || ir.get("version").and_then(Json::as_str) != Some(crate::ir_candidate::VERSION)
        || ir.get("coverage").and_then(Json::as_str) != Some("app-scalar-single-screen")
    {
        return fail("E_WEB_IR: unsupported candidate schema/version/coverage");
    }
    let raw = serde_json::to_string(ir).map_err(|e| crate::model::Error(e.to_string()))?;
    // Protect inline scripts from literal </script>, HTML comments and similar input.
    let escaped = raw
        .replace('&', "\\u0026")
        .replace('<', "\\u003c")
        .replace('>', "\\u003e");
    Ok(TEMPLATE.replace("__SEDJAVA_JSON__", &escaped))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{ir_candidate, parser};

    #[test]
    fn web_preview_reads_serializable_ir_without_ast() {
        let ir = ir_candidate::export(
            &parser::parse(include_str!("../../../examples/counter.sdr")).unwrap(),
        )
        .unwrap();
        let serialized = serde_json::to_string(&ir).unwrap();
        let detached: Json = serde_json::from_str(&serialized).unwrap();
        let html = generate(&detached).unwrap();
        assert!(html.contains("function runAction(name)"));
        assert!(html.contains(r#""coverage":"app-scalar-single-screen""#));
        assert!(!html.contains("eval("));
    }

    #[test]
    fn web_preview_rejects_wrong_contract() {
        assert!(generate(&serde_json::json!({"schema":"invalid"})).is_err());
    }
}
