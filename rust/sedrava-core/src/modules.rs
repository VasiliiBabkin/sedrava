//! Bounded, local-only source imports for the experimental native compiler.
//!
//! No network access, symlinks, traversal, arbitrary code execution or implicit
//! filesystem discovery. This is import expansion only; component/style macro
//! expansion and full Site/WebApp parsing remain separate migration work.
mod aliases;

use crate::model::{fail, Error, Result, MAX_SOURCE_CHARS};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::path::{Component, Path, PathBuf};

const MAX_IMPORT_DEPTH: usize = 16;
const MAX_FILES: usize = 32;
const MAX_MODULE_BYTES: u64 = MAX_SOURCE_CHARS as u64 * 4;

#[derive(Debug, Clone)]
pub struct ExpandedSource {
    pub source: String,
    pub imported_paths: BTreeSet<PathBuf>,
}

struct Expander {
    root: PathBuf,
    files: BTreeSet<PathBuf>,
    used_aliases: BTreeSet<String>,
    raw_generated_name_seen: bool,
    verified: Option<BTreeMap<PathBuf, String>>,
}

fn path_from_import(line: &str) -> Option<&str> {
    let raw = line.strip_prefix("import \"")?.strip_suffix('"')?;
    if raw.contains('"') || !raw.ends_with(".sdr") {
        return None;
    }
    Some(raw)
}

fn ensure_local_path(spec: &str) -> Result<PathBuf> {
    if spec.is_empty() || spec.contains('\\') || spec.contains(':') {
        return fail("Import path is invalid or platform-dependent");
    }
    let path = Path::new(spec);
    if path.is_absolute() {
        return fail("Import must be relative");
    }
    for component in path.components() {
        match component {
            Component::Normal(_) => (),
            _ => return fail("Import path must not contain parent or special segments"),
        }
    }
    Ok(path.to_owned())
}

fn reject_symlinks(root: &Path, relative: &Path) -> Result<()> {
    let mut current = root.to_path_buf();
    for component in relative.components() {
        current.push(component.as_os_str());
        let metadata = fs::symlink_metadata(&current)
            .map_err(|e| Error(format!("Missing local import {}: {e}", current.display())))?;
        if metadata.file_type().is_symlink() {
            return fail("Symlink imports are forbidden");
        }
    }
    Ok(())
}

fn permitted_module_line(line: &str) -> bool {
    let source = line.trim_start();
    if source.is_empty() || source.starts_with('#') {
        return true;
    }
    if line.starts_with(char::is_whitespace) {
        return true; // validated under one of the top-level declarations
    }
    [
        "import ",
        "component ",
        "style ",
        "record ",
        "fn ",
        "error ",
    ]
    .iter()
    .any(|prefix| source.starts_with(prefix))
}

impl Expander {
    fn expand(
        &mut self,
        source: &str,
        current: &Path,
        stack: &[PathBuf],
        depth: usize,
    ) -> Result<String> {
        if source.chars().count() > MAX_SOURCE_CHARS || depth > MAX_IMPORT_DEPTH {
            return fail("Expanded source or import depth exceeds limit");
        }
        if aliases::reserved_identifier(source) {
            // Never silently accept collisions with generated namespace names
            // when any alias import is present. Expanded (already lowered)
            // standalone sources without aliases remain valid inputs.
            self.raw_generated_name_seen = true;
        }
        let mut result = Vec::new();
        let mut namespace_exports = aliases::AliasMap::new();
        for (number, line) in source.lines().enumerate() {
            if line.trim_start().starts_with("import ") && !line.starts_with("import ") {
                return fail(format!(
                    "Line {}: module imports must be at column 1",
                    number + 1
                ));
            }
            let parsed_alias = aliases::alias_spec(line)?;
            let spec = match parsed_alias {
                Some((path, _)) => Some(path),
                None => path_from_import(line),
            };
            let Some(spec) = spec else {
                result.push(line.to_owned());
                continue;
            };
            let path = ensure_local_path(spec)?;
            let parent = current
                .parent()
                .ok_or_else(|| Error("Import source has no parent".into()))?;
            let candidate = parent.join(&path);
            let candidate_rel = candidate
                .strip_prefix(&self.root)
                .map_err(|_| Error(format!("Line {}: import outside root", number + 1)))?;
            reject_symlinks(&self.root, candidate_rel)?;
            let resolved = fs::canonicalize(&candidate).map_err(|e| {
                Error(format!(
                    "Line {}: cannot load module {spec}: {e}",
                    number + 1
                ))
            })?;
            if !resolved.starts_with(&self.root) || !resolved.is_file() {
                return fail(format!("Line {}: import outside project root", number + 1));
            }
            if stack.contains(&resolved) || depth >= MAX_IMPORT_DEPTH {
                return fail(format!("Line {}: cyclic or excessive imports", number + 1));
            }
            if !self.files.contains(&resolved) && self.files.len() >= MAX_FILES {
                return fail("Module file limit exceeded");
            }
            let metadata =
                fs::metadata(&resolved).map_err(|e| Error(format!("Cannot stat import: {e}")))?;
            if metadata.len() > MAX_MODULE_BYTES {
                return fail("Imported module too large");
            }
            let bytes = fs::read(&resolved)
                .map_err(|e| Error(format!("Cannot read module {}: {e}", resolved.display())))?;
            if bytes.len() as u64 > MAX_MODULE_BYTES {
                return fail("Imported module bytes exceed source limit");
            }
            if candidate_rel
                .components()
                .next()
                .is_some_and(|x| x.as_os_str() == "vendor")
            {
                let expected = self
                    .verified
                    .as_ref()
                    .and_then(|pins| pins.get(&resolved))
                    .ok_or_else(|| {
                        Error("Unreviewed vendored module import: sedrava.lock required".into())
                    })?;
                let actual = format!("{:x}", Sha256::digest(&bytes));
                if &actual != expected {
                    return fail("Vendored import changed after lock verification");
                }
            }
            let imported = String::from_utf8(bytes).map_err(|e| {
                Error(format!(
                    "Cannot read UTF-8 module {}: {e}",
                    resolved.display()
                ))
            })?;
            for (index, line) in imported.lines().enumerate() {
                // Flat source imports deliberately require explicit nominal IDs
                // instead of silently assigning the entrypoint's identity to
                // an imported error. Namespace aliases are not implemented.
                if line.starts_with("error ") && !line.contains(" id \"") {
                    return fail(format!(
                        "Line {}: {}:{} imported errors require an explicit stable id",
                        number + 1,
                        spec,
                        index + 1
                    ));
                }
                if !permitted_module_line(line) {
                    return fail(format!(
                        "Line {}: {}:{} cannot export app state, actions, rules or tests",
                        number + 1,
                        spec,
                        index + 1
                    ));
                }
            }
            self.files.insert(resolved.clone());
            let expanded = if let Some((_, alias)) = parsed_alias {
                if namespace_exports.contains_key(alias)
                    || !self.used_aliases.insert(alias.to_string())
                {
                    return fail(format!("E_IMPORT_ALIAS: duplicate namespace {alias}"));
                }
                let (lowered, exports) = aliases::lower(&imported, alias)?;
                namespace_exports.insert(alias.to_string(), exports);
                lowered
            } else {
                let mut next_stack = stack.to_vec();
                next_stack.push(resolved.clone());
                self.expand(&imported, &resolved, &next_stack, depth + 1)?
            };
            result.extend(expanded.lines().map(str::to_owned));
            if result
                .iter()
                .map(|line| line.chars().count() + 1)
                .sum::<usize>()
                > MAX_SOURCE_CHARS
            {
                return fail("Expanded imports exceed source limit");
            }
        }
        let output = aliases::qualified(&result.join("\n"), &namespace_exports)?;
        if output.chars().count() > MAX_SOURCE_CHARS {
            return fail("Expanded imports exceed source limit");
        }
        Ok(output)
    }
}

/// Expand imports under the original entrypoint directory; never use cwd
/// as an implicit permission boundary.
pub fn expand_local_imports(entrypoint: &Path) -> Result<ExpandedSource> {
    let canonical = fs::canonicalize(entrypoint)
        .map_err(|e| Error(format!("Source path is inaccessible: {e}")))?;
    let root = canonical
        .parent()
        .ok_or_else(|| Error("Source has no directory".into()))?
        .to_owned();
    if fs::metadata(&canonical)
        .map_err(|e| Error(e.to_string()))?
        .len()
        > MAX_MODULE_BYTES
    {
        return fail("Source file is too large");
    }
    let source =
        fs::read_to_string(&canonical).map_err(|e| Error(format!("Cannot read source: {e}")))?;
    let verified = crate::packages::verify_if_project(&canonical)?;
    let mut expander = Expander {
        root,
        files: BTreeSet::new(),
        used_aliases: BTreeSet::new(),
        raw_generated_name_seen: false,
        verified,
    };
    let output = expander.expand(&source, &canonical, &[canonical.clone()], 0)?;
    if !expander.used_aliases.is_empty() && expander.raw_generated_name_seen {
        return fail("E_IMPORT_ALIAS: original source cannot forge compiler namespace symbols");
    }
    Ok(ExpandedSource {
        source: output,
        imported_paths: expander.files,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn relative_import_validation() {
        for rejected in [
            "../bad.sdr",
            "/etc/passwd.sdr",
            "C:/tmp/file.sdr",
            "x\\y.sdr",
            "./foo.sdr",
            "a/../b.sdr",
        ] {
            assert!(ensure_local_path(rejected).is_err(), "{rejected}");
        }
        assert!(ensure_local_path("assets/normal.sdr").is_ok());
    }
    #[test]
    fn cycle_and_parent_traversal_are_rejected() {
        let dir = tempfile::tempdir().unwrap();
        let entry = dir.path().join("main.sdr");
        let module = dir.path().join("extra.sdr");
        fs::write(&entry, "app \"X\"\nimport \"extra.sdr\"\n").unwrap();
        fs::write(&module, "import \"main.sdr\"\n").unwrap();
        assert!(expand_local_imports(&entry).is_err());
        fs::write(&entry, "app \"X\"\nimport \"../outside.sdr\"\n").unwrap();
        assert!(expand_local_imports(&entry).is_err());
    }
    #[test]
    fn modules_may_not_declare_state_or_actions() {
        let dir = tempfile::tempdir().unwrap();
        let entry = dir.path().join("main.sdr");
        let module = dir.path().join("extra.sdr");
        fs::write(&entry, "app \"X\"\nimport \"extra.sdr\"\n").unwrap();
        fs::write(&module, "state admin = true\n").unwrap();
        assert!(expand_local_imports(&entry).is_err());
    }
    #[test]
    fn imported_pure_function_is_concatenated() {
        let dir = tempfile::tempdir().unwrap();
        let entry = dir.path().join("main.sdr");
        let module = dir.path().join("extra.sdr");
        fs::write(&entry, "app \"X\"\nimport \"extra.sdr\"\nstate n = 1\n").unwrap();
        fs::write(&module, "fn double(n: int) -> int = n * 2\n").unwrap();
        let expanded = expand_local_imports(&entry).unwrap();
        assert_eq!(expanded.imported_paths.len(), 1);
        assert!(expanded.source.contains("fn double(n: int) -> int = n * 2"));
    }
    #[test]
    fn imported_errors_require_explicit_stable_id() {
        let dir = tempfile::tempdir().unwrap();
        let main = dir.path().join("main.sdr");
        let library = dir.path().join("errors.sdr");
        fs::write(&main, "app \"T\"\nimport \"errors.sdr\"\nstate n = 0\n").unwrap();
        fs::write(
            &library,
            "error closed Fault:\n    Bad:\n        code: int\n",
        )
        .unwrap();
        assert!(expand_local_imports(&main).is_err());
        fs::write(
            &library,
            "error closed Fault id \"example.Fault\":\n    Bad:\n        code: int\n",
        )
        .unwrap();
        let result = expand_local_imports(&main).unwrap();
        assert!(result.source.contains("example.Fault"));
    }

    #[cfg(unix)]
    #[test]
    fn symlink_imports_are_rejected() {
        use std::os::unix::fs::symlink;
        let dir = tempfile::tempdir().unwrap();
        let entry = dir.path().join("main.sdr");
        let module = dir.path().join("real.sdr");
        fs::write(&entry, "app \"X\"\nimport \"alias.sdr\"\n").unwrap();
        fs::write(&module, "fn add(n: int) -> int = n + 1\n").unwrap();
        symlink(&module, dir.path().join("alias.sdr")).unwrap();
        assert!(expand_local_imports(&entry).is_err());
    }
}
