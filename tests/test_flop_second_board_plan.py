from dataclasses import FrozenInstanceError, replace
from fractions import Fraction
import unittest
from unittest import mock

from scripts import flop_second_board_plan as plan_module


class SecondBoardPlanTests(unittest.TestCase):
  def test_fixed_fixture_exact_blocker_conditioned_plan_and_admission(self):
    plan = plan_module.plan_second_board()
    self.assertEqual(plan.board, ("7c", "8d", "9h"))
    self.assertEqual(plan.oop_ranges, (("AsAd", Fraction(1)), ("QsQd", Fraction(1, 2))))
    self.assertEqual(plan.ip_ranges, (("AsKh", Fraction(1, 4)), ("KsKd", Fraction(1))))
    self.assertEqual(plan.compatible_pair_raw_products, (
        ("AsAd", "KsKd", Fraction(1)),
        ("QsQd", "AsKh", Fraction(1, 8)),
        ("QsQd", "KsKd", Fraction(1, 2)),
    ))
    self.assertEqual(plan.global_blocker_normalizer, Fraction(13, 8))
    self.assertEqual(plan.exact_pair_priors, (
        ("AsAd", "KsKd", Fraction(8, 13)),
        ("QsQd", "AsKh", Fraction(1, 13)),
        ("QsQd", "KsKd", Fraction(4, 13)),
    ))
    self.assertEqual(plan.canonical_pair_identities, (
        ("AdAs", "KdKs", "AsAd", "KsKd"),
        ("QdQs", "AsKh", "QsQd", "AsKh"),
        ("QdQs", "KdKs", "QsQd", "KsKd"),
    ))
    self.assertEqual(plan.ordered_runouts_per_pair, 1980)
    self.assertEqual(plan.distinct_turn_card_forecast, 49)
    self.assertEqual(plan.physical_world_forecast, 5940)
    audit = plan_module.admit_plan(plan)
    self.assertEqual(audit["physical_world_forecast"], 5940)
    self.assertEqual(audit["distinct_turn_card_forecast"], 49)
    self.assertIs(audit["class_tree_equivalence_claim"], False)
    self.assertEqual(audit["existing_limits_reference_only"]["physical_oracle"]["max_worlds"], 7920)
    self.assertEqual(audit["existing_limits_reference_only"]["candidate_partition"]["max_worlds"], 5940)


  def test_admission_does_not_prepare_or_rank(self):
    from scripts import flop_multistreet_validation as physical
    from scripts import flop_public_classes_candidate as candidate

    def forbidden(*args, **kwargs):
        raise AssertionError("planning must not allocate or rank a model")

    with mock.patch.object(physical, "prepare_oracle", forbidden, create=True), \
         mock.patch.object(candidate, "build_candidate", forbidden, create=True):
      self.assertEqual(plan_module.admit_plan()["compatible_pair_count"], 3)


  def test_canonical_hand_identities_match_physical_parser_without_world_build(self):
    from scripts import flop_multistreet_validation as physical
    plan = plan_module.plan_second_board()
    for role, rows in (("oop", plan.oop_ranges), ("ip", plan.ip_ranges)):
      parser_rows = [[label, f"{weight.numerator}/{weight.denominator}"]
                     for label, weight in rows]
      parsed = physical._hand_rows(parser_rows, plan.board)
      expected = tuple((tuple(sorted((label[:2], label[2:]))), weight)
                       for label, weight in rows)
      self.assertEqual(parsed, expected, role)
    canonical_hands = {hand for row in plan.canonical_pair_identities for hand in row[:2]}
    self.assertIn("AsKh", canonical_hands)
    self.assertNotIn("KhAs", canonical_hands)


  def test_lowered_live_caps_reject_before_any_preparation(self):
    from scripts import flop_multistreet_validation as physical
    from scripts import flop_public_classes_candidate as candidate

    def forbidden(*args, **kwargs):
      raise AssertionError("cap admission must happen before preparation")

    for module, attribute, lowered in (
        (physical, "MAX_PAIRS", 2),
        (physical, "MAX_WORLDS", 5_939),
        (candidate, "MAX_TURNS", 48),
    ):
      with self.subTest(attribute=attribute):
        with mock.patch.object(physical, "prepare_oracle", forbidden, create=True), \
             mock.patch.object(candidate, "build_candidate", forbidden, create=True), \
             mock.patch.object(module, attribute, lowered):
          with self.assertRaises(ValueError):
            plan_module.admit_plan()


  def test_oversized_forged_rows_rejected_by_length_before_iteration(self):
    class IterationTrap(tuple):
      def __iter__(self):
        raise AssertionError("oversized rows must be rejected before iteration")

    base = plan_module.plan_second_board()
    forged = replace(base, compatible_pair_raw_products=IterationTrap((None,) * 4))
    with self.assertRaises(ValueError):
      plan_module.validate_plan(forged)


  def test_forged_fixture_fields_are_rejected(self):
    cases = [
    ("board", ("2c", "3d", "4h")),
    ("board", ("7c", "8d", "9h", "Tc")),
    ("oop_ranges", (("AsAd", Fraction(1)),)),
    ("ip_ranges", (("AsKh", Fraction(1, 4)), ("KsKd", Fraction(2)))),
    ("compatible_pair_raw_products", ()),
    ("global_blocker_normalizer", Fraction(1)),
    ("exact_pair_priors", (("AsAd", "KsKd", Fraction(1)),)),
    ("canonical_pair_identities", ()),
    ("ordered_runouts_per_pair", 1981),
    ("physical_world_forecast", 5941),
    ("scope", "general-board-claim"),
    ]
    for field, value in cases:
      with self.subTest(field=field, value=value):
        forged = replace(plan_module.plan_second_board(), **{field: value})
        with self.assertRaises(ValueError):
          plan_module.validate_plan(forged)


  def test_type_aliases_and_mutable_container_forgery_rejected(self):
    cases = [
    ("ordered_runouts_per_pair", True),
    ("physical_world_forecast", 5940.0),
    ("board", ["7c", "8d", "9h"]),
    ("global_blocker_normalizer", 1.625),
    ("global_blocker_normalizer", True),
    ]
    for field, value in cases:
      with self.subTest(field=field, value=value):
        forged = replace(plan_module.plan_second_board(), **{field: value})
        with self.assertRaises(ValueError):
          plan_module.validate_plan(forged)


  def test_plan_is_frozen_and_exact_type_required(self):
    plan = plan_module.plan_second_board()
    with self.assertRaises(FrozenInstanceError):
      plan.board = ("2c", "3d", "4h")
    class Subclass(plan_module.SecondBoardPlan):
        pass
    with self.assertRaises(ValueError):
      plan_module.validate_plan(  # exact type is part of the contract
            Subclass(**{name: getattr(plan, name) for name in plan.__dataclass_fields__}))


if __name__ == "__main__":
  unittest.main()
