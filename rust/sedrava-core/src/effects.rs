//! Static Effects & Targets A1 for the already-checked app-domain pure function IR.
//!
//! An app-domain effect manifest is deliberately NOT a runtime permission grant,
//! a security proof for UI/storage, or a Host/server capabilities manifest.
use crate::model::{fail, Error, Expr, Kind, Program, PureFunction, Result};
use serde::Serialize;
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};

const MAX_FUNCTIONS: usize = 32;
const MAX_CALLS: usize = 256;
pub const SCHEMA: &str = "sedrava.effects.v1";
pub const KNOWN_EFFECTS: &[&str] = &[
    "host.fs.read",
    "host.fs.write",
    "host.fs.list",
    "host.fs.mkdir",
    "host.fs.rmdir",
    "server.db.read",
    "server.db.write",
    "server.http",
    "web.api",
];

fn identifier(name: &str) -> bool {
    let mut chars = name.chars();
    matches!(chars.next(), Some(x) if x == '_' || x.is_ascii_alphabetic())
        && chars.all(|x| x == '_' || x.is_ascii_alphanumeric())
}

pub fn normalize_effects(names: &[String]) -> Result<BTreeSet<String>> {
    let mut result = BTreeSet::new();
    for name in names {
        if !KNOWN_EFFECTS.contains(&name.as_str()) || !result.insert(name.clone()) {
            return fail("Unknown or duplicate effect identifier");
        }
    }
    Ok(result)
}

pub fn require_target(target: &str, effects: &BTreeSet<String>) -> Result<()> {
    let permitted: BTreeSet<&str> = match target {
        "app" | "android" | "site" => BTreeSet::new(),
        "web" | "webapp" => ["web.api"].into_iter().collect(),
        "host" => KNOWN_EFFECTS
            .iter()
            .copied()
            .filter(|effect| effect.starts_with("host."))
            .collect(),
        "server" => KNOWN_EFFECTS
            .iter()
            .copied()
            .filter(|effect| effect.starts_with("server."))
            .collect(),
        _ => return fail("Unknown compilation target"),
    };
    normalize_effects(&effects.iter().cloned().collect::<Vec<_>>())?;
    let unsupported: Vec<_> = effects
        .iter()
        .filter(|effect| !permitted.contains(effect.as_str()))
        .map(String::as_str)
        .collect();
    if !unsupported.is_empty() {
        return fail(format!(
            "E_TARGET_EFFECT: {target} does not support {}",
            unsupported.join(", ")
        ));
    }
    Ok(())
}

#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
pub struct FunctionEffect {
    pub name: String,
    pub direct: BTreeSet<String>,
    pub effective: BTreeSet<String>,
    pub declared: Option<BTreeSet<String>>,
}

#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
pub struct FunctionManifest {
    pub declared: Option<Vec<String>>,
    pub effective: Vec<String>,
    pub name: String,
}

#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
pub struct Manifest {
    pub effective: Vec<String>,
    pub functions: Vec<FunctionManifest>,
    pub kind: &'static str,
    pub schema: &'static str,
    pub source_sha256: String,
    pub target: String,
}

const PURE_COLLECTIONS: &[&str] = &[
    "result_ok",
    "result_or",
    "count",
    "next_id",
    "append",
    "update",
    "remove",
    "get",
    "has",
    "filter",
    "map",
    "find",
    "any",
    "all",
    "sort",
    "sum",
];
const QUERY_OPERATORS: &[&str] = &["filter", "map", "find", "any", "all", "sort", "sum"];

struct Scanner<'a> {
    symbols: &'a BTreeMap<String, Kind>,
    functions: &'a BTreeMap<String, PureFunction>,
    primitives: &'a BTreeMap<String, BTreeSet<String>>,
    edges: BTreeSet<String>,
    direct: BTreeSet<String>,
    calls: usize,
}

impl Scanner<'_> {
    fn scan(&mut self, value: &Expr) -> Result<()> {
        match value {
            Expr::Call { name, args, kwargs } => {
                self.calls += 1;
                if self.calls > MAX_CALLS {
                    return fail("Function call graph exceeds resource limit");
                }
                if let Some(function) = self.functions.get(name) {
                    let Some(Kind::Function { parameters, result }) = self.symbols.get(name) else {
                        return fail(format!("Unchecked call edge in typed function IR: {name}"));
                    };
                    if parameters
                        != &function
                            .parameters
                            .iter()
                            .map(|(_, k)| k.clone())
                            .collect::<Vec<_>>()
                        || result.as_ref() != &function.result
                    {
                        return fail(format!(
                            "Function call metadata does not match typed IR: {name}"
                        ));
                    }
                    self.edges.insert(name.clone());
                } else if let Some(effects) = self.primitives.get(name) {
                    // A runtime primitive is never implicitly callable merely
                    // because it has an entry in an effects manifest.
                    if !matches!(self.symbols.get(name), Some(Kind::Function { .. })) {
                        return fail(format!("Unregistered primitive signature: {name}"));
                    }
                    self.direct.extend(effects.iter().cloned());
                } else if (matches!(name.as_str(), "Ok" | "Err" | "error_id")
                    && !self.symbols.contains_key(name))
                    || name.split_once('.').is_some_and(|(family, _)| {
                        matches!(self.symbols.get(family), Some(Kind::Error { .. }))
                    })
                    || crate::stdlib::signature(name).is_some()
                    || PURE_COLLECTIONS.contains(&name.as_str())
                    || matches!(self.symbols.get(name), Some(Kind::Record { .. }))
                {
                    // Recognized by the same typed parser, not a textual "pure"
                    // name prefix or a user-supplied unknown marker.
                } else {
                    return fail(format!("Unclassified function call: {name}"));
                }
                if QUERY_OPERATORS.contains(&name.as_str()) {
                    if let Some(Expr::Ident(selector)) = args.get(1) {
                        if self.functions.contains_key(selector) {
                            // Query selectors are actual bounded callbacks.
                            // Their transitively inferred effects must be included.
                            self.edges.insert(selector.clone());
                        } else {
                            return fail("Unclassified query selector function");
                        }
                    }
                }
                for arg in args {
                    self.scan(arg)?;
                }
                for (_, arg) in kwargs {
                    self.scan(arg)?;
                }
            }
            Expr::Attr(base, _) | Expr::Unary(_, base) => self.scan(base)?,
            Expr::Conditional(a, b, c) => {
                self.scan(a)?;
                self.scan(b)?;
                self.scan(c)?;
            }
            Expr::Binary(_, left, right) => {
                self.scan(left)?;
                self.scan(right)?;
            }
            Expr::Int(_) | Expr::Bool(_) | Expr::Text(_) | Expr::Ident(_) => (),
        }
        Ok(())
    }
}

fn solve(
    name: &str,
    direct: &BTreeMap<String, BTreeSet<String>>,
    edges: &BTreeMap<String, BTreeSet<String>>,
    visiting: &mut BTreeSet<String>,
    cache: &mut BTreeMap<String, BTreeSet<String>>,
) -> Result<BTreeSet<String>> {
    if let Some(effects) = cache.get(name) {
        return Ok(effects.clone());
    }
    if !visiting.insert(name.into()) {
        return fail("Recursive effects require a separately bounded contract");
    }
    let mut result = direct
        .get(name)
        .cloned()
        .ok_or_else(|| Error(format!("Unknown function {name}")))?;
    for callee in &edges[name] {
        result.extend(solve(callee, direct, edges, visiting, cache)?);
    }
    visiting.remove(name);
    cache.insert(name.into(), result.clone());
    Ok(result)
}

/// Run on a *validated, typed* function environment and optional explicitly
/// registered primitive effects. User scripts cannot register runtime primitives.
/// A1 source parsing rejects effectful user-defined signatures.
pub fn infer(
    functions: &BTreeMap<String, PureFunction>,
    symbols: &BTreeMap<String, Kind>,
    primitive_effects: &BTreeMap<String, BTreeSet<String>>,
) -> Result<BTreeMap<String, FunctionEffect>> {
    if functions.len() > MAX_FUNCTIONS {
        return fail("Function effects resource limit");
    }
    for (name, effects) in primitive_effects {
        if !identifier(name) || functions.contains_key(name) {
            return fail("Invalid primitive effect signature");
        }
        normalize_effects(&effects.iter().cloned().collect::<Vec<_>>())?;
    }

    let mut edges = BTreeMap::new();
    let mut direct = BTreeMap::new();
    for (name, function) in functions {
        if name != &function.name {
            return fail("Function metadata key/name mismatch");
        }
        let mut types = symbols.clone();
        let mut seen_parameters = BTreeSet::new();
        for (arg, kind) in &function.parameters {
            if !seen_parameters.insert(arg) {
                return fail("Duplicate function parameter in typed IR");
            }
            // Functions are declared before mutable state. A later state with
            // the same identifier must not erase the parameter's lexical type.
            // The original parser already checked reserved type/function names
            // at the declaration site.
            types.insert(arg.clone(), kind.clone());
        }
        // Recheck the expression against its signature. Reject unknown, untyped
        // and dynamic calls before traversing the call graph.
        crate::typed_errors::validate_body(&function.body, &function.result, &types)?;
        let mut scanner = Scanner {
            symbols,
            functions,
            primitives: primitive_effects,
            edges: BTreeSet::new(),
            direct: BTreeSet::new(),
            calls: 0,
        };
        scanner.scan(&function.body)?;
        edges.insert(name.clone(), scanner.edges);
        direct.insert(name.clone(), scanner.direct);
    }
    let mut cache = BTreeMap::new();
    let mut results = BTreeMap::new();
    for (name, function) in functions {
        let effective = solve(name, &direct, &edges, &mut BTreeSet::new(), &mut cache)?;
        let declared = function.declared_effects.clone();
        if let Some(contract) = &declared {
            normalize_effects(&contract.iter().cloned().collect::<Vec<_>>())?;
            let exceeded: Vec<_> = effective.difference(contract).cloned().collect();
            if !exceeded.is_empty() {
                return fail(format!(
                    "E_PUBLIC_EFFECT: {name} exceeds declared effects: {}",
                    exceeded.join(", ")
                ));
            }
        }
        results.insert(
            name.clone(),
            FunctionEffect {
                name: name.clone(),
                direct: direct[name].clone(),
                effective,
                declared,
            },
        );
    }
    Ok(results)
}

pub fn infer_program(program: &Program) -> Result<BTreeMap<String, FunctionEffect>> {
    infer(&program.functions, &program.types, &BTreeMap::new())
}

/// Hash the checked, already-expanded source bytes; a hash is not a signature
/// and says nothing about the safety of other capabilities outside app-domain.
pub fn manifest(program: &Program, expanded_source: &str, target: &str) -> Result<Manifest> {
    let functions = infer_program(program)?;
    let mut all = BTreeSet::new();
    for item in functions.values() {
        all.extend(item.effective.iter().cloned());
    }
    require_target(target, &all)?;
    Ok(Manifest {
        effective: all.into_iter().collect(),
        functions: functions
            .into_values()
            .map(|f| FunctionManifest {
                declared: f.declared.map(|d| d.into_iter().collect()),
                effective: f.effective.into_iter().collect(),
                name: f.name,
            })
            .collect(),
        kind: "app-domain",
        schema: SCHEMA,
        source_sha256: format!("{:x}", Sha256::digest(expanded_source.as_bytes())),
        target: target.into(),
    })
}

/// serde_json's normal struct field order above is intentionally canonical:
/// fields and functions are emitted in sorted key order matching Python A1.
pub fn canonical_json(manifest: &Manifest) -> Result<String> {
    serde_json::to_string(manifest)
        .map_err(|e| Error(format!("Cannot serialize effect manifest: {e}")))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn basic(name: &str, body: Expr, declared: Option<BTreeSet<String>>) -> PureFunction {
        PureFunction {
            name: name.into(),
            parameters: vec![("x".into(), Kind::Int)],
            result: Kind::Int,
            body,
            declared_effects: declared,
        }
    }

    #[test]
    fn normalization_and_target_upper_bounds() {
        for target in ["app", "web", "android", "site", "webapp", "host", "server"] {
            require_target(target, &BTreeSet::new()).unwrap();
        }
        assert!(require_target("bad", &BTreeSet::new()).is_err());
        assert!(normalize_effects(&["web.api".into(), "web.api".into()]).is_err());
        assert!(normalize_effects(&["host.shell.exec".into()]).is_err());
        let read = BTreeSet::from(["host.fs.read".into()]);
        assert!(require_target("host", &read).is_ok());
        for target in ["app", "web", "android", "server"] {
            assert!(require_target(target, &read).is_err());
        }
        assert!(require_target("webapp", &BTreeSet::from(["web.api".into()])).is_ok());
    }

    #[test]
    fn transitive_closure_contracts_and_rejected_edges() {
        let mut funcs = BTreeMap::new();
        funcs.insert(
            "leaf".into(),
            basic(
                "leaf",
                Expr::Call {
                    name: "read_file".into(),
                    args: vec![Expr::Ident("x".into())],
                    kwargs: vec![],
                },
                None,
            ),
        );
        funcs.insert(
            "mid".into(),
            basic(
                "mid",
                Expr::Call {
                    name: "leaf".into(),
                    args: vec![Expr::Ident("x".into())],
                    kwargs: vec![],
                },
                None,
            ),
        );
        funcs.insert(
            "top".into(),
            basic(
                "top",
                Expr::Call {
                    name: "mid".into(),
                    args: vec![Expr::Ident("x".into())],
                    kwargs: vec![],
                },
                None,
            ),
        );
        let mut symbols = BTreeMap::new();
        let signature = Kind::Function {
            parameters: vec![Kind::Int],
            result: Box::new(Kind::Int),
        };
        for name in ["leaf", "mid", "top", "read_file"] {
            symbols.insert(name.into(), signature.clone());
        }
        let primitive =
            BTreeMap::from([("read_file".into(), BTreeSet::from(["host.fs.read".into()]))]);
        let inferred = infer(&funcs, &symbols, &primitive).unwrap();
        for name in ["leaf", "mid", "top"] {
            assert_eq!(
                inferred[name].effective,
                BTreeSet::from(["host.fs.read".into()])
            );
        }
        funcs.get_mut("top").unwrap().declared_effects = Some(BTreeSet::new());
        assert!(infer(&funcs, &symbols, &primitive)
            .unwrap_err()
            .0
            .contains("E_PUBLIC_EFFECT"));
        funcs.get_mut("top").unwrap().declared_effects =
            Some(BTreeSet::from(["host.fs.read".into()]));
        assert!(infer(&funcs, &symbols, &primitive).is_ok());
        symbols.remove("read_file");
        assert!(infer(&funcs, &symbols, &primitive).is_err());
        symbols.insert("read_file".into(), signature.clone());
        funcs.get_mut("leaf").unwrap().body = Expr::Call {
            name: "top".into(),
            args: vec![Expr::Ident("x".into())],
            kwargs: vec![],
        };
        assert!(infer(&funcs, &symbols, &primitive)
            .unwrap_err()
            .0
            .contains("Recursive effects"));
    }

    #[test]
    fn pure_annotation_manifest_is_canonical() {
        let src = "app \"A\"\nfn double(x: int) -> int effects pure = x * 2\nstate n = 1\n\
                   action add: n = double(n)\nscreen main:\n    value n\n";
        let parsed = crate::parse(src).unwrap();
        let one = manifest(&parsed, src, "web").unwrap();
        let two = manifest(&parsed, src, "web").unwrap();
        let output = canonical_json(&one).unwrap();
        assert_eq!(output, canonical_json(&two).unwrap());
        assert_eq!(one.effective, Vec::<String>::new());
        assert_eq!(one.functions[0].declared, Some(vec![]));
        assert_eq!(
            one.source_sha256,
            format!("{:x}", Sha256::digest(src.as_bytes()))
        );
    }
}
