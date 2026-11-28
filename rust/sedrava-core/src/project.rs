//! A25: explicit, local application projects (Unix preview).
//! Trusted operator-owned project/data paths; no package registry, shell execution,
//! secret generation or network deployment.
use crate::{
    model::{fail, Error, Result},
    server::{sql_api, RuntimeOptions},
    site,
};
use sedravasql::native_log::{
    migration, NativeChange, NativeLimits, NativeLog, NativeMutation, TransactionalStore,
};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::{
    collections::{BTreeMap, BTreeSet},
    fs::{self, File},
    io::Read,
    os::unix::fs::{MetadataExt, PermissionsExt},
    path::{Path, PathBuf},
};

mod domain;

const DOMAIN: &str = "domain.sdr";
const MANIFEST: &str = "sedrava-project.json";
const APP: &str = "app.sdr";
const API: &str = "api.sdr";
const MIGRATIONS: &str = "migrations.json";
const ASSETS: [&str; 3] = ["app.css", "app.js", "index.html"];
const LIMIT: u64 = 262144;

#[derive(Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Manifest {
    format: u32,
    name: String,
    version: String,
}
fn name_ok(s: &str) -> bool {
    !s.is_empty()
        && s.len() <= 48
        && s.as_bytes()[0].is_ascii_lowercase()
        && s.bytes()
            .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'-')
        && !s.ends_with('-')
        && !s.contains("--")
}
fn version_ok(s: &str) -> bool {
    let parts: Vec<_> = s.split('.').collect();
    parts.len() == 3
        && parts.iter().all(|p| {
            p.parse::<u32>().is_ok()
                && p.bytes().all(|b| b.is_ascii_digit())
                && (*p == "0" || !p.starts_with('0'))
        })
}
fn err(e: impl std::fmt::Display) -> Error {
    Error(format!("E_PROJECT: {e}"))
}
fn digest(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}
fn encode<T: Serialize>(v: &T) -> Result<Vec<u8>> {
    let mut b = serde_json::to_vec_pretty(v).map_err(err)?;
    b.push(b'\n');
    Ok(b)
}
fn read(path: &Path, limit: u64) -> Result<Vec<u8>> {
    let meta = fs::symlink_metadata(path).map_err(err)?;
    if !meta.is_file() || meta.len() > limit {
        return fail("E_PROJECT: expected bounded regular file");
    }
    let f = File::open(path).map_err(err)?;
    if !f.metadata().map_err(err)?.is_file() {
        return fail("E_PROJECT: expected regular file");
    }
    let mut b = Vec::new();
    f.take(limit + 1).read_to_end(&mut b).map_err(err)?;
    if b.len() as u64 > limit {
        return fail("E_PROJECT: file exceeds limit");
    }
    Ok(b)
}
fn text(raw: &[u8]) -> Result<&str> {
    std::str::from_utf8(raw).map_err(err)
}
fn directory(path: &Path) -> Result<()> {
    if !fs::symlink_metadata(path).map_err(err)?.is_dir() {
        return fail("E_PROJECT: real directory required");
    }
    Ok(())
}
fn absent(path: &Path) -> Result<bool> {
    match fs::symlink_metadata(path) {
        Ok(_) => Ok(false),
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => Ok(true),
        Err(e) => Err(err(e)),
    }
}
fn private_data(path: &Path) -> Result<PathBuf> {
    if !path.is_absolute() {
        return fail("E_PROJECT: absolute data directory required");
    }
    let m = fs::symlink_metadata(path).map_err(err)?;
    if !m.is_dir() || m.uid() != rustix::process::geteuid().as_raw() || m.mode() & 0o077 != 0 {
        return fail("E_PROJECT: owner-owned private data directory required");
    }
    Ok(path.join("app.log"))
}
// One marker in the same journal as migrations and rows. Only an empty
// journal may be bound; do not silently adopt pre-A26 or unmanaged data.
const IDENTITY_NS: &str = "sedrava_project_identity";
const IDENTITY_KEY: &str = "name";
const IDENTITY_REQUEST: &str = "sedrava-project-identity-v1";

pub(crate) fn verify_identity(db: &NativeLog, name: &str) -> Result<()> {
    let row = db
        .read(IDENTITY_NS, IDENTITY_KEY)
        .map_err(err)?
        .ok_or_else(|| err("database is not bound to a project"))?;
    if row.revision != 1 || row.value.as_deref() != Some(name) {
        return fail("E_PROJECT: database belongs to a different project or identity changed");
    }
    let receipt = db
        .lookup_receipt(IDENTITY_REQUEST)
        .map_err(err)?
        .ok_or_else(|| err("missing project identity receipt"))?;
    if receipt.sequence != 1 || receipt.entries.as_slice() != [row] {
        return fail("E_PROJECT: inconsistent project identity");
    }
    Ok(())
}
fn bind_identity(db: &mut NativeLog, name: &str, apply: bool) -> Result<()> {
    if apply && db.sequence() == 0 {
        db.commit_batch(
            IDENTITY_REQUEST,
            &[NativeMutation {
                namespace: IDENTITY_NS.into(),
                key: IDENTITY_KEY.into(),
                expected_revision: 0,
                change: NativeChange::Put(name.into()),
            }],
        )
        .map_err(err)?;
    }
    verify_identity(db, name)
}

struct Project {
    manifest: Manifest,
    sources: BTreeMap<String, Vec<u8>>,
    assets: BTreeMap<String, Vec<u8>>,
    api: sql_api::Api,
    plan: migration::Plan,
}
impl Project {
    fn load(root: &Path) -> Result<Self> {
        directory(root)?;
        let mut sources = BTreeMap::new();
        sources.insert(MANIFEST.to_owned(), read(&root.join(MANIFEST), 4096)?);
        let manifest: Manifest = serde_json::from_slice(&sources[MANIFEST]).map_err(err)?;
        if !matches!(manifest.format, 1 | 2)
            || !name_ok(&manifest.name)
            || !version_ok(&manifest.version)
        {
            return fail("E_PROJECT: invalid manifest");
        }
        if manifest.format == 1 {
            if !absent(&root.join(DOMAIN))? {
                return fail("E_PROJECT: ambiguous domain source in format 1");
            }
            for (name, limit) in [(APP, LIMIT), (API, 32768), (MIGRATIONS, 65536)] {
                sources.insert(name.to_owned(), read(&root.join(name), limit)?);
            }
        } else {
            let raw = read(&root.join(DOMAIN), 16384)?;
            let (app, api, migrations) = domain::lower(text(&raw)?)?;
            // Generated low-level files are part of verified bundles, never source overrides.
            let packaged = !absent(&root.join("checksums.json"))?;
            for (name, bytes, limit) in [
                (APP, app, LIMIT),
                (API, api, 32768),
                (MIGRATIONS, migrations, 65536),
            ] {
                if bytes.len() as u64 > limit {
                    return fail("E_PROJECT: generated source budget");
                }
                if !packaged && !absent(&root.join(name))? {
                    return fail("E_PROJECT: domain source cannot be mixed with manual sources");
                }
                sources.insert(name.to_owned(), bytes);
            }
            sources.insert(DOMAIN.to_owned(), raw);
        }
        // Self-contained source-only projects for A25. Local imports/assets
        // are intentionally not supported by this package contract.
        let assets = site::webapp::generate(text(&sources[APP])?, None)?.files;
        if assets.keys().map(String::as_str).collect::<Vec<_>>() != ASSETS
            || assets
                .values()
                .any(|b| b.is_empty() || b.len() as u64 > LIMIT)
        {
            return fail("E_PROJECT: expected exactly three bounded generated assets");
        }
        let api = sql_api::parse(text(&sources[API])?)?;
        let plan = migration::Plan::parse(&sources[MIGRATIONS]).map_err(err)?;
        Ok(Self {
            manifest,
            sources,
            assets,
            api,
            plan,
        })
    }
    fn bundle(&self) -> Result<BTreeMap<String, Vec<u8>>> {
        let mut files = self.sources.clone();
        for (name, bytes) in &self.assets {
            files.insert(format!("ui/{name}"), bytes.clone());
        }
        let hashes: BTreeMap<_, _> = files.iter().map(|(k, v)| (k.clone(), digest(v))).collect();
        files.insert(
            "checksums.json".into(),
            encode(&serde_json::json!({
                "format":1,"compiler":env!("CARGO_PKG_VERSION"),"files":hashes
            }))?,
        );
        Ok(files)
    }
    fn build_id(&self) -> Result<String> {
        let bundle = self.bundle()?;
        Ok(digest(&bundle["checksums.json"]))
    }
    fn test(&self) -> Result<()> {
        let tmp = tempfile::tempdir().map_err(err)?;
        fs::set_permissions(tmp.path(), fs::Permissions::from_mode(0o700)).map_err(err)?;
        let file = tmp.path().join("test.log");
        let mut db = NativeLog::create(&file).map_err(err)?;
        bind_identity(&mut db, &self.manifest.name, true)?;
        let result = migration::apply(&mut db, &self.plan).map_err(err)?;
        let before = read(&file, 64 * 1024 * 1024)?;
        let repeat = migration::apply(&mut db, &self.plan).map_err(err)?;
        if result.current_version != repeat.current_version
            || !repeat.pending.is_empty()
            || read(&file, 64 * 1024 * 1024)? != before
        {
            return fail("E_PROJECT: migration repeat changed test data");
        }
        db.verify().map_err(err)?;
        println!("PASS project {}: WebApp generation, API parsing, {} migration versions, byte-identical repeat, native verification",self.manifest.name,result.current_version);
        Ok(())
    }
}
#[cfg(any(target_os = "linux", target_vendor = "apple"))]
fn publish(path: &Path, files: &BTreeMap<String, Vec<u8>>) -> Result<()> {
    use rustix::fs::{renameat_with, RenameFlags, CWD};
    if !absent(path)? {
        return fail("E_PROJECT: output already exists");
    }
    let parent = path
        .parent()
        .filter(|p| !p.as_os_str().is_empty())
        .unwrap_or(Path::new("."));
    directory(parent)?;
    let stage = tempfile::tempdir_in(parent).map_err(err)?;
    fs::set_permissions(stage.path(), fs::Permissions::from_mode(0o755)).map_err(err)?;
    for (name, data) in files {
        let target = stage.path().join(name);
        if let Some(dir) = target.parent() {
            fs::create_dir_all(dir).map_err(err)?;
        }
        fs::write(&target, data).map_err(err)?;
    }
    renameat_with(CWD, stage.path(), CWD, path, RenameFlags::NOREPLACE).map_err(err)?;
    Ok(())
}
#[cfg(not(any(target_os = "linux", target_vendor = "apple")))]
fn publish(_path: &Path, _files: &BTreeMap<String, Vec<u8>>) -> Result<()> {
    fail("E_PROJECT: atomic no-replace directory publication unavailable")
}
fn verify_files(root: &Path, expected: &BTreeMap<String, Vec<u8>>) -> Result<()> {
    directory(root)?;
    let mut actual = BTreeSet::new();
    for entry in fs::read_dir(root).map_err(err)? {
        let entry = entry.map_err(err)?;
        let name = entry
            .file_name()
            .into_string()
            .map_err(|_| err("invalid output name"))?;
        if name == "ui" && entry.file_type().map_err(err)?.is_dir() {
            for child in fs::read_dir(entry.path()).map_err(err)? {
                let child = child.map_err(err)?;
                let name = child
                    .file_name()
                    .into_string()
                    .map_err(|_| err("invalid asset name"))?;
                if !child.file_type().map_err(err)?.is_file() {
                    return fail("E_PROJECT: unexpected asset");
                }
                let path = format!("ui/{name}");
                if !expected.contains_key(&path) {
                    return fail("E_PROJECT: unexpected asset name");
                }
                actual.insert(path);
            }
        } else if entry.file_type().map_err(err)?.is_file() {
            if !expected.contains_key(&name) {
                return fail("E_PROJECT: unexpected output name");
            }
            actual.insert(name);
        } else {
            return fail("E_PROJECT: unexpected output entry");
        }
    }
    if actual != expected.keys().cloned().collect() {
        return fail("E_PROJECT: bundle file set differs");
    }
    for (name, bytes) in expected {
        if read(&root.join(name), bytes.len() as u64)? != *bytes {
            return fail("E_PROJECT: bundle content differs");
        }
    }
    Ok(())
}
fn scaffold(name: &str) -> Result<()> {
    if !name_ok(name) {
        return fail("E_PROJECT: name must be lowercase ASCII, digits and single hyphens");
    }
    let manifest = Manifest {
        format: 1,
        name: name.into(),
        version: "0.1.0".into(),
    };
    let app = include_str!("../../../examples/sales_demo/native_app.sdr").replacen(
        "Sedrava · Native Sales",
        name,
        1,
    );
    // Reuse the tested A24 catalog/SQL contract, including orders API.
    let files = BTreeMap::from([
        (MANIFEST.into(), encode(&manifest)?),
        (APP.into(), app.into_bytes()),
        (
            API.into(),
            include_bytes!("../../../examples/sales_demo/sales_api.sdr").to_vec(),
        ),
        (
            MIGRATIONS.into(),
            include_bytes!("../../../examples/sales_demo/migrations.json").to_vec(),
        ),
        (
            ".gitignore".into(),
            b"/build/\n/dist/\n/data/\n*.log\n*.lock\n/auth.json\n".to_vec(),
        ),
    ]);
    publish(Path::new(name), &files)?;
    println!("Created project {name}");
    Ok(())
}
fn build(project: &Project, root: &Path) -> Result<PathBuf> {
    if !absent(&root.join("checksums.json"))? {
        verify_files(root, &project.bundle()?)?;
        return Ok(root.to_path_buf());
    }
    let parent = root.join("build");
    if absent(&parent)? {
        fs::create_dir(&parent).map_err(err)?;
    }
    directory(&parent)?;
    let output = parent.join(project.build_id()?);
    let bundle = project.bundle()?;
    if absent(&output)? {
        publish(&output, &bundle)?;
    } else {
        verify_files(&output, &bundle)?;
    }
    Ok(output)
}
#[derive(Default)]
struct Options {
    data: Option<PathBuf>,
    auth: Option<PathBuf>,
    trusted: bool,
    apply: bool,
    write: bool,
    port: Option<u16>,
    requests: Option<u32>,
    idle: Option<u32>,
    ttl: Option<u32>,
}
fn options(args: &[String], serve: bool) -> Result<Options> {
    let mut o = Options::default();
    let mut seen = BTreeSet::new();
    let mut it = args.iter();
    while let Some(flag) = it.next() {
        if !seen.insert(flag) {
            return fail("E_PROJECT: duplicate option");
        }
        let mut value = || it.next().ok_or_else(|| err("missing option value"));
        match flag.as_str() {
            "--data" => o.data = Some(PathBuf::from(value()?)),
            "--trusted" => o.trusted = true,
            "--apply" if !serve => o.apply = true,
            "--auth-file" if serve => o.auth = Some(PathBuf::from(value()?)),
            "--allow-write" if serve => o.write = true,
            "--port" if serve => o.port = Some(value()?.parse().map_err(err)?),
            "--max-requests" if serve => o.requests = Some(value()?.parse().map_err(err)?),
            "--idle-ms" if serve => o.idle = Some(value()?.parse().map_err(err)?),
            "--session-ttl" if serve => o.ttl = Some(value()?.parse().map_err(err)?),
            _ => return fail("E_PROJECT: unsupported option"),
        }
    }
    if !o.trusted || o.data.is_none() {
        return fail("E_PROJECT: --trusted and --data required");
    }
    if serve && o.auth.is_none() {
        return fail("E_PROJECT: --auth-file required");
    }
    Ok(o)
}
pub fn run(args: &[String]) -> Result<()> {
    let command = args
        .first()
        .map(String::as_str)
        .ok_or_else(|| err("expected project command"))?;
    if command == "new" {
        return match args {
            [_, name] => scaffold(name),
            _ => fail("E_PROJECT: expected new NAME"),
        };
    }
    if command == "verify-package" {
        return match args {
            [_, path] => {
                let root = Path::new(path);
                let project = Project::load(root)?;
                verify_files(root, &project.bundle()?)?;
                println!("PASS package {}", project.build_id()?);
                Ok(())
            }
            _ => fail("E_PROJECT: expected project verify-package DIR"),
        };
    }
    let root = std::env::current_dir().map_err(err)?;
    let project = Project::load(&root)?;
    if !absent(&root.join("checksums.json"))? {
        verify_files(&root, &project.bundle()?)?;
    }
    match args {
        [_] if command == "build" => {
            println!("{}", build(&project, &root)?.display());
            Ok(())
        }
        [_] if command == "test" => project.test(),
        [_, flag, path] if command == "package" && flag == "--output" => {
            let target = Path::new(path);
            publish(target, &project.bundle()?)?;
            println!("Packaged {} at {}", project.manifest.name, target.display());
            Ok(())
        }
        [_, rest @ ..] if command == "migrate" => {
            let o = options(rest, false)?;
            let path = private_data(o.data.as_deref().unwrap())?;
            let mut db = if o.apply && absent(&path)? {
                NativeLog::create(&path)
            } else {
                NativeLog::open(&path)
            }
            .map_err(err)?;
            db.verify().map_err(err)?;
            bind_identity(&mut db, &project.manifest.name, o.apply)?;
            let result = if o.apply {
                migration::apply(&mut db, &project.plan)
            } else {
                migration::status(&db, &project.plan)
            }
            .map_err(err)?;
            println!("{}", serde_json::to_string(&result).map_err(err)?);
            Ok(())
        }
        [_, rest @ ..] if command == "serve" => {
            let o = options(rest, true)?;
            let path = private_data(o.data.as_deref().unwrap())?;
            let auth = sql_api::Auth::load(o.auth.as_deref().unwrap())?;
            let output = build(&project, &root)?;
            let ui = sql_api::WebUi::load(&output.join("ui"))?;
            sql_api::serve_project(
                &project.api,
                &path,
                true,
                o.write,
                NativeLimits::default(),
                RuntimeOptions {
                    port: o.port.unwrap_or(0),
                    max_requests: o.requests.unwrap_or(1000),
                    idle_ms: o.idle.unwrap_or(120000),
                },
                (
                    Some(&auth),
                    Some(&ui),
                    Some(o.ttl.unwrap_or(900)),
                    Some((&project.plan, false)),
                    Some(&project.manifest.name),
                ),
            )
        }
        _ => fail("E_PROJECT: expected build, test, migrate, serve or package"),
    }
}
