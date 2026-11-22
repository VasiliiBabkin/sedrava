//! Offline, reviewable local-package content locks. No registry or downloads.
//! Compatible with the schema-1 lock shape from experimental Python 0.12.
//! The project folder is trusted against concurrently hostile path replacement.
use crate::model::{fail, Error, Result};
use serde::{Deserialize, Serialize};
use serde_json::{Map, Number, Value};
use sha2::{Digest, Sha256};
use std::{
    collections::{BTreeMap, BTreeSet},
    fs::{self, File},
    io::{Read, Write},
    path::{Path, PathBuf},
};
use tempfile::NamedTempFile;

const MAX_PACKAGES: usize = 32;
const MAX_FILES: usize = 256;
const MAX_ENTRIES: usize = 1024;
const MAX_BYTES: u64 = 8 * 1024 * 1024;
const MAX_DEPTH: usize = 16;
const MAX_PATH_CHARS: usize = 1024;
const MAX_MANIFEST_BYTES: u64 = 32_768;
const MAX_LOCK_BYTES: u64 = 128_000;

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Manifest {
    package: Metadata,
    #[serde(default)]
    dependencies: BTreeMap<String, Dependency>,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Metadata {
    name: String,
    version: String,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Dependency {
    path: String,
    version: String,
}
#[derive(Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
struct LockPackage {
    dependencies: Vec<String>,
    files: BTreeMap<String, String>,
    name: String,
    path: String,
    version: String,
}
#[derive(Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
struct LockRoot {
    dependencies: Vec<String>,
    manifest_sha256: String,
    name: String,
    version: String,
}
#[derive(Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
struct Lock {
    packages: Vec<LockPackage>,
    root: LockRoot,
    schema: i32,
}
struct Builder<'a> {
    root: &'a Path,
    packages: BTreeMap<String, LockPackage>,
    active: BTreeSet<String>,
}
fn issue(message: impl Into<String>) -> Error {
    Error(format!("Locked local packages: {}", message.into()))
}
fn valid_name(name: &str) -> bool {
    if name.is_empty() || !name.as_bytes()[0].is_ascii_lowercase() {
        return false;
    }
    name.split(['.', '-']).all(|part| {
        !part.is_empty()
            && part.as_bytes()[0].is_ascii_lowercase()
            && part
                .bytes()
                .all(|c| c.is_ascii_lowercase() || c.is_ascii_digit())
    })
}
fn valid_version(version: &str) -> bool {
    let parts: Vec<_> = version.split('.').collect();
    parts.len() == 3
        && parts.iter().all(|p| {
            !p.is_empty()
                && (p == &"0" || !p.starts_with('0'))
                && p.bytes().all(|b| b.is_ascii_digit())
        })
}
fn relative(spec: &str) -> Result<PathBuf> {
    if spec.len() > MAX_PATH_CHARS
        || spec.is_empty()
        || spec.contains(&['\\', ':', '\0'][..])
        || spec
            .split('/')
            .any(|part| part.is_empty() || part == "." || part == ".." || part.starts_with('.'))
    {
        return fail("Invalid vendored dependency path");
    }
    let parts: Vec<_> = spec.split('/').collect();
    if parts.len() < 2 || parts[0] != "vendor" {
        return fail("Dependencies must be under vendor/");
    }
    Ok(parts.iter().copied().collect())
}
fn no_links(root: &Path, path: &Path) -> Result<()> {
    let mut current = root.to_path_buf();
    for component in path.components() {
        current.push(component.as_os_str());
        let info = fs::symlink_metadata(&current)
            .map_err(|e| issue(format!("Missing path {}: {e}", current.display())))?;
        if info.file_type().is_symlink() {
            return fail("Package symlinks forbidden");
        }
    }
    Ok(())
}
fn digest(raw: &[u8]) -> String {
    format!("{:x}", Sha256::digest(raw))
}
fn read_regular(path: &Path, cap: u64) -> Result<Vec<u8>> {
    let info = fs::symlink_metadata(path)
        .map_err(|e| issue(format!("Missing {}: {e}", path.display())))?;
    if !info.file_type().is_file() || info.len() > cap {
        return fail("Package file is not regular or exceeds resource budget");
    }
    #[cfg(unix)]
    {
        use std::os::unix::fs::MetadataExt;
        if info.nlink() != 1 {
            return fail("Multiply linked package files are forbidden");
        }
    }
    let mut result = Vec::new();
    File::open(path)
        .map_err(|e| issue(e.to_string()))?
        .take(cap + 1)
        .read_to_end(&mut result)
        .map_err(|e| issue(e.to_string()))?;
    if result.len() as u64 > cap {
        return fail("Package bytes exceed resource budget");
    }
    Ok(result)
}
fn manifest(path: &Path) -> Result<(Manifest, Vec<u8>)> {
    let raw = read_regular(path, MAX_MANIFEST_BYTES)?;
    let text = std::str::from_utf8(&raw).map_err(|_| issue("Manifest not UTF-8"))?;
    let parsed: Manifest =
        toml::from_str(text).map_err(|e| issue(format!("Invalid TOML manifest: {e}")))?;
    if !valid_name(&parsed.package.name)
        || !valid_version(&parsed.package.version)
        || parsed.dependencies.len() > MAX_PACKAGES
    {
        return fail("Invalid package identity/version or dependency budget");
    }
    for (name, dep) in &parsed.dependencies {
        if !valid_name(name) || !valid_version(&dep.version) {
            return fail("Invalid dependency identity/version");
        }
        relative(&dep.path)?;
    }
    Ok((parsed, raw))
}
fn walk(
    folder: &Path,
    current: &Path,
    depth: usize,
    count: &mut usize,
    out: &mut Vec<PathBuf>,
) -> Result<()> {
    if depth > MAX_DEPTH {
        return fail("Local package directory depth exceeded");
    }
    let info = fs::symlink_metadata(current).map_err(|e| issue(e.to_string()))?;
    if !info.file_type().is_dir() {
        return fail("Package directory is not a directory");
    }
    let mut children = Vec::new();
    for entry in fs::read_dir(current).map_err(|e| issue(e.to_string()))? {
        let entry = entry.map_err(|e| issue(e.to_string()))?;
        *count += 1;
        if *count > MAX_ENTRIES {
            return fail("Package directory entry budget exceeded");
        }
        let name = entry.file_name();
        let name = name
            .to_str()
            .ok_or_else(|| issue("Non-UTF-8 package filename"))?;
        if name.starts_with('.') || name.is_empty() {
            return fail("Hidden package entry forbidden");
        }
        let path = entry.path();
        let rel = path
            .strip_prefix(folder)
            .map_err(|_| issue("Package escaped root"))?;
        let name = rel
            .to_str()
            .ok_or_else(|| issue("Non-UTF-8 package path"))?;
        if name.chars().count() > MAX_PATH_CHARS {
            return fail("Package filename budget exceeded");
        }
        let info = fs::symlink_metadata(&path).map_err(|e| issue(e.to_string()))?;
        if info.file_type().is_dir() {
            children.push(path);
        } else if info.file_type().is_file() {
            #[cfg(unix)]
            {
                use std::os::unix::fs::MetadataExt;
                if info.nlink() != 1 {
                    return fail("Multiply linked package files are forbidden");
                }
            }
            if out.len() >= MAX_FILES {
                return fail("Package file count exceeded");
            }
            out.push(path);
        } else {
            return fail("Package symlinks or special files forbidden");
        }
    }
    children.sort();
    for child in children {
        walk(folder, &child, depth + 1, count, out)?;
    }
    Ok(())
}
fn package_files(folder: &Path) -> Result<BTreeMap<String, String>> {
    let mut paths = Vec::new();
    walk(folder, folder, 0, &mut 0, &mut paths)?;
    paths.sort();
    let mut total = 0;
    let mut files = BTreeMap::new();
    for path in paths {
        let remaining = MAX_BYTES.saturating_sub(total);
        let raw = read_regular(&path, remaining)?;
        total += raw.len() as u64;
        let relative = path
            .strip_prefix(folder)
            .map_err(|_| issue("Bad relative package path"))?;
        let name = relative
            .to_str()
            .ok_or_else(|| issue("Non-UTF-8 filename"))?;
        files.insert(name.replace(std::path::MAIN_SEPARATOR, "/"), digest(&raw));
    }
    Ok(files)
}
impl Builder<'_> {
    fn load(&mut self, name: &str, dep: &Dependency) -> Result<()> {
        if self.active.contains(name) {
            return fail("Cyclic package dependency");
        }
        if let Some(existing) = self.packages.get(name) {
            if existing.version == dep.version && existing.path == dep.path {
                return Ok(());
            }
            return fail("Conflicting package version or path");
        }
        if self.packages.len() >= MAX_PACKAGES {
            return fail("Package count exceeded");
        }
        let rel = relative(&dep.path)?;
        no_links(self.root, &rel)?;
        let dir = self.root.join(&rel);
        let (definition, raw) = manifest(&dir.join("sedrava.toml"))?;
        if definition.package.name != name || definition.package.version != dep.version {
            return fail("Vendored package name/version mismatch");
        }
        self.active.insert(name.into());
        let files = package_files(&dir)?;
        if files.get("sedrava.toml") != Some(&digest(&raw)) {
            return fail("Package manifest changed during verification");
        }
        self.packages.insert(
            name.into(),
            LockPackage {
                dependencies: definition.dependencies.keys().cloned().collect(),
                files,
                name: name.into(),
                path: dep.path.clone(),
                version: dep.version.clone(),
            },
        );
        for (child, spec) in &definition.dependencies {
            self.load(child, spec)?;
        }
        self.active.remove(name);
        Ok(())
    }
}
fn snapshot(project: &Path) -> Result<Lock> {
    let root = fs::canonicalize(project).map_err(|e| issue(format!("Project not found: {e}")))?;
    if !root.is_dir() {
        return fail("Expected project directory");
    }
    let (entry, raw) = manifest(&root.join("sedrava.toml"))?;
    let mut builder = Builder {
        root: &root,
        packages: BTreeMap::new(),
        active: BTreeSet::new(),
    };
    for (name, dep) in &entry.dependencies {
        builder.load(name, dep)?;
    }
    if builder.packages.contains_key(&entry.package.name) {
        return fail("Package identity conflicts with root");
    }
    Ok(Lock {
        packages: builder.packages.into_values().collect(),
        root: LockRoot {
            dependencies: entry.dependencies.keys().cloned().collect(),
            manifest_sha256: digest(&raw),
            name: entry.package.name,
            version: entry.package.version,
        },
        schema: 1,
    })
}

// A strict decoder rejecting duplicate JSON object keys, not serde_json's
// ordinary Map behavior (which overwrites duplicates).
struct Unique(Value);
impl<'de> Deserialize<'de> for Unique {
    fn deserialize<D: serde::Deserializer<'de>>(
        deserializer: D,
    ) -> std::result::Result<Self, D::Error> {
        use serde::de::{self, MapAccess, SeqAccess, Visitor};
        struct OnlyUnique;
        impl<'de> Visitor<'de> for OnlyUnique {
            type Value = Unique;
            fn expecting(&self, f: &mut std::fmt::Formatter) -> std::fmt::Result {
                write!(f, "duplicate-free JSON")
            }
            fn visit_unit<E: de::Error>(self) -> std::result::Result<Unique, E> {
                Ok(Unique(Value::Null))
            }
            fn visit_bool<E: de::Error>(self, v: bool) -> std::result::Result<Unique, E> {
                Ok(Unique(Value::Bool(v)))
            }
            fn visit_i64<E: de::Error>(self, v: i64) -> std::result::Result<Unique, E> {
                Ok(Unique(Value::Number(Number::from(v))))
            }
            fn visit_u64<E: de::Error>(self, v: u64) -> std::result::Result<Unique, E> {
                Ok(Unique(Value::Number(Number::from(v))))
            }
            fn visit_f64<E: de::Error>(self, _: f64) -> std::result::Result<Unique, E> {
                Err(E::custom("Floating-point lock values forbidden"))
            }
            fn visit_str<E: de::Error>(self, v: &str) -> std::result::Result<Unique, E> {
                Ok(Unique(Value::String(v.to_owned())))
            }
            fn visit_string<E: de::Error>(self, v: String) -> std::result::Result<Unique, E> {
                Ok(Unique(Value::String(v)))
            }
            fn visit_seq<A: SeqAccess<'de>>(
                self,
                mut a: A,
            ) -> std::result::Result<Unique, A::Error> {
                let mut v = Vec::new();
                while let Some(next) = a.next_element::<Unique>()? {
                    if v.len() >= MAX_ENTRIES {
                        return Err(de::Error::custom("Lock array limit"));
                    }
                    v.push(next.0);
                }
                Ok(Unique(Value::Array(v)))
            }
            fn visit_map<A: MapAccess<'de>>(
                self,
                mut a: A,
            ) -> std::result::Result<Unique, A::Error> {
                let mut v = Map::new();
                while let Some((name, item)) = a.next_entry::<String, Unique>()? {
                    if v.len() >= MAX_ENTRIES || v.contains_key(&name) {
                        return Err(de::Error::custom("Duplicate/oversized lock object"));
                    }
                    v.insert(name, item.0);
                }
                Ok(Unique(Value::Object(v)))
            }
        }
        deserializer.deserialize_any(OnlyUnique)
    }
}

pub fn verify(project: &Path) -> Result<BTreeMap<PathBuf, String>> {
    let root = fs::canonicalize(project).map_err(|e| issue(format!("Project not found: {e}")))?;
    let path = root.join("sedrava.lock");
    let bytes = read_regular(&path, MAX_LOCK_BYTES)?;
    let Unique(encoded) = serde_json::from_slice::<Unique>(&bytes)
        .map_err(|e| issue(format!("Invalid strict lockfile JSON: {e}")))?;
    let actual: Lock = serde_json::from_value(encoded).map_err(|e| issue(e.to_string()))?;
    let expected = snapshot(&root)?;
    if actual != expected {
        return fail("Local dependency lock mismatch; run lock after reviewing changes");
    }
    let mut verified = BTreeMap::new();
    for package in expected.packages {
        for (path, hash) in package.files {
            verified.insert(root.join(&package.path).join(path), hash);
        }
    }
    Ok(verified)
}

pub fn verify_if_project(entrypoint: &Path) -> Result<Option<BTreeMap<PathBuf, String>>> {
    let entry = fs::canonicalize(entrypoint).map_err(|e| issue(e.to_string()))?;
    let root = entry.parent().ok_or_else(|| issue("No project root"))?;
    let manifest = fs::symlink_metadata(root.join("sedrava.toml"));
    let lock = fs::symlink_metadata(root.join("sedrava.lock"));
    match (manifest, lock) {
        (Err(a), Err(b))
            if a.kind() == std::io::ErrorKind::NotFound
                && b.kind() == std::io::ErrorKind::NotFound =>
        {
            Ok(None)
        }
        _ => verify(root).map(Some),
    }
}
pub fn write_lock(project: &Path) -> Result<PathBuf> {
    let root = fs::canonicalize(project).map_err(|e| issue(e.to_string()))?;
    let model = snapshot(&root)?;
    let target = root.join("sedrava.lock");
    match fs::symlink_metadata(&target) {
        Ok(info) if !info.file_type().is_file() => {
            return fail("Lockfile is a symlink or non-file")
        }
        Ok(_) => (),
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => (),
        Err(e) => return Err(issue(e.to_string())),
    }
    let raw = serde_json::to_string_pretty(&model).map_err(|e| issue(e.to_string()))? + "\n";
    if raw.len() as u64 > MAX_LOCK_BYTES {
        return fail("Lockfile serialization exceeds limit");
    }
    let mut stage = NamedTempFile::new_in(&root).map_err(|e| issue(e.to_string()))?;
    stage
        .write_all(raw.as_bytes())
        .map_err(|e| issue(e.to_string()))?;
    stage
        .as_file()
        .sync_all()
        .map_err(|e| issue(e.to_string()))?;
    stage
        .persist(&target)
        .map_err(|e| issue(e.error.to_string()))?;
    // Best-effort durability of the containing directory (not a power-loss guarantee).
    #[cfg(unix)]
    File::open(&root)
        .and_then(|d| d.sync_all())
        .map_err(|e| issue(e.to_string()))?;
    Ok(target)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn offline_reviewed_lock_is_deterministic_and_tamper_evident() {
        let d = tempfile::tempdir().unwrap();
        let root = d.path();
        fs::create_dir_all(root.join("vendor/my.lib")).unwrap();
        fs::write(root.join("sedrava.toml"),
            "[package]\nname=\"root.site\"\nversion=\"1.0.0\"\n[dependencies]\n\"my.lib\"={path=\"vendor/my.lib\",version=\"1.2.3\"}\n").unwrap();
        fs::write(
            root.join("vendor/my.lib/sedrava.toml"),
            "[package]\nname=\"my.lib\"\nversion=\"1.2.3\"\n",
        )
        .unwrap();
        fs::write(
            root.join("vendor/my.lib/lib.sdr"),
            "fn double(n: int) -> int = n * 2\n",
        )
        .unwrap();
        let lock = write_lock(root).unwrap();
        let first = fs::read(&lock).unwrap();
        write_lock(root).unwrap();
        assert_eq!(first, fs::read(&lock).unwrap());
        assert_eq!(verify(root).unwrap().len(), 2);
        fs::write(
            root.join("vendor/my.lib/lib.sdr"),
            "fn double(n: int) -> int = n * 3\n",
        )
        .unwrap();
        assert!(verify(root).is_err());
        fs::write(
            root.join("vendor/my.lib/lib.sdr"),
            "fn double(n: int) -> int = n * 2\n",
        )
        .unwrap();
        let locktext = fs::read_to_string(&lock).unwrap();
        fs::write(
            &lock,
            locktext.replacen("\"schema\": 1", "\"schema\": 1,\n  \"schema\": 1", 1),
        )
        .unwrap();
        assert!(verify(root).is_err());
    }
    #[cfg(unix)]
    #[test]
    fn package_symlinks_rejected() {
        use std::os::unix::fs::symlink;
        let d = tempfile::tempdir().unwrap();
        let root = d.path();
        fs::write(root.join("sedrava.toml"),
            "[package]\nname=\"root.site\"\nversion=\"1.0.0\"\n[dependencies]\n\"my.lib\"={path=\"vendor/my.lib\",version=\"1.2.3\"}\n").unwrap();
        fs::create_dir_all(root.join("vendor")).unwrap();
        symlink(root.join("vendor"), root.join("vendor/my.lib")).unwrap();
        assert!(write_lock(root).is_err());
    }
}
