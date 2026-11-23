//! Server A3: bounded idempotency + revision protocol.
//! Records are stored *with state in one atomic snapshot*, never separately.
//! A fixed, non-evicting ledger is deliberately finite. After reaching its
//! limit, reject all new writes rather than silently forgetting old keys.
use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};
use sha2::{Digest, Sha256};
use std::collections::BTreeSet;

pub const MAX_RECEIPTS: usize = 32;
pub const MAX_TRANSACTION_BYTES: u64 = 262_144;
pub const SCHEMA: &str = "sedrava.server.transaction.v1";

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Receipt {
    pub key: String,
    pub fingerprint: String,
    pub revision: u32,
    pub status: u16,
    pub response: Map<String, Value>,
}

#[derive(Clone, Debug, Default)]
pub struct Ledger {
    pub receipts: Vec<Receipt>,
}

impl Ledger {
    pub fn revision(&self) -> u32 {
        self.receipts.len() as u32
    }

    pub fn get(&self, key: &str) -> Option<&Receipt> {
        self.receipts.iter().find(|r| r.key == key)
    }

    pub fn append(&self, receipt: Receipt) -> Option<Self> {
        if self.receipts.len() >= MAX_RECEIPTS
            || receipt.revision != self.revision() + 1
            || self.get(&receipt.key).is_some()
        {
            return None;
        }
        let mut next = self.clone();
        next.receipts.push(receipt);
        Some(next)
    }

    pub fn valid(&self) -> bool {
        if self.receipts.len() > MAX_RECEIPTS {
            return false;
        }
        let mut seen = BTreeSet::new();
        for (index, r) in self.receipts.iter().enumerate() {
            if r.revision != (index + 1) as u32
                || !valid_key(&r.key)
                || !is_hash(&r.fingerprint)
                || !matches!(r.status, 200 | 201 | 202)
                || !seen.insert(r.key.as_str())
                || r.response.is_empty()
                || r.response.len() > 32
                || !r.response.iter().all(|(name, value)| {
                    valid_field(name)
                        && match value {
                            Value::Bool(_) => true,
                            Value::Number(n) => {
                                n.as_i64().is_some_and(|v| i32::try_from(v).is_ok())
                            }
                            Value::String(s) => {
                                s.chars().count() <= 1024 && !s.chars().any(char::is_control)
                            }
                            _ => false,
                        }
                })
            {
                return false;
            }
        }
        true
    }
}

pub fn valid_key(value: &str) -> bool {
    (12..=64).contains(&value.len())
        && value
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || matches!(b, b'-' | b'_' | b'.'))
}

fn is_hash(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|b| b.is_ascii_hexdigit() && !b.is_ascii_uppercase())
}

fn valid_field(value: &str) -> bool {
    let mut chars = value.chars();
    matches!(chars.next(), Some(c) if c.is_ascii_alphabetic())
        && chars.all(|c| c.is_ascii_alphanumeric() || c == '_')
        && value.len() <= 64
}

pub fn fingerprint(
    method: &str,
    path: &str,
    content_type: Option<&str>,
    body: &[u8],
    expected_revision: Option<&str>,
) -> String {
    // Tuple framing is unambiguous even when JSON text contains delimiters.
    let canonical = serde_json::to_vec(&(
        "sedrava.a3.idempotency.v1",
        method,
        path,
        content_type.unwrap_or(""),
        body,
        expected_revision.unwrap_or(""),
    ))
    .expect("static tuple serialization cannot fail");
    format!("{:x}", Sha256::digest(canonical))
}

pub fn parse_revision(value: &str) -> Option<u32> {
    if value.is_empty()
        || (value.len() > 1 && value.starts_with('0'))
        || !value.bytes().all(|x| x.is_ascii_digit())
    {
        return None;
    }
    value.parse::<u32>().ok()
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn idempotency_fingerprint_includes_method_path_payload_and_revision() {
        let base = fingerprint(
            "POST",
            "/x",
            Some("application/json"),
            br#"{"a":1}"#,
            Some("0"),
        );
        assert_eq!(
            base,
            fingerprint(
                "POST",
                "/x",
                Some("application/json"),
                br#"{"a":1}"#,
                Some("0")
            )
        );
        assert_ne!(
            base,
            fingerprint(
                "POST",
                "/x",
                Some("application/json"),
                br#"{"a":2}"#,
                Some("0")
            )
        );
        assert_ne!(
            base,
            fingerprint(
                "POST",
                "/y",
                Some("application/json"),
                br#"{"a":1}"#,
                Some("0")
            )
        );
        assert_ne!(
            base,
            fingerprint(
                "POST",
                "/x",
                Some("application/json"),
                br#"{"a":1}"#,
                Some("1")
            )
        );
        assert_ne!(
            base,
            fingerprint(
                "PUT",
                "/x",
                Some("application/json"),
                br#"{"a":1}"#,
                Some("0")
            )
        );
        assert!(valid_key("request-0000001"));
        assert!(!valid_key("a"));
        assert!(!valid_key("request with whitespace"));
        assert_eq!(parse_revision("0"), Some(0));
        assert_eq!(parse_revision("42"), Some(42));
        for bad in ["", "00", "01", "-1", "4294967296", "+1", "1.0"] {
            assert_eq!(parse_revision(bad), None);
        }
    }
    #[test]
    fn bounded_ledger_never_evicts_and_rejects_duplicate_ids() {
        let mut ledger = Ledger::default();
        for i in 0..MAX_RECEIPTS {
            let r = Receipt {
                key: format!("request-id-{i:04}"),
                fingerprint: "0".repeat(64),
                revision: (i + 1) as u32,
                status: 200,
                response: Map::from_iter([("ok".into(), Value::Bool(true))]),
            };
            ledger = ledger.append(r).unwrap();
            assert!(ledger.valid());
        }
        assert_eq!(ledger.revision(), MAX_RECEIPTS as u32);
        assert!(ledger
            .append(Receipt {
                key: "request-id-9999".into(),
                fingerprint: "0".repeat(64),
                revision: 33,
                status: 200,
                response: Map::from_iter([("ok".into(), Value::Bool(true))])
            })
            .is_none());
    }
}
