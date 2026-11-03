"""Shared collection backend metadata and portable Web runtime emission."""
import json
from sedrava_records import ListValue, fingerprint


STRICT_JSON = r'''// Strict bounded JSON parser: duplicate keys and non-JSON numeric constants reject.
function strictJSON(raw) {
  if (typeof raw !== 'string' || raw.length > 200000) throw Error('Snapshot too large');
  let i=0;
  function ws(){while (/\s/.test(raw[i]||'') && i<raw.length) { if (!' \n\r\t'.includes(raw[i])) throw Error('Invalid whitespace'); i++; }}
  function value(depth=0){
    if(depth>32) throw Error('JSON nesting limit'); ws(); const start=i;
    if(raw[i]==='"'){ i++; while(i<raw.length){if(raw[i]==='\\'){i+=2;continue;} if(raw[i++]==='"') return JSON.parse(raw.slice(start,i));} throw Error('Unterminated string'); }
    if(raw[i]==='{'){ i++;const out=Object.create(null); ws();if(raw[i]==='}'){i++;return out;} while(true){ws();if(raw[i]!=='"')throw Error('Key required');const key=value(depth+1);ws();if(raw[i++]!==':'||Object.hasOwn(out,key))throw Error('Duplicate or invalid key');out[key]=value(depth+1);ws();const end=raw[i++];if(end==='}')return out;if(end!==',')throw Error('Invalid object');}}
    if(raw[i]==='['){i++;const out=[];ws();if(raw[i]===']'){i++;return out;}while(true){out.push(value(depth+1));ws();const end=raw[i++];if(end===']')return out;if(end!==',')throw Error('Invalid array');}}
    const match=/^(?:true|false|null|-?(?:0|[1-9][0-9]*))/.exec(raw.slice(i));if(!match)throw Error('Invalid JSON');i+=match[0].length;return JSON.parse(match[0]);
  }
  const result=value();ws();if(i!==raw.length)throw Error('Trailing JSON');return result;
}
'''

def metadata(program):
    return {k: {'capacity': v.kind.capacity, 'fields': {name: {int:'number', bool:'boolean', str:'string'}[kind] for name, kind in v.kind.record.fields}} for k, v in program.states.items() if isinstance(v, ListValue)}


def js_runtime(program, quote):
    return 'const collectionTypes = JSON.parse(' + quote(json.dumps(metadata(program))) + ')'  + ';\nconst signature = ' + quote(fingerprint(program)) + ';\n' + r'''
function exactKeys(value, keys) { return value !== null && typeof value === 'object' && !Array.isArray(value) && Object.keys(value).length === keys.length && keys.every(k => Object.hasOwn(value,k)); }
function validRecord(row, fields, identity) {
  if (!exactKeys(row, [...Object.keys(fields), ...(identity ? ['id'] : [])])) return false;
  return Object.entries(fields).every(([k,t]) => typeof row[k] === t && (t === 'number' ? Number.isInteger(row[k]) && row[k] >= -2147483648 && row[k] <= 2147483647 : t === 'string' ? validText(row[k]) : true));
}
function validCollection(value, type) {
  if (!exactKeys(value,['next_id','items']) || !Number.isInteger(value.next_id) || value.next_id < 1 || value.next_id > 2147483647 || !Array.isArray(value.items) || value.items.length > type.capacity) return false;
  const ids = new Set();
  for (const row of value.items) {
    if (!validRecord(row,type.fields,true) || !Number.isInteger(row.id) || row.id <= 0 || row.id >= value.next_id || ids.has(row.id)) return false;
    ids.add(row.id);
  }
  return true;
}
function collectionOp(name, capacity, list, arg, record) {
  if (name === 'count') return list.items.length;
  if (name === 'next_id') return list.next_id;
  if (name === 'append') {
    if (list.items.length >= capacity) throw Error('Collection capacity exceeded');
    if (list.next_id === 2147483647) throw Error('Identity exhausted');
    return {next_id:list.next_id+1,items:[...list.items,{id:list.next_id,...arg}]};
  }
  const found = list.items.find(row => row.id === arg);
  if (name === 'has') return !!found;
  if (!found) throw Error('Missing record identity');
  if (name === 'get') { const {id,...fields} = found; return fields; }
  return {next_id:list.next_id,items:name === 'remove' ? list.items.filter(row=>row.id!==arg) : list.items.map(row=>row.id===arg ? {id:arg,...record} : row)};
}
''' + STRICT_JSON + r'''function restoreSnapshot(raw) {
  const saved = strictJSON(raw);
  if (!exactKeys(saved,['schema','signature','state']) || saved.schema !== 1 || saved.signature !== signature || !exactKeys(saved.state,persistentKeys)) throw Error('Incompatible snapshot');
  const candidate = {...initialState,...saved.state};
  if (!validateState(candidate)) throw Error('Invalid snapshot values or rules');
  return candidate;
}
function saveSnapshot() {
  // Never replace rejected data with defaults or a new session's edits.
  if (restoreError) throw Error('Saved data rejected; original retained');
  const previous = localStorage.getItem(storageKey);
  if (previous !== null) restoreSnapshot(previous);
  const saved=Object.fromEntries(persistentKeys.map(k=>[k,state[k]]));
  const raw=JSON.stringify({schema:1,signature,state:saved});
  if(raw.length>200000)throw Error('Snapshot too large');
  localStorage.setItem(storageKey,raw);
}
function renderCollections() {
  document.querySelectorAll('[data-list]').forEach(el=>{
    el.replaceChildren();
    for (const row of state[el.dataset.list].items) {
      const item=document.createElement('li');item.dataset.id=String(row.id);
      const label=document.createElement('span');label.textContent=Object.entries(row).filter(([k])=>k!=='id').map(([k,v])=>k+': '+v).join(' · ');item.append(label);
      const button=document.createElement('button');button.textContent='Select / Выбрать';button.type='button';button.setAttribute('aria-label','Select '+row.id);
      button.onclick=()=>{ const next=editState(state,el.dataset.select,row.id);if(next===state){showError('Selection rejected');return;}state=next;showError('');try{saveSnapshot();}catch(_){showError('Could not save state');}render(true);};
      item.append(button);el.append(item);
    }
  });
}
'''


def kt_support(program, quoted):
    kinds = {int:'Int', bool:'Boolean', str:'String'}
    lines = [
        'internal interface SdrRecord { fun check(); fun fields(): Map<String, Any?> }',
        'internal data class SdrItem<T: SdrRecord>(val id: Int, val record: T)',
        'internal data class SdrList<T: SdrRecord>(val capacity: Int, val items: List<SdrItem<T>> = emptyList(), val next_id: Int = 1) {',
        '  fun check() { require(capacity in 1..100 && items.size <= capacity && next_id > 0); val ids=mutableSetOf<Int>(); for (row in items) { require(row.id > 0 && row.id < next_id && ids.add(row.id)); row.record.check() } }',
        '}',
        'internal fun <T: SdrRecord> sdr_count(list: SdrList<T>) = list.items.size',
        'internal fun <T: SdrRecord> sdr_next_id(list: SdrList<T>) = list.next_id',
        'internal fun <T: SdrRecord> sdr_has(list: SdrList<T>, id: Int) = list.items.any { it.id == id }',
        'internal fun <T: SdrRecord> sdr_get(list: SdrList<T>, id: Int): T = list.items.find { it.id == id }?.record ?: throw IllegalArgumentException("Missing record identity")',
        'internal fun <T: SdrRecord> sdr_append(list: SdrList<T>, record: T): SdrList<T> { require(list.items.size < list.capacity && list.next_id < Int.MAX_VALUE); record.check(); return list.copy(items=list.items + SdrItem(list.next_id,record), next_id=list.next_id+1) }',
        'internal fun <T: SdrRecord> sdr_update(list: SdrList<T>, id: Int, record: T): SdrList<T> { sdr_get(list,id); record.check(); return list.copy(items=list.items.map { if(it.id==id) SdrItem(id,record) else it }) }',
        'internal fun <T: SdrRecord> sdr_remove(list: SdrList<T>, id: Int): SdrList<T> { sdr_get(list,id); return list.copy(items=list.items.filter { it.id!=id }) }',
    ]
    for name, record in program.records.items():
        lines += ['internal data class SdrRecord_' + name + '(' + ', '.join('val sdr_'+k+': '+kinds[t] for k,t in record.fields) + '): SdrRecord {', '  override fun check() {']
        lines += ['    checkedText(sdr_'+k+')' for k,t in record.fields if t is str]
        lines += ['  }', '  override fun fields(): Map<String, Any?> = mapOf(' + ', '.join(quoted(k)+' to sdr_'+k for k,_ in record.fields) + ')', '}']
    return lines


KT_JSON = r'''
// Strict JSON for snapshots; bounded depth and payload, duplicate keys rejected.
internal class SdrJson(val raw: String) {
  var i=0
  fun ws() { while(i<raw.length && raw[i] in " \r\n\t") i++ }
  fun parse(): Any? { require(raw.length<=200000); val result=value(0); ws(); require(i==raw.length); return result }
  fun value(depth: Int): Any? {
    require(depth<=32); ws(); require(i<raw.length)
    if(raw[i]=='"') return string()
    if(raw[i]=='{') { i++; val out=linkedMapOf<String,Any?>(); ws(); if(i<raw.length && raw[i]=='}'){i++;return out}; while(true){ws();val key=string();ws();require(i<raw.length && raw[i++]==':' && !out.containsKey(key));out[key]=value(depth+1);ws();require(i<raw.length);val end=raw[i++];if(end=='}')return out;require(end==',')} }
    if(raw[i]=='[') { i++; val out=mutableListOf<Any?>();ws();if(i<raw.length && raw[i]==']'){i++;return out};while(true){out.add(value(depth+1));ws();require(i<raw.length);val end=raw[i++];if(end==']')return out;require(end==',')} }
    for((word,result) in listOf("true" to true,"false" to false,"null" to null)){if(raw.startsWith(word,i)){i+=word.length;return result}}
    val match=Regex("-?(?:0|[1-9][0-9]*)").find(raw,i)
    require(match!=null && match.range.first==i);i+=match.value.length
    return match.value.toDouble()
  }
  fun string(): String {
    require(i<raw.length && raw[i++]=='"');val out=StringBuilder()
    while(i<raw.length){val c=raw[i++];if(c=='"')return out.toString();require(c.code>=32);if(c!='\\'){out.append(c);continue};require(i<raw.length);when(val e=raw[i++]){
      '"','\\','/' -> out.append(e)
      'b' -> out.append('\b')
      'f' -> out.append('\u000c')
      'n' -> out.append('\n')
      'r' -> out.append('\r')
      't' -> out.append('\t')
      'u' -> {require(i+4<=raw.length);val hex=raw.substring(i,i+4);require(hex.all{it in "0123456789abcdefABCDEF"});out.append(hex.toInt(16).toChar());i+=4}
      else -> throw IllegalArgumentException("Invalid JSON escape")
    }}
    throw IllegalArgumentException("Unterminated JSON string")
  }
}
internal fun sdrInt(value: Any?): Int { require(value is Number); val n=value.toDouble();require(n.isFinite() && n>=Int.MIN_VALUE.toDouble() && n<=Int.MAX_VALUE.toDouble() && n%1.0==0.0);return n.toInt() }
internal fun sdrString(value: Any?): String { require(value is String);return checkedText(value) }
internal fun sdrBool(value: Any?): Boolean { require(value is Boolean);return value }
internal fun sdrObject(value: Any?, keys: Set<String>): Map<*,*> { require(value is Map<*,*> && value.keys==keys);return value }
internal fun sdrEncode(value: Any?): String = when(value) {
  null -> "null"
  is String -> "\"" + buildString { for(c in value) when(c){'"'->append("\\\"");'\\'->append("\\\\");'\b'->append("\\b");'\u000c'->append("\\f");'\n'->append("\\n");'\r'->append("\\r");'\t'->append("\\t");else->if(c.code<32)append("\\u%04x".format(c.code))else append(c)} } + "\""
  is Boolean, is Int -> value.toString()
  is Map<*,*> -> value.entries.joinToString(",","{","}"){sdrEncode(it.key as String)+":"+sdrEncode(it.value)}
  is List<*> -> value.joinToString(",","[","]"){sdrEncode(it)}
  is SdrList<*> -> sdrEncode(mapOf("next_id" to value.next_id,"items" to value.items.map { mapOf("id" to it.id) + it.record.fields() }))
  else -> throw IllegalArgumentException("Invalid JSON value")
}
'''


def kt_persistence(program, quoted, literal):
    lines = [KT_JSON]
    for k,v in program.states.items():
        if not isinstance(v,ListValue): continue
        fields=v.kind.record.fields
        lines += ['internal fun decode_'+k+'(value: Any?): SdrList<SdrRecord_'+v.kind.record.name+'> {',
                  '  val raw=sdrObject(value,setOf("next_id","items"))',
                  '  val rows=raw["items"]; require(rows is List<*> && rows.size <= '+str(v.kind.capacity)+')',
                  '  return SdrList(capacity='+str(v.kind.capacity)+',next_id=sdrInt(raw["next_id"]),items=rows.map { row ->',
                  '    val item=sdrObject(row,setOf('+','.join(quoted(f) for f in ['id']+[n for n,_ in fields])+'))',
                  '    SdrItem(sdrInt(item["id"]),SdrRecord_'+v.kind.record.name+'('+','.join('sdr_'+n+'='+{int:'sdrInt',bool:'sdrBool',str:'sdrString'}[t]+'(item['+quoted(n)+'])' for n,t in fields)+'))', '  }).also { it.check() }', '}']
    persistent='setOf<String>('+','.join(quoted(k) for k in program.persistent)+')'
    allkeys='setOf<String>('+','.join(quoted(k) for k in program.states)+')'
    lines += ['internal fun snapshotState(state: SedravaState, full: Boolean = false): String {',
              '  val values=mapOf<String,Any?>('+','.join(quoted(k)+' to state.sdr_'+k for k in program.states)+').filterKeys { full || it in '+persistent+' }',
              '  val raw=sdrEncode(mapOf("schema" to 1,"signature" to '+quoted(fingerprint(program))+',"state" to values))',
              '  require(raw.length<=200000);return raw', '}',
              'internal fun restoreSnapshot(raw: String, full: Boolean = false): SedravaState {',
              '  val envelope=sdrObject(SdrJson(raw).parse(),setOf("schema","signature","state"))',
              '  require(sdrInt(envelope["schema"])==1 && envelope["signature"]=='+quoted(fingerprint(program))+')',
              '  val saved=sdrObject(envelope["state"],if(full) '+allkeys+' else '+persistent+')']
    for k,v in program.states.items():
        decoder='decode_'+k if isinstance(v,ListValue) else {int:'sdrInt',bool:'sdrBool',str:'sdrString'}[type(v)]
        condition='true' if k in program.persistent else 'full'
        lines.append('  val next_'+k+' = if('+condition+') '+decoder+'(saved['+quoted(k)+']) else '+literal(v))
    args=','.join('next_'+k for k in program.states)
    lines += ['  require(validState('+args+'));return SedravaState('+args+')', '}', 'internal fun snapshotValid(value: Any?): Boolean = try { require(value is String); restoreSnapshot(value); true } catch (_: IllegalArgumentException) { false }']
    return lines
