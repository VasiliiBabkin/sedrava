//! Experimental typed errors and contextual scalar Results.
//! Engine faults, policies and runtime budgets are never catchable Results.
use crate::expr;
use crate::model::{fail, validate, Expr, Kind, PureFunction, Result, State, Value};
use std::collections::{BTreeMap, BTreeSet};

pub fn result_type(raw: &str, types: &BTreeMap<String, Kind>) -> Result<Option<Kind>> {
    let Some(body) = raw
        .strip_prefix("Result<")
        .and_then(|s| s.strip_suffix('>'))
    else {
        return Ok(None);
    };
    let Some((success, error)) = body.split_once(", ") else {
        return fail("E_RESULT: expected Result<scalar, ErrorType>");
    };
    let success = match success {
        "int" => Kind::Int,
        "text" => Kind::Text,
        "bool" => Kind::Bool,
        _ => return fail("E_RESULT: only scalar successes are supported"),
    };
    let Some(kind @ Kind::Error { .. }) = types.get(error) else {
        return fail("E_RESULT: expected a declared nominal error family");
    };
    Ok(Some(Kind::Result {
        success: Box::new(success),
        error: Box::new(kind.clone()),
    }))
}

pub fn validate_body(body: &Expr, result: &Kind, types: &BTreeMap<String, Kind>) -> Result<()> {
    if let Kind::Result { success, error } = result {
        verify_expr(body, success, error, result, types)
    } else if expr::infer(body, types)? == *result {
        Ok(())
    } else {
        fail("Pure function return type mismatch")
    }
}

fn verify_expr(
    body: &Expr,
    success: &Kind,
    error: &Kind,
    expected: &Kind,
    types: &BTreeMap<String, Kind>,
) -> Result<()> {
    match body {
        Expr::Conditional(condition, yes, no) => {
            if expr::infer(condition, types)? != Kind::Bool {
                return fail("E_RESULT: conditional requires bool");
            }
            verify_expr(yes, success, error, expected, types)?;
            verify_expr(no, success, error, expected, types)
        }
        Expr::Call { name, args, kwargs } if name == "Ok" && !types.contains_key("Ok") => {
            if args.len() != 1 || !kwargs.is_empty() || expr::infer(&args[0], types)? != *success {
                return fail("E_RESULT: Ok requires exact scalar type");
            }
            Ok(())
        }
        Expr::Call { name, args, kwargs } if name == "Err" && !types.contains_key("Err") => {
            if args.len() != 1 || !kwargs.is_empty() || expr::infer(&args[0], types)? != *error {
                return fail("E_RESULT: Err requires typed nominal error");
            }
            Ok(())
        }
        other if expr::infer(other, types)? == *expected => Ok(()),
        _ => fail("E_RESULT: expression type mismatch"),
    }
}

pub fn evaluate_body(
    body: &Expr,
    result: &Kind,
    values: &State,
    types: &BTreeMap<String, Kind>,
    functions: &BTreeMap<String, PureFunction>,
) -> Result<Value> {
    let Kind::Result { success, error } = result else {
        let value = expr::evaluate_full(body, values, types, functions)?;
        validate(&value, result)?;
        return Ok(value);
    };
    let value = match body {
        Expr::Conditional(condition, yes, no) => {
            let condition = expr::evaluate_full(condition, values, types, functions)?;
            let chosen = if condition == Value::Bool(true) {
                yes
            } else {
                no
            };
            return evaluate_body(chosen, result, values, types, functions);
        }
        Expr::Call { name, args, kwargs } if name == "Ok" && !types.contains_key("Ok") => {
            if args.len() != 1 || !kwargs.is_empty() {
                return fail("E_RESULT: bad Ok call");
            }
            let value = expr::evaluate_full(&args[0], values, types, functions)?;
            validate(&value, success)?;
            Value::Result {
                kind: result.clone(),
                ok: true,
                value: Box::new(value),
            }
        }
        Expr::Call { name, args, kwargs } if name == "Err" && !types.contains_key("Err") => {
            if args.len() != 1 || !kwargs.is_empty() {
                return fail("E_RESULT: bad Err call");
            }
            let value = expr::evaluate_full(&args[0], values, types, functions)?;
            validate(&value, error)?;
            Value::Result {
                kind: result.clone(),
                ok: false,
                value: Box::new(value),
            }
        }
        other => expr::evaluate_full(other, values, types, functions)?,
    };
    validate(&value, result)?;
    Ok(value)
}

pub fn infer_constructor(
    name: &str,
    args: &[Expr],
    kwargs: &[(String, Expr)],
    types: &BTreeMap<String, Kind>,
    infer: &dyn Fn(&Expr) -> Result<Kind>,
) -> Result<Option<Kind>> {
    let Some((family, variant)) = name.split_once('.') else {
        return Ok(None);
    };
    let Some(kind @ Kind::Error { variants, .. }) = types.get(family) else {
        return fail("E_ERROR_TYPE: unknown family");
    };
    let Some((_, schema)) = variants.iter().find(|(key, _)| key == variant) else {
        return fail("E_ERROR_TYPE: unknown variant");
    };
    if !args.is_empty() || kwargs.len() != schema.len() {
        return fail("E_ERROR_TYPE: constructor expects exact named fields");
    }
    for (field, expected) in schema {
        let matches: Vec<_> = kwargs.iter().filter(|(key, _)| key == field).collect();
        if matches.len() != 1 || infer(&matches[0].1)? != *expected {
            return fail("E_ERROR_TYPE: missing, duplicate or ill-typed field");
        }
    }
    Ok(Some(kind.clone()))
}

pub fn construct(
    name: &str,
    args: &[Expr],
    kwargs: &[(String, Expr)],
    types: &BTreeMap<String, Kind>,
    eval: &dyn Fn(&Expr) -> Result<Value>,
) -> Result<Option<Value>> {
    let Some((family, variant)) = name.split_once('.') else {
        return Ok(None);
    };
    let Some(kind @ Kind::Error { variants, .. }) = types.get(family) else {
        return fail("E_ERROR_TYPE: unknown family");
    };
    let Some((_, schema)) = variants.iter().find(|(key, _)| key == variant) else {
        return fail("E_ERROR_TYPE: unknown variant");
    };
    if !args.is_empty() || kwargs.len() != schema.len() {
        return fail("E_ERROR_TYPE: constructor requires exact fields");
    }
    let mut fields = BTreeMap::new();
    for (field, kind) in schema {
        let matches: Vec<_> = kwargs.iter().filter(|(name, _)| name == field).collect();
        if matches.len() != 1 {
            return fail("E_ERROR_TYPE: missing or duplicate field");
        }
        let value = eval(&matches[0].1)?;
        validate(&value, kind)?;
        fields.insert(field.clone(), value);
    }
    Ok(Some(Value::Error {
        kind: kind.clone(),
        variant: variant.into(),
        fields,
    }))
}

pub fn exhaustive(kind: &Kind, arms: &[crate::model::MatchArm]) -> Result<()> {
    use crate::model::MatchPattern;
    let Kind::Result { error, .. } = kind else {
        return fail("E_MATCH: requires typed Result");
    };
    let Kind::Error { open, variants, .. } = error.as_ref() else {
        return fail("E_MATCH: legacy Error match not yet supported");
    };
    let mut has_ok = false;
    let mut fallback = false;
    let mut seen = BTreeSet::new();
    for arm in arms {
        match &arm.pattern {
            MatchPattern::Ok(_) => {
                if has_ok {
                    return fail("E_MATCH: duplicate Ok");
                }
                has_ok = true;
            }
            MatchPattern::Variant { name, .. } => {
                if fallback
                    || !variants.iter().any(|(key, _)| key == name)
                    || !seen.insert(name.clone())
                {
                    return fail("E_MATCH: unknown, duplicate or unreachable variant");
                }
            }
            MatchPattern::Fallback(_) => {
                if fallback || (!*open && seen.len() == variants.len()) {
                    return fail("E_MATCH: duplicate or unreachable Err fallback");
                }
                fallback = true;
            }
        }
    }
    if !has_ok || (*open && !fallback) || (!*open && !fallback && seen.len() != variants.len()) {
        return fail("E_MATCH: non-exhaustive error handling");
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn nominal_scalar_result() {
        let mut types = BTreeMap::new();
        types.insert(
            "Problem".into(),
            Kind::Error {
                name: "Problem".into(),
                id: "entry.Problem".into(),
                open: false,
                variants: vec![("Bad".into(), vec![])],
            },
        );
        assert!(matches!(
            result_type("Result<int, Problem>", &types).unwrap(),
            Some(Kind::Result { .. })
        ));
        for bad in [
            "Result<list, Problem>",
            "Result<int, Missing>",
            "Result<int, int>",
            "Result<int,Problem>",
        ] {
            assert!(result_type(bad, &types).is_err(), "{bad}");
        }
    }

    #[test]
    fn typed_result_and_match_atomic_state() {
        let source = r#"app "A"
error closed Fail id "demo.Fail":
    Overflow:
        left: int
fn checked(x: int) -> Result<int, Fail> effects pure = Ok(x) if x < 100 else Err(Fail.Overflow(left=x))
state n = 0
action success:
    match checked(3):
        Ok(value):
            n = value
        Err(Overflow { left }):
            n = left
action expected:
    match checked(100):
        Ok(value):
            n = value
        Err(Overflow { left }):
            n = left
action failed:
    n = 7
    match checked(100):
        Ok(value):
            n = value
        Err(Overflow { left }):
            n = left + 2147483647
test good: success -> n == 3
test bad: expected -> n == 100
"#;
        let program = crate::parser::parse(source).unwrap();
        assert_eq!(crate::runtime::run_tests(&program).unwrap(), 2);
        let output = crate::runtime::run_actions(&program, &["expected".into()]).unwrap();
        assert_eq!(output.get("n"), Some(&Value::Int(100)));
        assert!(crate::runtime::transition(&program, &program.states, "failed").is_err());
        assert_eq!(program.states.get("n"), Some(&Value::Int(0)));
    }

    #[test]
    fn open_requires_default_and_closed_rejects_unreachable_default() {
        let source = r#"app "A"
error open F:
    One:
fn checked(x: int) -> Result<int, F> = Err(F.One())
state n = 0
action t:
    match checked(0):
        Ok(v):
            n = v
        Err(One {}):
            n = 1
"#;
        assert!(crate::parser::parse(source).is_err());
        let valid = source.replace(
            "Err(One {}):\n            n = 1",
            "Err(One {}):\n            n = 1\n        Err(error):\n            n = 2",
        );
        let p = crate::parser::parse(&valid).unwrap();
        assert_eq!(
            crate::runtime::run_actions(&p, &["t".into()]).unwrap()["n"],
            Value::Int(1)
        );
        let closed = valid.replace("error open F:", "error closed F:");
        assert!(crate::parser::parse(&closed).is_err());
    }

    #[test]
    fn field_payload_is_exact_and_error_ids_nominal() {
        let baseline = r#"app "A"
error closed F id "example.F":
    First:
        value: text
fn failure(x: text) -> Result<text, F> = Err(F.First(value=x))
state title = ""
action choose:
    match failure("safe"):
        Ok(value):
            title = value
        Err(First { value }):
            title = error_id(F.First(value=value))
"#;
        let parsed = crate::parser::parse(baseline).unwrap();
        let result = crate::runtime::run_actions(&parsed, &["choose".into()]).unwrap();
        assert_eq!(result["title"], Value::Text("example.F.First".into()));
        for (a, b) in [
            ("F.First(value=x)", "F.First(value=1)"),
            ("F.First(value=x)", "F.First()"),
            ("F.First(value=x)", "F.First(value=x, value=x)"),
            (
                "error closed F id \"example.F\"",
                "error closed int id \"example.F\"",
            ),
        ] {
            assert!(crate::parser::parse(&baseline.replace(a, b)).is_err());
        }
    }
}
