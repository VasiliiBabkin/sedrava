//! A34: one declarative state machine with atomic, append-only transition history.
use super::events::Events;
use super::{error, label, name, Entity};
use crate::model::Result;
use serde_json::{json, Value};
use std::{collections::BTreeSet, fmt::Write};

struct Transition {
    name: String,
    label: String,
    from: String,
    to: String,
    capture: BTreeSet<String>,
}
pub(super) struct Workflow {
    pub target: String,
    initial: String,
    transitions: Vec<Transition>,
    pub events: Events,
}
impl Workflow {
    pub fn parse(src: &str, entities: &[Entity]) -> Result<Option<Self>> {
        let Some((_, tail)) = src.split_once("\nworkflow ") else {
            return Ok(None);
        };
        let mut lines = tail
            .lines()
            .enumerate()
            .filter(|(_, l)| !l.trim().is_empty() && !l.trim_start().starts_with('#'));
        let (_, head) = lines
            .next()
            .ok_or_else(|| error(1, "workflow target required"))?;
        let target = head
            .strip_suffix(':')
            .ok_or_else(|| error(1, "expected workflow ENTITY:"))?;
        if !entities.iter().any(|e| e.name == target) {
            return Err(error(1, "unknown workflow entity"));
        }
        let (_, initial) = lines
            .next()
            .ok_or_else(|| error(1, "initial state required"))?;
        let initial = initial
            .strip_prefix("    initial ")
            .filter(|s| name(s))
            .ok_or_else(|| error(1, "invalid initial state"))?;
        let mut transitions = Vec::new();
        let mut events = Events::default();
        let mut seen = BTreeSet::new();
        for (i, l) in lines {
            if let Some(raw) = l.strip_prefix("    event ") {
                if !transitions.is_empty() {
                    return Err(error(i + 1, "event fields must precede transitions"));
                }
                events.add(raw, i + 1)?;
                continue;
            }
            let raw = l
                .strip_prefix("    transition ")
                .ok_or_else(|| error(i + 1, "expected transition"))?;
            let (id, rest) = raw
                .split_once(' ')
                .ok_or_else(|| error(i + 1, "transition label required"))?;
            let (lbl, edge) = rest
                .rsplit_once(" from ")
                .ok_or_else(|| error(i + 1, "transition source required"))?;
            let (edge, capture) = if let Some((edge, raw)) = edge.split_once(" capture ") {
                (edge, events.capture(raw, i + 1)?)
            } else {
                (edge, BTreeSet::new())
            };
            let (from, to) = edge
                .split_once(" to ")
                .ok_or_else(|| error(i + 1, "transition destination required"))?;
            if !name(id)
                || matches!(id, "created" | "history")
                || !name(from)
                || !name(to)
                || !seen.insert(id)
                || transitions.len() >= 4
            {
                return Err(error(i + 1, "invalid/duplicate transition or budget"));
            }
            transitions.push(Transition {
                name: id.into(),
                label: label(lbl, i + 1)?,
                from: from.into(),
                to: to.into(),
                capture,
            });
        }
        if transitions.is_empty() {
            return Err(error(1, "workflow requires transitions"));
        }
        let mut reachable = BTreeSet::from([initial]);
        loop {
            let n = reachable.len();
            for t in &transitions {
                if reachable.contains(t.from.as_str()) {
                    reachable.insert(t.to.as_str());
                }
            }
            if reachable.len() == n {
                break;
            }
        }
        if transitions
            .iter()
            .any(|t| !reachable.contains(t.from.as_str()))
        {
            return Err(error(1, "unreachable transition source"));
        }
        Ok(Some(Self {
            target: target.into(),
            initial: initial.into(),
            transitions,
            events,
        }))
    }
    pub fn has_status(&self, s: &str) -> bool {
        self.initial == s || self.transitions.iter().any(|t| t.from == s || t.to == s)
    }
    pub fn states(&self, app: &mut String) {
        self.events.states(app);
        app.push_str("state wf_selected = \"\"\nstate wf_expected = \"\"\nstate wf_event = \"\"\nstate wf_note = \"\"\nstate wf_after = \"\"\n");
    }
    pub fn schema(&self, steps: &mut Vec<Value>) {
        let n = &self.target;
        for (name,sql) in [
            (format!("history_{n}"),format!("CREATE TABLE h_{n} (id TEXT PRIMARY KEY, subject TEXT, kind TEXT, beforestate TEXT, afterstate TEXT, note TEXT{});",self.events.ddl())),
            (format!("history_index_{n}"),format!("CREATE INDEX hi_{n} ON h_{n}(subject);")),
            (format!("history_fk_{n}"),format!("ALTER TABLE h_{n} ADD FOREIGN KEY (subject) REFERENCES d_{n}(id);"))
        ] {steps.push(json!({"version":steps.len()+1,"name":name,"sql":sql}));}
    }
    pub fn create(&self, api: &mut String, columns: &[String]) {
        let n = &self.target;
        let init = &self.initial;
        let sql = format!(
            "INSERT INTO d_{n} ({},w_status,w_revision) VALUES ({},'{init}',?)",
            columns.join(","),
            vec!["?"; columns.len()].join(",")
        );
        let mut using = columns.to_vec();
        using.push("id".into());
        let mut history_args = vec!["id".to_owned(), "id".to_owned()];
        let values = self.events.values(&BTreeSet::new(), &mut history_args);
        let hist=format!("INSERT INTO h_{n} (id,subject,kind,beforestate,afterstate,note{}) VALUES (?,?,'created','','{init}',''{values})",self.events.columns());
        writeln!(
            api,
            "    transaction {}",
            json!([{"sql":sql,"using":using},{"sql":hist,"using":history_args}])
        )
        .unwrap();
    }
    pub fn services(&self, app: &mut String, api: &mut String, extra_reads: &str) {
        let n = &self.target;
        for t in &self.transitions {
            let (id, from, to) = (&t.name, &t.from, &t.to);
            let update=format!("UPDATE d_{n} SET w_status='{to}',w_revision=? WHERE id=? AND w_revision=? AND w_status='{from}'");
            let mut args = vec!["event".into(), "subject".into(), "note".into()];
            let values = self.events.values(&t.capture, &mut args);
            let insert=format!("INSERT INTO h_{n} (id,subject,kind,beforestate,afterstate,note{}) VALUES (?,?,'{id}','{from}','{to}',?{values})",self.events.columns());
            writeln!(api,"route POST \"/workflow-{id}\":\n    param subject: text\n    param expected: text\n    param event: text\n    param note: text").unwrap();
            self.events.params(api, &t.capture);
            api.push_str("    require subject key\n    require expected key\n    require event key\n    require note length 1 256\n    require note nonblank\n");
            self.events.guards(api, &t.capture);
            writeln!(api,"    transaction {}",json!([{"sql":update,"using":["event","subject","expected"]},{"sql":insert,"using":args}])).unwrap();
            writeln!(app,"service wf_{id}:\n    origin self\n    path \"/workflow-{id}\"\n    method POST\n    auth session\n    idempotency true\n    refresh list_{n} wf_history{extra_reads}\n    body-field subject wf_selected\n    body-field expected wf_expected\n    body-field event wf_event\n    body-field note wf_note").unwrap();
            self.events.body(app, &t.capture);
            app.push_str("    response one:\n        kind text\n        affected int32\n        sequence int32\n        replayed bool\n");
        }
        writeln!(api,"route POST \"/workflow-history\":\n    param subject: text\n    param after: text\n    require subject key\n    require after length 0 128\n    query \"SELECT id,kind,beforestate,afterstate,note{} FROM h_{n} WHERE subject=? AND id>? ORDER BY id LIMIT 20\"",self.events.columns()).unwrap();
        app.push_str("service wf_history:\n    origin self\n    path \"/workflow-history\"\n    method POST\n    auth session\n    body-field subject wf_selected\n    body-field after wf_after\n    max-items 20\n    response sql-rows:\n        id text\n        kind text\n        beforestate text\n        afterstate text\n        note text\n");
        self.events.response(app);
    }
    pub fn pick(&self, app: &mut String) {
        app.push_str("                            row gap 8:\n                                paragraph \"Статус:\"\n                                field w_status\n                            row gap 8:\n                                paragraph \"Версия:\"\n                                field w_revision\n                            remote-pick \"Выбрать для операции\" bindings \"id:wf_selected w_revision:wf_expected\"\n");
    }
    pub fn panel(&self, app: &mut String) {
        app.push_str("                        heading \"Операции и история\" level 3\n                        paragraph \"Выберите запись из списка. После операции список обновится автоматически; выберите актуальную версию.\"\n                        input wf_selected label \"ID записи\" kind text\n                        input wf_expected label \"Ожидаемая версия\" kind text\n                        input wf_event label \"Новый ID события\" kind text\n                        input wf_note label \"Комментарий\" kind text\n");
        for t in &self.transitions {
            writeln!(app,"                        request \"{}\" service wf_{}\n                        remote wf_{}:\n                            field affected\n                            field sequence\n                            field replayed",t.label,t.name,t.name).unwrap();
        }
        app.push_str("                        input wf_after label \"История после ID\" kind text\n                        request \"Загрузить историю\" service wf_history\n                        remote wf_history:\n                            field id\n                            field kind\n                            field beforestate\n                            field afterstate\n                            field note\n");
        self.events.display(app);
    }
}
