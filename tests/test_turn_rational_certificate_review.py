"""Sol's independent terminal-history and exhaustive hidden-policy crosscheck."""
from copy import deepcopy
from fractions import Fraction as F
from itertools import product
import json
import unittest
from unittest.mock import Mock, patch

from scripts import audit_turn_rational_certificate as auditor
from scripts.benchmark_turn_river_independent import ROOT
from scripts.turn_rational_certificate import evaluate_exact
from scripts.turn_river_validation import _Action, _Decision, _Terminal


class RationalCertificateIndependentReviewTests(unittest.TestCase):
    def test_relabelled_parent_is_rejected_before_any_policy_replay(self):
        parent = ROOT / "benchmarks/results/turn-selected-accuracy-v1.json"
        relabelled = json.loads(parent.read_text(encoding="utf-8"))
        relabelled["results"][0]["policy_sha256"] = "0" * 64
        path = Mock()
        path.read_text.return_value = json.dumps(relabelled)
        with patch.object(auditor.validator, "replay_policy",
                          side_effect=AssertionError("replay preceded parent pin")):
            with self.assertRaisesRegex(ValueError, "pinned canonical digest"):
                auditor.audit(path, ROOT / "benchmarks/results")

    def test_changed_policy_bytes_are_rejected_before_any_policy_replay(self):
        parent = ROOT / "benchmarks/results/turn-selected-accuracy-v1.json"
        policies = ROOT / "benchmarks/results/turn-selected-accuracy-policies-v1"

        class ChangedPolicyDirectory:
            def __truediv__(self, filename):
                path = Mock()
                # Same JSON meaning, different raw bytes. The provenance pin
                # must reject this before any numeric replay/model construction.
                path.read_bytes.return_value = (policies / filename).read_bytes() + b" "
                return path

        with patch.object(auditor.validator, "replay_policy",
                          side_effect=AssertionError("replay preceded policy pin")):
            with self.assertRaisesRegex(ValueError, "pinned approved policy"):
                auditor.audit(parent, ChangedPolicyDirectory())

    def test_source_change_during_audit_rejects_all_completed_certificate_rows(self):
        parent = ROOT / "benchmarks/results/turn-selected-accuracy-v1.json"
        policies = ROOT / "benchmarks/results/turn-selected-accuracy-policies-v1"
        with patch.object(auditor, "_source_fingerprints",
                          side_effect=[{"model.py": "before"}, {"model.py": "after"}]):
            with self.assertRaisesRegex(RuntimeError, "Source files changed"):
                auditor.audit(parent, policies)

    def test_intermediate_fraction_width_rejects_even_when_final_value_would_fit(self):
        # Final EV is exactly20 (five bits). The first exact physical term
        # is40/3, whose numerator needs six bits. A final-only cap misses it.
        root = _Terminal("showdown", (10.0, 10.0))
        worlds = [dict(hands=(("Ah", "As"), ("Kh", "Ks")), river=None,
                       weight=F(2, 3), sign=1),
                  dict(hands=(("Ah", "As"), ("Qh", "Qs")), river=None,
                       weight=F(1, 3), sign=1)]
        before = deepcopy(worlds)
        with self.assertRaisesRegex(ValueError, "bit limit"):
            evaluate_exact(root, worlds, {}, 20.0, result={"strategy": []},
                           max_bits=5)
        self.assertEqual(worlds, before)
        full = evaluate_exact(root, worlds, {}, 20.0, result={"strategy": []})
        self.assertEqual(full["metrics"]["value_oop"], F(20))
        self.assertEqual(full["maximum_fraction_bits"], 6)

    def test_wide_tree_is_rejected_before_expanding_its_children(self):
        class UnexpandableChildren:
            def __len__(self):
                return 100_001

            def __iter__(self):
                raise AssertionError("wide child allocation was attempted before admission")

        root = _Decision(0, (), (), (), UnexpandableChildren())
        with self.assertRaisesRegex(ValueError, "work limit"):
            evaluate_exact(root, [], {}, 20.0, result={"strategy": []})

    def test_correlated_hidden_hands_match_all_legal_pure_responses_exactly(self):
        # These deliberately correlated physical masses prevent independent
        # private marginal normalization from accidentally giving the answer.
        hands = (("AhAs", "KhKs"), ("QhQs", "JhJs"))
        masses = {(0, 0): F(1, 10), (0, 1): F(2, 10),
                  (1, 0): F(3, 10), (1, 1): F(4, 10)}
        signs = {(0, 0): 1, (0, 1): -1, (1, 0): -1, (1, 1): 1}
        # Exact binary64 normalization is intentional: .1+.9 need not be
        # exactly one when the two stored floats are viewed as rationals.
        raw = {
            (0, hands[0][0], ()): (0.2, 0.8),
            (0, hands[0][1], ()): (0.6, 0.4),
            (1, hands[1][0], ("left",)): (0.25, 0.75),
            (1, hands[1][1], ("left",)): (0.75, 0.25),
            (1, hands[1][0], ("right",)): (0.9, 0.1),
            (1, hands[1][1], ("right",)): (0.3, 0.7),
        }
        normalized = {}
        for key, row in raw.items():
            exact = tuple(F.from_float(value) for value in row)
            normalized[key] = tuple(value / sum(exact) for value in exact)

        # The expected value is a separately written terminal-history equation.
        # No numeric-tree traversal, production evaluator or BR supplies it.
        def direct_value(policy):
            answer = F(0)
            for (i, j), mass in masses.items():
                left, right = policy[(0, hands[0][i], ())]
                surrender, showdown = policy[(1, hands[1][j], ("left",))]
                fold, call = policy[(1, hands[1][j], ("right",))]
                sign = signs[i, j]
                answer += mass * (
                    left * (surrender * -13 + showdown * sign * 13) +
                    right * (fold * 13 + call * sign * 20))
            return answer

        value = direct_value(normalized)
        responses = []
        enumeration_counts = []
        for player in (0, 1):
            keys = [key for key in raw if key[0] == player]
            values = []
            for choices in product((0, 1), repeat=len(keys)):
                candidate = dict(normalized)
                for key, choice in zip(keys, choices):
                    candidate[key] = (F(choice == 0), F(choice == 1))
                outcome = direct_value(candidate)
                values.append(outcome if player == 0 else -outcome)
            enumeration_counts.append(len(values))
            responses.append(max(values))
        self.assertEqual(enumeration_counts, [4, 16])

        board = ("2c", "7d", "9h", "Kd", "3d")
        actions = (_Action("first"), _Action("second"))
        left = _Decision(1, ("left",), board, actions,
                         (_Terminal("fold", (0.0, 0.0), 1),
                          _Terminal("showdown", (0.0, 0.0))))
        right = _Decision(1, ("right",), board, actions,
                          (_Terminal("fold", (0.0, 7.0), 0),
                           _Terminal("showdown", (7.0, 7.0))))
        root = _Decision(0, (), board, actions, (left, right))
        worlds = []
        for (i, j), mass in masses.items():
            worlds.append({"hands": (tuple(hands[0][i][k:k + 2] for k in (0, 2)),
                                      tuple(hands[1][j][k:k + 2] for k in (0, 2))),
                           "river": None, "board": board,
                           "weight": mass, "sign": signs[i, j]})
        rows = []
        for (player, hand, history), probabilities in raw.items():
            rows.append({
                "player": "oop" if player == 0 else "ip", "hand": hand,
                "street": "river", "board": list(board), "history": list(history),
                "actions": [dict(name=action.name, amount=action.amount,
                                 raise_to=action.raise_to, history_key=action.token,
                                 probability=probability)
                            for action, probability in zip(actions, probabilities)],
            })
        result = {"strategy": rows}
        before = deepcopy((worlds, raw, result))
        exact = evaluate_exact(root, worlds, raw, 26.0, result=result)
        br0, br1 = responses
        gap = br0 + br1
        expected = {"value_oop": value, "value_ip": -value,
                    "oop_best_response_value": br0, "ip_best_response_value": br1,
                    "oop_best_response_gain": br0 - value,
                    "ip_best_response_gain": br1 + value,
                    "nash_conv": gap, "exploitability": gap / 2}
        self.assertEqual(exact["metrics"], expected)
        self.assertEqual(exact["lower_value_bound"], -br1)
        self.assertEqual(exact["upper_value_bound"], br0)
        self.assertGreater(exact["max_row_adjustment"], 0)
        self.assertEqual((worlds, raw, result), before)


if __name__ == "__main__":
    unittest.main()
