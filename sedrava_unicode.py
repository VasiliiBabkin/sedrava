"""Versioned Unicode normalization/folding using shared data, not host libraries."""
import ast,json
from functools import lru_cache
from sedrava_unicode_data import VERSION,DATA,LICENSE_TEXT,MAX_EXPANSION
NORMALIZERS={'unicode_nfc':'NFC','unicode_nfd':'NFD','unicode_nfkc':'NFKC','unicode_nfkd':'NFKD'}

@lru_cache(maxsize=1)
def tables():
    rows={};compositions={}
    for item in DATA.split('|'):
        cp,ccc,flags,decomp,fold=item.split(':');cp=int(cp,16);flags=int(flags);ds=tuple(int(x,16) for x in decomp.split(',') if x);fs=tuple(int(x,16) for x in fold.split(',') if x)
        rows[cp]=(int(ccc),flags,ds,fs)
        if flags&2:compositions[ds]=cp
    return rows,compositions

def normalize_raw(value,form):
    from sedrava_core import checked_text
    checked_text(value)
    if form not in ('NFC','NFD','NFKC','NFKD'):raise ValueError('Explicit Unicode form required')
    rows,pairs=tables();compat=form in ('NFKC','NFKD');decomposed=[]
    def decompose(cp):
        if 0xac00<=cp<0xd7a4:
            s=cp-0xac00;decomposed.extend((0x1100+s//588,0x1161+(s%588)//28))
            if s%28:decomposed.append(0x11a7+s%28)
            return
        row=rows.get(cp)
        if row and row[2] and (compat or not row[1]&1):
            for item in row[2]:decompose(item)
        else:decomposed.append(cp)
    for char in value:decompose(ord(char))
    if len(decomposed)>1024*MAX_EXPANSION:raise ValueError('Unicode intermediate resource bound')
    ordered=[];buckets=[[] for _ in range(256)];pending=False
    def flush():
        nonlocal pending
        if pending:
            for bucket in buckets:
                ordered.extend(bucket);bucket.clear()
            pending=False
    for cp in decomposed:
        ccc=rows.get(cp,(0,))[0]
        if ccc:buckets[ccc].append(cp);pending=True
        else:flush();ordered.append(cp)
    flush()
    if form in ('NFD','NFKD'):return ''.join(map(chr,ordered))
    out=[];starter=-1;last=0
    for cp in ordered:
        ccc=rows.get(cp,(0,))[0];composed=None
        if starter>=0 and (last<ccc or last==0):
            a=out[starter]
            if 0x1100<=a<0x1113 and 0x1161<=cp<0x1176:composed=0xac00+(a-0x1100)*588+(cp-0x1161)*28
            elif 0xac00<=a<0xd7a4 and (a-0xac00)%28==0 and 0x11a8<=cp<0x11c3:composed=a+cp-0x11a7
            else:composed=pairs.get((a,cp))
        if composed is not None:out[starter]=composed
        else:
            if ccc==0:starter=len(out)
            out.append(cp);last=ccc
    return ''.join(map(chr,out))

def normalize(value,form):
    from sedrava_core import checked_text
    return checked_text(normalize_raw(value,form))

def casefold_raw(value):
    from sedrava_core import checked_text
    checked_text(value);rows,_=tables()
    return ''.join(chr(cp) for char in value for cp in (rows.get(ord(char),(0,0,(),()))[3] or (ord(char),)))

def casefold(value):
    from sedrava_core import checked_text
    return checked_text(casefold_raw(value))

def required(program):
    from sedrava_core import If,Repeat,ForEach
    expressions=[f.body for f in (program.functions or {}).values()]+list((program.derived or {}).values())+list(program.rules)
    def visit(body):
        for stmt in body:
            for key in ('expr','condition','collection'):
                if hasattr(stmt,key):expressions.append(getattr(stmt,key))
            if isinstance(stmt,If):visit(stmt.yes);visit(stmt.no)
            elif isinstance(stmt,(Repeat,ForEach)):visit(stmt.body)
    for body in program.actions.values():visit(body)
    return any(isinstance(n,ast.Call) and (getattr(n,'pure_builtin','') in (*NORMALIZERS,'text_casefold') or getattr(n,'result_operation','')=='try_normalize') for expr in expressions for n in ast.walk(expr))

JS_CODE=r'''
let _sdrUnicodeCache;
function sdrUnicodeTables(){if(_sdrUnicodeCache)return _sdrUnicodeCache;const rows=new Map(),pairs=new Map();for(const row of _sdrUnicodeData.split('|')){const [c,cc,f,d,fold]=row.split(':'),cp=parseInt(c,16),flags=Number(f),ds=d?d.split(',').map(x=>parseInt(x,16)):[],fs=fold?fold.split(',').map(x=>parseInt(x,16)):[];rows.set(cp,{cc:Number(cc),flags,ds,fs});if(flags&2)pairs.set(ds.join(','),cp);}_sdrUnicodeCache={rows,pairs};return _sdrUnicodeCache;}
function sdrNormalizeRaw(value,form){if(!validText(value)||!['NFC','NFD','NFKC','NFKD'].includes(form))throw RangeError('Invalid Unicode normalization input');const {rows,pairs}=sdrUnicodeTables(),compat=form==='NFKC'||form==='NFKD',parts=[];
 function decompose(cp){if(cp>=0xac00&&cp<0xd7a4){const s=cp-0xac00;parts.push(0x1100+Math.floor(s/588),0x1161+Math.floor((s%588)/28));if(s%28)parts.push(0x11a7+s%28);return;}const r=rows.get(cp);if(r&&r.ds.length&&(compat||!(r.flags&1))){for(const d of r.ds)decompose(d);}else parts.push(cp);}
 for(const char of value)decompose(char.codePointAt(0));if(parts.length>18432)throw RangeError('Unicode intermediate resource bound');
 const ordered=[],buckets=Array.from({length:256},()=>[]);let pending=false;const flush=()=>{if(pending){for(const b of buckets){ordered.push(...b);b.length=0;}pending=false;}};
 for(const cp of parts){const cc=rows.get(cp)?.cc||0;if(cc){buckets[cc].push(cp);pending=true;}else{flush();ordered.push(cp);}}flush();
 if(form==='NFD'||form==='NFKD')return ordered.map(cp=>String.fromCodePoint(cp)).join('');const out=[];let starter=-1,last=0;
 for(const cp of ordered){const cc=rows.get(cp)?.cc||0;let composed;if(starter>=0&&(last<cc||last===0)){const a=out[starter];if(a>=0x1100&&a<0x1113&&cp>=0x1161&&cp<0x1176)composed=0xac00+(a-0x1100)*588+(cp-0x1161)*28;else if(a>=0xac00&&a<0xd7a4&&(a-0xac00)%28===0&&cp>=0x11a8&&cp<0x11c3)composed=a+cp-0x11a7;else composed=pairs.get(a+','+cp);}if(composed!==undefined)out[starter]=composed;else{if(cc===0)starter=out.length;out.push(cp);last=cc;}}
 return out.map(cp=>String.fromCodePoint(cp)).join('');}
function sdrNormalize(value,form){const out=sdrNormalizeRaw(value,form);if(!validText(out))throw RangeError('Text limit after normalization');return out;}
function sdrCasefoldRaw(value){if(!validText(value))throw RangeError('Invalid Unicode folding input');const {rows}=sdrUnicodeTables();let out='';for(const ch of value){const cp=ch.codePointAt(0),fs=rows.get(cp)?.fs;out+=fs?.length?fs.map(x=>String.fromCodePoint(x)).join(''):ch;}return out;}
function sdrCasefold(value){const out=sdrCasefoldRaw(value);if(!validText(out))throw RangeError('Text limit after case folding');return out;}
'''
KT_CODE=r'''
internal data class SdrUcdRow(val cc:Int,val flags:Int,val ds:List<Int>,val fold:List<Int>)
internal object SdrUcd {
 val rows=mutableMapOf<Int,SdrUcdRow>();val pairs=mutableMapOf<Pair<Int,Int>,Int>()
 init {for(item in sdrUnicodeData.split('|')){val p=item.split(':');val cp=p[0].toInt(16);val ds=if(p[3].isEmpty())emptyList() else p[3].split(',').map{it.toInt(16)};val fold=if(p[4].isEmpty())emptyList() else p[4].split(',').map{it.toInt(16)};val flags=p[2].toInt();rows[cp]=SdrUcdRow(p[1].toInt(),flags,ds,fold);if(flags and 2!=0)pairs[Pair(ds[0],ds[1])]=cp}}
}
internal fun sdrNormalizeRaw(value:String,form:String):String {
 checkedText(value);require(form in listOf("NFC","NFD","NFKC","NFKD"));val compat=form=="NFKC"||form=="NFKD";val parts=mutableListOf<Int>()
 fun decompose(cp:Int){if(cp in 0xac00 until 0xd7a4){val s=cp-0xac00;parts.add(0x1100+s/588);parts.add(0x1161+(s%588)/28);if(s%28!=0)parts.add(0x11a7+s%28);return};val r=SdrUcd.rows[cp];if(r!=null&&r.ds.isNotEmpty()&&(compat||r.flags and 1==0)){for(d in r.ds)decompose(d)}else parts.add(cp)}
 for(ch in sdrScalars(value))decompose(ch.codePointAt(0));require(parts.size<=18432)
 val ordered=mutableListOf<Int>();val buckets=Array(256){mutableListOf<Int>()};var pending=false
 fun flush(){if(pending){for(bucket in buckets){ordered.addAll(bucket);bucket.clear()};pending=false}}
 for(cp in parts){val cc=SdrUcd.rows[cp]?.cc?:0;if(cc!=0){buckets[cc].add(cp);pending=true}else{flush();ordered.add(cp)}};flush()
 if(form=="NFD"||form=="NFKD")return buildString{for(cp in ordered)appendCodePoint(cp)}
 val out=mutableListOf<Int>();var starter=-1;var last=0
 for(cp in ordered){val cc=SdrUcd.rows[cp]?.cc?:0;var composed:Int?=null
 if(starter>=0&&(last<cc||last==0)){val a=out[starter];composed=if(a in 0x1100 until 0x1113&&cp in 0x1161 until 0x1176)0xac00+(a-0x1100)*588+(cp-0x1161)*28 else if(a in 0xac00 until 0xd7a4&&(a-0xac00)%28==0&&cp in 0x11a8 until 0x11c3)a+cp-0x11a7 else SdrUcd.pairs[Pair(a,cp)]}
 if(composed!=null)out[starter]=composed else {if(cc==0)starter=out.size;out.add(cp);last=cc}}
 return buildString{for(cp in out)appendCodePoint(cp)}
}
internal fun sdrNormalize(value:String,form:String):String=checkedText(sdrNormalizeRaw(value,form))
internal fun sdrCasefoldRaw(value:String):String {checkedText(value);return buildString{for(ch in sdrScalars(value)){val cp=ch.codePointAt(0);val fs=SdrUcd.rows[cp]?.fold;if(fs==null||fs.isEmpty())appendCodePoint(cp)else for(item in fs)appendCodePoint(item)}}}
internal fun sdrCasefold(value:String):String=checkedText(sdrCasefoldRaw(value))
'''

def runtime(target):
    license='/* '+LICENSE_TEXT.replace('*/','* /')+' */\n'
    if target=='js':return license+'const _sdrUnicodeData='+json.dumps(DATA)+';\n'+JS_CODE
    chunks=[DATA[i:i+8192] for i in range(0,len(DATA),8192)]
    return license+'internal val sdrUnicodeData=listOf('+','.join('"'+chunk+'"' for chunk in chunks)+').joinToString("")\n'+KT_CODE
