//! Native Sedrava A5: a pinned SedravaSQL SQLite adapter.
//!
//! The entire A3 server state and receipt ledger are one versioned
//! SedravaSQL key/value row, updated with CAS inside a SQLite WAL transaction
//! together with SedravaSQL audit and idempotency receipts. There is NO
//! support for multiple simultaneously running Sedrava server processes
//! on one state key; a stale commit returns an error and stops the process.
//! Experimental: no production reliability claim.
use super::state::{scalar_type, StateDef, Values};
use super::storage::{decoded_transaction, signature, SaveFailure};
use super::transaction::{Ledger, MAX_TRANSACTION_BYTES, SCHEMA};
use crate::model::{fail, Error, Result};
use sedravasql::{Change, Database};
use serde_json::json;
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;
use std::path::Path;

const NAMESPACE: &str = "sedrava_native";
const PREFIX: &str = "s_";

pub struct SqliteStore {
    db: Database,
    key: String,
    signature: String,
    defs: BTreeMap<String, StateDef>,
    db_revision: u64,
    receipt_count: usize,
}

impl SqliteStore {
    pub fn open(
        path: &Path,
        server_name: &str,
        defs: &BTreeMap<String, StateDef>,
        source_sha: &str,
    ) -> Result<(Self, Values, Ledger)> {
        if defs.is_empty() {
            return fail("E_SERVER_SQLITE: state declarations required");
        }
        let initial_sig = signature(server_name, defs)?;
        let input =
            serde_json::to_vec(&("sedrava.sqlite.state.v1", source_sha, initial_sig.as_str()))
                .map_err(|_| Error("E_SERVER_SQLITE: signature encoding failed".into()))?;
        let scoped_sig = format!("{:x}", Sha256::digest(input));
        // Full 64-char digest is a SedravaSQL-approved identifier.
        let key = format!("{PREFIX}{scoped_sig}");
        // Initializes a new schema-v1 SQLite file, but refuses unrelated /
        // unknown schemas. Caller is responsible for private filesystem dir.
        let db = Database::init(path)
            .map_err(|e| Error(format!("E_SERVER_SQLITE: cannot open database: {e}")))?;
        db.verify().map_err(|e| {
            Error(format!(
                "E_SERVER_SQLITE: integrity/schema check failed: {e}"
            ))
        })?;
        let saved = db
            .read(NAMESPACE, &key)
            .map_err(|e| Error(format!("E_SERVER_SQLITE: read failed: {e}")))?;
        let (values, ledger, db_revision) = if let Some(entry) = saved {
            let raw = entry
                .value
                .ok_or_else(|| Error("E_SERVER_SQLITE: unexpected deleted state row".into()))?;
            if raw.len() > MAX_TRANSACTION_BYTES as usize {
                return fail("E_SERVER_SQLITE: snapshot too large");
            }
            let (values, ledger) = decoded_transaction(raw.as_bytes(), &scoped_sig, defs)?;
            (values, ledger, entry.revision)
        } else {
            (
                defs.iter()
                    .map(|(key, def)| (key.clone(), def.initial.clone()))
                    .collect(),
                Ledger::default(),
                0,
            )
        };
        let receipt_count = ledger.receipts.len();
        Ok((
            Self {
                db,
                key,
                signature: scoped_sig,
                defs: defs.clone(),
                db_revision,
                receipt_count,
            },
            values,
            ledger,
        ))
    }

    pub fn save_transaction(
        &mut self,
        values: &Values,
        ledger: &Ledger,
    ) -> std::result::Result<(), SaveFailure> {
        if ledger.receipts.len() != self.receipt_count + 1
            || !ledger.valid()
            || values.len() != self.defs.len()
            || !self
                .defs
                .iter()
                .all(|(key, def)| values.get(key).and_then(scalar_type) == Some(def.kind))
        {
            return Err(SaveFailure::RejectedBeforeCommit);
        }
        let receipt = ledger.receipts.last().expect("nonempty checked");
        let output = serde_json::to_string(&json!({
            "schema":SCHEMA,
            "signature":self.signature,
            "revision":ledger.revision(),
            "state":values,
            "receipts":ledger.receipts,
        }))
        .map_err(|_| SaveFailure::RejectedBeforeCommit)?;
        if output.len() > MAX_TRANSACTION_BYTES as usize {
            return Err(SaveFailure::RejectedBeforeCommit);
        }
        // The SQL request key is scoped by NAMESPACE, so no collision with
        // user application keys. A3 replay is answered in memory before here.
        // Idempotency keys also bind to this source, not just SQL namespace.
        let request_key = format!("s{}-{}", &self.signature[..32], receipt.key);
        match self.db.mutate(
            NAMESPACE,
            &self.key,
            Change::Put(&output),
            self.db_revision,
            &request_key,
        ) {
            Ok(result) if !result.replayed && result.revision == self.db_revision + 1 => {
                self.db_revision = result.revision;
                self.receipt_count = ledger.receipts.len();
                Ok(())
            }
            // On ANY SQLite error the outcome of COMMIT may be uncertain.
            // Poison and halt rather than accidentally double-apply.
            _ => Err(SaveFailure::DurabilityUncertain),
        }
    }
}
