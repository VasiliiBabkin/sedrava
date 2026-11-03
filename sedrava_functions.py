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
