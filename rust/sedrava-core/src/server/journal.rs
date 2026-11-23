//! A4 limited, immutable per-commit redo journal. No checkpoint, compaction,
//! multi-writer support, production power-loss guarantee or automatic recovery.
//!
//! Each committed revision is a separate, fsynced, atomically renamed file.
//! Replay validates a contiguous hash-chained history with exact source binding.
//! This is an opt-in alternative to A3 snapshots, NEVER an implicit upgrade.
use super::state::{scalar_type, StateDef, Values};
use super::storage::{signature, SaveFailure, Strict};
use super::transaction::{Ledger, Receipt, MAX_RECEIPTS, MAX_TRANSACTION_BYTES};
use crate::model::{fail, Error, Result};
use serde::{Deserialize, Serialize};
#[cfg(test)]
use serde_json::json;
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;
use std::fs;
#[cfg(not(unix))]
use std::path::Path;

const FORMAT: &str = "sedrava.server.redo-journal.v1";
const GENESIS: &str = "0000000000000000000000000000000000000000000000000000000000000000";
const LOCK: &str = ".sedrava-server.lock";
const LEGACY: &str = "sedrava-state-v1.json";
const GUARD_BYTES: &[u8] = b"{\"schema\":\"sedrava.server.redo-journal.guard.v1\"}\n";
const MARKER: &str = "sedrava-journal-v1.manifest.json";
const MARKER_FORMAT: &str = "sedrava.server.redo-journal.manifest.v1";

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Manifest {
    schema: String,
    signature: String,
    genesis: String,
    max_receipts: usize,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Record {
    schema: String,
    signature: String,
    revision: u32,
    previous_hash: String,
    state: Values,
    receipt: Receipt,
    record_hash: String,
}

impl Record {
    fn new(signature: &str, previous_hash: &str, state: &Values, receipt: &Receipt) -> Self {
        let hash = Self::hash(signature, previous_hash, state, receipt);
        Self {
            schema: FORMAT.into(),
            signature: signature.into(),
            revision: receipt.revision,
            previous_hash: previous_hash.into(),
            state: state.clone(),
            receipt: receipt.clone(),
            record_hash: hash,
        }
    }

    fn hash(signature: &str, previous_hash: &str, state: &Values, receipt: &Receipt) -> String {
        let bytes = serde_json::to_vec(&(FORMAT, signature, previous_hash, state, receipt))
            .expect("serializing checked JSON record cannot fail");
        format!("{:x}", Sha256::digest(&bytes))
    }

    fn valid(
        &self,
        signature: &str,
        previous: &str,
        sequence: u32,
        defs: &BTreeMap<String, StateDef>,
    ) -> bool {
        self.schema == FORMAT
            && self.signature == signature
            && self.revision == sequence
            && self.receipt.revision == sequence
            && self.previous_hash == previous
            && self.record_hash == Self::hash(signature, previous, &self.state, &self.receipt)
            && self.state.len() == defs.len()
            && defs
                .iter()
                .all(|(key, def)| self.state.get(key).and_then(scalar_type) == Some(def.kind))
    }
}

fn journal_signature(
    server: &str,
    defs: &BTreeMap<String, StateDef>,
    source_sha: &str,
) -> Result<String> {
    if source_sha.len() != 64 || !source_sha.bytes().all(|b| b.is_ascii_hexdigit()) {
        return fail("E_SERVER_JOURNAL: invalid source hash");
    }
    let base = signature(server, defs)?;
    let bytes = serde_json::to_vec(&(FORMAT, base, source_sha))
        .map_err(|_| Error("E_SERVER_JOURNAL: cannot sign source contract".into()))?;
    Ok(format!("{:x}", Sha256::digest(bytes)))
}

fn filename(revision: u32) -> String {
    format!("txn-{revision:08}.json")
}

#[cfg(unix)]
mod unix {
    use super::super::storage::{checked_file, metadata_regular, private_folder};
    use super::*;
    use serde::Deserialize;
    use std::fs::{File, OpenOptions};
    use std::io::{Read, Write};
    use std::os::unix::fs::{MetadataExt, OpenOptionsExt};
    use std::path::{Path, PathBuf};

    pub struct JournalStore {
        dir: PathBuf,
        lock_inode: (u64, u64),
        lock_handle: File,
        signature: String,
        defs: BTreeMap<String, StateDef>,
        previous_hash: String,
        receipts: Vec<Receipt>,
    }

    fn strict_load(path: &Path, uid: u32) -> Result<Record> {
        let meta = checked_file(path, uid)?
            .ok_or_else(|| Error("E_SERVER_JOURNAL: missing commit file".into()))?;
        if meta.len() > MAX_TRANSACTION_BYTES {
            return fail("E_SERVER_JOURNAL: oversized commit file");
        }
        let file = OpenOptions::new()
            .read(true)
            .custom_flags(rustix::fs::OFlags::NOFOLLOW.bits() as i32)
            .open(path)
            .map_err(|_| Error("E_SERVER_JOURNAL: cannot safely read commit".into()))?;
        let opened = file
            .metadata()
            .map_err(|_| Error("E_SERVER_JOURNAL: cannot stat open commit".into()))?;
        if !metadata_regular(&opened, uid)
            || opened.dev() != meta.dev()
            || opened.ino() != meta.ino()
        {
            return fail("E_SERVER_JOURNAL: commit changed during opening");
        }
        let mut bytes = Vec::new();
        file.take(MAX_TRANSACTION_BYTES + 1)
            .read_to_end(&mut bytes)
            .map_err(|_| Error("E_SERVER_JOURNAL: commit read failed".into()))?;
        if bytes.len() > MAX_TRANSACTION_BYTES as usize {
            return fail("E_SERVER_JOURNAL: commit grew past limit");
        }
        let mut d = serde_json::Deserializer::from_slice(&bytes);
        let Strict(value) = Strict::deserialize(&mut d)
            .map_err(|_| Error("E_SERVER_JOURNAL: malformed or duplicate-key commit".into()))?;
        d.end()
            .map_err(|_| Error("E_SERVER_JOURNAL: trailing JSON".into()))?;
        serde_json::from_value::<Record>(value)
            .map_err(|_| Error("E_SERVER_JOURNAL: invalid commit structure".into()))
    }

    fn ensure_manifest(dir: &Path, signature: &str) -> Result<()> {
        let uid = rustix::process::geteuid().as_raw();
        let path = dir.join(MARKER);
        let existing = checked_file(&path, uid)?;
        if existing.is_none() {
            // Do not recreate a missing manifest in a non-empty journal.
            for entry in fs::read_dir(dir)
                .map_err(|_| Error("E_SERVER_JOURNAL: cannot list initial directory".into()))?
            {
                let entry = entry.map_err(|_| {
                    Error("E_SERVER_JOURNAL: cannot inspect initial directory".into())
                })?;
                if entry.file_name() != std::ffi::OsStr::new(LOCK) {
                    return fail("E_SERVER_JOURNAL: manifest absent in nonempty store");
                }
            }
            // Reserve the legacy filename with deliberately incompatible JSON.
            // Pre-A4 executables do not know our manifest, but they DO attempt
            // to load this filename and fail on its foreign schema, before bind.
            // A crash between guard and manifest leaves a deliberately
            // unopenable directory requiring explicit operator inspection.
            let guard_path = dir.join(LEGACY);
            let mut guard = tempfile::NamedTempFile::new_in(dir)
                .map_err(|_| Error("E_SERVER_JOURNAL: guard temp create failed".into()))?;
            guard
                .write_all(GUARD_BYTES)
                .map_err(|_| Error("E_SERVER_JOURNAL: guard write failed".into()))?;
            guard
                .as_file()
                .sync_all()
                .map_err(|_| Error("E_SERVER_JOURNAL: guard fsync failed".into()))?;
            guard
                .persist(&guard_path)
                .map_err(|_| Error("E_SERVER_JOURNAL: legacy guard publish failed".into()))?;
            File::open(dir)
                .and_then(|f| f.sync_all())
                .map_err(|_| Error("E_SERVER_JOURNAL: guard directory sync failed".into()))?;
            let manifest = Manifest {
                schema: MARKER_FORMAT.into(),
                signature: signature.into(),
                genesis: GENESIS.into(),
                max_receipts: MAX_RECEIPTS,
            };
            let data = serde_json::to_vec(&manifest)
                .map_err(|_| Error("E_SERVER_JOURNAL: manifest serialization failed".into()))?;
            let mut temp = tempfile::NamedTempFile::new_in(dir)
                .map_err(|_| Error("E_SERVER_JOURNAL: cannot allocate manifest temp".into()))?;
            temp.write_all(&data)
                .map_err(|_| Error("E_SERVER_JOURNAL: manifest write failed".into()))?;
            temp.as_file()
                .sync_all()
                .map_err(|_| Error("E_SERVER_JOURNAL: manifest fsync failed".into()))?;
            temp.persist(&path)
                .map_err(|_| Error("E_SERVER_JOURNAL: manifest publish failed".into()))?;
            File::open(dir)
                .and_then(|file| file.sync_all())
                .map_err(|_| Error("E_SERVER_JOURNAL: manifest directory fsync failed".into()))?;
        }
        let meta = checked_file(&path, uid)?
            .ok_or_else(|| Error("E_SERVER_JOURNAL: expected manifest missing".into()))?;
        if meta.len() > 4096 {
            return fail("E_SERVER_JOURNAL: oversized manifest");
        }
        let file = OpenOptions::new()
            .read(true)
            .custom_flags(rustix::fs::OFlags::NOFOLLOW.bits() as i32)
            .open(&path)
            .map_err(|_| Error("E_SERVER_JOURNAL: manifest cannot be opened".into()))?;
        let opened = file
            .metadata()
            .map_err(|_| Error("E_SERVER_JOURNAL: manifest cannot be inspected".into()))?;
        if !metadata_regular(&opened, uid)
            || opened.dev() != meta.dev()
            || opened.ino() != meta.ino()
        {
            return fail("E_SERVER_JOURNAL: manifest changed during read");
        }
        let mut data = Vec::new();
        file.take(4097)
            .read_to_end(&mut data)
            .map_err(|_| Error("E_SERVER_JOURNAL: cannot read manifest".into()))?;
        if data.len() > 4096 {
            return fail("E_SERVER_JOURNAL: manifest grew");
        }
        let mut decoder = serde_json::Deserializer::from_slice(&data);
        let Strict(value) = Strict::deserialize(&mut decoder)
            .map_err(|_| Error("E_SERVER_JOURNAL: invalid or duplicate-key manifest".into()))?;
        decoder
            .end()
            .map_err(|_| Error("E_SERVER_JOURNAL: manifest has trailing bytes".into()))?;
        let manifest: Manifest = serde_json::from_value(value)
            .map_err(|_| Error("E_SERVER_JOURNAL: malformed manifest".into()))?;
        if manifest.schema != MARKER_FORMAT
            || manifest.signature != signature
            || manifest.genesis != GENESIS
            || manifest.max_receipts != MAX_RECEIPTS
        {
            return fail("E_SERVER_JOURNAL: incompatible manifest or source");
        }
        let guard_path = dir.join(LEGACY);
        let guard_meta = checked_file(&guard_path, uid)?
            .ok_or_else(|| Error("E_SERVER_JOURNAL: missing legacy-format safety guard".into()))?;
        if guard_meta.len() != GUARD_BYTES.len() as u64 {
            return fail("E_SERVER_JOURNAL: invalid legacy-format safety guard");
        }
        let guard = OpenOptions::new()
            .read(true)
            .custom_flags(rustix::fs::OFlags::NOFOLLOW.bits() as i32)
            .open(&guard_path)
            .map_err(|_| Error("E_SERVER_JOURNAL: cannot open legacy safety guard".into()))?;
        let opened = guard
            .metadata()
            .map_err(|_| Error("E_SERVER_JOURNAL: cannot stat legacy safety guard".into()))?;
        if !metadata_regular(&opened, uid)
            || opened.dev() != guard_meta.dev()
            || opened.ino() != guard_meta.ino()
        {
            return fail("E_SERVER_JOURNAL: legacy guard changed during open");
        }
        let mut bytes = Vec::new();
        guard
            .take(GUARD_BYTES.len() as u64 + 1)
            .read_to_end(&mut bytes)
            .map_err(|_| Error("E_SERVER_JOURNAL: cannot read legacy safety guard".into()))?;
        if bytes != GUARD_BYTES {
            return fail("E_SERVER_JOURNAL: legacy safety guard mismatch");
        }
        Ok(())
    }

    fn read_history(
        dir: &Path,
        signature: &str,
        defs: &BTreeMap<String, StateDef>,
    ) -> Result<(Values, Ledger, String)> {
        let uid = rustix::process::geteuid().as_raw();
        let mut names = std::collections::BTreeSet::new();
        for entry in fs::read_dir(dir)
            .map_err(|_| Error("E_SERVER_JOURNAL: cannot inspect commit folder".into()))?
        {
            let entry = entry
                .map_err(|_| Error("E_SERVER_JOURNAL: cannot enumerate commit folder".into()))?;
            let name = entry
                .file_name()
                .into_string()
                .map_err(|_| Error("E_SERVER_JOURNAL: non-UTF8 directory member".into()))?;
            if name == LOCK || name == MARKER || name == LEGACY {
                continue;
            }
            let bytes = name.as_bytes();
            if !name.starts_with("txn-")
                || !name.ends_with(".json")
                || bytes.len() != 17
                || !bytes[4..12].iter().all(|b| b.is_ascii_digit())
            {
                // Includes uncommitted temp files after a crash. Operator must
                // inspect/clear them explicitly. No silent data deletion.
                return fail("E_SERVER_JOURNAL: unexpected directory member");
            }
            let revision = std::str::from_utf8(&bytes[4..12])
                .expect("ASCII-only revision")
                .parse::<u32>()
                .map_err(|_| Error("E_SERVER_JOURNAL: invalid filename revision".into()))?;
            if revision == 0 || revision > MAX_RECEIPTS as u32 || !names.insert(revision) {
                return fail("E_SERVER_JOURNAL: invalid or duplicate record filename");
            }
        }
        let mut values: Values = defs
            .iter()
            .map(|(key, def)| (key.clone(), def.initial.clone()))
            .collect();
        let mut ledger = Ledger::default();
        let mut previous = GENESIS.to_string();
        for revision in 1..=names.len() as u32 {
            if !names.contains(&revision) {
                return fail("E_SERVER_JOURNAL: missing middle revision");
            }
            let record = strict_load(&dir.join(filename(revision)), uid)?;
            if !record.valid(signature, &previous, revision, defs) {
                return fail("E_SERVER_JOURNAL: signature, hash chain, revision or type mismatch");
            }
            let next = ledger
                .append(record.receipt)
                .ok_or_else(|| Error("E_SERVER_JOURNAL: invalid or duplicated receipt".into()))?;
            if !next.valid() {
                return fail("E_SERVER_JOURNAL: receipt contract invalid");
            }
            ledger = next;
            values = record.state;
            previous = record.record_hash;
        }
        Ok((values, ledger, previous))
    }

    /// Debug builds only, for a test-owned child. Abrupt exit deliberately
    /// bypasses destructors, simulating an ungraceful process termination.
    /// RELEASE BINARIES DO NOT READ OR ACT ON SEDRAVA_A4_FAULT.
    #[cfg(debug_assertions)]
    pub(super) fn test_fault(point: &str) {
        if std::env::var("SEDRAVA_A4_FAULT").ok().as_deref() == Some(point) {
            eprintln!("SEDRAVA_A4_FAULT_INJECTED:{point}");
            std::process::exit(87);
        }
    }
    #[cfg(not(debug_assertions))]
    pub(super) fn test_fault(_: &str) {}

    impl JournalStore {
        pub fn open(
            path: &Path,
            server: &str,
            defs: &BTreeMap<String, StateDef>,
            source_sha: &str,
        ) -> Result<(Self, Values, Ledger)> {
            if defs.is_empty() {
                return fail("E_SERVER_JOURNAL: state declaration required");
            }
            let dir = private_folder(path)?;
            // Guard verification in ensure_manifest rejects real A2/A3
            // snapshots while also blocking PRE-A4 binaries from this dir.
            let lock_path = dir.join(LOCK);
            let mut lock = OpenOptions::new()
                .write(true)
                .create_new(true)
                .mode(0o600)
                .open(&lock_path)
                .map_err(|_| Error("E_SERVER_JOURNAL: exclusive lock exists".into()))?;
            let meta = lock
                .metadata()
                .map_err(|_| Error("E_SERVER_JOURNAL: cannot stat lock".into()))?;
            let lock_inode = (meta.dev(), meta.ino());
            let result = (|| {
                writeln!(lock, "pid={} source={}", std::process::id(), server)
                    .map_err(|_| Error("E_SERVER_JOURNAL: cannot write lock".into()))?;
                lock.sync_all()
                    .map_err(|_| Error("E_SERVER_JOURNAL: lock fsync failed".into()))?;
                let bound = journal_signature(server, defs, source_sha)?;
                ensure_manifest(&dir, &bound)?;
                let (values, ledger, previous) = read_history(&dir, &bound, defs)?;
                Ok((bound, values, ledger, previous))
            })();
            match result {
                Ok((bound, values, ledger, previous)) => Ok((
                    Self {
                        dir,
                        lock_inode,
                        lock_handle: lock,
                        signature: bound,
                        defs: defs.clone(),
                        previous_hash: previous,
                        receipts: ledger.receipts.clone(),
                    },
                    values,
                    ledger,
                )),
                Err(e) => {
                    if fs::symlink_metadata(&lock_path)
                        .ok()
                        .is_some_and(|m| (m.dev(), m.ino()) == lock_inode)
                    {
                        let _ = fs::remove_file(&lock_path);
                    }
                    Err(e)
                }
            }
        }

        pub fn save_transaction(
            &mut self,
            values: &Values,
            ledger: &Ledger,
        ) -> std::result::Result<(), SaveFailure> {
            let stage = (|| -> Result<String> {
                if !ledger.valid()
                    || ledger.receipts.len() != self.receipts.len() + 1
                    || ledger.receipts[..self.receipts.len()] != self.receipts[..]
                    || values.len() != self.defs.len()
                    || !self
                        .defs
                        .iter()
                        .all(|(key, def)| values.get(key).and_then(scalar_type) == Some(def.kind))
                {
                    return fail("E_SERVER_JOURNAL: invalid incremental transaction");
                }
                let receipt = ledger
                    .receipts
                    .last()
                    .ok_or_else(|| Error("E_SERVER_JOURNAL: missing receipt".into()))?;
                let record = Record::new(&self.signature, &self.previous_hash, values, receipt);
                let output = serde_json::to_vec(&record)
                    .map_err(|_| Error("E_SERVER_JOURNAL: cannot serialize commit".into()))?;
                if output.len() > MAX_TRANSACTION_BYTES as usize {
                    return fail("E_SERVER_JOURNAL: transaction record too large");
                }
                let dest = self.dir.join(filename(receipt.revision));
                if checked_file(&dest, rustix::process::geteuid().as_raw())?.is_some() {
                    return fail("E_SERVER_JOURNAL: target revision already exists");
                }
                let mut temp = tempfile::NamedTempFile::new_in(&self.dir)
                    .map_err(|_| Error("E_SERVER_JOURNAL: temp file create failed".into()))?;
                temp.write_all(&output)
                    .map_err(|_| Error("E_SERVER_JOURNAL: write failed".into()))?;
                test_fault("after_write");
                temp.as_file()
                    .sync_all()
                    .map_err(|_| Error("E_SERVER_JOURNAL: temp fsync failed".into()))?;
                test_fault("after_file_fsync");
                // This mode never overwrites earlier committed records.
                temp.persist(&dest)
                    .map_err(|_| Error("E_SERVER_JOURNAL: publish failed".into()))?;
                test_fault("after_rename");
                Ok(record.record_hash)
            })();
            let hash = stage.map_err(|_| SaveFailure::RejectedBeforeCommit)?;
            File::open(&self.dir)
                .and_then(|d| d.sync_all())
                .map_err(|_| SaveFailure::DurabilityUncertain)?;
            test_fault("after_dir_fsync");
            self.previous_hash = hash;
            self.receipts = ledger.receipts.clone();
            Ok(())
        }
    }

    impl Drop for JournalStore {
        fn drop(&mut self) {
            let lock_path = self.dir.join(LOCK);
            if self.lock_handle.metadata().is_ok_and(|descriptor| {
                fs::symlink_metadata(&lock_path).is_ok_and(|current| {
                    (descriptor.dev(), descriptor.ino()) == self.lock_inode
                        && (current.dev(), current.ino()) == self.lock_inode
                })
            }) {
                let _ = fs::remove_file(lock_path);
            }
        }
    }
}

#[cfg(unix)]
pub use unix::JournalStore;

#[cfg(not(unix))]
pub struct JournalStore;
#[cfg(not(unix))]
impl JournalStore {
    pub fn open(
        _: &Path,
        _: &str,
        _: &BTreeMap<String, StateDef>,
        _: &str,
    ) -> Result<(Self, Values, Ledger)> {
        fail("E_SERVER_JOURNAL: Unix only")
    }
    pub fn save_transaction(
        &mut self,
        _: &Values,
        _: &Ledger,
    ) -> std::result::Result<(), SaveFailure> {
        Err(SaveFailure::RejectedBeforeCommit)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::Map;
    #[test]
    fn record_hash_chain_binds_state_receipt_and_previous() {
        let receipt = Receipt {
            key: "test-request-001".into(),
            fingerprint: "a".repeat(64),
            revision: 1,
            status: 201,
            response: Map::from_iter([("ok".into(), json!(true))]),
        };
        let state = Values::from([("n".into(), json!(1))]);
        let r = Record::new("signature", &"0".repeat(64), &state, &receipt);
        let defs = BTreeMap::from([(
            "n".into(),
            StateDef {
                kind: super::super::ScalarType::Int,
                initial: json!(0),
            },
        )]);
        assert!(r.valid("signature", &"0".repeat(64), 1, &defs));
        assert!(!r.valid("signature", &"1".repeat(64), 1, &defs));
        assert!(!r.valid("signature", &"0".repeat(64), 2, &defs));
        let mut changed = r.clone();
        changed.state.insert("n".into(), json!(2));
        assert!(!changed.valid("signature", &"0".repeat(64), 1, &defs));
    }
}
