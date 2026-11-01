"""Reduce-only resource accounting for the opt-in exact certificate.

Fraction bit forecasting is cumulative, not an estimate of RSS or all CPython
integer allocations. Each Fraction input and operation reserves conservative
operand/intermediate/output bit widths before the operation. Structural integers
and JSON are bounded separately by the caller.
"""
from fractions import Fraction
from math import isfinite

DEFAULT_LIMITS = {'work': 500_000_000, 'entries': 8_000_000,
                  'integer_bits': 65_536, 'created_bits': 16_000_000_000}

class Budget:
    def __init__(self, limits=None):
        if limits is not None and (type(limits) is not dict or len(limits) > len(DEFAULT_LIMITS)):
            raise ValueError('limits must be a bounded plain mapping')
        limits = {} if limits is None else dict(limits)
        if set(limits) - set(DEFAULT_LIMITS):
            raise ValueError('unknown certificate budget limit')
        self.limits = dict(DEFAULT_LIMITS)
        for key, value in limits.items():
            if type(value) is not int or not 0 < value <= DEFAULT_LIMITS[key]:
                raise ValueError('limits must be positive and reduce-only')
            self.limits[key] = value
        self.work = self.logical_entries = self.created_bits = self.max_forecast_bits = 0
        self.counters = {}

    def charge(self, kind, n=1):
        if type(kind) is not str or not kind.isascii() or not 0 < len(kind) <= 64 or type(n) is not int or n < 0:
            raise ValueError('invalid work charge')
        if self.work + n > self.limits['work']:
            raise ValueError('certificate work limit exceeded')
        if kind not in self.counters:
            if len(self.counters) >= 256:
                raise ValueError('certificate counter-family limit exceeded')
            self.entries(2, 'counter metadata')
        self.work += n
        self.counters[kind] = self.counters.get(kind, 0) + n

    def entries(self, n, label):
        if type(n) is not int or n < 0:
            raise ValueError('invalid entry charge')
        if self.logical_entries + n > self.limits['entries']:
            raise ValueError(f'{label}: certificate entry limit exceeded')
        self.logical_entries += n

    def _reserve(self, sizes, label):
        largest = max((1, *sizes))
        if largest > self.limits['integer_bits']:
            raise ValueError(f'{label}: certificate integer bit limit exceeded')
        amount = sum(max(1, size) for size in sizes)
        if self.created_bits + amount > self.limits['created_bits']:
            raise ValueError(f'{label}: certificate cumulative integer bit limit exceeded')
        self.charge('fraction_operations')
        self.created_bits += amount
        self.max_forecast_bits = max(self.max_forecast_bits, largest)

    def input(self, value, label):
        if type(value) is float:
            if not isfinite(value):
                raise ValueError(f'{label}: finite value required')
            # binary64 as_integer_ratio is bounded before allocation by 1075 bits.
            self._reserve((1075, 1075), label)
            return Fraction.from_float(value)
        if type(value) is int:
            self._reserve((max(1, value.bit_length()), 1), label)
            return Fraction(value)
        if type(value) is Fraction:
            self._reserve((max(1, value.numerator.bit_length()), value.denominator.bit_length()), label)
            return value
        raise ValueError(f'{label}: expected int, finite float or Fraction')

    @staticmethod
    def _sizes(a):
        if type(a) is not Fraction:
            raise TypeError('budget operands must be Fraction snapshots')
        return max(1, a.numerator.bit_length()), a.denominator.bit_length()

    def _binary(self, a, b, label, op):
        an, ad = self._sizes(a); bn, bd = self._sizes(b)
        if op in ('add', 'sub'):
            x, y, d = an + bd, bn + ad, ad + bd
            self._reserve((x, y, max(x, y) + 1, d, max(x, y) + 1, d), label)
            return a + b if op == 'add' else a - b
        if op == 'div' and not b:
            raise ZeroDivisionError(label)
        n, d = (an + bn, ad + bd) if op == 'mul' else (an + bd, ad + bn)
        self._reserve((n, d, n, d), label)
        return a * b if op == 'mul' else a / b

    def add(self, a, b, label): return self._binary(a, b, label, 'add')
    def sub(self, a, b, label): return self._binary(a, b, label, 'sub')
    def mul(self, a, b, label): return self._binary(a, b, label, 'mul')
    def div(self, a, b, label): return self._binary(a, b, label, 'div')
    def compare(self, a, b, label):
        an, ad = self._sizes(a); bn, bd = self._sizes(b)
        self._reserve((an + bd, bn + ad), label)
        left = a.numerator * b.denominator
        right = b.numerator * a.denominator
        return (left > right) - (left < right)
    def neg(self, a, label):
        n, d = self._sizes(a)
        self._reserve((n, d), label)
        return -a
    def receipt(self):
        return {'limits': dict(self.limits), 'work': self.work, 'entries': self.logical_entries,
                'created_bits': self.created_bits, 'max_forecast_bits': self.max_forecast_bits,
                'counters': dict(self.counters)}
