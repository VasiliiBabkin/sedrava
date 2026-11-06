"""Closed/open error sums and exhaustive action match; no engine exception capture."""
import re
from dataclasses import dataclass

IDENT = r'[A-Za-z][A-Za-z0-9_]*'
HEADER = re.compile(r'error (closed|open) ('+IDENT+r')(?: id "([A-Za-z][A-Za-z0-9_.-]{0,127})")?:')
MAX_ERROR_TYPES = 16
MAX_VARIANTS = 16
MAX_FIELDS = 16
TYPE_NAMES = frozenset({'int','text','bool','list','Result','Error'})
ENGINE_FAULTS = frozenset({'BudgetExceeded', 'PolicyViolation', 'CapabilityDenied', 'CompilerError', 'InternalError'})

@dataclass(frozen=True)
class ErrorType:
    name: str
    identity: str
    opened: bool
    variants: tuple

@dataclass(frozen=True)
class ErrorValue:
    kind: ErrorType
    variant: str
    values: tuple

@dataclass(frozen=True)
class LegacyErrorType:
    """Opaque legacy Error payload: only wildcard matching is supported."""

@dataclass(frozen=True)
class MatchArm:
    tag: str  # Ok, Err (wildcard), or a variant name
    bindings: tuple  # (local name, field name); empty field means entire value
    body: tuple

@dataclass(frozen=True)
class Match:
    expr: object
    kind: object
    arms: tuple


def valid_name(name):
    from sedrava_syntax import is_reserved_identifier
    return bool(re.fullmatch(IDENT, name)) and not is_reserved_identifier(name) and name not in ENGINE_FAULTS and name not in ('Ok','Err')


def valid_error_name(name):
    return valid_name(name) and name not in TYPE_NAMES


def parse_declaration(lines, pos, symbols, errors):
    _, line, number = lines[pos]
    match = HEADER.fullmatch(line)
    def fail(message, n=number, col=1):
        raise ValueError(f'Line {n}: column {col}: E_ERROR_TYPE: {message}')
    if not match or not valid_error_name(match[2]) or match[2] in symbols:
        fail('invalid/duplicate error type')
    if len(errors) >= MAX_ERROR_TYPES:
        fail('error type resource limit')
    identity = match[3] or 'entry.' + match[2]
    if len(identity)>128:fail('stable error identity resource limit')
    if any(t.identity == identity for t in errors.values()):
        fail('duplicate stable error identity')
    variants = []
    pos += 1
    while pos < len(lines) and lines[pos][0] > 0:
        depth, text, n = lines[pos]
        variant = re.fullmatch('('+IDENT+r'):', text)
        if depth != 4 or not variant or len(variant[1])>64 or not valid_name(variant[1]) or variant[1] in dict(variants):
            fail('invalid/duplicate/reserved error variant', n, depth+1)
        if len(variants) >= MAX_VARIANTS:
            fail('variant resource limit', n, depth+1)
        fields = []
        pos += 1
        while pos < len(lines) and lines[pos][0] > 4:
            d, text, field_line = lines[pos]
            field = re.fullmatch('('+IDENT+r'): (int|text|bool)', text)
            if d != 8 or not field or len(field[1])>64 or not valid_name(field[1]) or field[1] in dict(fields):
                fail('invalid/duplicate error field', field_line, d+1)
            if len(fields) >= MAX_FIELDS:
                fail('field resource limit', field_line, d+1)
            fields.append((field[1], {'int': int, 'text': str, 'bool': bool}[field[2]]))
            pos += 1
        variants.append((variant[1], tuple(fields)))
    if not variants:
        fail('error type requires at least one variant')
    return ErrorType(match[2], identity, match[1] == 'open', tuple(variants)), pos


def pattern(source):
    """Pattern syntax shared by core checking and namespace hygiene.

    Return (tag, ((field, binder, start, end), ...)); positions are scalar columns.
    A shorthand field is lowered to field: hygienic_binding in modules.
    """
    simple = re.fullmatch(r'(Ok|Err)\(('+IDENT+r')\):', source)
    if simple:
        return simple[1], (('', simple[2], simple.start(2), simple.end(2)),)
    variant = re.fullmatch(r'Err\(('+IDENT+r')\s*\{(.*?)\}\):', source)
    if not variant:
        raise ValueError('E_MATCH: invalid Result pattern')
    entries = []
    raw = variant[2]
    cursor = variant.start(2)
    if raw.strip():
        for part in raw.split(','):
            entry = re.fullmatch(r'\s*('+IDENT+r')(?:\s*:\s*('+IDENT+r'))?\s*', part)
            if not entry:
                raise ValueError('E_MATCH: invalid field binding')
            group = 2 if entry[2] else 1
            entries.append((entry[1], entry[group], cursor+entry.start(group), cursor+entry.end(group)))
            cursor += len(part)+1
    return variant[1], tuple(entries)


def check_arm(kind, tag, entries, known, seen):
    from sedrava_results import ResultType
    if not isinstance(kind, ResultType):
        raise ValueError('E_MATCH: match requires Result')
    if 'Err' in seen or tag in seen:
        raise ValueError('E_MATCH: duplicate or unreachable branch')
    if tag == 'Ok':
        fields = {'': kind.value}
    elif tag == 'Err':
        fields = {'': kind.error or LegacyErrorType()}
        if kind.error is not None and not kind.error.opened and set(dict(kind.error.variants)) <= seen:
            raise ValueError('E_MATCH: unreachable wildcard')
    else:
        if kind.error is None or tag not in dict(kind.error.variants):
            raise ValueError('E_MATCH: unknown error variant '+tag)
        fields = dict(dict(kind.error.variants)[tag])
    scope = dict(known)
    used = set()
    bindings = []
    for field, binder, _, _ in entries:
        if field not in fields or field in used:
            raise ValueError('E_MATCH: unknown or duplicate field '+field)
        if not valid_name(binder) or binder in scope:
            raise ValueError('E_MATCH: duplicate/reserved/shadowing binding '+binder)
        used.add(field)
        scope[binder] = fields[field]
        bindings.append((binder, field))
    return scope, tuple(bindings)


def exhaustive(kind, seen):
    if 'Ok' not in seen:
        raise ValueError('E_MATCH: missing Ok branch')
    if kind.error is None or kind.error.opened:
        if 'Err' not in seen:
            raise ValueError('E_MATCH: open/legacy error requires final Err(error)')
    elif 'Err' not in seen and set(dict(kind.error.variants)) - seen:
        raise ValueError('E_MATCH: non-exhaustive closed error variants')


def validate(value, expected=None):
    from sedrava_core import checked_value
    if type(value) is not ErrorValue or not isinstance(value.kind,ErrorType) or expected is not None and value.kind != expected:
        raise ValueError('Invalid typed error')
    fields = dict(value.kind.variants).get(value.variant)
    if fields is None or type(value.values) is not tuple or len(value.values) != len(fields):
        raise ValueError('Invalid error variant payload')
    for (_, kind), item in zip(fields, value.values):
        checked_value(item, kind)
    return value


def constructor(node, types, type_of):
    import ast
    if not isinstance(node.func, ast.Attribute) or not isinstance(node.func.value, ast.Name):
        raise ValueError('E_ERROR_TYPE: expected named error variant constructor')
    kind = types.get(node.func.value.id)
    if not isinstance(kind, ErrorType) or node.func.value.id != kind.name:
        raise ValueError('E_ERROR_TYPE: constructor requires an error type symbol')
    fields = dict(kind.variants).get(node.func.attr)
    if fields is None:
        raise ValueError('E_ERROR_TYPE: unknown error variant '+node.func.attr)
    if node.args or len(node.keywords) != len(fields) or {kw.arg for kw in node.keywords} != set(dict(fields)):
        raise ValueError('E_ERROR_TYPE: variant requires exact named fields')
    if any(type_of(kw.value, types) is not dict(fields)[kw.arg] for kw in node.keywords):
        raise ValueError('E_ERROR_TYPE: variant field type mismatch')
    node.error_type, node.error_variant, node.error_fields = kind, node.func.attr, fields
    return kind


def checked_constructor_metadata(node):
    """Effects sees only actual typed constructors, never an arbitrary marker."""
    import ast
    kind=getattr(node,'error_type',None)
    if (not isinstance(kind,ErrorType) or not isinstance(node.func,ast.Attribute)
            or not isinstance(node.func.value,ast.Name) or node.func.value.id!=kind.name
            or getattr(node,'error_variant',None)!=node.func.attr
            or node.func.attr not in dict(kind.variants)
            or not isinstance(getattr(node,'error_fields',None),tuple)
            or dict(kind.variants).get(node.func.attr)!=node.error_fields
            or node.args or len(node.keywords)!=len(node.error_fields)
            or {kw.arg for kw in node.keywords}!=set(dict(node.error_fields))):
        raise ValueError('Error constructor metadata does not match typed IR')
