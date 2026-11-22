//! Deterministic scalar standard library shared with Python semantics.

use crate::model::{ensure_text, fail, Error, Kind, Result, Value};

pub fn signature(name: &str) -> Option<(Vec<Kind>, Kind)> {
    let (args, result) = match name {
        "text_length" => (vec![Kind::Text], Kind::Int),
        "trim" | "lower_ascii" => (vec![Kind::Text], Kind::Text),
        "contains" => (vec![Kind::Text, Kind::Text], Kind::Bool),
        "concat" => (vec![Kind::Text, Kind::Text], Kind::Text),
        "is_date" => (vec![Kind::Text], Kind::Bool),
        "date_days" => (vec![Kind::Text], Kind::Int),
        "date_add" => (vec![Kind::Text, Kind::Int], Kind::Text),
        _ => return None,
    };
    Some((args, result))
}

fn text(v: &Value) -> Result<&str> {
    if let Value::Text(s) = v {
        Ok(s)
    } else {
        fail("Text value required")
    }
}
fn int(v: &Value) -> Result<i32> {
    if let Value::Int(n) = v {
        Ok(*n)
    } else {
        fail("Int value required")
    }
}
fn leap(y: i32) -> bool {
    y % 4 == 0 && (y % 100 != 0 || y % 400 == 0)
}
fn civil_date(raw: &str) -> Result<(i32, i32, i32)> {
    let bytes = raw.as_bytes();
    if bytes.len() != 10
        || bytes[4] != b'-'
        || bytes[7] != b'-'
        || bytes
            .iter()
            .enumerate()
            .any(|(i, b)| i != 4 && i != 7 && !b.is_ascii_digit())
    {
        return fail("Expected YYYY-MM-DD");
    }
    let y = raw[..4]
        .parse::<i32>()
        .map_err(|_| Error("Invalid year".into()))?;
    let m = raw[5..7]
        .parse::<i32>()
        .map_err(|_| Error("Invalid month".into()))?;
    let d = raw[8..10]
        .parse::<i32>()
        .map_err(|_| Error("Invalid day".into()))?;
    if !(1..=9999).contains(&y) || !(1..=12).contains(&m) {
        return fail("Invalid civil date");
    }
    let max = match m {
        2 if leap(y) => 29,
        2 => 28,
        4 | 6 | 9 | 11 => 30,
        _ => 31,
    };
    if !(1..=max).contains(&d) {
        return fail("Invalid civil date");
    }
    Ok((y, m, d))
}
// Proleptic Gregorian civil date <-> days since 1970-01-01.
// Mathematically bounded to 0001..9999 by public callers.
fn days_from_civil(y: i32, m: i32, d: i32) -> i32 {
    let y = y - i32::from(m <= 2);
    let era = if y >= 0 { y } else { y - 399 } / 400;
    let yoe = y - era * 400;
    let mp = m + if m > 2 { -3 } else { 9 };
    let doy = (153 * mp + 2) / 5 + d - 1;
    let doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
    era * 146097 + doe - 719468
}
fn civil_from_days(z: i32) -> (i32, i32, i32) {
    let z = z + 719468;
    let era = if z >= 0 { z } else { z - 146096 } / 146097;
    let doe = z - era * 146097;
    let yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365;
    let mut y = yoe + era * 400;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let d = doy - (153 * mp + 2) / 5 + 1;
    let m = mp + if mp < 10 { 3 } else { -9 };
    y += i32::from(m <= 2);
    (y, m, d)
}
pub fn apply(name: &str, args: &[Value]) -> Result<Value> {
    let expected = signature(name).ok_or_else(|| Error(format!("Unknown builtin: {name}")))?;
    if args.iter().map(Value::kind).collect::<Vec<_>>() != expected.0 {
        return fail("Builtin argument type mismatch");
    }
    let v = match name {
        "text_length" => Value::Int(text(&args[0])?.chars().count() as i32),
        "trim" => Value::Text(
            text(&args[0])?
                .trim_matches([' ', '\t', '\n', '\r'])
                .to_owned(),
        ),
        "lower_ascii" => Value::Text(text(&args[0])?.to_ascii_lowercase()),
        "contains" => Value::Bool(text(&args[0])?.contains(text(&args[1])?)),
        "concat" => {
            let s = format!("{}{}", text(&args[0])?, text(&args[1])?);
            ensure_text(&s)?;
            Value::Text(s)
        }
        "is_date" => Value::Bool(civil_date(text(&args[0])?).is_ok()),
        "date_days" => {
            let (y, m, d) = civil_date(text(&args[0])?)?;
            Value::Int(days_from_civil(y, m, d))
        }
        "date_add" => {
            let (y, m, d) = civil_date(text(&args[0])?)?;
            let days = days_from_civil(y, m, d) as i64 + int(&args[1])? as i64;
            if !(-719162..=2932896).contains(&days) {
                return fail("Date outside 0001..9999");
            }
            let (y, m, d) = civil_from_days(days as i32);
            Value::Text(format!("{y:04}-{m:02}-{d:02}"))
        }
        _ => return fail("Unrecognized builtin"),
    };
    Ok(v)
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn civil_dates_roundtrip() {
        let samples = [
            "0001-01-01",
            "1582-10-15",
            "1900-03-01",
            "1970-01-01",
            "2000-02-29",
            "2026-11-22",
            "9999-12-31",
        ];
        for s in samples {
            let (y, m, d) = civil_date(s).unwrap();
            let days = days_from_civil(y, m, d);
            assert_eq!(civil_from_days(days), (y, m, d));
        }
        assert_eq!(days_from_civil(1, 1, 1), -719162);
        assert_eq!(days_from_civil(9999, 12, 31), 2932896);
        for invalid in [
            "0000-01-01",
            "2025-02-29",
            "1900-02-29",
            "2020-13-01",
            "abcd-aa-bb",
        ] {
            assert!(civil_date(invalid).is_err());
        }
    }
    #[test]
    fn string_functions() {
        assert_eq!(
            apply("text_length", &[Value::Text("А😀".into())]).unwrap(),
            Value::Int(2)
        );
        assert_eq!(
            apply("lower_ascii", &[Value::Text("AБZ".into())]).unwrap(),
            Value::Text("aБz".into())
        );
        assert_eq!(
            apply("trim", &[Value::Text(" \t a \n ".into())]).unwrap(),
            Value::Text("a".into())
        );
    }
}
