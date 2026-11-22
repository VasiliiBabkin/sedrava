//! Parser for the currently supported scalar application subset.
//!
//! Unsupported 0.11 features are rejected explicitly, not silently ignored.
//! This module does NOT claim complete Sedrava language compatibility.

use crate::expr;
use crate::model::{
    fail, EmbeddedTest, Error, Expr, Kind, Program, Result, State, Stmt, Value, MAX_ACTION_STEPS,
    MAX_BLOCK_DEPTH, MAX_SOURCE_CHARS,
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
                require_type(value, &scope, *kind, number)?,
            ));
        } else {
            return line_error(number, "Unsupported statement in native core");
        }
        *pos += 1;
    }
    Ok(body)
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
        if !types.contains_key(name) {
            return line_error(number, "Unknown value state or derive");
        }
    } else if let Some(name) = text.strip_prefix("input ") {
        if !matches!(states.get(name), Some(Value::Int(_)) | Some(Value::Text(_))) {
            return line_error(number, "Input requires int or text state");
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

/// Parse scalar app semantics, including states, derives, rules, actions, tests
/// and simple screens. Records, collections, nav and site/webapp are NOT supported.
pub fn parse(source: &str) -> Result<Program> {
    let mut lines = source_lines(source)?;
    let mut name: Option<String> = None;
    let mut states = State::new();
    let mut types = BTreeMap::new();
    let mut derives = Vec::new();
    let mut actions = BTreeMap::new();
    let mut rules = Vec::new();
    let mut tests = Vec::new();
    let mut persisted = BTreeSet::new();
    let mut widgets_actions = Vec::new();
    let mut seen_action_or_after = false;
    let mut seen_screen = false;
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
        } else if let Some(rest) = text.strip_prefix("state ") {
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
        } else if text == "screen main:" {
            seen_action_or_after = true;
            if seen_screen {
                return line_error(current.number, "Duplicate screen main");
            }
            seen_screen = true;
            i += 1;
            if i >= lines.len() || lines[i].indent == 0 {
                return line_error(current.number, "Empty screen");
            }
            let widget_indent = lines[i].indent;
            let mut count = 0;
            while i < lines.len() && lines[i].indent != 0 {
                if lines[i].indent != widget_indent {
                    return line_error(lines[i].number, "Invalid widget indentation");
                }
                if let Some(action) = parse_widget(&lines[i], &types, &states)? {
                    widgets_actions.push(action);
                }
                count += 1;
                i += 1;
            }
            if count == 0 {
                return line_error(current.number, "Empty screen");
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
    for test in &tests {
        for action in &test.actions {
            if !actions.contains_key(action) {
                return fail(format!("Unknown test action: {action}"));
            }
        }
    }
    for action in widgets_actions {
        if !actions.contains_key(&action) {
            return fail(format!("Unknown button action: {action}"));
        }
    }
    let program = Program {
        name,
        states,
        types,
        derives,
        actions,
        rules,
        tests,
    };
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
        assert!(parse("app \"X\"\nrecord Task:\n    title: text").is_err());
        assert!(parse("app \"X\"\nstate a = 1\nrule a").is_err());
        assert!(parse("app \"X\"\nstate a = 1\naction up: a = \"wrong\"").is_err());
    }
}
