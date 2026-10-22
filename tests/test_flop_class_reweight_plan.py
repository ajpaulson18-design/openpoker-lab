from fractions import Fraction
import unittest

from scripts.flop_class_reweight_plan import plan_weights


def _priors(plan):
    return tuple(row[2] for row in plan.exact_pair_priors)


class ReweightPlanTests(unittest.TestCase):
    def test_small_inputs_with_oversized_derived_joint_mass_reject_early(self):
        large = 1 << 127
        weights = tuple(Fraction(large-n, large-n-2) for n in (1, 5, 9, 13))
        with self.assertRaisesRegex(ValueError, "Derived joint world masses"):
            plan_weights(weights[:2], weights[2:])

    def test_baseline_weights_preserve_one_global_blocker_normalizer(self):
        plan = plan_weights((1, Fraction(1, 2)), (Fraction(1, 4), 1))
        self.assertEqual(plan.global_blocker_normalizer, Fraction(13, 8))
        self.assertEqual(_priors(plan), (Fraction(8, 13), Fraction(1, 13), Fraction(4, 13)))
        self.assertEqual(plan.physical_world_forecast, 5940)
        self.assertEqual(plan.ordered_runouts_per_pair, 1980)

    def test_uniform_and_skew_priors(self):
        uniform = plan_weights((1, 1), (1, 1))
        self.assertEqual(uniform.global_blocker_normalizer, 3)
        self.assertEqual(_priors(uniform), (Fraction(1, 3),) * 3)
        skew = plan_weights((4, 1), (4, 1))
        self.assertEqual(skew.global_blocker_normalizer, 9)
        self.assertEqual(_priors(skew), (Fraction(4, 9), Fraction(4, 9), Fraction(1, 9)))

    def test_seatwise_scaling_does_not_change_conditioned_pair_priors(self):
        original = plan_weights((1, Fraction(1, 2)), (Fraction(1, 4), 1))
        scaled = plan_weights((7, Fraction(7, 2)), (Fraction(3, 4), 3))
        self.assertEqual(_priors(scaled), _priors(original))
        self.assertEqual(scaled.global_blocker_normalizer,
                         21 * original.global_blocker_normalizer)

    def test_plan_is_immutable_and_scoped(self):
        plan = plan_weights((1, 1), (1, 1))
        with self.assertRaises(AttributeError):
            plan.physical_world_forecast = 0
        self.assertIn("Planning only", plan.scope)

    def test_rejects_malformed_types_and_nonpositive_weights(self):
        invalid = ((True, 1), (1.0, 1), ("1", 1), (Fraction(0), 1),
                   (Fraction(-1, 2), 1), [1, 1], (1,))
        for weights in invalid:
            with self.subTest(weights=weights), self.assertRaises(ValueError):
                plan_weights(weights, (1, 1))
        with self.assertRaises(ValueError):
            plan_weights((1, 1), (False, 1))

    def test_rejects_oversized_components_before_pair_products(self):
        too_large = 1 << 128
        with self.assertRaisesRegex(ValueError, "bit bound"):
            plan_weights((too_large, 1), (1, 1))
        with self.assertRaisesRegex(ValueError, "bit bound"):
            plan_weights((Fraction(1, too_large), 1), (1, 1))


if __name__ == "__main__":
    unittest.main()
