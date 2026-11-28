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
    pub session: bool,
    idempotency: bool,
    sql_columns: Option<Vec<String>>,
    #[serde(skip_serializing_if = "Vec::is_empty")]
    refresh: Vec<String>,
    #[serde(skip_serializing_if = "is_false")]
    tracked: bool,
    #[serde(skip)]
    body: Option<Expr>,
    #[serde(skip)]
    body_fields: BTreeMap<String, Expr>,
}

fn is_false(value: &bool) -> bool {
    !*value
}

impl Service {
    pub fn allows_remote_pick(&self) -> bool {
        self.session && self.sql_columns.is_some() && !self.idempotency
    }
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
        let mut sql_rows = false;
        let mut columns = Vec::new();
        let mut body_fields = BTreeMap::new();
        for line in &block[1..] {
            let (key, value) = line
                .text
                .split_once(' ')
                .ok_or_else(|| line.error("Missing HTTP declaration value"))?;
            match line.depth {
                1 if many.is_none() && key == "body-field" => {
                    let (field, raw) = value
                        .split_once(' ')
                        .ok_or_else(|| line.error("Expected body-field NAME EXPRESSION"))?;
                    if !name(field) || body_fields.len() >= 32 || body_fields.contains_key(field) {
                        return Err(line.error("Invalid or duplicate HTTP body field"));
                    }
                    let value = expr::parse(raw)?;
                    if !matches!(
                        expr::infer(&value, &program.types)?,
                        Kind::Int | Kind::Text | Kind::Bool
                    ) {
                        return Err(line.error("HTTP body-field requires a scalar expression"));
                    }
                    body_fields.insert(field.to_owned(), value);
                }
                1 if many.is_none() && key == "response" => {
                    many = Some(match value {
                        "one:" => false,
                        "many:" => true,
                        "sql-rows:" => {
                            sql_rows = true;
                            true
                        }
                        _ => return Err(line.error("Expected response one:, many: or sql-rows:")),
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
                            | "auth"
                            | "idempotency"
                            | "refresh"
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
                    columns.push(key.to_owned());
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
        if body.is_some() && !body_fields.is_empty() {
            return Err(header.error("HTTP body and body-field cannot be combined"));
        }
        if mutation != (body.is_some() || !body_fields.is_empty()) {
            return Err(
                header.error("POST, PUT and PATCH require a typed body; GET and DELETE forbid one")
            );
        }
        if let Some(body) = &body {
            if !matches!(expr::infer(body, &program.types)?, Kind::Record { .. }) {
                return Err(header.error("HTTP body requires a typed record"));
            }
        }
        let session = match properties.get("auth") {
            None => false,
            Some(&"session") => true,
            _ => return Err(header.error("HTTP auth requires session")),
        };
        let idempotency = match properties.get("idempotency") {
            None | Some(&"false") => false,
            Some(&"true") if session && mutation => true,
            _ => {
                return Err(
                    header.error("HTTP idempotency requires authenticated POST, PUT or PATCH")
                )
            }
        };
        if sql_rows && flag("cache")? {
            return Err(header.error("SQL row envelopes forbid persistent cache"));
        }
        if session && (flag("auto")? || flag("cache")?) {
            return Err(header.error("Authenticated services forbid auto and persistent cache"));
        }
        if session && ["/session-policy", "/session-login", "/session-logout"].contains(&path) {
            return Err(header.error("Session endpoints are reserved"));
        }
        let refresh = properties
            .get("refresh")
            .map(|raw| {
                raw.split_ascii_whitespace()
                    .map(str::to_owned)
                    .collect::<Vec<_>>()
            })
            .unwrap_or_default();
        if properties.contains_key("refresh")
            && (!idempotency
                || sql_rows
                || many != Some(false)
                || fields.len() != 4
                || fields.get("kind") != Some(&"text")
                || fields.get("affected") != Some(&"int32")
                || fields.get("sequence") != Some(&"int32")
                || fields.get("replayed") != Some(&"bool")
                || refresh.is_empty()
                || refresh.len() > 8
                || refresh.iter().any(|n| !name(n))
                || refresh
                    .iter()
                    .collect::<std::collections::BTreeSet<_>>()
                    .len()
                    != refresh.len())
        {
            return Err(header.error(
                "Refresh requires a typed authenticated mutation receipt and unique read targets",
            ));
        }
        services.insert(
            service_name.to_owned(),
            Service {
                path: path.into(),
                method: method.into(),
                body,
                body_fields,
                fields,
                session,
                idempotency,
                sql_columns: sql_rows.then_some(columns),
                refresh,
                tracked: false,
                many: many.unwrap(),
                timeout: integer("timeout", 10000, 100, 30000)?,
                max_bytes: integer("max-bytes", 65536, 1, 200000)?,
                max_items: integer("max-items", 100, 1, 1000)?,
                auto: flag("auto")?,
                cache: flag("cache")?,
            },
        );
    }
    let targets = services
        .values()
        .flat_map(|s| s.refresh.iter().cloned())
        .collect::<std::collections::BTreeSet<_>>();
    for target in targets {
        let service = services
            .get_mut(&target)
            .ok_or_else(|| crate::model::Error("E_HTTP: unknown refresh target".into()))?;
        if !service.allows_remote_pick()
            || !service.refresh.is_empty()
            || service.cache
            || service.auto
        {
            return Err(crate::model::Error("E_HTTP: refresh target must be authenticated non-idempotent SQL rows without cache or auto".into()));
        }
        service.tracked = true;
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
        } else if !service.body_fields.is_empty() {
            let entries = service
                .body_fields
                .iter()
                .map(|(field, value)| {
                    Ok(format!(
                        "[{},{}]",
                        web::json(field),
                        web::expr_js(value, names)?
                    ))
                })
                .collect::<Result<Vec<_>>>()?;
            writeln!(
                js,
                "serviceBodies[{}] = (r) => Object.fromEntries([{}]);",
                web::json(name),
                entries.join(",")
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
    fn refresh_contract() {
        let prefix="webapp \"Refresh\"\nstate value = \"x\"\nservice rows:\n    origin self\n    path \"/rows\"\n    auth session\n    response sql-rows:\n        id text\nservice write:\n    origin self\n    path \"/write\"\n    method POST\n    auth session\n    idempotency true\n    refresh rows\n    body-field id value\n    response one:\n        kind text\n        affected int32\n        sequence int32\n        replayed bool\nview main:\n    heading \"Refresh\"\n    session \"Key\"\n    remote rows:\n        field id\n    remote write:\n        field affected\n";
        let build = |s: &str| super::super::webapp::generate(s, None);
        assert!(build(prefix).is_ok());
        for s in [
            prefix.replace("refresh rows", "refresh missing"),
            prefix.replace("refresh rows", "refresh rows rows"),
            prefix.replace("refresh rows", "refresh write"),
            prefix.replace("    idempotency true\n", ""),
            prefix.replace("affected int32", "affected text"),
            prefix.replacen("auth session", "cache true", 1),
        ] {
            assert!(build(&s).is_err(), "{s}");
        }
    }

    #[test]
    fn remote_pick_type_and_scope_contract() {
        let prefix = "webapp \"Pick\"\nstate selected = \"\"\nstate n = 0\nstate yes = false\nderive computed = selected\nservice rows:\n    origin self\n    path \"/rows\"\n    auth session\n    response sql-rows:\n        id text\n        number int32\n        enabled bool\nview main:\n    heading \"Test\"\n    session \"Key\"\n    remote rows:\n";
        let build = |source: &str| super::super::webapp::generate(source, None);
        assert!(build(&format!("{prefix}        remote-pick \"Select\" bindings \"id:selected number:n enabled:yes\"\n")).is_ok());
        for bindings in [
            "id:n",
            "missing:selected",
            "id:computed",
            "id:selected id:selected",
            "id:missing",
            "id:selected:number",
            "",
        ] {
            assert!(
                build(&format!(
                    "{prefix}        remote-pick \"Select\" bindings \"{bindings}\"\n"
                ))
                .is_err(),
                "{bindings}"
            );
        }
        let good = format!("{prefix}        remote-pick \"Select\" bindings \"id:selected\"\n");
        assert!(
            build(&good.replace("derive computed", "persist selected\nderive computed")).is_err()
        );
        assert!(build(&good.replace("        remote-pick", "    remote-pick")).is_err());
        assert!(build(
            &good
                .replace("    auth session\n", "")
                .replace("    session \"Key\"\n", "")
        )
        .is_err());
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
