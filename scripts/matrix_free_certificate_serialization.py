"""Bounded inert JSON snapshots, canonical hashes and rational text.

Reservations count logical references and conservative ASCII output bytes, not
Python heap usage or RSS. Work units model scans, comparisons and encoding.
"""
from decimal import Decimal, localcontext
from fractions import Fraction
import hashlib
import json
from math import isfinite

MAX_JSON_NODES = 2_000_000
MAX_JSON_BYTES = 64 * 1024 * 1024
MAX_JSON_DEPTH = 40
MAX_INPUT_STRING = 4096
MAX_INPUT_INT_BITS = 4096
MAX_FRACTION_BITS = 65536


def _fail(message):
    raise ValueError(message)


def _decimal_digits(bits):
    # 30103/100000 strictly exceeds log10(2); one digit for zero.
    return max(1, (max(1, bits) * 30103) // 100000 + 1)


def _string_bound(value, budget):
    # Before inspecting code points, charge every character and both quotes.
    budget.charge('json_string_scan', len(value) + 2)
    count = 2
    for c in value:
        n = ord(c)
        if c in ('"', '\\') or n in (8, 9, 10, 12, 13): count += 2
        elif n < 32 or 127 <= n <= 65535: count += 6
        elif n > 65535: count += 12
        else: count += 1
    return count


def _scan(value, budget, *, clone, input_caps):
    nodes = 0
    byte_upper = 0
    work_start = budget.work
    entry_start = budget.logical_entries
    counters_start = dict(budget.counters)

    def add_bytes(count):
        nonlocal byte_upper
        if byte_upper + count > MAX_JSON_BYTES:
            _fail('certificate canonical JSON byte limit exceeded')
        byte_upper += count

    def visit(item, depth):
        nonlocal nodes
        budget.charge('json_scan_nodes')
        nodes += 1
        if nodes > MAX_JSON_NODES or depth > MAX_JSON_DEPTH:
            _fail('certificate JSON node/depth limit exceeded')
        kind = type(item)
        if item is None:
            add_bytes(4); return item
        if kind is bool:
            add_bytes(4 if item else 5); return item
        if kind is int:
            bits = item.bit_length()
            if bits > MAX_INPUT_INT_BITS:
                _fail('certificate JSON integer width exceeded')
            add_bytes(_decimal_digits(bits) + (item < 0))
            return item
        if kind is float:
            if not isfinite(item): _fail('certificate JSON contains nonfinite float')
            add_bytes(32); return item
        if kind is str:
            if input_caps and len(item) > MAX_INPUT_STRING:
                _fail('certificate JSON input string length exceeded')
            add_bytes(_string_bound(item, budget)); return item
        if kind in (list, tuple):
            n = len(item)
            if n > MAX_JSON_NODES - nodes: _fail('certificate JSON sequence limit exceeded')
            add_bytes(2 + max(0, n - 1))
            if clone:
                budget.entries(n + 1, 'JSON sequence snapshot')
                return [visit(child, depth + 1) for child in item]
            for child in item: visit(child, depth + 1)
            return None
        if kind is dict:
            n = len(item)
            if n > MAX_JSON_NODES - nodes: _fail('certificate JSON mapping limit exceeded')
            add_bytes(2 + max(0, n - 1) + n)
            if clone: budget.entries(2 * n + 1, 'JSON mapping snapshot')
            # Reserve key scan before reading each string; sorting comparisons
            # are precharged separately in canonical_hash before json.dumps.
            result = {} if clone else None
            for key, child in item.items():
                if type(key) is not str or (input_caps and len(key) > MAX_INPUT_STRING):
                    _fail('certificate JSON key must be a bounded plain string')
                add_bytes(_string_bound(key, budget))
                child_copy = visit(child, depth + 1)
                if clone: result[key] = child_copy
            return result
        _fail('certificate accepts inert JSON-compatible data only')

    result = visit(value, 0)
    delta = {k: v - counters_start.get(k, 0) for k, v in budget.counters.items()
             if v != counters_start.get(k, 0)}
    return result, {'nodes': nodes, 'json_bytes_upper': byte_upper,
                    'work_delta': budget.work - work_start,
                    'entry_delta': budget.logical_entries - entry_start,
                    'counters_delta': delta}


def clone_json(value, budget):
    return _scan(value, budget, clone=True, input_caps=True)


def canonical_hash(value, budget):
    # Hashes include normalized output strings, which have their own separate
    # cumulative FractionText bound and need not obey the input field cap.
    start_work, start_entries, start_counters = budget.work, budget.logical_entries, dict(budget.counters)
    _, receipt = _scan(value, budget, clone=False, input_caps=False)
    budget.entries(1, 'JSON hash traversal stack')
    stack = [value]
    while stack:
        obj = stack.pop()
        if type(obj) is dict:
            n = len(obj)
            budget.charge('json_key_length_scan', n)
            max_key = max((len(k) for k in obj), default=0)
            budget.charge('json_sorted_key_comparisons', n * (1 + n.bit_length()) * (1 + max_key))
            budget.entries(n, 'JSON hash traversal children')
            stack.extend(obj.values())
        elif type(obj) in (tuple, list):
            budget.entries(len(obj), 'JSON hash traversal children')
            stack.extend(obj)
    upper = receipt['json_bytes_upper']
    budget.charge('json_encoding_ascii_bytes', 2 * upper)
    text = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False)
    encoded = text.encode('ascii')
    if len(encoded) > upper:
        _fail('canonical JSON exceeded its ASCII forecast')
    digest = hashlib.sha256(encoded).hexdigest()
    delta = {k: v - start_counters.get(k, 0) for k, v in budget.counters.items()
             if v != start_counters.get(k, 0)}
    receipt = dict(receipt, ascii_bytes=len(encoded), text_buffer_bytes_upper=upper,
                   encoded_buffer_bytes_upper=upper, work_delta=budget.work - start_work,
                   entry_delta=budget.logical_entries - start_entries, counters_delta=delta)
    return digest, receipt


class FractionText:
    """Cumulative ASCII upper bound for exact rational output strings."""
    def __init__(self, budget, max_bytes=MAX_JSON_BYTES):
        if type(max_bytes) is not int or not 0 < max_bytes <= MAX_JSON_BYTES:
            _fail('Fraction text limit must be positive and reduce-only')
        self.budget = budget
        self.max_bytes = max_bytes
        self.bytes_upper = 0
        self.calls = 0

    def format(self, value):
        if type(value) is not Fraction: raise TypeError('Fraction required')
        nb, db = value.numerator.bit_length(), value.denominator.bit_length()
        if max(nb, db) > min(MAX_FRACTION_BITS, self.budget.limits['integer_bits']):
            _fail('Fraction text integer bit limit exceeded')
        count = _decimal_digits(nb) + (value.numerator < 0)
        if value.denominator != 1:
            count += 1 + _decimal_digits(db)
        if self.bytes_upper + count > self.max_bytes:
            _fail('cumulative Fraction text byte limit exceeded')
        self.budget.entries(1, 'Fraction text output reference')
        self.budget.charge('fraction_decimal_character_work', 16 * count)
        self.bytes_upper += count
        self.calls += 1
        with localcontext() as context:
            context.prec = 1
            numerator = format(Decimal(value.numerator), 'f')
            out = (numerator if value.denominator == 1 else
                   numerator + '/' + format(Decimal(value.denominator), 'f'))
        if len(out) > count: _fail('Fraction text exceeded its forecast')
        return out

    def receipt(self):
        return {'calls': self.calls, 'bytes_upper': self.bytes_upper,
                'max_bytes': self.max_bytes,
                'scope': 'Cumulative conservative ASCII characters; not process memory.'}
