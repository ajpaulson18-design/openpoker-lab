"""Explicit, strict binary64 boundary for the exact-product selected game.

This solve-local adapter supplies the existing shared CFR/diagnostics callback
shape. It does not select a solver or change legacy chance/payoff behavior.
Final policy quality still requires independent exact-game certification.
"""
from fractions import Fraction
from math import isfinite
from sys import float_info
from types import MappingProxyType

from .exact_selected_kernel import ExactSelectedRunoutKernel
from .river_tree import _Terminal
from .shared_public_topology import TerminalVertex
from .shared_topology_view import SharedPublicView

CONVERSION_CONTRACT = "exact-product-vectors-binary64-v1"
MAX_ADAPTER_WORK = 500_000_000
MAX_ADAPTER_STORAGE = 2_000_000


class ExactSelectedFloatAdapter:
    """Round each completed exact marginal/value component once.

    Original admitted terminal scales are snapshotted directly. Recovering an
    amount by subtracting and adding a positive-pot anchor is not assumed exact.
    No root correction is added after using the original whole-hand payoff.
    """
    def __init__(self, kernel, view, *, max_work=MAX_ADAPTER_WORK,
                 max_storage=MAX_ADAPTER_STORAGE):
        if type(kernel) is not ExactSelectedRunoutKernel or type(view) is not SharedPublicView:
            raise TypeError("Exact float adaptation requires its kernel and admitted shared view")
        if type(max_work) is not int or not 0 < max_work <= MAX_ADAPTER_WORK:
            raise ValueError("Invalid exact-adapter work limit")
        if type(max_storage) is not int or not 0 < max_storage <= MAX_ADAPTER_STORAGE:
            raise ValueError("Invalid exact-adapter storage limit")
        self.kernel, self.view = kernel, view
        self._max_work, self._max_storage = max_work, max_storage
        self._work = self._calls = self._conversions = self._rejections = 0
        self._temporary_peak = 0
        self._topology = view.topology
        self._vertices, self._terminals = view.topology.vertices, view._terminals
        self._anchor = view.anchor.hex()
        self._hands, self._weights = kernel.hands, kernel.weights
        self._selected, self._normalizer = kernel.selected, kernel.normalizer
        self.hand_counts = tuple(kernel.hand_counts)
        self._retained = 0
        # Reserve a conservative complete vertex/mapping snapshot before growing it.
        proposed = 8 * len(self._vertices) + 2 * sum(self.hand_counts) + 16
        self._reserve(8 * len(self._vertices) + 8, proposed)
        if len(self._terminals) != len(self._vertices):
            raise ValueError("Exact adapter view/vertex count mismatch")
        records = {}
        for index, vertex in enumerate(self._vertices):
            node = self._terminals[index]
            if not isinstance(vertex, TerminalVertex):
                if node is not None:
                    raise ValueError("Nonterminal vertex has a terminal snapshot")
                continue
            if type(node) is not _Terminal or node.kind != vertex.kind or node.winner != vertex.winner:
                raise ValueError("Exact adapter terminal identity mismatch")
            if len(vertex.contributions) != 2 or any(type(x) not in (int, float) or
                    not isfinite(x) or x < 0 for x in vertex.contributions):
                raise ValueError("Invalid original terminal contributions")
            if vertex.kind not in ("fold", "showdown") or (vertex.kind == "fold" and
                    (type(vertex.winner) is not int or vertex.winner not in (0, 1))) or (
                    vertex.kind == "showdown" and vertex.winner is not None):
                raise ValueError("Invalid original terminal kind/winner")
            scale = float(min(vertex.contributions))
            if not isfinite(scale) or abs(scale) > 1e12:
                raise ValueError("Original terminal scale exceeds adapter envelope")
            if vertex.kind == "fold" and vertex.winner == 1:
                scale = -scale
            if id(node) in records:
                raise ValueError("Terminal object aliases different admitted vertices")
            # Keeping node itself strongly prevents id reuse. Policy rows never use this map.
            records[id(node)] = (node, vertex.kind, Fraction.from_float(scale))
        self._records = MappingProxyType(records)
        self._retained = 8 * len(records) + 2 * sum(self.hand_counts) + 16
        self._assert_snapshot()

    def _reserve(self, work, temporary=0):
        if self._work + work > self._max_work or self._retained + temporary > self._max_storage:
            self._rejections += 1
            raise ValueError("Exact float-adapter work/storage admission rejected")
        self._work += work
        self._temporary_peak = max(self._temporary_peak, temporary)

    def _assert_snapshot(self):
        if (self.view.topology is not self._topology or self.view.topology.vertices is not self._vertices or
                self.view._terminals is not self._terminals or type(self.view.anchor) is not float or
                self.view.anchor.hex() != self._anchor or
                self.kernel.hands is not self._hands or self.kernel.weights is not self._weights or
                self.kernel.selected is not self._selected or self.kernel.normalizer is not self._normalizer or
                tuple(self.kernel.hand_counts) != self.hand_counts):
            self._rejections += 1
            raise ValueError("Exact float-adapter source/view changed after admission")

    def _convert(self, value, *, marginal=False):
        if type(value) is not Fraction or (marginal and value < 0):
            raise TypeError("Exact adapter components must be valid exact Fractions")
        self._conversions += 1
        if value == 0:
            return 0.0
        try:
            result = float(value)
        except (OverflowError, ValueError) as exc:
            self._rejections += 1
            raise ValueError("Exact component cannot be represented as finite normal binary64") from exc
        if not isfinite(result) or abs(result) < float_info.min:
            self._rejections += 1
            raise ValueError("Nonzero exact component converts to zero/subnormal/nonfinite binary64")
        return result

    def joint_marginals(self, prefix=()):
        self._reserve(8 + 4 * sum(self.hand_counts), 2 * sum(self.hand_counts))
        self._assert_snapshot()
        self._calls += 1
        exact = self.kernel.joint_marginals_exact(prefix)
        if len(exact) != 2 or tuple(map(len, exact)) != self.hand_counts:
            raise ValueError("Exact marginal dimension mismatch")
        return tuple(tuple(self._convert(value, marginal=True) for value in side) for side in exact)

    def values(self, node, opponent_reach, target_player, prefix=()):
        self._reserve(8 + 4 * sum(self.hand_counts), 2 * sum(self.hand_counts))
        self._assert_snapshot()
        self._calls += 1
        record = self._records.get(id(node))
        if record is None or record[0] is not node:
            self._rejections += 1
            raise ValueError("Foreign/stale terminal is outside the admitted exact view")
        if type(target_player) is not int or target_player not in (0, 1):
            raise ValueError("Exact adapter target player must be 0 or 1")
        _retained_node, kind, payoff = record
        exact = self.kernel.terminal_values_exact(prefix, kind=kind, payoff=payoff,
                    player=target_player, opponent_reach=opponent_reach)
        if len(exact) != self.hand_counts[target_player]:
            raise ValueError("Exact terminal vector dimension mismatch")
        return [self._convert(value) for value in exact]

    def receipt(self):
        return {"conversion_contract": CONVERSION_CONTRACT, "calls": self._calls,
                "conversions": self._conversions, "rejections": self._rejections,
                "modeled_work_entries": self._work, "work_limit": self._max_work,
                "retained_mapping_entries": self._retained,
                "temporary_peak_entries": self._temporary_peak,
                "entry_limit": self._max_storage, "unique_terminal_objects": len(self._records),
                "scope": "Once-per-component rounding of completed exact queries; approximate binary64 CFR trajectory, final policy quality requires independent exact-game certification. Logical entries are not CPU/allocator/RSS bounds."}
