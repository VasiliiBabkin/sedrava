"""Sedrava shared text/int32/bool core: restricted typed AST, interpreter and atomic transitions."""
import ast
import keyword
import re
from sedrava_records import RecordType, ListType, RecordValue, ListValue, value_type, validate, operation
from dataclasses import dataclass
from sedrava_functions import FunctionType, expression_cost, signature_type
from sedrava_stdlib import SIGNATURES
from sedrava_queries import NAMES as QUERY_NAMES, type_query
from sedrava_navigation import Span, Widget, Screen, Navigation, MAX_SCREENS, MAX_NAV_COMMANDS

from sedrava_syntax import MAX_SOURCE_CHARS, source_lines
MAX_TEXT_SCALARS = 1024
MAX_AST_NODES = 256
MAX_ACTION_STEPS = 10_000
MAX_BLOCK_DEPTH = 32
MAX_DERIVED_NODES = 4096

INT_MIN = -(2 ** 31)
INT_MAX = 2 ** 31 - 1

def checked_int(value):
    if type(value) is int and not INT_MIN <= value <= INT_MAX:
        raise ValueError("Integer overflow: outside signed 32-bit range")
    return value


def checked_text(value):
    if type(value) is not str:
        raise ValueError("Text value required")
    if len(value) > MAX_TEXT_SCALARS:
        raise ValueError("Text exceeds 1024 Unicode scalar values")
    if any(0xD800 <= ord(char) <= 0xDFFF for char in value):
        raise ValueError("Text contains an unpaired surrogate")
    return value


def checked_value(value, expected=None):
    if type(value) not in (int, bool, str) or (expected is not None and type(value) is not expected):
        raise ValueError("Value type mismatch")
    return checked_text(value) if type(value) is str else checked_int(value)


class LiteralError(ValueError):
    def __init__(self, message, offset):
        super().__init__(message)
        self.offset = offset


def read_literal(source, start=0):
    """Decode only the contract's double-quoted grammar, never Python escapes."""
    if start >= len(source) or source[start] != '"':
        raise LiteralError("Expected double-quoted text", start)
    chars = []
    i = start + 1
    escapes = {"\\": "\\", '"': '"', "n": "\n", "r": "\r", "t": "\t"}
    while i < len(source):
        char = source[i]
        if char == '"':
            try:
                return checked_text("".join(chars)), i + 1
            except ValueError as exc:
                raise LiteralError(str(exc), start) from exc
        if char in "\n\r":
            raise LiteralError("Unterminated text literal", i)
        if char == "\\":
            i += 1
            if i >= len(source) or source[i] not in escapes:
                raise LiteralError("Invalid text escape", i - 1)
            char = escapes[source[i]]
        chars.append(char)
        i += 1
    raise LiteralError("Unterminated text literal", start)


def literal_expression(source):
    """Keep booleans outside literals; placeholders prevent implicit concatenation."""
    prefix = "__sedrava_literal_"
    while prefix in source:
        prefix += "_"
    values, chunks = {}, []
    i = 0
    while i < len(source):
        if source[i] == '"':
            value, end = read_literal(source, i)
            name = prefix + str(len(values))
            values[name] = value
            chunks.append("(" + name + ")")
            i = end
        elif source[i] == "'":
            raise LiteralError("Text requires double quotes", i)
        else:
            end = source.find('"', i)
            end = len(source) if end == -1 else end
            chunk = source[i:end]
            if "'" in chunk:
                raise LiteralError("Text requires double quotes", i + chunk.index("'"))
            chunks.append(re.sub(r"\b(true|false)\b", lambda m: m[1].title(), chunk))
            i = end
    return "".join(chunks), values


@dataclass(frozen=True)
class Assign:
    name: str
    expr: ast.expr

@dataclass(frozen=True)
class Let:
    name: str
    expr: ast.expr

@dataclass(frozen=True)
class Require:
    condition: ast.expr

@dataclass(frozen=True)
class If:
    condition: ast.expr
    yes: tuple
    no: tuple

@dataclass(frozen=True)
class Repeat:
    """Statically bounded, half-open repetition with a scoped int counter."""
    name: str
    count: int
    body: tuple

@dataclass(frozen=True)
class Program:
    name: str
    states: dict
    actions: dict
    rules: tuple
    tests: tuple
    widgets: tuple
    derived: dict = None
    persistent: tuple = ()
    records: dict = None
    screens: dict = None
    navigation: dict = None
    initial_screen: str = "main"
    has_navigation: bool = False
    functions: dict = None

def parse_expr(source, types):
    source, literals = literal_expression(source)
    try:
        node = ast.parse(source, mode="eval").body
    except (SyntaxError, RecursionError) as exc:
        raise ValueError("Invalid or excessively nested expression") from exc
    class ReplaceLiterals(ast.NodeTransformer):
        def visit_Name(self, item):
            return ast.copy_location(ast.Constant(literals[item.id]), item) if item.id in literals else item
    node = ReplaceLiterals().visit(node)
    if sum(1 for _ in ast.walk(node)) > MAX_AST_NODES:
        raise ValueError("Expression exceeds complexity limit")
    # The signed minimum must fold in every AST position, including list-valued
    # fields (call arguments and comparison operands), before range validation.
    class SignedMinimum(ast.NodeTransformer):
        def visit_UnaryOp(self, item):
            self.generic_visit(item)
            if (isinstance(item.op, ast.USub) and isinstance(item.operand, ast.Constant)
                    and type(item.operand.value) is int and item.operand.value == -INT_MIN):
                return ast.copy_location(ast.Constant(INT_MIN), item)
            return item
    node = SignedMinimum().visit(node)
    for item in ast.walk(node):
        if isinstance(item, ast.Constant):
            checked_value(item.value)
    try:
        type_of(node, types)
        if expression_cost(node)>MAX_DERIVED_NODES:raise ValueError("Expression/function exceeds complexity limit")
    except ValueError as exc:
        unknown = next((item.id for item in ast.walk(node)
                        if isinstance(item, ast.Name) and item.id not in types and item.id not in SIGNATURES and item.id not in QUERY_NAMES and item.id not in ('append','update','remove','get','has','count','next_id','list_at','list_slice','list_clear')), None)
        if unknown is not None:
            raise ValueError(f"Unknown identifier: {unknown}") from exc
        raise
    return node

def type_of(node, types):
    if isinstance(node, ast.Subscript):
        kind=type_of(node.value, types)
        if kind is not str and not isinstance(kind, ListType):
            raise ValueError("Indexed value must be text or a bounded record list")
        node.subscript_kind=kind
        if isinstance(node.slice, ast.Slice):
            if (node.slice.lower is None or node.slice.upper is None or node.slice.step is not None
                    or type_of(node.slice.lower,types) is not int
                    or type_of(node.slice.upper,types) is not int):
                raise ValueError("Slice requires explicit int start:end and no step")
            return kind
        if type_of(node.slice,types) is not int:
            raise ValueError("Index must be int")
        return str if kind is str else kind.record
    if isinstance(node, ast.Attribute):
        kind = type_of(node.value, types)
        if isinstance(kind, RecordType) and node.attr in dict(kind.fields): return dict(kind.fields)[node.attr]
        raise ValueError("Unknown record field")
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        name = node.func.id
        if isinstance(types.get(name), FunctionType):
            function=types[name]
            if node.keywords or len(node.args)!=len(function.parameters) or any(type_of(arg,types)!=kind for arg,(_,kind) in zip(node.args,function.parameters)):
                raise ValueError('Function argument type/count mismatch')
            node.pure_function=function
            return function.result
        if name in types and isinstance(types[name], RecordType):
            kind = types[name]
            if node.args or len(node.keywords) != len(kind.fields) or {k.arg for k in node.keywords} != set(dict(kind.fields)):
                raise ValueError("Record requires exact named fields")
            if any(type_of(k.value, types) != dict(kind.fields)[k.arg] for k in node.keywords): raise ValueError("Record field type mismatch")
            node.record_type = kind
            return kind
        if name in QUERY_NAMES:return type_query(node,types,type_of)
        if name in SIGNATURES:
            parameters,result=SIGNATURES[name]
            if node.keywords or len(node.args)!=len(parameters) or any(type_of(arg,types) is not kind for arg,kind in zip(node.args,parameters)):raise ValueError('Standard operation argument type/count mismatch')
            node.pure_builtin=name
            return result
        if name in ('append', 'update', 'remove', 'get', 'has', 'count', 'next_id',
                    'list_at', 'list_slice', 'list_clear') and not node.keywords:
            count = {'append': 2, 'update': 3, 'remove': 2, 'get': 2,
                     'has': 2, 'count': 1, 'next_id': 1, 'list_at': 2,
                     'list_slice': 3, 'list_clear': 1}[name]
            if len(node.args) != count: raise ValueError("Invalid operation arguments")
            kind = type_of(node.args[0], types)
            if not isinstance(kind, ListType): raise ValueError("Collection required")
            node.collection_type = kind
            if name in ('get', 'has', 'remove', 'update', 'list_at', 'list_slice'):
                if type_of(node.args[1], types) is not int: raise ValueError("Identity/index must be int")
            if name == 'list_slice' and type_of(node.args[2], types) is not int:
                raise ValueError("Collection slice end must be int")
            if name in ('append', 'update') and type_of(node.args[-1], types) != kind.record: raise ValueError("Wrong record type")
            return kind.record if name in ('get', 'list_at') else bool if name == 'has' else int if name in ('count', 'next_id') else kind
        raise ValueError("Unknown operation")
    if isinstance(node,ast.IfExp):
        if type_of(node.test,types) is not bool or type_of(node.body,types)!=type_of(node.orelse,types):raise ValueError('Conditional requires bool and matching branch types')
        return type_of(node.body,types)
    if isinstance(node, ast.Constant) and type(node.value) in (int, bool, str):
        return type(node.value)
    if isinstance(node, ast.Name) and node.id in types:
        if isinstance(types[node.id],FunctionType):raise ValueError("Function requires a call")
        if isinstance(types[node.id],RecordType) and node.id==types[node.id].name:raise ValueError("Record constructor requires a call")
        return types[node.id]
    if isinstance(node, ast.UnaryOp):
        t = type_of(node.operand, types)
        if isinstance(node.op, ast.USub) and t is int: return int
        if isinstance(node.op, ast.Not) and t is bool: return bool
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult)):
        if type_of(node.left, types) is type_of(node.right, types) is int: return int
    if isinstance(node, ast.BoolOp) and isinstance(node.op, (ast.And, ast.Or)):
        if all(type_of(x, types) is bool for x in node.values): return bool
    if isinstance(node, ast.Compare) and len(node.ops) == len(node.comparators) == 1:
        a, b = type_of(node.left, types), type_of(node.comparators[0], types)
        if a in (int, bool, str) and a is b and (isinstance(node.ops[0], (ast.Eq, ast.NotEq)) or
                       (a is int and isinstance(node.ops[0], (ast.Lt, ast.LtE, ast.Gt, ast.GtE)))):
            return bool
    raise ValueError("Unsupported or ill-typed expression")

def evaluate(node, state):
    try:
        return _evaluate(node, state)
    except ValueError as exc:
        if hasattr(node, 'source_line') and not str(exc).startswith('Line '):
            raise ValueError(f"Line {node.source_line}: column {node.source_column}: {exc}") from exc
        raise


def _evaluate(node, state):
    if isinstance(node, ast.Subscript):
        base=evaluate(node.value,state)
        if isinstance(node.slice,ast.Slice):
            start=evaluate(node.slice.lower,state)
            end=evaluate(node.slice.upper,state)
            if type(base) is str:
                from sedrava_stdlib import apply
                return apply('text_slice',[base,start,end])
            return operation('list_slice',[base,start,end])
        index=evaluate(node.slice,state)
        if type(base) is str:
            from sedrava_stdlib import apply
            return apply('text_at',[base,index])
        return operation('list_at',[base,index])
    if isinstance(node, ast.Attribute):
        record = evaluate(node.value, state)
        return record.values[[k for k, _ in record.kind.fields].index(node.attr)]
    if isinstance(node, ast.Call):
        if hasattr(node,"collection_query"):
            from sedrava_queries import evaluate_query
            return evaluate_query(node,state,evaluate,checked_int)
        if hasattr(node,"pure_builtin"):
            from sedrava_stdlib import apply
            return checked_value(apply(node.pure_builtin,[evaluate(arg,state) for arg in node.args]))
        if hasattr(node,'pure_function'):
            function=node.pure_function
            values=[evaluate(arg,state) for arg in node.args]
            return evaluate(function.body,dict(zip((key for key,_ in function.parameters),values)))
        if hasattr(node, 'record_type'):
            fields = {k.arg: evaluate(k.value, state) for k in node.keywords}
            return validate(RecordValue(node.record_type, tuple(fields[k] for k, _ in node.record_type.fields)))
        return operation(node.func.id, [evaluate(arg, state) for arg in node.args])
    if isinstance(node,ast.IfExp):return evaluate(node.body if evaluate(node.test,state) else node.orelse,state)
    if isinstance(node, ast.Constant): return checked_value(node.value)
    if isinstance(node, ast.Name): return validate(state[node.id])
    if isinstance(node, ast.UnaryOp):
        x = evaluate(node.operand, state)
        return checked_int(-x) if isinstance(node.op, ast.USub) else not x
    if isinstance(node, ast.BinOp):
        a, b = evaluate(node.left, state), evaluate(node.right, state)
        if isinstance(node.op, ast.Add): return checked_int(a + b)
        if isinstance(node.op, ast.Sub): return checked_int(a - b)
        return checked_int(a * b)
    if isinstance(node, ast.BoolOp):
        if isinstance(node.op, ast.And):
            return all(evaluate(x, state) for x in node.values)
        return any(evaluate(x, state) for x in node.values)
    if isinstance(node, ast.Compare):
        a, b = evaluate(node.left, state), evaluate(node.comparators[0], state)
        op = node.ops[0]
        if isinstance(op, ast.Eq): return a == b
        if isinstance(op, ast.NotEq): return a != b
        if isinstance(op, ast.Lt): return a < b
        if isinstance(op, ast.LtE): return a <= b
        if isinstance(op, ast.Gt): return a > b
        return a >= b
    raise ValueError("Unsupported expression")

def parse(source):
    lines = source_lines(source, limit=MAX_SOURCE_CHARS)
    if lines and lines[0][1].split()[0] == 'site':
        raise ValueError(f"Line {lines[0][2]}: column 1: Site mode is Web-only; use sedrava build site")
    if lines and lines[0][1].split()[0] == 'webapp':
        raise ValueError(f"Line {lines[0][2]}: column 1: WebApp mode requires sedrava build webapp")
    states, actions, rules, tests, widgets, derived = {}, {}, [], [], [], {}
    persistent = []
    records = {}
    functions = {}
    types = {}
    name = None
    screens, navigation = {}, {}
    initial_screen = None
    navigation_seen = False
    widget_spans = []
    i = 0
    def expression(source, known_types, line_number, column=1):
        try:
            node = parse_expr(source, known_types)
            node.source_line, node.source_column = line_number, column
            return node
        except ValueError as exc:
            message = str(exc)
            column += getattr(exc, "offset", 0)
            if message.startswith("Unknown identifier: "):
                identifier = message.partition(": ")[2]
                match = re.search(r"\b" + re.escape(identifier) + r"\b", source)
                if match:
                    column += match.start()
            raise ValueError(f"Line {line_number}: column {column}: {message}") from exc
    def label(source, line_number, column=1):
        try:
            value, end = read_literal(source)
            if source[end:].strip():
                raise LiteralError("Unexpected text after literal", end)
            return value
        except LiteralError as exc:
            raise ValueError(f"Line {line_number}: column {column + exc.offset}: {exc}") from exc
    def statement_count(body):
        total=0
        for stmt in body:
            if isinstance(stmt, If):
                weight=1+statement_count(stmt.yes)+statement_count(stmt.no)
            elif isinstance(stmt, Repeat):
                weight=1+stmt.count*statement_count(stmt.body)
            else:
                weight=1
            total+=weight
            if total>MAX_ACTION_STEPS:
                return total
        return total
    def block(pos, indent, nesting=0, known=None):
        known=dict(types if known is None else known)
        if nesting > MAX_BLOCK_DEPTH:
            raise ValueError(f"Line {lines[pos][2]}: block nesting limit")
        result = []
        while pos < len(lines):
            depth, line, number = lines[pos]
            if depth < indent or line == "else:": break
            if depth != indent: raise ValueError(f"Line {number}: indentation")
            if line.startswith("repeat "):
                # No unbounded loops: only a literal 0..count half-open range.
                match = re.fullmatch(r"repeat ([A-Za-z][A-Za-z0-9_]*) in range\(0, ([0-9]{1,3})\):", line)
                if (not match or match[1] in known or keyword.iskeyword(match[1])
                        or match[1] in ('true','false') or not 1 <= int(match[2]) <= 100):
                    raise ValueError(f"Line {number}: invalid bounded repeat (expected repeat name in range(0, 1..100):)")
                if pos+1 >= len(lines) or lines[pos+1][0]<=indent:
                    raise ValueError(f"Line {number}: empty repeat")
                body, pos = block(pos+1,lines[pos+1][0],nesting+1,{**known,match[1]:int})
                result.append(Repeat(match[1],int(match[2]),tuple(body)))
                continue
            if line.startswith("if ") and line.endswith(":"):
                condition = expression(line[3:-1], known, number, depth + 4)
                if type_of(condition, known) is not bool: raise ValueError(f"Line {number}: condition must be bool")
                if pos + 1 >= len(lines) or lines[pos+1][0] <= indent: raise ValueError(f"Line {number}: empty if")
                yes, pos = block(pos + 1, lines[pos+1][0], nesting + 1, known)
                no = ()
                if pos < len(lines) and lines[pos][:2] == (indent, "else:"):
                    pos += 1
                    if pos >= len(lines) or lines[pos][0] <= indent: raise ValueError(f"Line {number}: empty else")
                    no, pos = block(pos, lines[pos][0], nesting + 1, known)
                result.append(If(condition, tuple(yes), tuple(no)))
                continue
            if line.startswith('require '):
                node = expression(line[8:], known, number, depth + 9)
                if type_of(node, known) is not bool: raise ValueError(f"Line {number}: column {depth+9}: require must be bool")
                result.append(Require(node)); pos += 1; continue
            if local := re.fullmatch(r'let ([A-Za-z][A-Za-z0-9_]*)\s*=\s*(.+)',line):
                if local[1] in known or local[1] in ('true','false') or keyword.iskeyword(local[1]):raise ValueError(f'Line {number}: duplicate/reserved local')
                expr=expression(local[2],known,number,depth+local.start(2)+1)
                known[local[1]]=type_of(expr,known);result.append(Let(local[1],expr));pos+=1;continue
            m = re.fullmatch(r"([A-Za-z_][A-Za-z_0-9]*)\s*=\s*(.+)", line)
            if not m or m[1] not in states: raise ValueError(f"Line {number}: invalid assignment")
            node = expression(m[2], known, number, depth + m.start(2) + 1)
            if type_of(node, known) != types[m[1]]: raise ValueError(f"Line {number}: type mismatch")
            result.append(Assign(m[1], node))
            pos += 1
        return tuple(result), pos
    while i < len(lines):
        depth, line, number = lines[i]
        if depth: raise ValueError(f"Line {number}: unexpected indentation")
        if m := re.fullmatch(r'app (.+)', line):
            if name is not None: raise ValueError(f"Line {number}: duplicate app")
            name = label(m[1], number, 5)
        elif m := re.fullmatch(r"fn ([A-Za-z][A-Za-z0-9_]*)\((.*?)\) -> (.+?) = (.+)",line):
            if states or actions or m[1] in types or keyword.iskeyword(m[1]) or len(functions)>=32 or m[1] in SIGNATURES or m[1] in QUERY_NAMES or m[1] in ('true','false','append','update','remove','get','has','count','next_id','list_at','list_slice','list_clear'):raise ValueError(f'Line {number}: invalid pure function declaration')
            params=[]
            for param in m[2].split(',') if m[2].strip() else ():
                spec=re.fullmatch(r'\s*([A-Za-z][A-Za-z0-9_]*)\s*:\s*(.+?)\s*',param)
                if not spec or spec[1] in types or spec[1] in ('true','false') or spec[1] in dict(params) or keyword.iskeyword(spec[1]):raise ValueError(f'Line {number}: invalid function parameter')
                try:params.append((spec[1],signature_type(spec[2],records)))
                except ValueError as exc:raise ValueError(f'Line {number}: invalid function parameter type') from exc
            if len(params)>8:raise ValueError(f'Line {number}: invalid function signature')
            try:result_type=signature_type(m[3],records)
            except ValueError as exc:raise ValueError(f'Line {number}: invalid function return type') from exc
            body=expression(m[4],{**records,**functions,**dict(params)},number,m.start(4)+1)
            if type_of(body,{**records,**functions,**dict(params)})!=result_type:raise ValueError(f'Line {number}: function return type mismatch')
            function=FunctionType(m[1],tuple(params),result_type,body,expression_cost(body))
            functions[m[1]]=function;types[m[1]]=function
        elif m := re.fullmatch(r"record ([A-Za-z_][A-Za-z_0-9]*):", line):
            if states or actions or len(records) >= 16 or m[1] in types or keyword.iskeyword(m[1]) or m[1] in ('true','false','append','update','remove','get','has','count','next_id'): raise ValueError(f"Line {number}: column 1: invalid record declaration")
            fields = []
            i += 1
            while i < len(lines) and lines[i][0] > 0:
                d, field, n = lines[i]
                f = re.fullmatch(r"([A-Za-z_][A-Za-z_0-9]*): (int|bool|text)", field)
                if not f or d != 4 or f[1] in ('id', 'true', 'false') or keyword.iskeyword(f[1]) or f[1] in dict(fields): raise ValueError(f"Line {n}: column {d+1}: invalid record field")
                fields.append((f[1], {'int': int, 'bool': bool, 'text': str}[f[2]]))
                i += 1
            if not 1 <= len(fields) <= 16: raise ValueError(f"Line {number}: column 1: record field limit")
            records[m[1]] = types[m[1]] = RecordType(m[1], tuple(fields))
            continue
        elif m := re.fullmatch(r"state ([A-Za-z_][A-Za-z_0-9]*): list<([A-Za-z_][A-Za-z_0-9]*)>\(max=([0-9]+)\) = \[\]", line):
            if actions or rules or tests or widgets or m[1] in types or keyword.iskeyword(m[1]) or m[1] in ('true','false') or m[2] not in records or not 1 <= int(m[3]) <= 100 or sum(isinstance(v, ListValue) for v in states.values()) >= 16:
                raise ValueError(f"Line {number}: column 1: invalid collection declaration")
            types[m[1]] = ListType(records[m[2]], int(m[3]))
            states[m[1]] = ListValue(types[m[1]])
        elif m := re.fullmatch(r"state ([A-Za-z_][A-Za-z_0-9]*)\s*=\s*(.+)", line):
            if actions or rules or tests or widgets: raise ValueError(f"Line {number}: states must precede actions")
            if m[1] in types: raise ValueError(f"Line {number}: duplicate state")
            if keyword.iskeyword(m[1]) or m[1] in ("true", "false"):
                raise ValueError(f"Line {number}: reserved identifier {m[1]}")
            node = expression(m[2], {}, number, m.start(2) + 1)
            try:
                states[m[1]] = evaluate(node, {})
            except ValueError as exc:
                raise ValueError(f"Line {number}: column {m.start(2) + 1}: {exc}") from exc
            types[m[1]] = type(states[m[1]])
        elif m := re.fullmatch(r"persist ([A-Za-z_][A-Za-z_0-9]*)", line):
            if m[1] not in states or m[1] in persistent:
                raise ValueError(f"Line {number}: persist requires a unique declared state")
            persistent.append(m[1])
        elif m := re.fullmatch(r"derive ([A-Za-z_][A-Za-z_0-9]*)\s*=\s*(.+)", line):
            if actions or rules or tests or widgets:
                raise ValueError(f"Line {number}: derives must precede actions")
            if m[1] in types:
                raise ValueError(f"Line {number}: duplicate identifier")
            node = expression(m[2], types, number, m.start(2) + 1)
            if keyword.iskeyword(m[1]) or m[1] in ("true", "false"):
                raise ValueError(f"Line {number}: reserved identifier {m[1]}")
            derived[m[1]] = node
            types[m[1]] = type_of(node, types)
        elif m := re.fullmatch(r"action ([A-Za-z_][A-Za-z_0-9]*):(?:\s*(.+))?", line):
            if m[1] in actions: raise ValueError(f"Line {number}: duplicate action")
            if m[2]: lines.insert(i+1, (4, m[2], number))
            if i+1 >= len(lines) or lines[i+1][0] <= 0: raise ValueError(f"Line {number}: empty action")
            body, i = block(i+1, lines[i+1][0])
            if statement_count(body) > MAX_ACTION_STEPS:
                raise ValueError(f"Line {number}: action exceeds statement limit")
            actions[m[1]] = body
            continue
        elif line.startswith("rule "):
            node = expression(line[5:], types, number, 6)
            if type_of(node, types) is not bool: raise ValueError(f"Line {number}: rule must be bool")
            rules.append(node)
        elif m := re.fullmatch(r"test ([A-Za-z_][A-Za-z_0-9]*):\s*(.*?)\s*->\s*(.+)", line):
            node = expression(m[3], types, number, m.start(3) + 1)
            if type_of(node, types) is not bool: raise ValueError(f"Line {number}: test must be bool")
            tests.append((m[1], tuple(x.strip() for x in m[2].split(",") if x.strip()), node))
        elif line == "navigation:":
            if navigation_seen: raise ValueError(f"Line {number}: column 1: duplicate navigation block")
            navigation_seen = True
            i += 1
            while i < len(lines) and lines[i][0] > 0:
                d, declaration, n = lines[i]
                if d != 4: raise ValueError(f"Line {n}: column {d+1}: navigation indentation")
                if m := re.fullmatch(r"initial ([A-Za-z_][A-Za-z_0-9]*)", declaration):
                    if initial_screen is not None: raise ValueError(f"Line {n}: column 5: duplicate initial screen")
                    initial_screen = m[1]
                    initial_span = n
                elif m := re.fullmatch(r"action ([A-Za-z_][A-Za-z_0-9]*) -> ([A-Za-z_][A-Za-z_0-9]*)(?: using ([A-Za-z_][A-Za-z_0-9]*))?", declaration):
                    if m[1] in navigation or len(navigation) >= MAX_NAV_COMMANDS: raise ValueError(f"Line {n}: column 5: duplicate navigation command or binding limit")
                    navigation[m[1]] = Navigation(m[1], m[2], m[3], Span(n,5))
                else: raise ValueError(f"Line {n}: column 5: invalid navigation declaration")
                i += 1
            continue
        elif m := re.fullmatch(r"screen ([A-Za-z_][A-Za-z_0-9]*)(?: when ([A-Za-z_][A-Za-z_0-9]*))?:", line):
            screen_name, guard_name = m[1], m[2]
            if screen_name in screens: raise ValueError(f"Line {number}: column 8: duplicate screen {screen_name}")
            if len(screens) >= MAX_SCREENS: raise ValueError(f"Line {number}: column 8: screen limit")
            guard = expression(guard_name, types, number, m.start(2)+1) if guard_name else None
            if guard is not None and type_of(guard,types) is not bool: raise ValueError(f"Line {number}: column 8: screen guard must be bool")
            screen_start = len(widgets)
            i += 1
            widget_indent = lines[i][0] if i < len(lines) else 0
            while i < len(lines) and lines[i][0] > 0:
                widget_depth, item, n = lines[i]
                if widget_depth != widget_indent: raise ValueError(f"Line {n}: widget indentation")
                widget_spans.append(Span(n,widget_depth+1))
                if m := re.fullmatch(r'list ([A-Za-z_][A-Za-z_0-9]*) select ([A-Za-z_][A-Za-z_0-9]*)(?: open ([A-Za-z_][A-Za-z_0-9]*))?(?: title ([A-Za-z_][A-Za-z_0-9]*)(?: status ([A-Za-z_][A-Za-z_0-9]*))?)?', item):
                    if not isinstance(types.get(m[1]), ListType) or m[2] not in states or types.get(m[2]) is not int: raise ValueError(f"Line {n}: column 1: list requires collection and int selection state")
                    if m[4] and (dict(types[m[1]].record.fields).get(m[4]) is not str or (m[5] and dict(types[m[1]].record.fields).get(m[5]) is not bool)): raise ValueError(f"Line {n}: column 1: list title/status require text/bool record fields")
                    widgets.append(("list_open", m[1], m[2], m[3], m[4], m[5]) if any(m[j] for j in (3,4,5)) else ("list",m[1],m[2]))
                elif m := re.fullmatch(r'text (.+)', item): widgets.append(("text", label(m[1], n, widget_depth + 6)))
                elif item.startswith('display '):
                    node=expression(item[8:],types,n,widget_depth+9)
                    if type_of(node,types) not in (int,bool,str): raise ValueError(f"Line {n}: column {widget_depth+9}: display requires scalar expression")
                    widgets.append(("display",node))
                elif m := re.fullmatch(r"value ([A-Za-z_][A-Za-z_0-9]*)", item):
                    if m[1] not in types: raise ValueError(f"Line {n}: unknown state")
                    if types[m[1]] not in (int, bool, str): raise ValueError(f"Line {n}: column {widget_depth+1}: value requires a scalar; use list for collections")
                    widgets.append(("value", m[1]))
                elif m := re.fullmatch(r'input ([A-Za-z_][A-Za-z_0-9]*)(?: label (.+))?', item):
                    if m[1] not in states or type(states[m[1]]) not in (int, str):
                        raise ValueError(f"Line {n}: input requires an integer or text state")
                    widgets.append(("input_text" if type(states[m[1]]) is str else "input_int", m[1], label(m[2],n,widget_depth+m.start(2)+1)) if m[2] else ("input_text" if type(states[m[1]]) is str else "input_int",m[1]))
                elif m := re.fullmatch(r'show ([A-Za-z_][A-Za-z_0-9]*) : text (.+)', item):
                    if m[1] not in types or types[m[1]] is not bool:
                        raise ValueError(f"Line {n}: show requires a boolean state or derive")
                    widgets.append(("show_text", m[1], label(m[2], n, widget_depth + m.start(2) + 1)))
                elif m := re.fullmatch(r'button (.+) -> ([A-Za-z_][A-Za-z_0-9]*)', item):
                    widgets.append(("button", label(m[1], n, widget_depth + 8), m[2]))
                else: raise ValueError(f"Line {n}: invalid widget")
                i += 1
            if len(widgets) == screen_start: raise ValueError(f"Line {number}: column 1: empty screen")
            screens[screen_name] = Screen(screen_name, tuple(Widget(w[0],w[1:],span) for w,span in zip(widgets[screen_start:],widget_spans[screen_start:])), guard, Span(number))
            continue
        else: raise ValueError(f"Line {number}: invalid declaration")
        i += 1
    if not name: raise ValueError("Missing app")
    has_navigation = navigation_seen or len(screens)>1
    if has_navigation:
        if not navigation_seen or initial_screen is None: raise ValueError("Line 1: column 1: navigation requires explicit initial screen")
        if initial_screen not in screens: raise ValueError(f"Line {initial_span}: column 5: unknown initial screen")
        if screens[initial_screen].guard is not None: raise ValueError(f"Line {screens[initial_screen].span.line}: column 1: initial screen must be unguarded")
        def fail_at(span,message): raise ValueError(f"Line {span.line}: column {span.column}: {message}")
        for screen in screens.values():
            if len(screen.name)>64 or screen.name in ('pop','true','false') or keyword.iskeyword(screen.name) or screen.name in types or screen.name in actions: fail_at(screen.span,"screen name conflict or invalid identifier")
        for binding in navigation.values():
            if len(binding.name)>64 or binding.name in ('true','false') or keyword.iskeyword(binding.name) or binding.name in types or binding.name in actions or binding.name in screens: fail_at(binding.span,"navigation name conflict")
            if binding.target!='pop' and binding.target not in screens: fail_at(binding.span,"unknown target screen "+binding.target)
            if binding.action and binding.action not in actions: fail_at(binding.span,"unknown domain action "+binding.action)
        used=set(); graph={key:set() for key in screens}
        for screen in screens.values():
            for widget in screen.widgets:
                command=widget.args[1] if widget.kind=='button' else widget.args[2] if widget.kind=='list_open' else None
                if command:
                    if widget.kind=="list_open" and command not in navigation: fail_at(widget.span,"list open requires a navigation command")
                    if command not in actions and command not in navigation: fail_at(widget.span,"Unknown action "+command)
                    if command in navigation:
                        used.add(command)
                        if navigation[command].target!='pop': graph[screen.name].add(navigation[command].target)
        for binding in navigation.values():
            if binding.name not in used: fail_at(binding.span,"unreachable navigation binding "+binding.name)
        reached={initial_screen}
        while True:
            expanded=reached | set().union(*(graph[key] for key in reached))
            if expanded==reached: break
            reached=expanded
        for screen in screens.values():
            if screen.name not in reached: fail_at(screen.span,"unreachable screen "+screen.name)
    else:
        initial_screen='main'
        if screens and set(screens)!={'main'}: raise ValueError("Line 1: column 1: non-main screen requires explicit navigation")
        for screen in screens.values():
            if screen.guard is not None: raise ValueError(f"Line {screen.span.line}: column 1: guarded screens require navigation")
    for _, seq, _ in tests:
        if any(action not in actions and action not in navigation for action in seq): raise ValueError("Unknown action")
    for widget,span in zip(widgets,widget_spans):
        if widget[0]=='button' and widget[2] not in actions and widget[2] not in navigation: raise ValueError(f"Line {span.line}: column {span.column}: Unknown action")
        if not has_navigation and (widget[0] in ('display','list_open') or len(widget)>2 and widget[0].startswith('input')): raise ValueError(f"Line {span.line}: column {span.column}: presentation extension requires navigation")
    # Bound expanded derived expressions: generators inline them in actions/rules.
    sizes = {key: 1 for key in states}
    for key, expr in derived.items():
        sizes[key] = sum(sizes.get(item.id, 1) if isinstance(item, ast.Name) else 1+(item.pure_function.cost if isinstance(item,ast.Call) and hasattr(item,"pure_function") else 0)+getattr(item,"query_cost",0) for item in ast.walk(expr))
        if sizes[key] > MAX_DERIVED_NODES:
            raise ValueError("Derived expression exceeds expansion limit")
    values = resolve(states, derived)
    if not all(evaluate(rule, values) for rule in rules): raise ValueError("Invalid initial state")
    program = Program(name, states, actions, tuple(rules), tuple(tests), tuple(widgets), derived, tuple(persistent), records, screens, navigation, initial_screen, has_navigation, functions)
    if records or has_navigation:
        from sedrava_records import check_resources
        try:
            check_resources(program, states)
        except ValueError as exc:
            raise ValueError(f"Line 1: column 1: {exc}") from exc
    return program

def resolve(state, derived):
    values = {name: validate(value) for name, value in state.items()}
    for name, expr in (derived or {}).items():
        values[name] = evaluate(expr, values)
    return values

def valid_state(program, state):
    try:
        if state.keys() != program.states.keys():
            return False
        for key, initial in program.states.items():
            validate(state[key], value_type(initial))
        values = resolve(state, program.derived)
        if program.records or program.has_navigation:
            from sedrava_records import check_resources
            check_resources(program, state)
        return all(evaluate(rule, values) for rule in program.rules)
    except (ValueError, KeyError):
        return False


def edit_state(program, state, key, value):
    if key not in program.states:
        return state.copy(), False
    candidate = {**state, key: value}
    return (candidate, True) if valid_state(program, candidate) else (state.copy(), False)


def restore_state(program, saved):
    if program.records or program.has_navigation:
        from sedrava_records import restore_snapshot
        try: return restore_snapshot(program, saved)
        except ValueError: return program.states.copy()
    candidate = program.states.copy()
    if type(saved) is dict:
        for key, initial in program.states.items():
            if key in program.persistent and key in saved:
                try:
                    candidate[key] = checked_value(saved[key], type(initial))
                except ValueError:
                    pass
    return candidate if valid_state(program, candidate) else program.states.copy()

def transition(program, state, action):
    if action not in program.actions: raise ValueError("Unknown action")
    if not valid_state(program, state): raise ValueError("Invalid action input state")
    candidate = state.copy()
    steps = 0
    def execute(stmts, local=None):
        nonlocal steps
        local=dict(local or {})
        for stmt in stmts:
            steps += 1
            if steps > MAX_ACTION_STEPS:
                raise ValueError("Action exceeds execution step limit")
            values={**resolve(candidate,program.derived),**local}
            if isinstance(stmt, Let):
                local[stmt.name]=evaluate(stmt.expr,values)
            elif isinstance(stmt, Require):
                if not evaluate(stmt.condition, values): raise ValueError('Action requirement rejected')
            elif isinstance(stmt, Assign):
                candidate[stmt.name] = evaluate(stmt.expr, values)
                resolve(candidate, program.derived)
            elif isinstance(stmt, Repeat):
                for repeat_index in range(stmt.count):
                    execute(stmt.body,{**local,stmt.name:repeat_index})
            elif isinstance(stmt, If):
                execute(stmt.yes if evaluate(stmt.condition, values) else stmt.no, local)
            else:
                raise ValueError("Unsupported action statement")
    execute(program.actions[action])
    values = resolve(candidate, program.derived)
    if program.records or program.has_navigation:
        from sedrava_records import check_resources
        check_resources(program, candidate)
    if not all(evaluate(rule, values) for rule in program.rules):
        return state.copy(), False
    return candidate, True

def run(program):
    for name, actions, expected in program.tests:
        state = program.states.copy()
        if program.has_navigation:
            from sedrava_navigation import initial_session, dispatch
            session=initial_session(program)
        for action in actions:
            if program.has_navigation:
                session,accepted=dispatch(program,session,action)
                state=session.state
            else:
                state, accepted = transition(program, state, action)
            if not accepted: raise AssertionError(f"{name}: invariant violated")
        if not evaluate(expected, resolve(state, program.derived)): raise AssertionError(f"{name}: assertion failed")
    return len(program.tests)
