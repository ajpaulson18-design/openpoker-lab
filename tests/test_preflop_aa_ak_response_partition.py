"""Cross-check an alternative BR calculation against the literal physical scan."""
from fractions import Fraction as Q
from unittest import TestCase, main
from unittest.mock import patch

from scripts import preflop_aa_ak_response_partition as partition
from scripts import preflop_three_rank_pure_response as reference
from scripts.preflop_mixed_pure_response import INFO_MENUS


def _fixture():
    sb = ("AcAd", "AcKc")
    bb = ("KdKh", "KdKs")
    means = (Q(4, 7), Q(-2, 7), Q(-3, 5), Q(1, 5))
    priors = (Q(1, 7), Q(2, 7), Q(3, 7), Q(1, 7))
    pairs = tuple({"sb_hand": s, "bb_hand": b, "prior": prior, "showdown_mean": mean}
                  for (s, b), prior, mean in zip(((s, b) for s in sb for b in bb), priors, means))
    policy = {}
    for player, hands in enumerate((sb, bb)):
        for hand_index, hand in enumerate(hands):
            for (owner, history), actions in INFO_MENUS.items():
                if owner == player:
                    weights = tuple(Q(i + 1 + hand_index + len(history)) for i in range(len(actions)))
                    mass = sum(weights)
                    policy[(player, hand, history)] = dict(zip(actions, (x / mass for x in weights)))
    return policy, {"sb_hands": sb, "bb_hands": bb, "pairs": pairs}


class PartitionedExactResponseTests(TestCase):
    def test_values_and_complete_argmax_policies_match_the_independent_scan(self):
        policy, game = _fixture()
        for player in (0, 1):
            with self.subTest(player=player):
                expected = reference._best_response(policy, game, player)
                stats = {}
                with patch.object(reference, "_terminal_response", side_effect=AssertionError("reference reused")):
                    observed = partition.best_response(policy, game, player, statistics=stats)
                self.assertEqual(observed, expected)
                self.assertEqual(stats["pair_terminal_contributions"], len(game["pairs"]) * 14)
                self.assertEqual(stats["pure_response_policies_enumerated"], expected[2])

    def test_hidden_opponent_conditioning_is_strictly_more_powerful(self):
        policy, game = _fixture()
        # BB always checks a limp and always calls an opening raise/shove.
        for (player, _hand, history), probabilities in policy.items():
            if player == 1:
                selected = "check" if history == ("call",) else "call"
                for action in probabilities:
                    probabilities[action] = Q(action == selected)
        legal = partition.best_response(policy, game, 0)[0]
        clairvoyant = Q()
        for pair in game["pairs"]:
            hidden = {**game, "sb_hands": (pair["sb_hand"],), "pairs": (pair,)}
            clairvoyant += partition.best_response(policy, hidden, 0)[0]
        self.assertGreater(clairvoyant, legal)

    def test_zero_reach_ties_choose_the_reference_first_complete_policy(self):
        policy, game = _fixture()
        for key, row in policy.items():
            actions = tuple(row)
            for action in actions:
                row[action] = Q(action == actions[0])
        for player in (0, 1):
            self.assertEqual(partition.best_response(policy, game, player),
                             reference._best_response(policy, game, player))

    def test_caps_and_fraction_bounds_reject_without_response_search(self):
        policy, game = _fixture()
        for player in (True, -1, 2):
            with self.subTest(player=player), self.assertRaisesRegex(ValueError, "exact 0 or 1"):
                partition.best_response(policy, game, player)
        with self.assertRaisesRegex(ValueError, "pair census"):
            partition.best_response(policy, {**game, "pairs": game["pairs"] * 22}, 0)
        first = dict(game["pairs"][0], prior=Q(1, 1 << partition.MAX_EXACT_BITS))
        with self.assertRaisesRegex(ValueError, "exact arithmetic"):
            partition.best_response(policy, {**game, "pairs": (first,)}, 0)
        with self.assertRaisesRegex(ValueError, "empty statistics"):
            partition.best_response(policy, game, 0, statistics={"old": 1})


if __name__ == "__main__":
    main()
