//! A6 experimental SQLite-backed state and permanently retained HTTP receipts.
//! Uses the separate, pinned SedravaSQL transaction API. No silent eviction;
//! operator-controlled archive/migration is not implemented.
use super::state::{scalar_type, StateDef, Values};
use super::storage::{signature, SaveFailure};
use super::transaction::Receipt as HttpReceipt;
use crate::model::{fail, Error, Result};
use sedravasql::{Change, Database, MAX_VALUE_BYTES};
use serde::{Deserialize, Serialize};
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
    ) -> Result<(Self, Values, u32)> {
        if defs.is_empty() {
            return fail("E_SERVER_SQLITE_V2: state declarations required");
        }
        let types_sig = signature(name, defs)?;
        let raw = serde_json::to_vec(&(SCHEMA, source_sha, types_sig))
            .map_err(|_| Error("E_SERVER_SQLITE_V2: signature encode failed".into()))?;
        let signature = format!("{:x}", Sha256::digest(raw));
        let key = format!("s_{signature}");
        let db = Database::init(path)
            .map_err(|_| Error("E_SERVER_SQLITE_V2: database open failed".into()))?;
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
    pub fn read_text(&self, namespace: &str, key: &str) -> Result<Option<String>> {
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
                Ok(Some(text))
            }
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
                    || !matches!(parsed.status, 200 | 201 | 202)
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
