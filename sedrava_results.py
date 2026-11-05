"""Ephemeral expected errors; engine faults and resource limits are never caught."""
from dataclasses import dataclass
@dataclass(frozen=True)
class ResultType:
    value: object
@dataclass(frozen=True)
class ResultValue:
    kind: ResultType
    value: object = None
    code: str = ''
NAMES={'try_add','try_chr','try_at','result_ok','result_code','result_or'}
CODES={'INT_OVERFLOW','INVALID_SCALAR','INDEX_BOUNDS'}
def validate(value,expected=None):
    from sedrava_records import validate as check
    if not isinstance(value,ResultValue) or expected is not None and value.kind!=expected:raise ValueError('Invalid Result type')
    if value.code:
        if value.code not in CODES or value.value is not None:raise ValueError('Invalid expected error')
    else:check(value.value,value.kind.value)
    return value

def type_result(node,types,type_of):
    from sedrava_records import ListType
    from sedrava_sequences import ValueListType
    name=node.func.id
    if node.keywords:raise ValueError('Result operations use positional arguments')
    args=[type_of(arg,types) for arg in node.args]
    if name=='try_add' and args==[int,int]:kind=ResultType(int)
    elif name=='try_chr' and args==[int]:kind=ResultType(str)
    elif name=='try_at' and len(args)==2 and args[1] is int and (args[0] is str or isinstance(args[0],(ListType,ValueListType))):
        base=args[0];kind=ResultType(str if base is str else base.element if isinstance(base,ValueListType) else base.record);node.result_base=base
    elif name in ('result_ok','result_code') and len(args)==1 and isinstance(args[0],ResultType):kind=bool if name=='result_ok' else str
    elif name=='result_or' and len(args)==2 and isinstance(args[0],ResultType) and args[0].value==args[1]:kind=args[1]
    else:raise ValueError('Result operation argument type/count mismatch')
    node.result_operation=name;node.result_type=kind
    return kind

def evaluate(node,args):
    name=node.result_operation;kind=node.result_type
    if name=='result_ok':return not args[0].code
    if name=='result_code':return args[0].code
    if name=='result_or':return args[1] if args[0].code else args[0].value
    if name=='try_add':
        value=args[0]+args[1]
        return ResultValue(kind,value) if -2147483648<=value<=2147483647 else ResultValue(kind,code='INT_OVERFLOW')
    if name=='try_chr':
        cp=args[0]
        return ResultValue(kind,chr(cp)) if 0<=cp<=0x10ffff and not 0xd800<=cp<=0xdfff else ResultValue(kind,code='INVALID_SCALAR')
    value,index=args;items=value if type(value) is str else value.items
    if not 0<=index<len(items):return ResultValue(kind,code='INDEX_BOUNDS')
    from sedrava_records import ListValue
    return ResultValue(kind,items[index][1] if isinstance(value,ListValue) else items[index])

def js(node,args):
    name=node.result_operation
    if name=='try_at':
        from sedrava_records import ListType
        flag='record' if isinstance(node.result_base,ListType) else 'value'
        return 'sdrTryAt('+','.join(args)+',"'+flag+'")'
    return {'try_add':'sdrTryAdd','try_chr':'sdrTryChr','result_ok':'sdrResultOk','result_code':'sdrResultCode','result_or':'sdrResultOr'}[name]+'('+','.join(args)+')'
def kt(node,args):
    name=node.result_operation
    return {'try_add':'sdrTryAdd','try_chr':'sdrTryChr','try_at':'sdrTryAt','result_ok':'sdrResultOk','result_code':'sdrResultCode','result_or':'sdrResultOr'}[name]+'('+','.join(args)+')'
JS_RUNTIME=r'''
function sdrTryAdd(a,b){const n=a+b;return n>=-2147483648&&n<=2147483647?{value:n,code:''}:{code:'INT_OVERFLOW'};}
function sdrTryChr(cp){return cp>=0&&cp<=0x10ffff&&!(cp>=0xd800&&cp<=0xdfff)?{value:String.fromCodePoint(cp),code:''}:{code:'INVALID_SCALAR'};}
function sdrTryAt(value,index,kind){const items=typeof value==='string'?Array.from(value):kind==='record'?value.items:value;if(index<0||index>=items.length)return {code:'INDEX_BOUNDS'};let item=items[index];if(kind==='record'){item={...item};delete item.id;}return {value:item,code:''};}
function sdrResultOk(r){return r.code==='';}
function sdrResultCode(r){return r.code;}
function sdrResultOr(r,fallback){return r.code?fallback:r.value;}
'''
KT_RUNTIME=r'''
internal data class SdrResult<T:Any>(val value:T?=null,val code:String="")
internal fun sdrTryAdd(a:Int,b:Int):SdrResult<Int> {val n=a.toLong()+b.toLong();return if(n in -2147483648L..2147483647L)SdrResult(n.toInt()) else SdrResult(code="INT_OVERFLOW")}
internal fun sdrTryChr(cp:Int):SdrResult<String> = if(cp>=0&&cp<=0x10ffff&&cp !in 0xd800..0xdfff)SdrResult(sdrUnicodeChr(cp)) else SdrResult(code="INVALID_SCALAR")
internal fun sdrTryAt(v:String,i:Int):SdrResult<String> = if(i>=0&&i<sdrTextLength(v))SdrResult(sdrTextAt(v,i)) else SdrResult(code="INDEX_BOUNDS")
internal fun <T:Any> sdrTryAt(v:SdrVector<T>,i:Int):SdrResult<T> = if(i>=0&&i<v.items.size)SdrResult(v.items[i]) else SdrResult(code="INDEX_BOUNDS")
internal fun <T:SdrRecord> sdrTryAt(v:SdrList<T>,i:Int):SdrResult<T> = if(i>=0&&i<v.items.size)SdrResult(v.items[i].record) else SdrResult(code="INDEX_BOUNDS")
internal fun <T:Any> sdrResultOk(r:SdrResult<T>):Boolean = r.code.isEmpty()
internal fun <T:Any> sdrResultCode(r:SdrResult<T>):String = r.code
internal fun <T:Any> sdrResultOr(r:SdrResult<T>,fallback:T):T = if(r.code.isEmpty())requireNotNull(r.value) else fallback
'''
