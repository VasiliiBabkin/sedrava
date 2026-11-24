//! A1 native Sedrava Server: a small, statically checked JSON HTTP DSL.
//! Experimental, loopback-only and deliberately not a general scripting host.
//! No Python, filesystem actions, outbound HTTP, DB or runtime eval.
use crate::model::{fail, Error, Result};
use serde::de::{self, MapAccess, Visitor};
use serde::{Deserialize, Deserializer};
use serde_json::{Map, Value};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};
use std::fmt;
use std::io::Write;
use std::net::TcpListener;
use std::thread;
use std::time::{Duration, Instant};

mod backend;
mod http;
mod journal;
mod kv_write;
mod sqlite;
mod sqlite_v2;
mod state;
mod storage;
mod transaction;

use backend::TransactionBackend;
use journal::JournalStore;
use kv_write::{BatchFailure, BatchPut, DbPut, PutFailure};
use sqlite::SqliteStore;
use sqlite_v2::SqliteV2Store;
use state::{StateDef, Step, Values};
use std::path::Path;
use storage::{SaveFailure, Store};
use transaction::{fingerprint, valid_key, Ledger, Receipt, MAX_RECEIPTS};

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

pub use state::Expr as ResponseValue;

#[derive(Clone, Debug)]
pub struct Route {
    method: String,
    path: String,
    request: BTreeMap<String, ScalarType>,
    steps: Vec<Step>,
    db_put: Option<DbPut>,
    batch_puts: Vec<BatchPut>,
    response: BTreeMap<String, ResponseValue>,
    status: u16,
}

#[derive(Clone, Debug)]
pub struct Server {
    pub name: String,
    routes: Vec<Route>,
    states: BTreeMap<String, StateDef>,
    source_sha: String,
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
    states: &BTreeMap<String, StateDef>,
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
        let (parsed, _kind) = state::expression(value, schema, states)?;
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
    let mut states = BTreeMap::new();
    let mut current: Option<Route> = None;
    let mut has_response = false;
    for (number, line) in lines.into_iter().skip(1) {
        if let Some(decl) = line.strip_prefix("state ") {
            if current.is_some() || !routes.is_empty() || states.len() >= 16 {
                return fail("E_SERVER_STATE: state declarations must precede routes (max 16)");
            }
            let (name, def) = state::parse_state(decl)?;
            if states.insert(name, def).is_some() {
                return fail("E_SERVER_STATE: duplicate state name");
            }
        } else if line.starts_with("route ") && !line.starts_with(' ') {
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
                steps: Vec::new(),
                db_put: None,
                batch_puts: Vec::new(),
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
            } else if content.starts_with("db_batch_put ") {
                if route.method != "PUT"
                    || has_response
                    || route.db_put.is_some()
                    || route.batch_puts.len() >= 2
                    || !route.steps.is_empty()
                {
                    return fail("E_SERVER_BATCH: exactly two batch puts precede a state update");
                }
                route
                    .batch_puts
                    .push(BatchPut::parse(content, &route.request)?);
            } else if content.starts_with("db_put ") {
                if route.method != "PUT"
                    || has_response
                    || route.db_put.is_some()
                    || !route.steps.is_empty()
                    || !route.batch_puts.is_empty()
                {
                    return fail("E_SERVER_DB_PUT: only one standalone PUT operation per route");
                }
                route.db_put = Some(DbPut::parse(content, &route.request)?);
            } else if content.starts_with("set ") || content.starts_with("require ") {
                if route.db_put.is_some() {
                    return fail("E_SERVER_DB_PUT: cannot mix KV put and state steps");
                }
                if !route.batch_puts.is_empty()
                    && (route.batch_puts.len() != 2
                        || !content.starts_with("set ")
                        || !route.steps.is_empty())
                {
                    return fail("E_SERVER_BATCH: requires one state set after two puts");
                }
                if has_response || route.steps.len() >= 32 {
                    return fail("E_SERVER_STEP: handler steps after response or over budget");
                }
                let step =
                    state::parse_step(content, &route.request, &states, route.method == "GET")?;
                route.steps.push(step);
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
                route.response = fields(value, &route.request, &states)?;
                if route.db_put.is_some()
                    && route
                        .response
                        .values()
                        .any(|v| !matches!(v, state::Expr::Literal(_) | state::Expr::Request(_)))
                {
                    return fail(
                        "E_SERVER_DB_PUT: response may use only request fields and literals",
                    );
                }
                if route.method != "GET"
                    && route.response.values().any(|v| {
                        matches!(
                            v,
                            state::Expr::DbGet { .. } | state::Expr::DbRevision { .. }
                        )
                    })
                {
                    return fail(
                        "E_SERVER_DB: database expressions permitted only in GET responses",
                    );
                }
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
        // Validate the FINISHED route: request declarations might have been
        // appended after db_put, bypassing its initial one-field check.
        if let Some(put) = &route.db_put {
            if route.method != "PUT"
                || !route.steps.is_empty()
                || route.request.len() != 1
                || route.request.get(&put.request_field) != Some(&ScalarType::Text)
            {
                return fail("E_SERVER_DB_PUT: only one declared text field, no state steps");
            }
        }
        if !route.batch_puts.is_empty() {
            if route.method != "PUT"
                || route.db_put.is_some()
                || route.batch_puts.len() != 2
                || !matches!(route.steps.as_slice(), [Step::Set { .. }])
                || route.request.len() != 4
            {
                return fail(
                    "E_SERVER_BATCH: two literal keys, four request fields and one state set",
                );
            }
            let a = &route.batch_puts[0];
            let b = &route.batch_puts[1];
            if (a.namespace.as_str(), a.key.as_str()) == (b.namespace.as_str(), b.key.as_str()) {
                return fail("E_SERVER_BATCH: duplicate managed key");
            }
            let names = [
                &a.value_field,
                &a.revision_field,
                &b.value_field,
                &b.revision_field,
            ];
            if names.iter().collect::<BTreeSet<_>>().len() != 4 {
                return fail("E_SERVER_BATCH: duplicate request field use");
            }
        }
        if !paths.insert((&route.method, &route.path)) {
            return fail("E_SERVER_PARSE: duplicate route");
        }
    }
    Ok(Server {
        name,
        routes,
        states,
        source_sha: format!("{:x}", Sha256::digest(source.as_bytes())),
    })
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

pub(crate) struct Session {
    values: Values,
    store: Option<Store>,
    journal: Option<JournalStore>,
    sqlite: Option<SqliteStore>,
    sqlite_v2: Option<SqliteV2Store>,
    revision_a6: Option<u32>,
    ledger: Option<Ledger>,
    poisoned: bool,
}
impl Session {
    fn open(
        program: &Server,
        state_dir: Option<&Path>,
        transactional: bool,
        journaled: bool,
        sqlite_state: Option<&Path>,
        sqlite_v2_state: Option<&Path>,
    ) -> Result<Self> {
        let uses_db = program.routes.iter().any(|r| {
            !r.batch_puts.is_empty()
                || r.db_put.is_some()
                || r.response.values().any(|v| {
                    matches!(
                        v,
                        state::Expr::DbGet { .. } | state::Expr::DbRevision { .. }
                    )
                })
        });
        if uses_db && sqlite_v2_state.is_none() {
            return fail("E_SERVER_DB: db_get requires --sqlite-v2-state (also db_revision)");
        }
        if transactional
            && state_dir.is_none()
            && sqlite_state.is_none()
            && sqlite_v2_state.is_none()
        {
            return fail(
                "E_SERVER_TRANSACTION: --transactional requires --state-dir, --sqlite-state or --sqlite-v2-state",
            );
        }
        if sqlite_state.is_some() && (!transactional || state_dir.is_some() || journaled) {
            return fail("E_SERVER_SQLITE: --sqlite-state requires --transactional and forbids --state-dir/--journaled");
        }
        if sqlite_v2_state.is_some()
            && (!transactional || state_dir.is_some() || journaled || sqlite_state.is_some())
        {
            return fail(
                "E_SERVER_SQLITE_V2: --sqlite-v2-state requires --transactional and is exclusive",
            );
        }
        if journaled && !transactional {
            return fail("E_SERVER_JOURNAL: --journaled requires --transactional");
        }
        let mut sqlite_v2 = None;
        let mut revision_a6 = None;
        let (store, journal, sqlite, values, ledger) = if let Some(path) = sqlite_v2_state {
            let (backend, values, revision) = SqliteV2Store::open(
                path,
                &program.name,
                &program.states,
                &program.source_sha,
                program.routes.iter().any(|r| !r.batch_puts.is_empty()),
            )?;
            sqlite_v2 = Some(backend);
            revision_a6 = Some(revision);
            (None, None, None, values, Ledger::default())
        } else if let Some(path) = sqlite_state {
            let (sqlite, values, ledger) =
                SqliteStore::open(path, &program.name, &program.states, &program.source_sha)?;
            (None, None, Some(sqlite), values, ledger)
        } else if journaled {
            let dir = state_dir.expect("checked --state-dir");
            let (journal, values, ledger) =
                JournalStore::open(dir, &program.name, &program.states, &program.source_sha)?;
            (None, Some(journal), None, values, ledger)
        } else if let Some(dir) = state_dir {
            let (store, values, ledger) =
                Store::open(dir, &program.name, &program.states, transactional)?;
            (Some(store), None, None, values, ledger)
        } else {
            (
                None,
                None,
                None,
                program
                    .states
                    .iter()
                    .map(|(name, def)| (name.clone(), def.initial.clone()))
                    .collect(),
                Ledger::default(),
            )
        };
        Ok(Self {
            values,
            store,
            journal,
            sqlite,
            sqlite_v2,
            revision_a6,
            ledger: (transactional && sqlite_v2_state.is_none()).then_some(ledger),
            poisoned: false,
        })
    }

    fn active_revision(&self) -> Option<u32> {
        self.revision_a6
            .or_else(|| self.ledger.as_ref().map(Ledger::revision))
    }

    fn backend(&mut self) -> Option<&mut dyn TransactionBackend> {
        if let Some(sqlite) = self.sqlite.as_mut() {
            return Some(sqlite);
        }
        if let Some(journal) = self.journal.as_mut() {
            return Some(journal);
        }
        self.store
            .as_mut()
            .map(|store| store as &mut dyn TransactionBackend)
    }
}

#[cfg(test)]
pub(crate) fn reply(
    program: &Server,
    method: &str,
    path: &str,
    body: &[u8],
    content_type: Option<&str>,
) -> http::Response {
    let mut session =
        Session::open(program, None, false, false, None, None).expect("in-memory state");
    reply_stateful(
        program,
        &mut session,
        method,
        path,
        body,
        content_type,
        None,
        None,
    )
}

pub(crate) fn reply_stateful(
    program: &Server,
    session: &mut Session,
    method: &str,
    path: &str,
    body: &[u8],
    content_type: Option<&str>,
    idempotency_key: Option<&str>,
    expected_revision: Option<u32>,
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
    // Transactional replays must be resolved BEFORE evaluating user steps.
    // The fingerprint includes the exact payload and optional CAS condition.
    let mut transaction = None;
    if !route.batch_puts.is_empty() {
        let Some(key) = idempotency_key else {
            return http::Response::error(428, "IDEMPOTENCY_KEY_REQUIRED");
        };
        if !valid_key(key) {
            return http::Response::error(400, "INVALID_IDEMPOTENCY_KEY");
        }
        let Some(expected) = expected_revision else {
            return http::Response::error(428, "STATE_REVISION_REQUIRED");
        };
        let Some(db) = session.sqlite_v2.as_ref() else {
            return http::Response::error(503, "DB_BACKEND_REQUIRED");
        };
        let digest = fingerprint(
            method,
            path,
            content_type,
            body,
            Some(&expected.to_string()),
        );
        match db.lookup_route_batch(method, path, key) {
            Ok(Some(saved)) => {
                if saved.fingerprint != digest {
                    return http::Response::error(409, "IDEMPOTENCY_CONFLICT");
                }
                // Replay from a different process may refer to a state
                // revision this live Session has not loaded. Return the
                // original receipt but never keep serving stale state.
                if session
                    .active_revision()
                    .is_some_and(|r| r < saved.state_revision)
                {
                    session.poisoned = true;
                }
                return http::Response::json(saved.status, Value::Object(saved.response))
                    .with_revision(saved.state_revision)
                    .with_batch_kv_revisions(saved.key_revisions)
                    .as_replay();
            }
            Ok(None) => {}
            Err(_) => {
                session.poisoned = true;
                return http::Response::error(503, "BATCH_RECEIPT_FAILED");
            }
        }
        if session.active_revision() != Some(expected) {
            return http::Response::error(412, "STATE_REVISION_CONFLICT");
        }
    } else if route.db_put.is_some() {
        // A8 uses per-KV CAS/revision and a business-row receipt, not the
        // unrelated A6 server-state revision/receipt. No state mutation here.
        let Some(key) = idempotency_key else {
            return http::Response::error(428, "IDEMPOTENCY_KEY_REQUIRED");
        };
        if !valid_key(key) {
            return http::Response::error(400, "INVALID_IDEMPOTENCY_KEY");
        }
        if expected_revision.is_none() {
            return http::Response::error(428, "KV_REVISION_REQUIRED");
        }
    } else if session.active_revision().is_some() {
        if route.method != "GET" {
            let Some(key) = idempotency_key else {
                return http::Response::error(428, "IDEMPOTENCY_KEY_REQUIRED");
            };
            if !valid_key(key) {
                return http::Response::error(400, "INVALID_IDEMPOTENCY_KEY");
            }
            let expected = expected_revision.map(|r| r.to_string());
            let digest = fingerprint(method, path, content_type, body, expected.as_deref());
            let prior = if let Some(ledger) = session.ledger.as_ref() {
                ledger.get(key).cloned()
            } else if let Some(db) = session.sqlite_v2.as_ref() {
                match db.lookup(key) {
                    Ok(entry) => entry,
                    Err(_) => {
                        session.poisoned = true;
                        return http::Response::error(503, "RECEIPT_LOOKUP_FAILED");
                    }
                }
            } else {
                None
            };
            if let Some(prior) = prior {
                if prior.fingerprint == digest {
                    return http::Response::json(
                        prior.status,
                        Value::Object(prior.response.clone()),
                    )
                    .with_revision(prior.revision)
                    .as_replay();
                }
                return http::Response::error(409, "IDEMPOTENCY_CONFLICT");
            }
            if session
                .ledger
                .as_ref()
                .is_some_and(|ledger| ledger.receipts.len() >= MAX_RECEIPTS)
            {
                return http::Response::error(507, "TRANSACTION_LEDGER_FULL");
            }
            if expected_revision.is_some_and(|rev| Some(rev) != session.active_revision()) {
                return http::Response::error(412, "REVISION_CONFLICT");
            }
            transaction = Some((key.to_owned(), digest));
        } else if idempotency_key.is_some() || expected_revision.is_some() {
            return http::Response::error(400, "READ_CANNOT_USE_TRANSACTION_HEADERS");
        }
    }
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
    // Candidate is isolated until all handler statements, response
    // expressions and optional durable storage succeed.
    let request: Values = bindings.into_iter().collect();
    let mut candidate = session.values.clone();
    if let Err(error) = state::run(&route.steps, &request, &mut candidate) {
        return match error {
            state::EvalError::Overflow => http::Response::error(422, "INTEGER_OVERFLOW"),
            state::EvalError::GuardRejected => http::Response::error(422, "GUARD_REJECTED"),
            state::EvalError::Invalid => http::Response::error(500, "HANDLER_FAILED"),
        };
    }
    let mut output = Map::new();
    // Resolve read-only SedravaSQL key/value lookups for GET responses.
    // Transient DB values are never written into server state.
    let mut view = candidate.clone();
    // A10: collect all distinct referenced managed keys before fetching.
    // SedravaSQL B7 reads them in ONE SQLite read-only transaction, so
    // concurrent B6/A9 batches cannot yield mixed commit generations.
    // In-memory candidate state is NOT part of this database snapshot.
    let mut references = BTreeSet::new();
    for expression in route.response.values() {
        match expression {
            state::Expr::DbGet { namespace, key, .. }
            | state::Expr::DbRevision { namespace, key, .. } => {
                references.insert((namespace.clone(), key.clone()));
            }
            _ => {}
        }
    }
    let mut db_rows = BTreeMap::new();
    if !references.is_empty() {
        let Some(db) = session.sqlite_v2.as_ref() else {
            return http::Response::error(503, "DB_BACKEND_REQUIRED");
        };
        let keys: Vec<_> = references.into_iter().collect();
        let values = match db.read_text_snapshot(&keys) {
            Ok(rows) => rows,
            Err(_) => {
                session.poisoned = true;
                return http::Response::error(503, "DB_READ_FAILED");
            }
        };
        for (key, value) in keys.into_iter().zip(values) {
            let Some(value) = value else {
                return http::Response::error(404, "DB_KEY_NOT_FOUND");
            };
            db_rows.insert(key, value);
        }
    }
    for expression in route.response.values() {
        let (namespace, key, slot, is_revision) = match expression {
            state::Expr::DbGet {
                namespace,
                key,
                slot,
            } => (namespace, key, slot, false),
            state::Expr::DbRevision {
                namespace,
                key,
                slot,
            } => (namespace, key, slot, true),
            _ => continue,
        };
        let (value, revision) = db_rows
            .get(&(namespace.clone(), key.clone()))
            .expect("all requested keys resolved");
        let result = if is_revision {
            let Ok(number) = i32::try_from(*revision) else {
                return http::Response::error(503, "DB_REVISION_RANGE");
            };
            Value::from(number)
        } else {
            Value::String(value.clone())
        };
        view.insert(slot.clone(), result);
    }
    for (key, expr) in &route.response {
        match state::eval(expr, &request, &view) {
            Ok(value) => {
                output.insert(key.clone(), value);
            }
            Err(state::EvalError::Overflow) => {
                return http::Response::error(422, "INTEGER_OVERFLOW")
            }
            Err(_) => return http::Response::error(500, "HANDLER_FAILED"),
        }
    }
    if !route.batch_puts.is_empty() {
        let Some(sql) = session.sqlite_v2.as_mut() else {
            return http::Response::error(503, "DB_BACKEND_REQUIRED");
        };
        let key = idempotency_key.expect("A9 headers checked");
        let expected = expected_revision.expect("A9 state revision checked");
        let digest = fingerprint(
            method,
            path,
            content_type,
            body,
            Some(&expected.to_string()),
        );
        return match sql.commit_route_batch(
            &route.batch_puts,
            &request,
            &candidate,
            expected,
            method,
            path,
            key,
            &digest,
            route.status,
            output,
        ) {
            Ok((receipt, replayed)) => {
                session.values = candidate;
                session.revision_a6 = Some(receipt.state_revision);
                let response =
                    http::Response::json(receipt.status, Value::Object(receipt.response))
                        .with_revision(receipt.state_revision)
                        .with_batch_kv_revisions(receipt.key_revisions);
                if replayed {
                    response.as_replay()
                } else {
                    response
                }
            }
            Err(BatchFailure::RevisionConflict) => {
                http::Response::error(412, "BATCH_REVISION_CONFLICT")
            }
            Err(BatchFailure::IdempotencyConflict) => {
                http::Response::error(409, "IDEMPOTENCY_CONFLICT")
            }
            Err(BatchFailure::Invalid) => http::Response::error(422, "BATCH_INVALID_REVISION"),
            Err(BatchFailure::Uncertain) => {
                session.poisoned = true;
                http::Response::error(503, "DB_BATCH_UNCERTAIN")
            }
        };
    }
    if let Some(put) = &route.db_put {
        let Some(sql) = session.sqlite_v2.as_mut() else {
            return http::Response::error(503, "DB_BACKEND_REQUIRED");
        };
        let Some(value) = request.get(&put.request_field).and_then(Value::as_str) else {
            return http::Response::error(422, "REQUEST_SCHEMA_MISMATCH");
        };
        let key = idempotency_key.expect("A8 checked headers");
        let expected = expected_revision.expect("A8 checked revision");
        let digest = fingerprint(
            method,
            path,
            content_type,
            body,
            Some(&expected.to_string()),
        );
        return match sql.put_text(
            put,
            method,
            path,
            value,
            expected,
            key,
            &digest,
            route.status,
            output,
        ) {
            Ok((receipt, replayed)) => {
                let response =
                    http::Response::json(receipt.status, Value::Object(receipt.response))
                        .with_kv_revision(receipt.revision);
                if replayed {
                    response.as_replay()
                } else {
                    response
                }
            }
            Err(PutFailure::IdempotencyConflict) => {
                http::Response::error(409, "IDEMPOTENCY_CONFLICT")
            }
            Err(PutFailure::RevisionConflict) => http::Response::error(412, "REVISION_CONFLICT"),
            Err(PutFailure::Invalid) => http::Response::error(507, "KV_REVISION_EXHAUSTED"),
            Err(PutFailure::Uncertain) => {
                session.poisoned = true;
                http::Response::error(503, "DB_PUT_UNCERTAIN")
            }
        };
    }
    if let Some((key, digest)) = transaction {
        let Some(revision) = session.active_revision().and_then(|v| v.checked_add(1)) else {
            return http::Response::error(507, "TRANSACTION_REVISION_EXHAUSTED");
        };
        let receipt = Receipt {
            key,
            fingerprint: digest,
            revision,
            status: route.status,
            response: output.clone(),
        };
        if let Some(sqlite_v2) = session.sqlite_v2.as_mut() {
            match sqlite_v2.commit(&candidate, &receipt) {
                Ok(()) => {
                    session.values = candidate;
                    session.revision_a6 = Some(revision);
                    return http::Response::json(route.status, Value::Object(output))
                        .with_revision(revision);
                }
                Err(SaveFailure::RejectedBeforeCommit) => {
                    return http::Response::error(503, "STATE_WRITE_FAILED");
                }
                Err(SaveFailure::DurabilityUncertain) => {
                    session.poisoned = true;
                    return http::Response::error(503, "STATE_COMMIT_UNCERTAIN");
                }
            }
        }
        let ledger = session
            .ledger
            .as_ref()
            .expect("A3/A4/A5 transactional mode");
        let Some(next) = ledger.append(receipt) else {
            return http::Response::error(507, "TRANSACTION_LEDGER_FULL");
        };
        if let Some(backend) = session.backend() {
            match backend.commit(&candidate, &next) {
                Ok(()) => {}
                Err(SaveFailure::RejectedBeforeCommit) => {
                    return http::Response::error(503, "STATE_WRITE_FAILED")
                }
                Err(SaveFailure::DurabilityUncertain) => {
                    session.poisoned = true;
                    return http::Response::error(503, "STATE_COMMIT_UNCERTAIN");
                }
            }
        }
        session.values = candidate;
        session.ledger = Some(next);
        return http::Response::json(route.status, Value::Object(output)).with_revision(revision);
    }
    if candidate != session.values {
        if let Some(store) = session.store.as_mut() {
            match store.save(&candidate) {
                Ok(()) => {}
                Err(SaveFailure::RejectedBeforeCommit) => {
                    return http::Response::error(503, "STATE_WRITE_FAILED")
                }
                Err(SaveFailure::DurabilityUncertain) => {
                    // Rename may already be visible. Stop to prevent
                    // subsequent requests from using stale in-memory state.
                    session.poisoned = true;
                    return http::Response::error(503, "STATE_COMMIT_UNCERTAIN");
                }
            }
        }
        session.values = candidate;
    }
    let response = http::Response::json(route.status, Value::Object(output));
    if let Some(revision) = session.active_revision() {
        response.with_revision(revision)
    } else {
        response
    }
}

/// Single-threaded local preview: no listening on public interfaces,
/// no long-lived keep-alive connections or concurrent state mutation.
pub fn serve(
    program: &Server,
    options: RuntimeOptions,
    state_dir: Option<&Path>,
    transactional: bool,
    journaled: bool,
    sqlite_state: Option<&Path>,
    sqlite_v2_state: Option<&Path>,
) -> Result<()> {
    if options.max_requests == 0
        || options.max_requests > 10_000
        || options.idle_ms < 500
        || options.idle_ms > 120_000
    {
        return fail("E_SERVER_RUN: max_requests 1..10000 and idle_ms 500..120000 required");
    }
    let mut session = Session::open(
        program,
        state_dir,
        transactional,
        journaled,
        sqlite_state,
        sqlite_v2_state,
    )?;
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
                http::process(program, &mut session, &mut stream);
                if session.poisoned {
                    return fail("E_SERVER_STORAGE: post-commit sync uncertain; process stopped");
                }
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
