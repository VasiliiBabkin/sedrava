//! A33: bounded declarative directory applications lowered to existing project DSLs.
mod workflow;
use crate::model::{Error, Result};
use serde_json::json;
use std::{collections::BTreeSet, fmt::Write};

#[derive(Debug, Clone)]
enum Ty {
    Text(u32, u32),
    Int(i32, i32),
    Bool,
    Ref(String),
}
#[derive(Debug)]
struct Field {
    name: String,
    label: String,
    ty: Ty,
}
#[derive(Debug)]
struct Entity {
    name: String,
    label: String,
    fields: Vec<Field>,
}

fn error(line: usize, message: &str) -> Error {
    Error(format!("E_DOMAIN line {line}: {message}"))
}
fn name(s: &str) -> bool {
    !s.is_empty()
        && s.len() <= 20
        && s.as_bytes()[0].is_ascii_lowercase()
        && s.bytes()
            .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit())
}
fn label(s: &str, line: usize) -> Result<String> {
    let v: String = serde_json::from_str(s).map_err(|_| error(line, "expected quoted label"))?;
    if v.trim().is_empty()
        || v.chars().count() > 80
        || v.chars().any(|c| c.is_control() || matches!(c, '"' | '\\'))
    {
        return Err(error(line, "invalid label"));
    }
    Ok(v)
}
fn parse(src: &str) -> Result<(String, Vec<Entity>)> {
    if src.len() > 16384 {
        return Err(error(1, "source budget"));
    }
    let mut lines = src
        .lines()
        .enumerate()
        .filter(|(_, l)| !l.trim().is_empty() && !l.trim_start().starts_with('#'));
    let (i, head) = lines
        .next()
        .ok_or_else(|| error(1, "expected application"))?;
    let title = label(
        head.strip_prefix("application ")
            .ok_or_else(|| error(i + 1, "expected application"))?,
        i + 1,
    )?;
    let (i, access) = lines
        .next()
        .ok_or_else(|| error(2, "explicit access required"))?;
    if access != "access session read write" {
        return Err(error(i + 1, "expected access session read write"));
    }
    let mut entities: Vec<Entity> = Vec::new();
    let mut names = BTreeSet::new();
    for (i, line) in lines {
        let n = i + 1;
        if let Some(rest) = line.strip_prefix("entity ") {
            let rest = rest
                .strip_suffix(':')
                .ok_or_else(|| error(n, "expected entity NAME LABEL:"))?;
            let (id, raw) = rest
                .split_once(' ')
                .ok_or_else(|| error(n, "expected entity label"))?;
            if !name(id) || !names.insert(id.to_owned()) || entities.len() >= 6 {
                return Err(error(n, "invalid/duplicate entity or entity budget"));
            }
            entities.push(Entity {
                name: id.into(),
                label: label(raw, n)?,
                fields: vec![],
            });
        } else {
            let rest = line
                .strip_prefix("    ")
                .ok_or_else(|| error(n, "expected entity or four spaces"))?;
            let (decl, raw) = rest
                .split_once(" label ")
                .ok_or_else(|| error(n, "expected field label"))?;
            let (id, ty) = decl
                .split_once(": ")
                .ok_or_else(|| error(n, "expected NAME: TYPE"))?;
            let e = entities
                .last_mut()
                .ok_or_else(|| error(n, "field outside entity"))?;
            if !name(id)
                || id == "id"
                || e.fields.len() >= 6
                || e.fields.iter().any(|f| f.name == id)
            {
                return Err(error(n, "invalid/duplicate field or field budget"));
            }
            let parts: Vec<_> = ty.split_ascii_whitespace().collect();
            let ty = match parts.as_slice() {
                ["text", a, b] => {
                    let a: u32 = a.parse().map_err(|_| error(n, "text minimum"))?;
                    let b: u32 = b.parse().map_err(|_| error(n, "text maximum"))?;
                    if a > b || b == 0 || b > 256 {
                        return Err(error(n, "text bounds"));
                    }
                    Ty::Text(a, b)
                }
                ["int", a, b] => {
                    let a: i32 = a.parse().map_err(|_| error(n, "integer minimum"))?;
                    let b: i32 = b.parse().map_err(|_| error(n, "integer maximum"))?;
                    if a > b {
                        return Err(error(n, "integer bounds"));
                    }
                    Ty::Int(a, b)
                }
                ["bool"] => Ty::Bool,
                ["ref", target] if name(target) && *target != e.name && names.contains(*target) => {
                    Ty::Ref((*target).into())
                }
                _ => {
                    return Err(error(
                        n,
                        "expected text MIN MAX, int MIN MAX, bool, or ref EARLIER_ENTITY",
                    ))
                }
            };
            e.fields.push(Field {
                name: id.into(),
                label: label(raw, n)?,
                ty,
            });
        }
    }
    if entities.is_empty() || entities.iter().any(|e| e.fields.is_empty()) {
        return Err(error(1, "entities must have 1..6 fields"));
    }
    Ok((title, entities))
}
fn sql_type(t: &Ty) -> &'static str {
    match t {
        Ty::Int(..) => "INT",
        Ty::Bool => "BOOL",
        _ => "TEXT",
    }
}
fn param_type(t: &Ty) -> &'static str {
    match t {
        Ty::Int(..) => "int",
        Ty::Bool => "bool",
        _ => "text",
    }
}
fn wire_type(t: &Ty) -> &'static str {
    match t {
        Ty::Int(..) => "int32",
        Ty::Bool => "bool",
        _ => "text",
    }
}
fn default(t: &Ty) -> String {
    match t {
        Ty::Int(a, b) => 0.clamp(*a, *b).to_string(),
        Ty::Bool => "false".into(),
        _ => "\"\"".into(),
    }
}
fn state(e: &Entity, f: &Field) -> String {
    format!("v_{}_{}", e.name, f.name)
}
fn col(f: &Field) -> String {
    format!("f_{}", f.name)
}
fn table(e: &Entity) -> String {
    format!("d_{}", e.name)
}
pub(super) fn lower(src: &str) -> Result<(Vec<u8>, Vec<u8>, Vec<u8>)> {
    if src.len() > 16384 {
        return Err(error(1, "source budget"));
    }
    let schema = src.split_once("\nworkflow ").map(|(s, _)| s).unwrap_or(src);
    let (title, entities) = parse(schema)?;
    let workflow = workflow::Workflow::parse(src, &entities)?;
    let mut app = format!(
        "webapp \"{title}\"\nstate section = \"{}\"\n",
        entities[0].name
    );
    let mut api = "database-api Domain\n".to_owned();
    let mut steps = Vec::new();
    for e in &entities {
        writeln!(
            app,
            "state id_{} = \"\"\nstate after_{} = \"\"",
            e.name, e.name
        )
        .unwrap();
        for f in &e.fields {
            writeln!(app, "state {} = {}", state(e, f), default(&f.ty)).unwrap();
        }
    }
    if let Some(w) = &workflow {
        w.states(&mut app);
    }
    for e in &entities {
        writeln!(app, "derive show_{} = section == \"{}\"", e.name, e.name).unwrap();
    }
    for e in &entities {
        writeln!(app, "action go_{}:\n    section = \"{}\"", e.name, e.name).unwrap();
    }
    for e in &entities {
        let t = table(e);
        let n = &e.name;
        let mut columns = vec!["id".to_owned()];
        columns.extend(e.fields.iter().map(col));
        let wf = workflow.as_ref().filter(|w| w.target == e.name);
        let mut ddl = vec!["id TEXT PRIMARY KEY".to_owned()];
        ddl.extend(
            e.fields
                .iter()
                .map(|f| format!("{} {}", col(f), sql_type(&f.ty))),
        );
        if wf.is_some() {
            ddl.extend(["w_status TEXT".into(), "w_revision TEXT".into()]);
        }
        steps.push(json!({"version":steps.len()+1,"name":format!("table_{n}"),"sql":format!("CREATE TABLE {t} ({});",ddl.join(", "))}));
        // Declaration order is migration order; append-only entities preserve the prefix.
        for f in &e.fields {
            if let Ty::Ref(parent) = &f.ty {
                let c = col(f);
                steps.push(json!({"version":steps.len()+1,"name":format!("index_{n}_{}",f.name),"sql":format!("CREATE INDEX ix_{n}_{} ON {t}({c});",f.name)}));
                steps.push(json!({"version":steps.len()+1,"name":format!("fk_{n}_{}",f.name),"sql":format!("ALTER TABLE {t} ADD FOREIGN KEY ({c}) REFERENCES d_{parent}(id);")}));
            }
        }
        writeln!(api,"route POST \"/domain-{n}-list\":\n    param after: text\n    require after length 0 128\n    query \"SELECT {} FROM {t} WHERE id>? ORDER BY id LIMIT 20\"",if wf.is_some(){format!("{},w_status,w_revision",columns.join(","))}else{columns.join(",")}).unwrap();
        writeln!(
            api,
            "route POST \"/domain-{n}-create\":\n    param id: text"
        )
        .unwrap();
        for f in &e.fields {
            writeln!(api, "    param {}: {}", col(f), param_type(&f.ty)).unwrap();
        }
        writeln!(api, "    require id key").unwrap();
        for f in &e.fields {
            let c = col(f);
            match &f.ty {
                Ty::Text(a, b) => {
                    writeln!(api, "    require {c} length {a} {b}").unwrap();
                    if *a > 0 {
                        writeln!(api, "    require {c} nonblank").unwrap();
                    }
                }
                Ty::Int(a, b) => writeln!(api, "    require {c} range {a} {b}").unwrap(),
                Ty::Ref(_) => writeln!(api, "    require {c} key").unwrap(),
                Ty::Bool => {}
            }
        }
        if let Some(w) = wf {
            w.create(&mut api, &columns);
        } else {
            writeln!(
                api,
                "    execute \"INSERT INTO {t} ({}) VALUES ({})\"",
                columns.join(","),
                vec!["?"; columns.len()].join(",")
            )
            .unwrap();
        }
        writeln!(app,"service list_{n}:\n    origin self\n    path \"/domain-{n}-list\"\n    method POST\n    auth session\n    body-field after after_{n}\n    max-items 20\n    response sql-rows:\n        id text").unwrap();
        for f in &e.fields {
            writeln!(app, "        {} {}", col(f), wire_type(&f.ty)).unwrap();
        }
        if wf.is_some() {
            app.push_str("        w_status text\n        w_revision text\n");
        }
        let refresh = if wf.is_some() {
            format!("list_{n} wf_history")
        } else {
            format!("list_{n}")
        };
        writeln!(app,"service create_{n}:\n    origin self\n    path \"/domain-{n}-create\"\n    method POST\n    auth session\n    idempotency true\n    refresh {refresh}\n    body-field id id_{n}").unwrap();
        for f in &e.fields {
            writeln!(app, "    body-field {} {}", col(f), state(e, f)).unwrap();
        }
        app.push_str("    response one:\n        kind text\n        affected int32\n        sequence int32\n        replayed bool\n");
    }
    if let Some(w) = &workflow {
        w.schema(&mut steps);
        w.services(&mut app, &mut api);
    }
    writeln!(app,"view main:\n    container max 1180 padding 24:\n        column gap 20:\n            heading \"{title}\"\n            session \"Ключ доступа\"\n            paragraph \"Локальное приложение. Откройте список; после записи открытые списки обновляются автоматически. Для следующей страницы укажите последний ID.\"\n            grid columns 3 md-columns 1 gap 8:").unwrap();
    for e in &entities {
        writeln!(
            app,
            "                button \"{}\" action go_{} variant secondary",
            e.label, e.name
        )
        .unwrap();
    }
    for e in &entities {
        let n = &e.name;
        writeln!(app,"            when show_{n}:\n                card:\n                    column gap 12:\n                        heading \"{}\" level 2\n                        input after_{n} label \"После ID\" kind text\n                        request \"Загрузить список\" service list_{n}\n                        remote list_{n}:\n                            row gap 8:\n                                paragraph \"ID:\"\n                                field id",e.label).unwrap();
        for f in &e.fields {
            writeln!(app,"                            row gap 8:\n                                paragraph \"{}:\"\n                                field {}",f.label,col(f)).unwrap();
        }
        if let Some(w) = workflow.as_ref().filter(|w| w.target == e.name) {
            w.pick(&mut app);
        }
        for child in &entities {
            for f in &child.fields {
                if matches!(&f.ty,Ty::Ref(parent) if parent==n) {
                    writeln!(app,"                            remote-pick \"{} · {}\" bindings \"id:{}\" action go_{}",child.label,f.label,state(child,f),child.name).unwrap();
                }
            }
        }
        writeln!(app,"                        heading \"Новая запись\" level 3\n                        input id_{n} label \"ID\" kind text").unwrap();
        for f in &e.fields {
            let widget = if matches!(f.ty, Ty::Bool) {
                "checkbox"
            } else {
                "input"
            };
            writeln!(
                app,
                "                        {widget} {} label \"{}\"",
                state(e, f),
                f.label
            )
            .unwrap();
        }
        writeln!(app,"                        request \"Сохранить\" service create_{n}\n                        remote create_{n}:\n                            field affected\n                            field sequence\n                            field replayed").unwrap();
        if let Some(w) = workflow.as_ref().filter(|w| w.target == e.name) {
            w.panel(&mut app);
        }
    }
    let mut migrations = serde_json::to_vec_pretty(&json!({"version":1,"steps":steps}))
        .map_err(|_| error(1, "migration encoding"))?;
    migrations.push(b'\n');
    Ok((app.into_bytes(), api.into_bytes(), migrations))
}
#[cfg(test)]
mod tests {
    use super::*;
    const GOOD:&str="application \"Test\"\naccess session read write\nentity client \"Clients\":\n    name: text 1 80 label \"Name\"\nentity site \"Sites\":\n    client: ref client label \"Client\"\n    floors: int 1 20 label \"Floors\"\n    active: bool label \"Active\"\n";
    #[test]
    fn deterministic_lowering_and_append_only_prefix() {
        let a = lower(GOOD).unwrap();
        assert_eq!(a, lower(GOOD).unwrap());
        let b = lower(
            &(GOOD.to_owned() + "entity asset \"Assets\":\n    site: ref site label \"Site\"\n"),
        )
        .unwrap();
        let steps = |x: &[u8]| {
            serde_json::from_slice::<serde_json::Value>(x).unwrap()["steps"]
                .as_array()
                .unwrap()
                .clone()
        };
        let aa = steps(&a.2);
        assert_eq!(aa.len(), 4);
        assert_eq!(aa, steps(&b.2)[..4]);
        assert!(crate::site::webapp::generate(std::str::from_utf8(&a.0).unwrap(), None).is_ok());
        assert!(crate::server::sql_api::parse(std::str::from_utf8(&a.1).unwrap()).is_ok());
    }
    #[test]
    fn workflow_contract() {
        let base=GOOD.to_owned()+"workflow site:\n    initial open\n    transition close \"Close\" from open to closed\n    transition reopen \"Reopen\" from closed to open\n";
        let a = lower(&base).unwrap();
        assert_eq!(a, lower(&base).unwrap());
        let api = std::str::from_utf8(&a.1).unwrap();
        assert!(api.contains("transaction "));
        assert!(!api.contains("route POST \"/workflow-history-create\""));
        assert!(crate::server::sql_api::parse(api).is_ok());
        assert!(crate::site::webapp::generate(std::str::from_utf8(&a.0).unwrap(), None).is_ok());
        for bad in [
            base.replace("workflow site:", "workflow missing:"),
            base.replace("transition close", "transition history"),
            base.replace("transition close", "transition created"),
            base.replace("transition reopen", "transition close"),
            base.replace("initial open", "initial unreachable"),
            base.replace("to closed", "to closed;"),
            base.clone() + "workflow site:\n    initial open\n",
        ] {
            assert!(lower(&bad).is_err(), "{bad}");
        }
    }

    #[test]
    fn strict_rejections() {
        for s in [
            GOOD.replace("access session read write", ""),
            GOOD.replace("ref client", "ref site"),
            GOOD.replace("ref client", "ref missing"),
            GOOD.replace("text 1 80", "text 80 1"),
            GOOD.replace("int 1 20", "int 20 1"),
            GOOD.replace("name:", "id:"),
            GOOD.replace("entity site", "entity client"),
            GOOD.replace("label \"Name\"", "label \"x\\ny\""),
            GOOD.replace("active: bool", "active: unknown"),
        ] {
            assert!(lower(&s).is_err(), "{s}");
        }
    }
}
