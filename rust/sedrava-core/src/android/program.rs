use super::kotlin_string as quote;
use crate::model::{fail, Binary, Error, Expr, Kind, Program, Result, Stmt, Unary, Value, Widget};
use std::{collections::BTreeMap, fmt::Write};

type Types = BTreeMap<String, Kind>;
type Names = BTreeMap<String, String>;

fn kotlin_type(kind: &Kind) -> Result<&'static str> {
    match kind {
        Kind::Int => Ok("Int"),
        Kind::Bool => Ok("Boolean"),
        Kind::Text => Ok("String"),
        Kind::Record { .. } => Ok("SdrRecord"),
        Kind::List { .. } => Ok("SdrList"),
        Kind::Function { .. } => fail("Android cannot use a function as a value"),
        Kind::Error { .. } => Ok("SdrError"),
        Kind::Result { .. } => Ok("SdrResult"),
    }
}

fn spec(kind: &Kind) -> Result<String> {
    Ok(match kind {
        Kind::Int => "SdrType.Integer".into(),
        Kind::Bool => "SdrType.BooleanValue".into(),
        Kind::Text => "SdrType.Text".into(),
        Kind::Record { name, .. } => format!("SdrType.Record({})", quote(name)),
        Kind::List { record, capacity } => {
            let Kind::Record { name, .. } = record.as_ref() else {
                return fail("List requires records");
            };
            format!("SdrType.Collection({}, {capacity})", quote(name))
        }
        Kind::Function { .. } => return fail("No runtime value type for function"),
        Kind::Error { name, .. } => format!("SdrType.Error({})", quote(name)),
        Kind::Result { success, error } => {
            format!("SdrType.Result({}, {})", spec(success)?, spec(error)?)
        }
    })
}

fn literal(value: &Value) -> Result<String> {
    Ok(match value {
        Value::Int(n) => n.to_string(),
        Value::Bool(b) => b.to_string(),
        Value::Text(s) => quote(s),
        Value::Record {
            kind: Kind::Record { name, fields },
            fields: values,
        } => {
            let args = fields
                .iter()
                .map(|(field, _)| Ok(format!("{} to {}", quote(field), literal(&values[field])?)))
                .collect::<Result<Vec<_>>>()?
                .join(", ");
            format!("record({}, mapOf({args}))", quote(name))
        }
        Value::List {
            kind: Kind::List { record, capacity },
            items,
            next_id,
        } => {
            let Kind::Record { name, .. } = record.as_ref() else {
                return fail("List requires records");
            };
            let rows = items
                .iter()
                .map(|row| Ok(format!("SdrRow({}, {})", row.id, literal(&row.record)?)))
                .collect::<Result<Vec<_>>>()?
                .join(", ");
            format!(
                "SdrList({}, {capacity}, {next_id}, listOf({rows}))",
                quote(name)
            )
        }
        _ => return fail("Invalid Android state literal"),
    })
}

fn value(name: &str, types: &Types, receiver: &str) -> Result<String> {
    let kind = types
        .get(name)
        .ok_or_else(|| Error(format!("Unknown Android value {name}")))?;
    Ok(format!(
        "({receiver}.getValue({}) as {})",
        quote(name),
        kotlin_type(kind)?
    ))
}

fn emit(expr: &Expr, types: &Types, locals: &Names, receiver: &str) -> Result<String> {
    let sub = |e| emit(e, types, locals, receiver);
    Ok(match expr {
        Expr::Int(n) => n.to_string(),
        Expr::Bool(b) => b.to_string(),
        Expr::Text(s) => quote(s),
        Expr::Ident(name) => match locals.get(name) {
            Some(local) => local.clone(),
            None => value(name, types, receiver)?,
        },
        Expr::Unary(Unary::Neg, inner) if matches!(inner.as_ref(), Expr::Int(2_147_483_648)) => {
            "Int.MIN_VALUE".into()
        }
        Expr::Unary(Unary::Neg, inner) => format!("Math.negateExact({})", sub(inner)?),
        Expr::Unary(Unary::Not, inner) => format!("!({})", sub(inner)?),
        Expr::Binary(op, a, b) => {
            let (a, b) = (sub(a)?, sub(b)?);
            match op {
                Binary::Add => format!("Math.addExact({a}, {b})"),
                Binary::Sub => format!("Math.subtractExact({a}, {b})"),
                Binary::Mul => format!("Math.multiplyExact({a}, {b})"),
                _ => {
                    let op = match op {
                        Binary::Eq => "==",
                        Binary::Ne => "!=",
                        Binary::Lt => "<",
                        Binary::Le => "<=",
                        Binary::Gt => ">",
                        Binary::Ge => ">=",
                        Binary::And => "&&",
                        Binary::Or => "||",
                        _ => unreachable!(),
                    };
                    format!("({a} {op} {b})")
                }
            }
        }
        Expr::Conditional(c, a, b) => format!("(if ({}) {} else {})", sub(c)?, sub(a)?, sub(b)?),
        Expr::Attr(base, field) => format!(
            "({}.fields.getValue({}) as {})",
            sub(base)?,
            quote(field),
            kotlin_type(&crate::expr::infer(expr, types)?)?
        ),
        Expr::Call { name, args, kwargs } => {
            if let Some(Kind::Record { fields, .. }) = types.get(name) {
                let fields = fields
                    .iter()
                    .map(|(field, _)| {
                        let (_, expr) = kwargs
                            .iter()
                            .find(|(key, _)| key == field)
                            .ok_or_else(|| Error("Missing record constructor field".into()))?;
                        Ok(format!("{} to {}", quote(field), sub(expr)?))
                    })
                    .collect::<Result<Vec<_>>>()?
                    .join(", ");
                format!("record({}, mapOf({fields}))", quote(name))
            } else if let Some((family, variant)) = name.split_once('.') {
                let Some(Kind::Error { variants, .. }) = types.get(family) else {
                    return fail("Android: unresolved nominal error family");
                };
                let Some((_, schema)) = variants.iter().find(|(key, _)| key == variant) else {
                    return fail("Android: unresolved nominal error variant");
                };
                if !args.is_empty() || kwargs.len() != schema.len() {
                    return fail("Android: invalid error constructor");
                }
                let payload = schema
                    .iter()
                    .map(|(field, _)| {
                        let (_, expression) = kwargs
                            .iter()
                            .find(|(name, _)| name == field)
                            .ok_or_else(|| Error("Missing nominal error payload field".into()))?;
                        Ok(format!("{} to {}", quote(field), sub(expression)?))
                    })
                    .collect::<Result<Vec<_>>>()?
                    .join(", ");
                format!(
                    "nominalError({}, {}, linkedMapOf({payload}))",
                    quote(family),
                    quote(variant)
                )
            } else if matches!(
                name.as_str(),
                "filter" | "map" | "find" | "any" | "all" | "sort" | "sum"
            ) {
                let base = sub(&args[0])?;
                let extra = args[2..].iter().map(sub).collect::<Result<Vec<_>>>()?;
                let capture = extra
                    .iter()
                    .enumerate()
                    .map(|(i, code)| format!("val queryArg{i} = {code}; "))
                    .collect::<String>();
                let selected = match &args[1] {
                    Expr::Ident(function) => {
                        let extra = (0..extra.len())
                            .map(|i| format!(", queryArg{i}"))
                            .collect::<String>();
                        format!("function_{function}(queryRow.record{extra})")
                    }
                    Expr::Text(field) => {
                        let access = if field == "id" {
                            "queryRow.id".into()
                        } else {
                            format!("queryRow.record.fields.getValue({})", quote(field))
                        };
                        if extra.is_empty() {
                            access
                        } else {
                            format!("{access} == queryArg0")
                        }
                    }
                    _ => return fail("Unknown Android query selector"),
                };
                let kind = crate::expr::infer(expr, types)?;
                if name == "map" {
                    let Kind::List { record, .. } = &kind else {
                        return fail("Map requires record list");
                    };
                    let Kind::Record { name, .. } = record.as_ref() else {
                        return fail("Map requires record type");
                    };
                    return Ok(format!("run {{ val queryBase = {base}; {capture}mapRows(queryBase, {}) {{ queryRow -> {selected} }} }}", quote(name)));
                }
                let result = kotlin_type(&kind)?;
                format!("(run {{ val queryBase = {base}; {capture}query({}, queryBase) {{ queryRow -> {selected} }} }} as {result})", quote(name))
            } else {
                let arguments = args.iter().map(sub).collect::<Result<Vec<_>>>()?.join(", ");
                if matches!(types.get(name), Some(Kind::Function { .. })) {
                    format!("function_{name}({arguments})")
                } else if !types.contains_key(name) && name == "Ok" && args.len() == 1 {
                    format!("SdrResult.Success({arguments})")
                } else if !types.contains_key(name) && name == "Err" && args.len() == 1 {
                    format!("SdrResult.Failure({arguments} as SdrError)")
                } else if !types.contains_key(name) && name == "error_id" && args.len() == 1 {
                    format!("({arguments} as SdrError).id")
                } else if !types.contains_key(name) && name == "result_ok" && args.len() == 1 {
                    format!("({arguments} is SdrResult.Success)")
                } else if !types.contains_key(name) && name == "result_or" && args.len() == 2 {
                    let kind = crate::expr::infer(&args[0], types)?;
                    let Kind::Result { success, .. } = kind else {
                        return fail("Android result_or expected typed Result");
                    };
                    // Both arguments evaluated once and in source order,
                    // even when the primary Result is successful.
                    format!("run {{ val _result = {}; val _fallback = {};                         if (_result is SdrResult.Success) _result.value as {} else _fallback }}",
                        sub(&args[0])?,sub(&args[1])?,kotlin_type(&success)?)
                } else if matches!(
                    name.as_str(),
                    "append" | "remove" | "get" | "has" | "update" | "count" | "next_id"
                ) || crate::stdlib::signature(name).is_some()
                {
                    format!("builtin_{name}({arguments})")
                } else {
                    return fail(format!("Unknown Android operation {name}"));
                }
            }
        }
    })
}

fn statements(
    out: &mut String,
    stmts: &[Stmt],
    types: &Types,
    locals: &Names,
    depth: usize,
    index: &mut usize,
) -> Result<()> {
    let mut types = types.clone();
    let mut locals = locals.clone();
    let pad = " ".repeat(depth);
    for stmt in stmts {
        let compile = |expr| emit(expr, &types, &locals, "values");
        match stmt {
            Stmt::Assign(name, expr) => {
                writeln!(out, "{pad}next[{}] = {}", quote(name), compile(expr)?).unwrap();
                writeln!(out, "{pad}values = resolve(next)").unwrap();
            }
            Stmt::Let(name, expr) => {
                let code = compile(expr)?;
                let kind = crate::expr::infer(expr, &types)?;
                let local = format!("local_{index}");
                *index += 1;
                writeln!(out, "{pad}val {local} = {code}").unwrap();
                types.insert(name.clone(), kind);
                locals.insert(name.clone(), local);
            }
            Stmt::Require(expr) => writeln!(out, "{pad}require({})", compile(expr)?).unwrap(),
            Stmt::Match(subject, arms) => {
                use crate::model::MatchPattern;
                let result_type = crate::expr::infer(subject, &types)?;
                let Kind::Result { success, error } = &result_type else {
                    return fail("Android match subject is not Result");
                };
                let Kind::Error { variants, .. } = error.as_ref() else {
                    return fail("Android legacy Error match not implemented");
                };
                let matched = format!("match_{}", index);
                *index += 1;
                writeln!(
                    out,
                    "{pad}val {matched} = {} as SdrResult",
                    compile(subject)?
                )
                .unwrap();
                for (arm_index, arm) in arms.iter().enumerate() {
                    let mut scoped_types = types.clone();
                    let mut scoped_locals = locals.clone();
                    match &arm.pattern {
                        MatchPattern::Ok(name) => {
                            let value = format!("local_{}", index);
                            *index += 1;
                            scoped_types.insert(name.clone(), success.as_ref().clone());
                            scoped_locals.insert(name.clone(), value.clone());
                            let code = format!(
                                "({matched} as SdrResult.Success).value as {}",
                                kotlin_type(success)?
                            );
                            writeln!(
                                out,
                                "{pad}{} ({matched} is SdrResult.Success) {{",
                                if arm_index == 0 { "if" } else { "else if" }
                            )
                            .unwrap();
                            writeln!(out, "{pad}    val {value} = {code}").unwrap();
                        }
                        MatchPattern::Variant { name, bindings } => {
                            let (_, fields) = variants
                                .iter()
                                .find(|(variant, _)| variant == name)
                                .ok_or_else(|| {
                                    Error("Android unknown typed error variant".into())
                                })?;
                            let cond = format!(
                                "{matched} is SdrResult.Failure && {matched}.error.variant == {}",
                                quote(name)
                            );
                            writeln!(
                                out,
                                "{pad}{} ({cond}) {{",
                                if arm_index == 0 { "if" } else { "else if" }
                            )
                            .unwrap();
                            for (field, binder) in bindings {
                                let kind = fields
                                    .iter()
                                    .find(|(key, _)| key == field)
                                    .map(|(_, kind)| kind)
                                    .ok_or_else(|| Error("Unbound typed error field".into()))?;
                                let local = format!("local_{}", index);
                                *index += 1;
                                scoped_types.insert(binder.clone(), kind.clone());
                                scoped_locals.insert(binder.clone(), local.clone());
                                writeln!(out,"{pad}    val {local} = ({matched} as SdrResult.Failure).error.fields.getValue({}) as {}",
                                    quote(field),kotlin_type(kind)?).unwrap();
                            }
                        }
                        MatchPattern::Fallback(name) => {
                            let local = format!("local_{}", index);
                            *index += 1;
                            scoped_types.insert(name.clone(), error.as_ref().clone());
                            scoped_locals.insert(name.clone(), local.clone());
                            writeln!(
                                out,
                                "{pad}{} ({matched} is SdrResult.Failure) {{",
                                if arm_index == 0 { "if" } else { "else if" }
                            )
                            .unwrap();
                            writeln!(out, "{pad}    val {local} = {matched}.error").unwrap();
                        }
                    };
                    statements(
                        out,
                        &arm.body,
                        &scoped_types,
                        &scoped_locals,
                        depth + 4,
                        index,
                    )?;
                    writeln!(out, "{pad}}}").unwrap();
                }
                writeln!(
                    out,
                    "{pad}else {{ throw IllegalArgumentException({}) }}",
                    quote("E_MATCH: unmatched typed Result")
                )
                .unwrap();
            }
            Stmt::Branch(cond, yes, no) => {
                writeln!(out, "{pad}if ({}) {{", compile(cond)?).unwrap();
                statements(out, yes, &types, &locals, depth + 4, index)?;
                if !no.is_empty() {
                    writeln!(out, "{pad}}} else {{").unwrap();
                    statements(out, no, &types, &locals, depth + 4, index)?;
                }
                writeln!(out, "{pad}}}").unwrap();
            }
        }
    }
    Ok(())
}

fn emit_widgets(out: &mut String, program: &Program) -> Result<()> {
    writeln!(out, "internal val screens = mapOf(").unwrap();
    for (name, screen) in &program.screens {
        let locals = Names::new();
        let guard = screen
            .guard
            .as_ref()
            .map(|e| emit(e, &program.types, &locals, "values"))
            .transpose()?
            .unwrap_or_else(|| "true".into());
        writeln!(
            out,
            "    {} to Screen(guard = {{ values -> {guard} }}, widgets = listOf(",
            quote(name)
        )
        .unwrap();
        for widget in &screen.widgets {
            let code = match widget {
                Widget::Text(text) => format!("Widget.Text({})", quote(text)),
                Widget::Value(name) => format!(
                    "Widget.Display({}) {{ values -> values.getValue({}) }}",
                    quote(&format!("{name}: ")),
                    quote(name)
                ),
                Widget::Display(expr) => format!(
                    "Widget.Display(\"\") {{ values -> {} }}",
                    emit(expr, &program.types, &locals, "values")?
                ),
                Widget::Input { state, label } => format!(
                    "Widget.Input({}, {}, {})",
                    quote(state),
                    quote(label),
                    program.types[state] == Kind::Int
                ),
                Widget::Show { condition, label } => {
                    format!("Widget.Show({}, {})", quote(condition), quote(label))
                }
                Widget::Button { label, action } => {
                    format!("Widget.Button({}, {})", quote(label), quote(action))
                }
                Widget::List {
                    collection,
                    selected,
                    options,
                } => {
                    let mut args = BTreeMap::new();
                    for (key, name) in options {
                        if !matches!(key.as_str(), "open" | "title" | "status")
                            || args.insert(key.as_str(), name).is_some()
                        {
                            return fail("Unsupported or duplicate Android list option");
                        }
                    }
                    let option = |key| {
                        args.get(key)
                            .map(|v| quote(v))
                            .unwrap_or_else(|| "null".into())
                    };
                    format!(
                        "Widget.Rows({}, {}, {}, {}, {})",
                        quote(collection),
                        quote(selected),
                        option("open"),
                        option("title"),
                        option("status")
                    )
                }
            };
            writeln!(out, "        {code},").unwrap();
        }
        writeln!(out, "    )),").unwrap();
    }
    writeln!(out, ")").unwrap();
    Ok(())
}

pub(super) fn generate(program: &Program) -> Result<String> {
    let mut out = String::new();
    writeln!(out, "internal val errorTypes = mapOf<String, ErrorFamily>(").unwrap();
    for (name, kind) in &program.types {
        if let Kind::Error { id, variants, .. } = kind {
            let mut members = Vec::new();
            for (variant, fields) in variants {
                let values = fields
                    .iter()
                    .map(|(field, kind)| Ok(format!("{} to {}", quote(field), spec(kind)?)))
                    .collect::<Result<Vec<_>>>()?
                    .join(", ");
                members.push(format!("{} to linkedMapOf({values})", quote(variant)));
            }
            writeln!(
                out,
                "    {} to ErrorFamily({}, mapOf({})),",
                quote(name),
                quote(id),
                members.join(", ")
            )
            .unwrap();
        }
    }
    writeln!(out, ")").unwrap();
    writeln!(
        out,
        "internal val recordTypes = mapOf<String, Map<String, SdrType>>("
    )
    .unwrap();
    for (name, kind) in &program.types {
        if let Kind::Record {
            name: type_name,
            fields,
        } = kind
        {
            if name != type_name {
                continue;
            }
            let fields = fields
                .iter()
                .map(|(name, kind)| Ok(format!("{} to {}", quote(name), spec(kind)?)))
                .collect::<Result<Vec<_>>>()?
                .join(", ");
            writeln!(out, "    {} to mapOf({fields}),", quote(name)).unwrap();
        }
    }
    writeln!(out, ")\ninternal val stateTypes = mapOf<String, SdrType>(").unwrap();
    for key in program.states.keys() {
        writeln!(out, "    {} to {},", quote(key), spec(&program.types[key])?).unwrap();
    }
    writeln!(out, ")\ninternal val defaultState: SdrState = mapOf(").unwrap();
    for (name, val) in &program.states {
        writeln!(out, "    {} to {},", quote(name), literal(val)?).unwrap();
    }
    let persisted = program
        .persistent
        .iter()
        .map(|key| quote(key))
        .collect::<Vec<_>>()
        .join(", ");
    writeln!(
        out,
        ")\ninternal val persistent = setOf<String>({persisted})"
    )
    .unwrap();
    writeln!(
        out,
        "internal const val snapshotSignature = {}",
        quote(&crate::snapshot::fingerprint(program)?)
    )
    .unwrap();
    let legacy = !program.has_navigation
        && !program
            .types
            .values()
            .any(|kind| matches!(kind, Kind::Record { .. }));
    writeln!(out, "internal const val legacyScalarPreferences = {legacy}").unwrap();
    writeln!(
        out,
        "internal const val initialScreen = {}",
        quote(&program.initial_screen)
    )
    .unwrap();

    for (name, function) in &program.functions {
        let mut types = program.types.clone();
        let mut locals = Names::new();
        let mut arguments = Vec::new();
        for (index, (key, kind)) in function.parameters.iter().enumerate() {
            let local = format!("p{index}");
            arguments.push(format!("{local}: {}", kotlin_type(kind)?));
            locals.insert(key.clone(), local);
            types.insert(key.clone(), kind.clone());
        }
        let result = kotlin_type(&function.result)?;
        let body = emit(&function.body, &types, &locals, "unused")?;
        writeln!(out, "private fun function_{name}({}): {result} {{\n    val result = {body}\n    checkValue(result, {})\n    return result\n}}",
            arguments.join(", "), spec(&function.result)?).unwrap();
    }
    writeln!(
        out,
        "internal fun derive(state: SdrState): SdrState {{\n    val values = state.toMutableMap()"
    )
    .unwrap();
    for (name, expr) in &program.derives {
        let code = emit(expr, &program.types, &Names::new(), "values")?;
        writeln!(
            out,
            "    values[{}] = checkValue({code}, {})",
            quote(name),
            spec(&program.types[name])?
        )
        .unwrap();
    }
    writeln!(
        out,
        "    return values\n}}\ninternal fun rulesHold(values: SdrState): Boolean {{"
    )
    .unwrap();
    for rule in &program.rules {
        writeln!(
            out,
            "    if (!({})) return false",
            emit(rule, &program.types, &Names::new(), "values")?
        )
        .unwrap();
    }
    writeln!(out, "    return true\n}}\ninternal val actions = mapOf<String, (MutableMap<String, Any>, SdrState) -> Unit>(").unwrap();
    for (name, stmts) in &program.actions {
        writeln!(
            out,
            "    {} to {{ next, initialValues ->\n        var values = initialValues",
            quote(name)
        )
        .unwrap();
        statements(&mut out, stmts, &program.types, &Names::new(), 8, &mut 0)?;
        writeln!(out, "    }},").unwrap();
    }
    writeln!(out, ")\ninternal val routes = mapOf<String, Route>(").unwrap();
    for (name, route) in &program.navigation {
        let action = route
            .action
            .as_ref()
            .map(|a| quote(a))
            .unwrap_or_else(|| "null".into());
        writeln!(
            out,
            "    {} to Route({}, {action}),",
            quote(name),
            quote(&route.target)
        )
        .unwrap();
    }
    writeln!(out, ")").unwrap();
    emit_widgets(&mut out, program)?;
    Ok(out)
}
