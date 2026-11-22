//! Portable record and bounded-list algebra with stable identities.
//! This module never consults the host, clock or filesystem.

use crate::model::{
    check_i32, fail, validate, Error, Expr, Kind, ListItem, PureFunction, Result, State, Value,
};
use std::collections::BTreeMap;

fn require_arity(args: &[Expr], n: usize) -> Result<()> {
    if args.len() != n {
        fail("Collection operation argument count mismatch")
    } else {
        Ok(())
    }
}

fn scalar_field_kind(kind: &Kind, field: &str) -> Result<Kind> {
    if field == "id" {
        return Ok(Kind::Int);
    }
    let Kind::Record { fields, .. } = kind else {
        return fail("Record required");
    };
    fields
        .iter()
        .find(|(name, _)| name == field)
        .map(|(_, k)| k.clone())
        .ok_or_else(|| Error(format!("Unknown record field: {field}")))
}

/// Infer and validate record constructors and collection operations.
pub fn infer_call(
    name: &str,
    args: &[Expr],
    kwargs: &[(String, Expr)],
    types: &BTreeMap<String, Kind>,
    infer: &dyn Fn(&Expr) -> Result<Kind>,
) -> Result<Kind> {
    if matches!(name, "result_ok" | "result_or") && !types.contains_key(name) {
        if !kwargs.is_empty() || args.len() != if name == "result_ok" { 1 } else { 2 } {
            return fail("E_RESULT: result intrinsic arity");
        }
        let Kind::Result { success, .. } = infer(&args[0])? else {
            return fail("E_RESULT: expected typed Result");
        };
        if name == "result_or" && infer(&args[1])? != *success {
            return fail("E_RESULT: fallback must have Result success type");
        }
        return Ok(if name == "result_ok" {
            Kind::Bool
        } else {
            *success
        });
    }
    if name == "error_id" && !types.contains_key("error_id") {
        if !kwargs.is_empty() || args.len() != 1 || !matches!(infer(&args[0])?, Kind::Error { .. })
        {
            return fail("E_RESULT: error_id requires a typed error value");
        }
        return Ok(Kind::Text);
    }
    if let Some(kind @ Kind::Record { fields, .. }) = types.get(name) {
        if !args.is_empty() || kwargs.len() != fields.len() {
            return fail("Record requires exact named fields");
        }
        for (field, expected) in fields {
            if kwargs.iter().filter(|(k, _)| k == field).count() != 1 {
                return fail("Duplicate or missing record field");
            }
            let (_, expr) = kwargs.iter().find(|(k, _)| k == field).unwrap();
            if infer(expr)? != *expected {
                return fail("Record field type mismatch");
            }
        }
        return Ok(kind.clone());
    }
    if let Some(Kind::Function { parameters, result }) = types.get(name) {
        if !kwargs.is_empty() || parameters.len() != args.len() {
            return fail("Pure function argument count mismatch");
        }
        for (expr, expected) in args.iter().zip(parameters) {
            if &infer(expr)? != expected {
                return fail("Pure function argument type mismatch");
            }
        }
        return Ok((**result).clone());
    }
    if let Some((params, return_type)) = crate::stdlib::signature(name) {
        if !kwargs.is_empty() || args.len() != params.len() {
            return fail("Builtin argument count mismatch");
        }
        for (expr, expected) in args.iter().zip(params.iter()) {
            if &infer(expr)? != expected {
                return fail("Builtin argument type mismatch");
            }
        }
        return Ok(return_type);
    }
    if !kwargs.is_empty() {
        return fail("Collection operations reject named arguments");
    }
    match name {
        "count" | "next_id" | "append" | "update" | "remove" | "get" | "has" => {
            require_arity(
                args,
                match name {
                    "count" | "next_id" => 1,
                    "append" | "remove" | "get" | "has" => 2,
                    "update" => 3,
                    _ => unreachable!(),
                },
            )?;
            let list = infer(&args[0])?;
            let Kind::List { record, .. } = &list else {
                return fail("Collection required");
            };
            if matches!(name, "get" | "has" | "remove" | "update") && infer(&args[1])? != Kind::Int
            {
                return fail("Identity must be int");
            }
            if name == "append" && infer(&args[1])? != **record {
                return fail("Wrong record type for append");
            }
            if name == "update" && infer(&args[2])? != **record {
                return fail("Wrong record type for update");
            }
            Ok(match name {
                "count" | "next_id" => Kind::Int,
                "get" => (**record).clone(),
                "has" => Kind::Bool,
                _ => list,
            })
        }
        "filter" | "map" | "find" | "any" | "all" | "sort" | "sum" => {
            if args.len() < 2 {
                return fail("Collection query requires selector");
            }
            let list = infer(&args[0])?;
            let Kind::List { record, capacity } = &list else {
                return fail("Collection query requires bounded list");
            };
            let selection_type = if let Expr::Ident(selector) = &args[1] {
                let Some(Kind::Function { parameters, result }) = types.get(selector) else {
                    return fail("Query selector must name a pure function");
                };
                if parameters.first() != Some(record.as_ref()) || parameters.len() != args.len() - 1
                {
                    return fail("Query function parameter count or record type mismatch");
                }
                for (arg, expected) in args.iter().skip(2).zip(parameters.iter().skip(1)) {
                    if &infer(arg)? != expected {
                        return fail("Query function extra argument type mismatch");
                    }
                }
                (**result).clone()
            } else if let Expr::Text(field) = &args[1] {
                if name == "map" {
                    return fail("Map requires a record-transforming function");
                }
                let selected = scalar_field_kind(record, field)?;
                let n = if matches!(name, "filter" | "find" | "any" | "all") {
                    3
                } else {
                    2
                };
                require_arity(args, n)?;
                if n == 3 && infer(&args[2])? != selected {
                    return fail("Query field/value type mismatch");
                }
                if n == 3 {
                    Kind::Bool
                } else {
                    selected
                }
            } else {
                return fail("Query selector must be field literal or pure function");
            };
            if matches!(name, "filter" | "find" | "any" | "all") && selection_type != Kind::Bool {
                return fail("Query predicate must return bool");
            }
            if name == "sum" && selection_type != Kind::Int {
                return fail("Sum selector must return int");
            }
            if name == "sort" && !matches!(selection_type, Kind::Int | Kind::Bool | Kind::Text) {
                return fail("Sort selector must be scalar");
            }
            if name == "map" && !matches!(selection_type, Kind::Record { .. }) {
                return fail("Map requires record-returning function");
            }
            Ok(match name {
                "any" | "all" => Kind::Bool,
                "sum" | "find" => Kind::Int,
                "map" => Kind::List {
                    record: Box::new(selection_type),
                    capacity: *capacity,
                },
                _ => list,
            })
        }
        _ => fail(format!("Unknown operation: {name}")),
    }
}

fn get_list(value: &Value) -> Result<(&Kind, &Vec<ListItem>, i32)> {
    if let Value::List {
        kind,
        items,
        next_id,
    } = value
    {
        Ok((kind, items, *next_id))
    } else {
        fail("Collection required")
    }
}
fn get_id(value: &Value) -> Result<i32> {
    if let Value::Int(v) = value {
        Ok(*v)
    } else {
        fail("Identity must be int")
    }
}
fn selected_field<'a>(row: &'a ListItem, field: &str) -> Result<Value> {
    if field == "id" {
        return Ok(Value::Int(row.id));
    }
    if let Value::Record { fields, .. } = &row.record {
        fields
            .get(field)
            .cloned()
            .ok_or_else(|| Error("Unknown record field".into()))
    } else {
        fail("List rows must be records")
    }
}
fn sort_order(a: &Value, b: &Value) -> Result<std::cmp::Ordering> {
    match (a, b) {
        (Value::Int(a), Value::Int(b)) => Ok(a.cmp(b)),
        (Value::Bool(a), Value::Bool(b)) => Ok(a.cmp(b)),
        (Value::Text(a), Value::Text(b)) => Ok(a.cmp(b)),
        _ => fail("Sort keys must have identical scalar types"),
    }
}

pub fn evaluate_call(
    name: &str,
    args: &[Expr],
    kwargs: &[(String, Expr)],
    types: &BTreeMap<String, Kind>,
    functions: &BTreeMap<String, PureFunction>,
    eval: &dyn Fn(&Expr) -> Result<Value>,
) -> Result<Value> {
    if matches!(name, "result_ok" | "result_or") && !types.contains_key(name) {
        if !kwargs.is_empty() || args.len() != if name == "result_ok" { 1 } else { 2 } {
            return fail("E_RESULT: invalid result intrinsic call");
        }
        let Value::Result { ok, value, .. } = eval(&args[0])? else {
            return fail("E_RESULT: result intrinsic requires typed Result");
        };
        if name == "result_ok" {
            return Ok(Value::Bool(ok));
        }
        let fallback = eval(&args[1])?;
        return Ok(if ok { *value } else { fallback });
    }
    if name == "error_id" && !types.contains_key("error_id") {
        if !kwargs.is_empty() || args.len() != 1 {
            return fail("E_RESULT: invalid error_id arguments");
        }
        let Value::Error {
            kind: Kind::Error { id, .. },
            variant,
            ..
        } = eval(&args[0])?
        else {
            return fail("E_RESULT: error_id needs user error");
        };
        return Ok(Value::Text(format!("{id}.{variant}")));
    }
    if let Some(kind @ Kind::Record { fields, .. }) = types.get(name) {
        if kwargs.len() != fields.len() || !args.is_empty() {
            return fail("Invalid record constructor");
        }
        let mut values = BTreeMap::new();
        for (field, expected) in fields {
            let Some((_, expression)) = kwargs.iter().find(|(k, _)| k == field) else {
                return fail("Missing record field");
            };
            let value = eval(expression)?;
            validate(&value, expected)?;
            values.insert(field.clone(), value);
        }
        return Ok(Value::Record {
            kind: kind.clone(),
            fields: values,
        });
    }
    if !kwargs.is_empty() {
        return fail("Unexpected named collection arguments");
    }
    if matches!(
        name,
        "filter" | "map" | "find" | "any" | "all" | "sort" | "sum"
    ) {
        if let Some(Expr::Ident(selector)) = args.get(1) {
            if let Some(function) = functions.get(selector) {
                let base = eval(&args[0])?;
                let (kind, rows, next_id) = get_list(&base)?;
                let extra: Vec<Value> = args.iter().skip(2).map(eval).collect::<Result<_>>()?;
                if function.parameters.len() != extra.len() + 1 {
                    return fail("Query function argument mismatch");
                }
                let mut selections = Vec::with_capacity(rows.len());
                for row in rows {
                    let mut environment = State::new();
                    environment.insert(function.parameters[0].0.clone(), row.record.clone());
                    for ((key, expected), value) in
                        function.parameters.iter().skip(1).zip(extra.iter())
                    {
                        validate(value, expected)?;
                        environment.insert(key.clone(), value.clone());
                    }
                    let selected =
                        crate::expr::evaluate_full(&function.body, &environment, types, functions)?;
                    validate(&selected, &function.result)?;
                    // Python any/all/find evaluate only as far as the answer requires.
                    // Evaluating later records can fail, so this is a semantic guarantee.
                    if name == "find" && selected == Value::Bool(true) {
                        return Ok(Value::Int(row.id));
                    }
                    if name == "any" && selected == Value::Bool(true) {
                        return Ok(Value::Bool(true));
                    }
                    if name == "all" && selected == Value::Bool(false) {
                        return Ok(Value::Bool(false));
                    }
                    selections.push(selected);
                }
                return match name {
                    "find" => Ok(Value::Int(0)),
                    "any" => Ok(Value::Bool(false)),
                    "all" => Ok(Value::Bool(true)),
                    "sum" => {
                        let mut n = 0_i32;
                        for value in selections {
                            if let Value::Int(x) = value {
                                n = n
                                    .checked_add(x)
                                    .ok_or_else(|| Error("Integer overflow".into()))?;
                            } else {
                                return fail("Sum requires int function");
                            }
                        }
                        Ok(Value::Int(n))
                    }
                    "filter" => Ok(Value::List {
                        kind: kind.clone(),
                        next_id,
                        items: rows
                            .iter()
                            .zip(&selections)
                            .filter(|(_, v)| **v == Value::Bool(true))
                            .map(|(row, _)| row.clone())
                            .collect(),
                    }),
                    "map" => {
                        let Kind::List { capacity, .. } = kind else {
                            return fail("List required");
                        };
                        let mapped: Vec<ListItem> = rows
                            .iter()
                            .zip(selections)
                            .map(|(row, selected)| ListItem {
                                id: row.id,
                                record: selected,
                            })
                            .collect();
                        Ok(Value::List {
                            kind: Kind::List {
                                record: Box::new(function.result.clone()),
                                capacity: *capacity,
                            },
                            items: mapped,
                            next_id,
                        })
                    }
                    "sort" => {
                        let mut keyed: Vec<(ListItem, Value)> =
                            rows.iter().cloned().zip(selections).collect();
                        keyed.sort_by(|a, b| {
                            sort_order(&a.1, &b.1).unwrap_or(std::cmp::Ordering::Equal)
                        });
                        Ok(Value::List {
                            kind: kind.clone(),
                            items: keyed.into_iter().map(|(row, _)| row).collect(),
                            next_id,
                        })
                    }
                    _ => fail("Unknown function selector query"),
                };
            }
        }
    }
    let evaluated: Vec<Value> = args.iter().map(eval).collect::<Result<_>>()?;
    if crate::stdlib::signature(name).is_some() {
        return crate::stdlib::apply(name, &evaluated);
    }
    let Some(first) = evaluated.first() else {
        return fail("Collection argument missing");
    };
    let (kind, rows, next_id) = get_list(first)?;
    match name {
        "count" => Ok(Value::Int(check_i32(rows.len() as i64)?)),
        "next_id" => Ok(Value::Int(next_id)),
        "append" => {
            let Kind::List { capacity, record } = kind else {
                return fail("Collection expected");
            };
            if rows.len() >= *capacity {
                return fail("Collection capacity exceeded");
            }
            if next_id == i32::MAX {
                return fail("Identity exhausted");
            }
            let v = evaluated
                .get(1)
                .ok_or_else(|| Error("Record argument missing".into()))?;
            validate(v, record)?;
            let mut new = rows.clone();
            new.push(ListItem {
                id: next_id,
                record: v.clone(),
            });
            Ok(Value::List {
                kind: kind.clone(),
                items: new,
                next_id: next_id + 1,
            })
        }
        "has" | "get" | "update" | "remove" => {
            let id = get_id(
                evaluated
                    .get(1)
                    .ok_or_else(|| Error("Identity missing".into()))?,
            )?;
            let match_row = rows.iter().find(|r| r.id == id);
            if name == "has" {
                return Ok(Value::Bool(match_row.is_some()));
            }
            let row = match_row.ok_or_else(|| Error("Missing record identity".into()))?;
            if name == "get" {
                return Ok(row.record.clone());
            }
            let replacement = if name == "update" {
                let v = evaluated
                    .get(2)
                    .ok_or_else(|| Error("New record missing".into()))?;
                if let Kind::List { record, .. } = kind {
                    validate(v, record)?;
                }
                Some(v)
            } else {
                None
            };
            let new = rows
                .iter()
                .filter_map(|r| {
                    if r.id != id {
                        Some(r.clone())
                    } else {
                        replacement.map(|new| ListItem {
                            id,
                            record: new.clone(),
                        })
                    }
                })
                .collect();
            Ok(Value::List {
                kind: kind.clone(),
                items: new,
                next_id,
            })
        }
        "filter" | "find" | "any" | "all" | "sort" | "sum" => {
            let Some(Value::Text(field)) = evaluated.get(1) else {
                return fail("Field selector required");
            };
            let selected: Vec<Value> = rows
                .iter()
                .map(|row| selected_field(row, field))
                .collect::<Result<_>>()?;
            let matched: Vec<bool> = if let Some(compare) = evaluated.get(2) {
                selected.iter().map(|v| v == compare).collect()
            } else {
                vec![false; rows.len()]
            };
            match name {
                "filter" => Ok(Value::List {
                    kind: kind.clone(),
                    next_id,
                    items: rows
                        .iter()
                        .zip(&matched)
                        .filter(|(_, m)| **m)
                        .map(|(r, _)| r.clone())
                        .collect(),
                }),
                "find" => Ok(Value::Int(
                    rows.iter()
                        .zip(&matched)
                        .find(|(_, m)| **m)
                        .map(|(r, _)| r.id)
                        .unwrap_or(0),
                )),
                "any" => Ok(Value::Bool(matched.iter().any(|v| *v))),
                "all" => Ok(Value::Bool(matched.iter().all(|v| *v))),
                "sum" => {
                    let mut sum = 0_i32;
                    for v in selected {
                        if let Value::Int(i) = v {
                            sum = sum
                                .checked_add(i)
                                .ok_or_else(|| Error("Integer overflow".into()))?;
                        } else {
                            return fail("Sum expects integer selector");
                        }
                    }
                    Ok(Value::Int(sum))
                }
                "sort" => {
                    let mut keyed: Vec<(ListItem, Value)> =
                        rows.iter().cloned().zip(selected).collect();
                    // Stable sorting matches Python: equal keys retain original order.
                    keyed.sort_by(|a, b| {
                        sort_order(&a.1, &b.1).unwrap_or(std::cmp::Ordering::Equal)
                    });
                    Ok(Value::List {
                        kind: kind.clone(),
                        items: keyed.into_iter().map(|(r, _)| r).collect(),
                        next_id,
                    })
                }
                _ => unreachable!(),
            }
        }
        _ => fail(format!("Unknown operation: {name}")),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn identities_never_reused() {
        let record = Kind::Record {
            name: "T".into(),
            fields: vec![("title".into(), Kind::Text)],
        };
        let kind = Kind::List {
            record: Box::new(record.clone()),
            capacity: 10,
        };
        let item = Value::Record {
            kind: record,
            fields: BTreeMap::from([("title".into(), Value::Text("hi".into()))]),
        };
        let empty = Value::List {
            kind: kind.clone(),
            items: vec![],
            next_id: 1,
        };
        let mut types = BTreeMap::new();
        types.insert("list".into(), kind);
        let args = vec![Expr::Ident("list".into()), Expr::Text("unused".into())];
        let result = evaluate_call(
            "append",
            &args,
            &[],
            &types,
            &BTreeMap::new(),
            &|e| match e {
                Expr::Ident(s) if s == "list" => Ok(empty.clone()),
                _ => Ok(item.clone()),
            },
        )
        .unwrap();
        let Value::List { items, next_id, .. } = result else {
            panic!("Expected list")
        };
        assert_eq!(items[0].id, 1);
        assert_eq!(next_id, 2);
    }
}
