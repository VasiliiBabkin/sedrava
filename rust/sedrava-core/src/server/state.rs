//! A2 checked scalar server-state DSL. No arbitrary function calls or eval.
use super::{identifier, ScalarType, MAX_SCALAR_TEXT};
use crate::model::{fail, Error, Result};
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;

pub type Values = BTreeMap<String, Value>;

#[derive(Clone, Debug)]
pub struct StateDef {
    pub kind: ScalarType,
    pub initial: Value,
}

#[derive(Clone, Debug, PartialEq)]
pub enum Expr {
    Literal(Value),
    Request(String),
    State(String),
    /// Read-only, explicitly named SedravaSQL key/value lookup (A6 only).
    DbGet {
        namespace: String,
        key: String,
        slot: String,
    },
    /// The current int32 revision of a managed SedravaSQL row (A7).
    DbRevision {
        namespace: String,
        key: String,
        slot: String,
    },
    Add(Box<Expr>, Box<Expr>),
}

#[derive(Clone, Copy, Debug)]
pub enum Comparison {
    Equal,
    NotEqual,
    Less,
    LessEqual,
    Greater,
    GreaterEqual,
}

#[derive(Clone, Debug)]
pub enum Step {
    Set {
        name: String,
        value: Expr,
    },
    Require {
        lhs: Expr,
        op: Comparison,
        rhs: Expr,
    },
}

#[derive(Clone, Debug)]
pub enum EvalError {
    Overflow,
    Invalid,
    GuardRejected,
}

pub fn scalar_type(value: &Value) -> Option<ScalarType> {
    match value {
        Value::Bool(_) => Some(ScalarType::Bool),
        Value::String(s)
            if s.chars().count() <= MAX_SCALAR_TEXT && !s.chars().any(char::is_control) =>
        {
            Some(ScalarType::Text)
        }
        Value::Number(n) if n.as_i64().is_some_and(|v| i32::try_from(v).is_ok()) => {
            Some(ScalarType::Int)
        }
        _ => None,
    }
}

pub fn parse_state(line: &str) -> Result<(String, StateDef)> {
    let (decl, value) = line
        .split_once(" = ")
        .ok_or_else(|| Error("E_SERVER_STATE: expected state name: type = value".into()))?;
    let (name, kind) = decl
        .split_once(": ")
        .ok_or_else(|| Error("E_SERVER_STATE: expected state name: type".into()))?;
    if !identifier(name) {
        return fail("E_SERVER_STATE: invalid state name");
    }
    let kind = match kind {
        "int" => ScalarType::Int,
        "bool" => ScalarType::Bool,
        "text" => ScalarType::Text,
        _ => return fail("E_SERVER_STATE: only int, bool, text allowed"),
    };
    let value: Value = serde_json::from_str(value)
        .map_err(|_| Error("E_SERVER_STATE: expected JSON scalar initial value".into()))?;
    if scalar_type(&value) != Some(kind) {
        return fail("E_SERVER_STATE: initial value does not match declared type");
    }
    Ok((
        name.into(),
        StateDef {
            kind,
            initial: value,
        },
    ))
}

/// Detect delimiter outside quoted JSON strings, requiring exactly one
/// occurrence. No recursion, function calls, precedence or nested expressions.
fn one_operator<'a>(source: &'a str, token: &str) -> Result<Option<(&'a str, &'a str)>> {
    let mut quoted = false;
    let mut escaped = false;
    let mut found = None;
    for (pos, character) in source.char_indices() {
        if quoted {
            if escaped {
                escaped = false
            } else if character == '\\' {
                escaped = true
            } else if character == '"' {
                quoted = false
            }
        } else if character == '"' {
            quoted = true;
        } else if source[pos..].starts_with(token) {
            if found.is_some() {
                return fail("E_SERVER_EXPR: multiple operators not allowed");
            }
            found = Some(pos);
        }
    }
    if quoted {
        return fail("E_SERVER_EXPR: unclosed string");
    }
    Ok(found.map(|pos| {
        let a = source[..pos].trim();
        let b = source[pos + token.len()..].trim();
        (a, b)
    }))
}

pub fn atom(
    raw: &str,
    request: &BTreeMap<String, ScalarType>,
    states: &BTreeMap<String, StateDef>,
) -> Result<(Expr, ScalarType)> {
    let raw = raw.trim();
    // Static and checked DB path only: no request-provided SQL identifiers.
    for (prefix, revision) in [("db_get(", false), ("db_revision(", true)] {
        if let Some(argument) = raw.strip_prefix(prefix).and_then(|r| r.strip_suffix(')')) {
            let path: String = serde_json::from_str(argument)
                .map_err(|_| Error("E_SERVER_DB: expected quoted namespace/key".into()))?;
            let (namespace, key) = path
                .split_once('/')
                .ok_or_else(|| Error("E_SERVER_DB: expected namespace/key".into()))?;
            let id_ok = |v: &str| {
                !v.is_empty()
                    && v.len() <= 128
                    && v.bytes()
                        .all(|b| b.is_ascii_alphanumeric() || matches!(b, b'.' | b'-' | b'_'))
            };
            if !id_ok(namespace) || !id_ok(key) || namespace.starts_with("sedrava_native") {
                return fail("E_SERVER_DB: invalid or reserved namespace/key");
            }
            // Two different slots share a single request-local row read.
            let slot = format!(
                "_sql_{}_{:x}",
                if revision { "rev" } else { "text" },
                Sha256::digest(path.as_bytes())
            );
            let expression = if revision {
                Expr::DbRevision {
                    namespace: namespace.into(),
                    key: key.into(),
                    slot,
                }
            } else {
                Expr::DbGet {
                    namespace: namespace.into(),
                    key: key.into(),
                    slot,
                }
            };
            return Ok((
                expression,
                if revision {
                    ScalarType::Int
                } else {
                    ScalarType::Text
                },
            ));
        }
    }
    if let Some(name) = raw.strip_prefix("request.") {
        let Some(&kind) = request.get(name) else {
            return fail("E_SERVER_EXPR: unknown request field");
        };
        return Ok((Expr::Request(name.into()), kind));
    }
    if let Some(name) = raw.strip_prefix("state.") {
        let Some(def) = states.get(name) else {
            return fail("E_SERVER_EXPR: unknown state field");
        };
        return Ok((Expr::State(name.into()), def.kind));
    }
    let value: Value = serde_json::from_str(raw).map_err(|_| {
        Error("E_SERVER_EXPR: expression must be scalar, request.X or state.X".into())
    })?;
    let Some(kind) = scalar_type(&value) else {
        return fail("E_SERVER_EXPR: scalar must be bounded int, bool or text");
    };
    Ok((Expr::Literal(value), kind))
}

pub fn expression(
    raw: &str,
    request: &BTreeMap<String, ScalarType>,
    states: &BTreeMap<String, StateDef>,
) -> Result<(Expr, ScalarType)> {
    if let Some((a, b)) = one_operator(raw, " + ")? {
        if a.is_empty() || b.is_empty() {
            return fail("E_SERVER_EXPR: missing side of addition");
        }
        let (a, ak) = atom(a, request, states)?;
        let (b, bk) = atom(b, request, states)?;
        if ak != ScalarType::Int || bk != ScalarType::Int {
            return fail("E_SERVER_EXPR: checked addition requires two int32 values");
        }
        return Ok((Expr::Add(Box::new(a), Box::new(b)), ScalarType::Int));
    }
    atom(raw, request, states)
}

pub fn parse_step(
    text: &str,
    request: &BTreeMap<String, ScalarType>,
    states: &BTreeMap<String, StateDef>,
    is_get: bool,
) -> Result<Step> {
    if text.contains("db_get(") || text.contains("db_revision(") {
        return fail("E_SERVER_DB: database expressions are GET-response-only");
    }
    if let Some(raw) = text.strip_prefix("set ") {
        if is_get {
            return fail("E_SERVER_STEP: GET cannot change state");
        }
        let (name, expr) = raw
            .split_once(" = ")
            .ok_or_else(|| Error("E_SERVER_STEP: expected set NAME = expression".into()))?;
        if !identifier(name) {
            return fail("E_SERVER_STEP: invalid target state name");
        }
        let Some(def) = states.get(name) else {
            return fail("E_SERVER_STEP: unknown state");
        };
        let (value, kind) = expression(expr, request, states)?;
        if kind != def.kind {
            return fail("E_SERVER_STEP: assignment type mismatch");
        }
        return Ok(Step::Set {
            name: name.into(),
            value,
        });
    }
    let Some(raw) = text.strip_prefix("require ") else {
        return fail("E_SERVER_STEP: expected require or set statement");
    };
    for (token, op) in [
        (" == ", Comparison::Equal),
        (" != ", Comparison::NotEqual),
        (" <= ", Comparison::LessEqual),
        (" >= ", Comparison::GreaterEqual),
        (" < ", Comparison::Less),
        (" > ", Comparison::Greater),
    ] {
        if let Some((left, right)) = one_operator(raw, token)? {
            let (lhs, lk) = expression(left, request, states)?;
            let (rhs, rk) = expression(right, request, states)?;
            if lk != rk
                || (!matches!(op, Comparison::Equal | Comparison::NotEqual)
                    && lk != ScalarType::Int)
            {
                return fail("E_SERVER_STEP: incompatible guard operand types");
            }
            return Ok(Step::Require { lhs, op, rhs });
        }
    }
    fail("E_SERVER_STEP: expected typed comparison")
}

pub fn eval(
    expr: &Expr,
    request: &Values,
    state: &Values,
) -> std::result::Result<Value, EvalError> {
    match expr {
        Expr::Literal(value) => Ok(value.clone()),
        Expr::Request(key) => request.get(key).cloned().ok_or(EvalError::Invalid),
        Expr::State(key) => state.get(key).cloned().ok_or(EvalError::Invalid),
        Expr::DbGet { slot, .. } | Expr::DbRevision { slot, .. } => {
            state.get(slot).cloned().ok_or(EvalError::Invalid)
        }
        Expr::Add(a, b) => {
            let a = eval(a, request, state)?;
            let b = eval(b, request, state)?;
            let (Some(a), Some(b)) = (a.as_i64(), b.as_i64()) else {
                return Err(EvalError::Invalid);
            };
            let sum = a
                .checked_add(b)
                .and_then(|n| i32::try_from(n).ok())
                .ok_or(EvalError::Overflow)?;
            Ok(Value::from(sum))
        }
    }
}

pub fn run(
    steps: &[Step],
    request: &Values,
    state: &mut Values,
) -> std::result::Result<(), EvalError> {
    for step in steps {
        match step {
            Step::Set { name, value } => {
                let evaluated = eval(value, request, state)?;
                state.insert(name.clone(), evaluated);
            }
            Step::Require { lhs, op, rhs } => {
                let lhs = eval(lhs, request, state)?;
                let rhs = eval(rhs, request, state)?;
                let good = match op {
                    Comparison::Equal => lhs == rhs,
                    Comparison::NotEqual => lhs != rhs,
                    Comparison::Less => lhs.as_i64().zip(rhs.as_i64()).is_some_and(|(a, b)| a < b),
                    Comparison::LessEqual => {
                        lhs.as_i64().zip(rhs.as_i64()).is_some_and(|(a, b)| a <= b)
                    }
                    Comparison::Greater => {
                        lhs.as_i64().zip(rhs.as_i64()).is_some_and(|(a, b)| a > b)
                    }
                    Comparison::GreaterEqual => {
                        lhs.as_i64().zip(rhs.as_i64()).is_some_and(|(a, b)| a >= b)
                    }
                };
                if !good {
                    return Err(EvalError::GuardRejected);
                }
            }
        }
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn a7_db_revision_is_typed_and_literal_only() {
        let request = BTreeMap::new();
        let state = BTreeMap::new();
        let (value, kind) =
            expression(r#"db_revision("public_notes/welcome")"#, &request, &state).unwrap();
        assert_eq!(kind, ScalarType::Int);
        assert!(matches!(
            value,
            Expr::DbRevision { namespace, key, .. }
              if namespace == "public_notes" && key == "welcome"
        ));
        assert_eq!(
            expression(r#"db_get("public_notes/welcome")"#, &request, &state)
                .unwrap()
                .1,
            ScalarType::Text
        );
        for invalid in [
            r#"db_revision("sedrava_native_a6/internal")"#,
            r#"db_revision("public_notes/../../wrong")"#,
            r#"db_revision(request.path)"#,
            r#"db_revision("public_notes/")"#,
        ] {
            assert!(expression(invalid, &request, &state).is_err(), "{invalid}");
        }
        assert!(parse_step(
            r#"require db_revision("public_notes/welcome") == 1"#,
            &request,
            &state,
            false
        )
        .is_err());
    }
    #[test]
    fn bounded_int_and_quoted_plus() {
        let mut state = BTreeMap::new();
        state.insert(
            "n".into(),
            StateDef {
                kind: ScalarType::Int,
                initial: Value::from(1),
            },
        );
        let request = BTreeMap::from([("amount".into(), ScalarType::Int)]);
        let (ex, k) = expression("state.n + request.amount", &request, &state).unwrap();
        assert_eq!(k, ScalarType::Int);
        assert_eq!(
            eval(
                &ex,
                &BTreeMap::from([("amount".into(), Value::from(2))]),
                &BTreeMap::from([("n".into(), Value::from(1))])
            )
            .unwrap(),
            Value::from(3)
        );
        assert!(expression("state.n + \"text\"", &request, &state).is_err());
        assert!(expression("state.n + request.amount + 1", &request, &state).is_err());
        assert!(expression("request.unknown", &request, &state).is_err());
        assert_eq!(
            expression("\"a + b\"", &request, &state).unwrap().1,
            ScalarType::Text
        );
    }
}
