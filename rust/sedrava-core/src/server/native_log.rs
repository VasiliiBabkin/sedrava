//! A12 experimental single-owner native append log, no SQLite database.
use super::kv_write::{BatchFailure, BatchPut, ServerBatchReceipt};
use super::state::{scalar_type, StateDef, Values};
use super::storage::signature;
use crate::model::{fail, Error, Result};
use sedravasql::native_log::{NativeChange, NativeLog, NativeMutation, TransactionalStore, MAX_VALUE_BYTES};
use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};
use sha2::{Digest, Sha256};
use std::{collections::{BTreeMap,BTreeSet}, path::Path};

const NS: &str = "sedrava_native_a12";
const STATE_KEY: &str = "state";
const STATE_SCHEMA: &str = "sedrava.server.native.state.v1";
const RECEIPT_SCHEMA: &str = "sedrava.server.native.batch.v1";
#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct StateSnapshot {
    schema: String,
    signature: String,
    revision: u32,
    state: Values,
}

pub(super) struct NativeLogStore {
    db: NativeLog,
    signature: String,
    defs: BTreeMap<String, StateDef>,
    revision: u32,
}
fn valid_state(defs: &BTreeMap<String, StateDef>, values: &Values) -> bool {
    values.len()==defs.len() && defs.iter().all(|(k,d)| values.get(k).and_then(scalar_type)==Some(d.kind))
}
fn valid_text(value: &str) -> bool {
    value.chars().count()<=1024 && !value.chars().any(char::is_control)
}
fn put(ns: &str,key: &str,rev:u64,value:String)->NativeMutation {
    NativeMutation { namespace:ns.into(), key:key.into(), expected_revision:rev, change:NativeChange::Put(value) }
}
impl NativeLogStore {
    pub(super) fn open(path:&Path,name:&str,defs:&BTreeMap<String,StateDef>,source_sha:&str)->Result<(Self,Values,u32)> {
        if !path.is_absolute() || defs.is_empty() {
            return fail("E_SERVER_NATIVE_LOG: absolute existing log and declared state required");
        }
        let sig=signature(name,defs)?;
        let raw=serde_json::to_vec(&(STATE_SCHEMA,source_sha,sig))
            .map_err(|_|Error("E_SERVER_NATIVE_LOG: signature failed".into()))?;
        let signature=format!("{:x}",Sha256::digest(raw));
        let mut db=NativeLog::open(path).map_err(|_|Error("E_SERVER_NATIVE_LOG: open/lock/verification failed".into()))?;
        db.verify().map_err(|_|Error("E_SERVER_NATIVE_LOG: verify failed".into()))?;
        let saved=db.read(NS,STATE_KEY).map_err(|_|Error("E_SERVER_NATIVE_LOG: state read failed".into()))?;
        let (values,revision)=match saved {
            Some(row)=>{
                let text=row.value.ok_or_else(||Error("E_SERVER_NATIVE_LOG: deleted state".into()))?;
                let state:StateSnapshot=serde_json::from_str(&text).map_err(|_|Error("E_SERVER_NATIVE_LOG: invalid state".into()))?;
                if state.schema!=STATE_SCHEMA || state.signature!=signature
                    || u64::from(state.revision)!=row.revision || state.revision>i32::MAX as u32
                    || !valid_state(defs,&state.state) {
                    return fail("E_SERVER_NATIVE_LOG: source/state signature or revision mismatch");
                }
                (state.state,state.revision)
            }
            None=>{
                // An empty journal is required for first initialization. Do
                // not attach another application's journal to this server.
                if db.sequence()!=0 { return fail("E_SERVER_NATIVE_LOG: unbound nonempty journal"); }
                (defs.iter().map(|(k,v)|(k.clone(),v.initial.clone())).collect(),0)
            }
        };
        Ok((Self{db,signature,defs:defs.clone(),revision},values,revision))
    }
    pub(super) fn read_text_snapshot(&self,keys:&[(String,String)])->Result<Vec<Option<(String,u64)>>> {
        let mut seen=BTreeSet::new();
        if keys.is_empty() || keys.len()>16 || keys.iter().any(|(ns,k)| ns.starts_with("sedrava_native") || !seen.insert((ns,k))) {
            return fail("E_SERVER_DB: invalid or reserved snapshot key list");
        }
        let refs:Vec<_>=keys.iter().map(|(ns,k)|(ns.as_str(),k.as_str())).collect();
        let snap=self.db.read_snapshot(&refs).map_err(|_|Error("E_SERVER_DB: native snapshot failed".into()))?;
        snap.rows.into_iter().map(|row| match row {
            Some(row)=>match row.value {
                Some(v) if valid_text(&v)=>Ok(Some((v,row.revision))),
                Some(_)=>fail("E_SERVER_DB: stored value outside text scalar limits"),
                None=>Ok(None),
            },
            None=>Ok(None),
        }).collect()
    }
    fn scoped(&self,method:&str,path:&str,key:&str)->String {
        let raw=serde_json::to_vec(&(RECEIPT_SCHEMA,&self.signature,method,path,key)).expect("static tuple");
        format!("r{:x}",Sha256::digest(raw))
    }
    pub(super) fn lookup_route_batch(&self,declarations:&[BatchPut],method:&str,path:&str,client_key:&str)->Result<Option<ServerBatchReceipt>> {
        let scoped=self.scoped(method,path,client_key);
        let bad=||Error("E_SERVER_NATIVE_LOG: receipt mismatch".into());
        let row=self.db.read(NS,&scoped).map_err(|_|bad())?;
        let engine=self.db.lookup_receipt(&scoped).map_err(|_|bad())?;
        match (row,engine) {
            (None,None)=>Ok(None),
            (Some(row),Some(engine))=>{
                let text=row.value.as_deref().ok_or_else(bad)?;
                let app:ServerBatchReceipt=serde_json::from_str(text).map_err(|_|bad())?;
                if row.revision!=1 || app.schema!=RECEIPT_SCHEMA || app.program_signature!=self.signature
                    || app.route!=format!("{method} {path}") || app.client_key!=client_key
                    || app.state_revision==0 || app.state_revision>self.revision
                    || app.key_revisions.len()!=2 || declarations.len()!=2 || engine.entries.len()!=4
                    || !matches!(app.status,200..=202) || app.fingerprint.len()!=64
                    || !app.fingerprint.bytes().all(|b|b.is_ascii_digit() || (b'a'..=b'f').contains(&b)) {
                    return Err(bad());
                }
                for ((entry,decl),rev) in engine.entries[..2].iter().zip(declarations).zip(&app.key_revisions) {
                    if entry.namespace!=decl.namespace || entry.key!=decl.key || entry.revision!=u64::from(*rev)
                        || *rev==0 || *rev>i32::MAX as u32 || entry.value.is_none() {return Err(bad());}
                }
                let state=&engine.entries[2];
                if state.namespace!=NS || state.key!=STATE_KEY || state.revision!=u64::from(app.state_revision)
                    || state.value.is_none() || engine.entries[3]!=row { return Err(bad()); }
                Ok(Some(app))
            }
            _=>Err(bad()),
        }
    }
    #[allow(clippy::too_many_arguments)]
    pub(super) fn commit_route_batch(&mut self,declarations:&[BatchPut],request:&Values,candidate:&Values,expected_state:u32,method:&str,path:&str,client_key:&str,fingerprint:&str,status:u16,response:Map<String,Value>)
        ->std::result::Result<(ServerBatchReceipt,bool),BatchFailure> {
        if declarations.len()!=2 || method!="PUT" || !matches!(status,200..=202)
            || expected_state!=self.revision || !valid_state(&self.defs,candidate) {return Err(BatchFailure::Uncertain);}
        let revision=expected_state.checked_add(1).filter(|v|*v<=i32::MAX as u32).ok_or(BatchFailure::Invalid)?;
        let mut ops=Vec::with_capacity(4);
        let mut key_revisions=Vec::with_capacity(2);
        for d in declarations {
            let value=request.get(&d.value_field).and_then(Value::as_str).filter(|v|valid_text(v)).ok_or(BatchFailure::Invalid)?;
            let expected=request.get(&d.revision_field).and_then(Value::as_i64).and_then(|v|u32::try_from(v).ok()).ok_or(BatchFailure::Invalid)?;
            let next=expected.checked_add(1).filter(|r|*r<=i32::MAX as u32).ok_or(BatchFailure::Invalid)?;
            ops.push(put(&d.namespace,&d.key,u64::from(expected),value.into()));
            key_revisions.push(next);
        }
        let state=StateSnapshot{schema:STATE_SCHEMA.into(),signature:self.signature.clone(),revision,state:candidate.clone()};
        let snapshot=serde_json::to_string(&state).map_err(|_|BatchFailure::Uncertain)?;
        let app=ServerBatchReceipt{schema:RECEIPT_SCHEMA.into(),program_signature:self.signature.clone(),route:format!("{method} {path}"),client_key:client_key.into(),fingerprint:fingerprint.into(),state_revision:revision,key_revisions,status,response};
        let receipt=serde_json::to_string(&app).map_err(|_|BatchFailure::Uncertain)?;
        if snapshot.len()>MAX_VALUE_BYTES || receipt.len()>MAX_VALUE_BYTES {return Err(BatchFailure::Invalid);}
        let scoped=self.scoped(method,path,client_key);
        ops.push(put(NS,STATE_KEY,u64::from(expected_state),snapshot));
        ops.push(put(NS,&scoped,0,receipt));
        match self.db.commit_batch(&scoped,&ops) {
            Ok(done)=>{
                if done.replayed || done.entries.len()!=4 || done.entries.iter().zip(&ops).any(|(r,o)|
                    r.namespace!=o.namespace || r.key!=o.key || r.revision!=o.expected_revision+1 ||
                    !matches!(&o.change,NativeChange::Put(v) if r.value.as_ref()==Some(v))) {
                    return Err(BatchFailure::Uncertain);
                }
                self.revision=revision;
                Ok((app,false))
            }
            Err(sedravasql::native_log::Error::Conflict(_))=>Err(BatchFailure::RevisionConflict),
            Err(sedravasql::native_log::Error::Invalid(_))=>Err(BatchFailure::Invalid),
            Err(_)=>Err(BatchFailure::Uncertain),
        }
    }
}
