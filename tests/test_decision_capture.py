"""Regression tests for transactional practice decision capture and retrieval."""
import json
from pathlib import Path
import shutil
import threading
import unittest
import uuid
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch

from pokerlab.models import Store
from pokerlab.practice import summarize
from pokerlab.server import make_server


BASE = Path(__file__).resolve().parents[1] / "work"
BASE.mkdir(exist_ok=True)


class DecisionCaptureHTTPTests(unittest.TestCase):
    def setUp(self):
        self.directory = BASE / f"capture-{uuid.uuid4().hex}"
        self.directory.mkdir()
        self.database = self.directory / "capture.sqlite3"
        self.server = make_server(0, self.database)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.root = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        shutil.rmtree(self.directory, ignore_errors=True)

    def post(self, path, payload):
        request = Request(self.root + path, json.dumps(payload).encode(),
                          {"Content-Type": "application/json"})
        return json.load(urlopen(request))

    def get(self, path):
        return json.load(urlopen(self.root + path))

    def failed_post(self, path, payload):
        with self.assertRaises(HTTPError) as caught:
            self.post(path, payload)
        with caught.exception as response:
            return response.code, json.load(response)

    def failed_get(self, path):
        with self.assertRaises(HTTPError) as caught:
            self.get(path)
        with caught.exception as response:
            return response.code, json.load(response)

    def new_game(self, stacks=None):
        return self.post("/api/game", {
            "stacks": stacks or [100, 100],
            "names": ["Hero", "Villain"] if len(stacks or [100, 100]) == 2
            else ["Hero", "Villain", "Other"], "seed": 61,
        })

    @staticmethod
    def action(game, action="call", amount=None, client_id=None, revision=None):
        data = {"id": game["id"], "action": action, "amount": amount,
                "coach_visible": False}
        if client_id is not None:
            data["client_action_id"] = client_id
        if revision is not None:
            data["expected_revision"] = revision
        return data

    def test_larger_raise_is_unassessed_and_evidence_is_retrievable(self):
        game = self.new_game()
        legal = game["legal"]
        self.assertTrue(legal["raise"])
        self.assertLess(legal["raise_min"], legal["raise_max"])
        amount = legal["raise_min"] + 1
        request = self.action(game, "raise", amount, "raise-once", 0)
        result = self.post("/api/act", request)
        self.assertEqual(result["revision"], 1)
        self.assertEqual(result["decision"]["assessment_status"], "unassessed_size")
        self.assertIsNone(result["decision"]["assessed_modeled_action_id"])
        self.assertIsNone(result["decision"]["ev_loss"])
        self.assertEqual(result["decision"]["chosen_action_detail"], {
            "name": "raise", "amount": amount, "amount_semantics": "street_total"})
        # A lost HTTP response can be retried with the same client ID and returns
        # the original accepted response even though its expected revision is old.
        self.assertEqual(self.post("/api/act", request), result)
        endpoint = f"/api/v1/decisions/{result['decision']['decision_id']}/analysis"
        captured = self.get(endpoint)
        self.assertEqual(captured["status"], "ready")
        self.assertEqual(captured["analysis"]["ref"], {
            "hand_id": game["id"], "decision_id": result["decision"]["decision_id"],
            "state_revision": 0})
        self.assertEqual(captured["choice"]["assessment_status"], "unassessed_size")
        self.assertEqual(captured["choice"]["amount"], amount)
        self.assertEqual(captured["analysis"]["context"]["hero_cards"],
                         game["hands"][0])
        self.assertNotIn("Villain", json.dumps(captured))
        self.assertNotIn("opponent_cards", json.dumps(captured))
        stored = Store(self.database).session(game["id"])["decisions"]
        self.assertEqual(len(stored), 1)
        self.assertEqual(stored[0]["decision_id"], result["decision"]["decision_id"])

    def test_minimum_raise_is_assessed_and_nonraise_amount_is_normalized(self):
        game = self.new_game()
        result = self.post("/api/act", self.action(
            game, "raise", game["legal"]["raise_min"], "min-raise", 0))
        self.assertEqual(result["decision"]["assessment_status"], "assessed")
        self.assertEqual(result["decision"]["assessed_modeled_action_id"], "raise:min")
        self.assertIsNotNone(result["decision"]["ev_loss"])
        self.assertEqual(result["revision"], 1)

        game = self.new_game()
        action = "call" if game["legal"]["call"] else "check"
        result = self.post("/api/act", self.action(
            game, action, 9999, "call-with-ignored-amount", 0))
        self.assertEqual(result["decision"]["chosen_action_detail"]["amount"],
                         game["legal"]["call"] if action == "call" else 0)
        self.assertIsNone(result["log"][-1]["amount"])

    def test_revision_and_client_id_conflicts_do_not_duplicate_action(self):
        game = self.new_game()
        action = "call" if game["legal"]["call"] else "check"
        request = self.action(game, action, 0, "unique-action", 0)
        first = self.post("/api/act", request)
        self.assertEqual(self.failed_post("/api/act", {
            **request, "expected_revision": True})[0], 400)
        self.assertEqual(self.failed_post("/api/act", {
            **request, "action": "fold" if action != "fold" else "check"})[0], 409)
        stale = self.action(first, "check", None, "second-action", 0)
        self.assertEqual(self.failed_post("/api/act", stale)[0], 409)
        rows = Store(self.database).session(game["id"])["decisions"]
        self.assertEqual(len(rows), 1)

    def test_failed_save_keeps_live_hand_and_retryable_revision_unchanged(self):
        game = self.new_game()
        action = "call" if game["legal"]["call"] else "check"
        request = self.action(game, action, 0, "retry-after-save-error", 0)
        with patch.object(Store, "save_decision", side_effect=RuntimeError("injected failure")):
            status, _ = self.failed_post("/api/act", request)
        self.assertEqual(status, 500)
        with Store(self.database).connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM decisions").fetchone()[0], 0)
        accepted = self.post("/api/act", request)
        self.assertEqual(accepted["revision"], 1)
        self.assertEqual(accepted["decision_order"], 1)
        with Store(self.database).connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM decisions").fetchone()[0], 1)

    def test_evidence_insert_failure_rolls_back_decision_and_session_completion(self):
        game = self.new_game()
        store = Store(self.database)
        with store.connect() as db:
            db.execute("""CREATE TRIGGER reject_coach_evidence BEFORE INSERT ON coach_decision_evidence
                         BEGIN SELECT RAISE(ABORT, 'injected evidence failure'); END""")
        self.assertTrue(game["legal"]["fold"])
        request = self.action(game, "fold", 0, "atomic-failure", 0)
        self.assertEqual(self.failed_post("/api/act", request)[0], 500)
        with store.connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM decisions").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM coach_decision_evidence").fetchone()[0], 0)
            self.assertIsNone(db.execute("SELECT completed_at FROM sessions WHERE id=?",
                                         (game["id"],)).fetchone()[0])
        with store.connect() as db:
            db.execute("DROP TRIGGER reject_coach_evidence")
        retried = self.post("/api/act", request)
        self.assertEqual(retried["revision"], 1)
        self.assertTrue(retried["done"])
        with store.connect() as db:
            self.assertIsNotNone(db.execute("SELECT completed_at FROM sessions WHERE id=?",
                                            (game["id"],)).fetchone()[0])

    def test_adapter_and_presentation_failures_do_not_advance_or_persist(self):
        game = self.new_game()
        action = "call" if game["legal"]["call"] else "check"
        request = self.action(game, action, 0, "retry-preparation", 0)
        with patch("pokerlab.server.adapt_practice_analysis",
                   side_effect=ValueError("injected adapter failure")):
            self.assertEqual(self.failed_post("/api/act", request)[0], 400)
        with Store(self.database).connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM decisions").fetchone()[0], 0)
        with patch("pokerlab.server.build_coach_explanation",
                   side_effect=RuntimeError("injected presentation failure")):
            visible_request = {**request, "coach_visible": True}
            status, _ = self.failed_post("/api/act", visible_request)
            self.assertEqual(status, 500)
        with Store(self.database).connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM decisions").fetchone()[0], 0)
        accepted = self.post("/api/act", request)
        self.assertEqual(accepted["revision"], 1)

    def test_legacy_evidence_status_unknown_id_and_tamper_are_controlled(self):
        store = Store(self.database)
        stored = store.save_decision("legacy-session", {"chosen_action": "call"})
        self.assertEqual(self.get(
            f"/api/v1/decisions/{stored['decision_id']}/analysis"), {
                "status": "unavailable",
                "reason": "Versioned coach evidence was not captured for this decision."})
        self.assertEqual(self.failed_get("/api/v1/decisions/missing/analysis")[0], 404)

        game = self.new_game()
        action = "call" if game["legal"]["call"] else "check"
        result = self.post("/api/act", self.action(game, action, 0, "tamper", 0))
        decision_id = result["decision"]["decision_id"]
        with store.connect() as db:
            db.execute("UPDATE coach_decision_evidence SET envelope=? WHERE decision_id=?",
                       ("{}", decision_id))
        status, payload = self.failed_get(f"/api/v1/decisions/{decision_id}/analysis")
        self.assertEqual(status, 500)
        self.assertEqual(payload, {"status": "failed",
                                   "error": "Stored decision evidence is invalid."})

    def test_review_excludes_unassessed_raise_and_old_raise_without_amount(self):
        base = {"decision_order": 1, "analysis_at_time": {
            "recommended": "raise", "baseline_recommended": "check"},
            "chosen_action": "raise", "ev_loss": 9.0,
            "matched_recommendation": True, "successful_exploit": True,
            "exploit_gain": 7.0}
        assessed = {**base, "decision_order": 2, "chosen_action": "call",
                    "chosen_action_detail": {"name": "call", "amount": 2,
                                              "amount_semantics": "chips_added"},
                    "ev_loss": 2.0, "matched_recommendation": False,
                    "successful_exploit": False, "exploit_gain": 0.0}
        review = summarize([base, assessed])
        self.assertEqual(review["analyzed_decisions"], 2)
        self.assertEqual(review["assessed_decisions"], 1)
        self.assertEqual(review["unassessed_decisions"], 1)
        self.assertEqual(review["total_ev_loss"], 2.0)
        self.assertEqual(review["matched_recommendation"], 0)
        self.assertEqual(review["successful_exploits"], 0)


if __name__ == "__main__":
    unittest.main()
