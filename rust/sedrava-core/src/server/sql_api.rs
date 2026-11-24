//! A17: explicit loopback-only SQL API with static statements, named scalar parameters.
//! Separate from the stateful HTTP DSL. No arbitrary SQL submitted over HTTP.
use super::{http, identifier, pathname, transaction::valid_key, RuntimeOptions, StrictObject};
use crate::{database, model::{fail,Error,Result}};
use sedravasql::native_log::{NativeLog,NativeLimits,Error as DbError,sql::{SqlKind,SqlResult}};
use serde::Deserialize;
use sha2::{Sha256,Digest};
use std::{collections::BTreeMap,io::Write,net::TcpListener,path::Path,thread,time::{Duration,Instant}};
pub struct Api {name:String,routes:BTreeMap<String,database::Program>}
pub fn parse(source:&str)->Result<Api>{
    if source.len()>32768||source.contains('\r')||source.contains('\0'){return fail("E_SQL_API: invalid source");}
    let mut lines=source.lines().filter(|l|!l.trim().is_empty()&&!l.trim_start().starts_with('#'));
    let name=lines.next().and_then(|l|l.strip_prefix("database-api ")).filter(|s|identifier(s)&&s.len()<=48).ok_or_else(||Error("E_SQL_API: expected database-api NAME".into()))?.to_owned();
    let mut routes=BTreeMap::new();let mut current:Option<(String,String)>=None;
    for line in lines{
        if let Some(raw)=line.strip_prefix("route POST "){
            if let Some((path,body))=current.take(){
                if routes.insert(path,database::parse(&body)?).is_some(){return fail("E_SQL_API: duplicate route");}
            }
            if routes.len()>=16{return fail("E_SQL_API: route budget");}
            let raw=raw.strip_suffix(':').ok_or_else(||Error("E_SQL_API: route must end with colon".into()))?;
            let path:String=serde_json::from_str(raw).map_err(|_|Error("E_SQL_API: route path string".into()))?;
            if !pathname(&path){return fail("E_SQL_API: invalid path");}
            current=Some((path,format!("database {name}\n")));
        }else{
            let (_,body)=current.as_mut().ok_or_else(||Error("E_SQL_API: expected route POST".into()))?;
            if !line.starts_with("    "){return fail("E_SQL_API: expected indented statement");}
            body.push_str(line);body.push('\n');
        }
    }
    if let Some((path,body))=current.take(){
        if routes.insert(path,database::parse(&body)?).is_some(){return fail("E_SQL_API: duplicate route");}
    }
    if routes.is_empty(){return fail("E_SQL_API: no routes");}
    Ok(Api{name,routes})
}
fn reply(api:&Api,db:&mut NativeLog,request:http::Request)->(http::Response,bool){
    let error=|status,code| (http::Response::error(status,code),false);
    let Some(route)=api.routes.get(&request.path) else{return error(404,"NOT_FOUND")};
    if request.method!="POST"{return (http::Response::error(405,"METHOD_NOT_ALLOWED").with_allow("POST".into()),false);}
    if request.expected_revision.is_some(){return error(400,"REVISION_HEADER_UNSUPPORTED");}
    if request.content_type.as_deref()!=Some("application/json"){return error(415,"JSON_CONTENT_TYPE_REQUIRED");}
    let mut decoder=serde_json::Deserializer::from_slice(&request.body);
    let object=match StrictObject::deserialize(&mut decoder){
        Ok(StrictObject(value)) if decoder.end().is_ok()=>value,
        _=>return error(400,"INVALID_JSON"),
    };
    let params=match route.bind_object(&object){Ok(p)=>p,Err(_)=>return error(422,"REQUEST_SCHEMA_MISMATCH")};
    let key=match route.kind(){
        SqlKind::Query=>{if request.idempotency_key.is_some(){return error(400,"READ_CANNOT_USE_TRANSACTION_HEADERS");}None}
        SqlKind::Write=>{
            let Some(key)=request.idempotency_key.as_deref() else{return error(428,"IDEMPOTENCY_KEY_REQUIRED")};
            if !valid_key(key){return error(400,"INVALID_IDEMPOTENCY_KEY");}
            let bytes=serde_json::to_vec(&(&api.name,&request.path,key)).expect("scalar strings");
            Some(format!("api{:x}",Sha256::digest(bytes)))
        }
    };
    match route.execute_on(db,&params,key.as_deref()){
        Ok(result)=>{
            let replay=matches!(&result,SqlResult::Write{replayed:true,..});
            let value=serde_json::to_value(result).expect("serializable bounded SQL result");
            let response=http::Response::json(200,value);
            (if replay{response.as_replay()}else{response},false)
        }
        Err(DbError::Conflict(_))=>error(409,"SQL_CONFLICT"),
        Err(DbError::Capacity(_))=>error(507,"SQL_CAPACITY"),
        Err(DbError::Invalid(_))=>error(422,"SQL_INVALID"),
        Err(_)=>(http::Response::error(503,"SQL_STORAGE_UNCERTAIN"),true),
    }
}
pub fn serve(api:&Api,path:&Path,trusted:bool,allow_write:bool,limits:NativeLimits,options:RuntimeOptions)->Result<()>{
    if !trusted||!path.is_absolute(){return fail("E_SQL_API_POLICY: trusted and absolute DB path required");}
    if api.routes.values().any(|p|p.kind()==SqlKind::Write)&&!allow_write{return fail("E_SQL_API_POLICY: write routes require --allow-write");}
    if !(1..=10000).contains(&options.max_requests)||!(500..=120000).contains(&options.idle_ms){return fail("E_SQL_API: invalid runtime limits");}
    let mut db=NativeLog::open(path).map_err(|e|Error(format!("E_SQL_API: {e}")))?;
    db.set_limits(limits).map_err(|e|Error(format!("E_SQL_API: {e}")))?;
    db.verify().map_err(|e|Error(format!("E_SQL_API: {e}")))?;
    let listener=TcpListener::bind(("127.0.0.1",options.port)).map_err(|e|Error(format!("E_SQL_API_BIND: {e}")))?;
    listener.set_nonblocking(true).map_err(|e|Error(e.to_string()))?;
    println!("LISTENING http://127.0.0.1:{}",listener.local_addr().map_err(|e|Error(e.to_string()))?.port());
    std::io::stdout().flush().map_err(|e|Error(e.to_string()))?;
    let idle=Duration::from_millis(options.idle_ms.into());let mut last=Instant::now();let mut served=0;
    while served<options.max_requests&&last.elapsed()<idle{
        match listener.accept(){
            Ok((mut stream,_))=>{
                let _=stream.set_read_timeout(Some(Duration::from_millis(1200)));
                let _=stream.set_write_timeout(Some(Duration::from_millis(1200)));
                let (response,stop)=match http::parse_request(&mut stream){Ok(r)=>reply(api,&mut db,r),Err(e)=>(e,false)};
                http::finish(&mut stream,response);
                if stop{return fail("E_SQL_API: storage uncertain; stopped");}
                served+=1;last=Instant::now();
            }
            Err(e) if e.kind()==std::io::ErrorKind::WouldBlock=>thread::sleep(Duration::from_millis(10)),
            Err(e) if e.kind()==std::io::ErrorKind::Interrupted=>continue,
            Err(e)=>return fail(format!("E_SQL_API: {e}")),
        }
    }
    println!("STOPPED requests={served}");Ok(())
}
