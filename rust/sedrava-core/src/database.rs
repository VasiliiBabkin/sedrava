//! A16 standalone, explicit-capability SQL host domain.
//! One checked statement, positional typed parameters, no implicit IO or interpolation.
use crate::model::{fail, Error, Result};
use sedravasql::native_log::{sql::{self,SqlKind,SqlResult,BoundStatement},table::Cell,NativeLog};
use std::{collections::BTreeSet,path::Path};
#[derive(Clone,Copy,Debug,PartialEq,Eq)]
enum Type{Int,Bool,Text}
impl Type{
    fn parse(s:&str)->Result<Self>{match s{"int"=>Ok(Self::Int),"bool"=>Ok(Self::Bool),"text"=>Ok(Self::Text),_=>fail("E_DATABASE: invalid parameter type")}}
    fn sample(self)->Cell{match self{Self::Int=>Cell::Int(0),Self::Bool=>Cell::Bool(false),Self::Text=>Cell::Text("sample".into())}}
    fn accepts(self,c:&Cell)->bool{matches!((self,c),(Self::Int,Cell::Int(_))|(Self::Bool,Cell::Bool(_))|(Self::Text,Cell::Text(_)))}
}
fn identifier(s:&str)->bool{
    !s.is_empty()&&s.len()<=48&&s.as_bytes()[0].is_ascii_alphabetic()&&s.bytes().all(|b|b.is_ascii_alphanumeric()||b==b'_')
}
// A23a: declarative, pure parameter guards. No SQL interpolation or IO.
#[derive(Debug, PartialEq, Eq)]
enum Guard {
    IntRange(usize, i32, i32),
    TextLength(usize, usize, usize),
    NonBlank(usize),
    Key(usize),
    Date(usize),
}
impl Guard {
    fn parse(raw: &str, params: &[(String, Type)]) -> Result<Self> {
        let words: Vec<_> = raw.split_ascii_whitespace().collect();
        let invalid = || Error("E_DATABASE: invalid require declaration".into());
        let [name, op, rest @ ..] = words.as_slice() else { return Err(invalid()); };
        let index = params.iter().position(|(n, _)| n == name).ok_or_else(invalid)?;
        match (*op, rest, params[index].1) {
            ("range", [lo, hi], Type::Int) => {
                let lo: i32 = lo.parse().map_err(|_| invalid())?;
                let hi: i32 = hi.parse().map_err(|_| invalid())?;
                if lo > hi { return Err(invalid()); }
                Ok(Self::IntRange(index, lo, hi))
            }
            ("length", [lo, hi], Type::Text) => {
                let lo: usize = lo.parse().map_err(|_| invalid())?;
                let hi: usize = hi.parse().map_err(|_| invalid())?;
                if lo > hi || hi > 65536 { return Err(invalid()); }
                Ok(Self::TextLength(index, lo, hi))
            }
            ("nonblank", [], Type::Text) => Ok(Self::NonBlank(index)),
            ("key", [], Type::Text) => Ok(Self::Key(index)),
            ("date", [], Type::Text) => Ok(Self::Date(index)),
            _ => Err(invalid()),
        }
    }
    fn accepts(&self, values: &[Cell]) -> bool {
        match self {
            Self::IntRange(i, lo, hi) => matches!(values.get(*i), Some(Cell::Int(n)) if (lo..=hi).contains(&n)),
            Self::TextLength(i, lo, hi) => matches!(values.get(*i), Some(Cell::Text(s)) if (*lo..=*hi).contains(&s.chars().count())),
            Self::NonBlank(i) => matches!(values.get(*i), Some(Cell::Text(s)) if !s.trim().is_empty()),
            Self::Date(i) => matches!(values.get(*i), Some(Cell::Text(s)) if valid_date(s)),
            Self::Key(i) => matches!(values.get(*i), Some(Cell::Text(s)) if !s.is_empty() && s.len() <= 128 && s.bytes().all(|b| b.is_ascii_alphanumeric() || matches!(b,b'_'|b'-'|b'.'))),
        }
    }
}
// Gregorian calendar date, no timezone or implicit clock.
fn valid_date(s: &str) -> bool {
    let b=s.as_bytes();
    if b.len()!=10 || b[4]!=b'-' || b[7]!=b'-' || b.iter().enumerate().any(|(i,c)| i!=4 && i!=7 && !c.is_ascii_digit()) {return false;}
    let y:u32=s[..4].parse().unwrap();
    let m:u32=s[5..7].parse().unwrap();
    let d:u32=s[8..].parse().unwrap();
    let max=match m {1|3|5|7|8|10|12=>31,4|6|9|11=>30,2 if y%4==0&&(y%100!=0||y%400==0)=>29,2=>28,_=>0};
    y>0 && d>0 && d<=max
}
#[derive(serde::Deserialize)]
#[serde(deny_unknown_fields)]
struct TransactionStep {
    sql:String,
    #[serde(rename="using")]
    arguments:Vec<String>,
}
pub struct Program{
    pub name:String,
    params:Vec<(String,Type)>,
    guards:Vec<Guard>,
    sql:String,
    transaction:Vec<(String,Vec<usize>)>,
    sequential:bool,
    kind:SqlKind,
}
pub fn parse(source:&str)->Result<Program>{
    if source.len()>32768{return fail("E_DATABASE: source budget");}
    let mut lines=source.lines().filter(|l|!l.trim().is_empty()&&!l.trim_start().starts_with('#'));
    let name=lines.next().and_then(|l|l.strip_prefix("database ")).filter(|s|identifier(s)).ok_or_else(||Error("E_DATABASE: expected database NAME".into()))?.to_owned();
    let mut names=BTreeSet::new();let mut params=Vec::new();let mut statement=None;let mut transaction=Vec::new();let mut sequential=false;let mut guards=Vec::new();
    for line in lines{
        if statement.is_some(){return fail("E_DATABASE: only one statement allowed");}
        let line=line.strip_prefix("    ").ok_or_else(||Error("E_DATABASE: expected four spaces".into()))?;
        if let Some(raw)=line.strip_prefix("param "){
            let (name,kind)=raw.split_once(": ").ok_or_else(||Error("E_DATABASE: expected param NAME: TYPE".into()))?;
            if !guards.is_empty()||!identifier(name)||!names.insert(name)||params.len()>=32{return fail("E_DATABASE: invalid/duplicate parameter");}
            params.push((name.to_owned(),Type::parse(kind)?));
        }else if let Some(raw)=line.strip_prefix("require "){
            if guards.len()>=64{return fail("E_DATABASE: require budget");}
            let guard=Guard::parse(raw,&params)?;
            if guards.contains(&guard){return fail("E_DATABASE: duplicate require");}
            guards.push(guard);
        }else if let Some(raw)=line.strip_prefix("transaction ").or_else(||line.strip_prefix("sequential ")){
            sequential=line.starts_with("sequential ");
            let steps:Vec<TransactionStep>=serde_json::from_str(raw).map_err(|_|Error("E_DATABASE: transaction requires JSON steps".into()))?;
            if steps.is_empty()||steps.len()>15{return fail("E_DATABASE: transaction requires 1..15 steps");}
            let mut used=BTreeSet::new();let mut has_write=false;
            for step in steps{
                if !step.sql.split_ascii_whitespace().next().is_some_and(|s|["INSERT","UPDATE","DELETE"].iter().any(|k|s.eq_ignore_ascii_case(k))||(sequential&&s.eq_ignore_ascii_case("SELECT"))){
                    return fail("E_DATABASE: transaction only permits DML");
                }
                let mut indices=Vec::new();
                for name in &step.arguments{
                    let index=params.iter().position(|(p,_)|p==name).ok_or_else(||Error("E_DATABASE: unknown transaction argument".into()))?;
                    used.insert(index);indices.push(index);
                }
                let sample=indices.iter().map(|i|params[*i].1.sample()).collect::<Vec<_>>();
                let kind=sql::check(&step.sql,&sample).map_err(|e|Error(format!("E_DATABASE: {e}")))?;
                if kind==SqlKind::Write{has_write=true;}else if !sequential{return fail("E_DATABASE: transaction only permits writes");}
                transaction.push((step.sql,indices));
            }
            if !has_write{return fail("E_DATABASE: transaction requires a write");}
            if used.len()!=params.len(){return fail("E_DATABASE: unused transaction parameter");}
            statement=Some((SqlKind::Write,String::new()));
        }else{
            let (kind,raw)=if let Some(s)=line.strip_prefix("query "){(SqlKind::Query,s)}else if let Some(s)=line.strip_prefix("execute "){(SqlKind::Write,s)}else{return fail("E_DATABASE: expected param, require, query or execute");};
            let text:String=serde_json::from_str(raw).map_err(|_|Error("E_DATABASE: expected quoted SQL string".into()))?;
            let samples=params.iter().map(|(_,t)|t.sample()).collect::<Vec<_>>();
            let actual=sql::check(&text,&samples).map_err(|e|Error(format!("E_DATABASE: {e}")))?;
            if actual!=kind{return fail("E_DATABASE: SQL statement kind mismatch");}
            statement=Some((kind,text));
        }
    }
    let (kind,sql)=statement.ok_or_else(||Error("E_DATABASE: missing statement".into()))?;
    Ok(Program{name,params,guards,sql,transaction,sequential,kind})
}
impl Program {
    pub(crate) fn kind(&self)->SqlKind { self.kind }
    pub(crate) fn bind_object(&self,object:&serde_json::Map<String,serde_json::Value>)->Result<Vec<Cell>> {
        if object.len()!=self.params.len(){return fail("E_DATABASE: parameter schema mismatch");}
        let mut out=Vec::with_capacity(self.params.len());
        for (name,kind) in &self.params{
            let v=object.get(name).ok_or_else(||Error("E_DATABASE: missing parameter".into()))?;
            let value:Cell=serde_json::from_value(v.clone()).map_err(|_|Error("E_DATABASE: invalid scalar parameter".into()))?;
            if !kind.accepts(&value){return fail("E_DATABASE: parameter type mismatch");}
            out.push(value);
        }
        Ok(out)
    }
    pub(crate) fn validate_guards(&self, values:&[Cell])->Result<()> {
        if values.len()!=self.params.len()||!self.guards.iter().all(|g|g.accepts(values)){
            return fail("E_DATABASE_RULE: parameter requirement failed");
        }
        Ok(())
    }
    pub(crate) fn execute_on(&self,db:&mut NativeLog,values:&[Cell],request:Option<&str>)->sedravasql::native_log::Result<SqlResult>{
        self.validate_guards(values).map_err(|_|sedravasql::native_log::Error::Invalid("database parameter requirement failed"))?;
        if self.transaction.is_empty(){return sql::execute_bound(db,&self.sql,values,request);}
        let request=request.ok_or(sedravasql::native_log::Error::Invalid("database transaction requires request key"))?;
        if values.len()!=self.params.len(){return Err(sedravasql::native_log::Error::Invalid("database transaction argument count"));}
        let steps=self.bound_steps(values);
        if self.sequential{sql::execute_sequential(db,&steps,request)}else{sql::execute_transaction(db,&steps,request)}
    }
    fn bound_steps(&self,values:&[Cell])->Vec<BoundStatement>{
        self.transaction.iter().map(|(sql,indices)|BoundStatement{sql:sql.clone(),params:indices.iter().map(|i|values[*i].clone()).collect()}).collect()
    }
    fn check_bound(&self,values:&[Cell])->Result<()> {
        if self.transaction.is_empty(){
            sql::check(&self.sql,values).map_err(|e|Error(format!("E_DATABASE: {e}")))?;
        }else{
            for step in self.bound_steps(values){
                sql::check(&step.sql,&step.params).map_err(|e|Error(format!("E_DATABASE: {e}")))?;
            }
        }
        Ok(())
    }
}
pub fn run(program:&Program,path:&Path,trusted:bool,allow_write:bool,request:Option<&str>,supplied:&[String])->Result<SqlResult>{
    if !trusted||!path.is_absolute(){return fail("E_DATABASE_POLICY: explicit trusted mode and absolute database path required");}
    match program.kind{
        SqlKind::Query if allow_write||request.is_some()=>return fail("E_DATABASE_POLICY: query does not accept write options"),
        SqlKind::Write if !allow_write||request.is_none()=>return fail("E_DATABASE_POLICY: write requires --allow-write and --request-key"),
        _=>{}
    }
    let mut values=std::collections::BTreeMap::new();
    for argument in supplied{
        let (name,raw)=argument.split_once('=').ok_or_else(||Error("E_DATABASE: expected --arg NAME=JSON".into()))?;
        if raw.len()>8192||!program.params.iter().any(|(n,_)|n==name)||values.contains_key(name){return fail("E_DATABASE: invalid/duplicate argument");}
        let value:Cell=serde_json::from_str(raw).map_err(|_|Error("E_DATABASE: expected scalar JSON value".into()))?;
        values.insert(name,value);
    }
    let mut bound=Vec::new();
    for (name,kind) in &program.params{
        let value=values.remove(name.as_str()).ok_or_else(||Error("E_DATABASE: missing argument".into()))?;
        if !kind.accepts(&value){return fail("E_DATABASE: parameter type mismatch");}
        bound.push(value);
    }
    // Recheck bound SQL before acquiring an exclusive DB handle.
    program.validate_guards(&bound)?;
    program.check_bound(&bound)?;
    let mut db=NativeLog::open(path).map_err(|e|Error(format!("E_DATABASE: {e}")))?;
    program.execute_on(&mut db,&bound,request).map_err(|e|Error(format!("E_DATABASE: {e}")))
}

#[cfg(test)]
mod guard_tests {
    use super::*;
    fn program(lines: &str) -> Result<Program> {
        parse(&format!("database Example\n    param amount: int\n    param id: text\n    param title: text\n{lines}    execute \"INSERT INTO T (amount,id,title) VALUES (?,?,?)\"\n"))
    }
    #[test]
    fn typed_guards_and_unicode() {
        let p = program("    require amount range 0 10\n    require id key\n    require title length 1 2\n    require title nonblank\n").unwrap();
        let bound = |n,id:&str,title:&str| vec![Cell::Int(n),Cell::Text(id.into()),Cell::Text(title.into())];
        for values in [bound(0,"a-1","Я🙂"),bound(10,"x","я")] { p.validate_guards(&values).unwrap(); }
        for values in [bound(-1,"a","x"),bound(11,"a","x"),bound(1,"a/b","x"),bound(1,"a","   "),bound(1,"a","абв"),bound(1,"a","\u{2003}")] {
            assert!(p.validate_guards(&values).is_err());
        }
    }
    #[test]
    fn calendar_guard() {
        let p=program("    require title date\n").unwrap();
        for s in ["2024-02-29","2000-02-29","0001-01-01","9999-12-31"] { assert!(p.validate_guards(&[Cell::Int(1),Cell::Text("a".into()),Cell::Text(s.into())]).is_ok()); }
        for s in ["1900-02-29","2026-02-29","2026-04-31","0000-01-01","2026-00-01","2026-01-00","2026-1-01","２０２６-01-01","2026-01-01T00:00"] { assert!(!valid_date(s),"{s}"); }
        assert!(program("    require amount date\n").is_err());
    }
    #[test]
    fn invalid_declarations_fail_at_check() {
        for rule in ["require missing key","require amount key","require title range 0 1","require id length 3 2","require id length 0 65537","require amount range 2147483648 2147483649","require amount range 5 1","require id key extra","require id key\n    require id key","require id key\n    param extra: int"] {
            assert!(program(&format!("    {rule}\n")).is_err(),"{rule}");
        }
    }
}
