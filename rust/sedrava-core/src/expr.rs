//! Restricted, typed scalar expression lexer, parser and evaluator.
//! No Rust/Python/JS eval, foreign calls, I/O, implicit casts or dynamic code.

use crate::model::{
    check_i32, ensure_text, fail, Binary, Error, Expr, Kind, PureFunction, Result, State, Unary,
    Value, MAX_AST_NODES,
};
use std::collections::BTreeMap;

#[derive(Clone, Debug, PartialEq)]
enum Tok {
    Int(i64),
    Str(String),
    Id(String),
    LParen,
    RParen,
    Comma,
    Dot,
    Assign,
    Plus,
    Minus,
    Mul,
    Eq,
    Ne,
    Lt,
    Le,
    Gt,
    Ge,
    And,
    Or,
    Not,
    If,
    Else,
    End,
}

fn lex(source: &str) -> Result<Vec<Tok>> {
    let chars: Vec<char> = source.chars().collect();
    let mut pos = 0;
    let mut out = Vec::new();
    while pos < chars.len() {
        let c = chars[pos];
        if c.is_whitespace() {
            pos += 1;
            continue;
        }
        let token = if c.is_ascii_digit() {
            let start = pos;
            while pos < chars.len() && chars[pos].is_ascii_digit() {
                pos += 1;
            }
            let raw: String = chars[start..pos].iter().collect();
            let x = raw
                .parse::<i64>()
                .map_err(|_| Error("Integer literal out of range".into()))?;
            Tok::Int(x)
        } else if c.is_ascii_alphabetic() || c == '_' {
            let start = pos;
            while pos < chars.len() && (chars[pos].is_ascii_alphanumeric() || chars[pos] == '_') {
                pos += 1;
            }
            let word: String = chars[start..pos].iter().collect();
            match word.as_str() {
                "and" => Tok::And,
                "or" => Tok::Or,
                "not" => Tok::Not,
                "if" => Tok::If,
                "else" => Tok::Else,
                _ => Tok::Id(word),
            }
        } else if c == '"' {
            pos += 1;
            let mut value = String::new();
            let mut closed = false;
            while pos < chars.len() {
                let next = chars[pos];
                pos += 1;
                if next == '"' {
                    closed = true;
                    break;
                }
                if next == '\n' || next == '\r' {
                    return fail("Unterminated text literal");
                }
                if next == '\\' {
                    if pos == chars.len() {
                        return fail("Invalid text escape");
                    }
                    let escaped = chars[pos];
                    pos += 1;
                    match escaped {
                        '\\' => value.push('\\'),
                        '"' => value.push('"'),
                        'n' => value.push('\n'),
                        'r' => value.push('\r'),
                        't' => value.push('\t'),
                        _ => return fail("Invalid text escape"),
                    }
                } else {
                    value.push(next);
                }
            }
            if !closed {
                return fail("Unterminated text literal");
            }
            ensure_text(&value)?;
            Tok::Str(value)
        } else {
            pos += 1;
            match c {
                '(' => Tok::LParen,
                ')' => Tok::RParen,
                ',' => Tok::Comma,
                '.' => Tok::Dot,
                '+' => Tok::Plus,
                '-' => Tok::Minus,
                '*' => {
                    if chars.get(pos) == Some(&'*') {
                        return fail("Power operator is not supported");
                    }
                    Tok::Mul
                }
                '=' if chars.get(pos) == Some(&'=') => {
                    pos += 1;
                    Tok::Eq
                }
                '=' => Tok::Assign,
                '!' if chars.get(pos) == Some(&'=') => {
                    pos += 1;
                    Tok::Ne
                }
                '<' if chars.get(pos) == Some(&'=') => {
                    pos += 1;
                    Tok::Le
                }
                '>' if chars.get(pos) == Some(&'=') => {
                    pos += 1;
                    Tok::Ge
                }
                '<' => Tok::Lt,
                '>' => Tok::Gt,
                _ => return fail(format!("Unsupported expression character: {c:?}")),
            }
        };
        out.push(token);
        if out.len() > MAX_AST_NODES * 3 {
            return fail("Expression exceeds complexity limit");
        }
    }
    out.push(Tok::End);
    Ok(out)
}

struct Parser {
    tokens: Vec<Tok>,
    pos: usize,
    nodes: usize,
    nesting: usize,
}

impl Parser {
    fn next(&mut self) -> Tok {
        let t = self.tokens[self.pos].clone();
        if t != Tok::End {
            self.pos += 1;
        }
        t
    }

    fn peek(&self) -> &Tok {
        &self.tokens[self.pos]
    }

    fn nested(&mut self, parse: impl FnOnce(&mut Self) -> Result<Expr>) -> Result<Expr> {
        const MAX_NESTING: usize = 64;
        if self.nesting >= MAX_NESTING {
            return fail("Expression nesting limit exceeded");
        }
        self.nesting += 1;
        let result = parse(self);
        self.nesting -= 1;
        result
    }

    fn build(&mut self, expr: Expr) -> Result<Expr> {
        self.nodes += 1;
        if self.nodes > MAX_AST_NODES {
            return fail("Expression exceeds complexity limit");
        }
        Ok(expr)
    }

    fn parse_conditional(&mut self) -> Result<Expr> {
        let then_value = self.parse_or()?;
        if *self.peek() != Tok::If {
            return Ok(then_value);
        }
        self.next();
        let condition = self.nested(|p| p.parse_conditional())?;
        if self.next() != Tok::Else {
            return fail("Conditional expression requires else");
        }
        let fallback = self.nested(|p| p.parse_conditional())?;
        self.build(Expr::Conditional(
            Box::new(condition),
            Box::new(then_value),
            Box::new(fallback),
        ))
    }

    fn parse_or(&mut self) -> Result<Expr> {
        let mut left = self.parse_and()?;
        while *self.peek() == Tok::Or {
            self.next();
            let right = self.parse_and()?;
            left = self.build(Expr::Binary(Binary::Or, Box::new(left), Box::new(right)))?;
        }
        Ok(left)
    }

    fn parse_and(&mut self) -> Result<Expr> {
        let mut left = self.parse_not()?;
        while *self.peek() == Tok::And {
            self.next();
            let right = self.parse_not()?;
            left = self.build(Expr::Binary(Binary::And, Box::new(left), Box::new(right)))?;
        }
        Ok(left)
    }

    fn parse_not(&mut self) -> Result<Expr> {
        if *self.peek() == Tok::Not {
            self.next();
            let inner = self.nested(|parser| parser.parse_not())?;
            self.build(Expr::Unary(Unary::Not, Box::new(inner)))
        } else {
            self.parse_compare()
        }
    }

    fn parse_compare(&mut self) -> Result<Expr> {
        let left = self.parse_add()?;
        let op = match self.peek() {
            Tok::Eq => Some(Binary::Eq),
            Tok::Ne => Some(Binary::Ne),
            Tok::Lt => Some(Binary::Lt),
            Tok::Le => Some(Binary::Le),
            Tok::Gt => Some(Binary::Gt),
            Tok::Ge => Some(Binary::Ge),
            _ => None,
        };
        if let Some(op) = op {
            self.next();
            let right = self.parse_add()?;
            self.build(Expr::Binary(op, Box::new(left), Box::new(right)))
        } else {
            Ok(left)
        }
    }

    fn parse_add(&mut self) -> Result<Expr> {
        let mut left = self.parse_mul()?;
        loop {
            let op = match self.peek() {
                Tok::Plus => Binary::Add,
                Tok::Minus => Binary::Sub,
                _ => break,
            };
            self.next();
            let right = self.parse_mul()?;
            left = self.build(Expr::Binary(op, Box::new(left), Box::new(right)))?;
        }
        Ok(left)
    }

    fn parse_mul(&mut self) -> Result<Expr> {
        let mut left = self.parse_neg()?;
        while *self.peek() == Tok::Mul {
            self.next();
            let right = self.parse_neg()?;
            left = self.build(Expr::Binary(Binary::Mul, Box::new(left), Box::new(right)))?;
        }
        Ok(left)
    }

    fn parse_neg(&mut self) -> Result<Expr> {
        if *self.peek() == Tok::Minus {
            self.next();
            let inner = self.nested(|parser| parser.parse_neg())?;
            self.build(Expr::Unary(Unary::Neg, Box::new(inner)))
        } else {
            self.parse_atom()
        }
    }

    fn parse_atom(&mut self) -> Result<Expr> {
        let expr = match self.next() {
            Tok::Int(x) => Expr::Int(x),
            Tok::Str(s) => Expr::Text(s),
            Tok::Id(s) if s == "true" || s == "True" => Expr::Bool(true),
            Tok::Id(s) if s == "false" || s == "False" => Expr::Bool(false),
            Tok::Id(s) => Expr::Ident(s),
            Tok::LParen => {
                let inner = self.nested(|parser| parser.parse_conditional())?;
                if self.next() != Tok::RParen {
                    return fail("Unclosed expression parenthesis");
                }
                inner
            }
            other => return fail(format!("Expected scalar expression, found {other:?}")),
        };
        let mut expr = self.build(expr)?;
        loop {
            match self.peek() {
                Tok::Dot => {
                    self.next();
                    let Tok::Id(field) = self.next() else {
                        return fail("Record field identifier expected");
                    };
                    expr = self.build(Expr::Attr(Box::new(expr), field))?;
                }
                Tok::LParen => {
                    let name = match expr {
                        Expr::Ident(name) => name,
                        Expr::Attr(base, variant) if matches!(base.as_ref(), Expr::Ident(_)) => {
                            let Expr::Ident(family) = *base else {
                                unreachable!()
                            };
                            format!("{family}.{variant}")
                        }
                        _ => return fail("Only declared named operations are callable"),
                    };
                    self.next();
                    let mut args = Vec::new();
                    let mut kwargs = Vec::new();
                    if *self.peek() != Tok::RParen {
                        loop {
                            let keyword = if let Tok::Id(s) = self.peek() {
                                if self.tokens.get(self.pos + 1) == Some(&Tok::Assign) {
                                    Some(s.clone())
                                } else {
                                    None
                                }
                            } else {
                                None
                            };
                            if let Some(key) = keyword {
                                self.next();
                                self.next();
                                let value = self.nested(|p| p.parse_conditional())?;
                                kwargs.push((key, value));
                            } else {
                                if !kwargs.is_empty() {
                                    return fail("Positional argument after named argument");
                                }
                                args.push(self.nested(|p| p.parse_conditional())?);
                            }
                            if *self.peek() != Tok::Comma {
                                break;
                            }
                            self.next();
                            if *self.peek() == Tok::RParen {
                                break;
                            }
                        }
                    }
                    if self.next() != Tok::RParen {
                        return fail("Unclosed function call");
                    }
                    expr = self.build(Expr::Call { name, args, kwargs })?;
                }
                _ => break,
            }
        }
        Ok(expr)
    }
}

/// Parse exactly one expression; rejects trailing tokens and unsupported forms.
pub fn parse(source: &str) -> Result<Expr> {
    let mut parser = Parser {
        tokens: lex(source)?,
        pos: 0,
        nodes: 0,
        nesting: 0,
    };
    let expr = parser.parse_conditional()?;
    if *parser.peek() != Tok::End {
        return fail("Unexpected trailing tokens in expression");
    }
    Ok(expr)
}

pub fn infer(expr: &Expr, types: &BTreeMap<String, Kind>) -> Result<Kind> {
    match expr {
        Expr::Int(x) => {
            check_i32(*x)?;
            Ok(Kind::Int)
        }
        Expr::Bool(_) => Ok(Kind::Bool),
        Expr::Text(_) => Ok(Kind::Text),
        Expr::Ident(name) => {
            let kind = types
                .get(name)
                .cloned()
                .ok_or_else(|| Error(format!("Unknown identifier: {name}")))?;
            if matches!(&kind, Kind::Record{name:record_name,..} if name==record_name)
                || matches!(kind, Kind::Function { .. })
                || matches!(&kind, Kind::Error { name: family, .. } if family == name)
            {
                return fail("Constructor or pure function requires a call");
            }
            Ok(kind)
        }
        Expr::Conditional(test, yes, no) => {
            if infer(test, types)? != Kind::Bool {
                return fail("Conditional requires bool test");
            }
            let left = infer(yes, types)?;
            if left != infer(no, types)? {
                return fail("Conditional branches must match types");
            }
            Ok(left)
        }
        Expr::Attr(base, field) => {
            let kind = infer(base, types)?;
            if let Kind::Record { fields, .. } = kind {
                fields
                    .iter()
                    .find(|(name, _)| name == field)
                    .map(|(_, t)| t.clone())
                    .ok_or_else(|| Error(format!("Unknown record field: {field}")))
            } else {
                fail("Record field access requires record value")
            }
        }
        Expr::Call { name, args, kwargs } => {
            if let Some(kind) =
                crate::typed_errors::infer_constructor(name, args, kwargs, types, &|e| {
                    infer(e, types)
                })?
            {
                return Ok(kind);
            }
            crate::collections::infer_call(name, args, kwargs, types, &|e| infer(e, types))
        }
        Expr::Unary(op, inner) => {
            if *op == Unary::Neg && matches!(inner.as_ref(), Expr::Int(2_147_483_648)) {
                return Ok(Kind::Int);
            }
            let kind = infer(inner, types)?;
            match (op, kind) {
                (Unary::Neg, Kind::Int) => Ok(Kind::Int),
                (Unary::Not, Kind::Bool) => Ok(Kind::Bool),
                _ => fail("Unary operation type mismatch"),
            }
        }
        Expr::Binary(op, left, right) => {
            let a = infer(left, types)?;
            let b = infer(right, types)?;
            if a != b {
                return fail("Binary operation type mismatch");
            }
            match op {
                Binary::Add | Binary::Sub | Binary::Mul if a == Kind::Int => Ok(Kind::Int),
                Binary::And | Binary::Or if a == Kind::Bool => Ok(Kind::Bool),
                Binary::Eq | Binary::Ne => Ok(Kind::Bool),
                Binary::Lt | Binary::Le | Binary::Gt | Binary::Ge if a == Kind::Int => {
                    Ok(Kind::Bool)
                }
                _ => fail("Unsupported operation for operand type"),
            }
        }
    }
}

fn as_int(value: Value) -> Result<i32> {
    if let Value::Int(x) = value {
        Ok(x)
    } else {
        fail("Expected int32")
    }
}
fn as_bool(value: Value) -> Result<bool> {
    if let Value::Bool(x) = value {
        Ok(x)
    } else {
        fail("Expected bool")
    }
}

pub fn evaluate(expr: &Expr, values: &State) -> Result<Value> {
    evaluate_with(expr, values, &BTreeMap::new())
}

pub fn evaluate_with(expr: &Expr, values: &State, types: &BTreeMap<String, Kind>) -> Result<Value> {
    evaluate_full(expr, values, types, &BTreeMap::new())
}

pub fn evaluate_full(
    expr: &Expr,
    values: &State,
    types: &BTreeMap<String, Kind>,
    functions: &BTreeMap<String, PureFunction>,
) -> Result<Value> {
    match expr {
        Expr::Int(v) => Ok(Value::Int(check_i32(*v)?)),
        Expr::Bool(v) => Ok(Value::Bool(*v)),
        Expr::Text(v) => Ok(Value::Text(v.clone())),
        Expr::Ident(name) => values
            .get(name)
            .cloned()
            .ok_or_else(|| Error(format!("Unknown identifier: {name}"))),
        Expr::Conditional(test, yes, no) => {
            if evaluate_full(test, values, types, functions)? == Value::Bool(true) {
                evaluate_full(yes, values, types, functions)
            } else {
                evaluate_full(no, values, types, functions)
            }
        }
        Expr::Attr(base, field) => {
            let record = evaluate_full(base, values, types, functions)?;
            if let Value::Record { fields, .. } = record {
                fields
                    .get(field)
                    .cloned()
                    .ok_or_else(|| Error(format!("Unknown record field: {field}")))
            } else {
                fail("Expected record")
            }
        }
        Expr::Call { name, args, kwargs } => {
            if let Some(function) = functions.get(name) {
                if !kwargs.is_empty() || args.len() != function.parameters.len() {
                    return fail("Pure function argument count mismatch");
                }
                let mut params = State::new();
                for ((key, expected), argument) in function.parameters.iter().zip(args.iter()) {
                    let value = evaluate_full(argument, values, types, functions)?;
                    crate::model::validate(&value, expected)?;
                    params.insert(key.clone(), value);
                }
                let result = crate::typed_errors::evaluate_body(
                    &function.body,
                    &function.result,
                    &params,
                    types,
                    functions,
                )?;
                crate::model::validate(&result, &function.result)?;
                Ok(result)
            } else {
                if let Some(value) =
                    crate::typed_errors::construct(name, args, kwargs, types, &|e| {
                        evaluate_full(e, values, types, functions)
                    })?
                {
                    return Ok(value);
                }
                crate::collections::evaluate_call(name, args, kwargs, types, functions, &|e| {
                    evaluate_full(e, values, types, functions)
                })
            }
        }
        Expr::Unary(Unary::Neg, inner) => {
            // Python AST folds this one valid i32 minimum literal.
            if matches!(inner.as_ref(), Expr::Int(2_147_483_648)) {
                return Ok(Value::Int(i32::MIN));
            }
            let v = as_int(evaluate_full(inner, values, types, functions)?)?;
            Ok(Value::Int(v.checked_neg().ok_or_else(|| {
                Error("Integer overflow: outside signed 32-bit range".into())
            })?))
        }
        Expr::Unary(Unary::Not, inner) => Ok(Value::Bool(!as_bool(evaluate_full(
            inner, values, types, functions,
        )?)?)),
        Expr::Binary(Binary::And, left, right) => {
            let a = as_bool(evaluate_full(left, values, types, functions)?)?;
            Ok(Value::Bool(
                a && as_bool(evaluate_full(right, values, types, functions)?)?,
            ))
        }
        Expr::Binary(Binary::Or, left, right) => {
            let a = as_bool(evaluate_full(left, values, types, functions)?)?;
            Ok(Value::Bool(
                a || as_bool(evaluate_full(right, values, types, functions)?)?,
            ))
        }
        Expr::Binary(op, left, right) => {
            let a = evaluate_full(left, values, types, functions)?;
            let b = evaluate_full(right, values, types, functions)?;
            let result = match op {
                Binary::Eq => return Ok(Value::Bool(a == b)),
                Binary::Ne => return Ok(Value::Bool(a != b)),
                Binary::Lt => return Ok(Value::Bool(as_int(a)? < as_int(b)?)),
                Binary::Le => return Ok(Value::Bool(as_int(a)? <= as_int(b)?)),
                Binary::Gt => return Ok(Value::Bool(as_int(a)? > as_int(b)?)),
                Binary::Ge => return Ok(Value::Bool(as_int(a)? >= as_int(b)?)),
                Binary::Add => as_int(a)?.checked_add(as_int(b)?),
                Binary::Sub => as_int(a)?.checked_sub(as_int(b)?),
                Binary::Mul => as_int(a)?.checked_mul(as_int(b)?),
                Binary::And | Binary::Or => unreachable!(),
            };
            result
                .map(Value::Int)
                .ok_or_else(|| Error("Integer overflow: outside signed 32-bit range".into()))
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn eval(src: &str) -> Result<Value> {
        let e = parse(src)?;
        evaluate(&e, &State::new())
    }

    #[test]
    fn operator_precedence_and_min_integer() {
        assert_eq!(eval("1 + 2 * 3").unwrap(), Value::Int(7));
        assert_eq!(eval("-2147483648").unwrap(), Value::Int(i32::MIN));
        assert!(eval("2147483648").is_err());
        assert!(eval("2147483647 + 1").is_err());
        assert_eq!(eval("not (true and false)").unwrap(), Value::Bool(true));
    }

    #[test]
    fn string_escaping_and_unicode() {
        assert_eq!(
            eval(r#""Алиса 😀\nline""#).unwrap(),
            Value::Text("Алиса 😀\nline".into())
        );
        assert!(parse(r#""invalid\q""#).is_err());
        assert!(parse("'single'").is_err());
        let max = "😀".repeat(1024);
        assert!(parse(&format!("{max:?}")).is_ok());
        let too_long = "😀".repeat(1025);
        assert!(parse(&format!("{too_long:?}")).is_err());
    }

    #[test]
    fn rejects_excessive_recursive_nesting() {
        let nested = format!("{}1{}", "(".repeat(1000), ")".repeat(1000));
        assert!(parse(&nested).is_err());
        assert!(parse(&format!("{}true", "not ".repeat(1000))).is_err());
        assert!(parse(&format!("{}1", "-".repeat(1000))).is_err());
    }

    #[test]
    fn rejects_unsafe_syntax() {
        for expr in ["eval('x')", "a[0]", "1 / 0", "1 == 1 == 1", "x = 2"] {
            assert!(parse(expr).is_err(), "accepted {expr}");
        }
    }
}
