//! Restricted, typed scalar expression lexer, parser and evaluator.
//! No Rust/Python/JS eval, foreign calls, I/O, implicit casts or dynamic code.

use crate::model::{
    check_i32, ensure_text, fail, Binary, Error, Expr, Kind, Result, State, Unary, Value,
    MAX_AST_NODES,
};
use std::collections::BTreeMap;

#[derive(Clone, Debug, PartialEq)]
enum Tok {
    Int(i64),
    Str(String),
    Id(String),
    LParen,
    RParen,
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

    fn build(&mut self, expr: Expr) -> Result<Expr> {
        self.nodes += 1;
        if self.nodes > MAX_AST_NODES {
            return fail("Expression exceeds complexity limit");
        }
        Ok(expr)
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
            let inner = self.parse_not()?;
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
            let inner = self.parse_neg()?;
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
                let inner = self.parse_or()?;
                if self.next() != Tok::RParen {
                    return fail("Unclosed expression parenthesis");
                }
                return Ok(inner);
            }
            other => return fail(format!("Expected scalar expression, found {other:?}")),
        };
        self.build(expr)
    }
}

/// Parse exactly one expression; rejects trailing tokens and unsupported forms.
pub fn parse(source: &str) -> Result<Expr> {
    let mut parser = Parser {
        tokens: lex(source)?,
        pos: 0,
        nodes: 0,
    };
    let expr = parser.parse_or()?;
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
        Expr::Ident(name) => types
            .get(name)
            .copied()
            .ok_or_else(|| Error(format!("Unknown identifier: {name}"))),
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
    match expr {
        Expr::Int(v) => Ok(Value::Int(check_i32(*v)?)),
        Expr::Bool(v) => Ok(Value::Bool(*v)),
        Expr::Text(v) => Ok(Value::Text(v.clone())),
        Expr::Ident(name) => values
            .get(name)
            .cloned()
            .ok_or_else(|| Error(format!("Unknown identifier: {name}"))),
        Expr::Unary(Unary::Neg, inner) => {
            // Python AST folds this one valid i32 minimum literal.
            if matches!(inner.as_ref(), Expr::Int(2_147_483_648)) {
                return Ok(Value::Int(i32::MIN));
            }
            let v = as_int(evaluate(inner, values)?)?;
            Ok(Value::Int(v.checked_neg().ok_or_else(|| {
                Error("Integer overflow: outside signed 32-bit range".into())
            })?))
        }
        Expr::Unary(Unary::Not, inner) => Ok(Value::Bool(!as_bool(evaluate(inner, values)?)?)),
        Expr::Binary(Binary::And, left, right) => {
            let a = as_bool(evaluate(left, values)?)?;
            Ok(Value::Bool(a && as_bool(evaluate(right, values)?)?))
        }
        Expr::Binary(Binary::Or, left, right) => {
            let a = as_bool(evaluate(left, values)?)?;
            Ok(Value::Bool(a || as_bool(evaluate(right, values)?)?))
        }
        Expr::Binary(op, left, right) => {
            let a = evaluate(left, values)?;
            let b = evaluate(right, values)?;
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
    fn rejects_unsafe_syntax() {
        for expr in ["eval('x')", "a.b", "a[0]", "1 / 0", "1 == 1 == 1", "x = 2"] {
            assert!(parse(expr).is_err(), "accepted {expr}");
        }
    }
}
