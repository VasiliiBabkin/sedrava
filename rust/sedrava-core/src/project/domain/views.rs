//! A36: typed, bounded views and grouped counts; no raw SQL from declarations.
use super::workflow::Workflow;
use super::{col, default, error, label, name, param_type, wire_type, Entity, Ty};
use crate::model::Result;
use std::{collections::BTreeSet, fmt::Write};

enum Mode {
    Status(String),
    Filter(String, Ty),
    Count(String, Ty),
    History(Vec<(String, String)>),
}
pub(super) struct View {
    name: String,
    label: String,
    target: String,
    mode: Mode,
}

pub(super) fn split(src: &str) -> (&str, &str) {
    for (i, _) in src.match_indices('\n') {
        let rest = &src[i + 1..];
        if rest.starts_with("view ") || rest.starts_with("report ") {
            return (&src[..i], rest);
        }
    }
    (src, "")
}
fn field(entity: &Entity, id: &str, wf: Option<&Workflow>) -> Option<(String, Ty)> {
    if id == "status" && wf.is_some_and(|w| w.target == entity.name) {
        if entity.fields.iter().any(|f| f.name == "status") {
            return None;
        }
        return Some(("w_status".into(), Ty::Text(1, 20)));
    }
    entity
        .fields
        .iter()
        .find(|f| f.name == id)
        .map(|f| (col(f), f.ty.clone()))
}
impl View {
    pub fn parse(src: &str, entities: &[Entity], wf: Option<&Workflow>) -> Result<Vec<Self>> {
        let mut out = vec![];
        let mut seen = BTreeSet::new();
        for (i, line) in src
            .lines()
            .enumerate()
            .filter(|(_, l)| !l.trim().is_empty() && !l.trim_start().starts_with('#'))
        {
            let n = i + 1;
            let (report, rest) = if let Some(v) = line.strip_prefix("view ") {
                (false, v)
            } else if let Some(v) = line.strip_prefix("report ") {
                (true, v)
            } else {
                return Err(error(n, "expected view or report"));
            };
            let (id, rest) = rest
                .split_once(' ')
                .ok_or_else(|| error(n, "view name required"))?;
            let (caption, body) = rest
                .rsplit_once(" from ")
                .ok_or_else(|| error(n, "expected quoted label from ENTITY"))?;
            if !name(id) || !seen.insert(id) || out.len() >= 4 {
                return Err(error(n, "invalid/duplicate view or view budget"));
            }
            let words = body.split_ascii_whitespace().collect::<Vec<_>>();
            let Some(target) = words.first() else {
                return Err(error(n, "entity required"));
            };
            let e = entities
                .iter()
                .find(|e| e.name == *target)
                .ok_or_else(|| error(n, "unknown view entity"))?;
            let mode = match (report, words.as_slice()) {
                (false, [_, "where", "status", "=", status])
                    if !e.fields.iter().any(|f| f.name == "status")
                        && wf.is_some_and(|w| w.target == e.name && w.has_status(status)) =>
                {
                    Mode::Status((*status).into())
                }
                (false, [_, "filter", id]) => {
                    let (c, t) = field(e, id, wf)
                        .ok_or_else(|| error(n, "unknown or ambiguous filter field"))?;
                    Mode::Filter(c, t)
                }
                (true, [_, "history", "sum", fields @ ..]) => {
                    let w = wf
                        .filter(|w| w.target == e.name)
                        .ok_or_else(|| error(n, "history report requires workflow"))?;
                    if fields.is_empty()
                        || fields.len() > 3
                        || fields.iter().collect::<BTreeSet<_>>().len() != fields.len()
                    {
                        return Err(error(n, "history sum needs unique numeric event fields"));
                    }
                    let metrics = fields
                        .iter()
                        .map(|f| {
                            w.events
                                .numeric(f)
                                .map(|label| (f.to_string(), label.to_owned()))
                                .ok_or_else(|| error(n, "unknown numeric event field"))
                        })
                        .collect::<Result<Vec<_>>>()?;
                    Mode::History(metrics)
                }
                (true, [_, "group", id, "count"]) => {
                    let (c, t) = field(e, id, wf).ok_or_else(|| error(n, "unknown group field"))?;
                    if !(c == "w_status"
                        || matches!(t, Ty::Bool)
                        || matches!(t,Ty::Int(a,b) if i64::from(b)-i64::from(a)<20))
                    {
                        return Err(error(n,"group requires workflow status, bool or integer domain of at most 20 values"));
                    }
                    Mode::Count(c, t)
                }
                _ => {
                    return Err(error(
                        n,
                        "expected where status = STATE, filter FIELD, or group FIELD count",
                    ))
                }
            };
            out.push(Self {
                name: id.into(),
                label: label(caption, n)?,
                target: e.name.clone(),
                mode,
            });
        }
        Ok(out)
    }
    pub fn target(&self) -> &str {
        &self.target
    }
    fn service(&self) -> String {
        format!("vread_{}", self.name)
    }
    pub fn for_entity(views: &[Self], target: &str) -> String {
        views
            .iter()
            .filter(|v| v.target == target)
            .map(|v| format!(" {}", v.service()))
            .collect()
    }
    pub fn states(&self, app: &mut String) {
        let n = &self.name;
        if !matches!(self.mode, Mode::Count(..) | Mode::History(..)) {
            writeln!(app, "state va_{n} = \"\"").unwrap();
        }
        match &self.mode {
            Mode::Filter(c, t) => writeln!(
                app,
                "state vf_{n} = {}",
                if c == "w_status" {
                    "\"\"".into()
                } else {
                    default(t)
                }
            )
            .unwrap(),
            // POST uses a bounded fixed scalar to keep the existing read API body contract.
            Mode::Count(..) => writeln!(app, "state vq_{n} = \"\"").unwrap(),
            _ => {}
        }
    }
    pub fn action(&self, app: &mut String) {
        if matches!(self.mode, Mode::Filter(_, Ty::Ref(_))) {
            let n = &self.name;
            writeln!(
                app,
                "action filter_{n}:\n    section = \"{}\"\n    va_{n} = \"\"",
                self.target
            )
            .unwrap();
        }
    }
    pub fn parent_pick(&self, app: &mut String, parent: &str) {
        if matches!(&self.mode,Mode::Filter(_,Ty::Ref(p)) if p==parent) {
            let n = &self.name;
            writeln!(app,"                            remote-pick \"{}\" bindings \"id:vf_{n}\" action filter_{n}",self.label).unwrap();
        }
    }
    pub fn emit(&self, app: &mut String, api: &mut String, e: &Entity, wf: Option<&Workflow>) {
        let n = &self.name;
        let service = self.service();
        let table = super::table(e);
        let path = format!("/view-{n}");
        writeln!(api, "route POST \"{path}\":").unwrap();
        writeln!(app,"service {service}:\n    origin self\n    path \"{path}\"\n    method POST\n    auth session").unwrap();
        if let Mode::History(fields) = &self.mode {
            let cols = fields
                .iter()
                .map(|(f, _)| format!(",SUM(ev_{f}) AS total_{f}"))
                .collect::<String>();
            writeln!(api,"    param subject: text\n    require subject key\n    query \"SELECT subject,COUNT(*) AS total{cols} FROM h_{} WHERE subject=? GROUP BY subject LIMIT 1\"",e.name).unwrap();
            app.push_str("    body-field subject wf_selected\n    max-items 1\n    response sql-rows:\n        subject text\n        total int32\n");
            for (f, _) in fields {
                writeln!(app, "        total_{f} int32").unwrap();
            }
            return;
        }
        if let Mode::Count(c, t) = &self.mode {
            // Fixed empty cursor: all valid nonempty primary keys, not a visible page.
            // LIMIT 21 is a sentinel; the UI only accepts <=20 groups, never a silently truncated report.
            writeln!(api,"    param after: text\n    require after length 0 0\n    query \"SELECT {c},COUNT(*) AS total FROM {table} WHERE id>? GROUP BY {c} ORDER BY {c} LIMIT 21\"").unwrap();
            writeln!(app,"    body-field after vq_{n}\n    max-items 20\n    response sql-rows:\n        {c} {}\n        total int32",wire_type(t)).unwrap();
            return;
        }
        let mut cols = vec!["id".to_string()];
        cols.extend(e.fields.iter().map(col));
        if wf.is_some_and(|w| w.target == e.name) {
            cols.extend(["w_status".into(), "w_revision".into()]);
        }
        writeln!(api, "    param after: text").unwrap();
        if let Mode::Filter(_, t) = &self.mode {
            writeln!(api, "    param value: {}", param_type(t)).unwrap();
        }
        writeln!(api, "    require after length 0 128").unwrap();
        let clause = match &self.mode {
            Mode::Status(s) => format!("w_status='{s}'"),
            Mode::Filter(c, t) => {
                match t {
                    Ty::Text(a, b) => {
                        writeln!(api, "    require value length {a} {b}").unwrap();
                        if *a > 0 {
                            writeln!(api, "    require value nonblank").unwrap();
                        }
                    }
                    Ty::Int(a, b) => writeln!(api, "    require value range {a} {b}").unwrap(),
                    Ty::Ref(_) => writeln!(api, "    require value key").unwrap(),
                    Ty::Bool => {}
                }
                format!("{c}=?")
            }
            _ => unreachable!(),
        };
        writeln!(
            api,
            "    query \"SELECT {} FROM {table} WHERE id>? AND {clause} ORDER BY id LIMIT 20\"",
            cols.join(",")
        )
        .unwrap();
        writeln!(app, "    body-field after va_{n}").unwrap();
        if matches!(self.mode, Mode::Filter(..)) {
            writeln!(app, "    body-field value vf_{n}").unwrap();
        }
        app.push_str("    max-items 20\n    response sql-rows:\n        id text\n");
        for f in &e.fields {
            writeln!(app, "        {} {}", col(f), wire_type(&f.ty)).unwrap();
        }
        if wf.is_some_and(|w| w.target == e.name) {
            app.push_str("        w_status text\n        w_revision text\n");
        }
    }
    pub fn panel(&self, app: &mut String, e: &Entity, wf: Option<&Workflow>) {
        let n = &self.name;
        let service = self.service();
        writeln!(
            app,
            "                        heading \"{}\" level 3",
            self.label
        )
        .unwrap();
        if let Mode::Filter(c, t) = &self.mode {
            let caption = if c == "w_status" {
                "Статус"
            } else {
                &e.fields.iter().find(|f| col(f) == *c).unwrap().label
            };
            let widget = if matches!(t, Ty::Bool) {
                "checkbox"
            } else {
                "input"
            };
            writeln!(
                app,
                "                        {widget} vf_{n} label \"{}\"",
                caption
            )
            .unwrap();
        }
        if !matches!(self.mode, Mode::Count(..) | Mode::History(..)) {
            writeln!(
                app,
                "                        input va_{n} label \"После ID\" kind text"
            )
            .unwrap();
        }
        writeln!(app,"                        request \"Обновить\" service {service}\n                        remote {service}:").unwrap();
        if let Mode::History(fields) = &self.mode {
            app.push_str("                            row gap 8:\n                                paragraph \"ID записи:\"\n                                field subject\n                            row gap 8:\n                                paragraph \"Событий:\"\n                                field total\n");
            for (f, label) in fields {
                writeln!(app,"                            row gap 8:\n                                paragraph \"{label} — итог:\"\n                                field total_{f}").unwrap();
            }
        } else if let Mode::Count(c, _) = &self.mode {
            let label = if c == "w_status" {
                "Статус"
            } else {
                &e.fields.iter().find(|f| col(f) == *c).unwrap().label
            };
            writeln!(app,"                            row gap 8:\n                                paragraph \"{label}:\"\n                                field {c}\n                            row gap 8:\n                                paragraph \"Количество:\"\n                                field total").unwrap();
        } else {
            app.push_str("                            row gap 8:\n                                paragraph \"ID:\"\n                                field id\n");
            for f in &e.fields {
                writeln!(app,"                            row gap 8:\n                                paragraph \"{}:\"\n                                field {}",f.label,col(f)).unwrap();
            }
            if let Some(w) = wf.filter(|w| w.target == e.name) {
                w.pick(app);
            }
        }
    }
}
