use super::services::{self, Services};
use super::{
    canonical_root, external, parse, parse_nodes, render, safe_url, syntax, validate_tree, Line,
    Node, Props, StaticSite, Token,
};
use crate::{
    model::{fail, Error, Kind, Program, Result},
    parser, runtime, web,
};
use regex::Regex;
use serde::Serialize;
use std::{
    collections::{BTreeMap, BTreeSet},
    path::Path,
    sync::LazyLock,
};

#[derive(Clone, Copy)]
pub(super) struct Widget {
    pub block: bool,
    pub positional: Option<&'static str>,
    pub state_argument: bool,
    required: &'static [&'static str],
    optional: &'static [&'static str],
}

pub(super) fn widget(kind: &str) -> Option<Widget> {
    const QUERY: &[&str] = &[
        "title", "status", "search", "sort", "where", "equals", "active", "empty",
    ];
    const TABLE: &[&str] = &[
        "title", "status", "search", "sort", "where", "equals", "active", "empty", "fields",
    ];
    let (block, positional, required, optional): (_, _, &[_], &[_]) = match kind {
        "session" => (false, "text", &["text"], &[]),
        "request" | "cancel" => (false, "text", &["text", "service"], &[]),
        "remote" => (false, "service", &["service"], &["search", "title"]),
        "value" => (false, "state", &["state"], &[]),
        "input" => (false, "state", &["state", "label"], &["kind"]),
        "checkbox" => (false, "state", &["state", "label"], &[]),
        "when" => (true, "state", &["state"], &[]),
        "select" => (true, "state", &["state", "label"], &[]),
        "option" => (false, "text", &["text", "value"], &[]),
        "list" => (false, "collection", &["collection", "select"], QUERY),
        "table" => (false, "collection", &["collection", "select"], TABLE),
        "each" => (true, "collection", &["collection", "select"], QUERY),
        "field" => (false, "field", &["field"], &[]),
        "row-when" => (true, "field", &["field"], &[]),
        "pick" => (false, "text", &["text"], &[]),
        "remote-pick" => (false, "text", &["text", "bindings"], &["action"]),
        "button" => (false, "text", &["text", "action"], &[]),
        "form" => (true, "", &["action"], &[]),
        "submit" => (false, "text", &["text"], &[]),
        "dialog" => (true, "", &["id", "label"], &[]),
        "open" | "close" => (false, "text", &["text", "to"], &[]),
        "navigate" => (false, "text", &["text", "to"], &["action"]),
        "back" => (false, "text", &["text"], &[]),
        _ => return None,
    };
    Some(Widget {
        block,
        positional: (!positional.is_empty()).then_some(positional),
        state_argument: matches!(positional, "state" | "collection" | "field" | "service"),
        required,
        optional,
    })
}

impl Widget {
    pub fn property(&self, key: &str, value: &Token, line: &Line) -> Option<Result<String>> {
        if !self.required.contains(&key) && !self.optional.contains(&key) {
            return None;
        }
        if matches!(key, "label" | "id") {
            return None;
        }
        let string = match value {
            Token::Word(s) | Token::Text(s) => Some(s.clone()),
            _ => None,
        };
        let accepted = match key {
            "value" => match value {
                Token::Int(v) => Some(v.to_string()),
                Token::Bool(v) => Some(v.to_string()),
                Token::Text(v) | Token::Word(v) => Some(serde_json::to_string(v).unwrap()),
                _ => None,
            },
            "text" | "empty" | "fields" | "bindings" => string,
            "kind" => {
                string.filter(|s| matches!(s.as_str(), "text" | "textarea" | "email" | "url"))
            }
            _ => string.filter(|s| syntax::identifier(s)),
        };
        Some(accepted.ok_or_else(|| line.error(format!("Invalid WebApp property {key}"))))
    }

    pub fn validate(
        &self,
        kind: &str,
        props: &mut Props,
        children: &[Node],
        domain: &Program,
        line: &Line,
    ) -> Result<()> {
        for key in self.required {
            if !props.contains_key(*key) {
                return Err(line.error(format!("Missing WebApp property {key}")));
            }
        }
        if props.get("text").is_some_and(|s| s.trim().is_empty())
            || matches!(kind, "input" | "checkbox" | "select" | "dialog")
                && props["label"].trim().is_empty()
        {
            return Err(line.error("Accessible control text must not be empty"));
        }
        if let Some(action) = props.get("action") {
            if !domain.actions.contains_key(action) {
                return Err(line.error(format!("Unknown action {action}")));
            }
        }
        if let Some(key) = props.get("state") {
            let actual = domain.types.get(key);
            let scalar = matches!(actual, Some(Kind::Int | Kind::Text | Kind::Bool));
            let mutable = domain.states.contains_key(key);
            let supported = match kind {
                "value" => scalar,
                "when" => actual == Some(&Kind::Bool),
                "checkbox" => mutable && actual == Some(&Kind::Bool),
                "input" => {
                    mutable
                        && matches!(actual, Some(Kind::Text | Kind::Int))
                        && (!props.contains_key("kind") || actual == Some(&Kind::Text))
                }
                "select" => scalar && mutable,
                _ => false,
            };
            if !supported {
                return Err(line.error(format!("Invalid state binding {key} for {kind}")));
            }
            if kind == "input" && actual == Some(&Kind::Int) {
                props.insert("kind".into(), "integer".into());
            }
            if kind == "select" {
                let mut values = BTreeSet::new();
                for option in children {
                    if option.kind != "option" {
                        return Err(option.line.error("Select requires option children"));
                    }
                    let value =
                        serde_json::from_str::<serde_json::Value>(&option.props["value"]).unwrap();
                    let expected = match value {
                        serde_json::Value::String(_) => Kind::Text,
                        serde_json::Value::Bool(_) => Kind::Bool,
                        _ => Kind::Int,
                    };
                    if actual != Some(&expected) || !values.insert(&option.props["value"]) {
                        return Err(option.line.error(
                            "Option requires distinct values matching the select state type",
                        ));
                    }
                }
            }
        }
        if matches!(kind, "list" | "table" | "each") {
            collection(kind, props, domain, line)?;
        }
        Ok(())
    }
}

fn collection(kind: &str, props: &mut Props, domain: &Program, line: &Line) -> Result<()> {
    let Some(Kind::List { record, .. }) = domain.types.get(&props["collection"]) else {
        return Err(line.error("List or table requires a declared collection"));
    };
    let Kind::Record { fields, .. } = record.as_ref() else {
        return Err(line.error("Expected a bounded record collection"));
    };
    let field = |name: &str| {
        fields
            .iter()
            .find(|(key, _)| key == name)
            .map(|(_, kind)| kind)
    };
    if !matches!(
        domain.states.get(&props["select"]),
        Some(crate::model::Value::Int(_))
    ) {
        return Err(line.error("List select requires mutable integer state"));
    }
    for (key, expected) in [("title", Kind::Text), ("status", Kind::Bool)] {
        if props
            .get(key)
            .is_some_and(|name| field(name) != Some(&expected))
        {
            return Err(line.error(format!("Invalid collection {key} field")));
        }
    }
    for (key, expected) in [("search", Kind::Text), ("active", Kind::Bool)] {
        if props
            .get(key)
            .is_some_and(|name| domain.types.get(name) != Some(&expected))
        {
            return Err(line.error(format!("Invalid collection {key} state")));
        }
    }
    if props.get("sort").is_some_and(|name| field(name).is_none()) {
        return Err(line.error("Unknown collection sort field"));
    }
    match props.get("where") {
        Some(name)
            if field(name).is_some()
                && props.get("equals").and_then(|key| domain.types.get(key)) == field(name) => {}
        None if !props.contains_key("equals") && !props.contains_key("active") => {}
        _ => return Err(line.error("Collection filter requires a matching field and state")),
    }
    if kind == "table" {
        let fields = props.get("fields").map_or_else(
            || {
                fields
                    .iter()
                    .map(|(key, _)| key.as_str())
                    .collect::<Vec<_>>()
            },
            |value| value.split_whitespace().collect(),
        );
        if fields.is_empty()
            || fields.iter().any(|name| field(name).is_none())
            || fields.iter().collect::<BTreeSet<_>>().len() != fields.len()
        {
            return Err(line.error("Table fields must be distinct record fields"));
        }
        props.insert("fields".into(), fields.join(" "));
    }
    Ok(())
}

#[derive(Serialize)]
pub(super) struct Route {
    pub path: String,
    pub guard: Option<String>,
}

pub(super) struct View {
    pub route: Route,
    pub nodes: Vec<Node>,
    pub name: String,
}

fn route(line: &Line, program: &Program) -> Result<(String, Route)> {
    static HEADER: LazyLock<Regex> = LazyLock::new(|| {
        Regex::new(r#"^view ([A-Za-z][A-Za-z0-9_]*)(?: at "([^"]+)")?(?: when ([A-Za-z][A-Za-z0-9_]*))?:$"#).unwrap()
    });
    let groups = HEADER
        .captures(&line.text)
        .ok_or_else(|| line.error("Invalid WebApp view declaration"))?;
    let name = groups[1].to_owned();
    let path = groups.get(2).map_or_else(
        || {
            if name == "main" {
                "/".into()
            } else {
                format!("/{name}")
            }
        },
        |v| v.as_str().into(),
    );
    let guard = groups.get(3).map(|v| v.as_str().to_owned());
    if name.len() > 64
        || !path.starts_with('/')
        || (name == "main" && (path != "/" || guard.is_some()))
        || guard
            .as_ref()
            .is_some_and(|key| program.types.get(key) != Some(&Kind::Bool))
    {
        return Err(line.error("Invalid WebApp route or boolean guard"));
    }
    let mut params = BTreeSet::new();
    if path != "/" {
        for part in path[1..].split('/') {
            if let Some(key) = part.strip_prefix(':') {
                if !syntax::identifier(key)
                    || !params.insert(key)
                    || !matches!(program.states.get(key), Some(crate::model::Value::Int(_)))
                {
                    return Err(
                        line.error("Route parameters require distinct mutable integer states")
                    );
                }
            } else if part.is_empty()
                || !part
                    .bytes()
                    .all(|c| c.is_ascii_alphanumeric() || b"_-".contains(&c))
            {
                return Err(line.error("Invalid route segment"));
            }
        }
    }
    Ok((name, Route { path, guard }))
}

fn overlap(a: &str, b: &str) -> bool {
    let is_number = |s: &str| {
        let s = s.strip_prefix('-').unwrap_or(s);
        !s.is_empty() && s.bytes().all(|b| b.is_ascii_digit())
    };
    a.split('/').count() == b.split('/').count()
        && a.split('/').zip(b.split('/')).all(|(x, y)| {
            x == y
                || x.starts_with(':') && (y.starts_with(':') || is_number(y))
                || y.starts_with(':') && is_number(x)
        })
}

fn validate_controls(
    nodes: &[Node],
    dialogs: &BTreeSet<String>,
    views: &BTreeSet<String>,
    parent: Option<&str>,
    form: bool,
    row_fields: Option<&BTreeMap<&str, Kind>>,
    program: &Program,
    services: &Services,
    remote_row: bool,
) -> Result<()> {
    for node in nodes {
        let kind = node.kind.as_str();
        if node
            .props
            .get("id")
            .is_some_and(|id| id.starts_with("sdr-field-") || id.starts_with("sdr-list-status-"))
        {
            return Err(node.line.error("Reserved generated UI ID prefix"));
        }
        if kind == "session" && (form || row_fields.is_some() || parent == Some("dialog")) {
            return Err(node.line.error("Session control cannot be nested in forms, rows or dialogs"));
        }
        if kind == "form" && form
            || kind == "submit" && !form
            || kind == "option" && parent != Some("select")
        {
            return Err(node.line.error("Invalid form or select nesting"));
        }
        if let Some(fields) = row_fields {
            if (remote_row && matches!(kind, "button" | "pick"))
                || node.props.contains_key("id")
                || matches!(
                    kind,
                    "each"
                        | "table"
                        | "list"
                        | "input"
                        | "checkbox"
                        | "select"
                        | "form"
                        | "submit"
                        | "dialog"
                        | "open"
                        | "close"
                        | "navigate"
                        | "back"
                        | "remote"
                        | "request"
                        | "cancel"
                        | "session"
                )
            {
                return Err(node
                    .line
                    .error("Unsupported nested row control or duplicate-prone id"));
            }
            if matches!(kind, "field" | "row-when") {
                let field = fields.get(node.props["field"].as_str());
                if field.is_none() || (kind == "row-when" && field != Some(&Kind::Bool)) {
                    return Err(node
                        .line
                        .error("Unknown row field or invalid boolean condition"));
                }
            }
        } else if matches!(kind, "field" | "row-when" | "pick") {
            return Err(node.line.error("Row control requires an each template"));
        }
        if kind == "remote-pick" {
            let fields = row_fields.filter(|_| remote_row).ok_or_else(||
                node.line.error("remote-pick requires an HTTP row template"))?;
            // A32 conservatively forbids persistent state in apps using remote selection.
            // This avoids copying protected fields into persistent state through actions.
            if !program.persistent.is_empty() {
                return Err(node.line.error("remote-pick requires a nonpersistent WebApp"));
            }
            let mut targets = BTreeSet::new();
            let mut count = 0;
            for binding in node.props["bindings"].split_ascii_whitespace() {
                let (field, target) = binding.split_once(':').ok_or_else(||
                    node.line.error("remote-pick requires FIELD:STATE bindings"))?;
                count += 1;
                if count > 8 || !syntax::identifier(field) || !syntax::identifier(target)
                    || !targets.insert(target) || !program.states.contains_key(target)
                    || !fields.get(field).is_some_and(|k| program.types.get(target)==Some(k))
                {
                    return Err(node.line.error("Invalid or duplicate typed remote-pick binding"));
                }
            }
            if count == 0 {
                return Err(node.line.error("remote-pick requires at least one binding"));
            }
        }
        let service = node
            .props
            .get("service")
            .map(|key| {
                services
                    .get(key)
                    .ok_or_else(|| node.line.error(format!("Unknown HTTP service {key}")))
            })
            .transpose()?;
        if kind == "remote" {
            fn contains_pick(nodes: &[Node]) -> bool {
                nodes.iter().any(|n| n.kind == "remote-pick" || contains_pick(&n.children))
            }
            if contains_pick(&node.children) && !service.unwrap().allows_remote_pick() {
                return Err(node.line.error("remote-pick requires authenticated SQL row service without idempotency"));
            }
        }
        if kind == "remote" {
            if node
                .props
                .get("search")
                .is_some_and(|key| program.types.get(key) != Some(&Kind::Text))
                || node
                    .props
                    .get("title")
                    .is_some_and(|key| service.unwrap().fields.get(key) != Some(&"text"))
            {
                return Err(node
                    .line
                    .error("Remote search requires text state and title requires a text field"));
            }
        }
        let local_fields = if kind == "remote" {
            Some(
                service
                    .unwrap()
                    .fields
                    .iter()
                    .map(|(key, kind)| {
                        (
                            key.as_str(),
                            match *kind {
                                "bool" => Kind::Bool,
                                "int32" => Kind::Int,
                                _ => Kind::Text,
                            },
                        )
                    })
                    .collect(),
            )
        } else if kind == "each" {
            let Kind::List { record, .. } = &program.types[&node.props["collection"]] else {
                unreachable!()
            };
            let Kind::Record { fields, .. } = record.as_ref() else {
                unreachable!()
            };
            Some(
                std::iter::once(("id", Kind::Int))
                    .chain(
                        fields
                            .iter()
                            .map(|(name, kind)| (name.as_str(), kind.clone())),
                    )
                    .collect(),
            )
        } else {
            None
        };
        match kind {
            "navigate" if !views.contains(&node.props["to"]) => {
                return Err(node.line.error("Unknown target view"))
            }
            "open" | "close" if !dialogs.contains(&node.props["to"]) => {
                return Err(node.line.error("Unknown dialog"))
            }
            "link" => {
                let to = &node.props["to"];
                if external(to, false).is_none()
                    && (!safe_url(to)
                        || !(to.starts_with('/') || to.starts_with('#'))
                        || to.contains(':'))
                {
                    return Err(node.line.error("Unsafe or unsupported link destination"));
                }
            }
            "image" => {
                let src = &node.props["src"];
                if external(src, true).is_none()
                    && (!safe_url(src)
                        || src.starts_with('/')
                        || src.contains([':', '%', '#', '?']))
                {
                    return Err(node.line.error("Unsafe or unsupported image URL"));
                }
            }
            _ => {}
        }
        validate_controls(
            &node.children,
            dialogs,
            views,
            Some(kind),
            form || kind == "form",
            local_fields.as_ref().or(row_fields),
            program,
            services,
            remote_row || kind == "remote",
        )?;
    }
    Ok(())
}

fn remote_render_cost(nodes: &[Node], services: &Services) -> usize {
    fn template_cost(nodes: &[Node]) -> usize {
        nodes
            .iter()
            .map(|node| 3 + template_cost(&node.children))
            .sum()
    }
    nodes
        .iter()
        .map(|node| {
            if node.kind == "remote" {
                let service = &services[&node.props["service"]];
                let content = if node.children.is_empty() {
                    service.fields.len()
                } else {
                    template_cost(&node.children)
                };
                service.max_rows() * (1 + content)
            } else {
                remote_render_cost(&node.children, services)
            }
        })
        .sum()
}

fn collect_dialogs(
    nodes: &[Node],
    dialogs: &mut BTreeSet<String>,
    count: &mut usize,
) -> Result<()> {
    for node in nodes {
        *count += 1;
        if *count > 512 {
            return Err(node.line.error("WebApp UI component limit (512) exceeded"));
        }
        if node.kind == "dialog" {
            dialogs.insert(node.props["id"].clone());
        }
        collect_dialogs(&node.children, dialogs, count)?;
    }
    Ok(())
}

pub fn generate(source: &str, root: Option<&Path>) -> Result<StaticSite> {
    let root = canonical_root(root)?;
    let lines = syntax::expand(source, root.as_deref(), true)?;
    let header = lines
        .first()
        .ok_or_else(|| Error("Missing webapp declaration".into()))?;
    let args = syntax::tokens(header, &header.text)?;
    let [Token::Word(mode), Token::Text(title)] = &args[..] else {
        return Err(header.error("Expected webapp and a nonempty quoted name"));
    };
    if mode != "webapp" || header.depth != 0 || title.trim().is_empty() {
        return Err(header.error("Expected webapp and a nonempty quoted name"));
    }
    let mut domain = format!("app {}\n", serde_json::to_string(title).unwrap());
    let mut presentation = Vec::new();
    let mut palettes = BTreeMap::new();
    let mut theme_state = None;
    let mut views = Vec::new();
    let mut service_blocks = Vec::new();
    let mut i = 1;
    while i < lines.len() {
        let line = &lines[i];
        if line.depth != 0 {
            return Err(line.error("Unexpected indentation"));
        }
        let from = i;
        i += 1;
        while i < lines.len() && lines[i].depth > 0 {
            i += 1;
        }
        let group = &lines[from..i];
        let keyword = line.text.split([' ', ':']).next().unwrap_or("");
        match keyword {
            "view" => views.push(group),
            "theme" if line.text != "theme:" => {
                let [Token::Word(_), Token::Word(name), Token::Colon] =
                    &syntax::tokens(line, &line.text)?[..]
                else {
                    return Err(line.error("Expected a named theme declaration"));
                };
                let mut palette = group.to_vec();
                palette[0].text = "theme:".into();
                if palettes.len() >= 8
                    || palettes
                        .insert(name.clone(), parse(&palette, false)?.0.theme)
                        .is_some()
                {
                    return Err(line.error("Duplicate or excessive named themes"));
                }
            }
            "theme-state" => {
                let [Token::Word(_), Token::Word(key)] = &syntax::tokens(line, &line.text)?[..]
                else {
                    return Err(line.error("Expected one mutable theme state"));
                };
                if !group[1..].is_empty() || theme_state.replace(key.clone()).is_some() {
                    return Err(line.error("Invalid or duplicate theme-state"));
                }
            }
            "theme" | "style" | "stylesheet" | "license" | "favicon" => {
                presentation.extend_from_slice(group)
            }
            "service" => service_blocks.push(group),
            "navigation" | "screen" | "origin" | "robots" | "social-image" => {
                return Err(line.error(format!("Unsupported native WebApp declaration {keyword}")));
            }
            _ if views.is_empty() => {
                for row in group {
                    domain.push_str(&" ".repeat(row.depth * 4));
                    domain.push_str(&row.text);
                    domain.push('\n');
                }
            }
            _ => return Err(line.error("Expected a WebApp view")),
        }
    }
    let (mut presentation, styles) = parse(&presentation, false)?;
    // The WebApp presentation supplies the views; parse the core domain without legacy screens.
    let mut program = parser::parse(&domain)?;
    if let Some(key) = &theme_state {
        let Some(crate::model::Value::Text(initial)) = program.states.get(key) else {
            return fail("Theme state requires a mutable text state");
        };
        presentation.theme = palettes
            .get(initial)
            .cloned()
            .ok_or_else(|| Error("Theme state requires a matching named palette".into()))?;
        let allowed = palettes
            .keys()
            .map(|name| format!("{key} == {}", web::json(name)))
            .collect::<Vec<_>>()
            .join(" or ");
        program.rules.push(crate::expr::parse(&allowed)?);
    } else if !palettes.is_empty() {
        return fail("Named themes require theme-state");
    }
    if !runtime::valid_state(&program, &program.states) {
        return fail("Invalid initial WebApp state");
    }
    let services = services::parse(&service_blocks, &program)?;
    let mut parsed: Vec<View> = Vec::new();
    let mut ids = BTreeSet::from(["content".into(), "sedrava-error".into()]);
    let mut count = 0;
    for group in views {
        let line = &group[0];
        let (name, route) = route(line, &program)?;
        if parsed.len() >= 32
            || parsed
                .iter()
                .any(|v| v.name == name || overlap(&v.route.path, &route.path))
        {
            return Err(line.error("Duplicate or overlapping WebApp route, or too many views"));
        }
        let mut nodes = parse_nodes(&group[1..], &mut 0, 1, &styles, Some(&program))?;
        let (mut previous, mut h1) = (0, 0);
        for node in &mut nodes {
            // WebApp permits nested navigation landmarks. Reuse heading and ID checks without Site landmark rules.
            validate_tree(node, false, &mut ids, &mut previous, &mut h1, false)?;
        }
        if h1 != 1 {
            return Err(line.error("WebApp requires exactly one h1 per view"));
        }
        parsed.push(View { name, route, nodes });
    }
    let names: BTreeSet<_> = parsed.iter().map(|v| v.name.clone()).collect();
    if !names.contains("main") {
        return fail("WebApp requires an initial view main");
    }
    for view in &parsed {
        let mut dialog_ids = BTreeSet::new();
        collect_dialogs(&view.nodes, &mut dialog_ids, &mut count)?;
        validate_controls(
            &view.nodes,
            &dialog_ids,
            &names,
            None,
            false,
            None,
            &program,
            &services,
            false,
        )?;
    }
    fn count_sessions(nodes: &[Node]) -> usize {
        nodes.iter().map(|n| usize::from(n.kind=="session")+count_sessions(&n.children)).sum()
    }
    let auth=services.values().any(|s|s.session);
    let main_count=parsed.iter().filter(|v|v.name=="main").map(|v|count_sessions(&v.nodes)).sum::<usize>();
    let total_count=parsed.iter().map(|v|count_sessions(&v.nodes)).sum::<usize>();
    if (auth && (main_count!=1 || total_count!=1)) || (!auth && total_count!=0) {
        return fail("Authenticated WebApp requires exactly one session control in main view");
    }
    if parsed
        .iter()
        .map(|view| remote_render_cost(&view.nodes, &services))
        .sum::<usize>()
        > 20_000
    {
        return fail("WebApp HTTP remote rendering exceeds the document budget");
    }
    let mut script = String::from("'use strict';\n");
    let namespace = format!("webapp:{}", program.name);
    let names = web::append_domain(&program, &mut script, Some(&namespace))?;
    let config: BTreeMap<_, _> = parsed.iter().map(|v| (&v.name, &v.route)).collect();
    script.push_str(&format!(
        "const viewConfig = JSON.parse({});\n",
        web::json(&serde_json::to_string(&config).unwrap())
    ));
    script.push_str(&format!(
        "const themeState = {};\n",
        web::json(&theme_state)
    ));
    if !services.is_empty() {
        services::emit(&services, &names, &mut script)?;
    }
    script.push_str(include_str!("webapp.js"));
    render::webapp(
        &program.name,
        presentation,
        &palettes,
        &parsed,
        script,
        !services.is_empty(),
        root.as_deref(),
    )
}
