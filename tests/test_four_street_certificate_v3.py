"""Independent acceptance controls for the fixed v3 exact certificate."""
from copy import deepcopy
from fractions import Fraction
import json
from pathlib import Path
from types import SimpleNamespace
import unittest

from scripts import four_street_certificate as certificate_v2
from scripts import four_street_certificate_v3 as certificate_v3
from scripts import four_street_expansion_preflight as expansion
from scripts import four_street_validation as validation
from tests.test_four_street_certificate import (
    _case, _payload, _check_call, _bb_no_bluff,
    _independent_exact_profile, _assert_family_schedule,
)
from tests.test_four_street_certificate_operator_seam import PINS, _pinned_bytes


ROOT = Path(__file__).resolve().parents[1]
V3_PROJECTION = (
    "schema_version", "model_sha256", "input_case_canonical_sha256",
    "input_policy_canonical_sha256", "normalized_policy_sha256", "metrics",
    "threshold", "threshold_met", "normalization_ledger", "normalized_policy_rows",
    "maximum_row_adjustment", "floating_comparison", "floating_replay",
    "depth_limit", "fraction_bit_limit", "work_limit",
)


def _fraction(value):
    return Fraction(value)


def _exact_row_expectations(payload):
    """Independent binary64-to-rational normalization and individual adjustment."""
    rows = []
    maximum = Fraction(0)
    for row in payload["strategy"]:
        raw = [Fraction.from_float(float(action["probability"]))
               for action in row["actions"]]
        total = sum(raw, Fraction(0))
        normalized = [value / total for value in raw]
        adjustments = [after - before for before, after in zip(raw, normalized)]
        maximum = max(maximum, *(abs(value) for value in adjustments))
        rows.append((row, raw, normalized, adjustments, total))
    return rows, maximum


def _normalized_payload(model, mode):
    payload = _payload(model, _check_call)
    for row in payload["strategy"]:
        actions = row["actions"]
        n = len(actions)
        if mode == "mixed":
            values = [0.25, 0.5, 0.25 + 1e-16] if n == 3 else [0.25, 0.75 + 1e-16]
        elif mode == "zero":
            values = [1.0] + [0.0] * (n - 1)
        elif mode == "subnormal":
            values = [5e-324, 1.0] + [0.0] * (n - 2)
        else:
            raise AssertionError(mode)
        for action, value in zip(actions, values):
            action["probability"] = value
    return payload


def _literal_terminal(node, group):
    matched = min(node.contributions)
    total = Fraction(0)
    for world, mass in group:
        sign = (1 if node.winner == 0 else -1) if node.kind == "fold" else world["sign"]
        payoff = float(sign) * float(matched)
        total += mass * Fraction.from_float(payoff)
    return total


def _assert_terminal_census(testcase, preparation):
    receipt = preparation["terminal_group_census"]
    expected = {
        "groups": 3015, "entries": 6760, "tie_only_groups": 228,
        "zero_sign_entries": 520, "nonzero_groups": 2787,
        "nonzero_entries": 6240, "signed_add_subtract_operations": 3453,
        "payoff_conversions": 2787, "payoff_multiplications": 2787,
    }
    testcase.assertTrue(receipt["admitted"])
    for key, value in expected.items():
        testcase.assertEqual(receipt[key], value, key)
    testcase.assertEqual(receipt["work"], sum(receipt["work_by_kind"].values()))
    testcase.assertEqual(set(receipt["work_by_kind"]), {
        "setup_entries", "group_frame_entries", "world_reference_entries", "output_entries"})
    testcase.assertLessEqual(receipt["work"], receipt["work_limit"])
    testcase.assertLessEqual(receipt["work"], 8_000_000)
    graph = preparation["structural_graph_validation"]
    testcase.assertEqual(graph["entry_limit"], 8_000_000)
    testcase.assertLessEqual(
        graph["total_entries_upper_bound"] + receipt["work"], graph["entry_limit"])


FORECAST_CORE = (
    "work", "work_limit", "admitted", "excess_work", "work_by_kind",
    "tree_nodes", "tree_decisions", "tree_depth", "worlds", "information_rows",
    "action_slots", "maximum_depth", "maximum_fraction_bits",
)


def _forecast_core(forecast):
    return {key: forecast[key] for key in FORECAST_CORE}


class FourStreetCertificateV3AcceptanceTests(unittest.TestCase):
    def test_v3_source_and_schedule_are_fixed(self):
        self.assertEqual(certificate_v3.SOURCE_IDENTITY,
                         "four-street-independent-exact-v3")
        self.assertEqual(certificate_v3.BUDGET_SCHEDULE_VERSION,
                         "four-street-exact-work-v3")
        self.assertEqual(certificate_v3.MAX_EXACT_WORK, 100_000)
        self.assertEqual(certificate_v3.MAX_FRACTION_BITS, 65_536)

    def test_terminal_signed_operator_matches_literal_per_world_arithmetic(self):
        observed = certificate_v2._ObservedBudget(100_000, 32, 65_536)
        node = SimpleNamespace(kind="showdown", contributions=(Fraction(1, 3), Fraction(1, 2)),
                               winner=None)
        groups = (
            # All signs, ties, cancellation through zero, then additional mass.
            (({"sign": 1}, Fraction(1, 7)), ({"sign": 0}, Fraction(2, 7)),
             ({"sign": -1}, Fraction(1, 7)), ({"sign": 1}, Fraction(1, 5))),
            (({"sign": 0}, Fraction(1)),),
            (),
            (({"sign": 1}, Fraction(0)),),
        )
        for group in groups:
            with self.subTest(group=group):
                expected = _literal_terminal(node, group)
                actual = certificate_v3._terminal_group_signed(
                    node, group, observed, "test contribution", "test sum")
                self.assertEqual(actual, expected)

        # Finite tie-only groups must yield exact zero.
        self.assertEqual(certificate_v3._terminal_group_signed(
            node, (({"sign": 0}, Fraction(1)),),
            certificate_v2._ObservedBudget(100_000, 32, 65_536),
            "tie contribution", "tie sum"), 0)

        # Fold outcomes override even a tied or contrary showdown sign.
        fold = SimpleNamespace(kind="fold", contributions=(Fraction(5, 4), Fraction(2)),
                               winner=0)
        fold_group = (({"sign": -1}, Fraction(2, 3)), ({"sign": 0}, Fraction(1, 3)))
        self.assertEqual(certificate_v3._terminal_group_signed(
            fold, fold_group, certificate_v2._ObservedBudget(100_000, 32, 65_536),
            "fold contribution", "fold sum"), _literal_terminal(fold, fold_group))

        # Fractional matched money is converted once using the literal binary64 payoff.
        fractional = SimpleNamespace(kind="showdown",
                                     contributions=(Fraction(1, 3), Fraction(2, 3)),
                                     winner=None)
        fractional_group = (({"sign": -1}, Fraction(1)),)
        self.assertEqual(certificate_v3._terminal_group_signed(
            fractional, fractional_group,
            certificate_v2._ObservedBudget(100_000, 32, 65_536),
            "fractional contribution", "fractional sum"),
            _literal_terminal(fractional, fractional_group))

    def test_terminal_operator_rejects_nonfinite_money_and_retained_first_width(self):
        huge = SimpleNamespace(kind="showdown", contributions=(float("inf"), float("inf")),
                               winner=None)
        with self.assertRaisesRegex(ValueError, "nonfinite"):
            certificate_v3._terminal_group_signed(
                huge, (({"sign": 1}, Fraction(1)),),
                certificate_v2._ObservedBudget(100_000, 32, 65_536),
                "huge contribution", "huge sum")
        # A tie-only group still validates money before its exact-zero shortcut.
        with self.assertRaisesRegex(ValueError, "nonfinite"):
            certificate_v3._terminal_group_signed(
                huge, (({"sign": 0}, Fraction(1)),),
                certificate_v2._ObservedBudget(100_000, 32, 65_536),
                "tied huge contribution", "tied huge sum")

        # The first mass is checked before any cancellation can make the accumulator small.
        boundary_mass = Fraction(1, 1 << 65_535)  # denominator occupies exactly 65,536 bits
        boundary_node = SimpleNamespace(kind="showdown",
                                         contributions=(Fraction(1), Fraction(1)),
                                         winner=None)
        boundary_group = (({"sign": 1}, boundary_mass), ({"sign": -1}, boundary_mass))
        self.assertEqual(certificate_v3._terminal_group_signed(
            boundary_node, boundary_group,
            certificate_v2._ObservedBudget(100_000, 32, 65_536),
            "boundary contribution", "boundary sum"), 0)
        too_wide_mass = Fraction(1, 1 << 65_536)
        too_wide_group = (({"sign": 1}, too_wide_mass),
                          ({"sign": -1}, too_wide_mass))
        with self.assertRaisesRegex(ValueError, "65536-bit limit"):
            certificate_v3._terminal_group_signed(
                boundary_node, too_wide_group,
                certificate_v2._ObservedBudget(100_000, 32, 65_536),
                "width contribution", "width sum")

    def test_saved_v1_projection_and_v2_interleaving_are_complete(self):
        publication = json.loads(_pinned_bytes("publication.json"))
        raw = json.loads(_pinned_bytes("attempt/raw-envelope.json"))
        exact = json.loads(_pinned_bytes("attempt/exact-certificate.json"))
        manifest = json.loads((ROOT / "benchmarks" / "four-street-integration-v1.json").read_bytes())
        self.assertEqual(publication["report_sha256"], PINS["attempt/report.json"])
        v2_before = certificate_v2.evaluate_exact(manifest["case"], raw["payload"])
        v3 = certificate_v3.evaluate_exact(manifest["case"], raw["payload"])
        v2_after = certificate_v2.evaluate_exact(manifest["case"], raw["payload"])
        self.assertEqual(v2_before, exact["certificate"])
        self.assertEqual(v2_after, v2_before)
        self.assertEqual(v3["source_identity"], "four-street-independent-exact-v3")
        self.assertEqual(v3["budget_schedule_version"], "four-street-exact-work-v3")
        self.assertEqual({key: v3[key] for key in V3_PROJECTION},
                         {key: exact["certificate"][key] for key in V3_PROJECTION})
        self.assertLessEqual(v3["maximum_fraction_bits"], v3["fraction_bit_limit"])

    def test_mixed_zero_and_subnormal_normalization_ledgers_are_exact(self):
        model = validation.build_model(_case())
        for mode in ("mixed", "zero", "subnormal"):
            with self.subTest(mode=mode):
                payload = _normalized_payload(model, mode)
                result = certificate_v3.evaluate_exact(_case(), payload)
                expected_rows, expected_max = _exact_row_expectations(payload)
                self.assertEqual(len(result["normalization_ledger"]), len(expected_rows))
                for ledger, (source, raw, normalized, adjustments, total) in zip(
                        result["normalization_ledger"], expected_rows):
                    self.assertEqual(ledger["raw_row_sum_fraction"], str(total))
                    self.assertEqual(len(ledger["actions"]), len(raw))
                    for item, before, after, adjustment in zip(
                            ledger["actions"], raw, normalized, adjustments):
                        self.assertEqual(_fraction(item["raw_binary64_fraction"]), before)
                        self.assertEqual(_fraction(item["normalized_fraction"]), after)
                        self.assertEqual(_fraction(item["adjustment_fraction"]), adjustment)
                self.assertEqual(_fraction(result["maximum_row_adjustment"]), expected_max)
                if mode in ("mixed", "subnormal"):
                    self.assertGreater(expected_max, 0)
                    row_l1_max = max(sum((abs(item) for item in adjustments), Fraction(0))
                                     for _row, _raw, _normalized, adjustments, _total
                                     in expected_rows)
                    self.assertLess(expected_max, row_l1_max)
                self.assertEqual(result["normalized_policy_sha256"],
                                 certificate_v2._canonical_hash(result["normalized_policy_rows"]))

    def test_fixed_candidate_profiles_and_familywise_forecast_dominance(self):
        case, _request = expansion._candidate_inputs()
        model = validation.build_model(case)
        forecast = certificate_v3.forecast_exact(case)
        policies = (
            ("positive", _payload(model, lambda _p, _h, _hist, actions:
                                  tuple(1.0 / len(actions) for _ in actions))),
            ("pure", _payload(model, _check_call)),
            ("pruned", _payload(model, _bb_no_bluff)),
        )
        for label, payload in policies:
            with self.subTest(policy=label):
                result = certificate_v3.evaluate_exact(case, payload)
                independent = _independent_exact_profile(model, payload)
                self.assertEqual(_fraction(result["metrics"]["value_sb"]), independent)
                self.assertEqual(_forecast_core(result["forecast"]), _forecast_core(forecast))
                _assert_family_schedule(self, result)
                self.assertLessEqual(result["actual_work"], result["forecast"]["work"])
                for kind, actual in result["actual_work_by_kind"].items():
                    self.assertLessEqual(actual, result["forecast"]["work_by_kind"][kind])

    def test_candidate_coupling_call_and_river_policy_anchors(self):
        case, _request = expansion._candidate_inputs()
        model = validation.build_model(case)
        baseline = _payload(model, _check_call)
        baseline_value = _independent_exact_profile(model, baseline)
        self.assertEqual(baseline_value, Fraction(-1, 20))
        changed = deepcopy(baseline)
        matches = [row for row in changed["strategy"]
                   if row["player"] == "sb" and row["hand"] in ("AsAd", "AdAs")
                   and row["street"] == "river"
                   and row["revealed_board"] == ["2c", "3c", "4d", "7h", "8h"]
                   and row["history"] == [
                       "call", "check", "flop@2c3c4d", "check", "check",
                       "turn@7h", "check", "check", "river@8h", "check"]]
        self.assertEqual(len(matches), 1)
        row = matches[0]
        selected = next((i for i, action in enumerate(row["actions"])
                         if action["name"] in ("bet", "raise")), None)
        self.assertIsNotNone(selected)
        for action in row["actions"]:
            action["probability"] = 0.0
        row["actions"][selected]["probability"] = 1.0
        changed_value = _independent_exact_profile(model, changed)
        self.assertEqual(changed_value, Fraction(1, 20))
        self.assertEqual(changed_value - baseline_value, Fraction(1, 10))
        result = certificate_v3.evaluate_exact(case, changed)
        self.assertEqual(_fraction(result["metrics"]["value_sb"]), changed_value)

    def test_public_case_payload_rows_and_operator_injection_guards(self):
        valid_case = _case()
        model = validation.build_model(valid_case)
        valid_payload = _payload(model, _check_call)
        bad_cases = (
            {}, {**valid_case, "sb_range": True}, {**valid_case, "sb_range": ""},
            {**valid_case, "config": {**valid_case["config"], "starting_stack": float("inf")}},
        )
        for bad_case in bad_cases:
            with self.subTest(kind="case", bad=repr(bad_case)[:50]):
                with self.assertRaises(ValueError):
                    certificate_v3.forecast_exact(bad_case)
                with self.assertRaises(ValueError):
                    certificate_v3.evaluate_exact(bad_case, valid_payload)
        for bad_payload in ({}, {"strategy": []}):
            with self.subTest(kind="payload", bad=repr(bad_payload)), self.assertRaises(ValueError):
                certificate_v3.evaluate_exact(valid_case, bad_payload)

        mutations = []
        missing_row = deepcopy(valid_payload)
        missing_row["strategy"].pop()
        mutations.append(missing_row)
        malformed_row = deepcopy(valid_payload)
        del malformed_row["strategy"][0]["history"]
        mutations.append(malformed_row)
        unknown_action = deepcopy(valid_payload)
        unknown_action["strategy"][0]["actions"][0]["name"] = "not-legal"
        mutations.append(unknown_action)
        malformed_action = deepcopy(valid_payload)
        del malformed_action["strategy"][0]["actions"][0]["history_key"]
        mutations.append(malformed_action)
        bad_probability = deepcopy(valid_payload)
        bad_probability["strategy"][0]["actions"][0]["probability"] = -0.25
        mutations.append(bad_probability)
        zero_probability = deepcopy(valid_payload)
        for action in zero_probability["strategy"][0]["actions"]:
            action["probability"] = 0.0
        mutations.append(zero_probability)
        nonfinite_probability = deepcopy(valid_payload)
        nonfinite_probability["strategy"][0]["actions"][0]["probability"] = float("inf")
        mutations.append(nonfinite_probability)
        for payload in mutations:
            with self.subTest(payload=payload["strategy"][0]), self.assertRaises(ValueError):
                certificate_v3.evaluate_exact(valid_case, payload)

        for name in ("operator", "callback", "terminal_operator", "normalizer",
                     "graph", "terminal_group_operator"):
            with self.subTest(api="forecast_exact", argument=name), self.assertRaises(TypeError):
                certificate_v3.forecast_exact(valid_case, **{name: lambda *_: None})
            with self.subTest(api="evaluate_exact", argument=name), self.assertRaises(TypeError):
                certificate_v3.evaluate_exact(valid_case, valid_payload,
                                              **{name: lambda *_: None})

    def test_fresh_candidate_census_has_exact_group_and_entry_counts(self):
        case, _request = expansion._candidate_inputs()
        forecast = certificate_v3.forecast_exact(case)
        _assert_terminal_census(self, forecast["preparation_receipts"])


if __name__ == "__main__":
    unittest.main()
