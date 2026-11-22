//! Pure state-machine runtime: no filesystem, network, clocks, randomness or eval.
//! Actions operate on a candidate copy; rule failures never publish it.

use crate::expr;
use crate::model::{
    fail, validate, Error, Program, Result, State, Stmt, Value, MAX_ACTION_STEPS,
    MAX_SNAPSHOT_UTF16,
};

/// Resolve every derived value from the accepted state in declaration order.
pub fn resolve(program: &Program, state: &State) -> Result<State> {
    if state.len() != program.states.len() || state.keys().ne(program.states.keys()) {
        return fail("Invalid action input state: state keys differ");
    }
    let mut values = state.clone();
    for (key, value) in state {
        let expected = program
            .types
            .get(key)
            .ok_or_else(|| Error(format!("Missing state type: {key}")))?;
        validate(value, expected).map_err(|e| Error(format!("State {key}: {e}")))?;
    }
    for (name, expression) in &program.derives {
        let value = expr::evaluate_full(expression, &values, &program.types, &program.functions)?;
        let expected = program
            .types
            .get(name)
            .ok_or_else(|| Error(format!("Missing derived type for {name}")))?;
        validate(&value, expected).map_err(|e| Error(format!("Derived {name}: {e}")))?;
        values.insert(name.to_owned(), value);
    }
    // Preserve resource budgeting for records and bounded collections.
    if state
        .values()
        .any(|v| matches!(v, Value::List { .. } | Value::Record { .. }))
    {
        let encoded = serde_json::to_string(&state)
            .map_err(|e| Error(format!("Cannot serialize state: {e}")))?;
        if encoded.encode_utf16().count() > MAX_SNAPSHOT_UTF16 {
            return fail("State exceeds snapshot resource limit");
        }
    }
    Ok(values)
}

pub fn rules_hold(program: &Program, values: &State) -> Result<bool> {
    for condition in &program.rules {
        if expr::evaluate_full(condition, values, &program.types, &program.functions)?
            != Value::Bool(true)
        {
            return Ok(false);
        }
    }
    Ok(true)
}

pub fn valid_state(program: &Program, state: &State) -> bool {
    match resolve(program, state) {
        Ok(values) => rules_hold(program, &values).unwrap_or(false),
        Err(_) => false,
    }
}

fn execute_block(
    program: &Program,
    candidate: &mut State,
    block: &[Stmt],
    locals: &mut State,
    steps: &mut usize,
) -> Result<()> {
    for statement in block {
        *steps += 1;
        if *steps > MAX_ACTION_STEPS {
            return fail("Action exceeds execution step limit");
        }
        let mut environment = resolve(program, candidate)?;
        environment.extend(locals.clone());
        match statement {
            Stmt::Assign(key, expression) => {
                let value = expr::evaluate_full(
                    expression,
                    &environment,
                    &program.types,
                    &program.functions,
                )?;
                candidate.insert(key.clone(), value);
                // Even when rules are checked only on final candidate, derived
                // expressions must remain computable after *each* assignment.
                resolve(program, candidate)?;
            }
            Stmt::Let(name, expression) => {
                locals.insert(
                    name.to_string(),
                    expr::evaluate_full(
                        expression,
                        &environment,
                        &program.types,
                        &program.functions,
                    )?,
                );
            }
            Stmt::Require(condition) => {
                if expr::evaluate_full(condition, &environment, &program.types, &program.functions)?
                    != Value::Bool(true)
                {
                    return fail("Action requirement rejected");
                }
            }
            Stmt::Match(expression, arms) => {
                use crate::model::MatchPattern;
                // Evaluate the subject exactly once. A candidate state is
                // published only by transition() after all branches succeed.
                let value = expr::evaluate_full(
                    expression,
                    &environment,
                    &program.types,
                    &program.functions,
                )?;
                let Value::Result { ok, value, .. } = value else {
                    return fail("E_MATCH: action subject must be Result");
                };
                let mut chosen = None;
                for arm in arms {
                    let mut bound = locals.clone();
                    let matches = match (&arm.pattern, ok, value.as_ref()) {
                        (MatchPattern::Ok(key), true, any) => {
                            bound.insert(key.clone(), any.clone());
                            true
                        }
                        (
                            MatchPattern::Variant { name, bindings },
                            false,
                            Value::Error {
                                variant, fields, ..
                            },
                        ) if name == variant => {
                            for (field, alias) in bindings {
                                let item = fields.get(field).ok_or_else(|| {
                                    Error("E_MATCH: missing checked error field".into())
                                })?;
                                bound.insert(alias.clone(), item.clone());
                            }
                            true
                        }
                        (MatchPattern::Fallback(key), false, err @ Value::Error { .. }) => {
                            bound.insert(key.clone(), err.clone());
                            true
                        }
                        _ => false,
                    };
                    if matches {
                        chosen = Some((&arm.body, bound));
                        break;
                    }
                }
                let Some((branch, mut bound)) = chosen else {
                    return fail("E_MATCH: exhaustive branch not found");
                };
                execute_block(program, candidate, branch, &mut bound, steps)?;
            }
            Stmt::Branch(condition, yes, no) => {
                let branch = if expr::evaluate_full(
                    condition,
                    &environment,
                    &program.types,
                    &program.functions,
                )? == Value::Bool(true)
                {
                    yes
                } else {
                    no
                };
                execute_block(program, candidate, branch, &mut locals.clone(), steps)?;
            }
        }
    }
    Ok(())
}

/// Returns (new_state, accepted). A rejected invariant returns old state.
/// A requirement/overflow/unknown action is a separate error.
pub fn transition(program: &Program, state: &State, action: &str) -> Result<(State, bool)> {
    if !valid_state(program, state) {
        return fail("Invalid action input state");
    }
    let body = program
        .actions
        .get(action)
        .ok_or_else(|| Error(format!("Unknown action: {action}")))?;
    let mut candidate = state.clone();
    execute_block(program, &mut candidate, body, &mut State::new(), &mut 0)?;
    let final_values = resolve(program, &candidate)?;
    if !rules_hold(program, &final_values)? {
        return Ok((state.clone(), false));
    }
    Ok((candidate, true))
}

pub fn run_actions(program: &Program, actions: &[String]) -> Result<State> {
    run_actions_from(program, &program.states, actions)
}

pub fn run_actions_from(program: &Program, initial: &State, actions: &[String]) -> Result<State> {
    let mut state = initial.clone();
    for action in actions {
        let (candidate, accepted) = transition(program, &state, action)?;
        if !accepted {
            return fail(format!(
                "Action {action}: invariant rejected; state unchanged"
            ));
        }
        state = candidate;
    }
    resolve(program, &state)
}

/// Execute embedded tests through exactly the same transition function as CLI run.
pub fn run_tests(program: &Program) -> Result<usize> {
    for test in &program.tests {
        if program.has_navigation {
            let (state, _) = crate::navigation::run_session(program, &test.actions)
                .map_err(|e| Error(format!("{}: {e}", test.name)))?;
            if expr::evaluate_full(&test.expected, &state, &program.types, &program.functions)?
                != Value::Bool(true)
            {
                return fail(format!("{}: assertion failed", test.name));
            }
            continue;
        }
        let mut state = program.states.clone();
        for action in &test.actions {
            let (candidate, accepted) = transition(program, &state, action)
                .map_err(|e| Error(format!("{}: {e}", test.name)))?;
            if !accepted {
                return fail(format!("{}: invariant violated", test.name));
            }
            state = candidate;
        }
        let values = resolve(program, &state)?;
        if expr::evaluate_full(&test.expected, &values, &program.types, &program.functions)?
            != Value::Bool(true)
        {
            return fail(format!("{}: assertion failed", test.name));
        }
    }
    Ok(program.tests.len())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::parser::parse;

    #[test]
    fn atomic_invariant_rejection_keeps_previous_state() {
        let p = parse(
            "app \"T\"\nstate a = 0\nstate b = 0\n\
             action bad:\n    a = 1\n    b = -1\n\
             rule b >= 0",
        )
        .unwrap();
        let (state, accepted) = transition(&p, &p.states, "bad").unwrap();
        assert!(!accepted);
        assert_eq!(state, p.states);
    }

    #[test]
    fn require_failure_keeps_state_unchanged() {
        let p = parse(
            "app \"T\"\nstate n = 0\n\
             action fail:\n    n = 1\n    require false",
        )
        .unwrap();
        assert!(transition(&p, &p.states, "fail").is_err());
        assert_eq!(p.states.get("n"), Some(&Value::Int(0)));
    }

    #[test]
    fn derived_and_local_value_semantics() {
        let p = parse(
            "app \"T\"\nstate n = 0\nderive positive = n > 0\n\
             action add:\n    let next = n + 1\n    n = next\n\
             test once: add -> n == 1 and positive",
        )
        .unwrap();
        assert_eq!(run_tests(&p).unwrap(), 1);
        let state = run_actions(&p, &["add".into()]).unwrap();
        assert_eq!(state.get("positive"), Some(&Value::Bool(true)));
    }

    #[test]
    fn nesting_and_if_branch() {
        let p = parse(
            "app \"T\"\nstate n = 0\n\
             action act:\n    if n == 0:\n        n = n + 5\n    else:\n        n = n - 1",
        )
        .unwrap();
        assert_eq!(
            run_actions(&p, &["act".into(), "act".into()])
                .unwrap()
                .get("n"),
            Some(&Value::Int(4))
        );
    }
}
