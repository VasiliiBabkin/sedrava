//! Experimental trusted local Host A1 file effects and A3 execution outcomes.
use crate::host_json::{self, Document, Key};
use crate::{
    expr,
    model::{ensure_text, fail, Error, Expr, Kind, Result, State, Value, MAX_SOURCE_CHARS},
};
use regex::Regex;
use rustix::{
    fd::{AsFd, OwnedFd},
    fs::{self, AtFlags, FileType, Mode, OFlags},
    io::Errno,
};
use serde::Serialize;
use serde_json::Value as JsonValue;
use std::{
    collections::{BTreeMap, BTreeSet},
    io::{Read, Write},
    path::PathBuf,
    sync::{
        atomic::{AtomicU64, Ordering},
        LazyLock,
    },
};

const MAX_FILE_BYTES: usize = 4096;
const MAX_STEPS: usize = 64;

enum Step {
    Let(String, Expr),
    Read(String, Expr),
    ReadJson(String, Expr),
    ListDir(String, Expr),
    JsonGet(String, String, Expr, JsonTarget),
    JsonCount(String, String),
    JsonObject(String),
    JsonSet(String, String, JsonInput),
    Write(Expr, Expr),
    WriteJson(Expr, String),
    Mkdir(Expr),
    Rmdir(Expr),
    Emit(Expr),
    EmitJson(String),
}

enum JsonTarget {
    Text,
    Int,
    Bool,
    Json,
}
enum JsonInput {
    Scalar(Expr),
    Document(String),
}

enum Pending {
    Write(String, String),
    Mkdir(String),
    Rmdir(String),
}
impl Pending {
    fn path(&self) -> &str {
        match self {
            Self::Write(p, _) | Self::Mkdir(p) | Self::Rmdir(p) => p,
        }
    }
}

pub struct HostProgram {
    arguments: BTreeMap<String, Kind>,
    types: BTreeMap<String, Kind>,
    steps: Vec<Step>,
    json_arguments: BTreeSet<String>,
    json_bindings: BTreeSet<String>,
    reads: bool,
    lists: bool,
    writes: bool,
    mkdirs: bool,
    rmdirs: bool,
}

pub struct Policy {
    pub root: PathBuf,
    pub trusted: bool,
    pub allow_read: bool,
    pub allow_write: bool,
    pub allow_list: bool,
    pub allow_mkdir: bool,
    pub allow_rmdir: bool,
    pub read_scope: String,
    pub write_scope: String,
    pub list_scope: String,
}

impl Policy {
    pub fn new(root: PathBuf) -> Self {
        Self {
            root,
            trusted: false,
            allow_read: false,
            allow_write: false,
            allow_list: false,
            allow_mkdir: false,
            allow_rmdir: false,
            read_scope: ".".into(),
            write_scope: ".".into(),
            list_scope: ".".into(),
        }
    }
}

#[derive(Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum Status {
    Success,
    Failed,
    Fault,
    Rejected,
}

#[derive(Clone, Copy, Serialize)]
#[serde(rename_all = "snake_case")]
enum Phase {
    Setup,
    Execute,
    Commit,
}

#[derive(Serialize)]
#[serde(rename_all = "snake_case")]
enum CommitState {
    NotStarted,
    NotApplicable,
    Committed,
    Unknown,
}

#[derive(Clone, Copy, Serialize)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
enum Code {
    ConfigurationRejected,
    PolicyViolation,
    EngineFault,
    FileNotFound,
    PermissionDenied,
    FileExists,
    InvalidEncoding,
    InvalidPath,
    InvalidJson,
    DirectoryNotEmpty,
    ResourceTooLarge,
    TextTooLong,
    #[serde(rename = "IO_FAILURE")]
    IoFailure,
    #[serde(rename = "IO_FAULT")]
    IoFault,
}

#[derive(Serialize)]
struct Failure {
    code: Code,
    retryable: bool,
}

#[derive(Serialize)]
pub struct Outcome {
    protocol: &'static str,
    pub status: Status,
    phase: Phase,
    commit_state: CommitState,
    result: Option<serde_json::Value>,
    error: Option<Failure>,
}

impl Outcome {
    pub fn rejected() -> Self {
        Self::failure(Phase::Setup, Code::ConfigurationRejected)
    }

    fn failure(phase: Phase, code: Code) -> Self {
        let status = match code {
            Code::ConfigurationRejected => Status::Rejected,
            Code::PolicyViolation | Code::EngineFault | Code::IoFault => Status::Fault,
            _ => Status::Failed,
        };
        Self {
            protocol: "sedrava.host.execution.v1",
            status,
            phase,
            commit_state: if matches!(phase, Phase::Commit) {
                CommitState::Unknown
            } else {
                CommitState::NotStarted
            },
            result: None,
            error: Some(Failure {
                code,
                retryable: false,
            }),
        }
    }

    fn success(result: JsonValue, written: Option<String>) -> Self {
        let committed = written.is_some();
        Self {
            protocol: "sedrava.host.execution.v1",
            status: Status::Success,
            phase: if committed {
                Phase::Commit
            } else {
                Phase::Execute
            },
            commit_state: if committed {
                CommitState::Committed
            } else {
                CommitState::NotApplicable
            },
            result: Some(serde_json::json!({"result": result, "written": written})),
            error: None,
        }
    }
}

fn checked(
    raw: &str,
    types: &BTreeMap<String, Kind>,
    expected: Option<Kind>,
) -> Result<(Expr, Kind)> {
    let expr = expr::parse(raw)?;
    let kind = expr::infer(&expr, types)?;
    if expected.is_some_and(|expected| expected != kind) {
        return fail("Host expression type mismatch");
    }
    Ok((expr, kind))
}

fn write_parts(raw: &str) -> Option<(&str, &str)> {
    let mut quoted = false;
    let mut escaped = false;
    for (index, ch) in raw.char_indices() {
        if !quoted && raw[index..].starts_with(" = ") {
            return Some((&raw[..index], &raw[index + 3..]));
        }
        if escaped {
            escaped = false;
        } else if ch == '"' {
            quoted = !quoted;
        } else if quoted && ch == '\\' {
            escaped = true;
        }
    }
    None
}

fn text_expr(raw: &str, types: &BTreeMap<String, Kind>) -> Result<Expr> {
    checked(raw, types, Some(Kind::Text)).map(|(expr, _)| expr)
}

fn path_expr(raw: &str, types: &BTreeMap<String, Kind>) -> Result<Expr> {
    let expr = text_expr(raw, types)?;
    if let Expr::Text(value) = &expr {
        path_parts(value).map_err(|_| Error("Invalid literal Host path".into()))?;
    }
    Ok(expr)
}

pub fn parse(source: &str) -> Result<HostProgram> {
    static BINDING: LazyLock<Regex> =
        LazyLock::new(|| Regex::new(r"^[A-Za-z][A-Za-z0-9_]{0,63}$").unwrap());
    if source.chars().count() > MAX_SOURCE_CHARS {
        return fail("Host source exceeds size limit");
    }
    let mut lines = source
        .lines()
        .enumerate()
        .filter(|(_, raw)| !raw.trim().is_empty() && !raw.trim_start().starts_with('#'));
    let (_, header) = lines
        .next()
        .ok_or_else(|| Error("Missing Host document".into()))?;
    let title = header
        .strip_prefix("host ")
        .ok_or_else(|| Error("Expected host declaration".into()))?;
    if !matches!(expr::parse(title)?, Expr::Text(_)) {
        return fail("Expected quoted Host title");
    }
    let mut program = HostProgram {
        arguments: BTreeMap::new(),
        types: BTreeMap::new(),
        steps: Vec::new(),
        json_arguments: BTreeSet::new(),
        json_bindings: BTreeSet::new(),
        reads: false,
        lists: false,
        writes: false,
        mkdirs: false,
        rmdirs: false,
    };
    let mut read_count = 0;
    for (index, (line, raw)) in lines.enumerate() {
        let invalid = |reason| Error(format!("Line {}: {reason}", line + 1));
        if index >= MAX_STEPS
            || raw.starts_with(char::is_whitespace)
            || matches!(
                program.steps.last(),
                Some(Step::Emit(_) | Step::EmitJson(_))
            )
        {
            return Err(invalid(
                "Host statement limit, indentation or final emit violated",
            ));
        }
        let raw = raw.trim_end();
        let (keyword, rest) = raw
            .split_once(' ')
            .ok_or_else(|| invalid("Expected Host statement"))?;
        let binding = |value: &str| {
            if BINDING.is_match(value)
                && !program.types.contains_key(value)
                && !program.json_bindings.contains(value)
                && matches!(expr::parse(value), Ok(Expr::Ident(_)))
            {
                Ok(value.to_owned())
            } else {
                Err(invalid("Invalid or duplicate Host binding"))
            }
        };
        let step = match keyword {
            "arg"
                if program.steps.is_empty()
                    && program.arguments.len() + program.json_arguments.len() < 16 =>
            {
                let (key, kind) = rest
                    .split_once(": ")
                    .ok_or_else(|| invalid("Expected a typed Host argument"))?;
                let key = binding(key)?;
                if kind == "json" {
                    program.json_arguments.insert(key.clone());
                    program.json_bindings.insert(key);
                    continue;
                }
                let kind = match kind {
                    "text" => Kind::Text,
                    "int" => Kind::Int,
                    "bool" => Kind::Bool,
                    _ => return Err(invalid("Unsupported Host argument type")),
                };
                program.arguments.insert(key.clone(), kind.clone());
                program.types.insert(key, kind);
                continue;
            }
            "let" => {
                let (key, value) = rest
                    .split_once(" = ")
                    .ok_or_else(|| invalid("Expected Host let binding"))?;
                let key = binding(key)?;
                let (value, kind) = checked(value, &program.types, None)?;
                program.types.insert(key.clone(), kind);
                Step::Let(key, value)
            }
            "read" if read_count < 8 => {
                let (key, path) = rest
                    .split_once(" from ")
                    .ok_or_else(|| invalid("Expected read name from path"))?;
                let key = binding(key)?;
                let path = path_expr(path, &program.types)?;
                read_count += 1;
                program.reads = true;
                program.types.insert(key.clone(), Kind::Text);
                Step::Read(key, path)
            }
            "read_json" if read_count < 8 => {
                let (key, path) = rest
                    .split_once(" from ")
                    .ok_or_else(|| invalid("Expected read_json name from path"))?;
                let key = binding(key)?;
                let path = path_expr(path, &program.types)?;
                read_count += 1;
                program.reads = true;
                program.json_bindings.insert(key.clone());
                Step::ReadJson(key, path)
            }
            "list_dir" if read_count < 8 => {
                let (key, path) = rest
                    .split_once(" from ")
                    .ok_or_else(|| invalid("Expected list_dir name from path"))?;
                let key = binding(key)?;
                let path = if rest.ends_with(" from \".\"") {
                    text_expr(path, &program.types)?
                } else {
                    path_expr(path, &program.types)?
                };
                read_count += 1;
                program.lists = true;
                program.json_bindings.insert(key.clone());
                Step::ListDir(key, path)
            }
            kind if kind.starts_with("json_get_") => {
                let target_kind = match kind {
                    "json_get_text" => JsonTarget::Text,
                    "json_get_int" => JsonTarget::Int,
                    "json_get_bool" => JsonTarget::Bool,
                    "json_get_json" => JsonTarget::Json,
                    _ => return Err(invalid("Unsupported JSON getter type")),
                };
                let (target, source_key) = rest
                    .split_once(" from ")
                    .ok_or_else(|| invalid("Expected json_get target from source at key"))?;
                let (source, key) = source_key
                    .split_once(" at ")
                    .ok_or_else(|| invalid("Expected JSON lookup key"))?;
                let target = binding(target)?;
                if !program.json_bindings.contains(source) {
                    return Err(invalid("JSON source document is missing"));
                }
                let (key_expr, key_kind) = checked(key, &program.types, None)?;
                if !matches!(key_kind, Kind::Int | Kind::Text) {
                    return Err(invalid("JSON getter needs int or text key"));
                }
                match target_kind {
                    JsonTarget::Json => {
                        program.json_bindings.insert(target.clone());
                    }
                    JsonTarget::Text => {
                        program.types.insert(target.clone(), Kind::Text);
                    }
                    JsonTarget::Int => {
                        program.types.insert(target.clone(), Kind::Int);
                    }
                    JsonTarget::Bool => {
                        program.types.insert(target.clone(), Kind::Bool);
                    }
                }
                Step::JsonGet(target, source.to_owned(), key_expr, target_kind)
            }
            "json_count" => {
                let (target, source) = rest
                    .split_once(" from ")
                    .ok_or_else(|| invalid("Expected json_count name from document"))?;
                let target = binding(target)?;
                if !program.json_bindings.contains(source) {
                    return Err(invalid("JSON count requires a document"));
                }
                program.types.insert(target.clone(), Kind::Int);
                Step::JsonCount(target, source.to_owned())
            }
            "json_object" => {
                let target = binding(rest)?;
                program.json_bindings.insert(target.clone());
                Step::JsonObject(target)
            }
            "json_set" => {
                let (left, value) = rest
                    .split_once(" = ")
                    .ok_or_else(|| invalid("Expected json_set object.field = value"))?;
                let (target, field) = left
                    .split_once('.')
                    .ok_or_else(|| invalid("Expected JSON object.field"))?;
                if !program.json_bindings.contains(target) || !BINDING.is_match(field) {
                    return Err(invalid(
                        "JSON field assignment requires an object and valid key",
                    ));
                }
                let value = if program.json_bindings.contains(value) {
                    JsonInput::Document(value.to_owned())
                } else {
                    let (expr, kind) = checked(value, &program.types, None)?;
                    if !matches!(kind, Kind::Text | Kind::Int | Kind::Bool) {
                        return Err(invalid("JSON field must be a scalar or JSON document"));
                    }
                    JsonInput::Scalar(expr)
                };
                Step::JsonSet(target.to_owned(), field.to_owned(), value)
            }
            "write_json" if !program.writes => {
                let (path, document) = write_parts(rest)
                    .ok_or_else(|| invalid("Expected write_json path = document"))?;
                if !program.json_bindings.contains(document) {
                    return Err(invalid("JSON write requires a document"));
                }
                program.writes = true;
                Step::WriteJson(path_expr(path, &program.types)?, document.to_owned())
            }
            "mkdir" if !program.writes => {
                program.writes = true;
                program.mkdirs = true;
                Step::Mkdir(path_expr(rest, &program.types)?)
            }
            "rmdir" if !program.writes => {
                program.writes = true;
                program.rmdirs = true;
                Step::Rmdir(path_expr(rest, &program.types)?)
            }
            "emit_json" => {
                if !program.json_bindings.contains(rest) {
                    return Err(invalid("emit_json requires a JSON document"));
                }
                Step::EmitJson(rest.to_owned())
            }
            "write" if !program.writes => {
                let (path, value) =
                    write_parts(rest).ok_or_else(|| invalid("Expected write path = text"))?;
                program.writes = true;
                Step::Write(
                    path_expr(path, &program.types)?,
                    text_expr(value, &program.types)?,
                )
            }
            "emit" => Step::Emit(checked(rest, &program.types, None)?.0),
            _ => return Err(invalid("Unsupported or excessive native Host instruction")),
        };
        program.steps.push(step);
    }
    if !matches!(
        program.steps.last(),
        Some(Step::Emit(_) | Step::EmitJson(_))
    ) {
        return fail("Host requires a final emit or emit_json");
    }
    Ok(program)
}

fn arguments(
    program: &HostProgram,
    supplied: &[String],
) -> Option<(State, BTreeMap<String, Document>)> {
    static INTEGER: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"^-?(0|[1-9][0-9]*)$").unwrap());
    if supplied.len() != program.arguments.len() + program.json_arguments.len() {
        return None;
    }
    let mut values = State::new();
    let mut documents = BTreeMap::new();
    for argument in supplied {
        let (key, raw) = argument.split_once('=')?;
        if program.json_arguments.contains(key) {
            let value = host_json::parse(raw).ok()?;
            if documents.insert(key.to_owned(), value).is_some() {
                return None;
            }
            continue;
        }
        let value = match program.arguments.get(key)? {
            Kind::Text if ensure_text(raw).is_ok() => Value::Text(raw.into()),
            Kind::Int if raw.len() <= 11 && INTEGER.is_match(raw) => Value::Int(raw.parse().ok()?),
            Kind::Bool if matches!(raw, "true" | "false") => Value::Bool(raw == "true"),
            _ => return None,
        };
        if values.insert(key.to_owned(), value).is_some() {
            return None;
        }
    }
    Some((values, documents))
}

fn path_parts(path: &str) -> std::result::Result<Vec<&str>, Code> {
    if path.chars().count() > 240 || path.contains('\\') || path.chars().any(char::is_control) {
        return Err(Code::InvalidPath);
    }
    let parts: Vec<_> = path.split('/').collect();
    if parts
        .iter()
        .any(|part| matches!(*part, "" | "." | "..") || part.len() > 120)
    {
        return Err(Code::InvalidPath);
    }
    Ok(parts)
}

fn classify(err: Errno) -> Code {
    match err {
        Errno::LOOP | Errno::NOTDIR => Code::PolicyViolation,
        Errno::NOENT => Code::FileNotFound,
        Errno::ACCESS | Errno::PERM => Code::PermissionDenied,
        Errno::EXIST => Code::FileExists,
        Errno::NOTEMPTY => Code::DirectoryNotEmpty,
        Errno::IO | Errno::NOSPC | Errno::INTR | Errno::STALE | Errno::AGAIN => Code::IoFailure,
        _ => Code::IoFault,
    }
}

const OPEN: OFlags = OFlags::RDONLY
    .union(OFlags::NOFOLLOW)
    .union(OFlags::CLOEXEC)
    .union(OFlags::NONBLOCK);

fn relative_dir(root: impl AsFd, parts: &[&str]) -> std::result::Result<OwnedFd, Code> {
    let mut dir = rustix::io::fcntl_dupfd_cloexec(root, 0).map_err(classify)?;
    for part in parts {
        dir = fs::openat(&dir, *part, OPEN | OFlags::DIRECTORY, Mode::empty()).map_err(classify)?;
    }
    Ok(dir)
}

fn scope(root: impl AsFd, relative: &str) -> std::result::Result<OwnedFd, Code> {
    if relative == "." {
        relative_dir(root, &[])
    } else {
        relative_dir(root, &path_parts(relative)?)
    }
}

fn regular(stat: fs::Stat) -> std::result::Result<(), Code> {
    if FileType::from_raw_mode(stat.st_mode) != FileType::RegularFile || stat.st_nlink != 1 {
        return Err(Code::PolicyViolation);
    }
    Ok(())
}

fn read_raw(root: &OwnedFd, path: &str) -> std::result::Result<Vec<u8>, Code> {
    let parts = path_parts(path)?;
    let (name, parents) = parts.split_last().unwrap();
    let parent = relative_dir(root, parents)?;
    // Directory-descriptor-relative access, no symlinks and no multiply linked files.
    regular(fs::statat(&parent, *name, AtFlags::SYMLINK_NOFOLLOW).map_err(classify)?)?;
    let file = fs::openat(&parent, *name, OPEN, Mode::empty()).map_err(classify)?;
    regular(fs::fstat(&file).map_err(classify)?)?;
    let mut bytes = Vec::new();
    std::fs::File::from(file)
        .take(MAX_FILE_BYTES as u64 + 1)
        .read_to_end(&mut bytes)
        .map_err(|err| {
            err.raw_os_error()
                .map_or(Code::IoFault, |raw| classify(Errno::from_raw_os_error(raw)))
        })?;
    if bytes.len() > MAX_FILE_BYTES {
        return Err(Code::ResourceTooLarge);
    }
    Ok(bytes)
}

fn read(root: &OwnedFd, path: &str) -> std::result::Result<Value, Code> {
    let value = String::from_utf8(read_raw(root, path)?).map_err(|_| Code::InvalidEncoding)?;
    ensure_text(&value).map_err(|_| Code::TextTooLong)?;
    Ok(Value::Text(value))
}

fn read_json(root: &OwnedFd, path: &str) -> std::result::Result<Document, Code> {
    let raw = String::from_utf8(read_raw(root, path)?).map_err(|_| Code::InvalidEncoding)?;
    host_json::parse(&raw).map_err(|_| Code::InvalidJson)
}

fn list_dir(root: &OwnedFd, path: &str) -> std::result::Result<Document, Code> {
    let subdir = if path == "." {
        relative_dir(root, &[])?
    } else {
        relative_dir(root, &path_parts(path)?)?
    };
    let entries = fs::Dir::read_from(&subdir).map_err(classify)?;
    let mut rows = Vec::new();
    for entry in entries {
        let entry = entry.map_err(classify)?;
        let name = entry.file_name().to_str().map_err(|_| Code::InvalidPath)?;
        if matches!(name, "." | "..") {
            continue;
        }
        path_parts(name)?;
        if rows.len() >= 32 {
            return Err(Code::ResourceTooLarge);
        }
        let info = fs::statat(&subdir, name, AtFlags::SYMLINK_NOFOLLOW).map_err(classify)?;
        let kind = match FileType::from_raw_mode(info.st_mode) {
            FileType::Directory => "directory",
            FileType::RegularFile => {
                regular(info)?;
                "file"
            }
            _ => return Err(Code::PolicyViolation),
        };
        rows.push(serde_json::json!({"name":name,"kind":kind}));
    }
    rows.sort_by(|a, b| a["name"].as_str().cmp(&b["name"].as_str()));
    host_json::validate(JsonValue::Array(rows)).map_err(|_| Code::ResourceTooLarge)
}

fn mkdir(root: &OwnedFd, path: &str) -> std::result::Result<(), Code> {
    let parts = path_parts(path)?;
    let (name, parents) = parts.split_last().unwrap();
    let parent = relative_dir(root, parents)?;
    fs::mkdirat(&parent, *name, Mode::RWXU).map_err(classify)?;
    fs::fsync(&parent).map_err(classify)
}

fn rmdir(root: &OwnedFd, path: &str) -> std::result::Result<(), Code> {
    let parts = path_parts(path)?;
    let (name, parents) = parts.split_last().unwrap();
    let parent = relative_dir(root, parents)?;
    let info = fs::statat(&parent, *name, AtFlags::SYMLINK_NOFOLLOW).map_err(classify)?;
    if FileType::from_raw_mode(info.st_mode) != FileType::Directory {
        return Err(Code::PolicyViolation);
    }
    fs::unlinkat(&parent, *name, AtFlags::REMOVEDIR).map_err(classify)?;
    fs::fsync(&parent).map_err(classify)
}

fn write(root: &OwnedFd, path: &str, data: &str) -> std::result::Result<(), Code> {
    static NEXT: AtomicU64 = AtomicU64::new(0);
    let parts = path_parts(path)?;
    let (name, parents) = parts.split_last().unwrap();
    let parent = relative_dir(root, parents)?;
    match fs::statat(&parent, *name, AtFlags::SYMLINK_NOFOLLOW) {
        Ok(stat) => {
            regular(stat)?;
            return Err(Code::FileExists);
        }
        Err(Errno::NOENT) => {}
        Err(err) => return Err(classify(err)),
    }
    let temp = format!(
        ".sedrava-host-{}-{}",
        std::process::id(),
        NEXT.fetch_add(1, Ordering::Relaxed)
    );
    let flags = OFlags::WRONLY | OFlags::CREATE | OFlags::EXCL | OFlags::NOFOLLOW | OFlags::CLOEXEC;
    let fd =
        fs::openat(&parent, temp.as_str(), flags, Mode::RUSR | Mode::WUSR).map_err(classify)?;
    let mut file = std::fs::File::from(fd);
    let result = (|| {
        file.write_all(data.as_bytes())
            .map_err(|_| Code::IoFailure)?;
        fs::fsync(&file).map_err(classify)?;
        fs::linkat(&parent, temp.as_str(), &parent, *name, AtFlags::empty()).map_err(classify)?;
        Ok(())
    })();
    let cleanup = fs::unlinkat(&parent, temp.as_str(), AtFlags::empty()).map_err(classify);
    result.and(cleanup)?;
    fs::fsync(&parent).map_err(classify)
}

pub fn run(program: &HostProgram, policy: &Policy, supplied: &[String]) -> Outcome {
    if !policy.trusted
        || (program.reads && !policy.allow_read)
        || (program.lists && !policy.allow_list)
        || (program.writes && !policy.allow_write)
        || (program.mkdirs && !policy.allow_mkdir)
        || (program.rmdirs && !policy.allow_rmdir)
    {
        return Outcome::rejected();
    }
    let Some((mut values, mut documents)) = arguments(program, supplied) else {
        return Outcome::rejected();
    };
    let scopes = (|| {
        let root =
            fs::open(&policy.root, OPEN | OFlags::DIRECTORY, Mode::empty()).map_err(classify)?;
        let read = program
            .reads
            .then(|| scope(&root, &policy.read_scope))
            .transpose()?;
        let write = program
            .writes
            .then(|| scope(&root, &policy.write_scope))
            .transpose()?;
        let list = program
            .lists
            .then(|| scope(&root, &policy.list_scope))
            .transpose()?;
        Ok::<_, Code>((read, write, list))
    })();
    let Ok((reader, writer, lister)) = scopes else {
        return Outcome::rejected();
    };
    let executed = (|| {
        let evaluate = |expr: &Expr, values: &State| {
            expr::evaluate_with(expr, values, &program.types).map_err(|_| Code::EngineFault)
        };
        let text = |expr: &Expr, values: &State| match evaluate(expr, values)? {
            Value::Text(value) => Ok(value),
            _ => Err(Code::EngineFault),
        };
        let mut pending: Option<Pending> = None;
        for step in &program.steps {
            match step {
                Step::Let(key, expr) => {
                    values.insert(key.clone(), evaluate(expr, &values)?);
                }
                Step::Read(key, path) => {
                    let path = text(path, &values)?;
                    values.insert(key.clone(), read(reader.as_ref().unwrap(), &path)?);
                }
                Step::ReadJson(key, path) => {
                    let path = text(path, &values)?;
                    documents.insert(key.clone(), read_json(reader.as_ref().unwrap(), &path)?);
                }
                Step::ListDir(key, path) => {
                    let path = text(path, &values)?;
                    documents.insert(key.clone(), list_dir(lister.as_ref().unwrap(), &path)?);
                }
                Step::JsonGet(target, source, key, target_kind) => {
                    let document = documents.get(source).ok_or(Code::EngineFault)?;
                    let key = match evaluate(key, &values)? {
                        Value::Text(t) => Key::Text(t),
                        Value::Int(i) => Key::Index(i),
                        _ => return Err(Code::EngineFault),
                    };
                    let child = host_json::get(document, key).map_err(|_| Code::InvalidJson)?;
                    match target_kind {
                        JsonTarget::Json => {
                            documents.insert(target.clone(), child);
                        }
                        JsonTarget::Text => match child.0 {
                            JsonValue::String(s) => {
                                values.insert(target.clone(), Value::Text(s));
                            }
                            _ => return Err(Code::InvalidJson),
                        },
                        JsonTarget::Int => match child.0 {
                            JsonValue::Number(n) => {
                                let v = n
                                    .as_i64()
                                    .and_then(|x| i32::try_from(x).ok())
                                    .ok_or(Code::InvalidJson)?;
                                values.insert(target.clone(), Value::Int(v));
                            }
                            _ => return Err(Code::InvalidJson),
                        },
                        JsonTarget::Bool => match child.0 {
                            JsonValue::Bool(v) => {
                                values.insert(target.clone(), Value::Bool(v));
                            }
                            _ => return Err(Code::InvalidJson),
                        },
                    }
                }
                Step::JsonCount(target, source) => {
                    let document = documents.get(source).ok_or(Code::EngineFault)?;
                    let count = host_json::count(document).map_err(|_| Code::InvalidJson)?;
                    values.insert(target.clone(), Value::Int(count));
                }
                Step::JsonObject(target) => {
                    documents.insert(
                        target.clone(),
                        Document(JsonValue::Object(Default::default())),
                    );
                }
                Step::JsonSet(target, field, value) => {
                    let original = documents.get(target).ok_or(Code::EngineFault)?;
                    let value = match value {
                        JsonInput::Document(name) => {
                            documents.get(name).ok_or(Code::EngineFault)?.0.clone()
                        }
                        JsonInput::Scalar(expr) => evaluate(expr, &values)?.plain(),
                    };
                    let next =
                        host_json::set(original, field, value).map_err(|_| Code::InvalidJson)?;
                    documents.insert(target.clone(), next);
                }
                Step::Write(path, value) => {
                    let path = text(path, &values)?;
                    path_parts(&path)?;
                    let value = text(value, &values)?;
                    if value.len() > MAX_FILE_BYTES {
                        return Err(Code::ResourceTooLarge);
                    }
                    pending = Some(Pending::Write(path, value));
                }
                Step::WriteJson(path, source) => {
                    let path = text(path, &values)?;
                    path_parts(&path)?;
                    let doc = documents.get(source).ok_or(Code::EngineFault)?;
                    let raw = host_json::compact(doc).map_err(|_| Code::InvalidJson)?;
                    pending = Some(Pending::Write(path, raw));
                }
                Step::Mkdir(path) => {
                    let path = text(path, &values)?;
                    path_parts(&path)?;
                    pending = Some(Pending::Mkdir(path));
                }
                Step::Rmdir(path) => {
                    let path = text(path, &values)?;
                    path_parts(&path)?;
                    pending = Some(Pending::Rmdir(path));
                }
                Step::Emit(expr) => return Ok((evaluate(expr, &values)?.plain(), pending)),
                Step::EmitJson(source) => {
                    let doc = documents.get(source).ok_or(Code::EngineFault)?;
                    host_json::compact(doc).map_err(|_| Code::InvalidJson)?;
                    return Ok((doc.0.clone(), pending));
                }
            }
        }
        Err(Code::EngineFault)
    })();
    match executed {
        Err(code) => Outcome::failure(Phase::Execute, code),
        Ok((result, None)) => Outcome::success(result, None),
        Ok((result, Some(pending))) => {
            let path = pending.path().to_owned();
            let committed = match pending {
                Pending::Write(path, value) => write(writer.as_ref().unwrap(), &path, &value),
                Pending::Mkdir(path) => mkdir(writer.as_ref().unwrap(), &path),
                Pending::Rmdir(path) => rmdir(writer.as_ref().unwrap(), &path),
            };
            match committed {
                Ok(()) => Outcome::success(result, Some(path)),
                Err(code) => Outcome::failure(Phase::Commit, code),
            }
        }
    }
}
