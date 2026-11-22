//! Bounded navigation stack and all-or-nothing domain transitions.

use crate::expr;
use crate::model::{Error, Program, Result, State, Value};
use crate::runtime::{resolve, transition, valid_state};

const MAX_STACK: usize = 32;

#[derive(Clone, Debug)]
pub struct Session {
    pub state: State,
    pub stack: Vec<String>,
}

pub fn visible(program: &Program, state: &State, screen: &str) -> bool {
    let Some(screen) = program.screens.get(screen) else {
        return false;
    };
    match &screen.guard {
        None => true,
        Some(guard) => {
            let Ok(values) = resolve(program, state) else {
                return false;
            };
            matches!(
                expr::evaluate_full(guard, &values, &program.types, &program.functions),
                Ok(Value::Bool(true))
            )
        }
    }
}

fn normalize(program: &Program, state: State, mut stack: Vec<String>) -> Session {
    while stack.len() > 1 && !visible(program, &state, stack.last().unwrap()) {
        stack.pop();
    }
    Session { state, stack }
}

pub fn initial(program: &Program) -> Result<Session> {
    if !valid_state(program, &program.states) {
        return Err(Error("Invalid initial session state".into()));
    }
    Ok(Session {
        state: program.states.clone(),
        stack: vec![program.initial_screen.clone()],
    })
}

fn stack_valid(program: &Program, session: &Session) -> bool {
    !session.stack.is_empty()
        && session.stack.len() <= MAX_STACK
        && session.stack.first() == Some(&program.initial_screen)
        && session
            .stack
            .iter()
            .all(|name| program.screens.contains_key(name))
}

pub fn dispatch(program: &Program, session: &Session, command: &str) -> (Session, bool) {
    if !stack_valid(program, session) || !valid_state(program, &session.state) {
        return (session.clone(), false);
    }
    let mut state = session.state.clone();
    let mut stack = session.stack.clone();
    if command == "$back" {
        if stack.len() > 1 {
            stack.pop();
        }
    } else if let Some(binding) = program.navigation.get(command) {
        if let Some(action) = &binding.action {
            let Ok((next, accepted)) = transition(program, &state, action) else {
                return (session.clone(), false);
            };
            if !accepted {
                return (session.clone(), false);
            }
            state = next;
        }
        if binding.target == "pop" {
            if stack.len() > 1 {
                stack.pop();
            }
        } else {
            if stack.len() >= MAX_STACK || !visible(program, &state, &binding.target) {
                return (session.clone(), false);
            }
            stack.push(binding.target.clone());
        }
    } else if program.actions.contains_key(command) {
        let Ok((next, accepted)) = transition(program, &state, command) else {
            return (session.clone(), false);
        };
        if !accepted {
            return (session.clone(), false);
        }
        state = next;
    } else {
        return (session.clone(), false);
    }
    (normalize(program, state, stack), true)
}

pub fn run_session(program: &Program, actions: &[String]) -> Result<(State, Vec<String>)> {
    let mut session = initial(program)?;
    for action in actions {
        let (next, accepted) = dispatch(program, &session, action);
        if !accepted {
            return Err(Error(format!(
                "Action {action}: invariant rejected; state unchanged"
            )));
        }
        session = next;
    }
    Ok((resolve(program, &session.state)?, session.stack))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::parser::parse;

    #[test]
    fn back_keeps_root_visible() {
        let p = parse("app \"T\"\nstate n = 0\nscreen main:\n    text \"T\"\n").unwrap();
        let session = initial(&p).unwrap();
        let (next, ok) = dispatch(&p, &session, "$back");
        assert!(ok);
        assert_eq!(next.stack, vec!["main"]);
    }
}
