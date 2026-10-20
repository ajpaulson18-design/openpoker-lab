"""Parity regression for the CFR+ targeted rematch traversal."""
import hashlib
import json
import os
from pathlib import Path
import unittest

from pokerlab import flop_checkdown_solver
from pokerlab.native_fixed_street import train_native_fixed_street
from pokerlab.public_cfr import train_public_batched
from pokerlab.river_tree import _Action, _Node, _Terminal
from tests.test_native_fixed_street import _independent_metrics


BUILD_DIRECTORY = os.environ.get("OPENPOKER_NATIVE_TRAIN_BUILD_DIR")
NATIVE_AVAILABLE = bool(BUILD_DIRECTORY and Path(BUILD_DIRECTORY).is_dir())
POT = 6.0
ITERATIONS = (1, 2, 3, 10, 100, 1000, 4000)


def _fixture():
    """A deep repeated-actor tree with sparse hands and a zero signed pair."""
    fold_to_oop = _Terminal("fold", (1.0, 0.0), winner=0)
    call_oop = _Terminal("showdown", (1.0, 1.0))
    ip_after_oop_bet = _Node(
        history=("bet@1",), player=1,
        actions=(_Action("fold"), _Action("call", 1.0, 1.0)),
        children=(fold_to_oop, call_oop),
    )

    # Every private hand receives identical utility from the two actions here,
    # giving the native CFR+ rematch path a genuine zero-regret actor row.
    zero_regret_oop = _Node(
        history=("check", "check"), player=0,
        actions=(_Action("check"), _Action("bet", 1.0, 1.0)),
        children=(_Terminal("showdown", (0.0, 0.0)),
                  _Terminal("showdown", (0.0, 0.0))),
    )

    fold_to_ip = _Terminal("fold", (0.0, 1.0), winner=1)
    call_ip = _Terminal("showdown", (1.0, 1.0))
    oop_after_ip_bet = _Node(
        history=("check", "bet@1"), player=0,
        actions=(_Action("fold"), _Action("call", 1.0, 1.0)),
        children=(fold_to_ip, call_ip),
    )
    ip_after_check = _Node(
        history=("check",), player=1,
        actions=(_Action("check"), _Action("bet", 1.0, 1.0)),
        children=(zero_regret_oop, oop_after_ip_bet),
    )
    root = _Node(
        history=(), player=0,
        actions=(_Action("check"), _Action("bet", 1.0, 1.0)),
        children=(ip_after_check, ip_after_oop_bet),
    )

    # Pair (7,20) has positive joint mass but zero signed showdown measure;
    # hand IDs are intentionally sparse, and hand 20 faces two hidden OOP hands.
    worlds = ((3, 20, 0.25, 0.15), (7, 20, 0.25, 0.0), (7, 41, 0.50, -0.20))
    infos = {}
    for node in (root, zero_regret_oop, oop_after_ip_bet):
        for hand in (3, 7):
            infos[(0, hand, node.history)] = len(node.actions)
    for node in (ip_after_check, ip_after_oop_bet):
        for hand in (20, 41):
            infos[(1, hand, node.history)] = len(node.actions)

    # Expand each (mass, signed mass) pair into ordinary payoff categories for
    # the independent small-tree value and best-response calculation.
    reference_worlds = (
        (3, 20, 0.20, 1.0), (3, 20, 0.05, -1.0),
        (7, 20, 0.25, 0.0),
        (7, 41, 0.15, 1.0), (7, 41, 0.35, -1.0),
    )
    return root, worlds, infos, reference_worlds, zero_regret_oop


def _policy_digest(policy):
    rows = [[player, hand, list(history), list(probabilities)]
            for (player, hand, history), probabilities in sorted(
                policy.items(), key=lambda item: item[0])]
    payload = json.dumps(rows, separators=(",", ":"), allow_nan=False).encode("ascii")
    return hashlib.sha256(payload).hexdigest()


def _assert_policies_equal(testcase, native, python):
    testcase.assertEqual(set(native), set(python))
    for key in sorted(python):
        testcase.assertEqual(len(native[key]), len(python[key]), key)
        for got, want in zip(native[key], python[key]):
            testcase.assertAlmostEqual(got, want, delta=1e-8, msg=repr(key))


@unittest.skipUnless(NATIVE_AVAILABLE,
                     "Set OPENPOKER_NATIVE_TRAIN_BUILD_DIR to the explicit rematch build")
class NativeCFRPlusRematchParityTests(unittest.TestCase):
    def test_deep_repeated_actor_tree_matches_python_all_algorithms_and_checkpoints(self):
        root, worlds, infos, reference_worlds, zero_regret_oop = _fixture()
        self.assertEqual({key[1] for key in infos if key[0] == 0}, {3, 7})
        self.assertEqual({key[1] for key in infos if key[0] == 1}, {20, 41})
        self.assertEqual(worlds[1], (7, 20, 0.25, 0.0))
        zero_keys = [(0, hand, zero_regret_oop.history) for hand in (3, 7)]

        for algorithm in ("vanilla", "dcfr", "cfrplus"):
            for iterations in ITERATIONS:
                with self.subTest(algorithm=algorithm, iterations=iterations):
                    python_policy = train_public_batched(
                        root, reference_worlds, infos, iterations, algorithm, pot=POT,
                        chance_type=flop_checkdown_solver._NoPublicChance)
                    native_policy, metadata = train_native_fixed_street(
                        root, worlds, infos, iterations, algorithm, pot=POT,
                        build_directory=BUILD_DIRECTORY, reduction="public-batched")
                    self.assertEqual(metadata["reduction"], "public-batched")
                    _assert_policies_equal(self, native_policy, python_policy)

                    for key in zero_keys:
                        self.assertEqual(native_policy[key], [0.5, 0.5])
                    if algorithm == "cfrplus" and iterations == 1:
                        # The first update makes OOP hand 3's root check reach
                        # zero; its downstream zero-regret row must still get
                        # the same normalized fallback in the native result.
                        self.assertEqual(native_policy[(0, 3, ())][0], 0.0)
                        self.assertEqual(native_policy[(0, 3, zero_regret_oop.history)],
                                         [0.5, 0.5])
                    python_metrics = _independent_metrics(
                        root, reference_worlds, python_policy, POT)
                    native_metrics = _independent_metrics(
                        root, reference_worlds, native_policy, POT)
                    for got, want in zip(native_metrics, python_metrics):
                        self.assertAlmostEqual(got, want, delta=1e-9)

                    if iterations == 4000:
                        repeated, _ = train_native_fixed_street(
                            root, worlds, infos, iterations, algorithm, pot=POT,
                            build_directory=BUILD_DIRECTORY, reduction="public-batched")
                        self.assertEqual(_policy_digest(native_policy),
                                         _policy_digest(repeated))


if __name__ == "__main__":
    unittest.main()
