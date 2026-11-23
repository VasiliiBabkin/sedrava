//! A8 checked, opt-in managed SedravaSQL write declaration.
//! This is NOT arbitrary SQL. It operates on exactly one literal KV key.
use super::{identifier, ScalarType};
use crate::model::{fail, Error, Result};
use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};
use std::collections::BTreeMap;

pub(super) const RECEIPT_SCHEMA: &str = "sedrava.server.a8.kv-put.v1";

#[derive(Clone, Debug)]
pub struct DbPut {
    pub namespace: String,
    pub key: String,
    pub request_field: String,
}

pub fn valid_db_id(input: &str) -> bool {
    !input.is_empty()
        && input.len() <= 128
        && input
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || matches!(b, b'.' | b'-' | b'_'))
}

impl DbPut {
    pub fn parse(raw: &str, request: &BTreeMap<String, ScalarType>) -> Result<Self> {
        let (literal, field) = raw
            .strip_prefix("db_put ")
            .and_then(|r| r.split_once(" = request."))
            .ok_or_else(|| {
                Error("E_SERVER_DB_PUT: expected db_put \"namespace/key\" = request.FIELD".into())
            })?;
        let path: String = serde_json::from_str(literal)
            .map_err(|_| Error("E_SERVER_DB_PUT: expected literal quoted namespace/key".into()))?;
        let (namespace, key) = path
            .split_once('/')
            .ok_or_else(|| Error("E_SERVER_DB_PUT: expected exactly one namespace/key".into()))?;
        if !valid_db_id(namespace)
            || !valid_db_id(key)
            || namespace.starts_with("sedrava_native")
            || !identifier(field)
            || request.len() != 1
            || request.get(field) != Some(&ScalarType::Text)
        {
            return fail(
                "E_SERVER_DB_PUT: invalid/reserved key or requires one text request field",
            );
        }
        Ok(Self {
            namespace: namespace.to_owned(),
            key: key.to_owned(),
            request_field: field.to_owned(),
        })
    }
}

/// Whole response is retained atomically with the KV value, audit, and receipt.
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct PutReceipt {
    pub schema: String,
    pub program_signature: String,
    pub route: String,
    pub client_key: String,
    pub fingerprint: String,
    pub revision: u32,
    pub status: u16,
    pub response: Map<String, Value>,
}

#[derive(Debug)]
pub enum PutFailure {
    IdempotencyConflict,
    RevisionConflict,
    Invalid,
    Uncertain,
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn only_literal_one_key_and_one_text_input() {
        let schema = BTreeMap::from([("value".into(), ScalarType::Text)]);
        let p = DbPut::parse(r#"db_put "public_notes/welcome" = request.value"#, &schema).unwrap();
        assert_eq!(p.namespace, "public_notes");
        assert_eq!(p.key, "welcome");
        assert_eq!(p.request_field, "value");
        for raw in [
            r#"db_put "sedrava_native_a6/state" = request.value"#,
            r#"db_put "public_notes/../../bad" = request.value"#,
            r#"db_put request.path = request.value"#,
            r#"db_put "public_notes/" = request.value"#,
            r#"db_put "public_notes/welcome" = request.unknown"#,
            r#"db_put "public_notes/welcome" = request.value + "!" "#,
            r#"db_put "public_notes/welcome/extra" = request.value"#,
        ] {
            assert!(DbPut::parse(raw, &schema).is_err(), "{raw}");
        }
        let invalid = BTreeMap::from([("value".into(), ScalarType::Int)]);
        assert!(
            DbPut::parse(r#"db_put "public_notes/welcome" = request.value"#, &invalid).is_err()
        );
    }
}
