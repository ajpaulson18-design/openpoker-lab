"""Bounded structural fingerprint for a private, already-validated model.

This helper detects later mutation; it does not validate a poker model and
cannot authorize skipping the existing independent validators.
"""
from collections import Counter
from dataclasses import fields
from fractions import Fraction
import hashlib
import math
import struct

from scripts.flop_class_reweight_plan import ReweightPlan
from scripts.flop_class_reweight_proof import WeightedClassModel
from scripts.flop_multistreet_validation import _Chance, _Decision, _Terminal


class FingerprintError(ValueError):
    pass


class Limits:
    __slots__ = ("objects", "edges", "depth", "string_chars", "integer_bits",
                 "output_bytes", "stack", "set_bytes")

    def __init__(self, *, objects=60_000, edges=240_000, depth=160,
                 string_chars=16_384, integer_bits=4_096,
                 output_bytes=16 * 1024 * 1024, stack=8_192,
                 set_bytes=1 * 1024 * 1024):
        values = (objects, edges, depth, string_chars, integer_bits,
                  output_bytes, stack, set_bytes)
        if any(type(v) is not int or v <= 0 for v in values):
            raise FingerprintError("Every fingerprint limit must be a positive exact integer")
        self.objects, self.edges, self.depth, self.string_chars, self.integer_bits, \
            self.output_bytes, self.stack, self.set_bytes = values


def _custom_fields(value):
    kind = type(value)
    if kind is WeightedClassModel:
        names = tuple(field.name for field in fields(WeightedClassModel))
        actual = vars(value)
        if set(actual) != set(names):
            raise FingerprintError("WeightedClassModel has missing or extra attributes")
        return "WeightedClassModel", tuple((name, actual[name]) for name in names)
    if kind is ReweightPlan:
        names = tuple(field.name for field in fields(ReweightPlan))
        actual = vars(value)
        if set(actual) != set(names):
            raise FingerprintError("ReweightPlan has missing or extra attributes")
        return "ReweightPlan", tuple((name, actual[name]) for name in names)
    node_fields = {
        _Decision: ("history", "player", "street", "board", "actions", "children"),
        _Chance: ("history", "card_index", "street", "branches"),
        _Terminal: ("history", "kind", "contributions", "winner"),
    }
    if kind in node_fields:
        names = node_fields[kind]
        if tuple(kind.__slots__) != names:
            raise FingerprintError("Physical node slot declaration changed")
        return kind.__name__, tuple((name, getattr(value, name)) for name in names)
    return None


def _integer_bytes(value, limits):
    if type(value) is not int or value.bit_length() > limits.integer_bits:
        raise FingerprintError("Integer type or bit length exceeds fingerprint bounds")
    size = max(1, (value.bit_length() + 7) // 8)
    return (b"-" if value < 0 else b"+") + abs(value).to_bytes(size, "big")


def _int_payload_size(value, limits):
    if type(value) is not int or value.bit_length() > limits.integer_bits:
        raise FingerprintError("Integer type or bit length exceeds fingerprint bounds")
    return 1 + max(1, (value.bit_length() + 7) // 8)


def _utf8_size(value, limits):
    if type(value) is not str or len(value) > limits.string_chars:
        raise FingerprintError("String exceeds fingerprint bounds")
    size = 0
    for char in value:
        code = ord(char)
        if 0xD800 <= code <= 0xDFFF:
            raise FingerprintError("String contains a non-UTF-8 surrogate")
        size += 1 if code <= 0x7F else (2 if code <= 0x7FF else (3 if code <= 0xFFFF else 4))
        if size > limits.string_chars:
            raise FingerprintError("UTF-8 string exceeds fingerprint bounds")
    return size


def _frame_size(payload_size):
    return 1 + 8 + payload_size


def _atomic_size(value, limits):
    kind = type(value)
    if value is None:
        return 1
    if kind is bool:
        return 2
    if kind is int:
        return _frame_size(_int_payload_size(value, limits))
    if kind is float:
        if not math.isfinite(value):
            raise FingerprintError("Non-finite float is not fingerprintable")
        return _frame_size(8)
    if kind is str:
        return _frame_size(_utf8_size(value, limits))
    if kind is Fraction:
        numerator = _frame_size(_int_payload_size(value.numerator, limits))
        denominator = _frame_size(_int_payload_size(value.denominator, limits))
        return _frame_size(numerator + denominator)
    raise FingerprintError("Set/frozenset members must be supported exact atomic values")


def _atomic_output_size(value, index, limits):
    kind = type(value)
    label_size = _utf8_size(str(index), limits)
    total = _frame_size(label_size)
    if value is None:
        return total + _frame_size(0)
    if kind is bool:
        return total + _frame_size(1)
    if kind is int:
        return total + _frame_size(_int_payload_size(value, limits))
    if kind is float:
        if not math.isfinite(value):
            raise FingerprintError("Non-finite float is not fingerprintable")
        return total + len(b"F64") + 8 + 8
    if kind is str:
        return total + _frame_size(_utf8_size(value, limits))
    if kind is Fraction:
        total += _frame_size(8)  # Fraction object marker
        for label, component in (("numerator", value.numerator),
                                 ("denominator", value.denominator)):
            total += _frame_size(_utf8_size(label, limits))
            total += _frame_size(_int_payload_size(component, limits))
        return total + _frame_size(_utf8_size("Fraction", limits))
    raise FingerprintError("Set/frozenset members must be supported exact atomic values")


def _frame(tag, payload):
    return tag + len(payload).to_bytes(8, "big") + payload


def _atomic_bytes(value, limits):
    """Small exact encoding used only to order set members."""
    kind = type(value)
    if value is None:
        return b"N"
    if kind is bool:
        return b"B1" if value else b"B0"
    if kind is int:
        return _frame(b"I", _integer_bytes(value, limits))
    if kind is float:
        if not math.isfinite(value):
            raise FingerprintError("Non-finite float is not fingerprintable")
        return _frame(b"F", struct.pack(">d", value))
    if kind is str:
        raw = value.encode("utf-8")
        return _frame(b"S", raw)
    if kind is Fraction:
        pair = _frame(b"I", _integer_bytes(value.numerator, limits)) + \
            _frame(b"I", _integer_bytes(value.denominator, limits))
        return _frame(b"Q", pair)
    raise FingerprintError("Set/frozenset members must be supported exact atomic values")


def fingerprint(value, *, limits=None):
    """Return ``(sha256, census)`` using bounded iterative graph traversal.

    Container insertion/order is significant. Shared reference topology is
    represented by traversal-local ordinals; process object ids never enter
    the digest. Sets are sorted only when every member has bounded atomic data.
    """
    limits = Limits() if limits is None else limits
    if type(limits) is not Limits:
        raise FingerprintError("Expected exact Limits")
    limit_values = tuple(getattr(limits, name) for name in Limits.__slots__)
    if any(type(item) is not int or item <= 0 for item in limit_values):
        raise FingerprintError("Mutated Limits must remain positive exact integers")
    digest = hashlib.sha256()
    emitted = 0
    edges = 0
    max_depth = 0
    max_stack = 1
    seen = {}
    counts = Counter()
    stack = [("visit", value, 0)]

    def emit(tag, payload=b""):
        nonlocal emitted
        if type(tag) is not bytes or type(payload) is not bytes:
            raise FingerprintError("Internal fingerprint token is malformed")
        size = len(tag) + 8 + len(payload)
        if emitted + size > limits.output_bytes:
            raise FingerprintError("Fingerprint stream exceeds output bound")
        digest.update(tag)
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
        emitted += size
        counts[tag.decode("ascii", "replace")] += 1

    def ensure_token(tag, payload=b""):
        if emitted + len(tag) + 8 + len(payload) > limits.output_bytes:
            raise FingerprintError("Fingerprint stream exceeds output bound")

    def ensure_token_size(tag, payload_size):
        if emitted + len(tag) + 8 + payload_size > limits.output_bytes:
            raise FingerprintError("Fingerprint stream exceeds output bound")

    def push(item):
        nonlocal max_stack
        if len(stack) + 1 > limits.stack:
            raise FingerprintError("Fingerprint traversal stack exceeds bound")
        stack.append(item)
        max_stack = max(max_stack, len(stack))

    def add_edges(amount):
        nonlocal edges
        if type(amount) is not int or amount < 0 or edges + amount > limits.edges:
            raise FingerprintError("Fingerprint edge count exceeds bound")
        edges += amount

    def partial_census():
        return {
            "objects": len(seen), "edges": edges, "max_depth": max_depth,
            "max_stack": max_stack, "stream_bytes": emitted,
            "token_counts": dict(sorted(counts.items())),
            "limits": {name: getattr(limits, name) for name in Limits.__slots__},
            "partial": True,
        }

    try:
        while stack:
            frame = stack.pop()
            if frame[0] == "iter":
                _, iterator, depth, label = frame
                try:
                    edge_label, child = next(iterator)
                except StopIteration:
                    emit(b"E", label.encode("ascii"))
                    continue
                if depth + 1 > limits.depth:
                    raise FingerprintError("Fingerprint nesting exceeds depth bound")
                if len(stack) + 2 > limits.stack:
                    raise FingerprintError("Fingerprint traversal stack exceeds bound")
                add_edges(1)
                edge_size = _utf8_size(edge_label, limits)
                ensure_token_size(b"L", edge_size)
                edge_bytes = edge_label.encode("utf-8")
                push(("iter", iterator, depth, label))
                emit(b"L", edge_bytes)
                push(("visit", child, depth + 1))
                continue

            _, current, depth = frame
            if depth > limits.depth:
                raise FingerprintError("Fingerprint nesting exceeds depth bound")
            max_depth = max(max_depth, depth)
            kind = type(current)
            if current is None:
                emit(b"N")
            elif kind is bool:
                emit(b"B", b"1" if current else b"0")
            elif kind is int:
                ensure_token_size(b"I", _int_payload_size(current, limits))
                emit(b"I", _integer_bytes(current, limits))
            elif kind is float:
                if not math.isfinite(current):
                    raise FingerprintError("Non-finite float is not fingerprintable")
                ensure_token_size(b"F64", 8)
                emit(b"F64", struct.pack(">d", current))
            elif kind is str:
                size = _utf8_size(current, limits)
                ensure_token_size(b"S", size)
                raw = current.encode("utf-8")
                emit(b"S", raw)
            else:
                custom = _custom_fields(current)
                is_fraction = kind is Fraction
                if custom is None and not is_fraction and kind not in (
                        dict, list, tuple, set, frozenset):
                    raise FingerprintError(f"Unsupported exact type: {kind.__name__}")
                identity = id(current)
                if identity in seen:
                    ensure_token_size(b"R", 8)
                    emit(b"R", seen[identity].to_bytes(8, "big"))
                    continue
                if len(seen) + 1 > limits.objects:
                    raise FingerprintError("Fingerprint object count exceeds bound")
                prepared_set = None
                set_temp_bytes = 0
                set_stream_bytes = 0
                if custom is not None:
                    label, pairs = custom
                    child_count = len(pairs)
                    marker = b"D"
                    ensure_token_size(marker, 8 + len(label))
                    marker_payload = len(seen).to_bytes(8, "big") + label.encode("ascii")
                elif is_fraction:
                    if (current.numerator.bit_length() > limits.integer_bits or
                            current.denominator.bit_length() > limits.integer_bits):
                        raise FingerprintError("Fraction integer exceeds fingerprint bit bound")
                    child_count = 2
                    marker = b"Q"
                    ensure_token_size(marker, 8)
                    marker_payload = len(seen).to_bytes(8, "big")
                elif kind is dict:
                    child_count = len(current) * 2
                    marker = b"M"
                    ensure_token_size(marker, 16)
                    marker_payload = len(seen).to_bytes(8, "big") + len(current).to_bytes(8, "big")
                elif kind in (list, tuple):
                    child_count = len(current)
                    marker = b"A" if kind is list else b"T"
                    ensure_token_size(marker, 16)
                    marker_payload = len(seen).to_bytes(8, "big") + len(current).to_bytes(8, "big")
                else:
                    child_count = len(current)
                    marker = b"U" if kind is set else b"V"
                    ensure_token_size(marker, 16)
                    marker_payload = len(seen).to_bytes(8, "big") + len(current).to_bytes(8, "big")
                if edges + child_count > limits.edges:
                    raise FingerprintError("Fingerprint edge count exceeds bound")
                ensure_token(marker, marker_payload)
                if kind in (set, frozenset):
                    # Reserve count, output space, and temporary encoding space
                    # before creating even one member encoding or sorting buffer.
                    set_label = "set" if kind is set else "frozenset"
                    set_stream_bytes = _frame_size(_utf8_size(set_label, limits))
                    for index, item in enumerate(current):
                        set_temp_bytes += _atomic_size(item, limits)
                        set_stream_bytes += _atomic_output_size(item, index, limits)
                        if set_temp_bytes > limits.set_bytes:
                            raise FingerprintError("Set temporary encoding exceeds bound")
                        if emitted + len(marker) + 8 + len(marker_payload) + \
                                set_stream_bytes > limits.output_bytes:
                            raise FingerprintError("Set sort encodings exceed remaining output bound")
                    prepared_set = sorted((_atomic_bytes(item, limits), item) for item in current)
                ordinal = len(seen)
                seen[identity] = ordinal
                if custom is not None:
                    emit(b"D", ordinal.to_bytes(8, "big") + label.encode("ascii"))
                    iterator = iter(pairs)
                    push(("iter", iterator, depth, label))
                elif is_fraction:
                    emit(b"Q", ordinal.to_bytes(8, "big"))
                    pair = (("numerator", current.numerator),
                            ("denominator", current.denominator))
                    push(("iter", iter(pair), depth, "Fraction"))
                elif kind is dict:
                    emit(b"M", ordinal.to_bytes(8, "big") + len(current).to_bytes(8, "big"))
                    # Iterator keeps allocation constant and preserves insertion order.
                    def dict_pairs(mapping):
                        for index, (key, child) in enumerate(mapping.items()):
                            yield (f"k{index}", key)
                            yield (f"v{index}", child)
                    push(("iter", iter(dict_pairs(current)), depth, "dict"))
                elif kind in (list, tuple):
                    label = "list" if kind is list else "tuple"
                    emit(b"A" if kind is list else b"T",
                         ordinal.to_bytes(8, "big") + len(current).to_bytes(8, "big"))
                    push(("iter", ((str(i), child) for i, child in enumerate(current)),
                          depth, label))
                else:
                    encoded = prepared_set
                    label = "set" if kind is set else "frozenset"
                    emit(b"U" if kind is set else b"V",
                         ordinal.to_bytes(8, "big") + len(current).to_bytes(8, "big"))
                    push(("iter", ((str(i), item) for i, (_, item) in enumerate(encoded)),
                          depth, label))

    except FingerprintError as exc:
        exc.partial_census = partial_census()
        raise
    census = {
        "objects": len(seen), "edges": edges, "max_depth": max_depth,
        "max_stack": max_stack, "stream_bytes": emitted,
        "token_counts": dict(sorted(counts.items())),
        "limits": {name: getattr(limits, name) for name in Limits.__slots__},
    }
    return digest.hexdigest(), census
