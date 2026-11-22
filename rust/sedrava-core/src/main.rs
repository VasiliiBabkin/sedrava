//! Standalone CLI for the experimental Rust engine; no Python required.
//! Differences from Python 0.11 are intentionally documented.

use sedrava_core::{parse, run_actions, run_tests, Error, Result};
use serde_json::json;
use std::env;
use std::fs;
use std::path::Path;

fn usage() {
    println!(
        "Sedrava native Rust core (EXPERIMENTAL)\n\
         Usage:\n\
           sedrava-native check FILE\n\
           sedrava-native test FILE\n\
           sedrava-native run FILE [ACTION ...]\n\
           sedrava-native inspect FILE\n\
         Not supported: Web/Android generation, database, records, collections,\n\
         navigation, functions, persistence, and the full 0.11 language.\n\
         See docs/RUST_CORE_MIGRATION.ru.md. Do not use for production."
    );
}

fn load(path: &str) -> Result<sedrava_core::Program> {
    let metadata = fs::metadata(path).map_err(|e| Error(format!("Cannot stat {path}: {e}")))?;
    if metadata.len() > (sedrava_core::model::MAX_SOURCE_CHARS as u64) * 4 {
        return Err(Error("Source file exceeds size limit".into()));
    }
    let raw = fs::read_to_string(Path::new(path))
        .map_err(|e| Error(format!("Cannot read {path}: {e}")))?;
    parse(&raw)
}

fn run() -> Result<()> {
    let args: Vec<String> = env::args().collect();
    if args.len() == 1 || args.get(1).is_some_and(|s| s == "--help" || s == "-h") {
        usage();
        return Ok(());
    }
    if args[1] == "--version" {
        println!("sedrava-native 0.1.0-alpha.1 (experimental Rust scalar core)");
        return Ok(());
    }
    if args.len() < 3 {
        usage();
        return Err(Error("Expected a command and a .sdr file".into()));
    }
    let command = &args[1];
    let source = &args[2];
    let program = load(source)?;
    match command.as_str() {
        "check" if args.len() == 3 => {
            println!("OK: {source}");
        }
        "test" if args.len() == 3 => {
            println!("PASS: {} Sedrava tests", run_tests(&program)?);
        }
        "run" => {
            if program.has_navigation {
                let (state, stack) = sedrava_core::navigation::run_session(&program, &args[3..])?;
                println!(
                    "{}",
                    serde_json::to_string(&json!({"state":state,"stack":stack}))
                        .map_err(|e| Error(e.to_string()))?
                );
            } else {
                let values = run_actions(&program, &args[3..])?;
                println!(
                    "{}",
                    serde_json::to_string(&values).map_err(|e| Error(e.to_string()))?
                );
            }
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
