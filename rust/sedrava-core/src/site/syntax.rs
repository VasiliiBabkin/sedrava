use super::assets::read_local;
use crate::model::{fail, Error, Result, MAX_SOURCE_CHARS};
use regex::Regex;
use std::{
    collections::{BTreeMap, BTreeSet},
    path::{Path, PathBuf},
};

pub(super) const MAX_DEPTH: usize = 32;

#[derive(Clone)]
pub(super) struct Line {
    pub number: usize,
    pub depth: usize,
    pub text: String,
}

impl Line {
    pub fn error(&self, message: impl std::fmt::Display) -> Error {
        Error(format!(
            "Line {}: column {}: {message}",
            self.number,
            self.depth * 4 + 1
        ))
    }
}

pub(super) fn lines(source: &str) -> Result<Vec<Line>> {
    if source.chars().count() > MAX_SOURCE_CHARS {
        return fail("Site source exceeds size limit");
    }
    let mut lines = Vec::new();
    for (i, raw) in source.lines().enumerate() {
        let spaces = raw.bytes().take_while(|&c| c == b' ').count();
        let text = raw[spaces..].trim_end();
        let line = Line {
            number: i + 1,
            depth: spaces / 4,
            text: text.into(),
        };
        if text.starts_with(['\t', '\u{feff}']) {
            return Err(line.error("Invalid Site indentation or nesting"));
        }
        if text.is_empty() || text.starts_with('#') {
            continue;
        }
        if spaces % 4 != 0 || line.depth > MAX_DEPTH {
            return Err(line.error("Invalid Site indentation or nesting"));
        }
        lines.push(line);
    }
    Ok(lines)
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub(super) enum Token {
    Word(String),
    Text(String),
    Int(i32),
    Bool(bool),
    Colon,
}

pub(super) fn identifier(s: &str) -> bool {
    s.len() <= 64
        && s.starts_with(|c: char| c.is_ascii_alphabetic())
        && s.bytes()
            .all(|c| c.is_ascii_alphanumeric() || b"_-".contains(&c))
}

pub(super) fn tokens(line: &Line, mut input: &str) -> Result<Vec<Token>> {
    let mut tokens = Vec::new();
    while !input.trim_start_matches(' ').is_empty() {
        input = input.trim_start_matches(' ');
        if let Some(rest) = input.strip_prefix(':') {
            tokens.push(Token::Colon);
            input = rest;
            continue;
        }
        if input.starts_with('"') {
            let mut json = serde_json::Deserializer::from_str(input).into_iter::<String>();
            let value = json
                .next()
                .expect("nonempty literal")
                .map_err(|_| line.error("Invalid quoted string"))?;
            if value.chars().any(|c| {
                (c < ' ' && !matches!(c, '\n' | '\r' | '\t'))
                    || matches!(c, '\u{fffe}' | '\u{ffff}')
            }) {
                return Err(line.error("Unsafe text characters"));
            }
            input = &input[json.byte_offset()..];
            tokens.push(Token::Text(value));
            continue;
        }
        let end = input.find([' ', ':']).unwrap_or(input.len());
        let value = &input[..end];
        tokens.push(match value {
            "true" => Token::Bool(true),
            "false" => Token::Bool(false),
            _ if value.starts_with(|c: char| c.is_ascii_digit() || c == '-') => {
                Token::Int(value.parse().map_err(|_| line.error("Invalid integer"))?)
            }
            _ if identifier(value) => Token::Word(value.into()),
            _ => return Err(line.error("Invalid token")),
        });
        input = &input[end..];
    }
    Ok(tokens)
}

struct Template {
    parameters: BTreeMap<String, String>,
    body: Vec<Line>,
}

fn block(lines: &[Line], start: usize, depth: usize) -> usize {
    start
        + lines[start..]
            .iter()
            .take_while(|l| l.depth > depth)
            .count()
}

fn imports(
    source: &str,
    root: Option<&Path>,
    webapp: bool,
    parent: &Path,
    stack: &mut Vec<PathBuf>,
    count: &mut usize,
    budget: &mut usize,
    out: &mut Vec<Line>,
) -> Result<()> {
    for line in lines(source)? {
        if line.depth == 0 {
            let keyword = line.text.split(' ').next().unwrap_or("");
            if keyword == "import" {
                let [Token::Text(path)] = &tokens(&line, &line.text[6..])?[..] else {
                    return Err(line.error("Expected a quoted Site module path"));
                };
                let root =
                    root.ok_or_else(|| line.error("Site imports require a source directory"))?;
                let (file, bytes) = read_local(root, parent, path, &["sdr"], MAX_SOURCE_CHARS * 4)?;
                if *count >= 32 || stack.len() >= 16 || stack.contains(&file) {
                    return Err(line.error("Cyclic or excessive Site imports"));
                }
                *count += 1;
                let source =
                    std::str::from_utf8(&bytes).map_err(|_| line.error("Module must use UTF-8"))?;
                stack.push(file.clone());
                imports(
                    source,
                    Some(root),
                    webapp,
                    file.parent().unwrap_or(root),
                    stack,
                    count,
                    budget,
                    out,
                )?;
                stack.pop();
                continue;
            }
            if !(stack.is_empty()
                || matches!(keyword, "component" | "style")
                || webapp && matches!(keyword, "fn" | "record"))
            {
                return Err(line.error("Unsupported declaration in local presentation module"));
            }
        }
        *budget += line.text.len() + 4 * line.depth + 1;
        if *budget > MAX_SOURCE_CHARS * 4 {
            return Err(line.error("Expanded Site imports exceed size limit"));
        }
        out.push(line);
    }
    Ok(())
}

pub(super) fn expand(source: &str, root: Option<&Path>, webapp: bool) -> Result<Vec<Line>> {
    let declaration = Regex::new(r"^component ([A-Za-z][A-Za-z0-9_]*)(?:\(([^()]*)\))?:$").unwrap();
    let mut all = Vec::new();
    imports(
        source,
        root,
        webapp,
        root.unwrap_or(Path::new(".")),
        &mut Vec::new(),
        &mut 0,
        &mut 0,
        &mut all,
    )?;
    if all
        .iter()
        .map(|line| line.text.chars().count() + line.depth * 4 + 1)
        .sum::<usize>()
        > MAX_SOURCE_CHARS
    {
        return fail("Expanded imports exceed source size limit");
    }
    let mut templates = BTreeMap::new();
    let mut kept = Vec::new();
    let mut i = 0;
    while i < all.len() {
        let line = &all[i];
        i += 1;
        if line.depth != 0 || !line.text.starts_with("component ") {
            kept.push(line.clone());
            continue;
        }
        let matched = declaration
            .captures(&line.text)
            .ok_or_else(|| line.error("Invalid component declaration"))?;
        let mut parameters = BTreeMap::new();
        if let Some(args) = matched.get(2).filter(|m| !m.as_str().is_empty()) {
            for arg in args.as_str().split(',') {
                let (name, kind) = arg
                    .split_once(':')
                    .ok_or_else(|| line.error("Expected typed component parameter"))?;
                let (name, kind) = (name.trim(), kind.trim());
                if !identifier(name)
                    || name.contains('-')
                    || !matches!(kind, "text" | "int" | "bool" | "ref")
                    || parameters.insert(name.into(), kind.into()).is_some()
                {
                    return Err(line.error("Invalid or duplicate component parameter"));
                }
            }
        }
        let end = block(&all, i, 0);
        if end == i || all[i].depth != 1 {
            return Err(line.error("Component requires an indented body"));
        }
        let body = all[i..end].to_vec();
        if body.iter().filter(|line| line.text == "slot").count() > 1
            || templates
                .insert(matched[1].to_owned(), Template { parameters, body })
                .is_some()
        {
            return Err(line.error("Duplicate component name or slot"));
        }
        i = end;
    }
    let substitution = Regex::new(r#"("(?:[^"\\]|\\.)*")|\$([A-Za-z][A-Za-z0-9_]*)"#).unwrap();
    let mut out = Vec::new();
    instantiate(
        &kept,
        &templates,
        &substitution,
        &mut BTreeSet::new(),
        &mut 0,
        &mut out,
    )?;
    if out
        .iter()
        .map(|line| line.text.chars().count() + line.depth * 4 + 1)
        .sum::<usize>()
        > MAX_SOURCE_CHARS
    {
        return fail("Expanded components exceed source size limit");
    }
    Ok(out)
}

fn instantiate(
    lines: &[Line],
    templates: &BTreeMap<String, Template>,
    substitution: &Regex,
    stack: &mut BTreeSet<String>,
    budget: &mut usize,
    out: &mut Vec<Line>,
) -> Result<()> {
    let mut i = 0;
    while i < lines.len() {
        let line = &lines[i];
        i += 1;
        *budget += line.text.len() + line.depth * 4 + 1;
        if *budget > MAX_SOURCE_CHARS * 4 || line.depth > MAX_DEPTH {
            return Err(line.error("Expanded Site components exceed size or depth limit"));
        }
        let Some(args) = line.text.strip_prefix("use ") else {
            out.push(line.clone());
            continue;
        };
        let args = tokens(line, args)?;
        let Some(Token::Word(name)) = args.first() else {
            return Err(line.error("Expected a component name"));
        };
        let template = templates
            .get(name)
            .ok_or_else(|| line.error(format!("Unknown component {name}")))?;
        if stack.len() >= MAX_DEPTH || !stack.insert(name.clone()) {
            return Err(line.error("Recursive or excessive component expansion"));
        }
        let has_block = args.last() == Some(&Token::Colon);
        let pairs = &args[1..args.len() - usize::from(has_block)];
        if pairs.len() != template.parameters.len() * 2 {
            return Err(line.error("Component requires exact parameters"));
        }
        let mut values = BTreeMap::new();
        for pair in pairs.chunks_exact(2) {
            let Token::Word(key) = &pair[0] else {
                return Err(line.error("Expected a component parameter name"));
            };
            let value = match (template.parameters.get(key).map(String::as_str), &pair[1]) {
                (Some("text"), Token::Text(v) | Token::Word(v)) => {
                    serde_json::to_string(v).unwrap()
                }
                (Some("int"), Token::Int(v)) => v.to_string(),
                (Some("bool"), Token::Bool(v)) => v.to_string(),
                (Some("ref"), Token::Word(v)) if !v.contains('-') => v.clone(),
                _ => return Err(line.error(format!("Invalid typed component parameter {key}"))),
            };
            if values.insert(key.as_str(), value).is_some() {
                return Err(line.error("Duplicate component parameter"));
            }
        }
        let end = if has_block {
            block(lines, i, line.depth)
        } else {
            i
        };
        if has_block != (end > i)
            || has_block != template.body.iter().any(|l| l.text == "slot")
            || (has_block && lines[i].depth != line.depth + 1)
        {
            return Err(line.error("Component slot requires matching indented content"));
        }
        let mut expanded = Vec::new();
        let mut expanded_bytes = 0;
        for item in &template.body {
            if item.text == "slot" {
                expanded_bytes += lines[i..end]
                    .iter()
                    .map(|row| row.text.len())
                    .sum::<usize>();
                if expanded_bytes > MAX_SOURCE_CHARS * 4 {
                    return Err(line.error("Expanded component exceeds size limit"));
                }
                expanded.extend(lines[i..end].iter().cloned().map(|mut child| {
                    child.depth = (child.depth - 1) + (item.depth - 1);
                    child
                }));
                continue;
            }
            let mut text = String::new();
            let mut offset = 0;
            for captures in substitution.captures_iter(&item.text) {
                let matched = captures.get(0).unwrap();
                text.push_str(&item.text[offset..matched.start()]);
                if let Some(key) = captures.get(2) {
                    text.push_str(
                        values
                            .get(key.as_str())
                            .ok_or_else(|| item.error("Unknown component parameter"))?,
                    );
                } else {
                    text.push_str(matched.as_str());
                }
                if text.len() > MAX_SOURCE_CHARS * 4 {
                    return Err(line.error("Expanded component text exceeds size limit"));
                }
                offset = matched.end();
            }
            text.push_str(&item.text[offset..]);
            expanded_bytes += text.len();
            if expanded_bytes > MAX_SOURCE_CHARS * 4 {
                return Err(line.error("Expanded component exceeds size limit"));
            }
            expanded.push(Line {
                text,
                depth: line.depth + item.depth - 1,
                number: item.number,
            });
        }
        instantiate(&expanded, templates, substitution, stack, budget, out)?;
        stack.remove(name);
        i = end;
    }
    Ok(())
}
