//! IR 1.0 candidate: explicitly bounded app-scalar slice, not a stable ABI.
//! Unlike the legacy debug IR, these nodes have explicit stable field names.
use crate::model::{fail, Binary, Expr, Kind, Program, Result, Stmt, Unary, Value, Widget};
use serde_json::{json, Value as Json};

pub const SCHEMA: &str = "sedrava.ir.app";
pub const VERSION: &str = "1.0-candidate.1";

fn unsupported(what: &str) -> crate::model::Error {
    crate::model::Error(format!("E_IR_CANDIDATE_UNSUPPORTED: {what}"))
}

fn scalar_type(kind: &Kind) -> Result<&'static str> {
    match kind {
        Kind::Int => Ok("int"),
        Kind::Bool => Ok("bool"),
        Kind::Text => Ok("text"),
        _ => Err(unsupported("non-scalar types")),
    }
}

fn scalar_value(value: &Value) -> Result<Json> {
    match value {
        Value::Int(v) => Ok(json!(v)),
        Value::Bool(v) => Ok(json!(v)),
        Value::Text(v) => Ok(json!(v)),
        _ => Err(unsupported("non-scalar initial state")),
    }
}

fn unary_name(op: &Unary) -> &'static str {
    match op {
        Unary::Neg => "neg",
        Unary::Not => "not",
    }
}

fn binary_name(op: &Binary) -> &'static str {
    match op {
        Binary::Add => "add",
        Binary::Sub => "sub",
        Binary::Mul => "mul",
        Binary::Eq => "eq",
        Binary::Ne => "ne",
        Binary::Lt => "lt",
        Binary::Le => "le",
        Binary::Gt => "gt",
        Binary::Ge => "ge",
        Binary::And => "and",
        Binary::Or => "or",
    }
}

fn expression(expr: &Expr) -> Result<Json> {
    match expr {
        Expr::Int(v) => {
            let i = i32::try_from(*v).map_err(|_| unsupported("integer literal outside int32"))?;
            Ok(json!({"node":"literal","type":"int","value":i}))
        }
        Expr::Bool(v) => Ok(json!({"node":"literal","type":"bool","value":v})),
        Expr::Text(v) => Ok(json!({"node":"literal","type":"text","value":v})),
        Expr::Ident(name) => Ok(json!({"node":"reference","name":name})),
        Expr::Unary(op, arg) => Ok(json!({
            "node":"unary", "operator":unary_name(op), "argument":expression(arg)?
        })),
        Expr::Binary(op, left, right) => Ok(json!({
            "node":"binary", "operator":binary_name(op),
            "left":expression(left)?, "right":expression(right)?
        })),
        Expr::Conditional(test, yes, no) => Ok(json!({
            "node":"conditional", "test":expression(test)?,
            "then":expression(yes)?, "else":expression(no)?
        })),
        Expr::Call { .. } | Expr::Attr(..) => Err(unsupported("calls and attribute expressions")),
    }
}

/// Prepare a deterministic candidate IR for a deliberately small target slice.
/// Every non-representable feature is rejected; nothing is silently dropped.
pub fn export(program: &Program) -> Result<Json> {
    if !program.derives.is_empty()
        || !program.functions.is_empty()
        || !program.persistent.is_empty()
        || !program.navigation.is_empty()
        || program.has_navigation
    {
        return Err(unsupported("derive/function/persist/navigation"));
    }
    if program.screens.len() != 1 {
        return Err(unsupported("requires exactly one screen"));
    }
    let screen = program
        .screens
        .values()
        .next()
        .ok_or_else(|| unsupported("missing screen"))?;
    if screen.guard.is_some() || screen.requires_navigation {
        return Err(unsupported("screen guards or navigation"));
    }
    let mut state = Vec::new();
    for name in &program.state_order {
        let kind = program
            .types
            .get(name)
            .ok_or_else(|| unsupported("missing state type"))?;
        let value = program
            .states
            .get(name)
            .ok_or_else(|| unsupported("missing initial value"))?;
        state.push(json!({
            "name":name, "type":scalar_type(kind)?, "initial":scalar_value(value)?
        }));
    }
    if state.len() != program.states.len() {
        return fail("E_IR_CANDIDATE: inconsistent state order");
    }
    let mut actions = Vec::new();
    for (name, block) in &program.actions {
        let mut statements = Vec::new();
        for stmt in block {
            match stmt {
                Stmt::Assign(target, expr) => {
                    statements
                        .push(json!({"op":"set","target":target,"expression":expression(expr)?}));
                }
                Stmt::Require(expr) => {
                    statements.push(json!({"op":"require","expression":expression(expr)?}));
                }
                _ => return Err(unsupported("let, branch or match statements")),
            }
        }
        actions.push(json!({"name":name,"statements":statements}));
    }
    let mut widgets = Vec::new();
    for widget in &screen.widgets {
        match widget {
            Widget::Text(text) => widgets.push(json!({"kind":"text","text":text})),
            Widget::Value(name) => widgets.push(json!({"kind":"value","name":name})),
            Widget::Button { label, action } => {
                widgets.push(json!({"kind":"button","label":label,"action":action}));
            }
            _ => return Err(unsupported("advanced screen widgets")),
        }
    }
    let rules = program
        .rules
        .iter()
        .map(expression)
        .collect::<Result<Vec<_>>>()?;
    Ok(json!({
        "schema":SCHEMA,
        "version":VERSION,
        "coverage":"app-scalar-single-screen",
        "program":{
            "name":program.name,
            "state":state,
            "actions":actions,
            "rules":rules,
            "screen":{"name":screen.name,"widgets":widgets}
        },
        "diagnostics":{
            "coverage":"declarations-only",
            "declarations":program.declaration_spans
        }
    }))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::parser::parse;

    const COUNTER: &str = include_str!("../../../examples/counter.sdr");

    #[test]
    fn candidate_is_deterministic_and_explicitly_typed() {
        let p = parse(COUNTER).unwrap();
        let a = export(&p).unwrap();
        assert_eq!(a, export(&p).unwrap());
        assert_eq!(a["schema"], SCHEMA);
        assert_eq!(a["version"], VERSION);
        assert_eq!(a["program"]["state"][0]["type"], "int");
        assert_eq!(a["program"]["state"][0]["name"], "count");
        assert_eq!(a["diagnostics"]["coverage"], "declarations-only");
        assert_eq!(a["program"]["actions"][1]["name"], "increment");
    }

    #[test]
    fn unsupported_constructs_fail_closed() {
        let p = parse(include_str!(
            "../../../examples/task_manager_navigation.sdr"
        ))
        .unwrap();
        assert!(export(&p)
            .unwrap_err()
            .to_string()
            .contains("E_IR_CANDIDATE_UNSUPPORTED"));
    }
}
