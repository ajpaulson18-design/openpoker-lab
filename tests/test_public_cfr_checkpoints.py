"""Public trainer checkpoint scheduling and snapshot ownership checks."""
import unittest

from pokerlab.public_cfr import train_public_batched
from pokerlab.river_tree import _Node, _Terminal


def _tiny_game():
    # One decision with chip-valued showdown outcomes. The exact policy is
    # intentionally uninteresting; this isolates the public callback contract.
    root = _Node((), 0, ("safe", "swing"), (
        _Terminal("showdown", (0.0, 0.0)),
        _Terminal("showdown", (6.0, 6.0)),
    ))
    worlds = [(0, 0, 1.0, -1)]
    infos = {(0, 0, ()): 2}
    return root, worlds, infos


class PublicCFRCheckpointTests(unittest.TestCase):
    def test_nondivisible_budget_emits_completed_interval_and_final_snapshots(self):
        root, worlds, infos = _tiny_game()
        seen = []

        def callback(iteration, fresh_average):
            seen.append((iteration, fresh_average))
            return False

        result = train_public_batched(
            root, worlds, infos, 13, "vanilla", pot=20,
            chance_type=type("NoChance", (), {}),
            checkpoint_interval=5, checkpoint_callback=callback,
        )
        self.assertEqual([iteration for iteration, _ in seen], [5, 10, 13])
        self.assertEqual(result, seen[-1][1])
        for _, profile in seen:
            self.assertAlmostEqual(sum(profile[(0, 0, ())]), 1.0)

    def test_early_stop_returns_policy_for_completed_stop_iteration(self):
        root, worlds, infos = _tiny_game()
        seen = []

        def callback(iteration, fresh_average):
            seen.append(iteration)
            return iteration == 7

        stopped = train_public_batched(
            root, worlds, infos, 20, "vanilla", pot=20,
            chance_type=type("NoChance", (), {}),
            checkpoint_interval=7, checkpoint_callback=callback,
        )
        expected = train_public_batched(
            root, worlds, infos, 7, "vanilla", pot=20,
            chance_type=type("NoChance", (), {}),
        )
        self.assertEqual(seen, [7])
        self.assertEqual(stopped, expected)

    def test_mutating_snapshot_does_not_change_trainer_average(self):
        root, worlds, infos = _tiny_game()
        baseline = train_public_batched(
            root, worlds, infos, 11, "vanilla", pot=20,
            chance_type=type("NoChance", (), {}),
        )

        def callback(iteration, snapshot):
            snapshot[(0, 0, ())][:] = [1.0, 0.0]
            return False

        actual = train_public_batched(
            root, worlds, infos, 11, "vanilla", pot=20,
            chance_type=type("NoChance", (), {}),
            checkpoint_interval=4, checkpoint_callback=callback,
        )
        self.assertEqual(actual, baseline)

    def test_checkpoint_options_must_be_paired_and_interval_must_be_positive_int(self):
        root, worlds, infos = _tiny_game()
        no_chance = type("NoChance", (), {})
        with self.assertRaises(ValueError):
            train_public_batched(root, worlds, infos, 10, pot=20,
                                 chance_type=no_chance, checkpoint_interval=3)
        with self.assertRaises(ValueError):
            train_public_batched(root, worlds, infos, 10, pot=20,
                                 chance_type=no_chance,
                                 checkpoint_callback=lambda *_: False)
        for interval in (True, 0, -1, 2.5):
            with self.subTest(interval=interval), self.assertRaises(ValueError):
                train_public_batched(
                    root, worlds, infos, 10, pot=20, chance_type=no_chance,
                    checkpoint_interval=interval,
                    checkpoint_callback=lambda *_: False,
                )


if __name__ == "__main__":
    unittest.main()
