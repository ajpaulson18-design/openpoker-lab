"""Exact four-street policy value and legal response controls."""
import copy
import hashlib
import json
import sys
import unittest
from decimal import Decimal, getcontext, localcontext
from fractions import Fraction
from decimal import Decimal
from unittest.mock import patch

from scripts import four_street_certificate as certificate
from scripts import four_street_validation as validation


CASE = {
    "id": "four-street-weighted-shared-future-v1",
    "sb_range": "AsAd:0.5,QsQd:0.25",
    "bb_range": "KsKd:0.75,JhJd:0.25",
    "config": {"starting_stack": 8, "small_blind": 0.5, "big_blind": 1,
                "raise_sizes": [0.5], "max_raises": 1, "include_all_in": False},
    "runouts": ["2c3c4d7h8h", "2c3c4d7hKc", "2c3c4dKc8h",
                "2c3c4dQd8h", "5c6d7s8c9h", "5c6d7s8cJc"],
    "flop_config": {"bet_sizes": [0.5], "raise_sizes": [],
                     "max_raises": 0, "include_all_in": False},
    "turn_config": None,
    "river_config": None,
}


def _case(sb="AsAd", bb="KsKd", runouts=("2c3c4d7h8h",), stacks=8):
    return {"id": "exact-certificate-control", "sb_range": sb, "bb_range": bb,
            "config": {"starting_stack": stacks, "small_blind": 0.5,
                       "big_blind": 1, "raise_sizes": [0.5], "max_raises": 1,
                       "include_all_in": False},
            "runouts": list(runouts),
            "flop_config": {"bet_sizes": [0.5], "raise_sizes": [],
                            "max_raises": 0, "include_all_in": False},
            "turn_config": None, "river_config": None}


def _payload(model, chooser):
    outcomes = validation._case_inputs(model.case)[6]
    payload = {
        "solver_version": "preflop-strategy-v1", "strategy_schema": "preflop-strategy-v1",
        "runout_mode": "conditioned-ordered-selected-runouts",
        "selected_runouts": [list(outcome) for outcome in outcomes],
        "reachable_runouts": [list(outcome) for outcome in outcomes
                               if any(world["board"] == outcome for world in model.worlds)],
        "worlds": model.counts["worlds"],
        "compatible_private_pairs": model.counts["compatible_pairs"],
        "info_sets": model.counts["infos"],
        "private_pair_probabilities": [
            {"sb_hand": row["sb_hand"], "bb_hand": row["bb_hand"],
             "probability": float(Fraction(row["fraction"]))}
            for row in model.counts["pair_probabilities"]],
        "strategy": [],
    }
    street = {0: "preflop", 3: "flop", 4: "turn", 5: "river"}
    for (player, hand, history), node in sorted(model.expected_infos.items()):
        probabilities = chooser(player, hand, history, node.actions)
        payload["strategy"].append({
            "player": "sb" if player == 0 else "bb", "hand": hand,
            "street": street[len(node.board)], "revealed_board": list(node.board),
            "history": list(history),
            "actions": [{"name": action.name, "amount": action.amount,
                         "raise_to": action.raise_to, "history_key": action.token,
                         "probability": probability}
                        for action, probability in zip(node.actions, probabilities)],
        })
    return payload


def _check_call(_player, _hand, _history, actions):
    names = [action.name for action in actions]
    selected = "check" if "check" in names else "call" if "call" in names else "fold"
    return tuple(1.0 if action.name == selected else 0.0 for action in actions)


def _bb_no_bluff(player, _hand, _history, actions):
    names = [action.name for action in actions]
    if player == 1:
        selected = "check" if "check" in names else "fold"
    else:
        selected = "check" if "check" in names else "call" if "call" in names else "fold"
    return tuple(1.0 if action.name == selected else 0.0 for action in actions)


def _independent_exact_profile(model, payload):
    """Slow exact per-world replay; deliberately separate from certificate traversal."""
    policies = {}
    for row in payload["strategy"]:
        player = 0 if row["player"] == "sb" else 1
        key = (player, row["hand"], tuple(row["history"]))
        raw = tuple(Fraction.from_float(float(action["probability"]))
                    for action in row["actions"])
        total = sum(raw, Fraction(0))
        policies[key] = tuple(value / total for value in raw)

    def utility(node, world):
        matched = min(node.contributions)
        sign = (1 if node.winner == 0 else -1) if node.kind == "fold" else world["sign"]
        binary64_payoff = float(sign) * float(matched)
        return Fraction.from_float(binary64_payoff)

    def play(node, world):
        if isinstance(node, validation._Terminal):
            return utility(node, world)
        if isinstance(node, validation.Reveal):
            return play(node.branches[world["board"][:node.board_length]], world)
        key = (node.player, "".join(world["hands"][node.player]), node.history)
        probabilities = policies[key]
        return sum((probability * play(child, world)
                    for probability, child in zip(probabilities, node.children)), Fraction(0))

    return sum((world["weight"] * play(model.root, world) for world in model.worlds),
               Fraction(0))


def _assert_family_schedule(testcase, result):
    forecast = result["forecast"]
    actual = result["actual_work_by_kind"]
    limit = forecast["work_by_kind"]
    testcase.assertEqual(sum(actual.values()), result["actual_work"])
    testcase.assertEqual(sum(limit.values()), forecast["work"])
    testcase.assertLessEqual(result["actual_work"], forecast["work"])
    testcase.assertFalse(set(actual) - set(limit))
    testcase.assertFalse(any(name.startswith("profile_") for name in actual))
    for name, count in actual.items():
        testcase.assertLessEqual(count, limit[name], (name, count, limit[name]))


class FourStreetCertificateTests(unittest.TestCase):
    def test_structural_preparation_is_separate_and_bounded_for_each_public_call(self):
        forecast = certificate.forecast_exact(CASE)
        model = validation.build_model(CASE)
        exact = certificate.evaluate_exact(CASE, _payload(model, _check_call))
        for result, passes in ((forecast, 2), (exact, 3)):
            receipt = result["preparation_receipts"]["structural_graph_validation"]
            self.assertEqual(receipt["owned_graph_validation_walks"], passes)
            self.assertEqual(receipt["per_walk_upper_bounds"], {
                "world_scan_entries": 124432,
                "copied_world_references": 31108,
                "information_key_iterations": 13816,
                "physical_mass_validation_additions": 22,
            })
            self.assertEqual(receipt["total_entries_upper_bound"], 169378 * passes)
            self.assertLessEqual(receipt["total_entries_upper_bound"], receipt["entry_limit"])
            self.assertTrue(receipt["admitted"])
        self.assertEqual(forecast["work"], 98298)
        self.assertEqual(exact["forecast"]["work"], 98298)

    def test_forecast_is_probability_independent_and_retains_full_overcap_receipt(self):
        first = certificate.forecast_exact(CASE)
        second = certificate.forecast_exact(copy.deepcopy(CASE))
        self.assertEqual(first, second)
        self.assertEqual(first["source_identity"], "four-street-independent-exact-v2")
        self.assertEqual(first["budget_schedule_version"], "four-street-exact-work-v2")
        self.assertEqual(first["work"], 98_298)
        self.assertTrue(first["admitted"])
        self.assertEqual(first["excess_work"], 0)
        self.assertEqual(first["tree_nodes"], 1414)
        self.assertEqual(first["tree_depth"], 14)
        self.assertEqual({key: first["work_by_kind"][key] for key in (
            "fused_profile_own_row_lookups", "fused_profile_own_action_multiplications",
            "fused_profile_own_action_additions", "fused_profile_reveal_additions",
            "fused_profile_opponent_additions", "fused_profile_root_additions",
            "fused_result_slots")}, {
                "fused_profile_own_row_lookups": 572,
                "fused_profile_own_action_multiplications": 1146,
                "fused_profile_own_action_additions": 1146,
                "fused_profile_reveal_additions": 293,
                "fused_profile_opponent_additions": 1144,
                "fused_profile_root_additions": 2,
                "fused_result_slots": 2640})
        self.assertFalse(any(name.startswith("profile_") for name in first["work_by_kind"]))
        literal_model = validation.build_model(CASE)
        base = certificate.evaluate_exact(CASE, _payload(literal_model, _check_call))
        self.assertEqual(Fraction(base["metrics"]["value_sb"]), Fraction(1, 34))
        self.assertEqual(len(base["normalized_policy_rows"]), 1200)
        _assert_family_schedule(self, base)

        changed = _payload(literal_model, _check_call)
        target_history = ["call", "check", "flop@2c3c4d", "check", "check",
                          "turn@7h", "check", "check", "river@8h", "check"]
        target = next(row for row in changed["strategy"]
                      if row["player"] == "sb" and row["hand"] == "AdAs" and
                      row["revealed_board"] == ["2c", "3c", "4d", "7h", "8h"] and
                      row["history"] == target_history)
        self.assertEqual([(action["name"], action["amount"], action["raise_to"])
                          for action in target["actions"]], [("check", 0.0, 0.0),
                                                               ("bet", 1.0, 2.0)])
        target["actions"][0]["probability"] = 0.0
        target["actions"][1]["probability"] = 1.0
        alternative = certificate.evaluate_exact(CASE, changed)
        self.assertEqual(Fraction(alternative["metrics"]["value_sb"]), Fraction(5, 34))
        self.assertEqual(Fraction(alternative["metrics"]["value_sb"]) -
                         Fraction(base["metrics"]["value_sb"]), Fraction(2, 17))
        self.assertEqual(alternative["metrics"]["sb_best_response_value"],
                         base["metrics"]["sb_best_response_value"])
        self.assertEqual(alternative["metrics"]["bb_best_response_value"],
                         base["metrics"]["bb_best_response_value"])
        self.assertEqual(len(alternative["normalized_policy_rows"]), 1200)
        _assert_family_schedule(self, alternative)

    def test_sure_winner_zero_gap_and_nonzero_gap_controls(self):
        case = _case()
        model = validation.build_model(case)
        all_check = _payload(model, _check_call)
        exact = certificate.evaluate_exact(case, all_check)
        metrics = {key: Fraction(value) for key, value in exact["metrics"].items()}
        self.assertEqual(metrics["value_sb"], 1)
        self.assertEqual(metrics["sb_best_response_value"], 8)
        self.assertEqual(metrics["bb_best_response_value"], -1)
        self.assertEqual(metrics["nash_conv"], 7)
        self.assertFalse(exact["threshold_met"])

        no_bluff = _payload(model, _bb_no_bluff)
        zero = certificate.evaluate_exact(case, no_bluff)
        self.assertEqual(Fraction(zero["metrics"]["value_sb"]), 1)
        self.assertEqual(Fraction(zero["metrics"]["nash_conv"]), 0)
        self.assertTrue(zero["threshold_met"])
        self.assertLessEqual(zero["actual_work"], zero["forecast"]["work"])

    def test_exact_normalization_ledger_and_mapping_hashes(self):
        case = _case()
        model = validation.build_model(case)

        def near(_player, _hand, _history, actions):
            probabilities = [1.0 / len(actions)] * len(actions)
            probabilities[-1] += 1e-16
            return tuple(probabilities)

        payload = _payload(model, near)
        result = certificate.evaluate_exact(case, payload)
        raw_hash = hashlib.sha256(json.dumps(
            payload, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("ascii")).hexdigest()
        self.assertEqual(result["input_policy_canonical_sha256"], raw_hash)
        self.assertEqual(len(result["normalization_ledger"]), model.counts["infos"])
        self.assertEqual(len(result["normalized_policy_rows"]), model.counts["infos"])
        self.assertGreater(Fraction(result["maximum_row_adjustment"]), 0)
        for row, ledger in zip(result["normalized_policy_rows"], result["normalization_ledger"]):
            exact_sum = sum((Fraction(action["probability_fraction"])
                             for action in row["actions"]), Fraction(0))
            self.assertEqual(exact_sum, 1)
            self.assertEqual(len(row["actions"]), len(ledger["actions"]))
        self.assertEqual(result["normalized_policy_sha256"], certificate._canonical_hash(
            result["normalized_policy_rows"]))
        self.assertLessEqual(result["actual_work"], result["forecast"]["work"])
        self.assertLessEqual(max(item["absolute_difference"]
                                 for item in result["floating_comparison"].values()), 1e-9)
        _assert_family_schedule(self, result)

    def test_fused_profile_matches_independent_exact_per_world_replay(self):
        case = copy.deepcopy(CASE)
        model = validation.build_model(case)

        def mixed(player, hand, history, actions):
            hand_index = sum(ord(character) for character in hand)
            offset = (player + len(history) + hand_index) % len(actions)
            weights = [float(index + 1 + offset) for index in range(len(actions))]
            total = sum(weights)
            return tuple(value / total for value in weights)

        payloads = [_payload(model, mixed), _payload(model, _check_call)]
        tiny = _payload(model, mixed)
        tiny_row = next(row for row in tiny["strategy"] if len(row["actions"]) > 1)
        tiny_row["actions"][0]["probability"] = 5e-324
        tiny_row["actions"][1]["probability"] = 1.0
        for action in tiny_row["actions"][2:]:
            action["probability"] = 0.0
        payloads.append(tiny)

        for payload in payloads:
            with self.subTest(policy=payload is not tiny and
                              payload["strategy"][0]["actions"][0]["probability"]):
                exact = certificate.evaluate_exact(case, payload)
                self.assertEqual(Fraction(exact["metrics"]["value_sb"]),
                                 _independent_exact_profile(model, payload))
                _assert_family_schedule(self, exact)

        fractional_case = _case(stacks=[2.01, 2.01])
        fractional_model = validation.build_model(fractional_case)
        fractional_payload = _payload(fractional_model, _check_call)
        fractional_result = certificate.evaluate_exact(fractional_case, fractional_payload)
        self.assertEqual(Fraction(fractional_result["metrics"]["value_sb"]),
                         _independent_exact_profile(fractional_model, fractional_payload))
        _assert_family_schedule(self, fractional_result)

    def test_policy_mutations_reject_under_normal_and_optimized_python(self):
        case = _case()
        model = validation.build_model(case)
        payload = _payload(model, _check_call)
        mutations = []
        bad_actor = copy.deepcopy(payload)
        bad_actor["strategy"][0]["player"] = "oop"
        mutations.append((bad_actor, "actor"))
        bad_amount = copy.deepcopy(payload)
        target_action = next(action for row in bad_amount["strategy"]
                             for action in row["actions"] if action["name"] == "call")
        target_action["raise_to"] += 0.25
        mutations.append((bad_amount, "raise_to"))
        missing = copy.deepcopy(payload)
        missing["strategy"].pop()
        mutations.append((missing, "row count"))
        bad_mass = copy.deepcopy(payload)
        bad_mass["private_pair_probabilities"][0]["probability"] += 0.01
        mutations.append((bad_mass, "pair mass"))
        bad_probability = copy.deepcopy(payload)
        bad_probability["strategy"][0]["actions"][0]["probability"] = True
        mutations.append((bad_probability, "probability"))
        for corrupted, message in mutations:
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                certificate.evaluate_exact(case, corrupted)

    def test_hidden_future_is_summed_before_legal_best_response(self):
        case = _case(runouts=("2c3c4d7h8h", "Kc2d3h7s8c"), stacks=[2, 1])

        def adversarial(player, _hand, history, actions):
            names = [action.name for action in actions]
            if player == 0 and not history:
                return tuple(0.5 if action.name in ("fold", "call") else 0.0
                             for action in actions)
            return _check_call(player, _hand, history, actions)

        payload = _payload(validation.build_model(case), adversarial)
        exact = certificate.evaluate_exact(case, payload)
        metrics = {key: Fraction(value) for key, value in exact["metrics"].items()}
        self.assertEqual(metrics["value_sb"], Fraction(-1, 4))
        self.assertEqual(metrics["sb_best_response_value"], 0)
        self.assertEqual(metrics["bb_best_response_value"], Fraction(1, 4))
        self.assertEqual(metrics["nash_conv"], Fraction(1, 4))

    def test_cycle_actor_reveal_mass_sign_and_action_structure_rejection(self):
        base = _case()
        original = validation.build_model(base)
        mutations = []
        cycle = validation.build_model(base)
        cycle.root.children = (cycle.root,) + cycle.root.children[1:]
        mutations.append((cycle, "cycle"))
        bad_actor = validation.build_model(base)
        bad_actor.root.player = 3
        mutations.append((bad_actor, "actor"))
        bad_mass = validation.build_model(base)
        bad_mass.worlds[0]["weight"] = Fraction(2)
        mutations.append((bad_mass, "mass"))
        bad_sign = validation.build_model(base)
        bad_sign.worlds[0]["sign"] = 2
        mutations.append((bad_sign, "sign"))
        bad_actions = validation.build_model(base)
        bad_actions.root.children = bad_actions.root.children[:-1]
        mutations.append((bad_actions, "misaligned"))
        bad_reveal = validation.build_model(base)
        reveal = next(node for node in _walk(bad_reveal.root)
                      if isinstance(node, validation.Reveal))
        reveal.branches.pop(next(iter(reveal.branches)))
        mutations.append((bad_reveal, "partition"))
        for model, message in mutations:
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                certificate._validate_graph(model)
        with self.assertRaisesRegex(ValueError, "plain bounded dictionary"):
            certificate.forecast_exact(original)
        with self.assertRaisesRegex(ValueError, "plain bounded dictionary"):
            certificate.evaluate_exact(original, {})

    def test_case_snapshot_rejects_exponential_dag_and_unbounded_scalars(self):
        # Reusing one nested list 128 times per level used to be cloned as an
        # exponentially large tree despite every individual container being small.
        shared = ["leaf"]
        for _ in range(3):
            shared = [shared] * 128
        with self.assertRaisesRegex(ValueError, "total node count"):
            certificate._snapshot_case({"id": "dag", "nested": shared})

        case = {"bool": True, "finite": 1.25}
        self.assertEqual(certificate._snapshot_case(case), case)
        with self.assertRaisesRegex(ValueError, "mapping"):
            certificate._snapshot_case({"x" * (validation.MAX_RANGE_EXPRESSION_LENGTH + 1): 1})
        for value, message in (
                (float("inf"), "finite"),
                ("x" * (validation.MAX_RANGE_EXPRESSION_LENGTH + 1), "string"),
                (1 << (certificate.MAX_FRACTION_BITS + 1), "integer"),
                (Fraction(1, 1 << certificate.MAX_FRACTION_BITS), "fraction")):
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                certificate._snapshot_case({"value": value})

    def test_zero_probability_policy_keeps_same_shape_forecast(self):
        case = _case()
        model = validation.build_model(case)
        zero_heavy = _payload(model, _check_call)
        # A valid pure policy has many zero-probability action entries.
        result = certificate.evaluate_exact(case, zero_heavy)
        self.assertEqual(result["forecast"]["work"], certificate.forecast_exact(case)["work"])
        self.assertLess(result["actual_work"], result["forecast"]["work"])
        self.assertLess(result["actual_work_by_kind"]["br_opponent_reach_multiplications"],
                        result["forecast"]["work_by_kind"]["br_opponent_reach_multiplications"])
        _assert_family_schedule(self, result)

        extreme = _payload(model, _check_call)
        row = next(row for row in extreme["strategy"]
                   if len(row["actions"]) > 1)
        row["actions"][0]["probability"] = 5e-324
        row["actions"][1]["probability"] = 1.0
        for action in row["actions"][2:]:
            action["probability"] = 0.0
        extreme_result = certificate.evaluate_exact(case, extreme)
        self.assertEqual(extreme_result["forecast"]["work"], result["forecast"]["work"])
        self.assertLessEqual(extreme_result["actual_work"],
                             extreme_result["forecast"]["work"])
        self.assertEqual(Fraction(extreme_result["metrics"]["value_sb"]),
                         _independent_exact_profile(model, extreme))
        _assert_family_schedule(self, extreme_result)

    def test_rational_width_and_forecast_counter_fail_closed_at_boundary(self):
        budget = certificate.rational._Budget(100_000, 32, 65_536)
        self.assertEqual(budget.fraction(Fraction(1, 1 << 65_535), "edge"),
                         Fraction(1, 1 << 65_535))
        with self.assertRaisesRegex(ValueError, "65536-bit limit"):
            budget.fraction(Fraction(1, 1 << 65_536), "over")
        counter = certificate._Counter(limit=4)
        counter.charge("edge", 4)
        with self.assertRaisesRegex(ValueError, "partial counters"):
            counter.charge("over", 1)
        observed = certificate._ObservedBudget(1, 32, 65_536)
        observed.charge("inside")
        with self.assertRaisesRegex(ValueError, "partial exact counters"):
            observed.charge("over")

    def test_fraction_text_formats_full_guard_width_without_global_limit_changes(self):
        from decimal import Decimal as ExactDecimal

        values = (
            Fraction(0), Fraction(1), Fraction(-1), Fraction(1, 3), Fraction(-7, 4),
            Fraction((1 << 65_535) + 1, 1),
            Fraction(-((1 << 65_535) + 1), 1),
            Fraction(1, (1 << 65_535) + 1),
        )
        digit_limit = sys.get_int_max_str_digits()
        original_precision = getcontext().prec
        with localcontext() as context:
            context.prec = 1
            self.assertEqual(getcontext().prec, 1)
            for value in values:
                rendered = certificate._fraction_text(value)
                numerator_text, separator, denominator_text = rendered.partition("/")
                self.assertEqual(ExactDecimal(numerator_text).as_integer_ratio(),
                                 (value.numerator, 1))
                self.assertEqual(ExactDecimal(denominator_text if separator else "1").as_integer_ratio(),
                                 (value.denominator, 1))
                if max(abs(value.numerator).bit_length(), value.denominator.bit_length()) < 4_000:
                    self.assertEqual(rendered, str(value))
                numerator_text, separator, denominator_text = rendered.partition("/")
                numerator, numerator_denominator = Decimal(numerator_text).as_integer_ratio()
                self.assertEqual(numerator_denominator, 1)
                if separator:
                    denominator, denominator_denominator = Decimal(
                        denominator_text).as_integer_ratio()
                    self.assertEqual(denominator_denominator, 1)
                    self.assertEqual(Fraction(numerator, denominator), value)
                else:
                    self.assertEqual((numerator, 1),
                                     (value.numerator, value.denominator))
                self.assertEqual(certificate._canonical_hash({"value": value}),
                                 certificate._canonical_hash({
                                     "value": {"$fraction": rendered}}))
            self.assertEqual(getcontext().prec, 1)
        self.assertEqual(getcontext().prec, original_precision)
        self.assertEqual(sys.get_int_max_str_digits(), digit_limit)
        with self.assertRaisesRegex(ValueError, "65536-bit limit"):
            certificate._fraction_text(Fraction(1, 1 << 65_536))


def _walk(root):
    pending = [root]
    seen = set()
    while pending:
        node = pending.pop()
        if id(node) in seen:
            continue
        seen.add(id(node))
        yield node
        pending.extend(certificate._children(node))


if __name__ == "__main__":
    unittest.main()
class TestFractionTextMathematicalIntegrity(unittest.TestCase):
    def test_large_fraction_text_round_trips_exact_integer_components(self):
        value = Fraction((1 << 60_000) - 123, (1 << 59_900) + 321)
        rendered = certificate._fraction_text(value)
        numerator, denominator = rendered.split("/")
        self.assertEqual(Decimal(numerator).as_integer_ratio(), (value.numerator, 1))
        self.assertEqual(Decimal(denominator).as_integer_ratio(), (value.denominator, 1))
import unittest
from fractions import Fraction
from decimal import Decimal
from scripts import four_street_certificate as certificate
