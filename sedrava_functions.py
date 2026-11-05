"""Pure call-by-value expression functions. No host-language execution or closures."""
import ast
from dataclasses import dataclass

@dataclass(frozen=True)
class FunctionType:
    name: str
    parameters: tuple
    result: object
    body: object
    cost: int


def expression_cost(node):
    return sum(1+(item.pure_function.cost if isinstance(item,ast.Call) and hasattr(item,'pure_function') else 0)+getattr(item,'query_cost',0) for item in ast.walk(node))


def signature_type(source, records):
    """Resolve explicit portable types, including exactly bounded record lists."""
    import re
    from sedrava_records import ListType
    from sedrava_sequences import ValueListType
    from sedrava_results import ResultType
    result=re.fullmatch(r'Result<(.+),\s*Error>',source)
    if result:
        inner=signature_type(result[1].strip(),records)
        if isinstance(inner,ResultType):raise ValueError('Nested Result is unsupported')
        return ResultType(inner)
    kinds={'int':int,'text':str,'bool':bool,**records}
    if source in kinds:return kinds[source]
    match=re.fullmatch(r'list<([A-Za-z][A-Za-z0-9_]*)>\(max=([0-9]{1,3})\)',source)
    if match and 1<=int(match[2])<=100:
        if match[1] in records:return ListType(records[match[1]],int(match[2]))
        if match[1] in kinds:return ValueListType(kinds[match[1]],int(match[2]))
    raise ValueError('Unknown or unbounded function type')


def kotlin_type(kind):
    from sedrava_records import ListType
    from sedrava_sequences import ValueListType
    from sedrava_results import ResultType
    if isinstance(kind,ResultType):return 'SdrResult<'+kotlin_type(kind.value)+'>'
    if isinstance(kind,ValueListType):return 'SdrVector<'+kotlin_type(kind.element)+'>'
    if isinstance(kind,ListType):return 'SdrList<'+kotlin_type(kind.record)+'>'
    return {int:'Int',str:'String',bool:'Boolean'}.get(kind,'SdrRecord_'+getattr(kind,'name',''))


def split_parameters(source):
    parts=[];start=0;depth=0
    for i,ch in enumerate(source):
        if ch in '<(':depth+=1
        elif ch in '>)':
            depth-=1
            if depth<0:raise ValueError('Unbalanced function parameter type')
        elif ch==',' and depth==0:parts.append(source[start:i]);start=i+1
    if depth:raise ValueError('Unbalanced function parameter type')
    if source.strip():parts.append(source[start:])
    return parts
