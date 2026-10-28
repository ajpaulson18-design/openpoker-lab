"""Focused tests for the unquotiented suit-equivariant packed CFR+ reference."""
from dataclasses import replace
import json
import gc
from pathlib import Path
import unittest
import weakref
from unittest.mock import patch
from array import array as python_array

from pokerlab.cards import DECK, expand_range
from pokerlab.direct_shared_topology import DecisionVertex
from pokerlab.equivariant_packed_cfr import (
    NUMERICAL_REDUCTION, _finite, _sorted_chance_sum, equivariant_additional_census,
    equivariant_layout_census, train_equivariant_packed,
)
from pokerlab import equivariant_packed_cfr as equivariant_module
from pokerlab.exact_selected_solver import _OnePrefixMarginals, _prepare_exact_selected, _revealed_board, _tokens
from pokerlab.shared_topology_view import layout_census_shared
from tests.test_exact_selected_solver import request_from_case


ROOT = Path(__file__).resolve().parents[1]


def _request():
    case = json.loads((ROOT / "benchmarks/four-street-integration-v1.json").read_text(encoding="utf-8"))["case"]
    return request_from_case(case)


def _suit_map_request(request):
    mapping = {"c": "d", "d": "c", "h": "h", "s": "s"}
    def card(token):
        return token[0] + mapping[token[1]]
    def range_text(text):
        rows = []
        for token in text.split(","):
            hand, separator, weight = token.partition(":")
            rows.append(card(hand[:2]) + card(hand[2:]) + (separator + weight if separator else ""))
        return ",".join(rows)
    return replace(request, sb_range=range_text(request.sb_range),
        bb_range=range_text(request.bb_range),
        runouts=tuple("".join(card(runout[i:i+2]) for i in range(0, 10, 2))
                      for runout in request.runouts))


def _train(request):
    prepared = _prepare_exact_selected(request, pair_diagnostics="compact")
    kernel, topology, view, adapter = (prepared.kernel, prepared.topology,
                                       prepared.view, prepared.adapter)
    legal = {prefix: kernel.legal_hands(prefix) for prefix in prepared.unique_prefixes}
    infos = {}
    for occurrence in topology.iter_occurrences():
        vertex = topology.vertices[occurrence.vertex_id]
        if not isinstance(vertex, DecisionVertex):
            continue
        prefix = _tokens(_revealed_board(occurrence.history))
        for hand in sorted(legal[prefix][vertex.player]):
            infos[(vertex.player, hand, occurrence.history)] = len(vertex.actions)
    legal.clear()
    marginals = _OnePrefixMarginals(adapter)
    try:
        policy, receipt = train_equivariant_packed(view.root, infos, request.iterations,
            operator=adapter, marginals=marginals, return_receipt=True, shared_view=view)
        return policy, receipt, kernel, infos
    except BaseException:
        kernel.clear_rank_cache()
        raise
    finally:
        marginals = None


def _mapped_history(history):
    mapping = {"c": "d", "d": "c", "h": "h", "s": "s"}
    def map_card(token):
        return token[0] + mapping[token[1]]
    result = []
    for token in history:
        if token.startswith("flop@"):
            cards = [map_card(token[i:i+2]) for i in (5, 7, 9)]
            cards.sort(key=DECK.index)
            result.append("flop@" + "".join(cards))
        elif token.startswith(("turn@", "river@")):
            result.append(token[:token.index("@") + 1] + map_card(token[token.index("@") + 1:]))
        else:
            result.append(token)
    return tuple(result)


class EquivariantPackedCFRTests(unittest.TestCase):
    def test_finite_canonical_zero_and_subnormal_contract(self):
        self.assertEqual(_finite(-0.0, "test").hex(), 0.0.hex())
        smallest = float.fromhex("0x0.0000000000001p-1022")
        self.assertEqual(_finite(smallest, "test").hex(), smallest.hex())
        for value in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "finite binary64"):
                _finite(value, "test")

    def test_sorted_chance_reduction_is_permutation_invariant_and_checks_before_sort(self):
        vectors = [[1e16, -0.0, 0.25], [-1e16, 1.0, 0.5], [1.0, -0.0, -0.75]]
        expected = _sorted_chance_sum(vectors, 3)
        for permutation in (vectors, list(reversed(vectors)), [vectors[1], vectors[2], vectors[0]]):
            self.assertEqual([x.hex() for x in _sorted_chance_sum(permutation, 3)],
                             [x.hex() for x in expected])
        with self.assertRaisesRegex(ValueError, "finite binary64"):
            _sorted_chance_sum([[float("nan")]], 1)

    def test_layout_adds_separate_work_and_nested_scratch_caps(self):
        prepared = _prepare_exact_selected(_request(), pair_diagnostics="compact")
        legal = {prefix: prepared.kernel.legal_hands(prefix) for prefix in prepared.unique_prefixes}
        infos = {}
        for occurrence in prepared.topology.iter_occurrences():
            vertex = prepared.topology.vertices[occurrence.vertex_id]
            if isinstance(vertex, DecisionVertex):
                prefix = _tokens(_revealed_board(occurrence.history))
                for hand in legal[prefix][vertex.player]:
                    infos[(vertex.player, hand, occurrence.history)] = len(vertex.actions)
        old = layout_census_shared(prepared.view, infos, prepared.kernel.hand_counts, 10)
        new = equivariant_layout_census(prepared.view, infos, prepared.kernel.hand_counts, 10)
        self.assertEqual(new["version"], old["version"])
        self.assertEqual(new["information_sets"], old["information_sets"])
        self.assertEqual(new["action_slots"], old["action_slots"])
        self.assertEqual(new["requested_layout_loop_entries"], old["requested_layout_loop_entries"])
        self.assertEqual(new["numerical_reduction"], NUMERICAL_REDUCTION)
        admission = new["equivariant_additional_admission"]
        with patch("pokerlab.equivariant_packed_cfr.layout_census_shared",
                   side_effect=AssertionError("extra preflight inspected information rows")):
            pre_rows = equivariant_additional_census(prepared.view, prepared.kernel.hand_counts, 10)
        self.assertEqual(pre_rows, admission)
        self.assertGreater(admission["maximum_chance_degree"], 0)
        self.assertEqual(admission["reduction_work_upper"],
            admission["target_passes"] * (admission["sort_component_work_upper"] +
                                           8 * admission["child_component_work_upper"]))
        self.assertEqual(admission["scalar_validation_work_upper"],
            64 * 10 * (admission["dense_action_slots_upper"] +
                sum(prepared.kernel.hand_counts) * (admission["decision_width_upper"] +
                                                      admission["logical_visits_upper"])) +
            32 * admission["dense_action_slots_upper"] + 32 * admission["logical_visits_upper"])
        self.assertEqual(admission["setup_work_upper"],
            4 * admission["logical_occurrences_scanned"] +
            admission["history_token_entries_scanned"] +
            2 * admission["chance_branch_occurrences"] +
            4 * admission["decision_occurrences"])
        self.assertGreaterEqual(admission["per_depth_scratch_entries_upper"],
                                admission["maximum_logical_depth_frames"] *
                                admission["maximum_chance_degree"] *
                                admission["maximum_hand_dimension"])
        self.assertLessEqual(admission["modeled_work_upper"], admission["modeled_work_limit"])
        self.assertLessEqual(admission["additional_retained_entries_upper"],
                             admission["additional_retained_entries_limit"])
        prepared.kernel.clear_rank_cache()

    def test_packed_numeric_arrays_release_with_gc_disabled_on_all_exit_paths(self):
        prior_gc = gc.isenabled()
        gc.disable()
        try:
            for failure in (None, "array", "traversal"):
                refs = []
                calls = []
                class TrackedArray(python_array):
                    def __mul__(self, count):
                        value = super().__mul__(count)
                        refs.append(weakref.ref(value))
                        return value
                def factory(*args, **kwargs):
                    calls.append(args[0] if args else None)
                    if failure == "array" and len(calls) == 5:
                        raise MemoryError("controlled packed buffer allocation failure")
                    return TrackedArray(*args, **kwargs)
                caught = None
                with patch.object(equivariant_module, "array", side_effect=factory):
                    if failure == "traversal":
                        with patch.object(equivariant_module, "_sorted_chance_sum",
                                          side_effect=RuntimeError("controlled traversal failure")):
                            try:
                                _train(_request())
                            except RuntimeError as exc:
                                caught = exc
                    elif failure == "array":
                        try:
                            _train(_request())
                        except MemoryError as exc:
                            caught = exc
                    else:
                        _policy, _receipt, kernel, _infos = _train(_request())
                        kernel.clear_rank_cache()
                with self.subTest(failure=failure):
                    if failure is None:
                        self.assertIsNone(caught)
                    else:
                        self.assertIsNotNone(caught)
                    self.assertTrue(refs)
                    self.assertTrue(all(reference() is None for reference in refs))
        finally:
            if prior_gc:
                gc.enable()
            else:
                gc.disable()

    def test_shared_exact_trainer_and_suit_mapped_game_have_identical_row_bits(self):
        request = _request()
        mapped_request = _suit_map_request(request)
        policy, receipt, kernel, infos = _train(request)
        mapped_policy, mapped_receipt, mapped_kernel, mapped_infos = _train(mapped_request)
        self.assertEqual(receipt["numerical_reduction"], NUMERICAL_REDUCTION)
        self.assertEqual(receipt["equivariant_additional_admission"],
                         mapped_receipt["equivariant_additional_admission"])
        mapped = {(player, hand, _mapped_history(history)): values
                  for (player, hand, history), values in mapped_policy.items()}
        self.assertEqual(set(policy), set(mapped))
        for key in policy:
            self.assertEqual([value.hex() for value in policy[key]],
                             [value.hex() for value in mapped[key]], key)
        mapped_info_keys = {(player, hand, _mapped_history(history))
                            for (player, hand, history) in mapped_infos}
        self.assertEqual(set(infos), mapped_info_keys)
        kernel.clear_rank_cache()
        mapped_kernel.clear_rank_cache()

    def test_common_tiny_weight_scale_matches_unit_scale_policy_bits(self):
        request = _request()
        def weighted(text, weight):
            return ",".join("".join(hand) + ":" + weight for hand in
                             expand_range(text))
        tiny = replace(request, sb_range=weighted(request.sb_range, "1e-200"),
                       bb_range=weighted(request.bb_range, "1e-200"))
        unit = replace(request, sb_range=weighted(request.sb_range, "1"),
                       bb_range=weighted(request.bb_range, "1"))
        tiny_policy, _tiny_receipt, tiny_kernel, _ = _train(tiny)
        unit_policy, _unit_receipt, unit_kernel, _ = _train(unit)
        self.assertEqual(set(tiny_policy), set(unit_policy))
        for key in tiny_policy:
            self.assertEqual([value.hex() for value in tiny_policy[key]],
                             [value.hex() for value in unit_policy[key]], key)
        tiny_kernel.clear_rank_cache()
        unit_kernel.clear_rank_cache()


if __name__ == "__main__":
    unittest.main()
