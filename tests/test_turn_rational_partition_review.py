"""Sol's correlated hand/river terminal-history enumeration witness."""
from copy import deepcopy
from fractions import Fraction as F
from itertools import product
import json
import unittest
from unittest.mock import Mock, patch

from scripts import audit_full_deck_turn_rational as auditor
from scripts.turn_rational_certificate import evaluate_exact
from scripts.turn_river_validation import _Action, _Chance, _Decision, _Terminal


def correlated_game():
    board = ("2c", "7d", "9h", "Kd")
    hands = (("AhAs", "KhKs"), ("QhQs", "JhJs"))
    rows = {
        (0, 0, "root"): (0.2, 0.8), (0, 1, "root"): (0.6, 0.4),
        (1, 0, "left"): (0.25, 0.75), (1, 1, "left"): (0.75, 0.25),
        (1, 0, "right"): (0.9, 0.1), (1, 1, "right"): (0.3, 0.7),
    }
    normalized = {}
    for key, values in rows.items():
        raw = tuple(F.from_float(value) for value in values)
        normalized[key] = tuple(value / sum(raw) for value in raw)
    masses = {(i, j, river): F(1 + 4 * i + 2 * j + river, 36)
              for i in (0, 1) for j in (0, 1) for river in (0, 1)}

    def terminal_history_value(replacements):
        value = F(0)
        for (i, j, river), mass in masses.items():
            def row(player, hand, history):
                return replacements.get((player, hand, history, river),
                    replacements.get((player, hand, history, None),
                                     normalized[player, hand, history]))
            left, right = row(0, i, "root")
            surrender, continue_left = row(1, j, "left")
            fold, continue_right = row(1, j, "right")
            sign = (1 if i == j else -1) * (1 if river == 0 else -1)
            value += mass * (
                left * (surrender * -13 + continue_left * sign * 63) +
                right * (fold * 13 + continue_right * sign * 13))
        return value

    expected_value = terminal_history_value({})
    legal, peek = [], []
    counts = []
    for player in (0, 1):
        base = [key for key in rows if key[0] == player]
        responses = []
        for future_visible in (False, True):
            keys = [(*key, river) for key in base
                    for river in ((0, 1) if future_visible else (None,))]
            values = []
            for choices in product((0, 1), repeat=len(keys)):
                replacements = {key: (F(choice == 0), F(choice == 1))
                                for key, choice in zip(keys, choices)}
                outcome = terminal_history_value(replacements)
                values.append(outcome if player == 0 else -outcome)
            responses.append(max(values))
            if not future_visible:
                counts.append(len(values))
        legal.append(responses[0])
        peek.append(responses[1])

    actions = (_Action("first"), _Action("second"))
    left_chance = _Chance(("left", "second"), {
        "3d": _Terminal("showdown", (50.0, 50.0)),
        "4d": _Terminal("showdown", (50.0, 50.0)),
        "5d": _Terminal("fold", (999.0, 999.0), 0),  # Empty bucket.
    })
    right_chance = _Chance(("right", "second"), {
        "3d": _Terminal("showdown", (0.0, 0.0)),
        "4d": _Terminal("showdown", (0.0, 0.0)),
    })
    left_node = _Decision(1, ("left",), board, actions,
                         (_Terminal("fold", (0.0, 0.0), 1), left_chance))
    right_node = _Decision(1, ("right",), board, actions,
                          (_Terminal("fold", (0.0, 0.0), 0), right_chance))
    root = _Decision(0, (), board, actions, (left_node, right_node))
    worlds = []
    for (i, j, river), mass in masses.items():
        private = tuple(tuple(hands[player][hand][k:k+2] for k in (0, 2))
                        for player, hand in ((0, i), (1, j)))
        worlds.append(dict(hands=private, river=("3d", "4d")[river], weight=mass,
                           sign=(1 if i == j else -1) * (1 if river == 0 else -1)))
    policies, serialized = {}, []
    for (player, hand, history), probabilities in rows.items():
        public_history = () if history == "root" else (history,)
        policies[player, hands[player][hand], public_history] = probabilities
        serialized.append(dict(player=("oop", "ip")[player], hand=hands[player][hand],
            street="turn", board=list(board), history=list(public_history),
            actions=[dict(name=action.name, amount=action.amount, raise_to=action.raise_to,
                          history_key=action.token, probability=probability)
                     for action, probability in zip(actions, probabilities)]))
    value = expected_value
    br0, br1 = legal
    metrics = dict(value_oop=value, value_ip=-value,
                   oop_best_response_value=br0, ip_best_response_value=br1,
                   oop_best_response_gain=br0-value, ip_best_response_gain=br1+value,
                   nash_conv=br0+br1, exploitability=(br0+br1)/2)
    return root, worlds, policies, {"strategy": serialized}, metrics, legal, peek, counts


class TurnRationalPartitionIndependentReviewTests(unittest.TestCase):
    def test_actual_saved_profile_with_self_consistent_wrong_bounds_is_rejected(self):
        parent, parent_rows, digest, case = auditor._pinned_parent(auditor.PARENT_REPORT)
        identity = ("matrix-free", 1000)
        actual = auditor._run_profile(identity, case, parent_rows[identity],
                                      auditor.POLICY_DIRECTORY)
        altered = deepcopy(actual)
        metrics = {key: F(value) for key, value in actual["exact_metrics"].items()}
        # Expand only the upper response bound by1/1000 and consistently update
        # every dependent exact identity. A local identity check accepts it;
        # fresh physical-policy recomputation must reject the false certificate.
        increment = F(1, 1000)
        for key in ("oop_best_response_value", "oop_best_response_gain", "nash_conv"):
            metrics[key] += increment
        metrics["exploitability"] += increment / 2
        altered["exact_metrics"] = {key: str(value) for key, value in metrics.items()}
        altered["upper_value_bound_fraction"] = str(F(actual["upper_value_bound_fraction"]) + increment)
        auditor._verify_fraction_row(altered)
        expected = dict(parent_report_canonical_sha256=digest, results=[altered])
        saved_path = Mock()
        saved_path.read_bytes.return_value = auditor._pretty_lf(expected)
        with self.assertRaisesRegex(ValueError, "fresh replay and exact recomputation"):
            auditor._verify_saved_artifact(saved_path, expected)

    def test_source_change_rejects_audit_even_after_all_six_profiles_pass(self):
        with patch.object(auditor, "_source_fingerprints",
                          side_effect=[{"source": "before"}, {"source": "after"}]):
            with patch.object(auditor, "_run_profile", wraps=auditor._run_profile) as replay:
                with self.assertRaisesRegex(RuntimeError, "changed during exact audit"):
                    auditor.audit()
                self.assertEqual(replay.call_count, 6)

    def test_partition_mode_rejects_intermediate_width_even_when_final_value_fits(self):
        # Every input and the final value20 fit five bits. The first exact
        # world contribution40/3 requires six bits and must not be rounded.
        root = _Chance((), {"L": _Terminal("showdown", (10.0, 10.0)),
                            "R": _Terminal("showdown", (10.0, 10.0))})
        worlds = [dict(hands=(("Ah", "As"), ("Kh", "Ks")), river="L",
                       weight=F(2, 3), sign=1),
                  dict(hands=(("Ah", "As"), ("Qh", "Qs")), river="R",
                       weight=F(1, 3), sign=1)]
        original = deepcopy(worlds)
        with self.assertRaisesRegex(ValueError, "bit limit"):
            evaluate_exact(root, worlds, {}, 20.0, result={"strategy": []},
                           chance_grouping="partition", max_bits=5)
        exact = evaluate_exact(root, worlds, {}, 20.0, result={"strategy": []},
                               chance_grouping="partition")
        self.assertEqual(exact["metrics"]["value_oop"], F(20))
        self.assertEqual(exact["maximum_fraction_bits"], 6)
        self.assertEqual(worlds, original)

    def test_correlated_future_and_hidden_hands_match_exhaustive_legal_responses(self):
        root, worlds, policies, payload, metrics, legal, peek, counts = correlated_game()
        self.assertEqual(counts, [4, 16])
        self.assertTrue(all(unfair > fair for unfair, fair in zip(peek, legal)))
        original = deepcopy((worlds, policies, payload))
        scan = evaluate_exact(root, worlds, policies, 26.0, result=payload)
        partition = evaluate_exact(root, worlds, policies, 26.0, result=payload,
                                   chance_grouping="partition")
        self.assertEqual(scan["metrics"], metrics)
        self.assertEqual(partition["metrics"], metrics)
        for field in ("normalization_ledger", "normalized_policy_rows", "max_row_adjustment",
                      "lower_value_bound", "upper_value_bound", "worlds", "tree_nodes",
                      "tree_depth", "threshold_met"):
            self.assertEqual(partition[field], scan[field], field)
        self.assertEqual((worlds, policies, payload), original)


if __name__ == "__main__":
    unittest.main()
