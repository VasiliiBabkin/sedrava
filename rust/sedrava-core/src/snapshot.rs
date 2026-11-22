//! Schema-1 persistence compatible with the Python 0.11 Sedrava interpreter.
//!
//! Snapshot validation is strict: every JSON object rejects duplicate keys,
//! all numbers must be int32, and restoration is never applied in-place.
//! This module implements the data codec only; CLI file replacement is separate.
use crate::model::{
    fail, validate, Error, Kind, ListItem, Program, Result, State, Value, MAX_SNAPSHOT_UTF16,
};
use crate::runtime::valid_state;
use serde::de::{self, Deserialize, Deserializer, MapAccess, SeqAccess, Visitor};
use serde_json::{json, Map, Value as Json};
use std::collections::BTreeSet;
use std::fmt;

pub fn fingerprint(program: &Program) -> Result<String> {
    let mut entries = Vec::with_capacity(program.state_order.len());
    for key in &program.state_order {
        let initial = program
            .states
            .get(key)
            .ok_or_else(|| Error("Invalid state declaration order".into()))?;
        let kind = match initial.kind() {
            Kind::Int => json!("int"),
            Kind::Bool => json!("bool"),
            Kind::Text => json!("str"),
            Kind::List { record, capacity } => {
                let Kind::Record { name, fields } = record.as_ref() else {
                    return fail("Unsupported snapshot collection type");
                };
                let fields: Vec<Json> = fields
                    .iter()
                    .map(|(name, kind)| {
                        json!([
                            name,
                            match kind {
                                Kind::Int => "int",
                                Kind::Bool => "bool",
                                Kind::Text => "str",
                                _ => "unsupported",
                            }
                        ])
                    })
                    .collect();
                json!(["list", name, fields, capacity])
            }
            _ => return fail("Unsupported snapshot state type"),
        };
        entries.push(json!([key, kind, program.persistent.contains(key)]));
    }
    serde_json::to_string(&entries)
        .map_err(|e| Error(format!("Snapshot schema encoding failed: {e}")))
}

fn max_size(raw: &str) -> Result<()> {
    if raw.encode_utf16().count() > MAX_SNAPSHOT_UTF16 {
        return fail("Snapshot exceeds UTF-16 code-unit limit");
    }
    Ok(())
}

pub fn serialize_state(program: &Program, state: &State) -> Result<String> {
    if !valid_state(program, state) {
        return fail("Invalid state; snapshot not generated");
    }
    let mut retained = Map::new();
    for key in &program.state_order {
        if program.persistent.contains(key) {
            let value = state
                .get(key)
                .ok_or_else(|| Error("Missing persistent state".into()))?;
            retained.insert(key.clone(), value.plain());
        }
    }
    let outer = json!({"schema":1,"signature":fingerprint(program)?,"state":retained});
    let raw =
        serde_json::to_string(&outer).map_err(|e| Error(format!("Snapshot JSON failed: {e}")))?;
    max_size(&raw)?;
    Ok(raw)
}

/// A recursive JSON value decoder rejecting duplicates, floats and overflow
/// before object keys can be collapsed into serde_json::Map.
struct StrictJson(Json);
impl<'de> Deserialize<'de> for StrictJson {
    fn deserialize<D: Deserializer<'de>>(deserializer: D) -> std::result::Result<Self, D::Error> {
        struct StrictVisitor;
        impl<'de> Visitor<'de> for StrictVisitor {
            type Value = StrictJson;
            fn expecting(&self, f: &mut fmt::Formatter) -> fmt::Result {
                f.write_str(
                    "strict JSON without duplicate keys, floating point values or int32 overflow",
                )
            }
            fn visit_unit<E: de::Error>(self) -> std::result::Result<Self::Value, E> {
                Ok(StrictJson(Json::Null))
            }
            fn visit_bool<E: de::Error>(self, b: bool) -> std::result::Result<Self::Value, E> {
                Ok(StrictJson(Json::Bool(b)))
            }
            fn visit_i64<E: de::Error>(self, v: i64) -> std::result::Result<Self::Value, E> {
                let v = i32::try_from(v).map_err(|_| E::custom("Integer outside int32"))?;
                Ok(StrictJson(json!(v)))
            }
            fn visit_u64<E: de::Error>(self, v: u64) -> std::result::Result<Self::Value, E> {
                let v = i32::try_from(v).map_err(|_| E::custom("Integer outside int32"))?;
                Ok(StrictJson(json!(v)))
            }
            fn visit_f64<E: de::Error>(self, _value: f64) -> std::result::Result<Self::Value, E> {
                Err(E::custom("Floating point JSON is not supported"))
            }
            fn visit_str<E: de::Error>(self, v: &str) -> std::result::Result<Self::Value, E> {
                Ok(StrictJson(Json::String(v.to_owned())))
            }
            fn visit_string<E: de::Error>(self, v: String) -> std::result::Result<Self::Value, E> {
                Ok(StrictJson(Json::String(v)))
            }
            fn visit_none<E: de::Error>(self) -> std::result::Result<Self::Value, E> {
                Ok(StrictJson(Json::Null))
            }
            fn visit_some<D: Deserializer<'de>>(
                self,
                d: D,
            ) -> std::result::Result<Self::Value, D::Error> {
                StrictJson::deserialize(d)
            }
            fn visit_seq<A: SeqAccess<'de>>(
                self,
                mut access: A,
            ) -> std::result::Result<Self::Value, A::Error> {
                let mut output = Vec::new();
                while let Some(element) = access.next_element::<StrictJson>()? {
                    output.push(element.0);
                }
                Ok(StrictJson(Json::Array(output)))
            }
            fn visit_map<A: MapAccess<'de>>(
                self,
                mut access: A,
            ) -> std::result::Result<Self::Value, A::Error> {
                let mut output = Map::new();
                while let Some((key, value)) = access.next_entry::<String, StrictJson>()? {
                    if output.insert(key.clone(), value.0).is_some() {
                        return Err(de::Error::custom(format!("Duplicate JSON key: {key}")));
                    }
                }
                Ok(StrictJson(Json::Object(output)))
            }
        }
        deserializer.deserialize_any(StrictVisitor)
    }
}

fn require_keys(obj: &Map<String, Json>, expected: &[&str]) -> Result<()> {
    if obj.len() != expected.len() || expected.iter().any(|key| !obj.contains_key(*key)) {
        return fail("Unexpected/missing snapshot keys");
    }
    Ok(())
}
fn json_i32(value: &Json) -> Result<i32> {
    match value {
        Json::Number(n) => n
            .as_i64()
            .and_then(|v| i32::try_from(v).ok())
            .ok_or_else(|| Error("Snapshot integer outside int32".into())),
        _ => fail("Expected JSON integer"),
    }
}
fn decode(json: &Json, kind: &Kind) -> Result<Value> {
    match (json, kind) {
        (Json::Bool(b), Kind::Bool) => Ok(Value::Bool(*b)),
        (Json::Number(_), Kind::Int) => Ok(Value::Int(json_i32(json)?)),
        (Json::String(s), Kind::Text) => {
            crate::model::ensure_text(s)?;
            Ok(Value::Text(s.clone()))
        }
        (Json::Object(fields), Kind::Record { fields: schema, .. }) => {
            if fields.len() != schema.len() {
                return fail("Record snapshot field count mismatch");
            }
            let mut decoded = std::collections::BTreeMap::new();
            for (name, field_kind) in schema {
                let raw = fields
                    .get(name)
                    .ok_or_else(|| Error("Missing snapshot record field".into()))?;
                decoded.insert(name.clone(), decode(raw, field_kind)?);
            }
            let value = Value::Record {
                kind: kind.clone(),
                fields: decoded,
            };
            validate(&value, kind)?;
            Ok(value)
        }
        (Json::Object(obj), Kind::List { record, capacity }) => {
            require_keys(obj, &["next_id", "items"])?;
            let next_id = json_i32(&obj["next_id"])?;
            let rows = obj["items"]
                .as_array()
                .ok_or_else(|| Error("Snapshot items must be array".into()))?;
            if rows.len() > *capacity {
                return fail("Snapshot collection exceeds capacity");
            }
            let Kind::Record {
                fields: record_fields,
                ..
            } = record.as_ref()
            else {
                return fail("List snapshot requires record item kind");
            };
            let mut items = Vec::with_capacity(rows.len());
            let mut identities = BTreeSet::new();
            for row in rows {
                let row = row
                    .as_object()
                    .ok_or_else(|| Error("List item must be an object".into()))?;
                if row.len() != record_fields.len() + 1
                    || row.keys().any(|key| {
                        key != "id" && !record_fields.iter().any(|(name, _)| name == key)
                    })
                {
                    return fail("Snapshot item fields differ from record type");
                }
                let id = json_i32(
                    row.get("id")
                        .ok_or_else(|| Error("Missing identity".into()))?,
                )?;
                if id <= 0 || id >= next_id || !identities.insert(id) {
                    return fail("Invalid or duplicate record identity");
                }
                let record_value = decode(
                    &Json::Object(
                        row.iter()
                            .filter(|(key, _)| key.as_str() != "id")
                            .map(|(k, v)| (k.clone(), v.clone()))
                            .collect(),
                    ),
                    record,
                )?;
                items.push(ListItem {
                    id,
                    record: record_value,
                });
            }
            let value = Value::List {
                kind: kind.clone(),
                items,
                next_id,
            };
            validate(&value, kind)?;
            Ok(value)
        }
        _ => fail("Snapshot value does not match declared type"),
    }
}

pub fn restore_snapshot(program: &Program, raw: &str) -> Result<State> {
    max_size(raw)?;
    let mut parser = serde_json::Deserializer::from_str(raw);
    let document = StrictJson::deserialize(&mut parser)
        .map_err(|e| Error(format!("Invalid snapshot JSON: {e}")))?
        .0;
    parser
        .end()
        .map_err(|e| Error(format!("Trailing snapshot input: {e}")))?;
    let obj = document
        .as_object()
        .ok_or_else(|| Error("Snapshot must be JSON object".into()))?;
    require_keys(obj, &["schema", "signature", "state"])?;
    if json_i32(&obj["schema"])? != 1 {
        return fail("Unsupported snapshot schema");
    }
    if obj["signature"].as_str() != Some(fingerprint(program)?.as_str()) {
        return fail("Incompatible snapshot signature");
    }
    let payload = obj["state"]
        .as_object()
        .ok_or_else(|| Error("Persistent state must be an object".into()))?;
    if payload.len() != program.persistent.len()
        || program
            .persistent
            .iter()
            .any(|key| !payload.contains_key(key))
    {
        return fail("Snapshot persisted keys differ from program");
    }
    let mut candidate = program.states.clone();
    for key in &program.persistent {
        let initial = program
            .states
            .get(key)
            .ok_or_else(|| Error("Unknown persistent state".into()))?;
        let source = payload
            .get(key)
            .ok_or_else(|| Error("Persistent value missing".into()))?;
        candidate.insert(key.clone(), decode(source, &initial.kind())?);
    }
    if !valid_state(program, &candidate) {
        return fail("Restored snapshot violates state invariants");
    }
    Ok(candidate)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::parser::parse;
    use crate::runtime::transition;

    fn fixture() -> Program {
        parse(include_str!(
            "../../../tests/rust_cases/persistent_records.sdr"
        ))
        .unwrap()
    }

    #[test]
    fn schema_signature_matches_python_011() {
        let p = fixture();
        let expected = r#"[["title","str",true],["tasks",["list","Task",[["title","str"],["done","bool"]],10],true],["selected","int",false]]"#;
        assert_eq!(fingerprint(&p).unwrap(), expected);
        assert_eq!(p.state_order, vec!["title", "tasks", "selected"]);
        assert_eq!(p.persistent.len(), 2);
    }

    #[test]
    fn portable_save_restore_with_records() {
        let p = fixture();
        let (state, accepted) = transition(&p, &p.states, "add").unwrap();
        assert!(accepted);
        let raw = serialize_state(&p, &state).unwrap();
        assert_eq!(restore_snapshot(&p, &raw).unwrap(), state);
        let document: Json = serde_json::from_str(&raw).unwrap();
        assert_eq!(document["schema"], 1);
        assert_eq!(document["state"]["tasks"]["items"][0]["id"], 1);
        assert!(document["state"].get("selected").is_none());
    }

    #[test]
    fn strict_json_rejects_mutations_and_duplicates() {
        let p = fixture();
        let (state, accepted) = transition(&p, &p.states, "add").unwrap();
        assert!(accepted);
        let raw = serialize_state(&p, &state).unwrap();
        let base: Json = serde_json::from_str(&raw).unwrap();
        let mut bad = base.clone();
        bad["schema"] = json!(2);
        assert!(restore_snapshot(&p, &bad.to_string()).is_err());
        let mut bad = base.clone();
        bad["signature"] = json!("incompatible");
        assert!(restore_snapshot(&p, &bad.to_string()).is_err());
        let mut bad = base.clone();
        bad["state"]["tasks"]["items"][0]["id"] = json!(true);
        assert!(restore_snapshot(&p, &bad.to_string()).is_err());
        let mut bad = base.clone();
        bad["state"]["tasks"]["next_id"] = json!(2_147_483_648_i64);
        assert!(restore_snapshot(&p, &bad.to_string()).is_err());
        let double = raw.replacen("\"schema\":1", "\"schema\":1,\"schema\":1", 1);
        assert!(restore_snapshot(&p, &double).is_err());
        let double_nested = raw.replacen("\"next_id\":2", "\"next_id\":2,\"next_id\":2", 1);
        assert!(restore_snapshot(&p, &double_nested).is_err());
    }

    #[test]
    fn failed_restore_cannot_mutate_program_defaults() {
        let p = fixture();
        let initial = p.states.clone();
        let mut doc: Json = serde_json::from_str(&serialize_state(&p, &initial).unwrap()).unwrap();
        doc["state"]["title"] = json!("Z".repeat(1025));
        assert!(restore_snapshot(&p, &doc.to_string()).is_err());
        assert_eq!(p.states, initial);
    }

    #[test]
    fn bounded_unicode_snapshot_roundtrips() {
        let p = fixture();
        for length in [0usize, 1, 17, 100, 1024] {
            let mut state = p.states.clone();
            state.insert("title".into(), Value::Text("😀".repeat(length)));
            let raw = serialize_state(&p, &state).unwrap();
            assert_eq!(restore_snapshot(&p, &raw).unwrap(), state);
        }
    }
}
