"""Internal, target-independent immutable record/list values and strict snapshots."""
from dataclasses import dataclass
import json
from sedrava_sequences import ValueList,ValueListType,validate_list

def structured(program):
    return bool(program.records or program.has_navigation or any(isinstance(v,ValueList) for v in program.states.values()))


@dataclass(frozen=True)
class RecordType:
    name: str
    fields: tuple

@dataclass(frozen=True)
class ListType:
    record: RecordType
    capacity: int

@dataclass(frozen=True)
class RecordValue:
    kind: RecordType
    values: tuple

@dataclass(frozen=True)
class ListValue:
    kind: ListType
    items: tuple = ()  # (stable id, RecordValue)
    next_id: int = 1


def value_type(value):
    from sedrava_results import ResultValue
    if isinstance(value,ResultValue):return value.kind
    return value.kind if isinstance(value, (ListValue, RecordValue, ValueList)) else type(value)


def validate(value, expected=None):
    from sedrava_core import checked_value
    from sedrava_results import ResultValue,validate as validate_result
    if isinstance(value,ResultValue):return validate_result(value,expected)
    kind = value_type(value)
    if expected is not None and kind != expected:
        raise ValueError('Value type mismatch')
    if isinstance(value, ValueList):return validate_list(value,expected)
    if isinstance(value, RecordValue):
        if type(value.values) is not tuple or len(value.values) != len(kind.fields):
            raise ValueError('Invalid record')
        for (_, field_type), field in zip(kind.fields, value.values):
            checked_value(field, field_type)
    elif isinstance(value, ListValue):
        if (type(value.items) is not tuple or len(value.items) > kind.capacity
                or type(value.next_id) is not int or not 1 <= value.next_id <= 2147483647):
            raise ValueError('Invalid collection')
        ids = set()
        for identity, record in value.items:
            if type(identity) is not int or not 0 < identity < value.next_id or identity in ids:
                raise ValueError('Invalid identity')
            ids.add(identity)
            validate(record, kind.record)
    else:
        return checked_value(value, expected)
    return value


def operation(name, values):
    collection = values[0]
    if isinstance(collection,ValueList):
        from sedrava_sequences import operation as vector_operation
        return vector_operation(name,values)
    if name=='list_capacity':return collection.kind.capacity
    if name=='list_identity':
        operation('list_at',values)
        return collection.items[values[1]][0]
    if name=='list_index':return next((i for i,(_,record) in enumerate(collection.items) if record==values[1]),-1)
    if name in ('list_replace_at','list_remove_at'):
        operation('list_at',values)
        identity=collection.items[values[1]][0]
        return operation('update' if name=='list_replace_at' else 'remove',[collection,identity,*values[2:]])
    if name == 'count': return len(collection.items)
    if name == 'next_id': return collection.next_id
    if name == 'list_at':
        index = values[1]
        if type(index) is not int or not 0 <= index < len(collection.items):
            raise ValueError('Collection positional index out of bounds')
        return collection.items[index][1]
    if name == 'list_slice':
        start, end = values[1], values[2]
        if (type(start) is not int or type(end) is not int
                or not 0 <= start <= end <= len(collection.items)):
            raise ValueError('Collection slice bounds invalid')
        return validate(ListValue(collection.kind, collection.items[start:end], collection.next_id))
    if name == 'list_clear':
        return validate(ListValue(collection.kind, (), collection.next_id))
    if name == 'append':
        if len(collection.items) >= collection.kind.capacity: raise ValueError('Collection capacity exceeded')
        if collection.next_id == 2147483647: raise ValueError('Identity exhausted')
        return validate(ListValue(collection.kind, collection.items + ((collection.next_id, values[1]),), collection.next_id + 1))
    identity = values[1]
    found = next((record for key, record in collection.items if key == identity), None)
    if name == 'has': return found is not None
    if found is None: raise ValueError('Missing record identity')
    if name == 'get': return found
    items = tuple((key, values[2] if key == identity else record) for key, record in collection.items) if name == 'update' else tuple((key, record) for key, record in collection.items if key != identity)
    return validate(ListValue(collection.kind, items, collection.next_id))


def plain(value):
    if isinstance(value, RecordValue): return {key: field for (key, _), field in zip(value.kind.fields, value.values)}
    if isinstance(value, ValueList):return list(value.items)
    if isinstance(value, ListValue): return {'next_id': value.next_id, 'items': [dict(id=key, **plain(record)) for key, record in value.items]}
    return value


def decode(value, kind):
    if isinstance(kind,ValueListType):
        if type(value) is not list or len(value)>kind.capacity:raise ValueError('Invalid value-list snapshot')
        return validate_list(ValueList(kind,tuple(value)))
    if isinstance(kind, ListType):
        if type(value) is not dict or set(value) != {'next_id', 'items'} or type(value['items']) is not list or len(value['items']) > kind.capacity:
            raise ValueError('Invalid collection snapshot')
        items = []
        for row in value['items']:
            if type(row) is not dict or set(row) != {'id', *(k for k, _ in kind.record.fields)}: raise ValueError('Invalid record snapshot')
            record = RecordValue(kind.record, tuple(row[k] for k, _ in kind.record.fields))
            items.append((row['id'], record))
        return validate(ListValue(kind, tuple(items), value['next_id']))
    return validate(value, kind)


def fingerprint(program):
    def kind(value):
        t = value_type(value)
        if isinstance(t,ValueListType):return ['value-list',t.element.__name__,t.capacity]
        if isinstance(t, ListType): return ['list', t.record.name, [[k, f.__name__] for k, f in t.record.fields], t.capacity]
        return t.__name__
    return json.dumps([[k, kind(v), k in program.persistent] for k, v in program.states.items()], separators=(',', ':'), ensure_ascii=True)


def serialize_state(program, state):
    from sedrava_core import valid_state
    if not valid_state(program, state): raise ValueError('Invalid state')
    raw = json.dumps({'schema': 1, 'signature': fingerprint(program), 'state': {k: plain(state[k]) for k in program.persistent}}, ensure_ascii=False, separators=(',', ':'))
    if len(raw.encode('utf-16-le')) // 2 > 200000: raise ValueError('Snapshot too large')
    return raw


def restore_snapshot(program, raw):
    from sedrava_core import valid_state
    def pairs(entries):
        result = {}
        for key, value in entries:
            if key in result: raise ValueError('Duplicate JSON key')
            result[key] = value
        return result
    def integer(token):
        if len(token) > 11: raise ValueError('JSON integer overflow')
        value = int(token)
        if not -2147483648 <= value <= 2147483647: raise ValueError('JSON integer overflow')
        return value
    try:
        if type(raw) is not str or len(raw.encode('utf-16-le')) // 2 > 200000: raise ValueError('Snapshot too large')
        data = json.loads(raw, object_pairs_hook=pairs, parse_int=integer, parse_float=lambda _: (_ for _ in ()).throw(ValueError('Integer JSON required')), parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Invalid JSON')))
        if type(data) is not dict or set(data) != {'schema', 'signature', 'state'} or type(data['schema']) is not int or data['schema'] != 1 or data['signature'] != fingerprint(program): raise ValueError('Incompatible schema')
        if type(data['state']) is not dict or set(data['state']) != set(program.persistent): raise ValueError('Invalid saved keys')
        candidate = program.states.copy()
        for key, value in data['state'].items(): candidate[key] = decode(value, value_type(program.states[key]))
        if not valid_state(program, candidate): raise ValueError('Saved invariants rejected')
        return candidate
    except (TypeError, KeyError, RecursionError, UnicodeError, OverflowError) as exc:
        raise ValueError('Invalid snapshot') from exc


def check_resources(program, state):
    raw = json.dumps({'schema': 1, 'signature': fingerprint(program), 'state': {k: plain(v) for k,v in state.items()}}, ensure_ascii=False, separators=(',', ':'))
    if len(raw.encode('utf-16-le')) // 2 > 200000: raise ValueError('State exceeds snapshot resource limit')
