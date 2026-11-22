//! Experimental Sedrava native core: records, lists and navigation remain nonproduction.
//!
//! This crate deliberately rejects unsupported constructs, rather than silently
//! changing their meaning. It is not a drop-in replacement for the Python 0.11
//! compiler: site/webapp modes, full UI generation, imports and host effects
//! remain in Python until native conformance is demonstrated.

pub mod collections;
pub mod expr;
pub mod model;
pub mod navigation;
pub mod parser;
pub mod runtime;
pub mod stdlib;

pub use model::{Error, Kind, Program, Result, State, Value};
pub use parser::parse;
pub use runtime::{run_actions, run_tests, transition};

#[cfg(test)]
mod conformance {
    use super::*;

    #[test]
    fn rejects_navigation_only_widgets_without_navigation() {
        assert!(parse("app \"T\"\nstate n = 1\nscreen main:\n    display n\n").is_err());
        assert!(parse("app \"T\"\nstate n = 1\nscreen main:\n    input n label \"N\"\n").is_err());
    }

    #[test]
    fn native_navigation_matches_existing_app() {
        let p = parse(include_str!(
            "../../../examples/task_manager_navigation.sdr"
        ))
        .unwrap();
        assert_eq!(run_tests(&p).unwrap(), 1);
        assert!(p.has_navigation);
        let (values, stack) = crate::navigation::run_session(&p, &[]).unwrap();
        assert_eq!(stack, vec!["main"]);
        assert_eq!(values.get("chosen"), Some(&Value::Bool(false)));
    }

    #[test]
    fn navigation_and_lazy_queries() {
        let p = parse(include_str!("../../../tests/rust_cases/navigation.sdr")).unwrap();
        assert_eq!(run_tests(&p).unwrap(), 2);
        let (values, stack) =
            crate::navigation::run_session(&p, &["open".into(), "step".into(), "$back".into()])
                .unwrap();
        assert_eq!(values.get("count"), Some(&Value::Int(2)));
        assert_eq!(stack, vec!["main"]);

        let p = parse(include_str!("../../../tests/rust_cases/lazy_queries.sdr")).unwrap();
        assert_eq!(run_tests(&p).unwrap(), 3);
    }

    #[test]
    fn parses_existing_counter_and_executes_tests() {
        let p = parse(include_str!("../../../examples/counter.sdr")).unwrap();
        assert_eq!(run_tests(&p).unwrap(), 2);
        let r = run_actions(&p, &["increment".into(), "increment".into()]).unwrap();
        assert_eq!(r.get("count"), Some(&Value::Int(2)));
    }

    #[test]
    fn parses_reference_09_and_executes_tests() {
        let p = parse(include_str!("../../../examples/reference_09.sdr")).unwrap();
        assert_eq!(run_tests(&p).unwrap(), 4);
        let r = run_actions(&p, &["add".into(), "add".into()]).unwrap();
        assert_eq!(r.get("progress"), Some(&Value::Int(2)));
        assert_eq!(r.get("sessions"), Some(&Value::Int(2)));
    }

    #[test]
    fn parses_unicode_profile_and_executes_tests() {
        let p = parse(include_str!("../../../examples/text_profile.sdr")).unwrap();
        assert_eq!(run_tests(&p).unwrap(), 3);
        let r = run_actions(&p, &["rename".into()]).unwrap();
        assert_eq!(r.get("name"), Some(&Value::Text("Алиса 😀".into())));
    }

    #[test]
    fn record_collection_semantics_match_existing_fixtures() {
        let p = parse(include_str!("../../../tests/rust_cases/records_lists.sdr")).unwrap();
        assert_eq!(run_tests(&p).unwrap(), 4);
        let state = run_actions(&p, &["add".into(), "finish".into()]).unwrap();
        assert_eq!(state.get("done_total"), Some(&Value::Int(1)));
        assert_eq!(state.get("first_done"), Some(&Value::Int(1)));
    }

    #[test]
    fn pure_functions_standard_library_and_queries() {
        let p = parse(include_str!(
            "../../../tests/rust_cases/functions_queries.sdr"
        ))
        .unwrap();
        assert_eq!(run_tests(&p).unwrap(), 3);
        let state = run_actions(&p, &["add".into()]).unwrap();
        assert_eq!(
            state.get("leap_end"),
            Some(&Value::Text("2024-03-01".into()))
        );
        assert_eq!(state.get("score_total"), Some(&Value::Int(2)));
        assert_eq!(state.get("matches_count"), Some(&Value::Int(1)));
    }

    #[test]
    fn parses_existing_task_manager_with_records_and_lists() {
        let p = parse(include_str!("../../../examples/task_manager.sdr")).unwrap();
        assert_eq!(run_tests(&p).unwrap(), 1);
        let values = run_actions(&p, &[]).unwrap();
        assert!(matches!(values.get("tasks"), Some(Value::List { .. })));
    }
}
