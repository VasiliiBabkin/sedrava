"""Portable action fuel: static bounds and per-statement runtime reservations.

Units bound AST/function evaluations and collection element visits, not wall time.
Scalar text and record sizes have independent fixed language bounds. Reserving a
conservative cost before evaluation prevents target-specific partial execution.
"""
import ast
from sedrava_functions import expression_cost
MAX_ACTION_WORK=1_000_000

def expression_work(node,derived_costs=None):
    total=expression_cost(node)
    for item in ast.walk(node):
        if isinstance(item,ast.Name):total+=(derived_costs or {}).get(item.id,0)
        total+=getattr(item,'collection_cost',0)
        builtin=getattr(item,'pure_builtin','')
        if builtin.startswith('unicode_nf'):total+=65536
        elif builtin=='text_casefold':total+=4096
        if hasattr(item,'pure_function'):total+=expression_work(item.pure_function.body)-item.pure_function.cost
        if hasattr(item,'query_function'):total+=item.query_collection.capacity*(expression_work(item.query_function.body)-item.query_function.cost)
        if getattr(item,'collection_query',None)=='sort':total+=item.query_collection.capacity**2
    return total

def derived_work(derived):
    costs={}
    for name,node in (derived or {}).items():costs[name]=expression_work(node,costs)
    return costs

def statement_work(stmt,derived):
    from sedrava_core import Assign,Let,Require,If,Repeat
    costs=derived_work(derived)
    total=1+sum(costs.values())
    node=stmt.expr if isinstance(stmt,(Assign,Let)) else stmt.condition if isinstance(stmt,(Require,If)) else getattr(stmt,'collection',None)
    if node is not None:total+=expression_work(node,costs)
    # Assignments revalidate derived values before any next statement.
    if isinstance(stmt,Assign):total+=sum(costs.values())
    return total

def block_work(body,derived):
    from sedrava_core import If,Repeat
    total=0
    for stmt in body:
        total+=statement_work(stmt,derived)
        if isinstance(stmt,If):total+=max(block_work(stmt.yes,derived),block_work(stmt.no,derived))
        elif isinstance(stmt,Repeat):total+=stmt.count*block_work(stmt.body,derived)
        elif hasattr(stmt,'collection'):total+=stmt.capacity*block_work(stmt.body,derived)
    return total

def base_work(derived,rules):
    costs=derived_work(derived)
    return 2*(sum(costs.values())+sum(expression_work(node,costs) for node in rules))

def action_work(body,derived,rules=()):
    return base_work(derived,rules)+block_work(body,derived)
