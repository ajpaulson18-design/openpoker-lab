"""Input-boundary and mathematical controls for the frozen Q52 bridge."""
from dataclasses import replace
from fractions import Fraction
from types import MappingProxyType
import unittest

from scripts.matrix_free_certificate_budget import Budget
from tests.virtual_grid_update_reference import (
    Fixture, Q, freeze_grid, raw_joint_update, sampled_grid_update,
    build_sampled_reference_context, admit_sampled_board, new_experiment_budget,
    complete_expectation,
)


class GridUpdateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.context = build_sampled_reference_context()
        cls.fixture = Fixture()
        cls.policy = cls.fixture.grid()
        cls.grid = freeze_grid(cls.fixture, cls.policy)

    def test_complete_snapshot_and_non_power_two_units(self):
        self.assertEqual(len(self.grid.units), 24420)
        self.assertEqual(sum(map(len, self.grid.units.values())), 58164)
        self.assertTrue(any(len(v) == 3 and v[0] not in (0, Q, Q//2, Q//4) for v in self.grid.units.values()))
        policy = dict(self.policy)
        k = next(iter(policy))
        original = self.grid.units[k]
        policy[k] = (Q,) + (0,)*(len(original)-1)
        self.assertEqual(self.grid.units[k], original)
        with self.assertRaises(TypeError):
            self.grid.units[k] = policy[k]

    def test_partition_and_inventory_rejection(self):
        k = next(iter(self.policy))
        for value in ((True,)*(len(self.policy[k])), (Q,)*len(self.policy[k]), (-1,)*len(self.policy[k])):
            with self.subTest(value=value), self.assertRaises(ValueError):
                freeze_grid(self.fixture, {**self.policy, k:value})
        missing = dict(self.policy); del missing[k]
        with self.assertRaises(ValueError):
            freeze_grid(self.fixture, missing)

    def test_resource_limits_are_reduce_only_and_reserved_first(self):
        with self.assertRaises(ValueError):
            new_experiment_budget(self.context, {'created_bits':16_000_000_001})
        with self.assertRaises(ValueError):
            new_experiment_budget(self.context, {'integer_bits':100})
        with self.assertRaises(ValueError):
            new_experiment_budget(self.context, {'work':200_000_000})

    def test_zero_target_board_retains_average(self):
        admission = next(a for b in self.context.physical.proposals
                         if not (a:=admit_sampled_board(self.context,b)).compatible_pairs)
        rows, root = sampled_grid_update(self.context, admission, self.grid, Budget())
        self.assertEqual(root, 0)
        self.assertTrue(any(any(avg) for _,avg in rows.values()))
        self.assertTrue(all(not any(raw) for raw,_ in rows.values()))

    def test_changed_admission_rejected_before_walk(self):
        a = admit_sampled_board(self.context,self.context.physical.proposals[0])
        with self.assertRaisesRegex(ValueError,'fields changed'):
            sampled_grid_update(self.context,replace(a,board_probability=Fraction(1)),self.grid,Budget())

    def test_zero_target_future_has_identical_earlier_street_averages(self):
        positive = {w.board for w in self.fixture.worlds}
        for length in (0,3,4):
            representatives = {b[:length]:b for b in positive}
            zero_board = next(b for b in self.context.physical.proposals
                              if b not in positive and b[:length] in representatives)
            prefix = zero_board[:length]
            future = representatives[prefix]
            outputs = []
            for board in (zero_board,future):
                rows,_ = sampled_grid_update(self.context,admit_sampled_board(self.context,board,'river_weighted'),
                                             self.grid,Budget())
                outputs.append({k:tuple(v[1]) for k,v in rows.items() if self.grid.prefixes[k]==prefix})
            with self.subTest(length=length):
                self.assertEqual(outputs[0],outputs[1])
                self.assertTrue(any(any(v) for v in outputs[0].values()))

    def test_inconsistent_snapshot_rejected_by_both_oracles(self):
        changed = replace(self.grid, probabilities=MappingProxyType({}))
        a=admit_sampled_board(self.context,self.context.physical.proposals[0])
        with self.assertRaisesRegex(ValueError,'snapshot fields changed'):
            sampled_grid_update(self.context,a,changed,Budget())
        with self.assertRaisesRegex(ValueError,'snapshot fields changed'):
            raw_joint_update(self.fixture,changed)
        with self.assertRaisesRegex(ValueError,'snapshot fields changed'):
            raw_joint_update(self.fixture,replace(self.grid,digest='0'*64))

    def test_snapshot_hash_binds_hidden_future_independent_rows(self):
        self.assertEqual(self.grid.digest,freeze_grid(self.fixture,dict(reversed(tuple(self.policy.items())))).digest)
        k = next(k for k,v in self.policy.items() if len(v)>1)
        p = dict(self.policy);p[k]=(Q,)+(0,)*(len(p[k])-1)
        self.assertNotEqual(self.grid.digest,freeze_grid(self.fixture,p).digest)
        self.assertEqual(set(map(len,self.grid.prefixes.values())),{0,3,4,5})

    def test_translation_requires_normalized_nonnegative_worlds_and_stakes(self):
        saved = self.fixture.stakes
        try:
            self.fixture.stakes = {**saved, next(iter(saved)):Fraction(9)}
            with self.assertRaisesRegex(ValueError,'preconditions'):
                raw_joint_update(self.fixture,self.grid)
        finally:
            self.fixture.stakes = saved

    def test_clipping_does_not_commute_with_expectation(self):
        # A raw unbiased +/-1 estimator at R=0 does not imply an unbiased
        # CFR+ accumulator. The bridge must never claim otherwise.
        self.assertEqual(sum((Fraction(-1,2),Fraction(1,2))),0)
        self.assertNotEqual((max(0,-1)+max(0,1))/2,max(0,0))

    def test_complete_two_law_expectation_with_zero_and_non_power_two_policy(self):
        # Keep the q-free and proposal walkers separate; compare every signed
        # action delta and average contribution, rather than only root value.
        from scripts.run_frozen_grid_update_study import profile
        grid = freeze_grid(self.fixture,profile(self.fixture,'zero-skew'))
        expected = raw_joint_update(self.fixture,grid)
        for law in ('uniform','river_weighted'):
            with self.subTest(law=law):
                budget = new_experiment_budget(self.context)
                actual = complete_expectation(self.context,grid,law,budget)
                self.assertEqual(actual,expected)
                self.assertLess(budget.created_bits,budget.limits['created_bits'])


if __name__ == '__main__':
    unittest.main()
