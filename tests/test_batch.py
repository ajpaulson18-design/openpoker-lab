import random
import unittest

from pokerlab.archetypes import (ArchetypePolicy, chen_score, hand_strength,
                                 play_hand, preflop_strength)
from pokerlab.batch import simulate_hands
from pokerlab.cards import cards
from pokerlab.game import Game
from pokerlab.models import ARCHETYPE_PRIORS


class ChenScoreTests(unittest.TestCase):
    def test_known_reference_scores(self):
        # Published reference values for the classic Chen formula.
        self.assertEqual(chen_score(cards('AsAh')), 20)
        self.assertEqual(chen_score(cards('KsKh')), 16)
        self.assertEqual(chen_score(cards('2d2c')), 5)
        self.assertEqual(chen_score(cards('AsKs')), 12)
        self.assertEqual(chen_score(cards('AsKh')), 10)
        self.assertEqual(chen_score(cards('TsJs')), 9)

    def test_percentile_is_monotonic_and_bounded(self):
        self.assertEqual(preflop_strength(cards('AsAh')), 1.0)
        self.assertGreater(preflop_strength(cards('AsAh')), preflop_strength(cards('KsKh')))
        self.assertGreater(preflop_strength(cards('KsKh')), preflop_strength(cards('7h2c')))
        for hand in (cards('AsAh'), cards('7h2c'), cards('TsJs')):
            self.assertTrue(0 <= preflop_strength(hand) <= 1)


class HandStrengthTests(unittest.TestCase):
    def test_postflop_strength_respects_hand_category_order(self):
        board = cards('2c7d9hJs')
        trips = hand_strength(cards('2s2h'), board)
        pair = hand_strength(cards('JcTc'), board)
        high = hand_strength(cards('KsQd'), board)
        self.assertGreater(trips, pair)
        self.assertGreater(pair, high)

    def test_preflop_uses_no_board(self):
        self.assertEqual(hand_strength(cards('AsAh'), ()), preflop_strength(cards('AsAh')))


class ArchetypePolicyLegalityTests(unittest.TestCase):
    def test_every_decision_is_legal_across_many_random_hands(self):
        rng = random.Random(99)
        for trial in range(200):
            stacks = [rng.randint(2, 400) for _ in range(rng.randint(2, 6))]
            archetypes = [rng.choice(list(ARCHETYPE_PRIORS)) for _ in stacks]
            game = Game(stacks, seed=trial)
            policies = {i: ArchetypePolicy(a, random.Random(trial * 7 + i))
                       for i, a in enumerate(archetypes)}
            actions = 0
            while not game.done:
                legal = game.legal()
                action, amount = policies[game.actor].decide(game, game.actor)
                self.assertTrue(legal.get(action), f"{action} illegal in {legal}")
                if action == "raise":
                    self.assertIsInstance(amount, int)
                    self.assertTrue(legal["raise_min"] <= amount <= legal["raise_max"])
                game.act(action, amount)
                actions += 1
                self.assertLess(actions, 400)
            self.assertEqual(sum(game.stacks), sum(stacks))

    def test_unknown_archetype_rejected(self):
        with self.assertRaises(ValueError):
            ArchetypePolicy('not-a-real-archetype', random.Random(1))


class BatchSimulationTests(unittest.TestCase):
    def test_deterministic_with_same_seed(self):
        a = simulate_hands([200, 200], ['balanced', 'balanced'], trials=300, seed=5)
        b = simulate_hands([200, 200], ['balanced', 'balanced'], trials=300, seed=5)
        self.assertEqual(a, b)

    def test_different_seed_changes_results(self):
        a = simulate_hands([200, 200], ['balanced', 'balanced'], trials=300, seed=5)
        b = simulate_hands([200, 200], ['balanced', 'balanced'], trials=300, seed=6)
        self.assertNotEqual(a['seats'][0]['total_net'], b['seats'][0]['total_net'])

    def test_every_hand_is_exactly_zero_sum(self):
        r = simulate_hands([150, 150, 150], ['maniac', 'nit', 'calling_station'],
                           trials=500, seed=3)
        self.assertAlmostEqual(sum(s['total_net'] for s in r['seats']), 0.0, places=9)
        self.assertAlmostEqual(
            sum(p['mean_net_per_hand'] * p['hands'] for p in r['positional_effects']),
            0.0, places=6)

    def test_nit_folds_far_more_than_maniac(self):
        r = simulate_hands([200, 200], ['nit', 'maniac'], trials=4000, seed=12)
        nit, maniac = r['seats']
        self.assertGreater(nit['observed_fold_to_bet'], maniac['observed_fold_to_bet'])
        self.assertLess(nit['observed_vpip'], maniac['observed_vpip'])
        self.assertLess(nit['observed_pfr'], maniac['observed_pfr'])

    def test_showdown_rate_is_per_seat_not_table_wide(self):
        r = simulate_hands([200, 200, 200], ['nit', 'maniac', 'maniac'], trials=3000, seed=7)
        nit, maniac_a, maniac_b = r['seats']
        # A seat cannot reach showdown far more often than it voluntarily plays a hand.
        self.assertLessEqual(nit['showdown_rate'], nit['observed_vpip'] + 1e-9)
        self.assertLess(nit['showdown_rate'], maniac_a['showdown_rate'])

    def test_trials_times_seats_is_capped(self):
        with self.assertRaises(ValueError):
            simulate_hands([200] * 6, ['maniac'] * 6, trials=20000, seed=1)
        # A 6-seat request within the combined cap still succeeds.
        simulate_hands([200] * 6, ['maniac'] * 6, trials=6000, seed=1)

    def test_multiway_table_runs_and_reports_every_seat(self):
        archetypes = ['nit', 'maniac', 'calling_station', 'loose_passive',
                      'tight_passive', 'balanced']
        r = simulate_hands([200] * 6, archetypes, trials=400, seed=21)
        self.assertEqual(len(r['seats']), 6)
        self.assertEqual(len(r['positional_effects']), 6)
        for seat in r['seats']:
            self.assertEqual(seat['hands'], 400)
            self.assertTrue(0 <= seat['win_rate'] <= 1)
            self.assertIn('assumption', r)

    def test_button_rotation_can_be_disabled(self):
        r = simulate_hands([200, 200], ['balanced', 'balanced'], trials=50,
                           seed=1, button=0, rotate_button=False)
        # With no rotation and identical archetypes, seat 0 is always the same position.
        self.assertEqual(r['positional_effects'][0]['hands'], 50)
        self.assertEqual(r['positional_effects'][1]['hands'], 50)

    def test_invalid_configuration_is_rejected(self):
        with self.assertRaises(ValueError):
            simulate_hands([200], ['balanced'], trials=100, seed=1)  # too few seats
        with self.assertRaises(ValueError):
            simulate_hands([200, 200], ['balanced'], trials=100, seed=1)  # mismatched lengths
        with self.assertRaises(ValueError):
            simulate_hands([200, 200], ['balanced', 'not-real'], trials=100, seed=1)
        with self.assertRaises(ValueError):
            simulate_hands([200, 200], ['balanced', 'balanced'], trials=10, seed=1)  # too few trials
        with self.assertRaises(ValueError):
            simulate_hands([200, 200], ['balanced', 'balanced'], trials=100_000, seed=1)


if __name__ == '__main__':
    unittest.main()
