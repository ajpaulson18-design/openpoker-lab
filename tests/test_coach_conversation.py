"""HTTP tests for bounded same-decision coach follow-ups."""
import json
from pathlib import Path
import shutil
import threading
import unittest
import uuid
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from tests.test_coach_request import FakeSelector
from pokerlab.server import make_server


BASE = Path(__file__).resolve().parents[1] / "work" / "coach-conversation-tests"
BASE.mkdir(parents=True, exist_ok=True)


class CoachConversationTests(unittest.TestCase):
    def setUp(self):
        self.directory = BASE / f"run-{uuid.uuid4().hex}"
        self.directory.mkdir()
        self.clock = [100.0]
        self.selector = FakeSelector()
        self.server = make_server(0, self.directory / "coach.sqlite3",
                                  coach_selector=self.selector, coach_enabled=True,
                                  coach_clock=lambda: self.clock[0])
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.root = f"http://127.0.0.1:{self.server.server_port}"
        self.game, self.decision = self.capture()
        analysis = self.get(f"/api/v1/decisions/{self.decision['decision_id']}/analysis")["analysis"]
        self.target = {**analysis["ref"], "evidence_id": analysis["evidence_id"]}

    def tearDown(self):
        self.selector.release.set()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        shutil.rmtree(self.directory, ignore_errors=True)

    def post(self, payload, *, external=False, timeout=5):
        headers = {"Content-Type": "application/json"}
        if external:
            headers["X-OpenPoker-External-AI"] = "1"
        request = Request(self.root + "/api/v1/coach/turns",
                          json.dumps(payload).encode(), headers)
        return json.load(urlopen(request, timeout=timeout))

    def post_error(self, payload, *, external=False):
        with self.assertRaises(HTTPError) as caught:
            self.post(payload, external=external)
        with caught.exception as response:
            return response.code, json.load(response)

    def get(self, path):
        return json.load(urlopen(self.root + path))

    def capture(self):
        game = self.post_game({"stacks": [100, 100], "names": ["Hero", "Villain"],
                               "button": 0, "seed": 71})
        action = "call" if game["legal"].get("call") else "check"
        request = Request(self.root + "/api/act", json.dumps({
            "id": game["id"], "action": action, "coach_visible": False,
            "expected_revision": 0, "client_action_id": uuid.uuid4().hex,
        }).encode(), {"Content-Type": "application/json"})
        result = json.load(urlopen(request))
        return game, result["decision"]

    def post_game(self, payload):
        request = Request(self.root + "/api/game", json.dumps(payload).encode(),
                          {"Content-Type": "application/json"})
        return json.load(urlopen(request))

    def body(self, *, client_turn_id=None, conversation_id=None, **updates):
        payload = {
            "client_turn_id": client_turn_id or uuid.uuid4().hex,
            "target": dict(self.target),
            "question": "Why did the saved estimate prefer this action?",
            "detail": "normal", "audience": "standard",
        }
        if conversation_id is not None:
            payload["conversation_id"] = conversation_id
        payload.update(updates)
        return payload

    def test_same_decision_turns_include_only_bounded_prior_questions_and_keep_binding(self):
        first = self.post(self.body(), external=False)
        self.assertEqual(first["status"], "fallback")
        self.assertEqual(first["binding"], self.target)
        self.assertTrue(first["conversation_id"])
        second_body = self.body(conversation_id=first["conversation_id"],
                                question="Can you explain that more simply?",
                                detail="short", audience="beginner")
        second = self.post(second_body, external=True)
        self.assertEqual(second["status"], "ready")
        self.assertEqual(second["binding"], self.target)
        self.assertEqual(second["client_turn_id"], second_body["client_turn_id"])
        self.assertEqual(len(self.selector.calls), 1)
        self.assertEqual(self.selector.calls[0][1:], (
            "Can you explain that more simply?", "short", "beginner",
            ({"question": "Why did the saved estimate prefer this action?",
              "intent": first["reply"]["intent"],
              "target_action_id": first["reply"].get("target_action_id"),
              "detail": "normal", "audience": "standard"},)))
        third_body = self.body(conversation_id=first["conversation_id"],
                               question="What should I study next?", detail="technical")
        third = self.post(third_body, external=True)
        self.assertEqual(third["binding"], first["binding"])
        self.assertEqual(len(self.selector.calls[1][4]), 2)
        self.assertEqual(self.selector.calls[1][4][0]["question"],
                         "Why did the saved estimate prefer this action?")
        self.assertEqual(self.selector.calls[1][4][1]["question"],
                         "Can you explain that more simply?")

    def test_idempotent_retry_includes_external_opt_in_and_conflicts_are_explicit(self):
        payload = self.body()
        first = self.post(payload, external=True)
        replay = self.post({**payload, "conversation_id": first["conversation_id"]}, external=True)
        self.assertEqual(replay, first)
        self.assertEqual(len(self.selector.calls), 1)

    def test_lost_first_response_can_retry_without_conversation_id(self):
        payload = self.body()
        first = self.post(payload, external=True)
        replay = self.post(payload, external=True)
        self.assertEqual(replay, first)
        self.assertEqual(len(self.selector.calls), 1)
        status, conflict = self.post_error(
            {**payload, "conversation_id": first["conversation_id"]}, external=False)
        self.assertEqual(status, 409)
        self.assertEqual(conflict["code"], "turn_id_conflict")
        status, conflict = self.post_error(self.body(
            client_turn_id=payload["client_turn_id"],
            conversation_id=first["conversation_id"], question="Different question"), external=True)
        self.assertEqual(status, 409)
        self.assertEqual(conflict["code"], "turn_id_conflict")
        self.assertEqual(len(self.selector.calls), 1)

    def test_target_reuse_and_unknown_or_expired_conversation_are_rejected(self):
        first = self.post(self.body())
        for field in ("hand_id", "evidence_id", "state_revision"):
            with self.subTest(field=field):
                stale_target = dict(self.target)
                stale_target[field] = (stale_target[field] + 1 if field == "state_revision"
                                       else "other-" + stale_target[field])
                status, conflict = self.post_error(self.body(
                    conversation_id=first["conversation_id"], target=stale_target))
                self.assertEqual(status, 409)
                self.assertEqual(conflict["code"], "binding_mismatch")
        _, second_decision = self.capture()
        second_analysis = self.get(
            f"/api/v1/decisions/{second_decision['decision_id']}/analysis")["analysis"]
        second_target = {**second_analysis["ref"], "evidence_id": second_analysis["evidence_id"]}
        status, conflict = self.post_error(self.body(
            conversation_id=first["conversation_id"], target=second_target,
            question="Use a different decision"))
        self.assertEqual(status, 409)
        self.assertEqual(conflict["code"], "binding_mismatch")
        status, expired = self.post_error(self.body(conversation_id="unknown-conversation"))
        self.assertEqual(status, 410)
        self.assertEqual(expired["code"], "conversation_expired")
        self.clock[0] += 30 * 60
        status, expired = self.post_error(self.body(conversation_id=first["conversation_id"]))
        self.assertEqual(status, 410)
        self.assertEqual(expired["code"], "conversation_expired")

    def test_external_opt_in_with_disabled_provider_uses_local_fallback(self):
        selector = FakeSelector()
        server = make_server(0, self.directory / "coach.sqlite3", coach_selector=selector,
                             coach_enabled=False)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        root = f"http://127.0.0.1:{server.server_port}"
        try:
            payload = self.body(question="Explain with the provider disabled")
            request = Request(root + "/api/v1/coach/turns", json.dumps(payload).encode(), {
                "Content-Type": "application/json", "X-OpenPoker-External-AI": "1"})
            result = json.load(urlopen(request))
            self.assertEqual(result["source"], "local_fallback")
            self.assertEqual(result["fallback_reason"], "external_ai_not_configured")
            self.assertEqual(selector.calls, [])
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_four_turn_cap_and_explicit_new_conversation(self):
        first = self.post(self.body())
        conversation_id = first["conversation_id"]
        for index in range(1, 4):
            result = self.post(self.body(conversation_id=conversation_id,
                                         question=f"Follow-up {index}"))
            self.assertEqual(result["conversation_id"], conversation_id)
        status, full = self.post_error(self.body(conversation_id=conversation_id,
                                                question="Fifth question"))
        self.assertEqual(status, 409)
        self.assertEqual(full["code"], "conversation_full")
        new = self.post(self.body(question="Start a fresh thread"))
        self.assertNotEqual(new["conversation_id"], conversation_id)

    def test_same_conversation_concurrent_turn_is_rejected_and_reservation_releases(self):
        first = self.post(self.body())
        self.selector.mode = "block"
        second_body = self.body(conversation_id=first["conversation_id"], question="Go deeper")
        response = {}

        def ask():
            response["result"] = self.post(second_body, external=True, timeout=5)

        worker = threading.Thread(target=ask)
        worker.start()
        self.assertTrue(self.selector.started.wait(2))
        next_game = self.post_game({"stacks": [100, 100], "names": ["New Hero", "New Villain"],
                                    "button": 0, "seed": 72})
        self.assertEqual(next_game["revision"], 0)
        status, conflict = self.post_error(self.body(
            conversation_id=first["conversation_id"], question="Another question"))
        self.assertEqual(status, 409)
        self.assertEqual(conflict["code"], "turn_in_progress")
        self.selector.release.set()
        worker.join(5)
        self.assertFalse(worker.is_alive())
        self.assertEqual(response["result"]["status"], "ready")
        self.selector.mode = "valid"
        follow = self.post(self.body(conversation_id=first["conversation_id"],
                                     question="Try after completion"))
        self.assertEqual(follow["status"], "fallback")

    def test_provider_failure_is_cached_as_local_fallback(self):
        self.selector.mode = "provider_error"
        payload = self.body()
        first = self.post(payload, external=True)
        replay = self.post({**payload, "conversation_id": first["conversation_id"]}, external=True)
        self.assertEqual(first["status"], "fallback")
        self.assertEqual(first["fallback_reason"], "timeout")
        self.assertEqual(replay, first)
        self.assertEqual(len(self.selector.calls), 1)

    def test_questions_are_not_written_to_sqlite_or_exports(self):
        question = "private follow-up question 91a27"
        self.post(self.body(question=question))
        self.assertNotIn(question, json.dumps(self.get("/api/export")))
        self.assertNotIn(question.encode(), (self.directory / "coach.sqlite3").read_bytes())


if __name__ == "__main__":
    unittest.main()
