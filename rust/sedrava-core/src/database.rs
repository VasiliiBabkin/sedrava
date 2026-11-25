//! A16 standalone, explicit-capability SQL host domain.
//! One checked statement, positional typed parameters, no implicit IO or interpolation.
use crate::model::{fail, Error, Result};
use sedravasql::native_log::{sql::{self,SqlKind,SqlResult,BoundStatement},table::Cell,NativeLog,NativeLimits,SqlStore};
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
    sql:String,
    transaction:Vec<(String,Vec<usize>)>,
    sequential:bool,
    kind:SqlKind,
}
pub fn parse(source:&str)->Result<Program>{
    if source.len()>32768{return fail("E_DATABASE: source budget");}
    let mut lines=source.lines().filter(|l|!l.trim().is_empty()&&!l.trim_start().starts_with('#'));
    let name=lines.next().and_then(|l|l.strip_prefix("database ")).filter(|s|identifier(s)).ok_or_else(||Error("E_DATABASE: expected database NAME".into()))?.to_owned();
    let mut names=BTreeSet::new();let mut params=Vec::new();let mut statement=None;let mut transaction=Vec::new();let mut sequential=false;
    for line in lines{
        if statement.is_some(){return fail("E_DATABASE: only one statement allowed");}
        let line=line.strip_prefix("    ").ok_or_else(||Error("E_DATABASE: expected four spaces".into()))?;
        if let Some(raw)=line.strip_prefix("param "){
            let (name,kind)=raw.split_once(": ").ok_or_else(||Error("E_DATABASE: expected param NAME: TYPE".into()))?;
            if !identifier(name)||!names.insert(name)||params.len()>=32{return fail("E_DATABASE: invalid/duplicate parameter");}
            params.push((name.to_owned(),Type::parse(kind)?));
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
            let (kind,raw)=if let Some(s)=line.strip_prefix("query "){(SqlKind::Query,s)}else if let Some(s)=line.strip_prefix("execute "){(SqlKind::Write,s)}else{return fail("E_DATABASE: expected param, query or execute");};
            let text:String=serde_json::from_str(raw).map_err(|_|Error("E_DATABASE: expected quoted SQL string".into()))?;
            let samples=params.iter().map(|(_,t)|t.sample()).collect::<Vec<_>>();
            let actual=sql::check(&text,&samples).map_err(|e|Error(format!("E_DATABASE: {e}")))?;
            if actual!=kind{return fail("E_DATABASE: SQL statement kind mismatch");}
            statement=Some((kind,text));
        }
    }
    let (kind,sql)=statement.ok_or_else(||Error("E_DATABASE: missing statement".into()))?;
    Ok(Program{name,params,sql,transaction,sequential,kind})
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
    pub(crate) fn execute_on(&self,db:&mut dyn SqlStore,values:&[Cell],request:Option<&str>)->sedravasql::native_log::Result<SqlResult>{
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
#[derive(Clone,Copy,Debug,Default,PartialEq,Eq)]
pub enum Backend { #[default] NativeLog, Cow }
impl Backend {
    pub fn parse(raw:&str)->Result<Self>{match raw{
        "native-log"=>Ok(Self::NativeLog),"cow"=>Ok(Self::Cow),
        _=>fail("E_DATABASE_POLICY: backend must be native-log or cow")
    }}
}
pub(crate) fn open_backend(path:&Path,backend:Backend,limits:NativeLimits)->sedravasql::native_log::Result<Box<dyn SqlStore>>{
    match backend {
        Backend::NativeLog=>{
            let mut db=NativeLog::open(path)?;
            db.set_limits(limits)?;
            db.verify()?;
            Ok(Box::new(db))
        },
        Backend::Cow=>{
            #[cfg(unix)]
            {
                let mut db=sedravasql::native_log::cow_store::CowStore::open(path)?;
                db.set_limits(limits)?;
                db.verify()?;
                Ok(Box::new(db))
            }
            #[cfg(not(unix))]
            Err(sedravasql::native_log::Error::Unsupported("COW backend requires Unix".into()))
        }
    }
}
pub fn run(program:&Program,path:&Path,trusted:bool,allow_write:bool,request:Option<&str>,supplied:&[String])->Result<SqlResult>{
    run_with_backend(program,path,trusted,allow_write,request,supplied,Backend::NativeLog)
}
pub fn run_with_backend(program:&Program,path:&Path,trusted:bool,allow_write:bool,request:Option<&str>,supplied:&[String],backend:Backend)->Result<SqlResult>{
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
    program.check_bound(&bound)?;
    let mut db=open_backend(path,backend,NativeLimits::default()).map_err(|e|Error(format!("E_DATABASE: {e}")))?;
    program.execute_on(db.as_mut(),&bound,request).map_err(|e|Error(format!("E_DATABASE: {e}")))
}
