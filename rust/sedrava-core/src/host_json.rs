//! Strict, bounded Host-only JSON. This is deliberately not a core value type
//! and never grants Web/Android filesystem capabilities.
use crate::model::ensure_text;
use serde::de::{self, Deserialize, Deserializer, MapAccess, SeqAccess, Visitor};
use serde_json::{Map, Number, Value};
use std::fmt;

pub(crate) const MAX_BYTES: usize = 4096;
const MAX_NODES: usize = 128;
const MAX_DEPTH: usize = 8;
const MAX_FIELDS: usize = 32;

#[derive(Clone, Debug)]
pub(crate) struct Document(pub(crate) Value);

#[derive(Debug)]
struct Unique(Value);

impl<'de> Deserialize<'de> for Unique {
    fn deserialize<D: Deserializer<'de>>(deserializer: D) -> std::result::Result<Self, D::Error> {
        struct JsonVisitor;
        impl<'de> Visitor<'de> for JsonVisitor {
            type Value = Unique;
            fn expecting(&self, f: &mut fmt::Formatter) -> fmt::Result {
                write!(
                    f,
                    "strict JSON without floats, duplicate keys or oversized integers"
                )
            }
            fn visit_unit<E: de::Error>(self) -> std::result::Result<Unique, E> {
                Ok(Unique(Value::Null))
            }
            fn visit_none<E: de::Error>(self) -> std::result::Result<Unique, E> {
                Ok(Unique(Value::Null))
            }
            fn visit_bool<E: de::Error>(self, x: bool) -> std::result::Result<Unique, E> {
                Ok(Unique(Value::Bool(x)))
            }
            fn visit_i64<E: de::Error>(self, x: i64) -> std::result::Result<Unique, E> {
                let n = i32::try_from(x).map_err(|_| E::custom("JSON int32 exceeded"))?;
                Ok(Unique(Value::Number(Number::from(n))))
            }
            fn visit_u64<E: de::Error>(self, x: u64) -> std::result::Result<Unique, E> {
                let n = i32::try_from(x).map_err(|_| E::custom("JSON int32 exceeded"))?;
                Ok(Unique(Value::Number(Number::from(n))))
            }
            fn visit_f64<E: de::Error>(self, _: f64) -> std::result::Result<Unique, E> {
                Err(E::custom("JSON floating-point values forbidden"))
            }
            fn visit_str<E: de::Error>(self, x: &str) -> std::result::Result<Unique, E> {
                ensure_text(x).map_err(E::custom)?;
                Ok(Unique(Value::String(x.into())))
            }
            fn visit_string<E: de::Error>(self, x: String) -> std::result::Result<Unique, E> {
                ensure_text(&x).map_err(E::custom)?;
                Ok(Unique(Value::String(x)))
            }
            fn visit_seq<A: SeqAccess<'de>>(
                self,
                mut a: A,
            ) -> std::result::Result<Unique, A::Error> {
                let mut values = Vec::new();
                while let Some(v) = a.next_element::<Unique>()? {
                    if values.len() == MAX_NODES {
                        return Err(de::Error::custom("JSON node limit"));
                    }
                    values.push(v.0);
                }
                Ok(Unique(Value::Array(values)))
            }
            fn visit_map<A: MapAccess<'de>>(
                self,
                mut a: A,
            ) -> std::result::Result<Unique, A::Error> {
                let mut values = Map::new();
                while let Some((k, v)) = a.next_entry::<String, Unique>()? {
                    ensure_text(&k).map_err(de::Error::custom)?;
                    if values.len() == MAX_FIELDS || values.contains_key(&k) {
                        return Err(de::Error::custom("JSON field limit or duplicate key"));
                    }
                    values.insert(k, v.0);
                }
                Ok(Unique(Value::Object(values)))
            }
        }
        deserializer.deserialize_any(JsonVisitor)
    }
}

fn bounded(value: &Value, depth: usize, nodes: &mut usize) -> Result<(), &'static str> {
    *nodes += 1;
    if *nodes > MAX_NODES || depth > MAX_DEPTH {
        return Err("JSON depth/node limit");
    }
    match value {
        Value::Null | Value::Bool(_) => {}
        Value::Number(n) => {
            if n.as_i64().and_then(|x| i32::try_from(x).ok()).is_none() {
                return Err("JSON requires int32 numbers");
            }
        }
        Value::String(s) => {
            ensure_text(s).map_err(|_| "JSON text limit")?;
        }
        Value::Array(items) => {
            for item in items {
                bounded(item, depth + 1, nodes)?;
            }
        }
        Value::Object(fields) => {
            if fields.len() > MAX_FIELDS {
                return Err("JSON object field limit");
            }
            for (key, item) in fields {
                ensure_text(key).map_err(|_| "JSON key limit")?;
                bounded(item, depth + 1, nodes)?;
            }
        }
    }
    Ok(())
}

pub(crate) fn validate(value: Value) -> Result<Document, &'static str> {
    bounded(&value, 0, &mut 0)?;
    let raw = serde_json::to_vec(&value).map_err(|_| "JSON serialization failed")?;
    if raw.len() > MAX_BYTES {
        return Err("JSON document byte limit");
    }
    Ok(Document(value))
}

pub(crate) fn parse(raw: &str) -> Result<Document, &'static str> {
    if raw.len() > MAX_BYTES {
        return Err("JSON input byte limit");
    }
    let Unique(value) = serde_json::from_str::<Unique>(raw).map_err(|_| "Invalid strict JSON")?;
    validate(value)
}

pub(crate) fn compact(doc: &Document) -> Result<String, &'static str> {
    validate(doc.0.clone())?;
    serde_json::to_string(&doc.0).map_err(|_| "JSON serialization failed")
}

pub(crate) enum Key {
    Text(String),
    Index(i32),
}

pub(crate) fn get(doc: &Document, key: Key) -> Result<Document, &'static str> {
    let value = match (&doc.0, key) {
        (Value::Object(m), Key::Text(k)) => m.get(&k),
        (Value::Array(a), Key::Index(i)) => usize::try_from(i).ok().and_then(|i| a.get(i)),
        _ => return Err("JSON object/array key type mismatch"),
    }
    .ok_or("JSON key not found")?;
    validate(value.clone())
}

pub(crate) fn count(doc: &Document) -> Result<i32, &'static str> {
    match &doc.0 {
        Value::Array(a) => i32::try_from(a.len()).map_err(|_| "JSON array too large"),
        Value::Object(o) => i32::try_from(o.len()).map_err(|_| "JSON object too large"),
        _ => Err("JSON count requires array or object"),
    }
}

pub(crate) fn set(doc: &Document, key: &str, value: Value) -> Result<Document, &'static str> {
    if key.is_empty() || key.len() > 128 {
        return Err("Invalid JSON object key");
    }
    ensure_text(key).map_err(|_| "Invalid JSON object key")?;
    let Value::Object(mut fields) = doc.0.clone() else {
        return Err("JSON set requires object");
    };
    if fields.contains_key(key) {
        return Err("Duplicate JSON field");
    }
    fields.insert(key.into(), value);
    validate(Value::Object(fields))
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn strict_documents_and_limits() {
        for bad in [
            r#"{"x":1,"x":2}"#,
            "1.0",
            "1e2",
            "2147483648",
            "-2147483649",
            r#"{"x":"\ud800"}"#,
            r#"{"x":NaN}"#,
            "[[[[[[[[[0]]]]]]]]]",
        ] {
            assert!(parse(bad).is_err(), "accepted {bad}");
        }
        assert!(parse(&format!(r#"{{"a":"{}"}}"#, "x".repeat(4096))).is_err());
        assert!(parse(r#"{"b":true,"a":[1,null]}"#).is_ok());
        assert!(parse(&format!("[{}]", vec!["0"; 128].join(","))).is_err());
    }
    #[test]
    fn json_mutations_and_keys() {
        let doc = parse(r#"{"item":{"title":"Hello"},"arr":[1,2]}"#).unwrap();
        let child = get(&doc, Key::Text("item".into())).unwrap();
        let title = get(&child, Key::Text("title".into())).unwrap();
        assert_eq!(title.0, Value::String("Hello".into()));
        assert_eq!(count(&get(&doc, Key::Text("arr".into())).unwrap()), Ok(2));
        assert!(get(&doc, Key::Index(0)).is_err());
        assert!(set(&doc, "item", Value::Null).is_err());
        let changed = set(&doc, "created", Value::Bool(true)).unwrap();
        assert_eq!(parse(&compact(&changed).unwrap()).unwrap().0, changed.0);
    }
}
