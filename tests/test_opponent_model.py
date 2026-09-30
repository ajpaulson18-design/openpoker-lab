import sqlite3
import tempfile
import unittest
from pathlib import Path

from pokerlab.contracts import TendencyContext
from pokerlab.models import (ARCHETYPE_PRIORS, OpponentDataError, Store,
                             TENDENCIES)


class OpponentModelV2Tests(unittest.TestCase):
    def store(self, directory, name="model.sqlite3"):
        return Store(Path(directory) / name)

    def test_priors_affect_zero_observation_estimates(self):
        with tempfile.TemporaryDirectory() as directory:
            store = self.store(directory)
            station = store.create_opponent("Station", "calling_station")
            nit = store.create_opponent("Nit", "nit")
            station_fold = store.get_tendency_estimate(station["id"], "fold_to_bet")
            nit_fold = store.get_tendency_estimate(nit["id"], "fold_to_bet")
            self.assertEqual(station_fold.posterior_mean,
                             ARCHETYPE_PRIORS["calling_station"]["fold_to_bet"])
            self.assertEqual(station_fold.opportunities, 0)
            self.assertGreater(nit_fold.posterior_mean, station_fold.posterior_mean)

    def test_observations_update_posterior_and_evidence_is_inspectable(self):
        with tempfile.TemporaryDirectory() as directory:
            store = self.store(directory)
            opponent = store.create_opponent("Player")
            initial = store.get_tendency_estimate(opponent["id"], "fold_to_bet")
            store.record_observation(opponent["id"], "fold_to_bet", 8, 10,
                                     TendencyContext("river", action_context="facing_bet"),
                                     "Ten observed river decisions", "batch-1")
            evidence = store.get_tendency_evidence(
                opponent["id"], "fold_to_bet",
                TendencyContext("river", action_context="facing_bet"))
            self.assertGreater(evidence.estimate.posterior_mean, initial.posterior_mean)
            self.assertEqual((evidence.estimate.successes, evidence.estimate.opportunities),
                             (8, 10))
            self.assertEqual(evidence.observations[0].observation_id, "batch-1")

    def test_uncertainty_decreases_with_more_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            store = self.store(directory)
            opponent = store.create_opponent("Player")
            before = store.get_tendency_estimate(opponent["id"], "aggression")
            store.record_observation(opponent["id"], "aggression", 75, 150)
            after = store.get_tendency_estimate(opponent["id"], "aggression")
            before_width = before.uncertainty.upper - before.uncertainty.lower
            after_width = after.uncertainty.upper - after.uncertainty.lower
            self.assertLess(after_width, before_width)
            self.assertEqual(after.uncertainty.confidence, "higher")

    def test_archetype_prior_can_be_overcome(self):
        with tempfile.TemporaryDirectory() as directory:
            store = self.store(directory)
            opponent = store.create_opponent("Reformed station", "calling_station")
            store.record_observation(opponent["id"], "fold_to_bet", 90, 100)
            estimate = store.get_tendency_estimate(opponent["id"], "fold_to_bet")
            self.assertGreater(estimate.posterior_mean, .8)
            self.assertGreater(estimate.posterior_mean,
                               ARCHETYPE_PRIORS["calling_station"]["fold_to_bet"])

    def test_street_specific_observations_are_separated(self):
        with tempfile.TemporaryDirectory() as directory:
            store = self.store(directory)
            opponent = store.create_opponent("Player")
            store.record_observation(opponent["id"], "fold_to_bet", 10, 10, "river")
            store.record_observation(opponent["id"], "fold_to_bet", 0, 10, "turn")
            river = store.get_tendency_estimate(opponent["id"], "fold_to_bet", "river")
            turn = store.get_tendency_estimate(opponent["id"], "fold_to_bet", "turn")
            pooled = store.get_tendency_estimate(opponent["id"], "fold_to_bet")
            self.assertGreater(river.posterior_mean, turn.posterior_mean)
            self.assertEqual((river.opportunities, turn.opportunities,
                              pooled.opportunities), (10, 10, 20))

    def test_save_reload_preserves_model_and_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "model.sqlite3"
            store = Store(path)
            opponent = store.create_opponent("Player", "overbluffer")
            store.record_observation(
                opponent["id"], "showdown_bluff", 4, 9,
                TendencyContext("river", "button", "shown_aggression",
                                (("pot", "single-raised"),)),
                observation_id="history-1")
            expected = store.opponent_snapshot(opponent["id"])
            actual = Store(path).opponent_snapshot(opponent["id"])
            self.assertEqual(actual, expected)

    def test_legacy_opponent_records_are_migrated_lazily_and_remain_usable(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "legacy.sqlite3"
            db = sqlite3.connect(path)
            try:
                db.executescript("""
                    CREATE TABLE opponents (id TEXT PRIMARY KEY, name TEXT NOT NULL,
                                            profile TEXT NOT NULL);
                    CREATE TABLE observations (
                        id TEXT PRIMARY KEY, opponent_id TEXT NOT NULL,
                        metric TEXT NOT NULL, street TEXT NOT NULL,
                        success INTEGER NOT NULL, note TEXT NOT NULL,
                        created_at TEXT DEFAULT CURRENT_TIMESTAMP);
                    CREATE TABLE analyses (
                        id TEXT PRIMARY KEY, input TEXT NOT NULL, result TEXT NOT NULL,
                        created_at TEXT DEFAULT CURRENT_TIMESTAMP);
                    INSERT INTO opponents VALUES ('legacy-id','Legacy','tight');
                    INSERT INTO observations(id,opponent_id,metric,street,success,note)
                    VALUES ('old-hand','legacy-id','fold_to_bet','river',1,'old data');
                """)
                db.commit()
            finally:
                db.close()
            store = Store(path)
            evidence = store.get_tendency_evidence("legacy-id", "fold_to_bet", "river")
            self.assertEqual((evidence.estimate.successes,
                              evidence.estimate.opportunities), (1, 1))
            self.assertTrue(evidence.observations[0].legacy)
            self.assertEqual(len(store.opponent_snapshot("legacy-id").tendencies),
                             len(TENDENCIES))

    def test_malformed_observations_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            store = self.store(directory)
            opponent = store.create_opponent("Player")
            invalid = [
                ("not-a-tendency", 1, 1, None),
                ("fold_to_bet", True, 1, None),
                ("fold_to_bet", 1, 1, "sixth-street"),
                ("vpip", 1, 1, "river"),
            ]
            for tendency, successes, opportunities, context in invalid:
                with self.subTest(tendency=tendency, context=context):
                    with self.assertRaises(ValueError):
                        store.record_observation(opponent["id"], tendency, successes,
                                                 opportunities, context)

    def test_impossible_counts_cannot_be_created(self):
        with tempfile.TemporaryDirectory() as directory:
            store = self.store(directory)
            opponent = store.create_opponent("Player")
            for successes, opportunities in ((2, 1), (-1, 2), (0, 0), (1, -1)):
                with self.subTest(counts=(successes, opportunities)):
                    with self.assertRaises(ValueError):
                        store.record_observation(opponent["id"], "aggression",
                                                 successes, opportunities)

    def test_identical_history_produces_identical_snapshots(self):
        with tempfile.TemporaryDirectory() as directory:
            store = self.store(directory)
            opponent = store.create_opponent("Player", "maniac")
            for identity, successes, opportunities, street in (
                    ("a", 2, 3, "flop"), ("b", 1, 4, "river")):
                store.record_observation(opponent["id"], "aggression", successes,
                                         opportunities, street,
                                         observation_id=identity)
            first = store.opponent_snapshot(opponent["id"])
            second = store.opponent_snapshot(opponent["id"])
            self.assertEqual(first, second)

    def test_reset_reinitializes_prior_and_can_clear_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            store = self.store(directory)
            opponent = store.create_opponent("Player", "nit")
            store.record_observation(opponent["id"], "vpip", 8, 10, "preflop")
            snapshot = store.reset_opponent_model(opponent["id"], "loose_passive")
            self.assertEqual(snapshot.prior_archetype, "loose_passive")
            estimate = snapshot.tendency("vpip")
            self.assertEqual(estimate.opportunities, 0)
            self.assertEqual(estimate.posterior_mean,
                             ARCHETYPE_PRIORS["loose_passive"]["vpip"])

    def test_corrupt_legacy_evidence_fails_explicitly(self):
        with tempfile.TemporaryDirectory() as directory:
            store = self.store(directory)
            opponent = store.create_opponent("Player")
            db = sqlite3.connect(store.path)
            try:
                db.execute("""INSERT INTO observations
                           (id,opponent_id,metric,street,success,note)
                           VALUES ('bad',?,'fold_to_bet','river',3,'bad')""",
                           (opponent["id"],))
                db.commit()
            finally:
                db.close()
            with self.assertRaises(OpponentDataError):
                store.get_tendency_estimate(opponent["id"], "fold_to_bet")


if __name__ == "__main__":
    unittest.main()
