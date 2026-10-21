"""Adversarial scratch tests for the fixed three-hand class quotient."""
from collections import defaultdict
from copy import deepcopy
from dataclasses import replace
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import unittest
from unittest import mock

from scripts import turn_three_hand_classes as classes
from scripts import turn_three_hand_reference as reference
from scripts import turn_river_validation as rules


REPORT_SHA256 = "1827e2163b897c5a1c5274e4a300ee365d8234fdf38235647772d63300953a7a"
POLICY_SHA256 = "c02e37dedf886f586e8b0ce9a98e86d079a32322d6e2ba4eb5beaab127dd6789"
METRICS = tuple(reference.METRICS)
CHECK_CALL = {
    "value_oop": Fraction(-9500, 891),
    "value_ip": Fraction(9500, 891),
    "oop_best_response_value": Fraction(6925, 891),
    "ip_best_response_value": Fraction(57550, 891),
    "oop_best_response_gain": Fraction(1825, 99),
    "ip_best_response_gain": Fraction(48050, 891),
    "nash_conv": Fraction(64475, 891),
    "exploitability": Fraction(64475, 1782),
}
EXPECTED_CLASS_MASSES = {
    "2c": Fraction(9, 11), "Ac": Fraction(5, 198), "Ah": Fraction(7, 198),
    "Kc": Fraction(1, 33), "Kh": Fraction(5, 198),
    "Qc": Fraction(7, 198), "Qh": Fraction(1, 33),
}
EXPECTED_CENSUS = {
    "public_nodes": 456, "public_decisions": 188, "terminal_nodes": 263,
    "chance_nodes": 5, "chance_edges": 35, "decision_edges": 420, "depth": 9,
    "policy_rows": 486, "policy_action_slots": 1086,
    "pair_class_prefix_entries": 54, "physical_branch_subtrees_compared": 240,
}


def _repo_root():
    return Path(reference.__file__).resolve().parents[1]


def _history_class(history, river_class):
    return tuple("river@" + river_class[token[6:]] if token.startswith("river@") else token
                 for token in history)


def _physical_policy(game, model, style):
    payload = reference.make_check_call_policy(game)
    for row in payload["strategy"]:
        if style == "check_call":
            continue
        count = len(row["actions"])
        if style == "uniform":
            probs = [1.0 / count] * count
            probs[-1] = 1.0 - sum(probs[:-1])
        else:
            history = _history_class(tuple(row["history"]), model.river_class)
            seed = sum(map(ord, row["player"] + row["hand"] + repr(history)))
            if count == 1:
                probs = [1.0]
            elif count == 2:
                first = 0.25 + 0.05 * (seed % 5)
                probs = [first, 1.0 - first]
            else:
                first = 0.15 + 0.02 * (seed % 4)
                second = 0.24 + 0.02 * ((seed // 3) % 4)
                probs = [first, second, 1.0 - first - second]
        for action, probability in zip(row["actions"], probs):
            action["probability"] = float(probability)
    return payload


def _identity(row):
    return row["player"], row["hand"], tuple(row["history"])


def _compare_policy_rows(test, before, after):
    test.assertEqual(len(before["strategy"]), 3606)
    test.assertEqual(len(after["strategy"]), 3606)
    a = {_identity(row): row for row in before["strategy"]}
    b = {_identity(row): row for row in after["strategy"]}
    test.assertEqual(set(a), set(b))
    for key in a:
        lhs, rhs = a[key], b[key]
        for field in ("player", "hand", "street", "board", "history"):
            test.assertEqual(lhs[field], rhs[field], (key, field))
        test.assertEqual(len(lhs["actions"]), len(rhs["actions"]))
        for left, right in zip(lhs["actions"], rhs["actions"]):
            test.assertEqual({k: v for k, v in left.items() if k != "probability"},
                             {k: v for k, v in right.items() if k != "probability"})
            test.assertEqual(left["probability"], right["probability"])


def _find_row(payload, player, hand, history):
    return next(row for row in payload["strategy"]
                if row["player"] == player and row["hand"] == hand
                and tuple(row["history"]) == tuple(history))


class ThreeHandClassAdversarialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.game = reference.model()
        cls.model = classes.build_model(cls.game)
        cls.repo = _repo_root()
        cls.report_path = cls.repo / "benchmarks" / "results" / "turn-three-hand-direct-tail-v1.json"
        cls.policy_path = cls.repo / "benchmarks" / "results" / "turn-three-hand-direct-tail-v1-policy.json"
        cls.report_raw = cls.report_path.read_bytes()
        cls.policy_raw = cls.policy_path.read_bytes()
        cls.report = json.loads(cls.report_raw)
        cls.saved_policy = json.loads(cls.policy_raw)

    def _assert_unchanged_caps(self, physical, lanes):
        caps = {"structural_node_visits": 27351, "weighted_row_operations": 3610332,
                "active_world_node_visits": 92664, "consumed_policy_rows": 38016,
                "policy_edge_multiplications": 85536, "terminal_world_contributions": 48708,
                "exact_fraction_operations": 1000000, "max_fraction_bits": 65536}
        for name, cap in caps.items():
            self.assertLessEqual(physical[name], cap, name)
        for lane in lanes.values():
            self.assertLessEqual(lane["work"], 100000)
            self.assertLessEqual(lane["maximum_fraction_bits"], 65536)

    def test_literal_classes_masses_and_compact_census(self):
        fixture, board, _config, worlds, selected, _root, _pairs = self.game
        members = {rep: tuple(cards) for rep, cards in self.model.class_members}
        neutral = tuple(card for card in selected if card[0] not in "AKQ")
        self.assertEqual(members, {
            "2c": neutral, "Ac": ("Ac", "Ad"), "Ah": ("Ah", "As"),
            "Kc": ("Kc", "Kd"), "Kh": ("Kh", "Ks"),
            "Qc": ("Qc", "Qd"), "Qh": ("Qh", "Qs"),
        })
        self.assertEqual(set(self.model.river_class), set(selected))
        self.assertEqual(self.model.class_masses, EXPECTED_CLASS_MASSES)
        self.assertEqual(self.model.census, EXPECTED_CENSUS)
        self.assertEqual(len(self.model.class_worlds), 45)
        self.assertEqual(sum((w["weight"] for w in self.model.class_worlds), Fraction()), 1)

        # Derive every class aggregation from physical world masses, without the
        # implementation's class_masses or aggregation helper.
        by_pair_class = defaultdict(Fraction)
        signs = defaultdict(set)
        for world in worlds:
            rep = self.model.river_class[world["river"]]
            key = (world["hands"], rep)
            by_pair_class[key] += world["weight"]
            signs[key].add(world["sign"])
        observed = {(w["hands"], w["river"]): w for w in self.model.class_worlds}
        self.assertEqual(set(observed), set(by_pair_class))
        for key, total in by_pair_class.items():
            self.assertEqual(observed[key]["weight"], total)
            self.assertEqual(signs[key], {observed[key]["sign"]})
            self.assertEqual(observed[key]["board"], board + (key[1],))
        for rep, cards in members.items():
            self.assertEqual(self.model.class_masses[rep], sum(
                (w["weight"] for w in worlds if self.model.river_class[w["river"]] == rep), Fraction()))
            self.assertEqual(len(cards), 36 if rep == "2c" else 2)
        self.assertEqual(classes.validate_model(self.model), EXPECTED_CENSUS)
        self.assertEqual(Path(classes.__file__).resolve().parents[1], Path(__file__).resolve().parents[1])
        self.assertEqual(Path(reference.__file__).resolve().parents[1], Path(rules.__file__).resolve().parents[1])

    def test_saved_raw_report_hashes_exact_metrics_and_positive_miss(self):
        self.assertEqual(hashlib.sha256(self.report_raw).hexdigest(), REPORT_SHA256)
        self.assertEqual(hashlib.sha256(self.policy_raw).hexdigest(), POLICY_SHA256)
        self.assertEqual(self.report["policy_sha256"], POLICY_SHA256)
        self.assertEqual(self.report["generation_head"], "03d54fefaad2aa6247f9d627e112e40688c0ead1")
        expected = {name: Fraction(value) for name, value in
                    self.report["results"]["exact_metrics_fractions"].items()}
        self.assertEqual(set(expected), set(METRICS))
        self.assertNotEqual(expected["nash_conv"], 0)
        self.assertGreater(expected["nash_conv"], Fraction(1, 1000))
        self.assertFalse(self.report["results"]["exact_threshold_met"])
        self.assertFalse(self.report["results"]["exact_nash_conv_zero"])

        saved_snapshot = deepcopy(self.saved_policy)
        with mock.patch("pokerlab.turn_tail_adapter.solve_turn_tail",
                        side_effect=AssertionError("class audit called producer")), \
             mock.patch("pokerlab.turn_tail_adapter._train_original_weight_tail",
                        side_effect=AssertionError("class audit called adapter trainer")), \
             mock.patch("pokerlab.cfr.train", side_effect=AssertionError("class audit called CFR trainer")), \
             mock.patch("pokerlab.cfr.evaluate", side_effect=AssertionError("class audit called CFR evaluator")), \
             mock.patch("pokerlab.cfr.best_response", side_effect=AssertionError("class audit called CFR BR")), \
             mock.patch("pokerlab.postflop_solver.solve_postflop",
                        side_effect=AssertionError("class audit called production solver")), \
             mock.patch("pokerlab.postflop_solver._build_postflop_tree",
                        side_effect=AssertionError("class audit built production tree")):
            result = classes.audit_policy(self.saved_policy, self.model)
        full = result["full_physical_exact_metrics"]
        self.assertEqual(full, expected)
        self.assertEqual(result["training_calls"], 0)
        self.assertEqual(set(result["generic_class_audits"]), {"scan", "partition"})
        for lane in result["generic_class_audits"].values():
            self.assertEqual(lane["metrics"], expected)
            self.assertLessEqual(lane["work"], 100_000)
            self.assertLessEqual(lane["maximum_fraction_bits"], 65_536)
        self.assertEqual(self.saved_policy, saved_snapshot)
        self.assertEqual(self.report_path.read_bytes(), self.report_raw)
        self.assertEqual(self.policy_path.read_bytes(), self.policy_raw)

    def test_control_uniform_and_mixed_roundtrip_under_both_chance_lanes(self):
        policies = {
            "check_call": reference.make_check_call_policy(self.game),
            "uniform": reference.make_uniform_policy(self.game),
            "mixed": _physical_policy(self.game, self.model, "mixed"),
        }
        projected = classes.project_policy(policies["mixed"], self.model)
        self.assertEqual(len(projected["policies"]), 486)
        class_mixed = deepcopy(projected["result"])
        for row in class_mixed["strategy"]:
            count = len(row["actions"])
            seed = sum(map(ord, row["player"] + row["hand"] + repr(tuple(row["history"]))))
            if count == 1:
                probs = [1.0]
            elif count == 2:
                first = 0.2 + 0.05 * (seed % 6)
                probs = [first, 1.0 - first]
            else:
                first = 0.13 + 0.02 * (seed % 5)
                second = 0.21 + 0.02 * ((seed // 3) % 5)
                probs = [first, second, 1.0 - first - second]
            for action, probability in zip(row["actions"], probs):
                action["probability"] = float(probability)
        compact_snapshot = deepcopy(class_mixed)
        lifted = classes.lift_policy(class_mixed, self.model)
        self.assertNotIn("results", lifted)
        self.assertNotIn("physical_exact_metrics", lifted)
        roundtrip = classes.project_policy(lifted, self.model)
        self.assertEqual(class_mixed, compact_snapshot)
        self.assertEqual(set(roundtrip["policies"]), set(projected["policies"]))
        _compare_policy_rows(self, lifted, classes.lift_policy(roundtrip["result"], self.model))
        for key, probabilities in projected["policies"].items():
            self.assertEqual(roundtrip["policies"][key], tuple(
                action["probability"] for action in next(row for row in class_mixed["strategy"]
                    if (0 if row["player"] == "oop" else 1, row["hand"], tuple(row["history"])) == key)["actions"]))
        policies["class_mixed_lifted"] = lifted

        for name, payload in policies.items():
            audited = classes.audit_policy(payload, self.model)
            self.assertEqual(audited["training_calls"], 0)
            self.assertEqual(set(audited["generic_class_audits"]), {"scan", "partition"})
            exact = audited["full_physical_exact_metrics"]
            self.assertEqual(set(exact), set(METRICS))
            if name == "check_call":
                self.assertEqual(exact, CHECK_CALL)
            self._assert_unchanged_caps(audited["physical_oracle_counters"],
                                        audited["generic_class_audits"])
            self.assertEqual(audited["generic_class_audits"]["scan"]["metrics"], exact, name)
            self.assertEqual(audited["generic_class_audits"]["partition"]["metrics"], exact, name)
            self.assertEqual(audited["generic_class_audits"]["scan"]["metrics"],
                             audited["generic_class_audits"]["partition"]["metrics"], name)

    def test_class_model_rejects_balanced_mass_sign_type_and_mapping_corruption(self):
        bad = deepcopy(self.model)
        groups = defaultdict(list)
        for world in bad.class_worlds:
            groups[world["river"]].append(world)
        totals = {rep: sum((world["weight"] for world in rows), Fraction())
                  for rep, rows in groups.items()}
        for rep, rows in groups.items():
            for world in rows:
                world["weight"] = world["weight"] / totals[rep] / 7
        self.assertEqual(sum((w["weight"] for w in bad.class_worlds), Fraction()), 1)
        with self.assertRaises(ValueError):
            classes.validate_model(bad)

        for mutation in (
            lambda m: m.class_worlds.append(deepcopy(m.class_worlds[0])),
            lambda m: m.class_worlds[0].__setitem__("sign", 1 if m.class_worlds[0]["sign"] != 1 else -1),
            lambda m: m.class_worlds[0].__setitem__("sign", True),
            lambda m: m.class_worlds[0].__setitem__("weight", float(m.class_worlds[0]["weight"])),
            lambda m: m.river_class.__setitem__("2c", "Ac"),
            lambda m: m.river_class.__setitem__(("KcKd", "2c"), "2c"),
            lambda m: object.__setattr__(m, "class_members", (("fake", ("2c",)),) + tuple(m.class_members[1:])),
        ):
            corrupted = deepcopy(self.model)
            mutation(corrupted)
            with self.subTest(mutation=mutation), self.assertRaises((ValueError, TypeError)):
                classes.validate_model(corrupted)

    def test_class_tree_rejects_cycles_early_terminal_and_action_or_actor_mutation(self):
        cycle = deepcopy(self.model)
        root = cycle.class_root
        object.__setattr__(root, "children", (root,) + tuple(root.children[1:]))
        with self.assertRaises(ValueError):
            classes.validate_model(cycle)

        terminal = deepcopy(self.model)
        node = terminal.class_root
        object.__setattr__(node, "children", (rules._Terminal("fold", (0.0, 0.0), 0),)
                           + tuple(node.children[1:]))
        with self.assertRaises(ValueError):
            classes.validate_model(terminal)

        for field in ("player", "actions"):
            corrupted = deepcopy(self.model)
            node = corrupted.class_root
            if field == "player":
                object.__setattr__(node, "player", 1 - node.player)
            else:
                changed = replace(node.actions[0], amount=node.actions[0].amount + 7.0)
                object.__setattr__(node, "actions", (changed,) + tuple(node.actions[1:]))
            with self.subTest(field=field), self.assertRaises(ValueError):
                classes.validate_model(corrupted)

    def test_projection_rejects_per_card_deviation_and_malformed_physical_rows(self):
        deviation = reference.make_check_call_policy(self.game)
        row = _find_row(deviation, "ip", "KcKd", ("check", "check", "river@2c", "check"))
        self.assertTrue(any(a["name"] == "bet" for a in row["actions"]))
        for action in row["actions"]:
            action["probability"] = float(action["name"] == "bet")
        with self.assertRaisesRegex(ValueError, "class-constant"):
            classes.project_policy(deviation, self.model)

        base = reference.make_check_call_policy(self.game)
        first = base["strategy"][0]
        mutations = []
        missing = deepcopy(base); missing["strategy"].pop(); mutations.append(missing)
        extra = deepcopy(base); extra["strategy"].append(deepcopy(first)); mutations.append(extra)
        duplicate = deepcopy(base); duplicate["strategy"][-1] = deepcopy(first); mutations.append(duplicate)
        wrong_history = deepcopy(base)
        history_row = next(row for row in wrong_history["strategy"] if row["history"])
        history_row["history"][0] = "future@2c"
        mutations.append(wrong_history)
        wrong_board = deepcopy(base); wrong_board["strategy"][0]["board"][0] = "As"; mutations.append(wrong_board)
        wrong_action = deepcopy(base); wrong_action["strategy"][0]["actions"][0]["amount"] += 1.0; mutations.append(wrong_action)
        for value in (-0.1, 1.1, float("nan"), float("inf"), True, 0):
            bad = deepcopy(base)
            bad["strategy"][0]["actions"][0]["probability"] = value
            mutations.append(bad)
        bad_sum = deepcopy(base)
        actions = bad_sum["strategy"][0]["actions"]
        actions[0]["probability"] = 0.4
        if len(actions) > 1:
            actions[1]["probability"] = 0.4
        mutations.append(bad_sum)
        for index, bad in enumerate(mutations):
            with self.subTest(index=index), self.assertRaises((ValueError, TypeError)):
                classes.project_policy(bad, self.model)

    def test_lift_rejects_malformed_compact_rows_before_physical_template(self):
        physical = reference.make_check_call_policy(self.game)
        compact = classes.project_policy(physical, self.model)["result"]
        self.assertEqual(len(compact["strategy"]), 486)

        first = compact["strategy"][0]
        missing = deepcopy(compact)
        missing["strategy"].pop()
        duplicate = deepcopy(compact)
        duplicate["strategy"][-1] = deepcopy(first)
        extra = deepcopy(compact)
        extra["strategy"].append(deepcopy(first))
        bad_board = deepcopy(compact)
        next(row for row in bad_board["strategy"]
             if len(row["board"]) == 5)["board"][-1] = "??"
        bad_history = deepcopy(compact)
        next(row for row in bad_history["strategy"]
             if row["history"])["history"][0] = "future@2c"

        # False equals 0.0 in ordinary equality. These mutations specifically
        # require a type check rather than rejection for a different amount.
        amount_type = deepcopy(compact)
        next(action for row in amount_type["strategy"] for action in row["actions"]
             if action["amount"] == 0.0)["amount"] = False
        raise_type = deepcopy(compact)
        next(action for row in raise_type["strategy"] for action in row["actions"]
             if action["raise_to"] == 0.0)["raise_to"] = False
        nonfloat = deepcopy(compact)
        nonfloat["strategy"][0]["actions"][0]["probability"] = True
        out_of_bounds = deepcopy(compact)
        out_of_bounds["strategy"][0]["actions"][0]["probability"] = 1.1
        bad_sum = deepcopy(compact)
        for action in bad_sum["strategy"][0]["actions"]:
            action["probability"] = 0.0

        for label, candidate in (
                ("missing", missing), ("duplicate", duplicate), ("extra", extra),
                ("board", bad_board), ("history", bad_history),
                ("bool amount", amount_type), ("bool raise_to", raise_type),
                ("non-float probability", nonfloat),
                ("out-of-bounds probability", out_of_bounds), ("bad sum", bad_sum)):
            with self.subTest(case=label), mock.patch.object(
                    classes.reference, "make_check_call_policy",
                    side_effect=AssertionError("lift allocated physical template before input rejection")) as template:
                with self.assertRaises(ValueError):
                    classes.lift_policy(candidate, self.model)
                template.assert_not_called()

    def test_numeric_discrepancy_and_generic_caps_are_not_swallowed(self):
        payload = reference.make_check_call_policy(self.game)
        numeric_metrics = {name: float(value) for name, value in CHECK_CALL.items()}
        numeric_metrics["value_oop"] += 1e-8
        exact = {"metrics": CHECK_CALL, "counters": {}}
        with mock.patch.object(classes.rules, "replay_policy", return_value=numeric_metrics), \
             mock.patch.object(classes.physical_oracle, "audit_policy", return_value=exact), \
             mock.patch.object(classes.generic_exact, "evaluate_exact",
                               side_effect=AssertionError("audit passed numeric gate")) as generic:
            with self.assertRaisesRegex(ValueError, "disagree beyond tolerance"):
                classes.audit_policy(payload, self.model)
            generic.assert_not_called()
        with mock.patch.object(classes.rules, "replay_policy", return_value=numeric_metrics), \
             mock.patch.object(classes.physical_oracle, "audit_policy", return_value=exact), \
             mock.patch.object(classes, "_project_validated",
                               side_effect=AssertionError("projection passed numeric gate")):
            with self.assertRaisesRegex(ValueError, "disagree beyond tolerance"):
                classes.project_policy(payload, self.model)

        # Keep public/range/policy plumbing and the generic evaluator real. Stub
        # only the already independently covered physical exact lane.
        with mock.patch.object(classes.physical_oracle, "audit_policy", return_value=exact), \
             mock.patch.object(classes, "_MAX_AUDIT_WORK", 1):
            with self.assertRaises(ValueError):
                classes.audit_policy(payload, self.model)
        with mock.patch.object(classes.physical_oracle, "audit_policy", return_value=exact), \
             mock.patch.object(classes, "_MAX_FRACTION_BITS", 1):
            with self.assertRaises(ValueError):
                classes.audit_policy(payload, self.model)

if __name__ == "__main__":
    unittest.main()
