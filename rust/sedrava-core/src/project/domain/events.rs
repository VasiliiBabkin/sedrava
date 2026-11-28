//! Explicit event payloads. All dates are operator-supplied; uncaptured numbers
//! use a declared constant, not a stale form value.
use super::{error, label, name};
use crate::model::Result;
use std::{collections::BTreeSet, fmt::Write};

#[derive(serde::Serialize)]
enum Kind {
    Date,
    Int(i32, i32, i32),
}
struct Event {
    name: String,
    label: String,
    kind: Kind,
}
#[derive(Default)]
pub(super) struct Events(Vec<Event>);
impl Events {
    pub fn add(&mut self, raw: &str, line: usize) -> Result<()> {
        let (decl, caption) = raw
            .split_once(" label ")
            .ok_or_else(|| error(line, "event label required"))?;
        let (id, ty) = decl
            .split_once(": ")
            .ok_or_else(|| error(line, "event NAME: TYPE required"))?;
        if !name(id) || self.0.len() >= 3 || self.0.iter().any(|e| e.name == id) {
            return Err(error(line, "invalid/duplicate event field or budget"));
        }
        let words = ty.split_ascii_whitespace().collect::<Vec<_>>();
        let kind = match words.as_slice() {
            ["date"] => Kind::Date,
            ["int", lo, hi, "otherwise", other] => {
                let parse = |s: &str| {
                    s.parse::<i32>()
                        .map_err(|_| error(line, "invalid event integer"))
                };
                let (lo, hi, other) = (parse(lo)?, parse(hi)?, parse(other)?);
                // Bound individual values; SQL also rejects overflowing sums.
                if lo > hi
                    || [lo, hi, other]
                        .iter()
                        .any(|n| !(-500000..=500000).contains(n))
                {
                    return Err(error(line, "event integer bounds"));
                }
                Kind::Int(lo, hi, other)
            }
            _ => return Err(error(line, "expected date or int MIN MAX otherwise VALUE")),
        };
        self.0.push(Event {
            name: id.into(),
            label: label(caption, line)?,
            kind,
        });
        Ok(())
    }
    pub fn capture(&self, raw: &str, line: usize) -> Result<BTreeSet<String>> {
        let ids = raw.split_ascii_whitespace().collect::<Vec<_>>();
        let set = ids.iter().map(|s| s.to_string()).collect::<BTreeSet<_>>();
        if ids.is_empty()
            || ids.len() != set.len()
            || set.iter().any(|id| {
                !self
                    .0
                    .iter()
                    .any(|e| e.name == *id && matches!(e.kind, Kind::Int(..)))
            })
        {
            return Err(error(line, "capture requires unique numeric event fields"));
        }
        Ok(set)
    }
    fn captured(e: &Event, capture: &BTreeSet<String>) -> bool {
        matches!(e.kind, Kind::Date) || capture.contains(&e.name)
    }
    pub fn states(&self, app: &mut String) {
        for e in &self.0 {
            let v = match e.kind {
                Kind::Date => "\"\"".into(),
                Kind::Int(a, b, _) => 0.clamp(a, b).to_string(),
            };
            writeln!(app, "state ev_{} = {v}", e.name).unwrap();
        }
    }
    pub fn ddl(&self) -> String {
        self.0
            .iter()
            .map(|e| {
                format!(
                    ", ev_{} {}",
                    e.name,
                    if matches!(e.kind, Kind::Date) {
                        "TEXT"
                    } else {
                        "INT"
                    }
                )
            })
            .collect()
    }
    pub fn columns(&self) -> String {
        self.0.iter().map(|e| format!(",ev_{}", e.name)).collect()
    }
    pub fn params(&self, api: &mut String, capture: &BTreeSet<String>) {
        for e in &self.0 {
            if Self::captured(e, capture) {
                writeln!(
                    api,
                    "    param ev_{}: {}",
                    e.name,
                    if matches!(e.kind, Kind::Date) {
                        "text"
                    } else {
                        "int"
                    }
                )
                .unwrap();
            }
        }
    }
    pub fn guards(&self, api: &mut String, capture: &BTreeSet<String>) {
        for e in &self.0 {
            if Self::captured(e, capture) {
                let rule = match e.kind {
                    Kind::Date => "date".into(),
                    Kind::Int(a, b, _) => format!("range {a} {b}"),
                };
                writeln!(api, "    require ev_{} {rule}", e.name).unwrap();
            }
        }
    }
    pub fn values(&self, capture: &BTreeSet<String>, args: &mut Vec<String>) -> String {
        self.0
            .iter()
            .map(|e| {
                if Self::captured(e, capture) {
                    args.push(format!("ev_{}", e.name));
                    ",?".into()
                } else {
                    match e.kind {
                        Kind::Int(_, _, n) => format!(",{n}"),
                        _ => unreachable!(),
                    }
                }
            })
            .collect()
    }
    pub fn body(&self, app: &mut String, capture: &BTreeSet<String>) {
        for e in &self.0 {
            if Self::captured(e, capture) {
                writeln!(app, "    body-field ev_{} ev_{}", e.name, e.name).unwrap();
            }
        }
    }
    pub fn inputs(&self, app: &mut String, capture: Option<&BTreeSet<String>>) {
        for e in &self.0 {
            if capture.is_none() || Self::captured(e, capture.unwrap()) {
                writeln!(
                    app,
                    "                        input ev_{} label \"{}\"",
                    e.name, e.label
                )
                .unwrap();
            }
        }
    }
    pub fn response(&self, app: &mut String) {
        for e in &self.0 {
            writeln!(
                app,
                "        ev_{} {}",
                e.name,
                if matches!(e.kind, Kind::Date) {
                    "text"
                } else {
                    "int32"
                }
            )
            .unwrap();
        }
    }
    pub fn display(&self, app: &mut String) {
        for e in &self.0 {
            writeln!(app,"                            row gap 8:\n                                paragraph \"{}:\"\n                                field ev_{}",e.label,e.name).unwrap();
        }
    }
    pub fn contract(&self) -> serde_json::Value {
        serde_json::json!(self
            .0
            .iter()
            .map(|e| serde_json::json!([e.name, e.kind]))
            .collect::<Vec<_>>())
    }
    pub fn numeric(&self, n: &str) -> Option<&str> {
        self.0
            .iter()
            .find(|e| e.name == n && matches!(e.kind, Kind::Int(..)))
            .map(|e| e.label.as_str())
    }
}
