//! Standalone CLI for the experimental Rust engine; no Python required.
//! Differences from Python 0.11 are intentionally documented.

use sedrava_core::navigation::run_session_from;
use sedrava_core::runtime::resolve;
use sedrava_core::snapshot::{restore_snapshot, serialize_state};
use sedrava_core::{parse, run_tests, Error, Result};
use serde_json::json;
use std::env;
use std::fs;
use std::io::Write;
use std::path::{Path, PathBuf};

fn usage() {
    println!(
        "Sedrava native Rust core (EXPERIMENTAL)\n\
         Usage:\n\
           sedrava-native check FILE\n\
           sedrava-native test FILE\n\
           sedrava-native run FILE [ACTION ...] [--state-file PATH]\n\
           sedrava-native inspect FILE
           sedrava-native ir FILE
           sedrava-native expand FILE
           sedrava-native build web FILE [--output PATH]\n\
         Supports typed records, bounded lists, pure functions, navigation,\n\
         snapshot persistence and experimental typed IR export.\n\
         Not supported: Web/Android generation, site/webapp DSL, component expansion,\n\
         Host Effects or the full 0.11 language.\n\
         See docs/RUST_CORE_MIGRATION.ru.md. Do not use for production."
    );
}

fn load(path: &str) -> Result<sedrava_core::Program> {
    let metadata = fs::metadata(path).map_err(|e| Error(format!("Cannot stat {path}: {e}")))?;
    if metadata.len() > (sedrava_core::model::MAX_SOURCE_CHARS as u64) * 4 {
        return Err(Error("Source file exceeds size limit".into()));
    }
    let expanded = sedrava_core::modules::expand_local_imports(Path::new(path))?;
    parse(&expanded.source)
}

/// Persist after successfully validating every action. No in-place truncation.
fn write_snapshot(path: &Path, raw: &str) -> Result<()> {
    let parent = path
        .parent()
        .filter(|p| !p.as_os_str().is_empty())
        .unwrap_or(Path::new("."));
    fs::create_dir_all(parent)
        .map_err(|e| Error(format!("Cannot create snapshot directory: {e}")))?;
    let mut temp = tempfile::NamedTempFile::new_in(parent)
        .map_err(|e| Error(format!("Cannot prepare temporary snapshot: {e}")))?;
    temp.write_all(raw.as_bytes())
        .map_err(|e| Error(format!("Cannot write snapshot: {e}")))?;
    temp.flush()
        .map_err(|e| Error(format!("Cannot flush snapshot: {e}")))?;
    temp.as_file()
        .sync_all()
        .map_err(|e| Error(format!("Cannot sync snapshot: {e}")))?;
    temp.persist(path)
        .map_err(|e| Error(format!("Cannot atomically replace snapshot: {e}")))?;
    // Directory sync is supported on Unix but not universally on Windows.
    #[cfg(unix)]
    {
        let dir = fs::File::open(parent)
            .map_err(|e| Error(format!("Cannot open snapshot directory for sync: {e}")))?;
        dir.sync_all()
            .map_err(|e| Error(format!("Cannot sync snapshot directory: {e}")))?;
    }
    Ok(())
}

fn read_snapshot(path: &Path) -> Result<String> {
    let meta = fs::metadata(path).map_err(|e| Error(format!("Cannot stat snapshot: {e}")))?;
    if meta.len() > 800_000 {
        return Err(Error("Snapshot file too large".into()));
    }
    fs::read_to_string(path).map_err(|e| Error(format!("Cannot read snapshot: {e}")))
}

/// The Python CLI accepts --state-file before or after the action list.
fn run_options(args: &[String]) -> Result<(Vec<String>, Option<PathBuf>)> {
    let mut actions = Vec::new();
    let mut state_file = None;
    let mut index = 0;
    while index < args.len() {
        if args[index] == "--state-file" {
            if state_file.is_some() || index + 1 >= args.len() {
                return Err(Error("Expected exactly one --state-file PATH".into()));
            }
            state_file = Some(PathBuf::from(&args[index + 1]));
            index += 2;
        } else {
            if args[index].starts_with("--") {
                return Err(Error(format!("Unknown run option: {}", args[index])));
            }
            actions.push(args[index].clone());
            index += 1;
        }
    }
    Ok((actions, state_file))
}

fn run() -> Result<()> {
    let args: Vec<String> = env::args().collect();
    if args.len() == 1 || args.get(1).is_some_and(|s| s == "--help" || s == "-h") {
        usage();
        return Ok(());
    }
    if args[1] == "--version" {
        println!("sedrava-native 0.1.0-alpha.1 (experimental partial Sedrava core)");
        return Ok(());
    }
    if args.len() < 3 {
        usage();
        return Err(Error("Expected a command and a .sdr file".into()));
    }
    let command = &args[1];
    let is_build = command == "build";
    if is_build && args.get(2).map(String::as_str) != Some("web") {
        return Err(Error(
            "Only scalar build web is supported natively; other targets are not migrated".into(),
        ));
    }
    let source_index = if is_build { 3 } else { 2 };
    let source = args
        .get(source_index)
        .ok_or_else(|| Error("Expected a command, target and .sdr file".into()))?;
    if is_build {
        let output = if args.len() == 4 {
            PathBuf::from("build/web/index.html")
        } else if args.len() == 6 && args[4] == "--output" {
            PathBuf::from(&args[5])
        } else {
            return Err(Error("Expected build web FILE [--output PATH]".into()));
        };
        let expanded = sedrava_core::modules::expand_local_imports(Path::new(source))?;
        let program = parse(&expanded.source)?;
        let generated = sedrava_core::web::generate_web(&program)?;
        let source_path = fs::canonicalize(source).map_err(|e| Error(e.to_string()))?;
        let parent = output
            .parent()
            .filter(|p| !p.as_os_str().is_empty())
            .unwrap_or(Path::new("."));
        let parent_real = if parent.exists() {
            fs::canonicalize(parent).map_err(|e| Error(e.to_string()))?
        } else {
            fs::create_dir_all(parent).map_err(|e| Error(e.to_string()))?;
            fs::canonicalize(parent).map_err(|e| Error(e.to_string()))?
        };
        let file_name = output
            .file_name()
            .ok_or_else(|| Error("Build output must be a file".into()))?;
        let output_canonical = parent_real.join(file_name);
        if output_canonical == source_path || expanded.imported_paths.contains(&output_canonical) {
            return Err(Error(
                "Web output must not overwrite the source or an imported module".into(),
            ));
        }
        write_snapshot(&output, &generated)?;
        // Snapshots deliberately use private tempfile permissions. Generated
        // static web artifacts, in contrast, must be readable by web servers.
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            fs::set_permissions(&output, fs::Permissions::from_mode(0o644))
                .map_err(|e| Error(format!("Cannot make generated web output readable: {e}")))?;
        }
        println!("{}", output.display());
        return Ok(());
    }
    if command == "expand" && args.len() == 3 {
        let expanded = sedrava_core::modules::expand_local_imports(Path::new(source))?;
        print!("{}", expanded.source);
        return Ok(());
    }
    let program = load(source)?;
    match command.as_str() {
        "check" if args.len() == 3 => {
            println!("OK: {source}");
        }
        "test" if args.len() == 3 => {
            println!("PASS: {} Sedrava tests", run_tests(&program)?);
        }
        "run" => {
            let (actions, state_file) = run_options(&args[3..])?;
            if let Some(path) = state_file.as_deref() {
                if path.exists() && fs::canonicalize(path).ok() == fs::canonicalize(source).ok() {
                    return Err(Error("Snapshot must differ from source file".into()));
                }
            }
            let initial = if let Some(path) = state_file.as_deref().filter(|path| path.exists()) {
                restore_snapshot(&program, &read_snapshot(path)?)?
            } else {
                program.states.clone()
            };
            let (final_state, output) = if program.has_navigation {
                let (state, stack) = run_session_from(&program, &initial, &actions)?;
                let values = resolve(&program, &state)?;
                let result = json!({"state":values,"stack":stack});
                (state, result)
            } else {
                let mut state = initial;
                for action in &actions {
                    let (next, accepted) = sedrava_core::transition(&program, &state, action)?;
                    if !accepted {
                        return Err(Error(format!(
                            "Action {action}: invariant rejected; state unchanged"
                        )));
                    }
                    state = next;
                }
                let result = serde_json::to_value(resolve(&program, &state)?)
                    .map_err(|e| Error(e.to_string()))?;
                (state, result)
            };
            if let Some(path) = state_file.as_deref() {
                // Serialization occurs before any filesystem write.
                let snapshot = serialize_state(&program, &final_state)?;
                write_snapshot(path, &snapshot)?;
            }
            println!(
                "{}",
                serde_json::to_string(&output).map_err(|e| Error(e.to_string()))?
            );
        }
        "ir" if args.len() == 3 => {
            let ir = sedrava_core::ir::export(&program)?;
            println!(
                "{}",
                serde_json::to_string_pretty(&ir).map_err(|e| Error(e.to_string()))?
            );
        }
        "inspect" if args.len() == 3 => {
            let output = json!({
                "engine": "rust-native-experimental",
                "project": program.name,
                "state_types": program.types,
                "actions": program.actions.keys().cloned().collect::<Vec<_>>(),
                "embedded_tests": program.tests.iter().map(|t| &t.name).collect::<Vec<_>>(),
                 "supported": "int32/bool/text, records, bounded lists, pure functions, queries, derives, rules, actions, tests, navigation",
                "full_language": false
            });
            println!(
                "{}",
                serde_json::to_string_pretty(&output).map_err(|e| Error(e.to_string()))?
            );
        }
        _ => {
            usage();
            return Err(Error(format!(
                "Unknown command or extra arguments: {command}"
            )));
        }
    }
    Ok(())
}

fn main() {
    if let Err(error) = run() {
        eprintln!("error: {error}");
        std::process::exit(1);
    }
}
