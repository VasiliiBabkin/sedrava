//! Bounded native namespace lowering: no dynamic imports or Python runtime.
use crate::model::{fail, Result};
use std::collections::BTreeMap;

pub type AliasMap = BTreeMap<String, BTreeMap<String, String>>;
const RESERVED: &str = "__sdns_";

/// Detect generated symbols outside quoted source strings and comments.
pub fn reserved_identifier(source: &str) -> bool {
    let bytes = source.as_bytes();
    let (mut pos, mut quoted, mut escaped) = (0, false, false);
    while pos < bytes.len() {
        let b = bytes[pos];
        if quoted {
            if escaped {
                escaped = false;
            } else if b == b'\\' {
                escaped = true;
            } else if b == b'"' {
                quoted = false;
            }
            pos += 1;
            continue;
        }
        if b == b'#' {
            while pos < bytes.len() && bytes[pos] != b'\n' {
                pos += 1;
            }
            continue;
        }
        if b == b'"' {
            quoted = true;
            pos += 1;
            continue;
        }
        if b.is_ascii_alphabetic() || b == b'_' {
            let start = pos;
            pos += 1;
            while pos < bytes.len() && (bytes[pos].is_ascii_alphanumeric() || bytes[pos] == b'_') {
                pos += 1;
            }
            if source[start..pos].starts_with(RESERVED) {
                return true;
            }
        } else {
            pos += 1;
        }
    }
    false
}

fn ident(s: &str) -> bool {
    let mut chars = s.chars();
    matches!(chars.next(), Some(x) if x.is_ascii_alphabetic())
        && chars.all(|x| x.is_ascii_alphanumeric() || x == '_')
}

pub fn alias_spec(line: &str) -> Result<Option<(&str, &str)>> {
    if !line.starts_with("import ") || !line.contains(" as ") {
        return Ok(None);
    }
    let Some((path, alias)) = line
        .strip_prefix("import \"")
        .and_then(|s| s.split_once("\" as "))
    else {
        return fail("E_IMPORT_ALIAS: expected import \"path.sdr\" as alias");
    };
    if path.contains('"')
        || !path.ends_with(".sdr")
        || !ident(alias)
        || alias.len() > 32
        || alias.starts_with("sdns_")
        || matches!(
            alias,
            "self"
                | "super"
                | "true"
                | "false"
                | "None"
                | "Result"
                | "Error"
                | "int"
                | "text"
                | "bool"
                | "list"
                | "fn"
                | "record"
                | "error"
                | "match"
                | "state"
                | "app"
                | "import"
                | "if"
                | "else"
                | "let"
                | "action"
                | "rule"
                | "test"
                | "screen"
                | "derive"
                | "persist"
                | "and"
                | "or"
                | "not"
                | "return"
        )
    {
        return fail("E_IMPORT_ALIAS: invalid path or namespace");
    }
    Ok(Some((path, alias)))
}

fn export(line: &str) -> Option<&str> {
    if line.starts_with(char::is_whitespace) {
        return None;
    }
    if let Some(rest) = line.strip_prefix("record ") {
        return rest.strip_suffix(':');
    }
    if let Some(rest) = line.strip_prefix("error ") {
        let (_, spec) = rest.split_once(' ')?;
        let body = spec.strip_suffix(':')?;
        return Some(body.split_once(" id ").map_or(body, |(name, _)| name));
    }
    line.strip_prefix("fn ")?.split_once('(').map(|(x, _)| x)
}

/// Lexical rewrite: preserve quoted text and comments, skip field and
/// attribute names and named keyword labels. The caller prohibits parameter
/// shadowing and never applies this to record/error field declaration lines.
fn local(line: &str, exports: &BTreeMap<String, String>) -> String {
    let b = line.as_bytes();
    let (mut pos, mut copied) = (0, 0);
    let (mut quoted, mut escaped) = (false, false);
    let mut out = String::with_capacity(line.len());
    while pos < b.len() {
        let ch = b[pos];
        if quoted {
            if escaped {
                escaped = false
            } else if ch == b'\\' {
                escaped = true
            } else if ch == b'"' {
                quoted = false
            }
            pos += 1;
            continue;
        }
        if ch == b'#' {
            break;
        }
        if ch == b'"' {
            quoted = true;
            pos += 1;
            continue;
        }
        if ch.is_ascii_alphabetic() || ch == b'_' {
            let start = pos;
            pos += 1;
            while pos < b.len() && (b[pos].is_ascii_alphanumeric() || b[pos] == b'_') {
                pos += 1
            }
            let token = &line[start..pos];
            let after = line[pos..].trim_start();
            if !line[..start].trim_end().ends_with('.') && !after.starts_with('=') {
                if let Some(new) = exports.get(token) {
                    out.push_str(&line[copied..start]);
                    out.push_str(new);
                    copied = pos;
                }
            }
        } else {
            pos += 1
        }
    }
    out.push_str(&line[copied..]);
    out
}

/// Substitute only declared namespace exports, never arbitrary dotted
/// selectors. Root alias tokens without a member are a compile error.
pub fn qualified(source: &str, aliases: &AliasMap) -> Result<String> {
    if aliases.is_empty() {
        return Ok(source.into());
    }
    let b = source.as_bytes();
    let (mut pos, mut copied) = (0, 0);
    let (mut quoted, mut escaped) = (false, false);
    let mut out = String::new();
    while pos < b.len() {
        let ch = b[pos];
        if quoted {
            if escaped {
                escaped = false
            } else if ch == b'\\' {
                escaped = true
            } else if ch == b'"' {
                quoted = false
            }
            pos += 1;
            continue;
        }
        if ch == b'#' {
            while pos < b.len() && b[pos] != b'\n' {
                pos += 1
            }
            continue;
        }
        if ch == b'"' {
            quoted = true;
            pos += 1;
            continue;
        }
        if ch.is_ascii_alphabetic() || ch == b'_' {
            let start = pos;
            pos += 1;
            while pos < b.len() && (b[pos].is_ascii_alphanumeric() || b[pos] == b'_') {
                pos += 1
            }
            let token = &source[start..pos];
            if let Some(exports) = aliases.get(token) {
                if start > 0 && b[start - 1] == b'.' {
                    // Field selector with the same spelling as a namespace.
                    continue;
                }
                if pos >= b.len() || b[pos] != b'.' {
                    return fail(format!(
                        "E_IMPORT_ALIAS: reserved namespace {token} requires a member"
                    ));
                }
                let begin = pos + 1;
                let mut end = begin;
                while end < b.len() && (b[end].is_ascii_alphanumeric() || b[end] == b'_') {
                    end += 1
                }
                let member = &source[begin..end];
                if !ident(member) {
                    return fail("E_IMPORT_ALIAS: invalid namespace member");
                }
                let Some(value) = exports.get(member) else {
                    return fail(format!("E_IMPORT_ALIAS: unknown export {token}.{member}"));
                };
                out.push_str(&source[copied..start]);
                out.push_str(value);
                copied = end;
                pos = end;
            }
        } else {
            pos += 1
        }
    }
    out.push_str(&source[copied..]);
    Ok(out)
}

/// Aliased files are simple libraries with declarations only. Error IDs
/// remain exactly those written by the author; no implicit entry.* prefix.
pub fn lower(source: &str, alias: &str) -> Result<(String, BTreeMap<String, String>)> {
    if reserved_identifier(source) {
        return fail("E_IMPORT_ALIAS: internal namespace prefix is reserved in module source");
    }
    let mut exports = BTreeMap::new();
    for line in source.lines() {
        if line.trim().is_empty() || line.trim_start().starts_with('#') {
            continue;
        }
        if line.starts_with("import ")
            || line.starts_with("component ")
            || line.starts_with("style ")
            || line.starts_with("app ")
        {
            return fail("E_IMPORT_ALIAS: only fn/record/error exports, no nested import");
        }
        if !line.starts_with(char::is_whitespace) {
            let Some(name) = export(line) else {
                return fail("E_IMPORT_ALIAS: unsupported library declaration");
            };
            if !ident(name)
                || name.len() > 64
                || name.starts_with(RESERVED)
                || exports.len() >= 32
                || exports.contains_key(name)
            {
                return fail("E_IMPORT_ALIAS: invalid, duplicate or too many exports");
            }
            if line.starts_with("error ") && !line.contains(" id \"") {
                return fail("E_IMPORT_ALIAS: error needs a stable explicit id");
            }
            let renamed = format!("{RESERVED}{alias}_{name}");
            if renamed.len() > 128 {
                return fail("E_IMPORT_ALIAS: generated name too long");
            }
            exports.insert(name.to_string(), renamed);
        }
    }
    if exports.is_empty() {
        return fail("E_IMPORT_ALIAS: empty library");
    }
    // Fail closed when a function parameter shadows any exported name.
    for line in source.lines() {
        if let Some(fnline) = line.strip_prefix("fn ") {
            let Some((_, tail)) = fnline.split_once('(') else {
                return fail("E_IMPORT_ALIAS: malformed function signature");
            };
            let Some((args, _)) = tail.split_once(')') else {
                return fail("E_IMPORT_ALIAS: malformed function parameters");
            };
            for arg in args.split(',').filter(|a| !a.trim().is_empty()) {
                let Some((name, _)) = arg.trim().split_once(':') else {
                    return fail("E_IMPORT_ALIAS: invalid function argument");
                };
                if exports.contains_key(name.trim()) {
                    return fail("E_IMPORT_ALIAS: parameter shadows a module export");
                }
            }
        }
    }
    let (mut output, mut in_fields) = (Vec::new(), false);
    for line in source.lines() {
        if line.trim().is_empty() || line.trim_start().starts_with('#') {
            output.push(line.to_owned());
            continue;
        }
        if !line.starts_with(char::is_whitespace) {
            in_fields = line.starts_with("record ") || line.starts_with("error ");
            output.push(local(line, &exports));
        } else if in_fields {
            output.push(line.to_owned());
        } else {
            output.push(local(line, &exports));
        }
    }
    Ok((output.join("\n"), exports))
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn quoted_literals_and_field_labels_survive() {
        let exports = BTreeMap::from([
            ("Fault".into(), "__sdns_math_Fault".into()),
            ("plus".into(), "__sdns_math_plus".into()),
        ]);
        assert_eq!(
            local("Fault.Bad(plus=plus)", &exports),
            "__sdns_math_Fault.Bad(plus=__sdns_math_plus)"
        );
        assert_eq!(
            local(
                "fn plus(x: text) -> text = concat(\"Fault plus\", x)",
                &exports
            ),
            "fn __sdns_math_plus(x: text) -> text = concat(\"Fault plus\", x)"
        );
    }
    #[test]
    fn only_known_members_lowered() {
        let aliases = AliasMap::from([(
            "math".into(),
            BTreeMap::from([("plus".into(), "__sdns_math_plus".into())]),
        )]);
        assert_eq!(
            qualified(
                "math.plus(1) == 2 and \"math.plus\" == \"math.plus\" # math.plus",
                &aliases
            )
            .unwrap(),
            "__sdns_math_plus(1) == 2 and \"math.plus\" == \"math.plus\" # math.plus"
        );
        assert!(qualified("math.missing(1)", &aliases).is_err());
        assert!(qualified("math", &aliases).is_err());
    }
    #[test]
    fn namespace_fields_are_not_hijacked() {
        let aliases = AliasMap::from([(
            "left".into(),
            BTreeMap::from([("twice".into(), "__sdns_left_twice".into())]),
        )]);
        assert_eq!(
            qualified("record.left == 1", &aliases).unwrap(),
            "record.left == 1"
        );
        assert!(reserved_identifier("state __sdns_fake = 1"));
        assert!(!reserved_identifier(
            "app \"__sdns_label\"\\n# __sdns_comment"
        ));
        assert!(!reserved_identifier("state suffix__sdns_ = 1"));
    }
    #[test]
    fn local_calls_rewrite_together() {
        let (s, e) = lower(
            "fn base(x: int) -> int = x + 1\nfn next(x: int) -> int = base(x) * 2",
            "math",
        )
        .unwrap();
        assert!(s.contains("fn __sdns_math_next"));
        assert!(s.contains("__sdns_math_base(x) * 2"));
        assert_eq!(e.len(), 2);
    }
}
