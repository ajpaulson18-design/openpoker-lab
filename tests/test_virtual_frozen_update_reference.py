from fractions import Fraction
from itertools import combinations, permutations
import struct
import unittest
from unittest.mock import patch

from tests.full_deck_public_chance_reference import PROOF9
from tests import virtual_frozen_update_reference as reference
from tests.virtual_frozen_update_reference import (
    _MAX_PREFIXES,
    _MAX_PROPOSALS,
    _TARGET_DK,
    _TARGET_SUFFIX_COUNTS,
    _UNFILTERED_COMPLETIONS,
    build_frozen_update_census,
    build_physical_prefix_index,
    frozen_profile_probabilities,
    scaled_proof9_ranges,
    selector_hash,
)


def _literal_prefix_mass_oracle(index):
    """Small 60-supported-pair-board oracle; retains prefix sums only."""
    masses = {}
    support_boards = set()
    for hand0, weight0 in index.ranges[0]:
        for hand1, weight1 in index.ranges[1]:
            if not set(hand0).isdisjoint(hand1):
                continue
            remaining = tuple(card for card in PROOF9 if card not in (*hand0, *hand1))
            joint_pair_prior = weight0 * weight1 / index.normalizer
            for flop in combinations(remaining, 3):
                last = tuple(card for card in remaining if card not in flop)
                for turn, river in permutations(last, 2):
                    board = (*flop, turn, river)
                    support_boards.add(board)
                    complete_mass = joint_pair_prior / 20
                    for length in (0, 3, 4, 5):
                        prefix = board[:length]
                        slot = masses.setdefault(prefix, [[Fraction(0) for _ in side]
                                                          for side in index.ranges])
                        for player, own in ((0, hand0), (1, hand1)):
                            hand_index = next(i for i, (hand, _w) in enumerate(index.ranges[player])
                                              if hand == own)
                            slot[player][hand_index] += complete_mass
    return masses, support_boards


def _literal_proposal_prefixes(index):
    uniform_board = Fraction(1, 2520)
    river_weights = {card: position + 1 for position, card in enumerate(PROOF9)}
    weighted_board_total = 0
    uniform = {length: {} for length in (0, 3, 4, 5)}
    weighted = {length: {} for length in (0, 3, 4, 5)}
    for board in index.proposals:
        weighted_board = Fraction(river_weights[board[4]], 12600)
        weighted_board_total += weighted_board
        for length in (0, 3, 4, 5):
            prefix = board[:length]
            uniform[length][prefix] = uniform[length].get(prefix, Fraction(0)) + uniform_board
            weighted[length][prefix] = weighted[length].get(prefix, Fraction(0)) + weighted_board
    if weighted_board_total != 1:
        raise AssertionError("literal river-weighted proposal failed normalization")
    return uniform, weighted


class FrozenProfileReferenceTests(unittest.TestCase):
    def test_protocol_hash_golden_and_exact_power_of_two_profile(self):
        actor, hand = 0, (16, 43)
        history = ("raise_1", "flop@2c3c4c")
        actions = ("fold", "call", "raise_1")
        self.assertEqual(selector_hash(actor, hand, history, actions),
                         16440708537006860105)
        profile = frozen_profile_probabilities(actor, hand, history, actions)
        self.assertEqual(profile, (Fraction(1, 4), Fraction(1, 4), Fraction(1, 2)))
        self.assertEqual(sum(profile), 1)
        self.assertTrue(all(value == 0 or value.denominator & (value.denominator - 1) == 0
                            for value in profile))

    def test_profile_menus_one_through_eight_sum_exactly_with_optional_zero(self):
        history = ("limp", "check", "flop@2c3c4c", "bet_0.5")
        hand = (16, 43)
        for width in range(1, 9):
            actions = tuple(f"a{index}" for index in range(width))
            for actor in (0, 1):
                probabilities = frozen_profile_probabilities(actor, hand, history, actions)
                self.assertEqual(len(probabilities), width)
                self.assertEqual(sum(probabilities), Fraction(1))
                self.assertLessEqual(sum(value == 0 for value in probabilities), 1)
                self.assertTrue(all(value == 0 or
                                    value.numerator == 1 and
                                    value.denominator & (value.denominator - 1) == 0
                                    for value in probabilities))

    def test_profile_rejects_unbounded_or_nonprotocol_row_identity_inputs(self):
        actions = ("fold", "call")
        with self.assertRaises(ValueError):
            selector_hash(2, (16, 43), (), actions)
        with self.assertRaises(ValueError):
            selector_hash(0, (43, 16), (), actions)
        with self.assertRaises(ValueError):
            selector_hash(0, (16, 43), ("call\N{SNOWMAN}",), actions)
        with self.assertRaises(ValueError):
            selector_hash(0, (16, 43), ("x",) * 65, actions)
        with self.assertRaises(ValueError):
            selector_hash(0, (16, 43), (), tuple(f"a{i}" for i in range(21)))
        with self.assertRaises(ValueError):
            selector_hash(0, (16, 43), ("x" * 65,), actions)


class PhysicalPrefixReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index = build_physical_prefix_index()

    def test_scaled_prior_law_and_prefix_target_masses_match_literal_world_oracle(self):
        index = self.index
        self.assertEqual(index.normalizer, Fraction(29, 64))
        self.assertEqual(tuple(sorted(index.prefixes)), (0, 3, 4, 5))
        self.assertEqual(sum(map(len, index.prefixes.values())), _MAX_PREFIXES)
        expected, target_boards = _literal_prefix_mass_oracle(index)
        self.assertEqual(len(target_boards), 60)
        for length, prefixes in index.prefixes.items():
            for prefix in prefixes:
                expected_mass = expected.get(prefix, ((Fraction(0),) * 2,) * 2)
                for player in (0, 1):
                    for hand_index in range(len(index.ranges[player])):
                        self.assertEqual(index.mass(prefix, player, hand_index),
                                         expected_mass[player][hand_index])
        self.assertEqual(index.supported_hand_counts(), {
            0: ((1, 1), (1, 1)),
            3: ((19, 10), (16, 10)),
            4: ((40, 20), (36, 20)),
            5: ((40, 20), (40, 20)),
        })
        totals = tuple(
            tuple(sum((index.mass(prefix, player, i)
                       for prefix in index.prefixes[length]
                       for i in range(len(index.ranges[player]))), Fraction(0))
                  for player in (0, 1))
            for length in (0, 3, 4, 5))
        self.assertEqual(totals, ((1, 1),) * 4)

    def test_proposal_prefix_q_is_separate_and_matches_literal_board_sums(self):
        index = self.index
        self.assertEqual(len(index.proposals), _MAX_PROPOSALS)
        uniform, weighted = _literal_proposal_prefixes(index)
        for length in (0, 3, 4, 5):
            for prefix in index.prefixes[length]:
                self.assertEqual(index.proposal_laws["uniform"]["prefix"][prefix],
                                 uniform[length][prefix])
                self.assertEqual(index.proposal_laws["river_weighted"]["prefix"][prefix],
                                 weighted[length][prefix])
            self.assertEqual(sum(index.proposal_laws["uniform"]["prefix"][p]
                                 for p in index.prefixes[length]), 1)
            self.assertEqual(sum(index.proposal_laws["river_weighted"]["prefix"][p]
                                 for p in index.prefixes[length]), 1)
        self.assertEqual(index.proposal_laws["uniform"]["prefix"][()], Fraction(1))
        self.assertEqual(index.proposal_laws["river_weighted"]["prefix"][()], Fraction(1))
        self.assertEqual(_TARGET_DK, {0: 1, 3: 10, 4: 20, 5: 20})
        self.assertEqual(_TARGET_SUFFIX_COUNTS, {0: 20, 3: 2, 4: 1, 5: 1})
        self.assertEqual(_UNFILTERED_COMPLETIONS, {0: 2520, 3: 30, 4: 5, 5: 1})

    def test_reduced_only_census_rejects_other_decks_and_priors(self):
        with self.assertRaises(ValueError):
            build_physical_prefix_index(deck=tuple(range(10)))
        ranges = scaled_proof9_ranges()
        altered = (ranges[0], ((ranges[1][0][0], Fraction(1, 2)), ranges[1][1]))
        with self.assertRaises(ValueError):
            build_physical_prefix_index(ranges=altered)

    def test_deck_and_fraction_width_validation_precede_range_expansion(self):
        class HostileRanges:
            def __iter__(self):
                raise AssertionError("invalid deck must reject before range iteration")

        class HostileDeck(tuple):
            def __len__(self):
                raise AssertionError("tuple subclasses must reject before invoking hooks")

            def __eq__(self, _other):
                raise AssertionError("tuple subclasses must reject before equality")

        with patch.object(reference, "_normalizer", side_effect=AssertionError("normalizer entered")), \
                patch.object(reference, "_proof_prefixes", side_effect=AssertionError("prefixes entered")):
            with self.assertRaises(ValueError):
                build_physical_prefix_index(ranges=HostileRanges(), deck=list(PROOF9))
            with self.assertRaises(ValueError):
                build_physical_prefix_index(ranges=HostileRanges(), deck=HostileDeck(PROOF9))

        ranges = scaled_proof9_ranges()
        huge = (ranges[0], ((ranges[1][0][0], Fraction(1 << 64, 1)),
                            ranges[1][1]))
        with patch.object(reference, "_normalizer", side_effect=AssertionError("normalizer entered")), \
                patch.object(reference, "_proof_prefixes", side_effect=AssertionError("prefixes entered")):
            with self.assertRaisesRegex(ValueError, "width"):
                build_physical_prefix_index(ranges=huge)

    def test_scaled_weight_inputs_have_the_pinned_binary64_bitmaps(self):
        expected = (
            ((43, 48, Fraction(1, 8)),
             (32, 43, Fraction(3, 4))),
            ((24, 37, Fraction(3, 8)),
             (16, 32, Fraction(1, 1))),
        )
        actual = scaled_proof9_ranges()
        self.assertEqual(tuple(tuple((hand[0], hand[1], weight) for hand, weight in side)
                               for side in actual), expected)
        bitmaps = tuple(tuple(struct.pack(">d", float(weight)).hex() for _hand, weight in side)
                        for side in actual)
        self.assertEqual(bitmaps, (("3fc0000000000000", "3fe8000000000000"),
                                   ("3fd8000000000000", "3ff0000000000000")))


class FrozenUpdateCensusTests(unittest.TestCase):
    def test_card_free_and_literal_counts_factor_into_physical_rows_without_materializing_rows(self):
        census = build_frozen_update_census()
        self.assertEqual(census["template"]["nodes"], 388)
        self.assertEqual(census["template"]["edges"], 410)
        self.assertEqual(census["literal_history_census"]["logical_occurrences"], 1105)
        self.assertEqual(census["literal_history_census"]["unique_symbolic_history_skeletons"], 1105)
        self.assertEqual(census["proposal_geometry"]["prefix_counts"],
                         {0: 1, 3: 84, 4: 504, 5: 2520})
        self.assertEqual(census["proposal_geometry"]["positive_target_prefix_counts"],
                         {0: 1, 3: 25, 4: 56, 5: 60})
        self.assertEqual(census["proposal_geometry"]["positive_target_prefix_total"], 142)
        self.assertEqual(census["proposal_geometry"]["target_supported_boards"], 60)
        self.assertEqual(census["rows"]["physical_supported_rows"], 24420)
        self.assertEqual(census["rows"]["physical_supported_decision_action_slots"], 58164)
        self.assertEqual(census["rows"]["unfiltered_public_decision_occurrences"], 766758)
        self.assertEqual(census["rows"]["unfiltered_decision_action_slots"], 1795263)
        self.assertEqual(census["rows"]["physical_supported_decision_occurrences"], 24102)
        self.assertEqual(census["rows"]["physical_supported_row_history_tokens"], 249662)
        self.assertEqual(census["rows"]["physical_supported_row_history_bytes"], 1500675)
        self.assertEqual(census["rows"]["estimated_staging_record_visits_by_street_per_proposal_law"],
                         {0: 30240, 3: 26400, 4: 33640, 5: 16800})
        self.assertEqual(census["rows"]["estimated_staging_record_visits_per_proposal_law"],
                         107080)
        self.assertEqual(census["rows"]["estimated_staging_record_visits_for_both_proposal_laws"],
                         214160)
        self.assertEqual(census["rows"]["estimated_staging_history_tokens_by_street_per_proposal_law"],
                         {0: 35280, 3: 130440, 4: 276700, 5: 189960})
        self.assertEqual(census["rows"]["estimated_staging_history_bytes_by_street_per_proposal_law"],
                         {0: 211680, 3: 845250, 4: 1674080, 5: 1137600})
        self.assertEqual(census["rows"]["estimated_staging_history_tokens_per_proposal_law"],
                         632380)
        self.assertEqual(census["rows"]["estimated_staging_history_bytes_per_proposal_law"],
                         3868610)
        self.assertEqual(census["rows"]["estimated_staging_history_tokens_for_both_proposal_laws"],
                         1264760)
        self.assertEqual(census["rows"]["estimated_staging_history_bytes_for_both_proposal_laws"],
                         7737220)
        self.assertEqual(census["rows"]["unfiltered_row_visits_per_board_two_target_passes"],
                         868)
        self.assertEqual(census["rows"]["unfiltered_action_slot_visits_per_board_two_target_passes"],
                         2078)
        for street in (0, 3, 4, 5):
            for player in (0, 1):
                self.assertEqual(sum(row["supported_rows"]
                                     for row in census["rows"]["by_hand"][street][player]),
                                 census["rows"]["by_actor"][street][player]["supported_rows"])
                self.assertTrue(all(row["betting_history_occurrences"] ==
                                    {0: 3, 3: 16, 4: 58, 5: 140}[street]
                                    for row in census["rows"]["by_hand"][street][player]))
        self.assertEqual(census["rows"]["staged_rows"], None)
        self.assertFalse(census["rows"]["attempted_staging"])
        self.assertEqual(census["rows"]["materialized_row_keys"], 0)
        self.assertEqual(census["target_prior"]["normalizer_z"], Fraction(29, 64))
        self.assertEqual(census["target_prior"]["compatible_pair_probabilities"],
                         (Fraction(3, 29), Fraction(8, 29), Fraction(18, 29)))


if __name__ == "__main__":
    unittest.main()
