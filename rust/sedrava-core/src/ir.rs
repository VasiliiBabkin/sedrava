//! Deterministic JSON representation of the experimental typed app IR.
//! This format is intentionally versioned and NOT yet a stable public ABI.
use crate::model::{Error, Program, Result};
use serde_json::{json, Value as Json};

pub const IR_SCHEMA: &str = "sedrava-native-typed-ir";
pub const IR_VERSION: u32 = 1;

pub fn export(program: &Program) -> Result<Json> {
    let ir = json!({
        "schema": IR_SCHEMA,
        "version": IR_VERSION,
        "status": "experimental-app-subset",
        "project": &program.name,
        "state_types": &program.types,
        "state_defaults": &program.states,
        "state_order": &program.state_order,
        "persistent": &program.persistent,
        "declarations": &program.declaration_spans,
        "derived": &program.derives,
        "functions": &program.functions,
        "actions": &program.actions,
        "rules": &program.rules,
        "tests": &program.tests,
        "screens": &program.screens,
        "navigation": &program.navigation,
        "initial_screen": &program.initial_screen,
        "has_navigation": program.has_navigation,
        "limitations": [
            "Not a stable external IR",
            "Source spans cover top-level declarations, not all AST nodes",
            "Site/WebApp, Host effects, imports and code generation not represented"
        ]
    });
    if ir.as_object().and_then(|v| v.get("state_order")).is_none() {
        return Err(Error("IR encoding failed".into()));
    }
    Ok(ir)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::parser::parse;

    #[test]
    fn stable_schema_and_top_level_spans() {
        let program = parse(
            "app \"IR\"\nstate count = 0\n\
           derive double = count * 2\n\
           action add: count = count + 1\n\
           test initial: -> count == 0\n\
           screen main:\n    text \"Hi\"\n",
        )
        .unwrap();
        let exported = export(&program).unwrap();
        assert_eq!(exported["schema"], IR_SCHEMA);
        assert_eq!(exported["version"], IR_VERSION);
        assert_eq!(exported["declarations"]["state:count"]["line"], 2);
        assert_eq!(exported["state_order"][0], "count");
        assert_eq!(export(&program).unwrap(), exported);
    }
}
