import copy
import json
import unittest
from fractions import Fraction
from unittest.mock import patch

from scripts import preflop_aa_ak_pure_response as audit
from scripts import preflop_mixed_pure_response as rules


def synthetic_sources():
    # Zero-mean showdown source rows keep the tiny exact equilibrium fixture
    # independent of any newly generated board counts.
    counts = (856_152, 0, 856_152, audit.BOARD_COUNT)
    return {key: (*counts, ("a" * 64)) for key in (
        *audit._AA_SOURCES.values(), audit._AKS_SOURCE, *audit._AKO_SOURCES.values())}


def synthetic_sources_by_mean():
    source_means = {
        **{key: {0: 1, 1: -1, 2: 1}[overlap]
           for overlap, key in audit._AA_SOURCES.items()},
        audit._AKS_SOURCE: 1,
        **{key: {0: -1, 1: 1}[overlap]
           for overlap, key in audit._AKO_SOURCES.items()},
    }
    result = {}
    for key, mean in source_means.items():
        counts = ((audit.BOARD_COUNT, 0, 0, audit.BOARD_COUNT) if mean == 1
                  else (0, 0, audit.BOARD_COUNT, audit.BOARD_COUNT))
        result[key] = (*counts, "b" * 64)
    return result


def policy_rows(action_by_key=None):
    action_by_key = action_by_key or {}
    sb_hands, bb_hands, _pairs, _counts = audit._literal_support()
    rows = []
    for player, hands in ((0, sb_hands), (1, bb_hands)):
        for hand in hands:
            for (owner, history), menu in rules.INFO_MENUS.items():
                if owner != player:
                    continue
                key = (player, hand, history)
                action = action_by_key.get(key, menu[0])
                probs = ["1" if item == action else "0" for item in menu]
                rows.append({"player": player, "hand": hand,
                             "history": list(history), "actions": list(menu),
                             "probabilities": probs})
    return rows


def equilibrium_rows():
    # With zero showdown means, limp/check and call every raise is an exact
    # mutual response: every reached pot is zero and every fold deviation loses.
    chosen = {
        (0, "", ()): "call",
        (0, "", ("call", "raise@2")): "call",
        (0, "", ("call", "all_in@3")): "call",
        (0, "", ("raise@2", "all_in@3")): "call",
        (1, "", ("call",)): "check",
        (1, "", ("raise@2",)): "all_in@3",
        (1, "", ("all_in@3",)): "call",
        (1, "", ("call", "raise@2", "all_in@3")): "call",
    }
    # Expand the same legal choices to every own hand.
    sb, bb, _, _ = audit._literal_support()
    full = {}
    for player, hands in ((0, sb), (1, bb)):
        for hand in hands:
            for (owner, history), _menu in rules.INFO_MENUS.items():
                if owner == player:
                    full[(player, hand, history)] = chosen[(player, "", history)]
    return policy_rows(full)


class AAKKPureResponseTests(unittest.TestCase):
    def setUp(self):
        self.game = audit._build_game(synthetic_sources())

    def test_literal_census_priors_and_source_class_transport(self):
        game = self.game
        self.assertEqual((len(game["sb_hands"]), len(game["bb_hands"]), len(game["pairs"])),
                         (22, 6, 84))
        self.assertEqual(game["type_pair_counts"], {"AA": 36, "AKs": 12, "AKo": 36})
        self.assertEqual(sum((p["prior"] for p in game["pairs"]), Fraction()), 1)
        self.assertEqual({p["prior"] for p in game["pairs"]}, {Fraction(1, 84)})
        self.assertEqual({p["source_identity_sha256"] for p in game["pairs"]}, {"a" * 64})

    def test_zero_mean_legal_profile_is_exact_mutual_response(self):
        with patch.object(audit, "_build_game", return_value=self.game):
            result = audit.verify_policy(equilibrium_rows(), "0")
        self.assertEqual(result["profile_value_sb_fraction"], "0")
        self.assertEqual(result["nash_conv_fraction"], "0")
        self.assertTrue(result["exact_mutual_response_verified"])
        self.assertEqual(result["pure_response_policies_enumerated"],
                         {"sb": 1056, "bb": 216, "total": 1272})
        self.assertEqual((len(result["sb_by_hand"]), len(result["bb_by_hand"])), (22, 6))

    def test_non_equilibrium_profile_reports_exact_gap_not_false_failure(self):
        # Apply the fold choice at every SB starting-hand row.
        folded = policy_rows({(0, hand, ()): "fold" for hand in self.game["sb_hands"]})
        with patch.object(audit, "_build_game", return_value=self.game):
            result = audit.verify_policy(folded)
        self.assertEqual(result["profile_value_sb_fraction"], "-1/2")
        self.assertEqual(result["nash_conv_fraction"], "3/2")
        self.assertEqual(result["status"], "failed")
        self.assertFalse(result["exact_mutual_response_verified"])

    def test_profile_value_and_response_are_summed_over_hidden_hands(self):
        # A deterministic, legal own-hand policy is accepted for analysis and
        # returns one independently selected BR witness per private hand.
        rows = policy_rows()
        with patch.object(audit, "_build_game", return_value=self.game):
            result = audit.verify_policy(rows)
        self.assertEqual(len(result["sb_by_hand"]), 22)
        self.assertEqual(len(result["bb_by_hand"]), 6)
        self.assertEqual({row["pure_policies_enumerated"] for row in result["sb_by_hand"]}, {48})
        self.assertEqual({row["pure_policies_enumerated"] for row in result["bb_by_hand"]}, {36})
        self.assertTrue(all(len(row["best_actions"]) == 4 for row in
                            result["sb_by_hand"] + result["bb_by_hand"]))

    def test_legal_own_hand_response_is_below_opponent_card_control(self):
        game = audit._build_game(synthetic_sources_by_mean())
        choices = {}
        for hand in game["bb_hands"]:
            choices[(1, hand, ("call",))] = "all_in@3"
            choices[(1, hand, ("raise@2",))] = "all_in@3"
            choices[(1, hand, ("all_in@3",))] = "call"
            choices[(1, hand, ("call", "raise@2", "all_in@3"))] = "call"
        parsed = audit._policy(policy_rows(choices), game)
        legal = rules._best_response(parsed, game, 0)[0]
        clairvoyant = rules._clairvoyant_response(parsed, game, 0)[0]
        self.assertGreater(clairvoyant, legal)

    def test_malformed_rows_reject_before_source_authentication(self):
        invalids = []
        rows = equilibrium_rows()
        invalids.append(rows[:-1])
        duplicate = copy.deepcopy(rows)
        duplicate[-1] = copy.deepcopy(duplicate[0])
        invalids.append(duplicate)
        leaked = copy.deepcopy(rows)
        leaked[0]["opponent_hand"] = "KdKs"
        invalids.append(leaked)
        bool_player = copy.deepcopy(rows)
        bool_player[0]["player"] = False
        invalids.append(bool_player)
        malformed_fraction = copy.deepcopy(rows)
        malformed_fraction[0]["probabilities"][0] = "1e1000000000"
        invalids.append(malformed_fraction)
        wrong_menu = copy.deepcopy(rows)
        wrong_menu[0]["actions"][0] = "opponent-conditioned-action"
        invalids.append(wrong_menu)
        for candidate in invalids:
            with self.subTest(case=len(invalids)):
                with patch.object(audit, "_build_game", side_effect=AssertionError("source read")):
                    with self.assertRaises(ValueError):
                        audit.verify_policy(candidate)

    def test_noncanonical_fraction_and_source_rows_reject(self):
        malformed = copy.deepcopy(equilibrium_rows())
        malformed[0]["probabilities"] = ["2/2", "0", "0", "0"]
        with patch.object(audit, "_build_game", side_effect=AssertionError("source read")):
            with self.assertRaises(ValueError):
                audit.verify_policy(malformed)
        bad_sources = synthetic_sources()
        key = next(iter(bad_sources))
        bad_sources[key] = (856_152, 0, 856_151, audit.BOARD_COUNT, "a" * 64)
        with self.assertRaises(ValueError):
            audit._build_game(bad_sources)

    def test_json_roundtrip_of_census_fields(self):
        with patch.object(audit, "_build_game", return_value=self.game):
            result = audit.verify_policy(equilibrium_rows(), "0")
        self.assertEqual(json.loads(json.dumps(result)), result)

    def test_receipt_source_pins_do_not_alias_future_authority(self):
        with patch.object(audit, "_build_game", return_value=self.game):
            result = audit.verify_policy(equilibrium_rows(), "0")
        before = audit.sources.SOURCE_PINS["aa"]["path"]
        result["source_basis_pins"]["aa"]["path"] = "mutated"
        self.assertEqual(audit.sources.SOURCE_PINS["aa"]["path"], before)


if __name__ == "__main__":
    unittest.main()
