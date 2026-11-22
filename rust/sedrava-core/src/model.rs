//! AST and value representation for the intentionally restricted native core.

use serde::Serialize;
use std::collections::BTreeMap;
use std::fmt;

pub const MAX_TEXT_SCALARS: usize = 1024;
pub const MAX_SOURCE_CHARS: usize = 100_000;
pub const MAX_AST_NODES: usize = 256;
pub const MAX_ACTION_STEPS: usize = 10_000;
pub const MAX_BLOCK_DEPTH: usize = 32;

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
#[serde(untagged)]
pub enum Value {
    Int(i32),
    Bool(bool),
    Text(String),
}

impl Value {
    pub fn kind(&self) -> Kind {
        match self {
            Self::Int(_) => Kind::Int,
            Self::Bool(_) => Kind::Bool,
            Self::Text(_) => Kind::Text,
        }
    }
}

pub type State = BTreeMap<String, Value>;

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize)]
#[serde(rename_all = "lowercase")]
pub enum Kind {
    Int,
    Bool,
    Text,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum Unary {
    Neg,
    Not,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
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

#[derive(Clone, Debug, PartialEq)]
pub enum Expr {
    Int(i64),
    Bool(bool),
    Text(String),
    Ident(String),
    Unary(Unary, Box<Expr>),
    Binary(Binary, Box<Expr>, Box<Expr>),
}

#[derive(Clone, Debug)]
pub enum Stmt {
    Assign(String, Expr),
    Let(String, Expr),
    Require(Expr),
    Branch(Expr, Vec<Stmt>, Vec<Stmt>),
}

#[derive(Clone, Debug)]
pub struct EmbeddedTest {
    pub name: String,
    pub actions: Vec<String>,
    pub expected: Expr,
}

#[derive(Clone, Debug)]
pub struct Program {
    pub name: String,
    pub states: State,
    pub types: BTreeMap<String, Kind>,
    pub derives: Vec<(String, Expr)>,
    pub actions: BTreeMap<String, Vec<Stmt>>,
    pub rules: Vec<Expr>,
    pub tests: Vec<EmbeddedTest>,
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
        return fail(format!("Text exceeds {MAX_TEXT_SCALARS} Unicode scalar values"));
    }
    Ok(())
}

pub fn check_i32(x: i64) -> Result<i32> {
    i32::try_from(x).map_err(|_| Error("Integer overflow: outside signed 32-bit range".into()))
}
