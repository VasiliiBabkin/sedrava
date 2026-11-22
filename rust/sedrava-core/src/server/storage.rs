//! A2 opt-in trusted private-directory scalar JSON persistence.
//! No user-supplied filenames inside DSL; no server-side arbitrary IO.
//! Crash-stale lock requires explicit operator recovery (not production).
use super::state::{scalar_type, StateDef, Values};
use super::transaction::{Ledger, Receipt, MAX_TRANSACTION_BYTES, SCHEMA as TX_SCHEMA};
use crate::model::{fail, Error, Result};
use serde::de::{self, MapAccess, SeqAccess, Visitor};
use serde::{Deserialize, Deserializer};
use serde_json::{json, Map, Value};
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;
use std::fmt;
use std::fs;
use std::path::{Path, PathBuf};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SaveFailure {
    RejectedBeforeCommit,
    DurabilityUncertain,
}

const MAX_STATE_BYTES: u64 = 16_384;
const FILE: &str = "sedrava-state-v1.json";
const LOCK: &str = ".sedrava-server.lock";

fn signature(server_name: &str, defs: &BTreeMap<String, StateDef>) -> Result<String> {
    let kinds: Vec<_> = defs
        .iter()
        .map(|(key, def)| {
            (
                key,
                match def.kind {
                    super::ScalarType::Int => "int",
                    super::ScalarType::Text => "text",
                    super::ScalarType::Bool => "bool",
                },
                &def.initial,
            )
        })
        .collect();
    let canonical = serde_json::to_vec(&(server_name, kinds))
        .map_err(|_| Error("E_SERVER_STATE: cannot encode schema".into()))?;
    Ok(format!("{:x}", Sha256::digest(canonical)))
}

/// Reject duplicate keys at *every* object nesting depth; reject all floating
/// numbers, overlarge int32 values and excessive nested arrays/objects.
struct Strict(Value);
impl<'de> Deserialize<'de> for Strict {
    fn deserialize<D: Deserializer<'de>>(d: D) -> std::result::Result<Self, D::Error> {
        struct Read;
        impl<'de> Visitor<'de> for Read {
            type Value = Strict;
            fn expecting(&self, f: &mut fmt::Formatter) -> fmt::Result {
                f.write_str("strict JSON with unique keys and scalar int32")
            }
            fn visit_bool<E: de::Error>(self, v: bool) -> std::result::Result<Self::Value, E> {
                Ok(Strict(Value::Bool(v)))
            }
            fn visit_i64<E: de::Error>(self, v: i64) -> std::result::Result<Self::Value, E> {
                let v = i32::try_from(v).map_err(|_| E::custom("int32 required"))?;
                Ok(Strict(json!(v)))
            }
            fn visit_u64<E: de::Error>(self, v: u64) -> std::result::Result<Self::Value, E> {
                let v = i32::try_from(v).map_err(|_| E::custom("int32 required"))?;
                Ok(Strict(json!(v)))
            }
            fn visit_f64<E: de::Error>(self, _: f64) -> std::result::Result<Self::Value, E> {
                Err(E::custom("floats prohibited"))
            }
            fn visit_str<E: de::Error>(self, v: &str) -> std::result::Result<Self::Value, E> {
                Ok(Strict(Value::String(v.into())))
            }
            fn visit_string<E: de::Error>(self, v: String) -> std::result::Result<Self::Value, E> {
                Ok(Strict(Value::String(v)))
            }
            fn visit_seq<A: SeqAccess<'de>>(
                self,
                mut a: A,
            ) -> std::result::Result<Self::Value, A::Error> {
                let mut values = Vec::new();
                while let Some(Strict(value)) = a.next_element::<Strict>()? {
                    if values.len() > 32 {
                        return Err(de::Error::custom("array bound exceeded"));
                    }
                    values.push(value);
                }
                Ok(Strict(Value::Array(values)))
            }
            fn visit_map<A: MapAccess<'de>>(
                self,
                mut a: A,
            ) -> std::result::Result<Self::Value, A::Error> {
                let mut m = Map::new();
                while let Some((key, Strict(value))) = a.next_entry::<String, Strict>()? {
                    if m.insert(key, value).is_some() {
                        return Err(de::Error::custom("duplicate key"));
                    }
                }
                Ok(Strict(Value::Object(m)))
            }
        }
        d.deserialize_any(Read)
    }
}

fn decoded(raw: &[u8], expected: &str, defs: &BTreeMap<String, StateDef>) -> Result<Values> {
    if raw.len() > MAX_STATE_BYTES as usize {
        return fail("E_SERVER_STATE: state file too large");
    }
    let mut d = serde_json::Deserializer::from_slice(raw);
    let Strict(value) = Strict::deserialize(&mut d)
        .map_err(|_| Error("E_SERVER_STATE: invalid or duplicate-key JSON".into()))?;
    d.end()
        .map_err(|_| Error("E_SERVER_STATE: trailing JSON bytes".into()))?;
    let obj = value
        .as_object()
        .ok_or_else(|| Error("E_SERVER_STATE: invalid root".into()))?;
    if obj.len() != 3
        || obj.get("schema") != Some(&Value::String("sedrava.server.state.v1".into()))
        || obj.get("signature") != Some(&Value::String(expected.into()))
    {
        return fail("E_SERVER_STATE: incompatible schema or source signature");
    }
    let Some(map) = obj.get("state").and_then(Value::as_object) else {
        return fail("E_SERVER_STATE: state object missing");
    };
    if map.len() != defs.len() {
        return fail("E_SERVER_STATE: state keys mismatch");
    }
    let mut values = Values::new();
    for (key, def) in defs {
        let value = map
            .get(key)
            .ok_or_else(|| Error("E_SERVER_STATE: state key missing".into()))?;
        if scalar_type(value) != Some(def.kind) {
            return fail("E_SERVER_STATE: invalid state field type");
        }
        values.insert(key.clone(), value.clone());
    }
    Ok(values)
}

fn decoded_transaction(
    raw: &[u8],
    expected: &str,
    defs: &BTreeMap<String, StateDef>,
) -> Result<(Values, Ledger)> {
    if raw.len() > MAX_TRANSACTION_BYTES as usize {
        return fail("E_SERVER_TRANSACTION: snapshot exceeds transaction limit");
    }
    let mut decoder = serde_json::Deserializer::from_slice(raw);
    let Strict(value) = Strict::deserialize(&mut decoder)
        .map_err(|_| Error("E_SERVER_TRANSACTION: invalid strict JSON".into()))?;
    decoder
        .end()
        .map_err(|_| Error("E_SERVER_TRANSACTION: trailing bytes".into()))?;
    let obj = value
        .as_object()
        .ok_or_else(|| Error("E_SERVER_TRANSACTION: invalid root".into()))?;
    if obj.len() != 5
        || obj.get("schema") != Some(&Value::String(TX_SCHEMA.into()))
        || obj.get("signature") != Some(&Value::String(expected.into()))
    {
        return fail("E_SERVER_TRANSACTION: incompatible snapshot schema/signature");
    }
    let revision = obj
        .get("revision")
        .and_then(Value::as_i64)
        .and_then(|n| u32::try_from(n).ok())
        .ok_or_else(|| Error("E_SERVER_TRANSACTION: invalid revision".into()))?;
    let items = obj
        .get("receipts")
        .and_then(Value::as_array)
        .ok_or_else(|| Error("E_SERVER_TRANSACTION: missing receipt ledger".into()))?;
    let receipts: Vec<Receipt> = serde_json::from_value(Value::Array(items.clone()))
        .map_err(|_| Error("E_SERVER_TRANSACTION: invalid receipt shape".into()))?;
    let ledger = Ledger { receipts };
    if !ledger.valid() || ledger.revision() != revision {
        return fail("E_SERVER_TRANSACTION: corrupt, inconsistent or exhausted receipts");
    }
    let states = obj
        .get("state")
        .and_then(Value::as_object)
        .ok_or_else(|| Error("E_SERVER_TRANSACTION: missing state object".into()))?;
    if states.len() != defs.len() {
        return fail("E_SERVER_TRANSACTION: state keys mismatch");
    }
    let mut values = Values::new();
    for (name, def) in defs {
        let Some(value) = states.get(name) else {
            return fail("E_SERVER_TRANSACTION: missing state field");
        };
        if scalar_type(value) != Some(def.kind) {
            return fail("E_SERVER_TRANSACTION: invalid state field type");
        }
        values.insert(name.clone(), value.clone());
    }
    Ok((values, ledger))
}

#[cfg(unix)]
mod unix {
    use super::*;
    use std::fs::{File, OpenOptions};
    use std::io::{Read, Write};
    use std::os::unix::fs::{MetadataExt, OpenOptionsExt, PermissionsExt};
    use std::path::Component;

    pub struct Store {
        dir: PathBuf,
        lock_inode: (u64, u64),
        lock_handle: File,
        signature: String,
        defs: BTreeMap<String, StateDef>,
        transactional: bool,
    }

    fn metadata_regular(metadata: &fs::Metadata, uid: u32) -> bool {
        metadata.is_file()
            && metadata.uid() == uid
            && metadata.nlink() == 1
            && metadata.permissions().mode() & 0o077 == 0
    }

    fn private_folder(dir: &Path) -> Result<PathBuf> {
        if !dir.is_absolute()
            || dir
                .components()
                .any(|c| !matches!(c, Component::RootDir | Component::Normal(_)))
        {
            return fail("E_SERVER_STORAGE: state directory must be a clean absolute path");
        }
        // No symlink in any ancestor, including final directory: canonical
        // equality also rejects dot-path aliases. The final dir must be 0700
        // and owned by the current user (private trusted storage contract).
        let absolute = fs::canonicalize(dir)
            .map_err(|_| Error("E_SERVER_STORAGE: state directory must exist".into()))?;
        if dir != absolute {
            return fail("E_SERVER_STORAGE: directory path must be canonical without symlinks");
        }
        let meta = fs::symlink_metadata(&absolute)
            .map_err(|_| Error("E_SERVER_STORAGE: cannot inspect directory".into()))?;
        if !meta.is_dir()
            || meta.uid() != rustix::process::geteuid().as_raw()
            || meta.permissions().mode() & 0o077 != 0
        {
            return fail(
                "E_SERVER_STORAGE: directory must be private, mode 0700, owned by operator",
            );
        }
        Ok(absolute)
    }

    fn checked_file(path: &Path, uid: u32) -> Result<Option<fs::Metadata>> {
        match fs::symlink_metadata(path) {
            Ok(meta) if metadata_regular(&meta, uid) => Ok(Some(meta)),
            Ok(_) => {
                fail("E_SERVER_STORAGE: state file is a symlink, hardlink, public or not regular")
            }
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => Ok(None),
            Err(_) => fail("E_SERVER_STORAGE: unable to inspect state file"),
        }
    }

    impl Store {
        pub fn open(
            path: &Path,
            server_name: &str,
            defs: &BTreeMap<String, StateDef>,
            transactional: bool,
        ) -> Result<(Self, Values, Ledger)> {
            if defs.is_empty() {
                return fail("E_SERVER_STORAGE: persistence requires declared server states");
            }
            let dir = private_folder(path)?;
            let uid = rustix::process::geteuid().as_raw();
            // Fail closed when stale lock remains after crash. Never unlink
            // a lock that an operator has not explicitly inspected.
            let lock_path = dir.join(LOCK);
            let mut lock_handle = OpenOptions::new()
                .write(true)
                .create_new(true)
                .mode(0o600)
                .open(&lock_path)
                .map_err(|_| {
                    Error("E_SERVER_STORAGE: server lock exists or is inaccessible".into())
                })?;
            let meta = lock_handle
                .metadata()
                .map_err(|_| Error("E_SERVER_STORAGE: cannot check lock descriptor".into()))?;
            let lock_inode = (meta.dev(), meta.ino());
            let result = (|| {
                writeln!(
                    &mut lock_handle,
                    "pid={} source={}",
                    std::process::id(),
                    server_name
                )
                .map_err(|_| Error("E_SERVER_STORAGE: cannot write lock".into()))?;
                lock_handle
                    .sync_all()
                    .map_err(|_| Error("E_SERVER_STORAGE: cannot sync lock".into()))?;
                let fingerprint = signature(server_name, defs)?;
                let state_path = dir.join(FILE);
                let (values, ledger) = match checked_file(&state_path, uid)? {
                    None => (
                        defs.iter()
                            .map(|(name, def)| (name.clone(), def.initial.clone()))
                            .collect(),
                        Ledger::default(),
                    ),
                    Some(meta) => {
                        if meta.len()
                            > if transactional {
                                MAX_TRANSACTION_BYTES
                            } else {
                                MAX_STATE_BYTES
                            }
                        {
                            return fail("E_SERVER_STORAGE: state file oversized");
                        }
                        let file = OpenOptions::new()
                            .read(true)
                            .custom_flags(rustix::fs::OFlags::NOFOLLOW.bits() as i32)
                            .open(&state_path)
                            .map_err(|_| {
                                Error("E_SERVER_STORAGE: cannot open state safely".into())
                            })?;
                        let opened = file.metadata().map_err(|_| {
                            Error("E_SERVER_STORAGE: cannot stat state descriptor".into())
                        })?;
                        if !metadata_regular(&opened, uid)
                            || opened.ino() != meta.ino()
                            || opened.dev() != meta.dev()
                        {
                            return fail("E_SERVER_STORAGE: state file changed during read");
                        }
                        let mut raw = Vec::new();
                        file.take(MAX_TRANSACTION_BYTES + 1)
                            .read_to_end(&mut raw)
                            .map_err(|_| Error("E_SERVER_STORAGE: cannot read state".into()))?;
                        if transactional {
                            decoded_transaction(&raw, &fingerprint, defs)?
                        } else {
                            (decoded(&raw, &fingerprint, defs)?, Ledger::default())
                        }
                    }
                };
                Ok((fingerprint, values, ledger))
            })();
            match result {
                Ok((fingerprint, values, ledger)) => Ok((
                    Self {
                        dir,
                        lock_inode,
                        lock_handle,
                        signature: fingerprint,
                        defs: defs.clone(),
                        transactional,
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
            let stage = (|| -> Result<()> {
                if !self.transactional
                    || values.len() != self.defs.len()
                    || !ledger.valid()
                    || ledger.receipts.is_empty()
                {
                    return fail("E_SERVER_TRANSACTION: invalid transaction mode/shape");
                }
                for (name, def) in &self.defs {
                    if values.get(name).and_then(scalar_type) != Some(def.kind) {
                        return fail("E_SERVER_TRANSACTION: state field type mismatch");
                    }
                }
                let output = serde_json::to_vec(&json!({
                    "schema":TX_SCHEMA, "signature":self.signature,
                    "state":values,"revision":ledger.revision(),
                    "receipts":ledger.receipts,
                }))
                .map_err(|_| Error("E_SERVER_TRANSACTION: encoding failed".into()))?;
                if output.len() > MAX_TRANSACTION_BYTES as usize {
                    return fail("E_SERVER_TRANSACTION: snapshot exceeds capacity");
                }
                let uid = rustix::process::geteuid().as_raw();
                let path = self.dir.join(FILE);
                checked_file(&path, uid)?;
                let mut temp = tempfile::NamedTempFile::new_in(&self.dir).map_err(|_| {
                    Error("E_SERVER_TRANSACTION: cannot allocate private temp".into())
                })?;
                temp.write_all(&output)
                    .map_err(|_| Error("E_SERVER_TRANSACTION: write failure".into()))?;
                temp.as_file()
                    .sync_all()
                    .map_err(|_| Error("E_SERVER_TRANSACTION: temp fsync failure".into()))?;
                temp.persist(&path)
                    .map_err(|_| Error("E_SERVER_TRANSACTION: atomic rename failure".into()))?;
                Ok(())
            })();
            stage.map_err(|_| SaveFailure::RejectedBeforeCommit)?;
            File::open(&self.dir)
                .and_then(|d| d.sync_all())
                .map_err(|_| SaveFailure::DurabilityUncertain)?;
            Ok(())
        }

        pub fn save(&mut self, values: &Values) -> std::result::Result<(), SaveFailure> {
            if self.transactional {
                return Err(SaveFailure::RejectedBeforeCommit);
            }
            let stage = (|| -> Result<()> {
                if values.len() != self.defs.len() {
                    return fail("E_SERVER_STORAGE: unexpected state shape");
                }
                for (name, def) in &self.defs {
                    if values.get(name).and_then(scalar_type) != Some(def.kind) {
                        return fail("E_SERVER_STORAGE: state field type mismatch");
                    }
                }
                let output = serde_json::to_vec(&json!({
                    "schema":"sedrava.server.state.v1",
                    "signature":self.signature,
                    "state":values,
                }))
                .map_err(|_| Error("E_SERVER_STORAGE: state serialization failed".into()))?;
                if output.len() > MAX_STATE_BYTES as usize {
                    return fail("E_SERVER_STORAGE: serialized state too large");
                }
                let uid = rustix::process::geteuid().as_raw();
                let path = self.dir.join(FILE);
                checked_file(&path, uid)?;
                let mut temp = tempfile::NamedTempFile::new_in(&self.dir).map_err(|_| {
                    Error("E_SERVER_STORAGE: cannot prepare temporary state file".into())
                })?;
                temp.write_all(&output)
                    .map_err(|_| Error("E_SERVER_STORAGE: state write failed".into()))?;
                temp.as_file()
                    .sync_all()
                    .map_err(|_| Error("E_SERVER_STORAGE: state file sync failed".into()))?;
                // Atomic replacement in trusted private directory. Full crash /
                // post-rename fsync failure recovery is not claimed in A2.
                temp.persist(&path)
                    .map_err(|_| Error("E_SERVER_STORAGE: atomic state publish failed".into()))?;
                Ok(())
            })();
            stage.map_err(|_| SaveFailure::RejectedBeforeCommit)?;
            // If directory fsync fails after rename, disk state *may* have
            // committed. The caller must poison and stop this process.
            File::open(&self.dir)
                .and_then(|d| d.sync_all())
                .map_err(|_| SaveFailure::DurabilityUncertain)?;
            Ok(())
        }
    }

    impl Drop for Store {
        fn drop(&mut self) {
            let path = self.dir.join(LOCK);
            // Protect a replaced lock inode from unintended unlink on exit.
            if self.lock_handle.metadata().is_ok_and(|descriptor| {
                fs::symlink_metadata(&path).is_ok_and(|current| {
                    (descriptor.dev(), descriptor.ino()) == self.lock_inode
                        && (current.dev(), current.ino()) == self.lock_inode
                })
            }) {
                let _ = fs::remove_file(path);
            }
        }
    }
}

#[cfg(unix)]
pub use unix::Store;

#[cfg(not(unix))]
pub struct Store;
#[cfg(not(unix))]
impl Store {
    pub fn open(
        _: &Path,
        _: &str,
        _: &BTreeMap<String, StateDef>,
        _: bool,
    ) -> Result<(Self, Values, Ledger)> {
        fail("E_SERVER_STORAGE: file persistence currently requires Unix")
    }
    pub fn save_transaction(
        &mut self,
        _: &Values,
        _: &Ledger,
    ) -> std::result::Result<(), SaveFailure> {
        Err(SaveFailure::RejectedBeforeCommit)
    }
    pub fn save(&mut self, _: &Values) -> std::result::Result<(), SaveFailure> {
        Err(SaveFailure::RejectedBeforeCommit)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::server::ScalarType;
    #[test]
    fn malformed_and_duplicate_snapshots_refused() {
        let defs = BTreeMap::from([(
            "n".into(),
            StateDef {
                kind: ScalarType::Int,
                initial: json!(0),
            },
        )]);
        let sig = signature("Test", &defs).unwrap();
        let raw = format!(
            r#"{{"schema":"sedrava.server.state.v1","signature":"{sig}","state":{{"n":1,"n":2}}}}"#
        );
        assert!(decoded(raw.as_bytes(), &sig, &defs).is_err());
        let raw = format!(
            r#"{{"schema":"sedrava.server.state.v1","signature":"{sig}","state":{{"n":2147483648}}}}"#
        );
        assert!(decoded(raw.as_bytes(), &sig, &defs).is_err());
        let raw = format!(
            r#"{{"schema":"sedrava.server.state.v1","signature":"wrong","state":{{"n":1}}}}"#
        );
        assert!(decoded(raw.as_bytes(), &sig, &defs).is_err());
    }
}
