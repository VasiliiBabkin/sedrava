//! Typed public browser HTTP capabilities. The compiler performs no network I/O.
use super::syntax::{identifier, Line};
use crate::{
    expr,
    model::{Expr, Kind, Program, Result},
    web,
};
use regex::Regex;
use serde::Serialize;
use std::{collections::BTreeMap, sync::LazyLock};

pub(super) type Services = BTreeMap<String, Service>;

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub(super) struct Service {
    path: String,
    method: String,
    timeout: u32,
    max_bytes: u32,
    many: bool,
    max_items: u32,
    pub fields: BTreeMap<String, &'static str>,
    auto: bool,
    cache: bool,
    #[serde(skip)]
    body: Option<Expr>,
}

impl Service {
    pub fn max_rows(&self) -> usize {
        if self.many {
            self.max_items as usize
        } else {
            1
        }
    }
}

fn name(value: &str) -> bool {
    identifier(value) && !value.contains('-')
}

fn literal<'a>(line: &Line, raw: &'a str) -> Result<&'a str> {
    raw.strip_prefix('"')
        .and_then(|s| s.strip_suffix('"'))
        .filter(|s| !s.contains(['"', '\\']))
        .ok_or_else(|| line.error("Expected an unescaped quoted HTTP literal"))
}

pub(super) fn parse(blocks: &[&[Line]], program: &Program) -> Result<Services> {
    static PARAMETER: LazyLock<Regex> =
        LazyLock::new(|| Regex::new(r":([A-Za-z][A-Za-z0-9_]*)").unwrap());
    let mut services = Services::new();
    for block in blocks {
        let header = &block[0];
        let service_name = header
            .text
            .strip_prefix("service ")
            .and_then(|s| s.strip_suffix(':'))
            .filter(|s| name(s))
            .ok_or_else(|| header.error("Invalid service declaration"))?;
        if services.len() >= 16 || services.contains_key(service_name) {
            return Err(header.error("Duplicate service or service limit exceeded"));
        }
        let mut properties = BTreeMap::new();
        let mut fields = BTreeMap::new();
        let mut many = None;
        for line in &block[1..] {
            let (key, value) = line
                .text
                .split_once(' ')
                .ok_or_else(|| line.error("Missing HTTP declaration value"))?;
            match line.depth {
                1 if many.is_none() && key == "response" => {
                    many = Some(match value {
                        "one:" => false,
                        "many:" => true,
                        _ => return Err(line.error("Expected response one: or response many:")),
                    });
                }
                1 if many.is_none()
                    && matches!(
                        key,
                        "origin"
                            | "path"
                            | "method"
                            | "timeout"
                            | "max-bytes"
                            | "max-items"
                            | "auto"
                            | "cache"
                            | "body"
                    ) =>
                {
                    if properties.insert(key, value).is_some() {
                        return Err(line.error("Duplicate HTTP property"));
                    }
                }
                2 if many.is_some() && name(key) => {
                    let kind = match value {
                        "int32" => "int32",
                        "text" => "text",
                        "bool" => "bool",
                        _ => return Err(line.error("Unknown HTTP field type")),
                    };
                    if fields.len() >= 32 || fields.insert(key.to_owned(), kind).is_some() {
                        return Err(line.error("Duplicate HTTP field or field limit exceeded"));
                    }
                }
                _ => return Err(line.error("Unexpected or unsupported HTTP declaration")),
            }
        }
        if fields.is_empty() {
            return Err(header.error("Service requires a response schema with fields"));
        }
        // Cross-origin browser connections cannot pin or verify DNS resolution.
        match properties.get("origin") {
            Some(&"self") => {}
            Some(origin) => {
                literal(header, origin)?;
                return Err(header.error("HTTP policy denies external origins; use origin self"));
            }
            None => return Err(header.error("Service requires origin")),
        }
        let path = literal(
            header,
            properties
                .get("path")
                .ok_or_else(|| header.error("Service requires path"))?,
        )?;
        if !path.starts_with('/')
            || path.starts_with("//")
            || path.len() > 2048
            || path.split('/').any(|part| matches!(part, "." | ".."))
            || path
                .bytes()
                .any(|b| !b.is_ascii_graphic() || b"?#%\\<>\"'".contains(&b))
        {
            return Err(header.error("HTTP path must be a bounded safe origin-relative ASCII path"));
        }
        let without_parameters = PARAMETER.replace_all(path, "");
        if without_parameters.contains(':')
            || PARAMETER
                .captures_iter(path)
                .any(|capture| program.types.get(&capture[1]) != Some(&Kind::Int))
        {
            return Err(
                header.error("HTTP path parameters require integer state or derived values")
            );
        }
        let method = properties.get("method").copied().unwrap_or("GET");
        if !matches!(method, "GET" | "POST" | "PUT" | "PATCH" | "DELETE") {
            return Err(header.error("Unsupported HTTP method"));
        }
        let integer = |key, default, min, max| match properties.get(key) {
            None => Ok(default),
            Some(raw) if raw.bytes().all(|b| b.is_ascii_digit()) => raw
                .parse::<u32>()
                .ok()
                .filter(|value| (min..=max).contains(value))
                .ok_or_else(|| header.error(format!("HTTP {key} is outside {min}..={max}"))),
            _ => Err(header.error(format!("HTTP {key} requires an unsigned integer"))),
        };
        let flag = |key| match properties.get(key) {
            None | Some(&"false") => Ok(false),
            Some(&"true") if method == "GET" => Ok(true),
            _ => Err(header.error(format!(
                "HTTP {key} requires a boolean and is only enabled for GET"
            ))),
        };
        let mutation = matches!(method, "POST" | "PUT" | "PATCH");
        let body = properties
            .get("body")
            .map(|value| expr::parse(value))
            .transpose()?;
        if mutation != body.is_some() {
            return Err(
                header.error("POST, PUT and PATCH require a typed body; GET and DELETE forbid one")
            );
        }
        if let Some(body) = &body {
            if !matches!(expr::infer(body, &program.types)?, Kind::Record { .. }) {
                return Err(header.error("HTTP body requires a typed record"));
            }
        }
        services.insert(
            service_name.to_owned(),
            Service {
                path: path.into(),
                method: method.into(),
                body,
                fields,
                many: many.unwrap(),
                timeout: integer("timeout", 10000, 100, 30000)?,
                max_bytes: integer("max-bytes", 65536, 1, 200000)?,
                max_items: integer("max-items", 100, 1, 1000)?,
                auto: flag("auto")?,
                cache: flag("cache")?,
            },
        );
    }
    Ok(services)
}

pub(super) fn emit(
    services: &Services,
    names: &BTreeMap<String, String>,
    js: &mut String,
) -> Result<()> {
    use std::fmt::Write;
    writeln!(
        js,
        "const serviceConfigs = JSON.parse({});",
        web::json(&serde_json::to_string(services).unwrap())
    )
    .unwrap();
    js.push_str("const serviceBodies = Object.create(null);\n");
    for (name, service) in services {
        if let Some(body) = &service.body {
            writeln!(
                js,
                "serviceBodies[{}] = (r) => ({});",
                web::json(name),
                web::expr_js(body, names)?
            )
            .unwrap();
        }
    }
    js.push_str(include_str!("services.js"));
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::parser;

    fn service(source: &str) -> Result<Services> {
        let program = parser::parse(
            "app \"HTTP\"\nstate id = 1\nderive target = id + 1\nstate label = \"one\"\n",
        )?;
        let lines = super::super::syntax::lines(source)?;
        parse(&[&lines], &program)
    }

    #[test]
    fn accepts_typed_derived_targets_and_fixed_limits() {
        let services = service(
            "service rows:\n    origin self\n    path \"/rows/:target\"\n    timeout 100\n    max-items 1\n    response many:\n        id int32\n",
        ).unwrap();
        assert_eq!(services["rows"].timeout, 100);
        assert_eq!(services["rows"].max_items, 1);
    }

    #[test]
    fn rejects_unsafe_targets_and_mistyped_bindings() {
        for path in [
            "//example.invalid/",
            "/a/../b",
            "/a/%252e",
            "/a?query",
            "/a/:label",
            "/a/:missing",
        ] {
            let source = format!("service rows:\n    origin self\n    path \"{path}\"\n    response one:\n        id int32\n");
            assert!(service(&source).is_err(), "{path}");
        }
        for origin in [
            "https://example.com",
            "https://localhost",
            "https://127.0.0.1",
            "http://192.168.0.1",
        ] {
            let source = format!("service rows:\n    origin \"{origin}\"\n    path \"/rows\"\n    response one:\n        id int32\n");
            assert!(service(&source).is_err(), "{origin}");
        }
    }

    #[test]
    fn rejects_implicit_methods_inconsistent_body_policy_and_limits() {
        for parameters in [
            "    method OPTIONS\n",
            "    method POST\n",
            "    body id\n",
            "    method POST\n    body label\n",
            "    method DELETE\n    cache true\n",
            "    method DELETE\n    auto true\n",
            "    timeout 99\n",
            "    timeout 30001\n",
            "    max-bytes 200001\n",
            "    max-items 1001\n",
            "    auto true\n    auto false\n",
        ] {
            let source = format!("service rows:\n    origin self\n    path \"/rows\"\n{parameters}    response one:\n        id int32\n");
            assert!(service(&source).is_err(), "{parameters}");
        }
    }

    #[test]
    fn rejects_remote_templates_that_exceed_render_budget() {
        let source = "webapp \"HTTP\"\nservice rows:\n    origin self\n    path \"/rows\"\n    max-items 1000\n    response many:\n        id int32\nview main:\n    heading \"Test\"\n    remote rows:\n".to_owned()
            + &"        field id\n".repeat(8);
        let error = match super::super::webapp::generate(&source, None) {
            Ok(_) => panic!("expected a rendering budget rejection"),
            Err(error) => error,
        };
        assert!(error.0.contains("remote rendering exceeds"));
    }
}
