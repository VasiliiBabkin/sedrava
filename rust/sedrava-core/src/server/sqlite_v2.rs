//! A6 experimental SQLite-backed state and permanently retained HTTP receipts.
//! Uses the separate, pinned SedravaSQL transaction API. No silent eviction;
//! operator-controlled archive/migration is not implemented.
use super::kv_write::{
    BatchFailure, BatchPut, DbPut, PutFailure, PutReceipt, ServerBatchReceipt, BATCH_HTTP_SCHEMA,
    RECEIPT_SCHEMA,
};
use super::state::{scalar_type, StateDef, Values};
use super::storage::{signature, SaveFailure};
use super::transaction::Receipt as HttpReceipt;
use crate::model::{fail, Error, Result};
use sedravasql::managed_batch::ManagedPut;
use sedravasql::{Change, Database, MAX_VALUE_BYTES};
use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;
use std::path::Path;

const NAMESPACE: &str = "sedrava_native_a6";
const SCHEMA: &str = "sedrava.server.sqlite.v2";

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct StateSnapshot {
    schema: String,
    signature: String,
    revision: u32,
    state: Values,
}

pub struct SqliteV2Store {
    db: Database,
    key: String,
    signature: String,
    defs: BTreeMap<String, StateDef>,
    db_revision: u64,
}

impl SqliteV2Store {
    pub fn open(
        path: &Path,
        name: &str,
        defs: &BTreeMap<String, StateDef>,
        source_sha: &str,
        enable_batches: bool,
    ) -> Result<(Self, Values, u32)> {
        if defs.is_empty() {
            return fail("E_SERVER_SQLITE_V2: state declarations required");
        }
        let types_sig = signature(name, defs)?;
        let raw = serde_json::to_vec(&(SCHEMA, source_sha, types_sig))
            .map_err(|_| Error("E_SERVER_SQLITE_V2: signature encode failed".into()))?;
        let signature = format!("{:x}", Sha256::digest(raw));
        let key = format!("s_{signature}");
        let mut db = Database::init(path)
            .map_err(|_| Error("E_SERVER_SQLITE_V2: database open failed".into()))?;
        if enable_batches {
            db.enable_managed_batches()
                .map_err(|_| Error("E_SERVER_BATCH: opt-in schema failed".into()))?;
        }
        db.verify()
            .map_err(|_| Error("E_SERVER_SQLITE_V2: database verification failed".into()))?;
        let saved = db
            .read(NAMESPACE, &key)
            .map_err(|_| Error("E_SERVER_SQLITE_V2: state read failed".into()))?;
        let (values, revision, db_revision) = if let Some(entry) = saved {
            let text = entry
                .value
                .ok_or_else(|| Error("E_SERVER_SQLITE_V2: deleted state row".into()))?;
            if text.len() > MAX_VALUE_BYTES {
                return fail("E_SERVER_SQLITE_V2: state too large");
            }
            let decoded: StateSnapshot = serde_json::from_str(&text)
                .map_err(|_| Error("E_SERVER_SQLITE_V2: invalid stored state".into()))?;
            if decoded.schema != SCHEMA
                || decoded.signature != signature
                || u64::from(decoded.revision) != entry.revision
                || !Self::valid_state(defs, &decoded.state)
            {
                return fail("E_SERVER_SQLITE_V2: state signature/revision/type mismatch");
            }
            (decoded.state, decoded.revision, entry.revision)
        } else {
            (
                defs.iter()
                    .map(|(k, v)| (k.clone(), v.initial.clone()))
                    .collect(),
                0,
                0,
            )
        };
        Ok((
            Self {
                db,
                key,
                signature,
                defs: defs.clone(),
                db_revision,
            },
            values,
            revision,
        ))
    }

    fn valid_state(defs: &BTreeMap<String, StateDef>, values: &Values) -> bool {
        values.len() == defs.len()
            && defs
                .iter()
                .all(|(key, def)| values.get(key).and_then(scalar_type) == Some(def.kind))
    }

    fn scoped_request(&self, client_key: &str) -> String {
        let encoded = serde_json::to_vec(&(self.signature.as_str(), client_key))
            .expect("tuple serialization");
        format!("r{:x}", Sha256::digest(encoded))
    }

    /// Narrow read-only bridge to a managed SedravaSQL UTF-8 KV value.
    pub fn read_text_and_revision(
        &self,
        namespace: &str,
        key: &str,
    ) -> Result<Option<(String, u64)>> {
        if namespace.starts_with("sedrava_native") {
            return fail("E_SERVER_DB: reserved namespace");
        }
        let entry = self
            .db
            .read(namespace, key)
            .map_err(|_| Error("E_SERVER_DB: KV read failed".into()))?;
        match entry {
            None => Ok(None),
            Some(row) => {
                let Some(text) = row.value else {
                    return Ok(None);
                };
                if text.chars().count() > 1_024 || text.chars().any(char::is_control) {
                    return fail("E_SERVER_DB: stored value outside text scalar limits");
                }
                Ok(Some((text, row.revision)))
            }
        }
    }

    fn put_receipt_key(
        &self,
        namespace: &str,
        key: &str,
        method: &str,
        route: &str,
        client_key: &str,
    ) -> String {
        let encoded = serde_json::to_vec(&(
            RECEIPT_SCHEMA,
            &self.signature,
            namespace,
            key,
            method,
            route,
            client_key,
        ))
        .expect("fixed tuple encoding");
        format!("r{:x}", Sha256::digest(encoded))
    }

    fn load_put_receipt(
        &self,
        put: &DbPut,
        route: &str,
        scoped: &str,
    ) -> std::result::Result<Option<PutReceipt>, PutFailure> {
        let saved = self
            .db
            .lookup_receipt(&put.namespace, scoped)
            .map_err(|_| PutFailure::Uncertain)?;
        let Some(saved) = saved else { return Ok(None) };
        if saved.namespace != put.namespace
            || saved.key != put.key
            || saved.operation != "put"
            || saved.revision == 0
        {
            return Err(PutFailure::Uncertain);
        }
        let body = saved.application_response.ok_or(PutFailure::Uncertain)?;
        let parsed: PutReceipt = serde_json::from_str(&body).map_err(|_| PutFailure::Uncertain)?;
        if parsed.schema != RECEIPT_SCHEMA
            || parsed.program_signature != self.signature
            || parsed.route != route
            || !matches!(parsed.status, 200..=202)
            || u64::from(parsed.revision) != saved.revision
            || parsed.revision > i32::MAX as u32
            || parsed.fingerprint.len() != 64
            || !parsed
                .fingerprint
                .bytes()
                .all(|c| c.is_ascii_hexdigit() && !c.is_ascii_uppercase())
        {
            return Err(PutFailure::Uncertain);
        }
        Ok(Some(parsed))
    }

    /// A8: commit ONE public managed KV value + audit + full HTTP receipt
    /// through SedravaSQL's already-atomic mutate_with_response transaction.
    ///
    /// No server-state mutation or generic SQL. Per-key revision (NOT A6
    /// server-state revision) appears in X-Sedrava-Revision.
    #[allow(clippy::too_many_arguments)]
    pub fn put_text(
        &mut self,
        put: &DbPut,
        method: &str,
        path: &str,
        value: &str,
        expected: u32,
        client_key: &str,
        fingerprint: &str,
        status: u16,
        response: Map<String, Value>,
    ) -> std::result::Result<(PutReceipt, bool), PutFailure> {
        let next = expected
            .checked_add(1)
            .filter(|r| *r <= i32::MAX as u32)
            .ok_or(PutFailure::Invalid)?;
        if method != "PUT"
            || value.chars().count() > 1024
            || value.chars().any(char::is_control)
            || !matches!(status, 200..=202)
            || !super::transaction::valid_key(client_key)
        {
            return Err(PutFailure::Uncertain);
        }
        let route = format!("{method} {path}");
        let scoped = self.put_receipt_key(&put.namespace, &put.key, method, path, client_key);
        let receipt = PutReceipt {
            schema: RECEIPT_SCHEMA.into(),
            program_signature: self.signature.clone(),
            route: route.clone(),
            client_key: client_key.into(),
            fingerprint: fingerprint.into(),
            revision: next,
            status,
            response,
        };
        let response_json = serde_json::to_string(&receipt).map_err(|_| PutFailure::Uncertain)?;
        if response_json.len() > 16_384 {
            return Err(PutFailure::Uncertain);
        }
        if let Some(prior) = self.load_put_receipt(put, &route, &scoped)? {
            if prior.client_key != client_key {
                return Err(PutFailure::Uncertain);
            }
            if prior.fingerprint != fingerprint {
                return Err(PutFailure::IdempotencyConflict);
            }
            return if prior == receipt {
                Ok((prior, true))
            } else {
                Err(PutFailure::Uncertain)
            };
        }
        let stored = self.db.mutate_with_response(
            &put.namespace,
            &put.key,
            Change::Put(value),
            u64::from(expected),
            &scoped,
            &response_json,
        );
        match stored {
            Ok(done) => {
                if done.namespace != put.namespace
                    || done.key != put.key
                    || done.operation != "put"
                    || done.revision != u64::from(next)
                    || done.application_response.as_deref() != Some(&response_json)
                {
                    return Err(PutFailure::Uncertain);
                }
                Ok((receipt, done.replayed))
            }
            Err(sedravasql::Error::Conflict(_)) => {
                // Read the scoped receipt again in case another process won
                // the race with the same idempotency key. Otherwise CAS stale.
                match self.load_put_receipt(put, &route, &scoped)? {
                    Some(prior) if prior.client_key != client_key => Err(PutFailure::Uncertain),
                    Some(prior) if prior.fingerprint != fingerprint => {
                        Err(PutFailure::IdempotencyConflict)
                    }
                    Some(prior) if prior == receipt => Ok((prior, true)),
                    Some(_) => Err(PutFailure::Uncertain),
                    None => Err(PutFailure::RevisionConflict),
                }
            }
            Err(_) => Err(PutFailure::Uncertain),
        }
    }

    fn route_batch_scope(&self, method: &str, path: &str) -> String {
        let tuple = serde_json::to_vec(&(BATCH_HTTP_SCHEMA, &self.signature, method, path))
            .expect("static scope tuple");
        format!("s{:x}", Sha256::digest(tuple))
    }

    /// Read a durable A9 whole-response before touching ANY candidate
    /// server state. This is required for exact replay of an older request.
    pub fn lookup_route_batch(
        &self,
        method: &str,
        path: &str,
        client_key: &str,
    ) -> Result<Option<ServerBatchReceipt>> {
        let scope = self.route_batch_scope(method, path);
        let saved = self
            .db
            .lookup_managed_batch(&scope, client_key)
            .map_err(|_| Error("E_SERVER_BATCH: receipt lookup failed".into()))?;
        let Some(saved) = saved else { return Ok(None) };
        if saved.revisions.len() != 3 {
            return fail("E_SERVER_BATCH: receipt does not contain two keys and state");
        }
        let parsed: ServerBatchReceipt = serde_json::from_str(&saved.application_response)
            .map_err(|_| Error("E_SERVER_BATCH: invalid persisted app receipt".into()))?;
        if parsed.schema != BATCH_HTTP_SCHEMA
            || parsed.program_signature != self.signature
            || parsed.route != format!("{method} {path}")
            || parsed.client_key != client_key
            || parsed.state_revision as u64 != saved.revisions[2]
            || parsed.key_revisions.len() != 2
            || parsed
                .key_revisions
                .iter()
                .zip(saved.revisions.iter())
                .any(|(a, b)| u64::from(*a) != *b)
            || !matches!(parsed.status, 200..=202)
            || parsed.fingerprint.len() != 64
            || !parsed
                .fingerprint
                .bytes()
                .all(|b| b.is_ascii_hexdigit() && !b.is_ascii_uppercase())
        {
            return fail("E_SERVER_BATCH: persisted receipt metadata mismatch");
        }
        Ok(Some(parsed))
    }

    #[allow(clippy::too_many_arguments)]
    pub fn commit_route_batch(
        &mut self,
        declarations: &[BatchPut],
        request: &Values,
        candidate: &Values,
        expected_state: u32,
        method: &str,
        path: &str,
        client_key: &str,
        fingerprint: &str,
        status: u16,
        response: Map<String, Value>,
    ) -> std::result::Result<(ServerBatchReceipt, bool), BatchFailure> {
        if declarations.len() != 2
            || method != "PUT"
            || !matches!(status, 200 | 201 | 202)
            || expected_state != self.db_revision as u32
            || !Self::valid_state(&self.defs, candidate)
        {
            return Err(BatchFailure::Uncertain);
        }
        let state_revision = expected_state
            .checked_add(1)
            .filter(|r| *r <= i32::MAX as u32)
            .ok_or(BatchFailure::Invalid)?;
        let mut ops = Vec::with_capacity(3);
        let mut kv_revisions = Vec::with_capacity(2);
        for entry in declarations {
            let Some(value) = request.get(&entry.value_field).and_then(Value::as_str) else {
                return Err(BatchFailure::Invalid);
            };
            if value.chars().count() > 1024 || value.chars().any(char::is_control) {
                return Err(BatchFailure::Invalid);
            }
            let Some(expected) = request
                .get(&entry.revision_field)
                .and_then(Value::as_i64)
                .and_then(|v| u32::try_from(v).ok())
            else {
                return Err(BatchFailure::Invalid);
            };
            let next = expected
                .checked_add(1)
                .filter(|r| *r <= i32::MAX as u32)
                .ok_or(BatchFailure::Invalid)?;
            ops.push(ManagedPut {
                namespace: entry.namespace.clone(),
                key: entry.key.clone(),
                value: value.to_owned(),
                expected_revision: u64::from(expected),
            });
            kv_revisions.push(next);
        }
        let state = StateSnapshot {
            schema: SCHEMA.into(),
            signature: self.signature.clone(),
            revision: state_revision,
            state: candidate.clone(),
        };
        let snapshot = serde_json::to_string(&state).map_err(|_| BatchFailure::Uncertain)?;
        if snapshot.len() > MAX_VALUE_BYTES {
            return Err(BatchFailure::Invalid);
        }
        ops.push(ManagedPut {
            namespace: NAMESPACE.into(),
            key: self.key.clone(),
            value: snapshot,
            expected_revision: self.db_revision,
        });
        let app = ServerBatchReceipt {
            schema: BATCH_HTTP_SCHEMA.into(),
            program_signature: self.signature.clone(),
            route: format!("{method} {path}"),
            client_key: client_key.into(),
            fingerprint: fingerprint.into(),
            state_revision,
            key_revisions: kv_revisions,
            status,
            response,
        };
        let json = serde_json::to_string(&app).map_err(|_| BatchFailure::Uncertain)?;
        let scope = self.route_batch_scope(method, path);
        let result = self
            .db
            .commit_managed_batch(&scope, client_key, &ops, &json);
        match result {
            Ok(result) => {
                if result.revisions.len() != 3
                    || result.revisions[2] != u64::from(state_revision)
                    || result.application_response != json
                {
                    return Err(BatchFailure::Uncertain);
                }
                self.db_revision = u64::from(state_revision);
                Ok((app, result.replayed))
            }
            Err(sedravasql::Error::Conflict(_)) => {
                // Potentially a concurrent A9 or A6 writer. The caller
                // does not publish candidate state until commit succeeds.
                match self.lookup_route_batch(method, path, client_key) {
                    Ok(Some(existing)) if existing.fingerprint != fingerprint => {
                        Err(BatchFailure::IdempotencyConflict)
                    }
                    Ok(Some(existing)) if existing == app => {
                        self.db_revision = u64::from(existing.state_revision);
                        Ok((existing, true))
                    }
                    Ok(Some(_)) => Err(BatchFailure::Uncertain),
                    Ok(None) => {
                        // If another process has advanced the server-state
                        // row, this Session is stale: reject and poison it.
                        // A mere public-key CAS mismatch leaves state live.
                        let current = self.db.read(NAMESPACE, &self.key);
                        match current {
                            Ok(row) => {
                                let revision = row.as_ref().map_or(0, |v| v.revision);
                                if revision != self.db_revision {
                                    Err(BatchFailure::Uncertain)
                                } else {
                                    Err(BatchFailure::RevisionConflict)
                                }
                            }
                            Err(_) => Err(BatchFailure::Uncertain),
                        }
                    }
                    Err(_) => Err(BatchFailure::Uncertain),
                }
            }
            Err(_) => Err(BatchFailure::Uncertain),
        }
    }

    pub fn lookup(&self, client_key: &str) -> Result<Option<HttpReceipt>> {
        let found = self
            .db
            .lookup_receipt(NAMESPACE, &self.scoped_request(client_key))
            .map_err(|_| Error("E_SERVER_SQLITE_V2: receipt read failed".into()))?;
        found
            .map(|receipt| {
                if receipt.namespace != NAMESPACE
                    || receipt.key != self.key
                    || receipt.operation != "put"
                    || receipt.revision == 0
                {
                    return fail("E_SERVER_SQLITE_V2: receipt metadata mismatch");
                }
                let body = receipt.application_response.ok_or_else(|| {
                    Error("E_SERVER_SQLITE_V2: missing application receipt".into())
                })?;
                let parsed: HttpReceipt = serde_json::from_str(&body)
                    .map_err(|_| Error("E_SERVER_SQLITE_V2: corrupt application receipt".into()))?;
                if parsed.key != client_key
                    || u64::from(parsed.revision) != receipt.revision
                    || !matches!(parsed.status, 200..=202)
                    || parsed.fingerprint.len() != 64
                    || !parsed
                        .fingerprint
                        .bytes()
                        .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
                {
                    return fail("E_SERVER_SQLITE_V2: untrusted application receipt");
                }
                Ok(parsed)
            })
            .transpose()
    }

    pub fn commit(
        &mut self,
        values: &Values,
        reply: &HttpReceipt,
    ) -> std::result::Result<(), SaveFailure> {
        if !Self::valid_state(&self.defs, values)
            || self.db_revision >= u64::from(u32::MAX)
            || u64::from(reply.revision) != self.db_revision + 1
        {
            return Err(SaveFailure::RejectedBeforeCommit);
        }
        let record = StateSnapshot {
            schema: SCHEMA.to_owned(),
            signature: self.signature.clone(),
            revision: reply.revision,
            state: values.clone(),
        };
        let snapshot =
            serde_json::to_string(&record).map_err(|_| SaveFailure::RejectedBeforeCommit)?;
        let response =
            serde_json::to_string(reply).map_err(|_| SaveFailure::RejectedBeforeCommit)?;
        if snapshot.len() > MAX_VALUE_BYTES || response.len() > 16_384 {
            return Err(SaveFailure::RejectedBeforeCommit);
        }
        // The full HTTP reply is committed atomically with state and SQL audit.
        // Any uncertain SQL commit or conflicting external writer stops the
        // server; neither optimistic in-memory state nor response is published.
        let outcome = self.db.mutate_with_response(
            NAMESPACE,
            &self.key,
            Change::Put(&snapshot),
            self.db_revision,
            &self.scoped_request(&reply.key),
            &response,
        );
        match outcome {
            Ok(done)
                if !done.replayed
                    && done.revision == self.db_revision + 1
                    && done.application_response.as_deref() == Some(response.as_str()) =>
            {
                self.db_revision = done.revision;
                Ok(())
            }
            _ => Err(SaveFailure::DurabilityUncertain),
        }
    }
}
