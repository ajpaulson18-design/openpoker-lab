"""Exact four-street policy value and legal response controls."""
import copy
import hashlib
import json
import unittest
from fractions import Fraction
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


class FourStreetCertificateTests(unittest.TestCase):
    def test_forecast_is_probability_independent_and_retains_full_overcap_receipt(self):
        first = certificate.forecast_exact(CASE)
        second = certificate.forecast_exact(copy.deepcopy(CASE))
        self.assertEqual(first, second)
        self.assertEqual(first["work"], 118_261)
        self.assertFalse(first["admitted"])
        self.assertEqual(first["excess_work"], 18_261)
        self.assertEqual(first["tree_nodes"], 1414)
        self.assertEqual(first["tree_depth"], 14)
        self.assertGreater(first["work_by_kind"]["br_opponent_reach_multiplications"], 0)
        literal_model = validation.build_model(CASE)
        with self.assertRaisesRegex(ValueError, "forecast exceeds its hard work limit"):
            certificate.evaluate_exact(CASE, _payload(literal_model, _check_call))

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

    def test_zero_probability_policy_keeps_same_shape_forecast(self):
        case = _case()
        model = validation.build_model(case)
        zero_heavy = _payload(model, _check_call)
        # A valid pure policy has many zero-probability action entries.
        result = certificate.evaluate_exact(case, zero_heavy)
        self.assertEqual(result["forecast"]["work"], certificate.forecast_exact(case)["work"])
        self.assertLess(result["actual_work"], result["forecast"]["work"])

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
