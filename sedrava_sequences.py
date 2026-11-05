"""First-order bounded value lists, distinct from identity-bearing record lists."""
from dataclasses import dataclass

@dataclass(frozen=True)
class ValueListType:
    element: type
    capacity: int
    def __post_init__(self):
        if self.element not in (int,bool,str) or type(self.capacity) is not int or not 1<=self.capacity<=100:raise ValueError('Invalid bounded value-list type')

@dataclass(frozen=True)
class ValueList:
    kind: ValueListType
    items: tuple=()

NAMES={'append':2,'count':1,'list_at':2,'list_slice':3,'list_clear':1,'list_remove_at':2,'list_replace_at':3,'list_index':2,'list_capacity':1,'list_sort':1,'list_sum':1}

def validate_list(value,expected=None):
    from sedrava_core import checked_value
    if not isinstance(value,ValueList) or expected is not None and value.kind!=expected or type(value.items) is not tuple or len(value.items)>value.kind.capacity:raise ValueError('Invalid bounded value list')
    for item in value.items:checked_value(item,value.kind.element)
    return value

def operation(name,args):
    from sedrava_core import checked_int
    value=args[0];items=value.items
    if name=='count':return len(items)
    if name=='list_capacity':return value.kind.capacity
    if name=='list_at':
        index=args[1]
        if type(index) is not int or not 0<=index<len(items):raise ValueError('Collection positional index out of bounds')
        return items[index]
    if name=='append':
        if len(items)>=value.kind.capacity:raise ValueError('Collection capacity exceeded')
        result=(*items,args[1])
    elif name=='list_clear':result=()
    elif name=='list_slice':
        start,end=args[1:]
        if type(start) is not int or type(end) is not int or not 0<=start<=end<=len(items):raise ValueError('Collection slice bounds invalid')
        result=items[start:end]
    elif name in ('list_remove_at','list_replace_at'):
        index=args[1]
        if type(index) is not int or not 0<=index<len(items):raise ValueError('Collection positional index out of bounds')
        result=items[:index]+(() if name=='list_remove_at' else (args[2],))+items[index+1:]
    elif name=='list_index':return next((i for i,item in enumerate(items) if type(item) is type(args[1]) and item==args[1]),-1)
    elif name=='list_sort':result=tuple(sorted(items))
    elif name=='list_sum':
        total=0
        for item in items:total=checked_int(total+item)
        return total
    else:raise ValueError('Unknown value-list operation')
    return validate_list(ValueList(value.kind,tuple(result)))

JS_RUNTIME=r'''
function validVector(items,type){return Array.isArray(items)&&items.length<=type.capacity&&items.every(item=>typeof item===type.element&&(type.element==='number'?Number.isInteger(item)&&item>=-2147483648&&item<=2147483647:type.element==='string'?validText(item):true));}
function vectorOp(op,capacity,items,arg,value){
 if(op==='count')return items.length;
 if(op==='list_capacity')return capacity;
 if(op==='list_index')return items.findIndex(x=>x===arg);
 if(op==='list_sum'){let sum=0;for(const item of items)sum=checkedInt(sum+item);return sum;}
 if(op==='list_sort')return items.slice().sort((a,b)=>{if(typeof a!=='string')return a<b?-1:a>b?1:0;const x=Array.from(a,c=>c.codePointAt(0)),y=Array.from(b,c=>c.codePointAt(0));for(let i=0;i<Math.min(x.length,y.length);i++)if(x[i]!==y[i])return x[i]<y[i]?-1:1;return x.length-y.length;});
 if(op==='append'){if(items.length>=capacity)throw Error('Collection capacity exceeded');return [...items,arg];}
 if(op==='list_clear')return [];
 if(op==='list_slice'){if(!Number.isInteger(arg)||!Number.isInteger(value)||arg<0||arg>value||value>items.length)throw Error('Collection slice bounds invalid');return items.slice(arg,value);}
 if(!Number.isInteger(arg)||arg<0||arg>=items.length)throw Error('Collection positional index out of bounds');
 if(op==='list_at')return items[arg];
 if(op==='list_remove_at')return items.filter((_,i)=>i!==arg);
 if(op==='list_replace_at')return items.map((item,i)=>i===arg?value:item);
 throw Error('Unknown value-list operation');
}
'''
KT_RUNTIME=r'''
internal data class SdrVector<T:Any>(val capacity:Int,val items:List<T> = emptyList()) {
 fun check(){require(capacity in 1..100&&items.size<=capacity);val first=items.firstOrNull();for(item in items){require(item is Int||item is Boolean||item is String);require(first==null||item.javaClass==first.javaClass);if(item is String)checkedText(item)}}
}
internal fun <T:Any> sdrVector_count(v:SdrVector<T>):Int=v.items.size
internal fun <T:Any> sdrVector_list_capacity(v:SdrVector<T>):Int=v.capacity
internal fun <T:Any> sdrVector_list_at(v:SdrVector<T>,i:Int):T {require(i>=0&&i<v.items.size){"Collection positional index out of bounds"};return v.items[i]}
internal fun <T:Any> sdrVector_append(v:SdrVector<T>,item:T):SdrVector<T> = v.copy(items=v.items+item).also{it.check()}
internal fun <T:Any> sdrVector_list_clear(v:SdrVector<T>):SdrVector<T> = v.copy(items=emptyList())
internal fun <T:Any> sdrVector_list_slice(v:SdrVector<T>,start:Int,end:Int):SdrVector<T> {require(start>=0&&start<=end&&end<=v.items.size){"Collection slice bounds invalid"};return v.copy(items=v.items.subList(start,end)).also{it.check()}}
internal fun <T:Any> sdrVector_list_remove_at(v:SdrVector<T>,i:Int):SdrVector<T> {sdrVector_list_at(v,i);return v.copy(items=v.items.filterIndexed{index,_->index!=i})}
internal fun <T:Any> sdrVector_list_replace_at(v:SdrVector<T>,i:Int,item:T):SdrVector<T> {sdrVector_list_at(v,i);return v.copy(items=v.items.mapIndexed{index,old->if(index==i)item else old}).also{it.check()}}
internal fun <T:Any> sdrVector_list_index(v:SdrVector<T>,item:T):Int=v.items.indexOf(item)
internal fun <T:Any> sdrVector_list_sort(v:SdrVector<T>):SdrVector<T> = v.copy(items=v.items.sortedWith(Comparator{a,b->sdrCompareKeys(a,b)}))
internal fun sdrVector_list_sum(v:SdrVector<Int>):Int=v.items.fold(0){a,b->Math.addExact(a,b)}
'''
