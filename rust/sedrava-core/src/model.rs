//! Typed values and expression IR for the experimental native Sedrava core.

use serde::{Serialize, Serializer};
use std::collections::{BTreeMap, BTreeSet};
use std::fmt;

pub const MAX_TEXT_SCALARS: usize = 1024;
pub const MAX_SOURCE_CHARS: usize = 100_000;
pub const MAX_AST_NODES: usize = 256;
pub const MAX_ACTION_STEPS: usize = 10_000;
pub const MAX_BLOCK_DEPTH: usize = 32;
pub const MAX_COLLECTIONS: usize = 16;
pub const MAX_RECORDS: usize = 16;
pub const MAX_SNAPSHOT_UTF16: usize = 200_000;

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub enum Kind {
    Int,
    Bool,
    Text,
    Record {
        name: String,
        fields: Vec<(String, Kind)>,
    },
    List {
        record: Box<Kind>,
        capacity: usize,
    },
    Function {
        parameters: Vec<Kind>,
        result: Box<Kind>,
    },
    /// Nominal immutable user error family. Not an OS fault or capability.
    Error {
        name: String,
        id: String,
        open: bool,
        variants: Vec<(String, Vec<(String, Kind)>)>,
    },
    /// Ephemeral typed Result. It cannot appear as a persistent state.
    Result {
        success: Box<Kind>,
        error: Box<Kind>,
    },
}

#[derive(Clone, Debug, PartialEq)]
pub struct ListItem {
    pub id: i32,
    pub record: Value,
}

#[derive(Clone, Debug, PartialEq)]
pub enum Value {
    Int(i32),
    Bool(bool),
    Text(String),
    Record {
        kind: Kind,
        fields: BTreeMap<String, Value>,
    },
    List {
        kind: Kind,
        items: Vec<ListItem>,
        next_id: i32,
    },
    Error {
        kind: Kind,
        variant: String,
        fields: BTreeMap<String, Value>,
    },
    Result {
        kind: Kind,
        ok: bool,
        value: Box<Value>,
    },
}

impl Value {
    pub fn kind(&self) -> Kind {
        match self {
            Self::Int(_) => Kind::Int,
            Self::Bool(_) => Kind::Bool,
            Self::Text(_) => Kind::Text,
            Self::Record { kind, .. }
            | Self::List { kind, .. }
            | Self::Error { kind, .. }
            | Self::Result { kind, .. } => kind.clone(),
        }
    }

    pub fn plain(&self) -> serde_json::Value {
        match self {
            Self::Int(v) => serde_json::json!(v),
            Self::Bool(v) => serde_json::json!(v),
            Self::Text(v) => serde_json::json!(v),
            Self::Record { fields, .. } => serde_json::Value::Object(
                fields
                    .iter()
                    .map(|(key, v)| (key.clone(), v.plain()))
                    .collect(),
            ),
            Self::Error {
                kind,
                variant,
                fields,
            } => {
                let Kind::Error { id, .. } = kind else {
                    unreachable!("validated error kind")
                };
                serde_json::json!({
                    "id":format!("{id}.{variant}"),
                    "variant":variant,
                    "fields":fields.iter().map(|(key,v)| (key.clone(),v.plain()))
                        .collect::<serde_json::Map<_,_>>(),
                })
            }
            Self::Result { ok, value, .. } => {
                if *ok {
                    serde_json::json!({"value":value.plain(),"code":"","error":null})
                } else {
                    serde_json::json!({"code":"","error":value.plain()})
                }
            }
            Self::List { items, next_id, .. } => {
                let rows: Vec<_> = items
                    .iter()
                    .map(|row| {
                        let mut data = match row.record.plain() {
                            serde_json::Value::Object(m) => m,
                            _ => unreachable!("typed collection rows contain records"),
                        };
                        data.insert("id".to_owned(), serde_json::json!(row.id));
                        serde_json::Value::Object(data)
                    })
                    .collect();
                serde_json::json!({"next_id":next_id,"items":rows})
            }
        }
    }
}

impl Serialize for Value {
    fn serialize<S: Serializer>(&self, serializer: S) -> std::result::Result<S::Ok, S::Error> {
        self.plain().serialize(serializer)
    }
}

pub fn validate(value: &Value, expected: &Kind) -> Result<()> {
    if &value.kind() != expected {
        return fail("Value type mismatch");
    }
    match (value, expected) {
        (Value::Text(v), Kind::Text) => ensure_text(v),
        (Value::Record { fields, .. }, Kind::Record { fields: schema, .. }) => {
            if fields.len() != schema.len() {
                return fail("Invalid record field count");
            }
            for (name, field_kind) in schema {
                let Some(v) = fields.get(name) else {
                    return fail("Missing record field");
                };
                validate(v, field_kind)?;
            }
            Ok(())
        }
        (Value::List { items, next_id, .. }, Kind::List { record, capacity }) => {
            if *next_id < 1 || items.len() > *capacity {
                return fail("Invalid bounded collection");
            }
            let mut ids = BTreeSet::new();
            for row in items {
                if row.id <= 0 || row.id >= *next_id || !ids.insert(row.id) {
                    return fail("Invalid or duplicate record identity");
                }
                validate(&row.record, record)?;
            }
            Ok(())
        }
        (
            Value::Error {
                variant, fields, ..
            },
            Kind::Error { variants, .. },
        ) => {
            let (_, schema) = variants
                .iter()
                .find(|(name, _)| name == variant)
                .ok_or_else(|| Error("Unknown nominal error variant".into()))?;
            if schema.len() != fields.len() {
                return fail("Invalid error field count");
            }
            for (name, kind) in schema {
                validate(
                    fields
                        .get(name)
                        .ok_or_else(|| Error("Missing error field".into()))?,
                    kind,
                )?;
            }
            Ok(())
        }
        (Value::Result { ok, value, .. }, Kind::Result { success, error }) => {
            validate(value, if *ok { success } else { error })
        }
        (Value::Int(_), Kind::Int) | (Value::Bool(_), Kind::Bool) => Ok(()),
        _ => fail("Type mismatch"),
    }
}

pub type State = BTreeMap<String, Value>;

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize)]
pub enum Unary {
    Neg,
    Not,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize)]
pub enum Binary {
    Add,
    Sub,
    Mul,
    Eq,
    Ne,
    Lt,
    Le,
    Gt,
    Ge,
    And,
    Or,
}

#[derive(Clone, Debug, PartialEq, Serialize)]
pub enum Expr {
    Int(i64),
    Bool(bool),
    Text(String),
    Ident(String),
    Attr(Box<Expr>, String),
    Conditional(Box<Expr>, Box<Expr>, Box<Expr>),
    Call {
        name: String,
        args: Vec<Expr>,
        kwargs: Vec<(String, Expr)>,
    },
    Unary(Unary, Box<Expr>),
    Binary(Binary, Box<Expr>, Box<Expr>),
}

#[derive(Clone, Debug, Serialize)]
pub enum Stmt {
    Assign(String, Expr),
    Let(String, Expr),
    Require(Expr),
    Branch(Expr, Vec<Stmt>, Vec<Stmt>),
    /// Bounded while: re-evaluate condition before each iteration; fail closed
    /// if the explicit iteration cap is reached while still true.
    While(Expr, u16, Vec<Stmt>),
    Match(Expr, Vec<MatchArm>),
}

#[derive(Clone, Debug, Serialize)]
pub enum MatchPattern {
    Ok(String),
    Variant {
        name: String,
        bindings: Vec<(String, String)>,
    },
    Fallback(String),
}

#[derive(Clone, Debug, Serialize)]
pub struct MatchArm {
    pub pattern: MatchPattern,
    pub body: Vec<Stmt>,
}

#[derive(Clone, Debug, Serialize)]
pub struct EmbeddedTest {
    pub name: String,
    pub actions: Vec<String>,
    pub expected: Expr,
}

#[derive(Clone, Debug, Serialize)]
pub struct PureFunction {
    pub name: String,
    pub parameters: Vec<(String, Kind)>,
    pub result: Kind,
    pub body: Expr,
    /// An opt-in upper bound for app-domain effects. Some(empty) is pure.
    /// This is neither a permission grant nor a complete UI/Host manifest.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub declared_effects: Option<BTreeSet<String>>,
}

#[derive(Clone, Debug, Serialize)]
pub enum Widget {
    Text(String),
    Value(String),
    Show {
        condition: String,
        label: String,
    },
    Input {
        state: String,
        label: String,
    },
    Button {
        label: String,
        action: String,
    },
    Display(Expr),
    List {
        collection: String,
        selected: String,
        options: Vec<(String, String)>,
    },
}

#[derive(Clone, Debug, Serialize)]
pub struct Screen {
    pub name: String,
    pub guard: Option<Expr>,
    pub commands: Vec<String>,
    pub widgets: Vec<Widget>,
    pub requires_navigation: bool,
}

#[derive(Clone, Debug, Serialize)]
pub struct Navigation {
    pub name: String,
    pub target: String,
    pub action: Option<String>,
}

/// Top-level declaration source position. Expression-level spans are not yet covered.
#[derive(Clone, Debug, Serialize)]
pub struct SourceSpan {
    pub line: usize,
    pub column: usize,
}

#[derive(Clone, Debug)]
pub struct Program {
    pub name: String,
    pub states: State,
    /// Declaration order is part of the Python 0.11 snapshot signature.
    pub state_order: Vec<String>,
    /// Partial source mapping for top-level declarations only.
    pub declaration_spans: BTreeMap<String, SourceSpan>,
    /// Names explicitly marked with \`persist\` in the source.
    pub persistent: BTreeSet<String>,
    pub types: BTreeMap<String, Kind>,
    pub derives: Vec<(String, Expr)>,
    pub functions: BTreeMap<String, PureFunction>,
    pub actions: BTreeMap<String, Vec<Stmt>>,
    pub rules: Vec<Expr>,
    pub tests: Vec<EmbeddedTest>,
    pub screens: BTreeMap<String, Screen>,
    pub navigation: BTreeMap<String, Navigation>,
    pub initial_screen: String,
    pub has_navigation: bool,
}

#[derive(Debug, Clone)]
pub struct Error(pub String);

impl fmt::Display for Error {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.0)
    }
}
impl std::error::Error for Error {}

pub type Result<T> = std::result::Result<T, Error>;

pub fn fail<T>(msg: impl Into<String>) -> Result<T> {
    Err(Error(msg.into()))
}

pub fn ensure_text(s: &str) -> Result<()> {
    if s.chars().count() > MAX_TEXT_SCALARS {
        return fail(format!(
            "Text exceeds {MAX_TEXT_SCALARS} Unicode scalar values"
        ));
    }
    Ok(())
}

pub fn check_i32(x: i64) -> Result<i32> {
    i32::try_from(x).map_err(|_| Error("Integer overflow: outside signed 32-bit range".into()))
}
