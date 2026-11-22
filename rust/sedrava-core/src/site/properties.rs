use super::syntax::{identifier, Line, Token};
use crate::model::Result;
use std::collections::BTreeMap;

pub(super) type Props = BTreeMap<String, String>;
pub(super) const BREAKPOINTS: [(&str, i32); 3] = [("sm", 640), ("md", 768), ("lg", 1024)];
pub(super) const THEME: [(&str, &str); 7] = [
    ("background", "#10101a"),
    ("surface", "#1c1a2b"),
    ("foreground", "#f7f4ff"),
    ("accent", "#b59bff"),
    ("gold", "#f3d087"),
    ("muted", "#bfb6d3"),
    ("border", "#49415d"),
];

pub(super) fn color(value: &str) -> Option<String> {
    if THEME.iter().any(|(key, _)| *key == value) {
        return Some(value.to_owned());
    }
    let hex = value.strip_prefix('#')?;
    if !matches!(hex.len(), 3 | 6) || !hex.bytes().all(|c| c.is_ascii_hexdigit()) {
        return None;
    }
    let hex = hex.to_ascii_lowercase();
    if hex.len() == 3 {
        return Some(format!(
            "#{}",
            hex.chars().flat_map(|c| [c, c]).collect::<String>()
        ));
    }
    Some(format!("#{hex}"))
}

pub(super) fn base_key(key: &str) -> (&str, Option<&str>) {
    match key.split_once('-') {
        Some((bp @ ("sm" | "md" | "lg"), name)) => (name, Some(bp)),
        _ => (key, None),
    }
}

pub(super) fn props(items: &[Token], line: &Line) -> Result<BTreeMap<String, Token>> {
    let mut result = BTreeMap::new();
    let mut i = 0;
    while i < items.len() {
        let Token::Word(key) = &items[i] else {
            return Err(line.error("Expected property name"));
        };
        i += 1;
        let val = if base_key(key).0 == "wrap" && !matches!(items.get(i), Some(Token::Bool(_))) {
            Token::Bool(true)
        } else {
            let value = items
                .get(i)
                .ok_or_else(|| line.error(format!("Missing value for {key}")))?;
            i += 1;
            value.clone()
        };
        if result.insert(key.clone(), val).is_some() {
            return Err(line.error(format!("Duplicate property {key}")));
        }
    }
    Ok(result)
}

pub(super) fn validate(
    key: &str,
    value: &Token,
    kind: Option<&str>,
    line: &Line,
) -> Result<String> {
    let (name, breakpoint) = base_key(key);
    let error = || line.error(format!("Unsupported or invalid property {key}"));
    if (kind.is_none()
        && matches!(
            name,
            "class" | "id" | "style" | "label" | "text" | "to" | "target" | "src" | "alt" | "level"
        ))
        || (breakpoint.is_some()
            && matches!(
                name,
                "class"
                    | "id"
                    | "style"
                    | "label"
                    | "text"
                    | "to"
                    | "target"
                    | "src"
                    | "alt"
                    | "level"
                    | "variant"
            ))
    {
        return Err(error());
    }
    let text = match value {
        Token::Word(v) | Token::Text(v) => v.as_str(),
        _ => "",
    };
    let int = |lo, hi| match value {
        Token::Int(v) if (lo..=hi).contains(v) => Some(v.to_string()),
        _ => None,
    };
    let choice = |options: &[&str]| options.contains(&text).then(|| text.to_owned());
    let raw = || match value {
        Token::Text(v) | Token::Word(v) => Some(v.clone()),
        _ => None,
    };
    let result = match name {
        "gap" | "padding" | "margin" | "height" => int(0, 4096),
        "width" => choice(&["auto", "full"]).or_else(|| int(1, 4096)),
        "max" => int(1, 4096),
        "size" if kind == Some("spacer") => int(0, 4096),
        "size" => int(10, 160),
        "radius" => int(0, 256),
        "color" | "background" => color(text),
        "align" => choice(&["start", "center", "end", "stretch"]),
        "justify" => choice(&["start", "center", "end", "between", "around", "evenly"]),
        "text-align" => choice(&["start", "center", "end", "left", "right"]),
        "weight" => choice(&["normal", "medium", "semibold", "bold"]),
        "shadow" => choice(&["none", "soft", "glow"]),
        "wrap" if kind.is_none() || kind == Some("row") => match value {
            Token::Bool(v) => Some(v.to_string()),
            _ => None,
        },
        "columns" if kind.is_none() || kind == Some("grid") => int(1, 12),
        "id" | "style" => identifier(text).then(|| text.to_owned()),
        "class" => {
            let classes: Vec<_> = text.split_whitespace().collect();
            ((1..=16).contains(&classes.len()) && classes.iter().all(|c| identifier(c)))
                .then(|| text.to_owned())
        }
        "label" => raw(),
        "text"
            if matches!(
                kind,
                Some("heading" | "paragraph" | "link" | "button" | "code")
            ) =>
        {
            raw()
        }
        "to" if matches!(kind, Some("link" | "button")) => raw(),
        "target" if matches!(kind, Some("link" | "button")) => choice(&["self", "blank"]),
        "src" | "alt" if kind == Some("image") => raw(),
        "level" if kind == Some("heading") => int(1, 6),
        "variant" => match kind {
            None => raw(),
            Some("heading") => choice(&["default", "display"]),
            Some("paragraph") => choice(&["default", "lead", "eyebrow", "muted", "brand"]),
            Some("link") => choice(&["default", "quiet"]),
            Some("button") => choice(&["primary", "secondary", "ghost"]),
            Some("card") => choice(&["default", "highlight", "muted"]),
            Some("callout") => choice(&["default", "info", "warning"]),
            Some(_) => None,
        },
        _ => None,
    };
    result.ok_or_else(error)
}

pub(super) fn defaults(kind: &str) -> Props {
    let pairs: &[(&str, &str)] = match kind {
        "container" => &[("max", "1160")],
        "row" => &[("gap", "16"), ("wrap", "true")],
        "column" => &[("gap", "16")],
        "grid" => &[("columns", "3"), ("gap", "20")],
        "button" => &[("variant", "primary")],
        "card" => &[("padding", "28"), ("radius", "24")],
        "spacer" => &[("size", "24")],
        "navbar" => &[
            ("gap", "16"),
            ("padding", "20"),
            ("label", "Primary navigation"),
        ],
        "footer" => &[("padding", "24")],
        "callout" => &[("padding", "24"), ("radius", "16")],
        "code" => &[("padding", "20"), ("radius", "12")],
        _ => &[],
    };
    pairs.iter().map(|&(k, v)| (k.into(), v.into())).collect()
}

pub(super) fn declarations(kind: &str, props: &Props) -> String {
    let mut result = Vec::new();
    for (key, value) in props {
        let value = value.as_str();
        let declaration = match key.as_str() {
            "gap" | "height" => format!("{key}:{value}px"),
            "radius" => format!("border-radius:{value}px"),
            "padding" => format!("padding:min({value}px,10%)"),
            "margin" => format!("--s-margin:min({value}px,5%);margin:var(--s-margin)"),
            "width" => match value {
                "auto" => "width:auto".into(),
                "full" => "width:100%".into(),
                _ => format!("width:min(100%,{value}px)"),
            },
            "max" => format!("--s-max:{value}px"),
            "size" if kind == "spacer" => format!("height:{value}px"),
            "size" => format!("font-size:{value}px"),
            "color" | "background" if value.starts_with('#') => format!("{key}:{value}"),
            "color" | "background" => format!("{key}:var(--{value})"),
            "align" => format!("align-items:{}", flex(value)),
            "justify" => format!("justify-content:{}", flex(value)),
            "text-align" => format!("text-align:{value}"),
            "weight" => format!(
                "font-weight:{}",
                match value {
                    "medium" => 500,
                    "semibold" => 600,
                    "bold" => 700,
                    _ => 400,
                }
            ),
            "shadow" => format!(
                "box-shadow:{}",
                match value {
                    "soft" => "0 18px 50px #00000030",
                    "glow" => "0 0 60px #b59bff18",
                    _ => "none",
                }
            ),
            "wrap" if value == "true" => "flex-wrap:wrap".into(),
            "wrap" => "flex-wrap:nowrap".into(),
            "columns" => format!("grid-template-columns:repeat({value},minmax(0,1fr))"),
            _ => continue,
        };
        result.push(declaration);
    }
    result.join(";")
}

fn flex(value: &str) -> &str {
    match value {
        "start" => "flex-start",
        "end" => "flex-end",
        "between" => "space-between",
        "around" => "space-around",
        "evenly" => "space-evenly",
        _ => value,
    }
}
