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
    kinds={'int':int,'text':str,'bool':bool,**records}
    if source in kinds:return kinds[source]
    match=re.fullmatch(r'list<([A-Za-z][A-Za-z0-9_]*)>\(max=([0-9]{1,3})\)',source)
    if match and match[1] in records and 1<=int(match[2])<=100:return ListType(records[match[1]],int(match[2]))
    raise ValueError('Unknown or unbounded function type')


def kotlin_type(kind):
    from sedrava_records import ListType
    if isinstance(kind,ListType):return 'SdrList<'+kotlin_type(kind.record)+'>'
    return {int:'Int',str:'String',bool:'Boolean'}.get(kind,'SdrRecord_'+getattr(kind,'name',''))
