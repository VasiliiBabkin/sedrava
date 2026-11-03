"""Bounded typed collection algebra shared by the interpreter and code generators."""
import ast
from sedrava_records import ListType,ListValue,RecordType,validate
from sedrava_functions import FunctionType

NAMES=frozenset(('filter','map','find','any','all','sort','sum'))


def type_query(node, types, type_of):
    op=node.func.id
    if node.keywords or len(node.args)<2:raise ValueError('Collection query requires a collection and selector')
    kind=type_of(node.args[0],types)
    if not isinstance(kind,ListType):raise ValueError('Collection query requires a bounded collection')
    selector=node.args[1];function=types.get(selector.id) if isinstance(selector,ast.Name) else None
    fields={'id':int,**dict(kind.record.fields)}
    if isinstance(function,FunctionType):
        if not function.parameters or function.parameters[0][1]!=kind.record:raise ValueError('Query function first parameter must match record type')
        if len(node.args)-2!=len(function.parameters)-1:raise ValueError('Query function argument count mismatch')
        for arg,(_,expected) in zip(node.args[2:],function.parameters[1:]):
            if type_of(arg,types)!=expected:raise ValueError('Query function argument type mismatch')
        value_type=function.result;node.query_function=function
        node.query_extra_types=tuple(t for _,t in function.parameters[1:])
        node.query_cost=kind.capacity*function.cost
    elif isinstance(selector,ast.Constant) and type(selector.value) is str and selector.value in fields:
        field=selector.value;value_type=fields[field]
        count=3 if op in ('filter','find','any','all') else 2
        if len(node.args)!=count or (count==3 and type_of(node.args[2],types) is not value_type):raise ValueError('Query field/value type mismatch')
        if op=='map':raise ValueError('Map requires a record-transforming function')
        node.query_field=field;node.query_extra_types=(value_type,) if count==3 else ()
        if count==3:value_type=bool
        node.query_cost=kind.capacity
    else:raise ValueError('Query selector must be a known field literal or pure function')
    if op in ('filter','find','any','all') and value_type is not bool:raise ValueError('Query predicate must return bool')
    if op=='sum' and value_type is not int:raise ValueError('Sum selector must return int')
    if op=='sort' and value_type not in (int,str,bool):raise ValueError('Sort selector must return a scalar')
    if op=='map' and not isinstance(value_type,RecordType):raise ValueError('Map must return a declared record')
    node.collection_query=op;node.query_collection=kind
    node.query_result=ListType(value_type,kind.capacity) if op=='map' else kind
    return int if op in ('find','sum') else bool if op in ('any','all') else node.query_result


def evaluate_query(node,state,evaluate,checked_int):
    collection=evaluate(node.args[0],state)
    extras=[evaluate(arg,state) for arg in node.args[2:]]
    def select(item):
        identity,record=item
        if hasattr(node,'query_function'):
            function=node.query_function
            return evaluate(function.body,dict(zip((key for key,_ in function.parameters),(record,*extras))))
        value=identity if node.query_field=='id' else record.values[list(dict(record.kind.fields)).index(node.query_field)]
        return value==extras[0] if extras else value
    op=node.collection_query
    if op=='find':return next((identity for identity,record in collection.items if select((identity,record))),0)
    if op=='any':return any(select(item) for item in collection.items)
    if op=='all':return all(select(item) for item in collection.items)
    if op=='sum':
        result=0
        for item in collection.items:result=checked_int(result+select(item))
        return result
    items=collection.items
    if op=='filter':items=tuple(item for item in items if select(item))
    elif op=='sort':items=tuple(sorted(items,key=select))
    elif op=='map':items=tuple((identity,select((identity,record))) for identity,record in items)
    return validate(ListValue(node.query_result,items,collection.next_id))


def selector_names(node, record, identity, extras):
    if hasattr(node,'query_function'):
        return dict(zip((key for key,_ in node.query_function.parameters),(record,*extras)))
    return None


def js_query(node, emit, names):
    op=node.collection_query;extras=['_query_extra'+str(i) for i in range(len(node.query_extra_types))]
    if hasattr(node,'query_function'):
        body=emit(node.query_function.body,selector_names(node,'_query_record','_query_identity',extras))
    else:
        from web_codegen import json_script
        body='_query_identity' if node.query_field=='id' else '_query_record['+json_script(node.query_field)+']'
        if extras:body='('+body+' === '+extras[0]+')'
    args=[emit(node.args[0],names),*(emit(arg,names) for arg in node.args[2:])]
    return '(('+','.join(['_query_list',*extras])+')=>sdrQuery('+repr(op)+',_query_list,(_query_record,_query_identity)=>'+body+'))('+','.join(args)+')'


def kt_query(node,emit,names):
    extras=['_query_extra'+str(i) for i in range(len(node.query_extra_types))]
    def kind(t):return {int:'Int',str:'String',bool:'Boolean'}.get(t,'SdrRecord_'+getattr(t,'name',''))
    if hasattr(node,'query_function'):
        body=emit(node.query_function.body,selector_names(node,'_query_record','_query_identity',extras))
    else:
        body='_query_identity' if node.query_field=='id' else '_query_record.sdr_'+node.query_field
        if extras:body='('+body+' == '+extras[0]+')'
    declaration=['_query_list:SdrList<SdrRecord_'+node.query_collection.record.name+'>',*(key+':'+kind(t) for key,t in zip(extras,node.query_extra_types))]
    args=[emit(node.args[0],names),*(emit(arg,names) for arg in node.args[2:])]
    return '({'+','.join(declaration)+' -> sdrQuery_'+node.collection_query+'(_query_list){_query_record,_query_identity -> '+body+'}})('+','.join(args)+')'


JS_RUNTIME=r'''
function sdrQuery(op,list,select){
 const value=row=>{const {id,...record}=row;return select(record,id);};
 if(op==='find')return list.items.find(row=>value(row))?.id||0;
 if(op==='any')return list.items.some(value);
 if(op==='all')return list.items.every(value);
 if(op==='sum'){let total=0;for(const row of list.items)total=checkedInt(total+value(row));return total;}
 let items=list.items;
 if(op==='filter')items=items.filter(value);
 if(op==='map')items=items.map(row=>({id:row.id,...value(row)}));
 if(op==='sort'){
  const compare=(a,b)=>{if(typeof a!=='string')return a<b?-1:a>b?1:0;const x=Array.from(a,c=>c.codePointAt(0)),y=Array.from(b,c=>c.codePointAt(0));for(let i=0;i<Math.min(x.length,y.length);i++)if(x[i]!==y[i])return x[i]<y[i]?-1:1;return x.length-y.length;};
  items=items.map((row,index)=>({row,index,key:value(row)})).sort((a,b)=>compare(a.key,b.key)||a.index-b.index).map(x=>x.row);
 }return {items,next_id:list.next_id};
}
'''

KT_RUNTIME=r'''
internal fun <T:SdrRecord> sdrQuery_filter(list:SdrList<T>,predicate:(T,Int)->Boolean)=list.copy(items=list.items.filter{predicate(it.record,it.id)})
internal fun <T:SdrRecord,R:SdrRecord> sdrQuery_map(list:SdrList<T>,transform:(T,Int)->R)=SdrList(list.capacity,list.items.map{SdrItem(it.id,transform(it.record,it.id))},list.next_id).also{it.check()}
internal fun <T:SdrRecord> sdrQuery_find(list:SdrList<T>,predicate:(T,Int)->Boolean):Int=list.items.firstOrNull{predicate(it.record,it.id)}?.id?:0
internal fun <T:SdrRecord> sdrQuery_any(list:SdrList<T>,predicate:(T,Int)->Boolean)=list.items.any{predicate(it.record,it.id)}
internal fun <T:SdrRecord> sdrQuery_all(list:SdrList<T>,predicate:(T,Int)->Boolean)=list.items.all{predicate(it.record,it.id)}
internal fun <T:SdrRecord> sdrQuery_sum(list:SdrList<T>,value:(T,Int)->Int):Int=list.items.fold(0){sum,item->Math.addExact(sum,value(item.record,item.id))}
internal fun sdrCompareKeys(a:Any,b:Any):Int = when(a){
 is Int->a.compareTo(b as Int)
 is Boolean->a.compareTo(b as Boolean)
 is String->{val x=a.codePoints().toArray();val y=(b as String).codePoints().toArray();var result=0;var i=0;while(i<minOf(x.size,y.size)&&result==0){result=x[i].compareTo(y[i]);i++};if(result==0)x.size.compareTo(y.size) else result}
 else->throw IllegalArgumentException("Invalid sort key")
}
internal fun <T:SdrRecord> sdrQuery_sort(list:SdrList<T>,key:(T,Int)->Any):SdrList<T>{
 val sorted=list.items.mapIndexed{i,row->Triple(row,key(row.record,row.id),i)}.sortedWith(Comparator{a,b->val order=sdrCompareKeys(a.second,b.second);if(order==0)a.third.compareTo(b.third) else order})
 return list.copy(items=sorted.map{it.first})
}
'''
