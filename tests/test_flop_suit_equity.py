"""Independent regressions for global suit-orbit fixed-flop equity transfer."""
from dataclasses import replace
from fractions import Fraction
from itertools import combinations, permutations
import math
import unittest
from unittest.mock import patch

from scripts.flop_checkdown_validation import prepare_oracle, replay
from pokerlab import flop_checkdown_equity as equity
from pokerlab import flop_checkdown_solver as solver
from pokerlab import flop_checkdown_worlds as worlds
from pokerlab import flop_suit_equity as suit_equity
from pokerlab.cards import DECK, SUITS

BOARD, OOP, IP = "2c3c4d", "QhJh", "QcQd"
ANCHOR = {"pot": 2, "effective_stack": 1, "bet_sizes": [0.5],
          "raise_sizes": [], "max_raises": 0, "include_all_in": True}
DECK_ORDER = {card: index for index, card in enumerate(DECK)}


def map_card(card, mapping):
    return card[0] + mapping[card[1]]


def map_hand(hand, mapping):
    return "".join(sorted(map_card(hand[index:index + 2], mapping)
                          for index in (0, 2)))


def map_board(board, mapping):
    mapped = [map_card(board[index:index + 2], mapping)
              for index in range(0, len(board), 2)]
    return tuple(sorted(mapped, key=DECK_ORDER.__getitem__))


def joint_map_exists(source_board, source_oop, source_ip,
                     target_board, target_oop, target_ip):
    for values in permutations(SUITS):
        mapping = dict(zip(SUITS, values))
        if (map_board(source_board, mapping) == tuple(target_board)
                and map_hand(source_oop, mapping) == target_oop
                and map_hand(source_ip, mapping) == target_ip):
            return True
    return False


def legal_joint_target(board, oop_hand, ip_hand):
    board_cards = (tuple(board[index:index + 2] for index in range(0, len(board), 2))
                   if isinstance(board, str) else tuple(board))
    all_cards = board_cards + (oop_hand[:2], oop_hand[2:], ip_hand[:2], ip_hand[2:])
    return len(board_cards) == 3 and len(set(all_cards)) == 7


class FlopSuitEquityTransferTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = equity.prepare_flop_checkdown_equities(BOARD, OOP, IP)

    def test_all_24_global_maps_preserve_joint_endpoints_and_future_deck(self):
        seen_maps, seen_boards = set(), set()
        source_board = self.source.board
        source_dead = set(source_board + ("Qh", "Jh", "Qc", "Qd"))
        source_remaining = set(DECK) - source_dead
        source_future_pairs = {tuple(sorted(pair)) for pair in combinations(source_remaining, 2)}
        self.assertEqual((len(source_remaining), len(source_future_pairs)), (45, 990))

        with patch.object(worlds, "rank_hand", side_effect=AssertionError("rank called")), \
             patch.object(worlds, "combinations", side_effect=AssertionError("boards enumerated")), \
             patch.object(worlds.FlopCheckdownPlan, "build",
                          side_effect=AssertionError("counts rebuilt")):
            for values in permutations(SUITS):
                mapping = dict(zip(SUITS, values))
                target_board = map_board(BOARD, mapping)
                target_oop, target_ip = map_hand(OOP, mapping), map_hand(IP, mapping)
                transferred = suit_equity.remap_flop_checkdown_equities_by_suit(
                    self.source, "".join(target_board), target_oop, target_ip)
                provenance = suit_equity.flop_suit_remap_provenance(
                    self.source, "".join(target_board), target_oop, target_ip)
                self.assertEqual(transferred.board, target_board)
                self.assertEqual(transferred.counts, self.source.counts)
                self.assertEqual(transferred.pairs[0][2], Fraction(1))
                self.assertIsNone(transferred.validate())

                self.assertEqual(len(provenance), 1)
                row = provenance[0]
                self.assertEqual(row["source_board"], list(source_board))
                self.assertEqual(row["target_board"], list(target_board))
                self.assertEqual((row["source_oop_hand"], row["source_ip_hand"]), ("JhQh", IP))
                self.assertEqual((row["target_oop_hand"], row["target_ip_hand"]),
                                 (target_oop, target_ip))
                witness = row["suit_permutation"]
                self.assertEqual(tuple(witness), tuple(SUITS))
                self.assertEqual(set(witness.values()), set(SUITS))
                self.assertEqual(map_board(BOARD, witness), target_board)
                self.assertEqual(map_hand(OOP, witness), target_oop)
                self.assertEqual(map_hand(IP, witness), target_ip)

                target_dead = set(target_board + (target_oop[:2], target_oop[2:],
                                                  target_ip[:2], target_ip[2:]))
                target_remaining = set(DECK) - target_dead
                mapped_remaining = {map_card(card, witness) for card in source_remaining}
                self.assertEqual(mapped_remaining, target_remaining)
                self.assertEqual(len(mapped_remaining), 45)
                mapped_pairs = {tuple(sorted((map_card(a, witness), map_card(b, witness))))
                                for a, b in source_future_pairs}
                self.assertEqual(mapped_pairs,
                                 {tuple(sorted(pair)) for pair in combinations(target_remaining, 2)})
                seen_maps.add(tuple(witness[suit] for suit in SUITS))
                seen_boards.add(target_board)

        self.assertEqual(len(seen_maps), 24)
        self.assertEqual(len(seen_boards), 12)

    def test_non_joint_targets_reject_before_ranking(self):
        cases = [("2c3c5d", OOP, IP), ("2c3d4d", OOP, IP), (BOARD, IP, OOP)]
        private_only = next(
            (map_hand(OOP, dict(zip(SUITS, p))), map_hand(IP, dict(zip(SUITS, p))))
            for p in permutations(SUITS)
            if legal_joint_target(BOARD, map_hand(OOP, dict(zip(SUITS, p))),
                                  map_hand(IP, dict(zip(SUITS, p))))
            and not joint_map_exists(BOARD, OOP, IP, self.source.board,
                                     map_hand(OOP, dict(zip(SUITS, p))),
                                     map_hand(IP, dict(zip(SUITS, p)))))
        cases.append((BOARD, *private_only))
        split = next(
            (map_hand(OOP, dict(zip(SUITS, p))), map_hand(IP, dict(zip(SUITS, q))))
            for p in permutations(SUITS) for q in permutations(SUITS) if p != q
            if legal_joint_target(BOARD, map_hand(OOP, dict(zip(SUITS, p))),
                                  map_hand(IP, dict(zip(SUITS, q))))
            and not joint_map_exists(BOARD, OOP, IP, self.source.board,
                                     map_hand(OOP, dict(zip(SUITS, p))),
                                     map_hand(IP, dict(zip(SUITS, q)))))
        cases.append((BOARD, *split))

        for target_board, target_oop, target_ip in cases:
            target_cards = tuple(target_board[index:index + 2]
                                 for index in range(0, len(target_board), 2))
            self.assertTrue(legal_joint_target(target_cards, target_oop, target_ip))
            self.assertFalse(joint_map_exists(BOARD, OOP, IP, target_cards, target_oop, target_ip))
            with self.subTest(board=target_board, oop=target_oop, ip=target_ip), \
                 patch.object(worlds, "rank_hand", side_effect=AssertionError("ranked before rejection")), \
                 patch.object(worlds, "combinations", side_effect=AssertionError("enumerated before rejection")), \
                 patch.object(worlds.FlopCheckdownPlan, "build",
                              side_effect=AssertionError("built before rejection")):
                with self.assertRaisesRegex(ValueError, "not covered"):
                    suit_equity.remap_flop_checkdown_equities_by_suit(
                        self.source, target_board, target_oop, target_ip)
                with self.assertRaisesRegex(ValueError, "not covered"):
                    suit_equity.flop_suit_remap_provenance(
                        self.source, target_board, target_oop, target_ip)

    def test_invalid_sources_reject_before_target_plan_or_orbit_lookup(self):
        class DerivedEquities(equity.FlopCheckdownEquities):
            pass

        subclass = DerivedEquities(self.source.board, self.source.hands, self.source.pairs,
                                   self.source.counts, self.source._budget_items)
        wins, ties, losses = self.source.counts[0]
        malformed = replace(self.source, counts=((wins + 2, ties, losses),))
        self.assertIsNone(subclass.validate())

        with patch.object(suit_equity, "prepare_flop_worlds",
                          side_effect=AssertionError("target plan built before source validation")):
            for source in (object(), subclass):
                with self.subTest(source_type=type(source).__name__):
                    with self.assertRaises(TypeError):
                        suit_equity.remap_flop_checkdown_equities_by_suit(source, BOARD, OOP, IP)
                    with self.assertRaises(TypeError):
                        suit_equity.flop_suit_remap_provenance(source, BOARD, OOP, IP)
            for call in (suit_equity.remap_flop_checkdown_equities_by_suit,
                         suit_equity.flop_suit_remap_provenance):
                with self.assertRaisesRegex(ValueError, "counts totaling"):
                    call(malformed, BOARD, OOP, IP)

    def test_invalid_target_and_range_caps_reject_before_source_orbit_lookup(self):
        with patch.object(suit_equity, "_source_orbits",
                          side_effect=AssertionError("source orbit lookup before target admission")), \
             patch.object(worlds, "rank_hand",
                          side_effect=AssertionError("ranked before target admission")):
            with self.assertRaises(ValueError):
                suit_equity.remap_flop_checkdown_equities_by_suit(self.source, "2c2c4d", OOP, IP)
            with self.assertRaisesRegex(ValueError, "candidate pair limit"):
                suit_equity.remap_flop_checkdown_equities_by_suit(
                    self.source, BOARD, "random", "random")
            with self.assertRaisesRegex(ValueError, "compatible pair limit"):
                suit_equity.remap_flop_checkdown_equities_by_suit(
                    self.source, BOARD, "random", "AsAd")

    def test_conflicting_source_orbit_counts_reject_before_transfer(self):
        source = equity.prepare_flop_checkdown_equities(BOARD, "QhJh:0.5,QsJs:0.5", IP)
        self.assertEqual(len(source.pairs), 2)
        self.assertEqual(source.counts[0], source.counts[1])
        wins, ties, losses = source.counts[1]
        if losses >= 2:
            forged_counts = (wins + 2, ties, losses - 2)
        elif ties >= 2:
            forged_counts = (wins + 2, ties - 2, losses)
        else:
            self.fail("Expected an outcome count to perturb")
        forged = replace(source, counts=(source.counts[0], forged_counts))
        self.assertIsNone(forged.validate())

        with patch.object(worlds, "rank_hand", side_effect=AssertionError("ranked before orbit check")), \
             patch.object(worlds, "combinations", side_effect=AssertionError("enumerated before orbit check")), \
             patch.object(worlds.FlopCheckdownPlan, "build",
                          side_effect=AssertionError("built before orbit check")):
            with self.assertRaisesRegex(ValueError, "inconsistent.*orbit"):
                suit_equity.remap_flop_checkdown_equities_by_suit(forged, BOARD, OOP, IP)

    def test_joint_transfer_reweights_and_replays_conditional_future_worlds(self):
        target_oop, target_ip = "QhJh:0.5,QsJs:0.25", "QcQd:1"
        with patch.object(worlds, "rank_hand", side_effect=AssertionError("ranked during transfer")), \
             patch.object(worlds, "combinations", side_effect=AssertionError("enumerated during transfer")), \
             patch.object(worlds.FlopCheckdownPlan, "build",
                          side_effect=AssertionError("rebuilt during transfer")):
            transferred = suit_equity.remap_flop_checkdown_equities_by_suit(
                self.source, BOARD, target_oop, target_ip)
            provenance1 = suit_equity.flop_suit_remap_provenance(
                self.source, BOARD, target_oop, target_ip)
            provenance2 = suit_equity.flop_suit_remap_provenance(
                self.source, BOARD, target_oop, target_ip)
            with self.assertRaisesRegex(ValueError, "not covered by the source table"):
                equity.reweight_flop_checkdown_equities(self.source, target_oop, target_ip)

        priors = {("".join(transferred.hands[0][i]), "".join(transferred.hands[1][j])): p
                  for i, j, p in transferred.pairs}
        self.assertEqual(priors, {("JhQh", "QcQd"): Fraction(2, 3),
                                  ("JsQs", "QcQd"): Fraction(1, 3)})
        self.assertEqual(sum(priors.values(), Fraction()), Fraction(1))
        self.assertEqual(transferred.counts, (self.source.counts[0],) * 2)
        self.assertEqual(provenance1, provenance2)
        self.assertIsNot(provenance1[0], provenance2[0])
        provenance1[0]["source_board"].append("As")
        self.assertEqual(provenance2[0]["source_board"], list(self.source.board))

        built_worlds, _ = transferred.build()
        pair_masses = {}
        for i, j, mass, _sign in built_worlds:
            self.assertGreater(mass, 0)
            pair_masses[(i, j)] = pair_masses.get((i, j), 0.0) + mass
        for i, j, prior in transferred.pairs:
            self.assertTrue(math.isclose(pair_masses[(i, j)], float(prior),
                                         rel_tol=0, abs_tol=1e-15))
        self.assertTrue(math.isclose(math.fsum(row[2] for row in built_worlds), 1.0,
                                     rel_tol=0, abs_tol=1e-15))

        prepared = solver.solve_prepared_flop_checkdown(
            transferred, config=ANCHOR, iterations=10, algorithm="cfrplus")
        fresh = solver.solve_flop_checkdown(
            BOARD, target_oop, target_ip, config=ANCHOR, iterations=10, algorithm="cfrplus")
        self.assertEqual(prepared.pop("equity_preparation")["mode"], "prepared-counts")
        self.assertEqual(prepared, fresh)
        replay(prepared, prepare_oracle(BOARD, target_oop, target_ip, ANCHOR))


if __name__ == "__main__":
    unittest.main()
