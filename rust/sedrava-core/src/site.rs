//! Native static Site DSL preview. The subset is deliberately narrow:
//! unknown directives and modifiers fail, rather than silently disappearing.
//! This is NOT a replacement for the Python 0.11 Site compiler.

use crate::model::{fail, Error, Result, MAX_SOURCE_CHARS};
use std::collections::BTreeMap;

const MAX_PAGES: usize = 32;
const MAX_NESTING: usize = 20;

#[derive(Debug, Clone)]
struct Line {
    number: usize,
    indent: usize,
    text: String,
}

#[derive(Debug)]
pub struct StaticSite {
    /// Safe, relative file names only; the caller stages the directory atomically.
    pub files: BTreeMap<String, String>,
}

fn error<T>(line: usize, message: &str) -> Result<T> {
    fail(format!("Line {line}: {message}"))
}

fn lines(source: &str) -> Result<Vec<Line>> {
    if source.chars().count() > MAX_SOURCE_CHARS {
        return fail("Site source exceeds size limit");
    }
    let mut result = Vec::new();
    for (index, raw) in source.lines().enumerate() {
        let number = index + 1;
        if raw.starts_with('\u{feff}') {
            return error(number, "UTF-8 BOM is unsupported");
        }
        let indent = raw.chars().take_while(|ch| *ch == ' ' || *ch == '\t').count();
        if raw.chars().take(indent).any(|ch| ch == '\t') {
            return error(number, "Tabs in indentation are unsupported");
        }
        let value = raw.trim();
        if value.is_empty() || value.starts_with('#') {
            continue;
        }
        if indent % 4 != 0 {
            return error(number, "Indentation must use multiples of four spaces");
        }
        result.push(Line {
            number,
            indent,
            text: value.to_owned(),
        });
    }
    Ok(result)
}

fn quoted(input: &str, line: usize) -> Result<(String, &str)> {
    if !input.starts_with('"') {
        return error(line, "Expected a JSON-compatible quoted string");
    }
    let mut escaped = false;
    for (offset, ch) in input.char_indices().skip(1) {
        if escaped {
            escaped = false;
            continue;
        }
        if ch == '\\' {
            escaped = true;
        } else if ch == '"' {
            let value = serde_json::from_str::<String>(&input[..=offset])
                .map_err(|_| Error(format!("Line {line}: Invalid quoted string")))?;
            return Ok((value, input[offset + 1..].trim_start()));
        }
    }
    error(line, "Unclosed string literal")
}

fn only_quoted(input: &str, line: usize) -> Result<String> {
    let (value, remaining) = quoted(input, line)?;
    if !remaining.is_empty() {
        return error(line, "Unexpected modifiers (not supported in native Site preview)");
    }
    Ok(value)
}

fn html(raw: &str) -> String {
    raw.replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
        .replace('"', "&quot;")
        .replace('\'', "&#39;")
}

fn valid_href(value: &str) -> bool {
    if value.is_empty()
        || value.contains('\\')
        || value.chars().any(|c| c.is_control() || c.is_whitespace())
    {
        return false;
    }
    if let Some(host_path) = value.strip_prefix("https://") {
        let host = host_path.split(&['/', '?', '#'][..]).next().unwrap_or("");
        return !host.is_empty() && !host.starts_with('.') && !host.contains('@')
            && host.chars().all(|c| c.is_ascii_alphanumeric() || ".-:".contains(c));
    }
    if value.starts_with("//") || value.contains("..") {
        return false;
    }
    value.starts_with('/') || (value.starts_with('#') && value.len() > 1)
}

fn output_path(route: &str, line: usize) -> Result<String> {
    if route == "/" {
        return Ok("index.html".to_owned());
    }
    if !route.starts_with('/') || !route.ends_with('/') || route.contains("//") {
        return error(line, "Page route must be / or /safe/segments/");
    }
    let pieces: Vec<_> = route.trim_matches('/').split('/').collect();
    if pieces.is_empty()
        || pieces.iter().any(|segment| {
            segment.is_empty()
                || segment == &"."
                || segment == &".."
                || !segment.chars().all(|c| c.is_ascii_alphanumeric() || c == '-' || c == '_')
        })
    {
        return error(line, "Unsafe page route");
    }
    Ok(format!("{}/index.html", pieces.join("/")))
}

fn parse_nodes(lines: &[Line], index: &mut usize, indent: usize, depth: usize) -> Result<String> {
    if depth > MAX_NESTING {
        return fail("Site layout nesting exceeds limit");
    }
    let mut out = String::new();
    while *index < lines.len() && lines[*index].indent >= indent {
        let current = &lines[*index];
        if current.indent != indent {
            return error(current.number, "Unexpected indentation in layout");
        }
        *index += 1;
        if let Some(block) = current.text.strip_suffix(':') {
            let (tag, class) = match block {
                "container" => ("main", "site-container"),
                "column" => ("div", "site-column"),
                "row" => ("div", "site-row"),
                "grid" => ("div", "site-grid"),
                "card" => ("section", "site-card"),
                "navbar" => ("nav", "site-nav"),
                "footer" => ("footer", "site-footer"),
                "callout" => ("aside", "site-callout"),
                _ => return error(current.number, "Unsupported Site layout or modifiers"),
            };
            out.push_str(&format!("<{tag} class=\"{class}\">\n"));
            if *index >= lines.len() || lines[*index].indent <= indent {
                return error(current.number, "Layout block requires a child");
            }
            out.push_str(&parse_nodes(lines, index, indent + 4, depth + 1)?);
            out.push_str(&format!("</{tag}>\n"));
        } else if let Some(rest) = current.text.strip_prefix("heading ") {
            out.push_str(&format!("<h1>{}</h1>\n", html(&only_quoted(rest, current.number)?)));
        } else if let Some(rest) = current.text.strip_prefix("paragraph ") {
            out.push_str(&format!("<p>{}</p>\n", html(&only_quoted(rest, current.number)?)));
        } else if let Some(rest) = current.text.strip_prefix("code ") {
            out.push_str(&format!(
                "<pre><code>{}</code></pre>\n",
                html(&only_quoted(rest, current.number)?)
            ));
        } else if current.text == "divider" {
            out.push_str("<hr>\n");
        } else if let Some(rest) = current
            .text
            .strip_prefix("link ")
            .or_else(|| current.text.strip_prefix("button "))
        {
            let (label, remainder) = quoted(rest, current.number)?;
            let href_src = remainder
                .strip_prefix("to ")
                .ok_or_else(|| Error(format!("Line {}: Expected 'to' after link label", current.number)))?;
            let destination = only_quoted(href_src, current.number)?;
            if !valid_href(&destination) {
                return error(current.number, "Unsafe or unsupported link destination");
            }
            out.push_str(&format!(
                "<a href=\"{}\">{}</a>\n",
                html(&destination),
                html(&label)
            ));
        } else {
            return error(current.number, "Unsupported Site node or modifier");
        }
    }
    Ok(out)
}

pub fn generate(source: &str) -> Result<StaticSite> {
    let source_lines = lines(source)?;
    let first = source_lines
        .first()
        .ok_or_else(|| Error("Empty Site source".to_owned()))?;
    if first.indent != 0 {
        return error(first.number, "Expected site declaration at column 1");
    }
    let site_name = first
        .text
        .strip_prefix("site ")
        .ok_or_else(|| Error("Expected site declaration".to_owned()))?;
    let name = only_quoted(site_name, first.number)?;
    if name.is_empty() {
        return error(first.number, "Empty site name");
    }
    let mut index = 1;
    let mut files = BTreeMap::new();
    while index < source_lines.len() {
        let header = &source_lines[index];
        if header.indent != 0 {
            return error(header.number, "Expected top-level page declaration");
        }
        let page_header = header
            .text
            .strip_prefix("page ")
            .and_then(|s| s.strip_suffix(':'))
            .ok_or_else(|| Error(format!(
                "Line {}: Native Site preview only supports page declarations",
                header.number
            )))?;
        let (slug, route_text) = page_header
            .split_once(" at ")
            .ok_or_else(|| Error(format!("Line {}: Expected 'page name at \"/\":'", header.number)))?;
        if slug.is_empty()
            || !slug.chars().next().is_some_and(|ch| ch.is_ascii_alphabetic())
            || !slug.chars().all(|ch| ch.is_ascii_alphanumeric() || ch == '_')
        {
            return error(header.number, "Invalid page identifier");
        }
        let route = only_quoted(route_text, header.number)?;
        let file = output_path(&route, header.number)?;
        if files.contains_key(&file) {
            return error(header.number, "Duplicate page route");
        }
        if files.len() >= MAX_PAGES {
            return error(header.number, "Too many site pages");
        }
        index += 1;
        let mut title = None;
        let mut description = None;
        while index < source_lines.len() && source_lines[index].indent == 4 {
            let meta = &source_lines[index];
            if let Some(rest) = meta.text.strip_prefix("title ") {
                if title.is_some() {
                    return error(meta.number, "Duplicate page title");
                }
                title = Some(only_quoted(rest, meta.number)?);
            } else if let Some(rest) = meta.text.strip_prefix("description ") {
                if description.is_some() {
                    return error(meta.number, "Duplicate page description");
                }
                description = Some(only_quoted(rest, meta.number)?);
            } else {
                break;
            }
            index += 1;
        }
        let title = title.ok_or_else(|| Error(format!(
            "Line {}: Page must include title",
            header.number
        )))?;
        if title.is_empty() {
            return error(header.number, "Page title cannot be empty");
        }
        let body = parse_nodes(&source_lines, &mut index, 4, 0)?;
        if body.is_empty() {
            return error(header.number, "Page must contain visible content");
        }
        let description_tag = description
            .map(|value| format!("<meta name=\"description\" content=\"{}\">\n", html(&value)))
            .unwrap_or_default();
        let document = format!(
            "<!doctype html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n<title>{}</title>\n{}<style>body{{font:1rem/1.6 system-ui,sans-serif;margin:0;color:#202030;background:#fff}}\
            .site-container{{max-width:68rem;margin:auto;padding:1.5rem}}\
            .site-column{{display:flex;flex-direction:column;gap:1rem}}\
            .site-row{{display:flex;flex-wrap:wrap;gap:1rem}}\
            .site-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,16rem),1fr));gap:1rem}}\
            .site-card,.site-callout{{padding:1.25rem;border:1px solid #ddd;border-radius:.75rem}}\
            .site-nav,.site-footer{{padding:1rem}}a{{color:#1855aa}}\
            pre{{overflow:auto;white-space:pre-wrap}}:focus-visible{{outline:3px solid #1855aa;outline-offset:3px}}</style>\n\
            </head>\n<body>\n{}\n</body>\n</html>\n",
            html(&title),
            description_tag,
            body
        );
        files.insert(file, document);
    }
    if files.is_empty() {
        return fail("Site requires at least one page");
    }
    Ok(StaticSite { files })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn generates_two_pages_with_escaped_text() {
        let input = r#"site "Example"
page home at "/":
    title "Hello & World"
    description "<safe>"
    container:
        column:
            heading "Hello <Rust>"
            paragraph "Native Site"
            link "Guide" to "/guide/"
page guide at "/guide/":
    title "Guide"
    paragraph "Second page"
"#;
        let site = generate(input).unwrap();
        assert_eq!(site.files.len(), 2);
        let html = &site.files["index.html"];
        assert!(html.contains("<h1>Hello &lt;Rust&gt;</h1>"));
        assert!(html.contains("Hello &amp; World"));
        assert!(html.contains("content=\"&lt;safe&gt;\""));
        assert!(html.contains("href=\"/guide/\""));
        assert!(site.files["guide/index.html"].contains("Second page"));
    }

    #[test]
    fn rejects_unsupported_syntax_and_unsafe_routes() {
        for source in [
            "site \"x\"\npage home at \"/../\":\n    title \"T\"\n    heading \"H\"\n",
            "site \"x\"\npage a at \"/\":\n    title \"T\"\n    paragraph \"Good\"\n    script \"bad\"\n",
            "site \"x\"\npage a at \"/\":\n    title \"T\"\n    link \"bad\" to \"javascript:alert(1)\"\n",
            "site \"x\"\npage a at \"/\":\n    title \"T\"\n    paragraph \"ok\" variant lead\n",
            "site \"x\"\npage a at \"/\":\n    title \"T\"\n    paragraph \"ok\"\npage b at \"/\":\n    title \"T\"\n    paragraph \"bad\"\n",
        ] {
            assert!(generate(source).is_err(), "Unexpected acceptance: {source}");
        }
    }

    #[test]
    fn invalid_json_literal_and_bad_indentation_fail() {
        assert!(generate("site \"x\"\npage h at \"/\":\n    title \"T\"\n  heading \"H\"\n").is_err());
        assert!(generate("site \"x\"\npage h at \"/\":\n    title \"T\"\n    heading \"\\uZZZZ\"\n").is_err());
    }
}
