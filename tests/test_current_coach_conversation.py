"""HTTP tests for bounded, preview-bound live coach follow-ups."""
import json
from pathlib import Path
import shutil
import threading
import unittest
import uuid
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from tests.test_current_coach import FakeSelector
from pokerlab.server import make_server


BASE = Path(__file__).resolve().parents[1] / "work" / "current-coach-conversation-tests"
BASE.mkdir(parents=True, exist_ok=True)


class CurrentCoachConversationTests(unittest.TestCase):
    def setUp(self):
        self.directory = BASE / f"run-{uuid.uuid4().hex}"
        self.directory.mkdir()
        self.clock = [100.0]
        self.selector = FakeSelector()
        self.server = make_server(0, self.directory / "coach.sqlite3",
                                  coach_selector=self.selector, coach_enabled=True,
                                  coach_timeout=0.25, coach_clock=lambda: self.clock[0])
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.root = f"http://127.0.0.1:{self.server.server_port}"
        self.game = self.post_json("/api/game", {
            "stacks": [100, 100], "names": ["Hero", "Villain"], "seed": 91,
        })
        self.preview = self.preview_for(self.game)
        self.target = self.preview["binding"]

    def tearDown(self):
        self.selector.release.set()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        shutil.rmtree(self.directory, ignore_errors=True)

    def request(self, path, payload, *, external=False, timeout=6):
        headers = {"Content-Type": "application/json"}
        if external:
            headers["X-OpenPoker-External-AI"] = "1"
        request = Request(self.root + path, json.dumps(payload).encode(), headers)
        try:
            with urlopen(request, timeout=timeout) as response:
                return response.status, json.load(response)
        except HTTPError as error:
            with error:
                return error.code, json.load(error)

    def post_json(self, path, payload, *, external=False):
        status, result = self.request(path, payload, external=external)
        self.assertEqual(status, 200, result)
        return result

    def preview_for(self, game):
        return self.post_json(f"/api/v1/hands/{game['id']}/current-study", {
            "expected_revision": game["revision"], "opponent_id": None,
        })

    def body(self, *, question="What is the current modeled recommendation?",
             client_turn_id=None, conversation_id=None, target=None, detail="normal",
             audience="standard"):
        body = {
            "client_turn_id": client_turn_id or str(uuid.uuid4()),
            "target": dict(target or self.target),
            "question": question, "detail": detail, "audience": audience,
        }
        if conversation_id is not None:
            body["conversation_id"] = conversation_id
        return body

    def turn_path(self, hand_id=None):
        return f"/api/v1/hands/{hand_id or self.game['id']}/current-coach/turns"

    def test_followups_keep_binding_and_send_only_opted_in_validated_context(self):
        first_body = self.body(question="What is the current modeled recommendation?")
        first = self.post_json(self.turn_path(), first_body, external=True)
        self.assertEqual(first["status"], "ready")
        self.assertEqual(first["turn_index"], 1)
        self.assertEqual(first["binding"], self.target)
        self.assertEqual(first["client_turn_id"], first_body["client_turn_id"])
        self.assertNotIn("choice", {fact["kind"] for block in first["reply"]["blocks"]
                                     for fact in block["facts"]})
        self.assertEqual(len(self.selector.calls), 1)

        second_body = self.body(
            client_turn_id=str(uuid.uuid4()), conversation_id=first["conversation_id"],
            question="Explain the recommendation more simply.", detail="short",
            audience="beginner")
        second = self.post_json(self.turn_path(), second_body, external=True)
        self.assertEqual(second["status"], "ready")
        self.assertEqual(second["turn_index"], 2)
        self.assertEqual(second["conversation_id"], first["conversation_id"])
        self.assertEqual(second["binding"], first["binding"])
        self.assertEqual(len(self.selector.calls), 2)
        self.assertEqual(self.selector.calls[1][1:], (
            second_body["question"], "short", "beginner",
            ({"question": first_body["question"],
              "intent": first["reply"]["intent"],
              "target_action_id": first["reply"].get("target_action_id"),
              "detail": "normal", "audience": "standard"},), True))

    def test_local_fallback_turn_is_not_reused_as_provider_strategy_context(self):
        first_body = self.body()
        first = self.post_json(self.turn_path(), first_body, external=True)
        self.assertEqual(first["status"], "ready")
        second_body = self.body(client_turn_id=str(uuid.uuid4()),
                                conversation_id=first["conversation_id"],
                                question="Explain this preview.")
        second = self.post_json(self.turn_path(), second_body, external=False)
        self.assertEqual(second["source"], "local_fallback")
        self.assertEqual(second["turn_index"], 2)
        third_body = self.body(client_turn_id=str(uuid.uuid4()),
                               conversation_id=first["conversation_id"],
                               question="What is the current modeled recommendation?")
        third = self.post_json(self.turn_path(), third_body, external=True)
        self.assertEqual(third["turn_index"], 3)
        self.assertEqual(len(self.selector.calls), 2)
        self.assertEqual(self.selector.calls[1][4], (
            {"question": first_body["question"],
             "intent": "recommendation", "target_action_id": None,
             "detail": "normal", "audience": "standard"},))

    def test_four_turn_limit_retry_conflict_and_new_conversation(self):
        first_body = self.body()
        first = self.post_json(self.turn_path(), first_body, external=True)
        replay = self.post_json(self.turn_path(), first_body, external=True)
        self.assertEqual(replay, first)
        self.assertEqual(len(self.selector.calls), 1)
        status, conflict = self.request(self.turn_path(), first_body, external=False)
        self.assertEqual(status, 409)
        self.assertEqual(conflict["code"], "turn_id_conflict")

        results = [first]
        for index in range(2, 5):
            results.append(self.post_json(self.turn_path(), self.body(
                conversation_id=first["conversation_id"],
                question=f"What does turn {index} mean?"), external=True))
        self.assertEqual([result["turn_index"] for result in results], [1, 2, 3, 4])
        status, full = self.request(self.turn_path(), self.body(
            conversation_id=first["conversation_id"], question="Fifth question"))
        self.assertEqual(status, 409)
        self.assertEqual(full["code"], "conversation_full")
        fresh = self.post_json(self.turn_path(), self.body(question="Start over"))
        self.assertEqual(fresh["turn_index"], 1)
        self.assertNotEqual(fresh["conversation_id"], first["conversation_id"])

    def test_choice_loss_and_invalid_turn_ids_fail_closed(self):
        for question in ("Was my call wrong?", "Did I make a bad call?",
                         "How much did I lose on my chosen action?"):
            result = self.post_json(self.turn_path(), self.body(question=question), external=True)
            self.assertEqual(result["reply"]["intent"], "unavailable")
            self.assertIn("choice", result["reply"]["unavailable_fields"])
            self.assertIn("choice_loss", result["reply"]["unavailable_fields"])
        self.assertEqual(self.selector.calls, [])
        status, invalid = self.request(self.turn_path(), self.body(client_turn_id="predictable"))
        self.assertEqual(status, 400)
        self.assertEqual(invalid["code"], "invalid_request")

    def test_unknown_mismatched_and_expired_targets_are_controlled(self):
        first = self.post_json(self.turn_path(), self.body())
        status, missing = self.request(self.turn_path(), self.body(
            conversation_id="unknown-conversation"))
        self.assertEqual(status, 410)
        self.assertEqual(missing["code"], "conversation_expired")

        other_game = self.post_json("/api/game", {
            "stacks": [100, 100], "names": ["Other", "Villain"], "seed": 92,
        })
        other_target = self.preview_for(other_game)["binding"]
        status, mismatch = self.request(self.turn_path(other_game["id"]), self.body(
            conversation_id=first["conversation_id"], target=other_target,
            question="Switch preview"))
        self.assertEqual(status, 409)
        self.assertEqual(mismatch["code"], "binding_mismatch")

        self.clock[0] += 61
        status, expired = self.request(self.turn_path(), self.body(
            conversation_id=first["conversation_id"], question="After preview expiry"))
        self.assertEqual(status, 409)
        self.assertEqual(expired["code"], "preview_expired")
        self.assertTrue(expired["refresh_required"])

    def test_gameplay_advances_during_provider_wait_and_turn_aborts_as_stale(self):
        self.selector.mode = "block"
        result = {}
        body = self.body()
        worker = threading.Thread(target=lambda: result.setdefault(
            "response", self.request(self.turn_path(), body, external=True, timeout=8)),
            daemon=True)
        worker.start()
        self.assertTrue(self.selector.started.wait(3), "provider request did not start")
        action = "call" if self.game["legal"].get("call") else "check"
        status, acted = self.request("/api/act", {
            "id": self.game["id"], "action": action, "expected_revision": 0,
            "coach_visible": False, "client_action_id": str(uuid.uuid4()),
        })
        self.assertEqual(status, 200, acted)
        self.selector.release.set()
        worker.join(5)
        self.assertFalse(worker.is_alive())
        status, stale = result["response"]
        self.assertEqual(status, 409)
        self.assertEqual(stale["code"], "stale_context")

    def test_live_and_saved_conversation_ledgers_are_independent(self):
        live = self.post_json(self.turn_path(), self.body())
        action = "call" if self.game["legal"].get("call") else "check"
        _, captured = self.request("/api/act", {
            "id": self.game["id"], "action": action, "expected_revision": 0,
            "coach_visible": False, "client_action_id": str(uuid.uuid4()),
        })
        decision = captured.get("decision")
        if not decision:
            self.skipTest("This seed did not record a hero decision.")
        analysis = json.load(urlopen(
            self.root + f"/api/v1/decisions/{decision['decision_id']}/analysis"))["analysis"]
        saved_target = {**analysis["ref"], "evidence_id": analysis["evidence_id"]}
        status, error = self.request("/api/v1/coach/turns", {
            "client_turn_id": str(uuid.uuid4()), "conversation_id": live["conversation_id"],
            "target": saved_target, "question": "Saved decision follow-up",
            "detail": "normal", "audience": "standard",
        })
        self.assertEqual(status, 410)
        self.assertEqual(error["code"], "conversation_expired")


if __name__ == "__main__":
    unittest.main()
