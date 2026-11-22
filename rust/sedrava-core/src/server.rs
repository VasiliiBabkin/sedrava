//! A1 native Sedrava Server: a small, statically checked JSON HTTP DSL.
//! Experimental, loopback-only and deliberately not a general scripting host.
//! No Python, filesystem actions, outbound HTTP, DB or runtime eval.
use crate::model::{fail, Error, Result};
use serde::de::{self, MapAccess, Visitor};
use serde::{Deserialize, Deserializer};
use serde_json::{Map, Value};
use std::collections::{BTreeMap, BTreeSet};
use std::fmt;
use std::io::Write;
use std::net::TcpListener;
use std::thread;
use std::time::{Duration, Instant};

mod http;

pub const MAX_REQUEST_BODY: usize = 16_384;
const MAX_SOURCE: usize = 32_768;
const MAX_ROUTE_COUNT: usize = 32;
const MAX_ROUTE_FIELDS: usize = 16;
const MAX_RESPONSE_FIELDS: usize = 32;
const MAX_SCALAR_TEXT: usize = 1_024;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum ScalarType {
    Text,
    Int,
    Bool,
}

#[derive(Clone, Debug, PartialEq)]
pub enum ResponseValue {
    Literal(Value),
    RequestField(String),
}

#[derive(Clone, Debug)]
pub struct Route {
    method: String,
    path: String,
    request: BTreeMap<String, ScalarType>,
    response: BTreeMap<String, ResponseValue>,
    status: u16,
}

#[derive(Clone, Debug)]
pub struct Server {
    pub name: String,
    routes: Vec<Route>,
}

#[derive(Clone, Copy, Debug)]
pub struct RuntimeOptions {
    pub port: u16,
    pub max_requests: u32,
    pub idle_ms: u32,
}

fn identifier(raw: &str) -> bool {
    let mut chars = raw.chars();
    matches!(chars.next(), Some(c) if c.is_ascii_alphabetic())
        && chars.all(|c| c.is_ascii_alphanumeric() || c == '_')
        && raw.len() <= 64
}

fn pathname(path: &str) -> bool {
    path.starts_with('/')
        && path.len() <= 128
        && !path.contains("//")
        && !path.contains("..")
        && path
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || matches!(b, b'/' | b'_' | b'-'))
}

fn json_string(raw: &str) -> Result<String> {
    let value: String = serde_json::from_str(raw)
        .map_err(|_| Error("E_SERVER_PARSE: expected a JSON double-quoted string".into()))?;
    if value.chars().count() > MAX_SCALAR_TEXT || value.chars().any(|c| c.is_control()) {
        return fail("E_SERVER_PARSE: illegal control character or excessive text length");
    }
    Ok(value)
}

fn fields(
    raw: &str,
    schema: &BTreeMap<String, ScalarType>,
) -> Result<BTreeMap<String, ResponseValue>> {
    let source = raw.trim();
    if !source.starts_with('{') || !source.ends_with('}') {
        return fail("E_SERVER_RESPONSE: expected { field: scalar, ... }");
    }
    let inner = &source[1..source.len() - 1];
    if inner.trim().is_empty() {
        return fail("E_SERVER_RESPONSE: response object cannot be empty");
    }
    // Splitting only outside JSON quoted strings prevents string injection,
    // including strings containing a comma, colon, or escaped quote.
    let mut parts = Vec::new();
    let mut quoted = false;
    let mut escaped = false;
    let mut last = 0;
    for (idx, ch) in inner.char_indices() {
        if quoted {
            if escaped {
                escaped = false;
            } else if ch == '\\' {
                escaped = true;
            } else if ch == '"' {
                quoted = false;
            }
        } else if ch == '"' {
            quoted = true;
        } else if ch == ',' {
            parts.push(inner[last..idx].trim());
            last = idx + 1;
        }
    }
    if quoted || escaped {
        return fail("E_SERVER_RESPONSE: unterminated quoted value");
    }
    parts.push(inner[last..].trim());
    if parts.len() > MAX_RESPONSE_FIELDS {
        return fail("E_SERVER_RESPONSE: too many fields");
    }
    let mut result = BTreeMap::new();
    for item in parts {
        let (key, value) = item
            .split_once(':')
            .ok_or_else(|| Error("E_SERVER_RESPONSE: expected name: value".into()))?;
        let key = key.trim();
        let value = value.trim();
        if !identifier(key) || result.contains_key(key) || value.is_empty() {
            return fail("E_SERVER_RESPONSE: invalid or repeated response key");
        }
        let parsed = if let Some(field) = value.strip_prefix("request.") {
            if !identifier(field) || !schema.contains_key(field) {
                return fail("E_SERVER_RESPONSE: unknown typed request field");
            }
            ResponseValue::RequestField(field.into())
        } else {
            let literal: Value = serde_json::from_str(value)
                .map_err(|_| Error("E_SERVER_RESPONSE: expected JSON scalar".into()))?;
            match &literal {
                Value::String(v)
                    if v.chars().count() <= MAX_SCALAR_TEXT && !v.chars().any(char::is_control) => {
                }
                Value::Bool(_) => {}
                Value::Number(v) if v.as_i64().is_some_and(|n| i32::try_from(n).is_ok()) => {}
                _ => return fail("E_SERVER_RESPONSE: only text, int32 and bool literals"),
            }
            ResponseValue::Literal(literal)
        };
        result.insert(key.to_string(), parsed);
    }
    Ok(result)
}

pub fn parse(source: &str) -> Result<Server> {
    if source.len() > MAX_SOURCE || source.contains('\r') || source.contains('\0') {
        return fail("E_SERVER_PARSE: oversized or illegal source");
    }
    let mut lines = Vec::new();
    for (idx, raw) in source.lines().enumerate() {
        if raw.trim().is_empty() || raw.trim_start().starts_with('#') {
            continue;
        }
        if raw.contains('\t') || raw.trim_end() != raw {
            return fail(format!(
                "E_SERVER_PARSE: line {} uses tabs or trailing whitespace",
                idx + 1
            ));
        }
        lines.push((idx + 1, raw));
    }
    let Some((_, first)) = lines.first() else {
        return fail("E_SERVER_PARSE: source is empty");
    };
    let Some(header) = first.strip_prefix("server ") else {
        return fail("E_SERVER_PARSE: expected server \"name\"");
    };
    let name = json_string(header)?;
    if name.is_empty() || name.chars().count() > 64 {
        return fail("E_SERVER_PARSE: invalid server name");
    }
    let mut routes = Vec::new();
    let mut current: Option<Route> = None;
    let mut has_response = false;
    for (number, line) in lines.into_iter().skip(1) {
        if line.starts_with("route ") && !line.starts_with(' ') {
            if let Some(previous) = current.take() {
                if !has_response {
                    return fail(format!(
                        "E_SERVER_PARSE: route {} missing respond",
                        previous.path
                    ));
                }
                routes.push(previous);
            }
            has_response = false;
            if routes.len() >= MAX_ROUTE_COUNT {
                return fail("E_SERVER_PARSE: route limit exceeded");
            }
            let declaration = line.strip_prefix("route ").unwrap();
            let (method, quoted) = declaration
                .split_once(' ')
                .ok_or_else(|| Error("E_SERVER_PARSE: expected route METHOD \"/path\":".into()))?;
            if !matches!(method, "GET" | "POST" | "PUT" | "PATCH" | "DELETE")
                || !quoted.ends_with(':')
            {
                return fail("E_SERVER_PARSE: unsupported method or missing colon");
            }
            let path = json_string(&quoted[..quoted.len() - 1])?;
            if !pathname(&path) {
                return fail("E_SERVER_PARSE: path must be an exact ASCII /path without query");
            }
            if routes.iter().any(|r| r.method == method && r.path == path) {
                return fail("E_SERVER_PARSE: duplicate route");
            }
            current = Some(Route {
                method: method.into(),
                path,
                request: BTreeMap::new(),
                response: BTreeMap::new(),
                status: 200,
            });
        } else if let Some(content) = line.strip_prefix("    ") {
            if content.starts_with(' ') {
                return fail(format!("E_SERVER_PARSE: invalid indent at line {number}"));
            }
            let route = current
                .as_mut()
                .ok_or_else(|| Error("E_SERVER_PARSE: declaration outside route".into()))?;
            if let Some(field) = content.strip_prefix("request ") {
                if has_response || !matches!(route.method.as_str(), "POST" | "PUT" | "PATCH") {
                    return fail(
                        "E_SERVER_PARSE: request fields must precede response on write routes",
                    );
                }
                if route.request.len() >= MAX_ROUTE_FIELDS {
                    return fail("E_SERVER_PARSE: too many request fields");
                }
                let (key, kind) = field
                    .split_once(": ")
                    .ok_or_else(|| Error("E_SERVER_PARSE: expected request name: type".into()))?;
                if !identifier(key) || route.request.contains_key(key) {
                    return fail("E_SERVER_PARSE: duplicate or invalid request field");
                }
                let kind = match kind {
                    "int" => ScalarType::Int,
                    "text" => ScalarType::Text,
                    "bool" => ScalarType::Bool,
                    _ => return fail("E_SERVER_PARSE: only int, bool, text supported"),
                };
                route.request.insert(key.to_string(), kind);
            } else if let Some(response) = content.strip_prefix("respond ") {
                if has_response {
                    return fail("E_SERVER_PARSE: multiple respond statements");
                }
                let (status, value) = response.split_once(' ').ok_or_else(|| {
                    Error("E_SERVER_PARSE: expected respond STATUS { ... }".into())
                })?;
                route.status = status
                    .parse::<u16>()
                    .map_err(|_| Error("E_SERVER_PARSE: invalid response status".into()))?;
                if !matches!(route.status, 200 | 201 | 202) {
                    return fail("E_SERVER_PARSE: only 200, 201, 202 accepted in A1");
                }
                route.response = fields(value, &route.request)?;
                has_response = true;
            } else {
                return fail(format!(
                    "E_SERVER_PARSE: unknown statement at line {number}"
                ));
            }
        } else {
            return fail(format!("E_SERVER_PARSE: illegal top-level line {number}"));
        }
    }
    if let Some(route) = current {
        if !has_response {
            return fail("E_SERVER_PARSE: last route has no respond");
        }
        routes.push(route);
    }
    if routes.is_empty() {
        return fail("E_SERVER_PARSE: server requires at least one route");
    }
    let mut paths = BTreeSet::new();
    for route in &routes {
        if !paths.insert((&route.method, &route.path)) {
            return fail("E_SERVER_PARSE: duplicate route");
        }
    }
    Ok(Server { name, routes })
}

struct StrictObject(Map<String, Value>);

impl<'de> Deserialize<'de> for StrictObject {
    fn deserialize<D: Deserializer<'de>>(deserializer: D) -> std::result::Result<Self, D::Error> {
        struct Reader;
        impl<'de> Visitor<'de> for Reader {
            type Value = StrictObject;
            fn expecting(&self, fmt: &mut fmt::Formatter) -> fmt::Result {
                write!(fmt, "JSON object without duplicate keys")
            }
            fn visit_map<A: MapAccess<'de>>(
                self,
                mut map: A,
            ) -> std::result::Result<Self::Value, A::Error> {
                let mut object = Map::new();
                while let Some((key, value)) = map.next_entry::<String, Value>()? {
                    if object.contains_key(&key) {
                        return Err(de::Error::custom("duplicate request field"));
                    }
                    object.insert(key, value);
                }
                Ok(StrictObject(object))
            }
        }
        deserializer.deserialize_map(Reader)
    }
}

pub(crate) fn reply(
    program: &Server,
    method: &str,
    path: &str,
    body: &[u8],
    content_type: Option<&str>,
) -> http::Response {
    let Some(route) = program
        .routes
        .iter()
        .find(|r| r.method == method && r.path == path)
    else {
        if program.routes.iter().any(|r| r.path == path) {
            let methods = program
                .routes
                .iter()
                .filter(|r| r.path == path)
                .map(|r| r.method.as_str())
                .collect::<BTreeSet<_>>()
                .into_iter()
                .collect::<Vec<_>>()
                .join(", ");
            return http::Response::error(405, "METHOD_NOT_ALLOWED").with_allow(methods);
        }
        return http::Response::error(404, "NOT_FOUND");
    };
    let mut bindings = Map::new();
    if body.len() > MAX_REQUEST_BODY {
        return http::Response::error(413, "BODY_TOO_LARGE");
    }
    if route.request.is_empty() {
        if !body.is_empty() {
            return http::Response::error(400, "UNEXPECTED_BODY");
        }
    } else {
        if body.is_empty() {
            return http::Response::error(422, "EXPECTED_JSON_OBJECT");
        }
        if content_type.map(str::trim) != Some("application/json") {
            return http::Response::error(415, "JSON_CONTENT_TYPE_REQUIRED");
        }
        // Limit nesting to a single object with scalar values. serde_json is
        // allowed to parse arbitrary nesting but only after a byte cap and
        // validation rejects every non-scalar binding.
        let mut decoder = serde_json::Deserializer::from_slice(body);
        let object = match StrictObject::deserialize(&mut decoder) {
            Ok(StrictObject(value)) if decoder.end().is_ok() => value,
            _ => return http::Response::error(400, "INVALID_JSON"),
        };
        if object.len() != route.request.len() {
            return http::Response::error(422, "REQUEST_SCHEMA_MISMATCH");
        }
        for (key, kind) in &route.request {
            let Some(value) = object.get(key) else {
                return http::Response::error(422, "REQUEST_SCHEMA_MISMATCH");
            };
            let valid = match (kind, value) {
                (ScalarType::Text, Value::String(v)) => {
                    v.chars().count() <= MAX_SCALAR_TEXT && !v.chars().any(char::is_control)
                }
                (ScalarType::Bool, Value::Bool(_)) => true,
                (ScalarType::Int, Value::Number(v)) => {
                    v.as_i64().is_some_and(|n| i32::try_from(n).is_ok())
                }
                _ => false,
            };
            if !valid {
                return http::Response::error(422, "REQUEST_SCHEMA_MISMATCH");
            }
            bindings.insert(key.clone(), value.clone());
        }
    }
    let mut output = Map::new();
    for (key, value) in &route.response {
        let data = match value {
            ResponseValue::Literal(v) => v.clone(),
            ResponseValue::RequestField(name) => bindings[name].clone(),
        };
        output.insert(key.clone(), data);
    }
    http::Response::json(route.status, Value::Object(output))
}

/// Single-threaded local preview: no listening on public interfaces,
/// no long-lived keep-alive connections or concurrent state mutation.
pub fn serve(program: &Server, options: RuntimeOptions) -> Result<()> {
    if options.max_requests == 0
        || options.max_requests > 10_000
        || options.idle_ms < 500
        || options.idle_ms > 120_000
    {
        return fail("E_SERVER_RUN: max_requests 1..10000 and idle_ms 500..120000 required");
    }
    let listener = TcpListener::bind(("127.0.0.1", options.port))
        .map_err(|e| Error(format!("E_SERVER_BIND: unable to bind loopback: {e}")))?;
    listener
        .set_nonblocking(true)
        .map_err(|e| Error(format!("E_SERVER_BIND: cannot set nonblocking: {e}")))?;
    let local = listener
        .local_addr()
        .map_err(|e| Error(format!("E_SERVER_BIND: local address unavailable: {e}")))?;
    println!("LISTENING http://127.0.0.1:{}", local.port());
    std::io::stdout()
        .flush()
        .map_err(|e| Error(format!("E_SERVER_RUN: cannot print listen address: {e}")))?;
    let idle = Duration::from_millis(u64::from(options.idle_ms));
    let mut last = Instant::now();
    let mut served = 0;
    while served < options.max_requests && last.elapsed() < idle {
        match listener.accept() {
            Ok((mut stream, _)) => {
                let _ = stream.set_read_timeout(Some(Duration::from_millis(1200)));
                let _ = stream.set_write_timeout(Some(Duration::from_millis(1200)));
                http::process(program, &mut stream);
                served += 1;
                last = Instant::now();
            }
            Err(e) if e.kind() == std::io::ErrorKind::WouldBlock => {
                thread::sleep(Duration::from_millis(10))
            }
            Err(e) if e.kind() == std::io::ErrorKind::Interrupted => continue,
            Err(e) => return fail(format!("E_SERVER_RUN: accept error: {e}")),
        }
    }
    println!("STOPPED requests={served}");
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn valid() -> &'static str {
        "server \"API\"\nroute GET \"/health\":\n    respond 200 { status: \"ok\", version: 1 }\nroute POST \"/items\":\n    request name: text\n    request quantity: int\n    request enabled: bool\n    respond 201 { name: request.name, quantity: request.quantity, enabled: request.enabled, status: \"created\" }\n"
    }

    #[test]
    fn parse_and_respond_with_checked_types() {
        let server = parse(valid()).unwrap();
        assert_eq!(server.routes.len(), 2);
        let r = reply(&server, "GET", "/health", b"", None);
        assert_eq!(r.status, 200);
        assert_eq!(r.body["status"], "ok");
        let r = reply(
            &server,
            "POST",
            "/items",
            br#"{"name":"milk","quantity":2,"enabled":true}"#,
            Some("application/json"),
        );
        assert_eq!(r.status, 201);
        assert_eq!(r.body["name"], "milk");
        assert_eq!(r.body["quantity"], 2);
        assert_eq!(r.body["enabled"], true);
        for malformed in [
            r#"{"name":"milk","quantity":2147483648,"enabled":true}"#,
            r#"{"name":"milk","quantity":"two","enabled":true}"#,
            r#"{"name":"milk","quantity":2,"enabled":true,"secret":1}"#,
            r#"{"name":"milk","quantity":2}"#,
            r#"{"name":"milk","quantity":2,"enabled":null}"#,
        ] {
            assert_eq!(
                reply(
                    &server,
                    "POST",
                    "/items",
                    malformed.as_bytes(),
                    Some("application/json")
                )
                .status,
                422
            );
        }
        assert_eq!(
            reply(&server, "POST", "/items", b"{}", Some("text/plain")).status,
            415
        );
        assert_eq!(reply(&server, "DELETE", "/items", b"", None).status, 405);
        assert_eq!(
            reply(
                &server,
                "POST",
                "/items",
                br#"{"name":"a","name":"b","quantity":2,"enabled":true}"#,
                Some("application/json")
            )
            .status,
            400
        );
        assert_eq!(reply(&server, "GET", "/missing", b"", None).status, 404);
    }
    #[test]
    fn rejects_routes_with_ambiguous_or_effectful_forms() {
        for raw in [
            "server \"API\"\n",
            "server \"API\"\nroute GET \"/health\":\n",
            "server \"API\"\nroute GET \"/health\":\n    respond 200 {status: \"ok\"}\nroute GET \"/health\":\n    respond 200 {a: 1}\n",
            "server \"API\"\nroute GET \"/../secret\":\n    respond 200 {a: 1}\n",
            "server \"API\"\nroute GET \"/health\":\n    request name: text\n    respond 200 {a: 1}\n",
            "server \"API\"\nroute POST \"/health\":\n    respond 200 {a: request.secret}\n",
            "server \"API\"\nroute GET \"/health\":\n    respond 200 {a: [1,2]}\n",
            "server \"API\"\nroute GET \"/health\":\n    respond 200 {a: 1.5}\n",
            "server \"API\"\nroute GET \"/health\":\n    respond 200 {a: 20000000000}\n",
            "server \"API\"\nroute GET \"/health\":\n    respond 200 {a: null}\n",
            "server \"API\"\nroute GET \"/health\":\n    respond 204 {a: true}\n",
            "server \"API\"\nroute GET \"/health\":\n    respond 200 {a: 1, a: 2}\n",
            "server \"API\"\nroute GET \"/health\":\n    respond 200 {a: 1}\n    respond 200 {a: 2}\n",
            "server \"API\"\nroute GET \"/health\":\n        respond 200 {a: 1}\n",
            "server \"API\"\nroute GET \"/health\":\n    action write:\n        disk.write(\"secret\")\n",
        ] {
            assert!(parse(raw).is_err(), "{raw}");
        }
    }
    #[test]
    fn response_literals_escape_colons_commas_and_quotes() {
        let program = parse("server \"T\"\nroute GET \"/\":\n    respond 200 { message: \"hello, world: \\\"value\\\"\", safe: true }\n").unwrap();
        let reply = reply(&program, "GET", "/", b"", None);
        assert_eq!(reply.body["message"], "hello, world: \"value\"");
    }
}
