//! Experimental Sedrava native scalar core.
//!
//! This crate deliberately rejects unsupported constructs, rather than silently
//! changing their meaning. It is not a drop-in replacement for the Python 0.11
//! compiler: collections, records, pure functions, navigation and codegen
//! remain in Python until native conformance is demonstrated.

pub mod expr;
pub mod model;
pub mod parser;
pub mod runtime;

pub use model::{Error, Kind, Program, Result, State, Value};
pub use parser::parse;
pub use runtime::{run_actions, run_tests, transition};

#[cfg(test)]
mod conformance {
    use super::*;

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
    fn rejects_unsupported_record_program() {
        assert!(parse(include_str!("../../../examples/task_manager.sdr")).is_err());
    }
}
