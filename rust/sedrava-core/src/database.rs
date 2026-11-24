//! A16 standalone, explicit-capability SQL host domain.
//! One checked statement, positional typed parameters, no implicit IO or interpolation.
use crate::model::{fail, Error, Result};
use sedravasql::native_log::{sql::{self,SqlKind,SqlResult},table::Cell,NativeLog};
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
pub struct Program{
    pub name:String,
    params:Vec<(String,Type)>,
    sql:String,
    kind:SqlKind,
}
pub fn parse(source:&str)->Result<Program>{
    if source.len()>32768{return fail("E_DATABASE: source budget");}
    let mut lines=source.lines().filter(|l|!l.trim().is_empty()&&!l.trim_start().starts_with('#'));
    let name=lines.next().and_then(|l|l.strip_prefix("database ")).filter(|s|identifier(s)).ok_or_else(||Error("E_DATABASE: expected database NAME".into()))?.to_owned();
    let mut names=BTreeSet::new();let mut params=Vec::new();let mut statement=None;
    for line in lines{
        if statement.is_some(){return fail("E_DATABASE: only one statement allowed");}
        let line=line.strip_prefix("    ").ok_or_else(||Error("E_DATABASE: expected four spaces".into()))?;
        if let Some(raw)=line.strip_prefix("param "){
            let (name,kind)=raw.split_once(": ").ok_or_else(||Error("E_DATABASE: expected param NAME: TYPE".into()))?;
            if !identifier(name)||!names.insert(name)||params.len()>=32{return fail("E_DATABASE: invalid/duplicate parameter");}
            params.push((name.to_owned(),Type::parse(kind)?));
        }else{
            let (kind,raw)=if let Some(s)=line.strip_prefix("query "){(SqlKind::Query,s)}else if let Some(s)=line.strip_prefix("execute "){(SqlKind::Write,s)}else{return fail("E_DATABASE: expected param, query or execute");};
            let text:String=serde_json::from_str(raw).map_err(|_|Error("E_DATABASE: expected quoted SQL string".into()))?;
            let samples=params.iter().map(|(_,t)|t.sample()).collect::<Vec<_>>();
            let actual=sql::check(&text,&samples).map_err(|e|Error(format!("E_DATABASE: {e}")))?;
            if actual!=kind{return fail("E_DATABASE: SQL statement kind mismatch");}
            statement=Some((kind,text));
        }
    }
    let (kind,sql)=statement.ok_or_else(||Error("E_DATABASE: missing statement".into()))?;
    Ok(Program{name,params,sql,kind})
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
    pub(crate) fn execute_on(&self,db:&mut NativeLog,values:&[Cell],request:Option<&str>)->sedravasql::native_log::Result<SqlResult>{
        sql::execute_bound(db,&self.sql,values,request)
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
    sql::check(&program.sql,&bound).map_err(|e|Error(format!("E_DATABASE: {e}")))?;
    let mut db=NativeLog::open(path).map_err(|e|Error(format!("E_DATABASE: {e}")))?;
    sql::execute_bound(&mut db,&program.sql,&bound,request).map_err(|e|Error(format!("E_DATABASE: {e}")))
}
