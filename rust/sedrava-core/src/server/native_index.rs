//! A11: explicit read-only offline native snapshot backend.
use crate::model::{fail, Error, Result};
use sedravasql::native_log::index::VerifiedIndexReader;
use std::{collections::BTreeSet, path::Path};

pub(super) struct NativeIndexStore {
    reader: VerifiedIndexReader,
}

impl NativeIndexStore {
    pub(super) fn open(path: &Path, approved: &str) -> Result<Self> {
        if !path.is_absolute() || approved.len() != 64
            || !approved.bytes().all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b)) {
            return fail("E_SERVER_NATIVE_INDEX: absolute path and lowercase SHA-256 required");
        }
        let reader = VerifiedIndexReader::open(path)
            .map_err(|_| Error("E_SERVER_NATIVE_INDEX: index verification failed".into()))?;
        if reader.report().index_sha256 != approved {
            return fail("E_SERVER_NATIVE_INDEX: approved SHA-256 mismatch");
        }
        Ok(Self { reader })
    }

    pub(super) fn read_text_snapshot(&mut self, keys: &[(String, String)]) -> Result<Vec<Option<(String, u64)>>> {
        let mut seen = BTreeSet::new();
        if keys.is_empty() || keys.len() > 16 || keys.iter().any(|(ns,key)|
            ns.starts_with("sedrava_native") || !seen.insert((ns,key))) {
            return fail("E_SERVER_DB: invalid or reserved snapshot key list");
        }
        let mut output = Vec::with_capacity(keys.len());
        for (ns,key) in keys {
            let row = self.reader.get(ns,key)
                .map_err(|_| Error("E_SERVER_DB: native index read failed".into()))?;
            let item = match row {
                Some(row) => match row.value {
                    Some(value) => {
                        if value.chars().count() > 1024 || value.chars().any(char::is_control) {
                            return fail("E_SERVER_DB: stored value outside text scalar limits");
                        }
                        Some((value,row.revision))
                    }
                    None => None,
                },
                None => None,
            };
            output.push(item);
        }
        Ok(output)
    }
}
