"""Hand-computed completed-sweep/own-reach control across two chance reveals."""
from fractions import Fraction
import unittest
from unittest.mock import patch
from pokerlab import public_cfr
from pokerlab.postflop_solver import _Chance
from pokerlab.preflop_solver import _Action
from pokerlab.preflop_delayed_cfrplus import train_delayed_public_cfrplus
from pokerlab.river_tree import _Node, _Terminal


class FlopDelayedAveragingControlTests(unittest.TestCase):
    def test_hand_computed_delayed_completed_profiles_and_own_reach(self):
        terminal = _Terminal("showdown", (0., 0.))
        child_history = ("5c", "9h", "left")
        root_history = ("5c", "9h")
        child = _Node(child_history, 0, (_Action("a"), _Action("b")),
                      (terminal, terminal))
        decision = _Node(root_history, 0, (_Action("left"), _Action("right")),
                         (child, terminal))
        root = _Chance((), {"5c": _Chance(("5c",), {"9h": decision})})
        worlds = ((0, 0, 1., 1, "5c", "9h"),)
        root_key, child_key = (0, 0, root_history), (0, 0, child_history)
        infos = {root_key: 2, child_key: 2}
        # Independent, prescribed regret increments create the completed profiles
        # root: (1/4,3/4), (2/3,1/3), (1/7,6/7);
        # child: (1,0), (1/4,3/4), (4/5,1/5).
        # Mocking regret deltas isolates averaging, not Hold'em utility or BRs.
        increments = (((1,3),(4,0)), ((3,-1),(-3,3)), ((-3,4),(3,-2)))
        for delay, expected_root, expected_child in (
                (0, Fraction(169,504), Fraction(389,845)),
                (1, Fraction(20,63), Fraction(83,200))):
            calls = []
            def deltas(_root, _edges, _infos, current, player, *_args):
                sweep = len(calls) // 2
                calls.append(player)
                if player == 1:
                    # The opponent sweep sees the newly updated OOP profile.
                    expected = (Fraction(1,4), Fraction(2,3), Fraction(1,7))[sweep]
                    self.assertAlmostEqual(current[root_key][0], float(expected), delta=1e-15)
                    return {}
                first, second = increments[sweep]
                return {root_key: first, child_key: second}
            with self.subTest(delay=delay), patch.object(
                    public_cfr, "_cfrplus_target_deltas", side_effect=deltas):
                result = train_delayed_public_cfrplus(
                    root, worlds, infos, 3, averaging_delay=delay,
                    pot=10., chance_type=_Chance)
            self.assertEqual(calls, [0,1,0,1,0,1])
            self.assertAlmostEqual(result[root_key][0], float(expected_root), delta=1e-15)
            self.assertAlmostEqual(result[child_key][0], float(expected_child), delta=1e-15)
            for row in result.values():
                self.assertAlmostEqual(sum(row), 1., delta=1e-15)


if __name__ == "__main__":
    unittest.main()
