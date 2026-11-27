//! A17: explicit loopback-only SQL API with static statements, named scalar parameters.
//! Separate from the stateful HTTP DSL. No arbitrary SQL submitted over HTTP.
use super::{http, identifier, pathname, transaction::valid_key, RuntimeOptions, StrictObject};
use crate::{database, model::{fail,Error,Result}};
use sedravasql::native_log::{NativeLog,NativeLimits,Error as DbError,sql::{SqlKind,SqlResult}};
use serde::Deserialize;
use sha2::{Sha256,Digest};
use std::{collections::BTreeMap,io::Write,net::TcpListener,path::Path,time::{Duration,Instant}};
#[derive(Clone,Copy,Deserialize,PartialEq,Eq)]
#[serde(rename_all="snake_case")]
enum Role { Read, Write }
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Credential { id:String, sha256:String, role:Role }
pub struct Auth { credentials:Vec<Credential> }
impl Auth {
    #[cfg(unix)]
    pub fn load(path:&Path)->Result<Self>{
        use std::{fs::OpenOptions,io::Read,os::unix::fs::{OpenOptionsExt,MetadataExt}};
        use rustix::fs::OFlags;
        if !path.is_absolute(){return fail("E_SQL_API_AUTH: absolute credentials file required");}
        let file=OpenOptions::new().read(true).custom_flags((OFlags::NOFOLLOW|OFlags::NONBLOCK).bits() as i32)
            .open(path).map_err(|_|Error("E_SQL_API_AUTH: cannot open credentials".into()))?;
        let m=file.metadata().map_err(|_|Error("E_SQL_API_AUTH: metadata".into()))?;
        if !m.is_file()||m.nlink()!=1||m.uid()!=rustix::process::geteuid().as_raw()||m.mode()&0o077!=0||m.len()>16384{
            return fail("E_SQL_API_AUTH: credentials must be private owner-owned regular single-link file");
        }
        let mut raw=Vec::new();file.take(16385).read_to_end(&mut raw).map_err(|_|Error("E_SQL_API_AUTH: read failed".into()))?;
        if raw.len()>16384{return fail("E_SQL_API_AUTH: credential budget");}
        let credentials:Vec<Credential>=serde_json::from_slice(&raw).map_err(|_|Error("E_SQL_API_AUTH: invalid credential JSON".into()))?;
        let mut ids=std::collections::BTreeSet::new();let mut hashes=std::collections::BTreeSet::new();
        if credentials.is_empty()||credentials.len()>32{return fail("E_SQL_API_AUTH: credential count");}
        for c in &credentials {
            if !identifier(&c.id)||c.id.len()>48||!ids.insert(&c.id)||!hashes.insert(&c.sha256)||c.sha256.len()!=64||!c.sha256.bytes().all(|b|b.is_ascii_digit()||(b'a'..=b'f').contains(&b)){
                return fail("E_SQL_API_AUTH: invalid or duplicate credential");
            }
        }
        Ok(Self{credentials})
    }
    #[cfg(not(unix))]
    pub fn load(_path:&Path)->Result<Self>{fail("E_SQL_API_AUTH: private credentials require Unix")}
    fn authenticate(&self,header:Option<&str>)->Option<&Credential>{
        let token=header?.strip_prefix("Bearer ")?;
        // Operator-generated 32-byte random lowercase hex token. Store only its SHA-256.
        if token.len()!=64||!token.bytes().all(|b|b.is_ascii_digit()||(b'a'..=b'f').contains(&b)){return None;}
        let digest=format!("{:x}",Sha256::digest(token.as_bytes()));
        let mut found=None;
        for c in &self.credentials {
            let mismatch=c.sha256.bytes().zip(digest.bytes()).fold(0u8,|v,(a,b)|v|(a^b));
            if std::hint::black_box(mismatch)==0{found=Some(c);}
        }
        found
    }
}
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
fn reply(api:&Api,db:&mut NativeLog,request:http::Request,auth:Option<&Auth>)->(http::Response,bool){
    let error=|status,code| (http::Response::error(status,code),false);
    let principal=if let Some(auth)=auth{
        match auth.authenticate(request.authorization.as_deref()){
            Some(c)=>Some(c),
            None=>return error(401,"AUTH_REQUIRED"),
        }
    }else{
        if request.authorization.is_some(){return error(400,"AUTH_NOT_CONFIGURED");}
        None
    };
    let Some(route)=api.routes.get(&request.path) else{return error(404,"NOT_FOUND")};
    if route.kind()==SqlKind::Write&&principal.is_some_and(|c|c.role!=Role::Write){return error(403,"WRITE_FORBIDDEN");}
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
            let bytes=match principal{
                Some(c)=>serde_json::to_vec(&("auth-v1",&api.name,&request.path,&c.id,key)),
                None=>serde_json::to_vec(&(&api.name,&request.path,key)),
            }.expect("scalar strings");
            Some(format!("api{:x}",Sha256::digest(bytes)))
        }
    };
    match route.execute_on(db,&params,key.as_deref()){
        Ok(result)=>{
            let replay=matches!(&result,SqlResult::Write{replayed:true,..}|SqlResult::Transaction{replayed:true,..});
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
/// Explicit allowlisted static assets, loaded once before binding the listener.
pub struct WebUi {
    html: Vec<u8>,
    script: Vec<u8>,
    style: Vec<u8>,
}
impl WebUi {
    #[cfg(unix)]
    pub fn load(dir: &Path) -> Result<Self> {
        use std::io::Read;
        use std::os::unix::fs::OpenOptionsExt;
        use rustix::fs::OFlags;
        if !dir.is_absolute() || !std::fs::symlink_metadata(dir).is_ok_and(|m|m.is_dir()) {
            return fail("E_SQL_UI: absolute non-symlink asset directory required");
        }
        let read = |name: &str| -> Result<Vec<u8>> {
            let file = std::fs::OpenOptions::new().read(true)
                .custom_flags((OFlags::NOFOLLOW | OFlags::NONBLOCK).bits() as i32)
                .open(dir.join(name)).map_err(|_|Error("E_SQL_UI: cannot open asset".into()))?;
            let m=file.metadata().map_err(|_|Error("E_SQL_UI: asset metadata".into()))?;
            if !m.is_file() || m.len()==0 || m.len()>262144 {
                return fail("E_SQL_UI: expected bounded regular asset");
            }
            let mut bytes=Vec::new();
            file.take(262145).read_to_end(&mut bytes).map_err(|_|Error("E_SQL_UI: asset read".into()))?;
            if bytes.is_empty() || bytes.len()>262144 || std::str::from_utf8(&bytes).is_err() {
                return fail("E_SQL_UI: expected bounded UTF-8 asset");
            }
            Ok(bytes)
        };
        Ok(Self{html:read("index.html")?,script:read("app.js")?,style:read("app.css")?})
    }
    #[cfg(not(unix))]
    pub fn load(_dir: &Path) -> Result<Self> { fail("E_SQL_UI: Unix asset loader required") }
    fn asset(&self,path:&str)->Option<(&'static str,&[u8])>{
        match path {
            "/" => Some(("text/html; charset=utf-8",&self.html)),
            "/ui-script" => Some(("text/javascript; charset=utf-8",&self.script)),
            "/ui-style" => Some(("text/css; charset=utf-8",&self.style)),
            _=>None,
        }
    }
}
pub fn serve(api:&Api,path:&Path,trusted:bool,allow_write:bool,limits:NativeLimits,options:RuntimeOptions)->Result<()>{
    serve_with_auth(api,path,trusted,allow_write,limits,options,None)
}
pub fn serve_with_auth(api:&Api,path:&Path,trusted:bool,allow_write:bool,limits:NativeLimits,options:RuntimeOptions,auth:Option<&Auth>)->Result<()>{
    serve_with_ui(api,path,trusted,allow_write,limits,options,auth,None)
}
pub fn serve_with_ui(api:&Api,path:&Path,trusted:bool,allow_write:bool,limits:NativeLimits,options:RuntimeOptions,auth:Option<&Auth>,ui:Option<&WebUi>)->Result<()>{
    if ui.is_some() && (auth.is_none() || ["/","/ui-script","/ui-style"].iter().any(|p|api.routes.contains_key(*p))) {
        return fail("E_SQL_UI: authentication required and UI routes reserved");
    }
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
        #[cfg(unix)]
        {
            use rustix::event::{poll, PollFd, PollFlags, Timespec};
            let remaining=idle.saturating_sub(last.elapsed());
            if remaining.is_zero(){break;}
            let timeout=Timespec{tv_sec:remaining.as_secs() as _,tv_nsec:remaining.subsec_nanos() as _};
            let mut fds=[PollFd::new(&listener,PollFlags::IN)];
            match poll(&mut fds,Some(&timeout)){
                Ok(0)=>break,
                Ok(_)=>{},
                Err(rustix::io::Errno::INTR)=>continue,
                Err(e)=>return fail(format!("E_SQL_API_POLL: {e}")),
            }
        }

        match listener.accept(){
            Ok((mut stream,_))=>{
                let _=stream.set_read_timeout(Some(Duration::from_millis(1200)));
                let _=stream.set_write_timeout(Some(Duration::from_millis(1200)));
                let (response,stop)=match http::parse_request(&mut stream){
                    Ok(r)=>{
                        if let Some((mime,bytes))=ui.and_then(|u|u.asset(&r.path)){
                            if r.method=="GET" && r.body.is_empty() && r.expected_revision.is_none() && r.idempotency_key.is_none(){
                                http::finish_asset(&mut stream,mime,bytes);
                                served+=1;last=Instant::now();continue;
                            }
                            (http::Response::error(405,"UI_GET_ONLY").with_allow("GET".into()),false)
                        }else{reply(api,&mut db,r,auth)}
                    },
                    Err(e)=>(e,false)
                };
                http::finish(&mut stream,response);
                if stop{return fail("E_SQL_API: storage uncertain; stopped");}
                served+=1;last=Instant::now();
            }
            Err(e) if e.kind()==std::io::ErrorKind::WouldBlock=>{
                #[cfg(not(unix))]
                std::thread::sleep(Duration::from_millis(10));
            },
            Err(e) if e.kind()==std::io::ErrorKind::Interrupted=>continue,
            Err(e)=>return fail(format!("E_SQL_API: {e}")),
        }
    }
    println!("STOPPED requests={served}");Ok(())
}
