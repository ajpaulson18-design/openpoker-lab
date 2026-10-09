"""Known-value accuracy checks for each production configured CFR trainer.

The fixture is Kuhn poker encoded as a tiny fixed-board betting abstraction.
The published equilibrium value and the independent exhaustive policy oracle
make this a quality check, rather than only a backend-to-backend comparison.
"""
from fractions import Fraction
from math import fsum
import unittest

from pokerlab import cfr
from pokerlab.postflop_solver import (
    _chance_child,
    _chance_partitions,
    _node_key,
)
from pokerlab.river_tree import _terminal_value
from scripts.cfr_quality import (
    KNOWN_P1_VALUE,
    _direct_profile_value,
    _equilibrium_family,
    _independent_best_response,
    _ordered_worlds,
    build_kuhn_adapter,
    check_metrics,
    train_profile,
    verify_known_equilibrium_family,
)


class KnownKuhnQualityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.adapter = build_kuhn_adapter()
        cls.layout = cls.adapter["layout"]

    def assert_production_metrics_match_oracle(self, profile, oracle):
        adapter = self.adapter
        config = adapter["config"]
        payoff = lambda node, world: _terminal_value(node, world[3], config.pot)
        value = cfr.evaluate(adapter["root"], adapter["worlds"], profile,
                             payoff, _node_key, _chance_child)
        br0 = cfr.best_response(0, adapter["root"], adapter["worlds"],
                                profile, payoff, _node_key, _chance_partitions)
        br1 = cfr.best_response(1, adapter["root"], adapter["worlds"],
                                profile, payoff, _node_key, _chance_partitions)
        self.assertAlmostEqual(value, oracle["value_p1"], delta=1e-12)
        self.assertAlmostEqual(br0, oracle["p1_best_response"], delta=1e-12)
        self.assertAlmostEqual(br1, oracle["p2_best_response"], delta=1e-12)

    def test_production_tree_encodes_six_ordered_kuhn_deals(self):
        adapter = self.adapter
        self.assertEqual(adapter["config"].pot, 2.0)
        self.assertEqual(adapter["config"].stacks, (1.0, 1.0))
        self.assertEqual(len(adapter["worlds"]), 6)
        self.assertEqual(len(adapter["nodes"]), 4)
        self.assertEqual(len(adapter["infos"]), 12)
        self.assertEqual(
            {(world[0], world[1]) for world in adapter["worlds"]},
            {(first, second) for first in range(3) for second in range(3)
             if first != second},
        )
        self.assertEqual(fsum(world[2] for world in adapter["worlds"]), 1.0)

    def test_independent_oracle_matches_uniform_and_published_equilibrium_values(self):
        # Directly evaluate the uniform policy from the six ordered deals and
        # Kuhn terminal rules. Exhaustive private-hand policies give exact BRs.
        uniform = {key: [Fraction(1, 2), Fraction(1, 2)]
                   for key in self.adapter["infos"]}
        worlds = _ordered_worlds(exact=True)
        value = _direct_profile_value(uniform, uniform, worlds, self.layout)
        br0 = _independent_best_response(0, uniform, worlds, self.layout)
        br1 = _independent_best_response(1, uniform, worlds, self.layout)
        self.assertEqual(value, Fraction(1, 8))
        self.assertEqual(br0, Fraction(1, 2))
        self.assertEqual(br1, Fraction(5, 12))
        self.assertEqual(br0 - value, Fraction(3, 8))
        self.assertEqual(br1 + value, Fraction(13, 24))

        # Kuhn's published equilibrium family has value -1/18 and zero BR gain.
        proof = verify_known_equilibrium_family()
        self.assertEqual([row["alpha"] for row in proof], ["0", "1/6", "1/3"])
        for alpha in (Fraction(0), Fraction(1, 6), Fraction(1, 3)):
            profile = _equilibrium_family(alpha, self.layout)
            self.assertEqual(
                _direct_profile_value(profile, profile, worlds, self.layout),
                KNOWN_P1_VALUE,
            )
            self.assertEqual(
                _independent_best_response(0, profile, worlds, self.layout),
                KNOWN_P1_VALUE,
            )
            self.assertEqual(
                _independent_best_response(1, profile, worlds, self.layout),
                -KNOWN_P1_VALUE,
            )

    def test_production_metrics_match_the_independent_policy_oracle(self):
        # The common production evaluator and BR routines must match the
        # independent exact oracle on every member of Kuhn's equilibrium family.
        for alpha in (Fraction(0), Fraction(1, 6), Fraction(1, 3)):
            profile = _equilibrium_family(alpha, self.layout)
            oracle = check_metrics(profile, layout=self.layout)
            self.assert_production_metrics_match_oracle(profile, oracle)

    def test_all_trainers_reduce_known_game_gap(self):
        for algorithm, final_limit in (("vanilla", 0.01), ("dcfr", 0.003)):
            for backend in ("recursive", "planned", "public-batched"):
                with self.subTest(backend=backend, algorithm=algorithm):
                    reports = []
                    for iterations in (100, 1000, 10000):
                        profile = train_profile(iterations, algorithm, backend)
                        oracle = check_metrics(profile, layout=self.layout)
                        self.assert_production_metrics_match_oracle(profile, oracle)
                        reports.append((iterations, oracle))
                    _, start = reports[0]
                    _, middle = reports[1]
                    _, final = reports[2]
                    self.assertGreater(start["nash_conv"], 0.0)
                    self.assertLess(middle["nash_conv"], start["nash_conv"])
                    self.assertLess(final["nash_conv"], start["nash_conv"] / 5.0)
                    self.assertLess(final["nash_conv"], final_limit)
                    self.assertLess(final["value_error"], 0.001)


if __name__ == "__main__":
    unittest.main()
