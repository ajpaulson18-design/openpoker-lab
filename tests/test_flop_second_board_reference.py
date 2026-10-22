from fractions import Fraction
import unittest
from unittest import mock

from scripts import flop_multistreet_validation as physical
from scripts import flop_public_classes_candidate as candidate
from scripts import flop_second_board_plan as planning
from scripts import flop_second_board_reference as reference


class SecondBoardReferenceTests(unittest.TestCase):
  FOLD = {"name": "fold", "amount": 0.0, "raise_to": 0.0,
          "history_key": "fold", "full_raise": False}
  CALL = {"name": "call", "amount": 0.0, "raise_to": 0.0,
          "history_key": "call", "full_raise": False}

  def setUp(self):
    self.plan = planning.plan_second_board()
    self.priors = reference._pair_priors(self.plan)

  def tiny_oracle(self):
    rows = []
    counts = []
    for (oop, ip), prior in self.priors.items():
      dead = set(self.plan.board + (oop[:2], oop[2:], ip[:2], ip[2:]))
      remaining = [card for card in physical.DECK if card not in dead]
      future = (remaining[0], remaining[1])
      rows.append((oop, ip, prior, 0, self.plan.board + future))
      counts.append({
          "oop_hand": oop, "ip_hand": ip, "wins": 0, "ties": 1,
          "losses": 0, "ordered_outcomes": 1,
          "pair_probability_fraction": f"{prior.numerator}/{prior.denominator}",
          "pair_probability": float(prior),
      })
    return {"worlds": tuple(rows), "counts": tuple(counts),
            "normalizer": self.plan.global_blocker_normalizer}

  def mock_full_oracle(self):
    oracle = self.tiny_oracle()
    worlds = oracle["worlds"]
    counts = oracle["counts"]
    runouts = tuple((turn, river) for turn in physical.DECK if turn not in self.plan.board
                    for river in physical.DECK if river not in self.plan.board and turn != river)
    reachable = tuple(sorted({world[4][3:] for world in worlds},
                             key=lambda row: tuple(physical.DECK_INDEX[c] for c in row)))
    nodes = {}

    def action(name, *, key=None, amount=0.0, raise_to=0.0):
      return {"name": name, "amount": amount, "raise_to": raise_to,
              "history_key": key if key is not None else name,
              "full_raise": False}

    def decision(player, street, history, actions, children):
      visible = reference._history_cards(history, self.plan.board)
      board = self.plan.board + visible
      node = physical._Decision(history, player, street, board, actions, children)
      key = (player, history)
      self.assertNotIn(key, nodes)
      nodes[key] = node
      return node

    def fold(player, history):
      return physical._Terminal(history, "fold", (0.0, 0.0), 1 - player)

    def river_chance(history):
      river_history = history + ("river@Jc",)
      river_decision = decision(
          0, "river", river_history,
          (dict(self.FOLD), dict(self.CALL)),
          (fold(0, river_history), physical._Terminal(
              river_history + ("call",), "showdown", (5.0, 5.0), None)))
      return physical._Chance(history, 4, "river", {"Jc": river_decision})

    def turn_chance(history):
      turn_history = history + ("turn@Tc",)
      turn_decision = decision(
          0, "turn", turn_history,
          (dict(self.FOLD), dict(self.CALL)),
          (fold(0, turn_history), river_chance(turn_history + ("call",))))
      return physical._Chance(history, 3, "turn", {"Tc": turn_decision})

    checked_history = ("check",)
    checked_bet_history = checked_history + ("bet@5.0",)
    checked_bet = decision(
        0, "flop", checked_bet_history,
        (dict(self.FOLD), dict(self.CALL)),
        (fold(0, checked_bet_history), turn_chance(checked_bet_history + ("call",))))
    checked = decision(
        1, "flop", checked_history,
        (action("check"), action("bet", key="bet@5.0", amount=5.0, raise_to=5.0)),
        (turn_chance(checked_history + ("check",)), checked_bet))
    bet_history = ("bet@5.0",)
    bet_response = decision(
        1, "flop", bet_history,
        (dict(self.FOLD), dict(self.CALL)),
        (fold(1, bet_history), turn_chance(bet_history + ("call",))))
    root = decision(
        0, "flop", (),
        (action("check"), action("bet", key="bet@5.0", amount=5.0, raise_to=5.0)),
        (checked, bet_response))
    _view, _tree_hash, tree_census = reference._bounded_tree(
        {"root": root, "nodes": nodes}, self.plan.board)
    config = physical._public_config(physical._configuration(reference.CONFIG))
    rank_keys = set()
    for oop, ip, _mass, _sign, full_board in worlds:
      rank_board = tuple(sorted(full_board, key=physical.DECK_INDEX.__getitem__))
      rank_keys.add((oop[:2], oop[2:]) + rank_board)
      rank_keys.add((ip[:2], ip[2:]) + rank_board)
    oracle.update({
        "deals": worlds, "pair_counts": counts, "board": tuple(self.plan.board),
        "runouts": runouts, "reachable_runouts": reachable, "runout_mode": "full-deck",
        "pair_probabilities": {pair: float(prior) for pair, prior in self.priors.items()},
        "world_count_per_pair": {pair[0] + "/" + pair[1]: 1 for pair in self.priors},
        "root": root, "nodes": nodes,
        "worlds_count": len(worlds), "physical_worlds": len(worlds),
        "compatible_pairs": len(self.priors), "config": config,
        "street_configs": {street: dict(config) for street in ("flop", "turn", "river")},
        "public_nodes": tree_census["decision_nodes"],
        "public_states": tree_census["public_states"],
        "chance_nodes": tree_census["chance_nodes"],
        "terminal_nodes": tree_census["terminal_nodes"],
        "pot": 10.0, "effective_stack": [5.0, 5.0],
        "source_counters": {"rank_hand_calls": len(rank_keys),
            "physical_world_rows": len(worlds), "pair_runout_rows_checked": len(worlds),
            "world_count_by_pair": {pair[0] + "/" + pair[1]: 1 for pair in self.priors}},
    })
    return oracle, rank_keys

  def test_small_test_hook_checks_exact_support_mass_and_sign_metadata(self):
    oracle = self.tiny_oracle()
    receipt = reference._validate_world_rows(self.plan, oracle, outcomes_per_pair=1)
    self.assertEqual(receipt["world_count"], 3)
    self.assertEqual(receipt["pair_count"], 3)
    self.assertEqual(receipt["joint_mass"], "1/1")

  def test_rejects_duplicate_bad_mass_blockers_and_missing_support(self):
    base = self.tiny_oracle()
    bads = []
    duplicate = dict(base)
    duplicate["worlds"] = base["worlds"] + (base["worlds"][0],)
    bads.append(duplicate)
    wrong_mass = dict(base)
    wrong_mass["worlds"] = (base["worlds"][0][:2] +
                              (Fraction(1),) + base["worlds"][0][3:],) + base["worlds"][1:]
    bads.append(wrong_mass)
    blocked = dict(base)
    row = base["worlds"][0]
    blocked["worlds"] = ((row[0], row[1], row[2], row[3],
                           self.plan.board + (row[0][:2], row[1][:2])),) + base["worlds"][1:]
    bads.append(blocked)
    missing = dict(base)
    missing["worlds"] = base["worlds"][:-1]
    bads.append(missing)
    for bad in bads:
      with self.subTest(world_count=len(bad["worlds"])):
        with self.assertRaises(ValueError):
          reference._validate_world_rows(self.plan, bad, outcomes_per_pair=1)

  def test_boolean_and_float_pair_count_aliases_rejected(self):
    for replacement in (True, 1.0):
      oracle = self.tiny_oracle()
      rows = [dict(row) for row in oracle["counts"]]
      rows[0]["ties"] = replacement
      oracle["counts"] = tuple(rows)
      with self.subTest(replacement=replacement):
        with self.assertRaises(ValueError):
          reference._validate_world_rows(self.plan, oracle, outcomes_per_pair=1)

  def test_same_ranker_recheck_uses_fresh_cache_and_detects_sign_mismatch(self):
    worlds = self.tiny_oracle()["worlds"]
    calls = []
    result = reference._rank_recheck(worlds, ranker=lambda key: calls.append(key) or 7)
    self.assertEqual(result["world_comparisons"], 3)
    self.assertEqual(result["unique_rank_calls"], len(calls))
    self.assertLessEqual(result["unique_rank_calls"], reference.MAX_RECHECK_RANK_CALLS)
    self.assertIn("same established reference ranker", result["interpretation"])
    bad = list(worlds)
    row = bad[0]
    bad[0] = row[:3] + (1,) + row[4:]
    with self.assertRaises(ValueError):
      reference._rank_recheck(tuple(bad), ranker=lambda key: 7)

  def test_candidate_builder_receives_fresh_test_rows_and_keeps_candidate_only_flags(self):
    rows = [[oop, ip, str(mass), sign, list(board)]
            for oop, ip, mass, sign, board in self.tiny_oracle()["worlds"]]
    partition = candidate.build_candidate(rows, board=self.plan.board)
    self.assertIs(partition["candidate_only"], True)
    self.assertIs(partition["physical_provenance"], False)
    self.assertEqual(partition["input_completeness"], "unverified-caller-supplied-records")
    self.assertEqual(partition["physical_world_count"], 3)
    self.assertEqual(partition["compatible_pair_count"], 3)

  def test_bounded_tree_walk_checks_index_visibility_and_serializes(self):
    oracle, _ = self.mock_full_oracle()
    root = oracle["root"]
    view, digest, census = reference._bounded_tree(oracle, self.plan.board)
    self.assertEqual(view[0]["kind"], "decision")
    self.assertEqual(view[0]["history"], [])
    self.assertEqual(view[0]["board"], list(self.plan.board))
    self.assertEqual(census["decision_nodes"], len(oracle["nodes"]))
    self.assertEqual(len(digest), 64)
    self.assertEqual(census["public_states"], len(view))

  def test_bounded_tree_rejects_a_coherent_subgame_as_the_flop_root(self):
    oracle, _ = self.mock_full_oracle()
    # A child decision can be internally coherent but cannot stand in for the
    # requested full flop-start tree.
    bad = dict(oracle, root=oracle["root"].children[0])
    with self.assertRaises(ValueError):
      reference._bounded_tree(bad, self.plan.board)

  def test_cycle_is_rejected(self):
    root = physical._Decision(
        (), 0, "flop", self.plan.board,
        ({"name": "check", "amount": 0.0, "raise_to": 0.0,
          "history_key": "check", "full_raise": False},
         {"name": "bet", "amount": 5.0, "raise_to": 5.0,
          "history_key": "bet@5.0", "full_raise": False}), ())
    root.children = (root, root)
    original_need = reference._need

    def isolate_cycle_guard(ok, message):
      # A coherent game history cannot itself form a cycle because each action
      # extends the history. Suppress only that guard here to exercise the
      # separate active-node cycle detector directly.
      if message == "Non-fold child history must append the selected action":
        return
      original_need(ok, message)

    with mock.patch.object(reference, "_need", side_effect=isolate_cycle_guard):
      with self.assertRaisesRegex(ValueError, "cycle"):
        reference._bounded_tree({"root": root, "nodes": {(0, ()): root}}, self.plan.board)

  def test_public_history_rejects_private_or_duplicate_reveals(self):
    for history in (("As",), ("turn@7c",), ("river@5c",)):
      bad = physical._Terminal(history, "fold", (0.0, 0.0), 1)
      with self.subTest(history=history):
        with self.assertRaises(ValueError):
          reference._bounded_tree({"root": bad, "nodes": {}}, self.plan.board)

  def test_preflight_rejects_lowered_caps_before_oracle_preparation(self):
    def forbidden(*args, **kwargs):
      raise AssertionError("oracle preparation ran before admission")
    with mock.patch.object(physical, "prepare_oracle", forbidden), \
         mock.patch.object(candidate, "MAX_WORLDS", 5_000):
      with self.assertRaises(ValueError):
        reference.prepare_reference(self.plan)

  def test_public_prepare_success_counts_calls_restores_ranker_and_passes_board(self):
    oracle, rank_keys = self.mock_full_oracle()
    fake_rank = lambda key: 7
    original_builder = candidate.build_candidate
    builder_calls = []

    def fake_prepare(board, oop_rows, ip_rows, config):
      self.assertEqual(tuple(board), self.plan.board)
      self.assertEqual(config, reference.CONFIG)
      for key in rank_keys:
        physical.independent_rank(key)
      return oracle

    def capture_builder(rows, *, board):
      builder_calls.append(tuple(board))
      return original_builder(rows, board=board)

    progress = {}
    with mock.patch.object(physical, "independent_rank", fake_rank), \
         mock.patch.object(physical, "prepare_oracle", side_effect=fake_prepare), \
         mock.patch.object(candidate, "build_candidate", side_effect=capture_builder), \
         mock.patch.object(reference, "RUNOUTS_PER_PAIR", 1):
      report = reference.prepare_reference(self.plan, progress=progress)
      self.assertIs(physical.independent_rank, fake_rank)

    self.assertEqual(builder_calls, [self.plan.board])
    self.assertEqual(progress["phase"], "complete")
    self.assertEqual(progress["preparation_rank_calls"], len(rank_keys))
    self.assertEqual(progress["recheck_rank_calls"], len(rank_keys))
    self.assertEqual(report["physical"]["worlds_sha256"].__len__(), 64)
    self.assertEqual(report["candidate_partition"]["board"], list(self.plan.board))
    self.assertIs(report["candidate_partition"]["candidate_only"], True)
    self.assertFalse(report["claims"]["class_or_tree_equivalence_proved"])

  def test_public_prepare_restores_ranker_and_keeps_partial_attempt_receipt_on_error(self):
    fake_rank = lambda key: 7
    progress = {}
    def failing_prepare(*args):
      physical.independent_rank(("As", "Ad", "7c", "8d", "9h", "Tc", "Jc"))
      raise RuntimeError("synthetic preparation failure")

    with mock.patch.object(physical, "independent_rank", fake_rank), \
         mock.patch.object(physical, "prepare_oracle", side_effect=failing_prepare):
      with self.assertRaisesRegex(RuntimeError, "synthetic preparation failure"):
        reference.prepare_reference(self.plan, progress=progress)
      self.assertIs(physical.independent_rank, fake_rank)
    self.assertEqual(progress["phase"], "physical-preparation")
    self.assertEqual(progress["preparation_ranker_attempts"], 1)
    self.assertEqual(progress["preparation_rank_calls"], 1)
    self.assertEqual(progress["recheck_rank_calls"], 0)


if __name__ == "__main__":
  unittest.main()
