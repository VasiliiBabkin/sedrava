//! Native static Site DSL, using the Python 0.11 presentation contract as reference.
mod assets;
mod properties;
mod render;
mod syntax;
pub mod webapp;

use crate::model::{fail, Error, Result};
use properties::{Props, THEME};
use regex::Regex;
use std::{
    collections::{BTreeMap, BTreeSet},
    path::Path,
    sync::LazyLock,
};
use syntax::{identifier, Line, Token};
use url::Url;

#[derive(Debug)]
pub struct StaticSite {
    /// Relative files to stage together before publication.
    pub files: BTreeMap<String, Vec<u8>>,
}

struct Node {
    kind: String,
    props: Props,
    children: Vec<Node>,
    line: Line,
}

struct Page {
    route: String,
    title: String,
    description: String,
    lang: String,
    nodes: Vec<Node>,
    ids: BTreeSet<String>,
}

#[derive(Default)]
struct Settings {
    stylesheets: Vec<String>,
    licenses: Vec<String>,
    images: BTreeMap<String, String>,
    origin: Option<String>,
    robots: Option<bool>,
}

struct Site {
    pages: Vec<Page>,
    theme: Props,
    settings: Settings,
}

type Styles = BTreeMap<String, BTreeMap<String, Token>>;

pub fn generate(source: &str) -> Result<StaticSite> {
    generate_at(source, None)
}

pub fn generate_at(source: &str, root: Option<&Path>) -> Result<StaticSite> {
    let root = canonical_root(root)?;
    let lines = syntax::expand(source, root.as_deref(), false)?;
    let site = parse(&lines, true)?.0;
    render::generate(site, root.as_deref())
}

fn canonical_root(root: Option<&Path>) -> Result<Option<std::path::PathBuf>> {
    root.map(Path::canonicalize)
        .transpose()
        .map_err(|err| Error(format!("Cannot resolve Web source directory: {err}")))
}

fn parse(lines: &[Line], require_pages: bool) -> Result<(Site, Styles)> {
    let mut i = 0;
    if require_pages {
        let first = lines
            .first()
            .ok_or_else(|| Error("Missing site declaration".into()))?;
        match &syntax::tokens(first, &first.text)?[..] {
            [Token::Word(key), Token::Text(name)]
                if first.depth == 0 && key == "site" && !name.trim().is_empty() => {}
            _ => return Err(first.error("Expected site and a nonempty quoted name")),
        }
        i = 1;
    }
    let mut theme: Props = THEME.iter().map(|&(k, v)| (k.into(), v.into())).collect();
    let mut styles = Styles::new();
    let mut settings = Settings::default();
    let mut headers = Vec::new();
    let mut seen_theme = false;
    while i < lines.len() {
        let start = i;
        let line = &lines[i];
        if line.depth != 0 {
            return Err(line.error("Expected top-level Site declaration"));
        }
        i += 1;
        while i < lines.len() && lines[i].depth > 0 {
            i += 1;
        }
        let body = &lines[start + 1..i];
        let args = syntax::tokens(line, &line.text)?;
        match &args[..] {
            [Token::Word(keyword), Token::Colon] if keyword == "theme" => {
                if seen_theme || body.is_empty() {
                    return Err(line.error("Expected a unique nonempty theme block"));
                }
                seen_theme = true;
                let mut keys = BTreeSet::new();
                for row in body {
                    let items = syntax::tokens(row, &row.text)?;
                    let [Token::Word(key), Token::Text(value)] = &items[..] else {
                        return Err(row.error("Expected theme token and quoted hex color"));
                    };
                    let color = properties::color(value).filter(|c| c.starts_with('#'));
                    if row.depth != 1
                        || !theme.contains_key(key)
                        || !keys.insert(key.clone())
                        || color.is_none()
                    {
                        return Err(row.error("Invalid or duplicate theme token"));
                    }
                    theme.insert(key.clone(), color.unwrap());
                }
            }
            [Token::Word(keyword), Token::Word(name) | Token::Text(name), Token::Colon]
                if keyword == "style" =>
            {
                if !identifier(name) || body.is_empty() || styles.contains_key(name) {
                    return Err(line.error("Invalid, empty or duplicate style"));
                }
                let mut style = BTreeMap::new();
                for row in body {
                    let parsed = properties::props(&syntax::tokens(row, &row.text)?, row)?;
                    if row.depth != 1 || parsed.len() != 1 {
                        return Err(row.error("Expected one indented style property"));
                    }
                    for (key, value) in parsed {
                        properties::validate(&key, &value, None, row)?;
                        if style.insert(key, value).is_some() {
                            return Err(row.error("Duplicate style property"));
                        }
                    }
                }
                styles.insert(name.clone(), style);
            }
            [Token::Word(keyword), Token::Word(name) | Token::Text(name), Token::Word(at), Token::Text(route), Token::Colon]
                if keyword == "page" && at == "at" =>
            {
                if !identifier(name) || !valid_route(route) {
                    return Err(line.error("Invalid page name or route"));
                }
                if headers.len() >= 32 || headers.iter().any(|(n, r, _, _)| n == name || r == route)
                {
                    return Err(line.error("Duplicate page name or route, or too many pages"));
                }
                headers.push((name.clone(), route.clone(), line, body));
            }
            [Token::Word(key), Token::Text(value)] if body.is_empty() => {
                let group = match key.as_str() {
                    "stylesheet" => &mut settings.stylesheets,
                    "license" => &mut settings.licenses,
                    "favicon" | "social-image" => {
                        if settings.images.insert(key.clone(), value.clone()).is_some() {
                            return Err(line.error("Duplicate Site image directive"));
                        }
                        continue;
                    }
                    "origin" => {
                        let parsed = external(value, true).filter(|url| {
                            url.scheme() == "https"
                                && url.path() == "/"
                                && url.query().is_none()
                                && url.fragment().is_none()
                        });
                        if settings.origin.is_some()
                            || parsed.is_none()
                            || !value.starts_with("https://")
                        {
                            return Err(
                                line.error("Expected a unique bare HTTPS publishing origin")
                            );
                        }
                        settings.origin = Some(value.trim_end_matches('/').to_owned());
                        continue;
                    }
                    _ => return Err(line.error(format!("Unsupported Site directive {key}"))),
                };
                if group.len() >= 8 {
                    return Err(line.error("Too many Site presentation directives"));
                }
                group.push(value.clone());
            }
            [Token::Word(key), Token::Bool(value)] if body.is_empty() && key == "robots" => {
                if settings.robots.replace(*value).is_some() {
                    return Err(line.error("Duplicate robots directive"));
                }
            }
            _ => return Err(line.error("Expected theme, style, page or supported Site directive")),
        }
    }
    if settings.robots.is_some() && settings.origin.is_none() {
        return fail("robots requires an explicit publishing origin");
    }
    let pages = headers
        .into_iter()
        .map(|(_, route, line, body)| parse_page(route, line, body, &styles))
        .collect::<Result<Vec<_>>>()?;
    if require_pages && !pages.iter().any(|p| p.route == "/") {
        return fail("Site requires a page at /");
    }
    let routes = pages
        .iter()
        .map(|page| (page.route.as_str(), &page.ids))
        .collect::<BTreeMap<_, _>>();
    for page in &pages {
        links(&page.nodes, page, &routes)?;
    }
    Ok((
        Site {
            pages,
            theme,
            settings,
        },
        styles,
    ))
}

fn valid_route(route: &str) -> bool {
    route == "/"
        || (route.starts_with('/')
            && route.ends_with('/')
            && !route.contains("//")
            && route[1..route.len() - 1].split('/').all(|word| {
                !word.is_empty()
                    && word
                        .bytes()
                        .all(|b| b.is_ascii_alphanumeric() || b"_-".contains(&b))
            }))
}

fn parse_page(route: String, header: &Line, body: &[Line], styles: &Styles) -> Result<Page> {
    static LANG: LazyLock<Regex> =
        LazyLock::new(|| Regex::new(r"^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*$").unwrap());
    let mut meta = BTreeMap::new();
    let mut index = 0;
    for line in body {
        let key = line.text.split(' ').next().unwrap_or("");
        if line.depth != 1 || !matches!(key, "title" | "description" | "lang") {
            break;
        }
        let args = syntax::tokens(line, &line.text)?;
        let value = match &args[..] {
            [_, Token::Text(value)] => value,
            [_, Token::Word(value)] if key == "lang" => value,
            _ => return Err(line.error("Invalid page metadata")),
        };
        if meta.insert(key, value.clone()).is_some() {
            return Err(line.error("Duplicate page metadata"));
        }
        index += 1;
    }
    let title = meta
        .remove("title")
        .filter(|s| !s.trim().is_empty())
        .ok_or_else(|| header.error("Page requires a title"))?;
    let description = meta.remove("description").unwrap_or_default();
    let lang = meta.remove("lang").unwrap_or_else(|| "en".into());
    if lang.len() > 35 || !LANG.is_match(&lang) {
        return Err(header.error("Invalid page language"));
    }
    let mut nodes = parse_nodes(body, &mut index, 1, styles, None)?;
    let mut ids = BTreeSet::from(["content".into()]);
    let (mut previous, mut h1) = (0, 0);
    let len = nodes.len();
    for (i, node) in nodes.iter_mut().enumerate() {
        if (node.kind == "navbar" && i != 0) || (node.kind == "footer" && i + 1 != len) {
            return Err(node
                .line
                .error("Navbar and footer must be the first and last top-level components"));
        }
        validate_tree(node, false, &mut ids, &mut previous, &mut h1, true)?;
    }
    if h1 != 1 {
        return Err(header.error("Each page requires exactly one h1"));
    }
    Ok(Page {
        route,
        title,
        description,
        lang,
        nodes,
        ids,
    })
}

fn parse_nodes(
    lines: &[Line],
    index: &mut usize,
    depth: usize,
    styles: &Styles,
    domain: Option<&crate::model::Program>,
) -> Result<Vec<Node>> {
    let mut out = Vec::new();
    while let Some(line) = lines.get(*index).filter(|l| l.depth >= depth) {
        if line.depth != depth {
            return Err(line.error("Unexpected indentation in Site layout"));
        }
        *index += 1;
        let args = syntax::tokens(line, &line.text)?;
        let Some(Token::Word(kind)) = args.first() else {
            return Err(line.error("Expected Site component name"));
        };
        let widget = domain.and_then(|_| webapp::widget(kind));
        let block = match kind.as_str() {
            "container" | "row" | "column" | "grid" | "card" | "navbar" | "footer" | "callout" => {
                true
            }
            "heading" | "paragraph" | "link" | "button" | "image" | "spacer" | "divider"
            | "code" => false,
            _ if widget.is_some() => widget.unwrap().block,
            _ => return Err(line.error(format!("Unsupported Site/WebApp component {kind}"))),
        };
        if block != (args.last() == Some(&Token::Colon)) {
            return Err(line.error("Invalid block or leaf component"));
        }
        let positional = match kind.as_str() {
            "heading" | "paragraph" | "link" | "button" | "code" => Some("text"),
            "image" => Some("src"),
            _ => None,
        };
        let positional = widget.and_then(|widget| widget.positional).or(positional);
        let state_argument = widget.is_some_and(|w| w.state_argument);
        let has_pos = if state_argument {
            matches!(args.get(1), Some(Token::Word(_)))
        } else {
            positional.is_some() && matches!(args.get(1), Some(Token::Text(_)))
        };
        if state_argument && !has_pos {
            return Err(line.error("Expected a state, collection or row field identifier"));
        }
        let validate = |key: &str, value: &Token| {
            if let Some(widget) = widget {
                if kind == "button" && matches!(key, "to" | "target") {
                    return Err(line.error(format!("Unknown WebApp button property {key}")));
                }
                if let Some(result) = widget.property(key, value, line) {
                    return result;
                }
            }
            properties::validate(key, value, Some(kind), line)
        };
        let mut tokens = properties::props(
            &args[1 + usize::from(has_pos)..args.len() - usize::from(block)],
            line,
        )?;
        if has_pos
            && tokens
                .insert(positional.unwrap().into(), args[1].clone())
                .is_some()
        {
            return Err(line.error("Duplicate positional property"));
        }
        let mut props = properties::defaults(kind);
        if kind == "submit" {
            props.insert("variant".into(), "primary".into());
        }
        for (key, value) in &tokens {
            props.insert(key.clone(), validate(key, value)?);
        }
        if let Some(style) = props.remove("style") {
            let style = styles
                .get(&style)
                .ok_or_else(|| line.error(format!("Unknown style {style}")))?;
            for (key, value) in style {
                let validated = validate(key, value)?;
                if !tokens.contains_key(key) {
                    props.insert(key.clone(), validated);
                }
            }
        }
        if positional.is_some_and(|p| !props.contains_key(p))
            || (widget.is_none()
                && matches!(kind.as_str(), "link" | "button")
                && !props.contains_key("to"))
            || (kind == "image" && !props.contains_key("alt"))
        {
            return Err(line.error("Missing required Site component property"));
        }
        if matches!(kind.as_str(), "heading" | "link" | "button" | "code")
            && props["text"].trim().is_empty()
        {
            return Err(line.error("Accessible text must not be empty"));
        }
        let mut children = Vec::new();
        if block {
            children = parse_nodes(lines, index, depth + 1, styles, domain)?;
            if children.is_empty() {
                return Err(line.error("Empty Site component block"));
            }
        }
        if let (Some(widget), Some(domain)) = (widget, domain) {
            widget.validate(kind, &mut props, &children, domain, line)?;
        }
        out.push(Node {
            kind: kind.clone(),
            props,
            children,
            line: line.clone(),
        });
    }
    Ok(out)
}

fn validate_tree(
    node: &mut Node,
    nested: bool,
    ids: &mut BTreeSet<String>,
    previous: &mut i32,
    h1: &mut usize,
    site_landmarks: bool,
) -> Result<()> {
    if site_landmarks && nested && matches!(node.kind.as_str(), "navbar" | "footer") {
        return Err(node
            .line
            .error("Navbar and footer must be top-level components"));
    }
    if let Some(id) = node.props.get("id") {
        if !ids.insert(id.clone()) {
            return Err(node.line.error(format!("Duplicate or reserved id {id}")));
        }
    }
    if node.kind == "heading" {
        let level = node
            .props
            .get("level")
            .map_or(if *previous == 0 { 1 } else { 2 }, |level| {
                level.parse().unwrap()
            });
        if level > *previous + 1 {
            return Err(node.line.error("Heading levels must not skip a level"));
        }
        node.props.insert("level".into(), level.to_string());
        *previous = level;
        *h1 += usize::from(level == 1);
    }
    for child in &mut node.children {
        validate_tree(child, true, ids, previous, h1, site_landmarks)?;
    }
    Ok(())
}

fn safe_url(value: &str) -> bool {
    let mut decoded = value.to_owned();
    for _ in 0..3 {
        let mut bytes = Vec::new();
        let mut i = 0;
        while i < decoded.len() {
            let b = decoded.as_bytes()[i];
            if b == b'%' {
                if let Some(hex) = decoded.get(i + 1..i + 3) {
                    if hex.bytes().all(|b| b.is_ascii_hexdigit()) {
                        let v = u8::from_str_radix(hex, 16).expect("two hexadecimal digits");
                        bytes.push(v);
                        i += 3;
                        continue;
                    }
                }
            }
            bytes.push(b);
            i += 1;
        }
        decoded = match String::from_utf8(bytes) {
            Ok(s) => s,
            Err(_) => return false,
        };
    }
    !decoded.is_empty()
        && !decoded.starts_with("//")
        && !decoded.contains(['\\', '<', '>', '"', '\''])
        && !decoded.chars().any(|c| c.is_whitespace() || c.is_control())
        && !decoded
            .split(['?', '#'])
            .next()
            .unwrap_or("")
            .split('/')
            .any(|p| matches!(p, "." | ".."))
}

fn external(value: &str, image: bool) -> Option<Url> {
    if !safe_url(value) {
        return None;
    }
    let url = Url::parse(value).ok()?;
    match url.scheme() {
        "https" | "http" if !image || url.scheme() == "https" => {
            let (_, rest) = value.split_once("://")?;
            let host = rest.split(['/', '?', '#']).next()?;
            (!host.is_empty() && !host.contains(['@', '%']) && url.host().is_some()).then_some(url)
        }
        "mailto" if !image => {
            static MAIL: LazyLock<Regex> =
                LazyLock::new(|| Regex::new(r"^[^@?\s]+@[^@?\s]+\.[^@?\s]+$").unwrap());
            (MAIL.is_match(url.path()) && url.query().is_none()).then_some(url)
        }
        "tel" if !image => {
            static TEL: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"^\+?[0-9()-]+$").unwrap());
            TEL.is_match(url.path()).then_some(url)
        }
        _ => None,
    }
}

fn links(nodes: &[Node], page: &Page, routes: &BTreeMap<&str, &BTreeSet<String>>) -> Result<()> {
    for node in nodes {
        if let Some(value) = node.props.get("to") {
            if external(value, false).is_none() {
                let (path, suffix) = split_target(value);
                let target = if path.is_empty() { &page.route } else { path };
                let anchor = suffix.split_once('#').map(|(_, anchor)| anchor);
                if !safe_url(value)
                    || !(value.starts_with('/') || value.starts_with('#'))
                    || value.contains(':')
                {
                    return Err(node.line.error("Unsafe or unsupported link destination"));
                }
                let ids = routes
                    .get(target)
                    .ok_or_else(|| node.line.error(format!("Unknown site route {target}")))?;
                if let Some(anchor) = anchor.filter(|s| !s.is_empty()) {
                    if !ids.contains(anchor) {
                        return Err(node.line.error(format!("Unknown anchor {anchor}")));
                    }
                }
            }
        }
        if let Some(src) = node.props.get("src") {
            if external(src, true).is_none()
                && (!safe_url(src) || src.starts_with('/') || src.contains([':', '%', '#', '?']))
            {
                return Err(node.line.error("Unsafe or unsupported image URL"));
            }
        }
        links(&node.children, page, routes)?;
    }
    Ok(())
}

fn split_target(value: &str) -> (&str, &str) {
    value.split_at(value.find(['?', '#']).unwrap_or(value.len()))
}

#[cfg(test)]
mod tests {
    use super::*;

    const HOME: &str =
        "site \"Demo\"\npage home at \"/\":\n    title \"Home\"\n    heading \"<Rust>\"\n";

    #[test]
    fn emits_escaped_semantic_html_and_relative_routes() {
        let source = format!(
            "{HOME}    link \"Go\" to \"/guide/#info\"\npage guide at \"/guide/\":\n    title \"Guide\"\n    heading \"Info\" id info\n    link \"Back\" to \"/\"\n"
        );
        let site = generate(&source).unwrap();
        let index = std::str::from_utf8(&site.files["index.html"]).unwrap();
        assert!(index.contains("&lt;Rust&gt;</h1>"));
        assert!(index.contains("href=\"guide/index.html#info\""));
        let guide = std::str::from_utf8(&site.files["guide/index.html"]).unwrap();
        assert!(guide.contains("href=\"../index.html\""));
    }

    #[test]
    fn rejects_unsafe_or_unresolved_site_markup() {
        for suffix in [
            "    script \"bad\"\n",
            "    link \"unsafe\" to \"javascript:void(0)\"\n",
            "    link \"unsafe\" to \"/%252e%252e/\"\n",
            "    link \"missing\" to \"/#unknown\"\n",
            "    paragraph \"duplicate\" id content\n",
            "    paragraph \"unsafe color\" color \"#fff;display:none\"\n",
            "  paragraph \"bad indentation\"\n",
            "    paragraph \"\\uZZZZ\"\n",
            "page home at \"/guide/\":\n    title \"Guide\"\n    heading \"Duplicate\"\n",
        ] {
            assert!(generate(&format!("{HOME}{suffix}")).is_err(), "{suffix}");
        }
    }

    #[test]
    fn component_expansion_preserves_slot_depth_and_escapes_arguments() {
        let source = r#"site "Demo"
component Card(title: text):
    card:
        heading $title level 2
        slot
page home at "/":
    title "Home"
    heading "Home"
    use Card title "<Safe>":
        paragraph "Slotted"
"#;
        let site = generate(source).unwrap();
        let html = std::str::from_utf8(&site.files["index.html"]).unwrap();
        assert!(html.contains("&lt;Safe&gt;</h2><p"));
        assert!(html.contains(">Slotted</p></article>"));
    }
}
