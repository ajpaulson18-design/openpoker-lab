from contextlib import contextmanager
from copy import deepcopy
from fractions import Fraction
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import flop_second_board_cfrplus as adapter
from scripts import flop_second_board_cfrplus_budget as budget
from scripts import flop_second_board_equivalence as proof
from scripts import verify_flop_second_board_equivalence_publication as publication


def _rows():
    result = {}
    hands = {0: ("AdAs", "QdQs"), 1: ("AsKh", "KdKs")}
    for player, choices in hands.items():
        for hand in choices:
            for index in range(152):
                result[(player, hand, ("check", f"h{index}"))] = [0.5, 0.5]
    return result


class BinaryRowNormalizationTests(unittest.TestCase):
    def test_splits_608_rows_into_two_existing_helper_batches_without_mutation(self):
        raw = _rows()
        before = deepcopy(raw)
        normalized, receipt = adapter.canonicalize_binary_rows(raw)
        self.assertEqual(raw, before)
        self.assertEqual(len(normalized), 608)
        self.assertEqual(receipt["normalizer_batches"], 2)
        self.assertEqual(receipt["rows_per_batch"], [304, 304])
        self.assertEqual(receipt["grid_bits"], 52)
        self.assertTrue(all(sum(map(Fraction, row)) == 1 for row in normalized.values()))

    def test_uses_unchanged_policy_normalizer_twice(self):
        raw = _rows()
        from scripts import flop_class_policy
        original = flop_class_policy.canonicalize_binary_rows
        with patch.object(flop_class_policy, "canonicalize_binary_rows", wraps=original) as normalize:
            adapter.canonicalize_binary_rows(raw)
        self.assertEqual(normalize.call_count, 2)
        self.assertEqual([len(call.args[0]) for call in normalize.call_args_list], [304, 304])

    def test_rejects_bad_row_and_wrong_player_split_before_normalization(self):
        raw = _rows()
        bad = dict(raw)
        key = next(iter(bad))
        bad[key] = [True, 0.0]
        with patch("scripts.flop_class_policy.canonicalize_binary_rows") as normalize:
            with self.assertRaises(ValueError):
                adapter.canonicalize_binary_rows(bad)
            normalize.assert_not_called()

        only_zero = {key: value for key, value in raw.items() if key[0] == 0}
        with patch("scripts.flop_class_policy.canonicalize_binary_rows") as normalize:
            with self.assertRaises(ValueError):
                adapter.canonicalize_binary_rows(only_zero)
            normalize.assert_not_called()


class AdapterOrchestrationTests(unittest.TestCase):
    def setUp(self):
        self.zero_calls = {key: 0 for key in publication.AUTHORITY_KEYS}
        self.state = {"revision": "a" * 40, "status": "",
                      "source_lf_sha256": {f"source-{i}": f"{i:064x}" for i in range(54)}}
        self.model = SimpleNamespace(root=object(), worlds=tuple(), census={"synthetic": True},
                                     physical={"root": object(), "worlds": tuple()})
        self.rows = _rows()
        self.events = []
        self.train_calls = []

    def _common_patches(self):
        active_guards = {"count": 0}

        @contextmanager
        def guard():
            active_guards["count"] += 1
            try:
                yield dict(self.zero_calls)
            finally:
                active_guards["count"] -= 1

        def train(*args, **kwargs):
            self.events.append("train")
            self.train_calls.append((args, kwargs))
            self.assertEqual(active_guards["count"], 0)
            self.assertEqual(kwargs.get("delay"), 0)
            return self.rows

        exact = {key: Fraction(0) for key in proof.METRICS}
        exact["nash_conv"] = Fraction(1, 100)
        numeric = {key: float(value) for key, value in exact.items()}
        payload = {"strategy": [None] * budget.PHYSICAL_POLICY_ROWS}
        physical_rows = {index: None for index in range(budget.PHYSICAL_POLICY_ROWS)}
        projected_rows = adapter.canonicalize_binary_rows(self.rows)[0]
        return (
            patch.object(adapter, "admit_request", side_effect=lambda _t: (
                self.events.append("admit") or {"total_admitted_work": 1})),
            patch.object(adapter, "_source_snapshot", side_effect=[self.state, self.state]),
            patch.object(proof, "build_model", side_effect=lambda **kwargs: (
                self.events.append("build"),
                kwargs["progress"].update(prerequisite={"status": "reference-auth"}),
                self.model)[-1]),
            patch.object(adapter, "_training_inputs", return_value=(tuple(), self._infos(), 33)),
            patch.object(proof.shared, "independent_guard", guard),
            patch.object(adapter.cfr_plus, "train", side_effect=train),
            patch.object(proof, "_lift", return_value=payload),
            patch.object(proof, "_project", return_value=(projected_rows, physical_rows)),
            patch.object(proof.shared, "_exact_metrics", side_effect=[exact, exact]),
            patch.object(proof.physical, "replay", return_value=numeric),
            patch.object(proof, "validate_model", return_value={}),
            patch.object(proof, "_digest", return_value="d" * 64),
            patch.object(adapter.publication, "verify", side_effect=lambda: (
                self.events.append("saved-auth") or {"status": "saved-auth"})),
        )

    def _infos(self):
        return {key: 2 for key in self.rows}

    def test_source_hashes_extend_the_inherited_49_to_the_required_54_paths(self):
        inherited = {f"inherited-{i}": f"{i:064x}" for i in range(49)}
        with patch.object(evidence_module(), "_snapshot",
                          return_value={"revision": "b" * 40, "status": "",
                                        "source_lf_sha256": inherited}):
            hashes = adapter.source_hashes()
        self.assertEqual(len(hashes), 54)
        self.assertEqual(set(hashes) - set(inherited), {name for name, _path in adapter._EXTRA})
        self.assertTrue(all(len(value) == 64 for value in hashes.values()))

    def test_one_dynamic_train_call_outside_guards_and_completed_quality_miss_is_retained(self):
        with _entered(self._common_patches()):
            report = adapter.solve_second_board(560)
        self.assertEqual(report["status"], "trained-policy-physically-verified")
        self.assertIs(report["quality_target_met"], False)
        self.assertEqual(report["training_calls"], 1)
        self.assertEqual(report["preparation_forbidden_calls"], self.zero_calls)
        self.assertEqual(report["diagnostic_forbidden_calls"], self.zero_calls)
        self.assertEqual(report["audit"]["exact_metric_count"], 8)
        self.assertEqual(report["normalization"]["rows_per_batch"], [304, 304])
        self.assertEqual(len(self.train_calls), 1)
        self.assertEqual(self.train_calls[0][0][3], 560)
        self.assertEqual(self.train_calls[0][1]["delay"], 0)
        self.assertLess(self.events.index("admit"), self.events.index("saved-auth"))
        self.assertLess(self.events.index("saved-auth"), self.events.index("build"))
        self.assertLess(self.events.index("build"), self.events.index("train"))

    def test_invalid_request_stops_before_source_auth_or_training(self):
        with patch.object(budget, "_kernel_hashes", side_effect=AssertionError("source read")), \
             patch.object(adapter, "_source_snapshot", side_effect=AssertionError("snapshot")), \
             patch.object(proof, "build_model", side_effect=AssertionError("model")), \
             patch.object(adapter.cfr_plus, "train", side_effect=AssertionError("train")):
            observation = {}
            with self.assertRaises(ValueError):
                adapter.solve_second_board(True, observation=observation)
        self.assertEqual(observation["status"], "error")
        self.assertEqual(observation["training_calls"], 0)

    def test_budget_has_fixed_cap_and_rejects_aliases_before_kernel_hashing(self):
        forecast = budget.admit_second_board_request(560)
        self.assertEqual(forecast["requested_iterations"], 560)
        self.assertEqual(forecast["total_admitted_work"], 100_992_488)
        self.assertLessEqual(forecast["total_admitted_work"],
                             forecast["cap"]["maximum_total_admitted_logical_work"])
        with patch.object(budget, "_kernel_hashes", side_effect=AssertionError("hashing")) as hashes:
            for invalid in (True, False, 0, 561, 1.0, "1"):
                with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                    budget.admit_second_board_request(invalid)
            hashes.assert_not_called()

    def test_full_training_input_preflight_uses_170_worlds_608_rows_and_tree_hash(self):
        census = {
            "compact_public_states": 1270, "compact_decisions": 400,
            "compact_chance_nodes": 68, "compact_terminals": 802,
            "compact_worlds": 170, "compact_policy_rows": 608,
            "compact_action_slots": 1216, "physical_policy_rows": 16912,
            "physical_action_slots": 33824, "compact_tree_sha256": budget.COMPACT_TREE_SHA256,
        }
        worlds = tuple(("AdAs", "AsKh", Fraction(1, 170), 1,
                        ("7c", "8d", "9h", "Tc", "Jc")) for _ in range(170))
        model = SimpleNamespace(root=object(), worlds=worlds, census=census)
        nodes = {key: SimpleNamespace(actions=(None, None)) for key in self._infos()}
        with patch.object(proof, "validate_model", return_value=census), \
             patch.object(proof, "_class_rows", return_value=nodes):
            prepared_worlds, infos, max_visits = adapter._training_inputs(model)
        self.assertEqual(len(prepared_worlds), 170)
        self.assertEqual(len(infos), 608)
        self.assertEqual(max_visits, 1)
        self.assertEqual(sum(key[0] == 0 for key in infos), 304)
        self.assertEqual(sum(key[0] == 1 for key in infos), 304)

        bad = dict(census, compact_tree_sha256="0" * 64)
        with patch.object(proof, "validate_model", return_value=bad), \
             patch.object(proof, "_class_rows", return_value=nodes):
            with self.assertRaisesRegex(ValueError, "digest mismatch"):
                adapter._training_inputs(model)

    def test_training_input_rejects_zero_and_binary64_underflow_mass(self):
        census = {
            "compact_public_states": 1270, "compact_decisions": 400,
            "compact_chance_nodes": 68, "compact_terminals": 802,
            "compact_worlds": 170, "compact_policy_rows": 608,
            "compact_action_slots": 1216, "physical_policy_rows": 16912,
            "physical_action_slots": 33824, "compact_tree_sha256": budget.COMPACT_TREE_SHA256,
        }
        hands = ("AdAs", "AsKh", ("7c", "8d", "9h", "Tc", "Jc"))
        zero_worlds = tuple((hands[0], hands[1], Fraction(0), 1, hands[2])
                            for _ in range(170))
        tiny = Fraction(1, 10**1000)
        underflow_worlds = ((hands[0], hands[1], tiny, 1, hands[2]),) + tuple(
            (hands[0], hands[1], (1 - tiny) / 169, 1, hands[2]) for _ in range(169))
        nodes = {key: SimpleNamespace(actions=(None, None)) for key in self._infos()}
        for worlds in (zero_worlds, underflow_worlds):
            model = SimpleNamespace(root=object(), worlds=worlds, census=census)
            with patch.object(proof, "validate_model", return_value=census), \
                 patch.object(proof, "_class_rows", return_value=nodes):
                with self.assertRaises(ValueError):
                    adapter._training_inputs(model)

    def test_invalid_second_player_normalizer_key_rejects_before_either_batch(self):
        raw = _rows()
        bad_key = next(key for key in reversed(raw) if key[0] == 1)
        values = raw.pop(bad_key)
        raw[(1, "AsKhXX", bad_key[2])] = values
        with patch("scripts.flop_class_policy.canonicalize_binary_rows") as normalize:
            with self.assertRaises(ValueError):
                adapter.canonicalize_binary_rows(raw)
            normalize.assert_not_called()

    def test_preparation_failure_exits_guard_and_does_not_train(self):
        patches = list(self._common_patches())
        patches[2] = patch.object(proof, "build_model", side_effect=RuntimeError("build failed"))
        patches[5] = patch.object(adapter.cfr_plus, "train", side_effect=AssertionError("train called"))
        with _entered(patches):
            observation = {}
            with self.assertRaisesRegex(RuntimeError, "build failed"):
                adapter.solve_second_board(560, observation=observation)
        self.assertEqual(observation["preparation_forbidden_calls"], self.zero_calls)
        self.assertEqual(observation["training_calls"], 0)

    def test_real_authority_guard_merges_all_41_counters_after_suppressed_failure(self):
        patches = list(self._common_patches())
        real_guard = proof.shared.independent_guard
        patches[2] = patch.object(proof, "build_model", side_effect=RuntimeError("synthetic build failure"))
        patches[4] = patch.object(proof.shared, "independent_guard", real_guard)
        patches[5] = patch.object(adapter.cfr_plus, "train", side_effect=AssertionError("trainer called"))
        with _entered(patches):
            observation = {}
            with self.assertRaisesRegex(RuntimeError, "synthetic build failure"):
                adapter.solve_second_board(560, observation=observation)
        self.assertEqual(set(observation["preparation_forbidden_calls"]), set(publication.AUTHORITY_KEYS))
        self.assertTrue(all(type(value) is int and value == 0
                            for value in observation["preparation_forbidden_calls"].values()))
        self.assertEqual(observation["training_calls"], 0)

    def test_observed_dimension_rejection_stops_before_train(self):
        patches = list(self._common_patches())
        patches[3] = patch.object(adapter, "_training_inputs",
                                  side_effect=ValueError("wrong census/hash/path"))
        patches[5] = patch.object(adapter.cfr_plus, "train",
                                  side_effect=AssertionError("trainer called"))
        with _entered(patches):
            observation = {}
            with self.assertRaisesRegex(ValueError, "wrong census"):
                adapter.solve_second_board(560, observation=observation)
        self.assertEqual(observation["training_calls"], 0)
        self.assertEqual(observation["preparation_forbidden_calls"], self.zero_calls)
        self.assertEqual(observation["final_model_validation"], "passed")

    def test_policy_shape_failure_keeps_raw_rows_and_runs_cleanup_validation(self):
        patches = list(self._common_patches())
        patches[5] = patch.object(adapter.cfr_plus, "train", return_value={})
        with _entered(patches) as stack:
            validate = stack.enter_context(patch.object(proof, "validate_model", return_value={}))
            observation = {}
            with self.assertRaisesRegex(ValueError, "omits or adds"):
                adapter.solve_second_board(560, observation=observation)
        self.assertEqual(observation["training_calls"], 1)
        self.assertEqual(observation["raw_class_policy"], [])
        validate.assert_called_once_with(self.model)

    def test_oversized_or_nonfinite_raw_rows_are_retained_with_safe_receipt(self):
        patches = list(self._common_patches())
        extra = (0, "AdAs", ("extra",))
        large = dict(self.rows)
        large[extra] = [0.5, 0.5]
        patches[5] = patch.object(adapter.cfr_plus, "train", return_value=large)
        with _entered(patches):
            observation = {}
            with self.assertRaisesRegex(ValueError, "omits or adds"):
                adapter.solve_second_board(560, observation=observation)
        self.assertEqual(observation["raw_class_policy"]["reported_rows"], 609)
        self.assertIs(observation["raw_class_policy"]["complete_policy_retained"], False)
        self.assertEqual(observation["training_calls"], 1)

        malformed = dict(self.rows)
        malformed[next(iter(malformed))] = [float("nan"), 0.5]
        patches = list(self._common_patches())
        patches[5] = patch.object(adapter.cfr_plus, "train", return_value=malformed)
        with _entered(patches):
            observation = {}
            with self.assertRaisesRegex(ValueError, "malformed"):
                adapter.solve_second_board(560, observation=observation)
        first_values = observation["raw_class_policy"][0][1]
        self.assertEqual(first_values[0], "nan")
        self.assertEqual(observation["status"], "error")

    def test_numeric_gap_rejection_runs_cleanup_and_preserves_observed_exact_metrics(self):
        patches = list(self._common_patches())
        patches[9] = patch.object(proof.physical, "replay",
                                  return_value={key: (1e-4 if key == "nash_conv" else 0.0)
                                                for key in proof.METRICS})
        with _entered(patches) as stack:
            validate = stack.enter_context(patch.object(proof, "validate_model", return_value={}))
            observation = {}
            with self.assertRaisesRegex(ValueError, "Numeric physical replay"):
                adapter.solve_second_board(560, observation=observation)
        self.assertEqual(observation["exact_compact_metrics"]["nash_conv"], "1/100")
        self.assertEqual(observation["exact_physical_metrics"]["nash_conv"], "1/100")
        validate.assert_called_once_with(self.model)

    def test_training_error_still_runs_final_validation_and_preserves_raw_exception(self):
        patches = list(self._common_patches())
        train_error = RuntimeError("trainer failed")
        patches[5] = patch.object(adapter.cfr_plus, "train", side_effect=train_error)
        with _entered(patches) as stack:
            validate = stack.enter_context(patch.object(proof, "validate_model", return_value={}))
            observation = {}
            with self.assertRaises(RuntimeError) as caught:
                adapter.solve_second_board(560, observation=observation)
        self.assertIs(caught.exception, train_error)
        validate.assert_called_once_with(self.model)
        self.assertEqual(observation["training_calls"], 1)
        self.assertEqual(observation["final_model_validation"], "passed")
        self.assertEqual(observation["status"], "error")


class _entered:
    def __init__(self, patches):
        self.patches = patches
        self.stack = None

    def __enter__(self):
        from contextlib import ExitStack
        self.stack = ExitStack()
        for item in self.patches:
            self.stack.enter_context(item)
        return self.stack

    def __exit__(self, *args):
        return self.stack.__exit__(*args)


def evidence_module():
    return adapter.evidence


if __name__ == "__main__":
    unittest.main()
