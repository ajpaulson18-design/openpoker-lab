from copy import deepcopy
from fractions import Fraction
import unittest
from unittest import mock

from scripts import flop_public_classes_candidate as candidate
from scripts import flop_second_board_plan as planning
from scripts import flop_second_board_partition_proof as proof


class SecondBoardPartitionProofTests(unittest.TestCase):
  @classmethod
  def setUpClass(cls):
    cls.plan = planning.plan_second_board()
    cls.worlds = cls._synthetic_worlds()
    candidate_rows = [[oop, ip, str(mass), sign, list(board)]
                      for oop, ip, mass, sign, board in cls.worlds]
    cls.partition = candidate.build_candidate(candidate_rows, board=cls.plan.board)

  @classmethod
  def _synthetic_worlds(cls):
    rows = []
    for pair_index, (literal_oop, literal_ip, prior) in enumerate(
            cls.plan.exact_pair_priors):
      oop = "".join(sorted((literal_oop[:2], literal_oop[2:])))
      ip = "".join(sorted((literal_ip[:2], literal_ip[2:])))
      private = (oop[:2], oop[2:], ip[:2], ip[2:])
      dead = set(cls.plan.board + private)
      remaining = [card for card in candidate.DECK if card not in dead]
      for turn in remaining:
        for river in remaining:
          if turn == river:
            continue
          # Deterministic synthetic signs vary over both cards and pairs. No
          # poker ranker or physical model is called by this fixture.
          value = (candidate._DECK_INDEX[turn] + 2 * candidate._DECK_INDEX[river]
                   + pair_index) % 3
          rows.append((oop, ip, prior / (45 * 44), value - 1,
                       cls.plan.board + (turn, river)))
    return tuple(rows)

  def run_audit(self, partition=None, worlds=None, **kwargs):
    return proof.verify_partition(
        self.partition if partition is None else partition,
        self.worlds if worlds is None else worlds, **kwargs)

  def test_full_joint_support_and_candidate_partition_audit(self):
    turns, rivers, compact, census = self.run_audit()
    self.assertEqual(len(self.worlds), 5_940)
    self.assertEqual(census["compatible_pairs"], 3)
    self.assertEqual(census["physical_worlds"], 5_940)
    self.assertEqual(census["turn_cards"], 49)
    self.assertEqual(census["joint_mass"], "1/1")
    self.assertEqual(len(turns), 49)
    self.assertEqual(len(rivers), census["ordered_runouts"])
    self.assertEqual(len(compact), census["class_worlds"])
    self.assertEqual(census["turn_classes"], self.partition["turn_class_count"])
    self.assertEqual(census["river_signatures"], self.partition["river_class_count"])

  def test_rejects_board_mismatch_before_candidate_rebuild(self):
    with mock.patch.object(candidate, "build_candidate",
                           side_effect=AssertionError("rebuild must not run")):
      with self.assertRaisesRegex(ValueError, "restricted"):
        self.run_audit(board=("2c", "3d", "4h"))

  def test_rejects_incomplete_physical_pair_support(self):
    with self.assertRaisesRegex(ValueError, "complete|support|runout"):
      self.run_audit(worlds=self.worlds[:-1])

  def test_partition_pending_children_are_reserved_before_extend(self):
    value = {"a": [0, 0, 0, 0], "b": []}
    with mock.patch.object(proof, "MAX_PARTITION_ITEMS", 6):
      with self.assertRaisesRegex(ValueError, "pending-item reservation"):
        proof._bounded_partition(value)

  def test_fourth_pair_is_rejected_before_processing_later_rows(self):
    first_by_pair = {}
    for row in self.worlds:
      first_by_pair.setdefault(row[:2], row)
    prefix = list(first_by_pair.values())
    oop, ip = "AcAd", "KcKd"
    dead = set(self.plan.board + ("Ac", "Ad", "Kc", "Kd"))
    remaining = [card for card in candidate.DECK if card not in dead]
    extra = (oop, ip, Fraction(1, 5_940), 0,
             self.plan.board + (remaining[0], remaining[1]))
    selected = set(prefix)
    tail = [row for row in self.worlds if row not in selected]
    malformed = ("poison-row-must-not-be-read",)
    forged = tuple(prefix + [extra, malformed] + tail[:5_935])
    self.assertEqual(len(forged), 5_940)
    with mock.patch.object(proof, "_canonical_hand", wraps=proof._canonical_hand) as parser:
      with self.assertRaisesRegex(ValueError, "more than three private pairs"):
        self.run_audit(worlds=forged)
    self.assertEqual(parser.call_count, 8)

  def test_world_fraction_bit_limit_precedes_accumulation(self):
    changed = list(self.worlds)
    row = changed[0]
    changed[0] = row[:2] + (Fraction(1 << 400, 1),) + row[3:]
    with mock.patch.object(proof, "_add_fraction",
                           side_effect=AssertionError("must reject before addition")):
      with self.assertRaisesRegex(ValueError, "fraction bit bound"):
        self.run_audit(worlds=changed)

  def test_rejects_same_global_mass_with_changed_joint_class_masses(self):
    changed = deepcopy(self.partition)
    first, second = changed["class_worlds"][:2]
    a, b = Fraction(*first["mass"]), Fraction(*second["mass"])
    delta = min(a, b) / 7
    first["mass"] = [ (a - delta).numerator, (a - delta).denominator ]
    second["mass"] = [ (b + delta).numerator, (b + delta).denominator ]
    self.assertEqual(sum((Fraction(*row["mass"]) for row in changed["class_worlds"]),
                         Fraction()), Fraction(1))
    with self.assertRaisesRegex(ValueError, "mass|marginal|descriptive"):
      self.run_audit(partition=changed)

  def test_rejects_changed_sign_signature(self):
    changed = deepcopy(self.partition)
    row = changed["class_worlds"][0]
    row["sign"] = -row["sign"] if row["sign"] else 1
    with self.assertRaisesRegex(ValueError, "sign|signature|descriptive"):
      self.run_audit(partition=changed)

  def test_rejects_changed_turn_posterior_or_transition_class(self):
    changed = deepcopy(self.partition)
    left, right = changed["turn_classes"][:2]
    left_card, right_card = left["members"][0], right["members"][0]
    left["members"][0], right["members"][0] = right_card, left_card
    with self.assertRaises(ValueError):
      self.run_audit(partition=changed)

  def test_rejects_missing_duplicate_and_changed_river_transports(self):
    for mutation in ("missing", "duplicate", "destination"):
      changed = deepcopy(self.partition)
      rows = changed["turn_classes"][0]["river_transports"]
      with self.subTest(mutation=mutation):
        if mutation == "missing":
          rows.pop()
        elif mutation == "duplicate":
          rows.append(deepcopy(rows[0]))
        else:
          rows[0]["representative_river"] = rows[1]["representative_river"]
        with self.assertRaises(ValueError):
          self.run_audit(partition=changed)

  def test_rejects_bool_count_alias(self):
    for mutation in ("count", "mass", "class-id"):
      changed = deepcopy(self.partition)
      with self.subTest(mutation=mutation):
        if mutation == "count":
          changed["class_worlds"][0]["physical_world_count"] = True
        elif mutation == "mass":
          changed["class_worlds"][0]["mass"][0] = True
        else:
          changed["turn_classes"][0]["id"] = True
        with self.assertRaises(ValueError):
          self.run_audit(partition=changed)

  def test_rejects_world_mass_or_sign_tampering(self):
    mass_changed = list(self.worlds)
    row = mass_changed[0]
    mass_changed[0] = row[:2] + (row[2] + Fraction(1, 1000),) + row[3:]
    sign_changed = list(self.worlds)
    row = sign_changed[0]
    sign_changed[0] = row[:3] + (1 if row[3] != 1 else -1,) + row[4:]
    for changed in (mass_changed, sign_changed):
      with self.subTest(kind="mass" if changed is mass_changed else "sign"):
        with self.assertRaises(ValueError):
          self.run_audit(worlds=changed)

  def test_rejects_changed_pair_marginals_even_when_global_mass_is_preserved(self):
    changed = list(self.worlds)
    pairs = []
    for row in changed:
      pair = row[:2]
      if pair not in pairs:
        pairs.append(pair)
    delta = Fraction(1, 260)
    per_world = delta / (45 * 44)
    for index, row in enumerate(changed):
      if row[:2] == pairs[0]:
        changed[index] = row[:2] + (row[2] + per_world,) + row[3:]
      elif row[:2] == pairs[1]:
        changed[index] = row[:2] + (row[2] - per_world,) + row[3:]
    self.assertEqual(sum((row[2] for row in changed), Fraction()), Fraction(1))
    with self.assertRaisesRegex(ValueError, "pair marginals"):
      self.run_audit(worlds=changed)


if __name__ == "__main__":
  unittest.main()
