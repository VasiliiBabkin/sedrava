//! Parser for the currently supported scalar application subset.
//!
//! Unsupported 0.11 features are rejected explicitly, not silently ignored.
//! This module does NOT claim complete Sedrava language compatibility.

use crate::expr;
use crate::model::{
    fail, EmbeddedTest, Error, Expr, Kind, MatchArm, MatchPattern, Navigation, Program,
    PureFunction, Result, Screen, SourceSpan, State, Stmt, Value, Widget, MAX_ACTION_STEPS,
    MAX_BLOCK_DEPTH, MAX_COLLECTIONS, MAX_RECORDS, MAX_SOURCE_CHARS,
};
use std::collections::{BTreeMap, BTreeSet};

#[derive(Debug, Clone)]
struct Line {
    number: usize,
    indent: usize,
    content: String,
}

fn line_error<T>(number: usize, error: impl std::fmt::Display) -> Result<T> {
    fail(format!("Line {number}: {error}"))
}

fn source_lines(source: &str) -> Result<Vec<Line>> {
    if source.chars().count() > MAX_SOURCE_CHARS {
        return fail("Source exceeds size limit");
    }
    let mut result = Vec::new();
    for (index, raw) in source.split('\n').enumerate() {
        let number = index + 1;
        if raw.starts_with('\u{feff}') {
            return line_error(number, "UTF-8 BOM is not supported");
        }
        let indent = raw.chars().take_while(|c| *c == ' ' || *c == '\t').count();
        if raw.chars().take(indent).any(|c| c == '\t') {
            return line_error(number, "tabs are not allowed in indentation");
        }
        let content = raw.trim();
        if content.is_empty() || content.starts_with('#') {
            continue;
        }
        result.push(Line {
            number,
            indent,
            content: content.to_owned(),
        });
    }
    Ok(result)
}

fn user_error_identifier(name: &str) -> bool {
    let mut chars = name.chars();
    matches!(chars.next(),Some(c) if c.is_ascii_alphabetic())
        && chars.all(|c| c.is_ascii_alphanumeric() || c == '_')
}

fn is_identifier(name: &str) -> bool {
    let mut chars = name.chars();
    let Some(first) = chars.next() else {
        return false;
    };
    (first.is_ascii_alphabetic() || first == '_')
        && chars.all(|c| c.is_ascii_alphanumeric() || c == '_')
        && !matches!(
            name,
            "true"
                | "false"
                | "True"
                | "False"
                | "None"
                | "and"
                | "or"
                | "not"
                | "if"
                | "else"
                | "for"
                | "while"
                | "class"
                | "def"
                | "return"
                | "lambda"
                | "import"
                | "from"
                | "try"
                | "except"
                | "with"
        )
}

fn checked_expression(
    source: &str,
    kinds: &BTreeMap<String, Kind>,
    line: usize,
) -> Result<(Expr, Kind)> {
    let expr = expr::parse(source).map_err(|e| Error(format!("Line {line}: {e}")))?;
    let kind = expr::infer(&expr, kinds).map_err(|e| Error(format!("Line {line}: {e}")))?;
    Ok((expr, kind))
}

fn require_type(
    source: &str,
    kinds: &BTreeMap<String, Kind>,
    expected: Kind,
    line: usize,
) -> Result<Expr> {
    let (expr, actual) = checked_expression(source, kinds, line)?;
    if actual != expected {
        return line_error(
            line,
            format!("Type mismatch: expected {expected:?}, found {actual:?}"),
        );
    }
    Ok(expr)
}

fn value_text(expr: &Expr, line: usize) -> Result<String> {
    match expr::evaluate(expr, &State::new()) {
        Ok(Value::Text(text)) => Ok(text),
        _ => line_error(line, "Expected a double-quoted text literal"),
    }
}

fn parse_label(source: &str, number: usize) -> Result<String> {
    let expr = require_type(source, &BTreeMap::new(), Kind::Text, number)?;
    value_text(&expr, number)
}

fn split_decl<'a>(rest: &'a str, number: usize) -> Result<(&'a str, &'a str)> {
    let Some((name, value)) = rest.split_once('=') else {
        return line_error(number, "Missing '=' in declaration");
    };
    let name = name.trim();
    let value = value.trim();
    if !is_identifier(name) || value.is_empty() {
        return line_error(number, "Invalid declaration");
    }
    Ok((name, value))
}

fn parse_match(
    lines: &[Line],
    pos: &mut usize,
    indent: usize,
    depth: usize,
    known: &BTreeMap<String, Kind>,
    states: &BTreeMap<String, Kind>,
    count: &mut usize,
) -> Result<Stmt> {
    let line = &lines[*pos];
    let source = line
        .content
        .strip_prefix("match ")
        .and_then(|v| v.strip_suffix(':'))
        .ok_or_else(|| Error("E_MATCH: invalid match declaration".into()))?;
    let (expression, kind) = checked_expression(source, known, line.number)?;
    let Kind::Result { success, error } = &kind else {
        return line_error(line.number, "E_MATCH: expected typed Result expression");
    };
    let Kind::Error { variants, .. } = error.as_ref() else {
        return line_error(line.number, "E_MATCH: legacy Result not yet supported");
    };
    *pos += 1;
    if *pos >= lines.len() || lines[*pos].indent <= indent {
        return line_error(line.number, "E_MATCH: expected nonempty arms");
    }
    let arm_indent = lines[*pos].indent;
    let mut arms = Vec::new();
    let mut had_fallback = false;
    while *pos < lines.len() && lines[*pos].indent >= arm_indent {
        let arm = &lines[*pos];
        if arm.indent != arm_indent || !arm.content.ends_with(':') || had_fallback {
            return line_error(
                arm.number,
                "E_MATCH: invalid arm indentation or arm after fallback",
            );
        }
        *count += 1;
        if *count > MAX_ACTION_STEPS {
            return line_error(arm.number, "E_MATCH: action statement budget");
        }
        let name = arm.content.trim_end_matches(':');
        let mut scope = known.clone();
        let (pattern, binds): (MatchPattern, Vec<(String, Kind)>) = if let Some(value) =
            name.strip_prefix("Ok(").and_then(|v| v.strip_suffix(')'))
        {
            if !is_identifier(value) || value.len() > 64 || scope.contains_key(value) {
                return line_error(arm.number, "E_MATCH: bad Ok binder");
            }
            (
                MatchPattern::Ok(value.into()),
                vec![(value.into(), success.as_ref().clone())],
            )
        } else if let Some(value) = name.strip_prefix("Err(").and_then(|v| v.strip_suffix(')')) {
            if let Some((variant, fields)) = value.split_once(" {") {
                let Some(fields) = fields.strip_suffix('}') else {
                    return line_error(arm.number, "E_MATCH: expected closing brace");
                };
                let variant = variant.trim();
                let Some((_, schema)) = variants.iter().find(|(n, _)| n == variant) else {
                    return line_error(arm.number, "E_MATCH: unknown variant");
                };
                let mut aliases = Vec::new();
                let mut used = BTreeSet::new();
                let mut binds = Vec::new();
                if !fields.trim().is_empty() {
                    for field in fields.split(',') {
                        let field = field.trim();
                        let (key, alias) = if let Some((key, alias)) = field.split_once(':') {
                            (key.trim(), alias.trim())
                        } else {
                            (field, field)
                        };
                        let Some((_, kind)) = schema.iter().find(|(n, _)| n == key) else {
                            return line_error(arm.number, "E_MATCH: unknown error payload field");
                        };
                        if !is_identifier(alias)
                            || alias.len() > 64
                            || scope.contains_key(alias)
                            || !used.insert(key)
                            || binds.iter().any(|(n, _)| n == alias)
                        {
                            return line_error(arm.number, "E_MATCH: invalid/duplicate arm binder");
                        }
                        aliases.push((key.into(), alias.into()));
                        binds.push((alias.into(), kind.clone()));
                    }
                }
                (
                    MatchPattern::Variant {
                        name: variant.into(),
                        bindings: aliases,
                    },
                    binds,
                )
            } else {
                let binder = value.trim();
                if variants.iter().any(|(name, _)| name == binder) {
                    return line_error(arm.number, "E_MATCH: variant pattern requires braces");
                }
                if !is_identifier(binder) || binder.len() > 64 || scope.contains_key(binder) {
                    return line_error(arm.number, "E_MATCH: bad fallback binder");
                }
                had_fallback = true;
                (
                    MatchPattern::Fallback(binder.into()),
                    vec![(binder.into(), error.as_ref().clone())],
                )
            }
        } else {
            return line_error(arm.number, "E_MATCH: expected Ok(...) or Err(...)");
        };
        for (key, kind) in binds {
            scope.insert(key, kind);
        }
        *pos += 1;
        if *pos >= lines.len() || lines[*pos].indent <= arm_indent {
            return line_error(arm.number, "E_MATCH: empty arm");
        }
        let body_indent = lines[*pos].indent;
        let body = parse_block(lines, pos, body_indent, depth + 1, &scope, states, count)?;
        if body.is_empty() {
            return line_error(arm.number, "E_MATCH: empty arm");
        }
        arms.push(MatchArm { pattern, body });
        if arms.len() > 18 {
            return line_error(arm.number, "E_MATCH: arm count exceeds budget");
        }
    }
    crate::typed_errors::exhaustive(&kind, &arms)?;
    Ok(Stmt::Match(expression, arms))
}

fn parse_block(
    lines: &[Line],
    pos: &mut usize,
    indent: usize,
    depth: usize,
    known: &BTreeMap<String, Kind>,
    states: &BTreeMap<String, Kind>,
    count: &mut usize,
) -> Result<Vec<Stmt>> {
    if depth > MAX_BLOCK_DEPTH {
        return fail("Action block nesting limit exceeded");
    }
    let mut scope = known.clone();
    let mut body = Vec::new();
    while *pos < lines.len() {
        let current = &lines[*pos];
        if current.indent < indent || (current.indent == indent && current.content == "else:") {
            break;
        }
        if current.indent != indent {
            return line_error(current.number, "Unexpected indentation in action");
        }
        *count += 1;
        if *count > MAX_ACTION_STEPS {
            return line_error(current.number, "Action exceeds statement limit");
        }
        let number = current.number;
        let text = current.content.as_str();
        if text.starts_with("match ") && text.ends_with(':') {
            body.push(parse_match(
                lines, pos, indent, depth, &scope, states, count,
            )?);
            continue;
        }
        if text.starts_with("if ") && text.ends_with(':') {
            let condition = require_type(&text[3..text.len() - 1], &scope, Kind::Bool, number)?;
            *pos += 1;
            if *pos >= lines.len() || lines[*pos].indent <= indent {
                return line_error(number, "Empty if block");
            }
            let next_indent = lines[*pos].indent;
            let yes = parse_block(lines, pos, next_indent, depth + 1, &scope, states, count)?;
            if yes.is_empty() {
                return line_error(number, "Empty if branch");
            }
            let mut no = Vec::new();
            if *pos < lines.len() && lines[*pos].indent == indent && lines[*pos].content == "else:"
            {
                *pos += 1;
                if *pos >= lines.len() || lines[*pos].indent <= indent {
                    return line_error(number, "Empty else block");
                }
                let else_indent = lines[*pos].indent;
                no = parse_block(lines, pos, else_indent, depth + 1, &scope, states, count)?;
                if no.is_empty() {
                    return line_error(number, "Empty else branch");
                }
            }
            body.push(Stmt::Branch(condition, yes, no));
            continue;
        }
        if let Some(rest) = text.strip_prefix("require ") {
            body.push(Stmt::Require(require_type(
                rest,
                &scope,
                Kind::Bool,
                number,
            )?));
        } else if let Some(rest) = text.strip_prefix("let ") {
            let (name, value) = split_decl(rest, number)?;
            if scope.contains_key(name) {
                return line_error(number, "Duplicate or reserved local");
            }
            let (expression, kind) = checked_expression(value, &scope, number)?;
            scope.insert(name.to_string(), kind);
            body.push(Stmt::Let(name.to_string(), expression));
        } else if let Ok((name, value)) = split_decl(text, number) {
            let Some(kind) = states.get(name) else {
                return line_error(number, "Assignment target is not a declared state");
            };
            body.push(Stmt::Assign(
                name.to_string(),
                require_type(value, &scope, kind.clone(), number)?,
            ));
        } else {
            return line_error(number, "Unsupported statement in native core");
        }
        *pos += 1;
    }
    Ok(body)
}

fn portable_type(raw: &str, types: &BTreeMap<String, Kind>) -> Result<Kind> {
    if let Some(kind) = crate::typed_errors::result_type(raw, types)? {
        return Ok(kind);
    }
    match raw {
        "int" => return Ok(Kind::Int),
        "bool" => return Ok(Kind::Bool),
        "text" => return Ok(Kind::Text),
        _ => {}
    }
    if let Some(kind @ Kind::Record { .. }) = types.get(raw) {
        return Ok(kind.clone());
    }
    if let Some(spec) = raw.strip_prefix("list<") {
        let Some((name, capacity)) = spec.split_once(">(max=") else {
            return fail("Invalid bounded list function type");
        };
        let cap = capacity
            .strip_suffix(')')
            .and_then(|n| n.parse::<usize>().ok())
            .ok_or_else(|| Error("Invalid list capacity".into()))?;
        if !(1..=100).contains(&cap) {
            return fail("Function list capacity must be 1..100");
        }
        if let Some(record @ Kind::Record { .. }) = types.get(name) {
            return Ok(Kind::List {
                record: Box::new(record.clone()),
                capacity: cap,
            });
        }
    }
    fail(format!("Unknown function type: {raw}"))
}

fn parse_widget(
    line: &Line,
    types: &BTreeMap<String, Kind>,
    states: &State,
) -> Result<Option<String>> {
    let number = line.number;
    let text = line.content.as_str();
    if let Some(label) = text.strip_prefix("text ") {
        parse_label(label, number)?;
    } else if let Some(name) = text.strip_prefix("value ") {
        if !matches!(
            types.get(name),
            Some(Kind::Int) | Some(Kind::Text) | Some(Kind::Bool)
        ) {
            return line_error(number, "Value requires scalar state or derive");
        }
    } else if let Some(rest) = text.strip_prefix("list ") {
        let tokens: Vec<&str> = rest.split_whitespace().collect();
        if tokens.len() < 3 || tokens[1] != "select" {
            return line_error(number, "Expected list collection select state");
        }
        let Some(Kind::List { record, .. }) = types.get(tokens[0]) else {
            return line_error(number, "List widget requires declared collection");
        };
        if !matches!(states.get(tokens[2]), Some(Value::Int(_))) {
            return line_error(number, "List selection must be int state");
        }
        let mut pos = 3;
        let mut action = None;
        while pos < tokens.len() {
            if pos + 1 >= tokens.len() {
                return line_error(number, "Invalid list widget option");
            }
            match tokens[pos] {
                "open" => {
                    action = Some(tokens[pos + 1].to_owned());
                }
                "title" | "status" => {
                    let required = if tokens[pos] == "title" {
                        Kind::Text
                    } else {
                        Kind::Bool
                    };
                    let Kind::Record { fields, .. } = record.as_ref() else {
                        return line_error(number, "List rows must be records");
                    };
                    if !fields
                        .iter()
                        .any(|(f, k)| f == tokens[pos + 1] && *k == required)
                    {
                        return line_error(number, "List title/status record field mismatch");
                    }
                }
                _ => return line_error(number, "Unsupported list widget option"),
            }
            pos += 2;
        }
        return Ok(action);
    } else if let Some(rest) = text.strip_prefix("display ") {
        let (_, kind) = checked_expression(rest, types, number)?;
        if !matches!(kind, Kind::Int | Kind::Bool | Kind::Text) {
            return line_error(number, "Display requires scalar expression");
        }
    } else if let Some(rest) = text.strip_prefix("input ") {
        let (name, label) = if let Some((name, label)) = rest.split_once(" label ") {
            (name, Some(label))
        } else {
            (rest, None)
        };
        if !matches!(states.get(name), Some(Value::Int(_)) | Some(Value::Text(_))) {
            return line_error(number, "Input requires int or text state");
        }
        if let Some(label) = label {
            parse_label(label, number)?;
        }
    } else if let Some(rest) = text.strip_prefix("show ") {
        let Some((key, label)) = rest.split_once(" : text ") else {
            return line_error(number, "Invalid show text widget");
        };
        if types.get(key) != Some(&Kind::Bool) {
            return line_error(number, "Show requires bool state or derive");
        }
        parse_label(label, number)?;
    } else if let Some(rest) = text.strip_prefix("button ") {
        let Some((label, action)) = rest.rsplit_once(" -> ") else {
            return line_error(number, "Invalid button widget");
        };
        parse_label(label, number)?;
        if !is_identifier(action) {
            return line_error(number, "Invalid action name in button");
        }
        return Ok(Some(action.to_owned()));
    } else {
        return line_error(number, "Widget unsupported by native scalar core");
    }
    Ok(None)
}

/// Preserve validated widget declarations as structured data for backends.
fn widget_ast(line: &Line, types: &BTreeMap<String, Kind>) -> Result<Widget> {
    let text = line.content.as_str();
    let n = line.number;
    if let Some(value) = text.strip_prefix("text ") {
        return Ok(Widget::Text(parse_label(value, n)?));
    }
    if let Some(key) = text.strip_prefix("value ") {
        return Ok(Widget::Value(key.to_owned()));
    }
    if let Some(rest) = text.strip_prefix("input ") {
        let (key, label) = if let Some((key, label)) = rest.split_once(" label ") {
            (key, parse_label(label, n)?)
        } else {
            (rest, rest.to_owned())
        };
        return Ok(Widget::Input {
            state: key.to_owned(),
            label,
        });
    }
    if let Some(rest) = text.strip_prefix("show ") {
        let Some((condition, label)) = rest.split_once(" : text ") else {
            return line_error(n, "Invalid show declaration");
        };
        return Ok(Widget::Show {
            condition: condition.to_owned(),
            label: parse_label(label, n)?,
        });
    }
    if let Some(rest) = text.strip_prefix("button ") {
        let Some((label, action)) = rest.rsplit_once(" -> ") else {
            return line_error(n, "Invalid button declaration");
        };
        return Ok(Widget::Button {
            label: parse_label(label, n)?,
            action: action.to_owned(),
        });
    }
    if let Some(rest) = text.strip_prefix("display ") {
        let (expr, _) = checked_expression(rest, types, n)?;
        return Ok(Widget::Display(expr));
    }
    if let Some(rest) = text.strip_prefix("list ") {
        let tokens: Vec<&str> = rest.split_whitespace().collect();
        if tokens.len() < 3 {
            return line_error(n, "Invalid list declaration");
        }
        let options = tokens[3..]
            .chunks(2)
            .map(|chunk| (chunk[0].to_owned(), chunk.get(1).unwrap_or(&"").to_string()))
            .collect();
        return Ok(Widget::List {
            collection: tokens[0].to_owned(),
            selected: tokens[2].to_owned(),
            options,
        });
    }
    line_error(n, "Unsupported widget for native backend")
}

/// Parse supported app semantics including typed records/lists, functions,
/// rules, actions, tests and navigation. Site/WebApp DSL is NOT supported.
pub fn parse(source: &str) -> Result<Program> {
    let mut lines = source_lines(source)?;
    let mut name: Option<String> = None;
    let mut states = State::new();
    let mut state_order = Vec::new();
    let mut declaration_spans = BTreeMap::new();
    let mut types = BTreeMap::new();
    let mut derives = Vec::new();
    let mut functions = BTreeMap::new();
    let mut actions = BTreeMap::new();
    let mut rules = Vec::new();
    let mut tests = Vec::new();
    let mut persisted = BTreeSet::new();
    let mut screens = BTreeMap::new();
    let mut navigation = BTreeMap::new();
    let mut initial_screen: Option<String> = None;
    let mut navigation_seen = false;
    let mut seen_action_or_after = false;
    let mut i = 0;

    while i < lines.len() {
        let current = lines[i].clone();
        if current.indent != 0 {
            return line_error(current.number, "Unexpected top-level indentation");
        }
        let text = current.content.as_str();
        if let Some(label) = text.strip_prefix("app ") {
            if name.is_some() {
                return line_error(current.number, "Duplicate app");
            }
            let title = parse_label(label, current.number)?;
            if title.is_empty() {
                return line_error(current.number, "Empty app name");
            }
            name = Some(title);
        } else if let Some(header) = text.strip_prefix("error ") {
            if seen_action_or_after
                || !states.is_empty()
                || !functions.is_empty()
                || types
                    .values()
                    .filter(|kind| matches!(kind, Kind::Error { .. }))
                    .count()
                    >= 16
            {
                return line_error(
                    current.number,
                    "E_ERROR_TYPE: error families must precede functions/states and be <=16",
                );
            }
            let Some(header) = header.strip_suffix(':') else {
                return line_error(current.number, "E_ERROR_TYPE: expected ending ':'");
            };
            let (spec, explicit_id) = if let Some((spec, id)) = header.split_once(" id ") {
                (spec, Some(parse_label(id, current.number)?))
            } else {
                (header, None)
            };
            let Some((openness, family)) = spec.split_once(' ') else {
                return line_error(
                    current.number,
                    "E_ERROR_TYPE: expected error closed|open Name",
                );
            };
            if !matches!(openness, "open" | "closed")
                || !is_identifier(family)
                || family.len() > 64
                || types.contains_key(family)
                || matches!(
                    family,
                    "int"
                        | "text"
                        | "bool"
                        | "list"
                        | "Result"
                        | "Error"
                        | "Ok"
                        | "Err"
                        | "error_id"
                        | "BudgetExceeded"
                        | "PolicyViolation"
                        | "CapabilityDenied"
                        | "CompilerError"
                        | "InternalError"
                )
            {
                return line_error(
                    current.number,
                    "E_ERROR_TYPE: invalid or reserved error name",
                );
            }
            let id = explicit_id.unwrap_or_else(|| format!("entry.{family}"));
            if id.is_empty()
                || id.len() > 128
                || id.starts_with('.')
                || id.ends_with('.')
                || id.split('.').any(|part| {
                    part.is_empty()
                        || !part
                            .chars()
                            .all(|c| c.is_ascii_alphanumeric() || c == '_' || c == '-')
                })
                || types
                    .values()
                    .any(|kind| matches!(kind, Kind::Error{id:other,..} if other==&id))
            {
                return line_error(
                    current.number,
                    "E_ERROR_TYPE: invalid/duplicate stable error identifier",
                );
            }
            let mut variants: Vec<(String, Vec<(String, Kind)>)> = Vec::new();
            i += 1;
            while i < lines.len() && lines[i].indent > 0 {
                let variant = &lines[i];
                if variant.indent != 4 || !variant.content.ends_with(':') {
                    return line_error(variant.number, "E_ERROR_TYPE: variant indent must be four");
                }
                let name = variant.content.trim_end_matches(':');
                if !is_identifier(name)
                    || name.len() > 64
                    || variants.iter().any(|(x, _)| x == name)
                    || variants.len() >= 16
                {
                    return line_error(
                        variant.number,
                        "E_ERROR_TYPE: invalid/duplicate error variant",
                    );
                }
                i += 1;
                let mut fields: Vec<(String, Kind)> = Vec::new();
                while i < lines.len() && lines[i].indent > 4 {
                    let field = &lines[i];
                    if field.indent != 8 {
                        return line_error(
                            field.number,
                            "E_ERROR_TYPE: field indent must be eight",
                        );
                    }
                    let Some((name, kind)) = field.content.split_once(": ") else {
                        return line_error(field.number, "E_ERROR_TYPE: expected field: scalar");
                    };
                    if !user_error_identifier(name)
                        || name.len() > 64
                        || fields.len() >= 16
                        || fields.iter().any(|(x, _)| x == name)
                    {
                        return line_error(field.number, "E_ERROR_TYPE: invalid or repeated field");
                    }
                    let kind = match kind {
                        "int" => Kind::Int,
                        "text" => Kind::Text,
                        "bool" => Kind::Bool,
                        _ => {
                            return line_error(field.number, "E_ERROR_TYPE: payload must be scalar")
                        }
                    };
                    fields.push((name.into(), kind));
                    i += 1;
                }
                variants.push((name.into(), fields));
            }
            if variants.is_empty() {
                return line_error(
                    current.number,
                    "E_ERROR_TYPE: error family requires variants",
                );
            }
            declaration_spans.insert(
                format!("error:{family}"),
                SourceSpan {
                    line: current.number,
                    column: 1,
                },
            );
            types.insert(
                family.into(),
                Kind::Error {
                    name: family.into(),
                    id,
                    open: openness == "open",
                    variants,
                },
            );
            continue;
        } else if let Some(rest) = text.strip_prefix("record ") {
            if seen_action_or_after
                || !states.is_empty()
                || types
                    .values()
                    .filter(|x| matches!(x, Kind::Record { .. }))
                    .count()
                    >= MAX_RECORDS
            {
                return line_error(
                    current.number,
                    "Record declarations must precede states/actions",
                );
            }
            let Some(record_name) = rest.strip_suffix(':') else {
                return line_error(current.number, "Expected record name:");
            };
            if !is_identifier(record_name) || types.contains_key(record_name) {
                return line_error(current.number, "Invalid record name");
            }
            i += 1;
            let mut fields = Vec::new();
            while i < lines.len() && lines[i].indent > 0 {
                let field = &lines[i];
                if field.indent != 4 {
                    return line_error(field.number, "Record field indentation must be 4");
                }
                let Some((name, raw_type)) = field.content.split_once(": ") else {
                    return line_error(field.number, "Expected record field: type");
                };
                if !is_identifier(name) || name == "id" || fields.iter().any(|(n, _)| n == name) {
                    return line_error(field.number, "Invalid or duplicate record field");
                }
                let kind = match raw_type {
                    "int" => Kind::Int,
                    "bool" => Kind::Bool,
                    "text" => Kind::Text,
                    _ => return line_error(field.number, "Record fields must be int/bool/text"),
                };
                fields.push((name.to_owned(), kind));
                i += 1;
            }
            if fields.is_empty() || fields.len() > 16 {
                return line_error(current.number, "Record must have 1..16 fields");
            }
            declaration_spans.insert(
                format!("record:{record_name}"),
                SourceSpan {
                    line: current.number,
                    column: 1,
                },
            );
            types.insert(
                record_name.to_string(),
                Kind::Record {
                    name: record_name.to_string(),
                    fields,
                },
            );
            continue;
        } else if let Some(rest) = text.strip_prefix("fn ") {
            if seen_action_or_after || !states.is_empty() || functions.len() >= 32 {
                return line_error(current.number, "Pure functions must precede states/actions");
            }
            let Some((signature, expression)) = rest.split_once(" = ") else {
                return line_error(current.number, "Expected function body after =");
            };
            let Some((declaration, returns)) = signature.split_once(" -> ") else {
                return line_error(current.number, "Function requires explicit return type");
            };
            let Some((name, args)) = declaration.split_once('(') else {
                return line_error(current.number, "Function requires parameter list");
            };
            let Some(args) = args.strip_suffix(')') else {
                return line_error(current.number, "Unclosed function parameters");
            };
            if !is_identifier(name)
                || types.contains_key(name)
                || crate::stdlib::signature(name).is_some()
                || matches!(
                    name,
                    "append"
                        | "update"
                        | "remove"
                        | "get"
                        | "has"
                        | "count"
                        | "next_id"
                        | "filter"
                        | "map"
                        | "find"
                        | "any"
                        | "all"
                        | "sort"
                        | "sum"
                )
            {
                return line_error(current.number, "Duplicate or reserved pure function");
            }
            let mut parameters = Vec::new();
            let mut scope = types.clone();
            if !args.trim().is_empty() {
                for raw in args.split(',') {
                    let Some((param_name, raw_type)) = raw.trim().split_once(": ") else {
                        return line_error(current.number, "Invalid function parameter");
                    };
                    if !is_identifier(param_name)
                        || scope.contains_key(param_name)
                        || parameters.iter().any(|(key, _)| key == param_name)
                    {
                        return line_error(current.number, "Duplicate or reserved parameter");
                    }
                    let kind = portable_type(raw_type.trim(), &types)
                        .map_err(|e| Error(format!("Line {}: {e}", current.number)))?;
                    scope.insert(param_name.into(), kind.clone());
                    parameters.push((param_name.into(), kind));
                }
            }
            if parameters.len() > 8 {
                return line_error(current.number, "Function parameter limit exceeded");
            }
            let (returns, declared_effects) =
                if let Some(kind) = returns.strip_suffix(" effects pure") {
                    if kind.is_empty() || kind.contains(" effects ") {
                        return line_error(current.number, "Malformed effects pure annotation");
                    }
                    (kind, Some(BTreeSet::new()))
                } else if returns.contains(" effects") {
                    return line_error(
                        current.number,
                        "Only effects pure is supported for functions",
                    );
                } else {
                    (returns, None)
                };
            let result_kind = portable_type(returns.trim(), &types)
                .map_err(|e| Error(format!("Line {}: {e}", current.number)))?;
            let body = if matches!(result_kind, Kind::Result { .. }) {
                let parsed = expr::parse(expression.trim())
                    .map_err(|e| Error(format!("Line {}: {e}", current.number)))?;
                crate::typed_errors::validate_body(&parsed, &result_kind, &scope)
                    .map_err(|e| Error(format!("Line {}: {e}", current.number)))?;
                parsed
            } else {
                require_type(
                    expression.trim(),
                    &scope,
                    result_kind.clone(),
                    current.number,
                )?
            };
            let kind = Kind::Function {
                parameters: parameters.iter().map(|(_, v)| v.clone()).collect(),
                result: Box::new(result_kind.clone()),
            };
            declaration_spans.insert(
                format!("fn:{name}"),
                SourceSpan {
                    line: current.number,
                    column: 1,
                },
            );
            functions.insert(
                name.into(),
                PureFunction {
                    name: name.into(),
                    parameters,
                    result: result_kind,
                    body,
                    declared_effects,
                },
            );
            types.insert(name.into(), kind);
        } else if let Some(rest) = text.strip_prefix("state ") {
            if rest.contains(": list<") {
                if seen_action_or_after {
                    return line_error(current.number, "States must precede actions and rules");
                }
                let Some((key, spec)) = rest.split_once(": list<") else {
                    return line_error(current.number, "Invalid bounded list state");
                };
                let Some((record_name, after)) = spec.split_once(">(max=") else {
                    return line_error(current.number, "Bounded list requires max=...");
                };
                let Some(cap) = after
                    .strip_suffix(") = []")
                    .and_then(|raw| raw.parse::<usize>().ok())
                else {
                    return line_error(current.number, "Bounded list requires empty initial list");
                };
                if !is_identifier(key)
                    || types.contains_key(key)
                    || cap == 0
                    || cap > 100
                    || states
                        .values()
                        .filter(|x| matches!(x, Value::List { .. }))
                        .count()
                        >= MAX_COLLECTIONS
                {
                    return line_error(
                        current.number,
                        "Invalid or duplicate collection declaration",
                    );
                }
                let Some(record @ Kind::Record { .. }) = types.get(record_name) else {
                    return line_error(current.number, "Unknown declared record type");
                };
                let kind = Kind::List {
                    record: Box::new(record.clone()),
                    capacity: cap,
                };
                declaration_spans.insert(
                    format!("state:{key}"),
                    SourceSpan {
                        line: current.number,
                        column: 1,
                    },
                );
                state_order.push(key.to_owned());
                states.insert(
                    key.to_string(),
                    Value::List {
                        kind: kind.clone(),
                        items: vec![],
                        next_id: 1,
                    },
                );
                types.insert(key.to_string(), kind);
                i += 1;
                continue;
            }

            if seen_action_or_after {
                return line_error(current.number, "States must precede actions and rules");
            }
            let (key, value) = split_decl(rest, current.number)?;
            if states.contains_key(key) || types.contains_key(key) {
                return line_error(current.number, "Duplicate state");
            }
            // Defaults cannot depend on mutable state.
            let (expr, kind) = checked_expression(value, &BTreeMap::new(), current.number)?;
            let initial = expr::evaluate(&expr, &State::new())
                .map_err(|e| Error(format!("Line {}: {e}", current.number)))?;
            state_order.push(key.to_owned());
            declaration_spans.insert(
                format!("state:{key}"),
                SourceSpan {
                    line: current.number,
                    column: 1,
                },
            );
            states.insert(key.into(), initial);
            types.insert(key.into(), kind);
        } else if let Some(key) = text.strip_prefix("persist ") {
            if !states.contains_key(key) || !persisted.insert(key.to_owned()) {
                return line_error(current.number, "Persist requires a unique state");
            }
        } else if let Some(rest) = text.strip_prefix("derive ") {
            if seen_action_or_after {
                return line_error(current.number, "Derives must precede actions");
            }
            let (key, value) = split_decl(rest, current.number)?;
            if types.contains_key(key) {
                return line_error(current.number, "Duplicate derived identifier");
            }
            let (expr, kind) = checked_expression(value, &types, current.number)?;
            types.insert(key.into(), kind);
            declaration_spans.insert(
                format!("derive:{key}"),
                SourceSpan {
                    line: current.number,
                    column: 1,
                },
            );
            derives.push((key.into(), expr));
        } else if let Some(rest) = text.strip_prefix("action ") {
            seen_action_or_after = true;
            let Some((action, tail)) = rest.split_once(':') else {
                return line_error(current.number, "Expected action name followed by ':'");
            };
            if !is_identifier(action) || actions.contains_key(action) {
                return line_error(current.number, "Invalid or duplicate action");
            }
            if !tail.trim().is_empty() {
                lines.insert(
                    i + 1,
                    Line {
                        number: current.number,
                        indent: 4,
                        content: tail.trim().to_string(),
                    },
                );
            }
            i += 1;
            if i >= lines.len() || lines[i].indent == 0 {
                return line_error(current.number, "Empty action");
            }
            let indent = lines[i].indent;
            let state_types: BTreeMap<_, _> = states
                .iter()
                .map(|(key, val)| (key.clone(), val.kind()))
                .collect();
            let mut step_count = 0;
            let statements = parse_block(
                &lines,
                &mut i,
                indent,
                0,
                &types,
                &state_types,
                &mut step_count,
            )?;
            if statements.is_empty() {
                return line_error(current.number, "Empty action");
            }
            declaration_spans.insert(
                format!("action:{action}"),
                SourceSpan {
                    line: current.number,
                    column: 1,
                },
            );
            actions.insert(action.into(), statements);
            continue;
        } else if let Some(rest) = text.strip_prefix("rule ") {
            seen_action_or_after = true;
            rules.push(require_type(rest, &types, Kind::Bool, current.number)?);
        } else if let Some(rest) = text.strip_prefix("test ") {
            seen_action_or_after = true;
            let Some((test_name, body)) = rest.split_once(':') else {
                return line_error(current.number, "Invalid test declaration");
            };
            let Some((sequences, condition)) = body.split_once("->") else {
                return line_error(current.number, "Expected '->' in test");
            };
            if !is_identifier(test_name) || tests.iter().any(|t: &EmbeddedTest| t.name == test_name)
            {
                return line_error(current.number, "Invalid or duplicate test");
            }
            declaration_spans.insert(
                format!("test:{test_name}"),
                SourceSpan {
                    line: current.number,
                    column: 1,
                },
            );
            tests.push(EmbeddedTest {
                name: test_name.into(),
                actions: sequences
                    .split(',')
                    .map(str::trim)
                    .filter(|s| !s.is_empty())
                    .map(str::to_string)
                    .collect(),
                expected: require_type(condition.trim(), &types, Kind::Bool, current.number)?,
            });
        } else if let Some(rest) = text.strip_prefix("screen ") {
            seen_action_or_after = true;
            let Some(decl) = rest.strip_suffix(':') else {
                return line_error(current.number, "Screen requires a trailing colon");
            };
            let (screen_name, guard) = if let Some((name, guard)) = decl.split_once(" when ") {
                (
                    name,
                    Some(require_type(guard, &types, Kind::Bool, current.number)?),
                )
            } else {
                (decl, None)
            };
            if !is_identifier(screen_name)
                || screens.contains_key(screen_name)
                || screens.len() >= 32
            {
                return line_error(current.number, "Duplicate or invalid screen");
            }
            i += 1;
            if i >= lines.len() || lines[i].indent == 0 {
                return line_error(current.number, "Empty screen");
            }
            let widget_indent = lines[i].indent;
            let mut commands = Vec::new();
            let mut widgets = Vec::new();
            let mut requires_navigation = false;
            let mut count = 0;
            while i < lines.len() && lines[i].indent != 0 {
                if lines[i].indent != widget_indent {
                    return line_error(lines[i].number, "Invalid widget indentation");
                }
                let widget = &lines[i].content;
                if widget.starts_with("display ")
                    || (widget.starts_with("input ") && widget.contains(" label "))
                    || (widget.starts_with("list ") && widget.contains(" open "))
                {
                    requires_navigation = true;
                }
                if let Some(action) = parse_widget(&lines[i], &types, &states)? {
                    commands.push(action);
                }
                widgets.push(widget_ast(&lines[i], &types)?);
                count += 1;
                i += 1;
            }
            if count == 0 {
                return line_error(current.number, "Empty screen");
            }
            declaration_spans.insert(
                format!("screen:{screen_name}"),
                SourceSpan {
                    line: current.number,
                    column: 1,
                },
            );
            screens.insert(
                screen_name.to_owned(),
                Screen {
                    name: screen_name.to_owned(),
                    guard,
                    commands,
                    widgets,
                    requires_navigation,
                },
            );
            continue;
        } else if text == "navigation:" {
            seen_action_or_after = true;
            if navigation_seen {
                return line_error(current.number, "Duplicate navigation block");
            }
            navigation_seen = true;
            i += 1;
            while i < lines.len() && lines[i].indent > 0 {
                let next = &lines[i];
                if next.indent != 4 {
                    return line_error(next.number, "Navigation indentation must be four spaces");
                }
                if let Some(name) = next.content.strip_prefix("initial ") {
                    if initial_screen.is_some() || !is_identifier(name) {
                        return line_error(
                            next.number,
                            "Duplicate or invalid navigation initial screen",
                        );
                    }
                    initial_screen = Some(name.into());
                } else if let Some(rest) = next.content.strip_prefix("action ") {
                    let Some((command, destination)) = rest.split_once(" -> ") else {
                        return line_error(next.number, "Navigation command requires target");
                    };
                    let (target, action) =
                        if let Some((target, action)) = destination.split_once(" using ") {
                            (target, Some(action.to_string()))
                        } else {
                            (destination, None)
                        };
                    if !is_identifier(command)
                        || !is_identifier(target)
                        || navigation.len() >= 64
                        || navigation.contains_key(command)
                    {
                        return line_error(next.number, "Invalid/duplicate navigation command");
                    }
                    if let Some(ref action) = action {
                        if !is_identifier(action) {
                            return line_error(next.number, "Invalid action");
                        }
                    }
                    declaration_spans.insert(
                        format!("navigation:{command}"),
                        SourceSpan {
                            line: next.number,
                            column: 5,
                        },
                    );
                    navigation.insert(
                        command.into(),
                        Navigation {
                            name: command.into(),
                            target: target.into(),
                            action,
                        },
                    );
                } else {
                    return line_error(next.number, "Unknown navigation declaration");
                }
                i += 1;
            }
            continue;
        } else {
            return line_error(
                current.number,
                "Unsupported declaration in native core (records, collections, navigation, functions, WebApp and site need Python)",
            );
        }
        i += 1;
    }

    let Some(name) = name else {
        return fail("Missing app");
    };
    let has_navigation = navigation_seen || screens.len() > 1;
    let initial = if has_navigation {
        if !navigation_seen {
            return fail("Multiple screens require navigation block");
        }
        let name =
            initial_screen.ok_or_else(|| Error("Navigation requires initial screen".into()))?;
        let Some(screen) = screens.get(&name) else {
            return fail("Unknown initial screen");
        };
        if screen.guard.is_some() {
            return fail("Initial screen must be unguarded");
        }
        name
    } else {
        if screens.keys().any(|key| key != "main") {
            return fail("Non-main screen requires navigation");
        }
        if screens
            .values()
            .any(|screen| screen.guard.is_some() || screen.requires_navigation)
        {
            return fail("Extended widgets or guarded screen require navigation");
        }
        "main".into()
    };
    for (name, binding) in &navigation {
        if types.contains_key(name) || actions.contains_key(name) || screens.contains_key(name) {
            return fail(format!("Navigation name conflict: {name}"));
        }
        if binding.target != "pop" && !screens.contains_key(&binding.target) {
            return fail(format!("Unknown navigation target: {}", binding.target));
        }
        if let Some(action) = &binding.action {
            if !actions.contains_key(action) {
                return fail(format!("Unknown domain action: {action}"));
            }
        }
    }
    let mut referenced = BTreeSet::new();
    let mut reachable = BTreeSet::from([initial.clone()]);
    let mut edges: BTreeMap<String, BTreeSet<String>> = BTreeMap::new();
    for (name, screen) in &screens {
        for command in &screen.commands {
            if !actions.contains_key(command) && !navigation.contains_key(command) {
                return fail(format!("Unknown screen command: {command}"));
            }
            if let Some(binding) = navigation.get(command) {
                referenced.insert(command.clone());
                if binding.target != "pop" {
                    edges
                        .entry(name.clone())
                        .or_default()
                        .insert(binding.target.clone());
                }
            }
        }
    }
    for name in navigation.keys() {
        if !referenced.contains(name) {
            return fail(format!("Unreachable navigation binding: {name}"));
        }
    }
    if has_navigation {
        loop {
            let old = reachable.len();
            let known: Vec<String> = reachable.iter().cloned().collect();
            for name in known {
                if let Some(targets) = edges.get(&name) {
                    reachable.extend(targets.iter().cloned());
                }
            }
            if old == reachable.len() {
                break;
            }
        }
        for name in screens.keys() {
            if !reachable.contains(name) {
                return fail(format!("Unreachable screen: {name}"));
            }
        }
    }
    for test in &tests {
        for action in &test.actions {
            if !actions.contains_key(action) && !navigation.contains_key(action) {
                return fail(format!("Unknown test action: {action}"));
            }
        }
    }
    let program = Program {
        name,
        states,
        state_order,
        declaration_spans,
        persistent: persisted,
        types,
        derives,
        functions,
        actions,
        rules,
        tests,
        screens,
        navigation,
        initial_screen: initial,
        has_navigation,
    };
    // A1: audit the typed function domain before any backend can consume it.
    // The result is NOT a grant of filesystem/network privileges.
    crate::effects::infer_program(&program)?;
    let initial = crate::runtime::resolve(&program, &program.states)?;
    if !crate::runtime::rules_hold(&program, &initial)? {
        return fail("Invalid initial state");
    }
    Ok(program)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn accepts_scalar_counter() {
        let p = parse(
            "app \"Counter\"\nstate count = 0\naction add: count = count + 1\n\
             rule count >= 0\ntest once: add -> count == 1\nscreen main:\n    text \"Hello\"\n    value count\n    button \"Add\" -> add\n",
        )
        .unwrap();
        assert_eq!(p.tests.len(), 1);
        assert_eq!(p.states.get("count"), Some(&Value::Int(0)));
    }

    #[test]
    fn unsupported_features_and_bad_types_fail_loudly() {
        assert!(parse("app \"X\"\nrecord Task:\n    id: text").is_err());
        assert!(parse("app \"X\"\nstate a = 1\nrule a").is_err());
        assert!(parse("app \"X\"\nstate a = 1\naction up: a = \"wrong\"").is_err());
    }
}
