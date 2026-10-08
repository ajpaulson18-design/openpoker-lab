"""HTTP boundary tests for the optional one-shot saved-decision coach."""
from dataclasses import replace
import json
from pathlib import Path
import shutil
import threading
import unittest
import uuid
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from pokerlab.coach_grounding import CoachReplyPlan
from pokerlab.coach_provider import CoachProviderError
from pokerlab.models import Store
from pokerlab.server import make_server


BASE = Path(__file__).resolve().parents[1] / "work" / "coach-request-tests"
BASE.mkdir(parents=True, exist_ok=True)


class FakeSelector:
    def __init__(self):
        self.calls = []
        self.mode = "valid"
        self.started = threading.Event()
        self.release = threading.Event()

    def select_plan(self, bundle, question, detail, audience):
        self.calls.append((bundle, question, detail, audience))
        self.started.set()
        if self.mode == "block":
            self.release.wait(3)
        if self.mode == "provider_error":
            raise CoachProviderError("timeout")
        if self.mode == "unexpected_error":
            raise RuntimeError("sensitive fake exception")
        if self.mode == "unknown_fact":
            return CoachReplyPlan(bundle.binding, "limits", ("f_" + "0" * 64,), None,
                                  detail, audience)
        if self.mode == "wrong_binding":
            binding = replace(bundle.binding, evidence_id="other-evidence")
            return CoachReplyPlan(binding, "recommendation", (), None, detail, audience)
        if self.mode == "invented_target":
            return CoachReplyPlan(bundle.binding, "compare", (), "raise:999", detail, audience)
        intent = "recommendation" if self.mode != "unavailable" else "unavailable"
        return CoachReplyPlan(bundle.binding, intent, (), None, detail, audience)


class CoachRequestTests(unittest.TestCase):
    def setUp(self):
        self.directory = BASE / f"run-{uuid.uuid4().hex}"
        self.directory.mkdir()
        self.database = self.directory / "coach.sqlite3"
        self.selector = FakeSelector()
        self.server = make_server(0, self.database, coach_selector=self.selector,
                                  coach_enabled=True, coach_timeout=0.25)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.root = f"http://127.0.0.1:{self.server.server_port}"
        self.game, self.decision = self.capture()

    def tearDown(self):
        self.selector.release.set()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        shutil.rmtree(self.directory, ignore_errors=True)

    def post_raw(self, path, payload, *, external=False, timeout=5):
        headers = {"Content-Type": "application/json"}
        if external:
            headers["X-OpenPoker-External-AI"] = "1"
        request = Request(self.root + path, json.dumps(payload).encode(), headers)
        return json.load(urlopen(request, timeout=timeout))

    def get(self, path):
        return json.load(urlopen(self.root + path))

    def failed_post(self, path, payload, *, external=False):
        with self.assertRaises(HTTPError) as caught:
            self.post_raw(path, payload, external=external)
        with caught.exception as response:
            return response.code, json.load(response)

    def capture(self):
        game = self.post_raw("/api/game", {"stacks": [100, 100],
                                            "names": ["Hero", "Villain"],
                                            "button": 0, "seed": 61})
        action = "call" if game["legal"].get("call") else "check"
        result = self.post_raw("/api/act", {"id": game["id"], "action": action,
                                            "coach_visible": False,
                                            "expected_revision": 0,
                                            "client_action_id": uuid.uuid4().hex})
        return game, result["decision"]

    def coach_path(self, decision_id=None):
        return f"/api/v1/decisions/{decision_id or self.decision['decision_id']}/coach"

    def body(self, **updates):
        result = {"evidence_id": self.decision["evidence_id"],
                  "question": "Why did the saved estimate prefer this action?",
                  "detail": "normal", "audience": "standard"}
        result.update(updates)
        return result

    def test_external_ai_is_off_per_request_and_uses_local_fallback_without_calling_provider(self):
        result = self.post_raw(self.coach_path(), self.body())
        self.assertEqual(result["status"], "fallback")
        self.assertEqual(result["source"], "local_fallback")
        self.assertEqual(result["fallback_reason"], "external_ai_not_selected")
        self.assertTrue(result["retryable"])
        self.assertEqual(self.selector.calls, [])
        self.assertEqual(result["source_label"], "Practice estimate")
        self.assertIsInstance(result["reply"]["caveats"], list)
        self.assertEqual(result["teaching_note"]["source_label"], "Practice estimate")
        self.assertEqual(result["teaching_note"]["binding"], result["binding"])

    def test_explicit_local_enablement_is_required_even_with_a_selector(self):
        disabled_selector = FakeSelector()
        disabled_db = self.directory / "disabled.sqlite3"
        server = make_server(0, disabled_db, coach_selector=disabled_selector,
                             coach_enabled=False)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        root = f"http://127.0.0.1:{server.server_port}"
        try:
            status = json.load(urlopen(root + "/api/health"))
            self.assertFalse(status["external_ai_coach_available"])
            disabled_game = json.load(urlopen(Request(root + "/api/game", json.dumps({
                "stacks": [100, 100], "names": ["Hero", "Villain"], "button": 0,
                "seed": 62}).encode(), {"Content-Type": "application/json"})))
            action = "call" if disabled_game["legal"].get("call") else "check"
            accepted = json.load(urlopen(Request(root + "/api/act", json.dumps({
                "id": disabled_game["id"], "action": action, "coach_visible": False,
                "expected_revision": 0, "client_action_id": uuid.uuid4().hex}).encode(),
                {"Content-Type": "application/json"})))
            decision = accepted["decision"]
            request = Request(root + f"/api/v1/decisions/{decision['decision_id']}/coach",
                              json.dumps({"evidence_id": decision["evidence_id"],
                                          "question": "Explain", "detail": "normal",
                                          "audience": "standard"}).encode(),
                              {"Content-Type": "application/json",
                               "X-OpenPoker-External-AI": "1"})
            result = json.load(urlopen(request))
            self.assertEqual(result["source"], "local_fallback")
            self.assertEqual(result["fallback_reason"], "external_ai_not_configured")
            self.assertIsNotNone(result["teaching_note"])
            self.assertEqual(disabled_selector.calls, [])
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_opted_in_request_uses_bound_bundle_and_returns_only_server_rendered_blocks(self):
        result = self.post_raw(self.coach_path(), self.body(question="Why?", detail="technical",
                                                            audience="beginner"), external=True)
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["source"], "openai")
        self.assertEqual(result["binding"]["evidence_id"], self.decision["evidence_id"])
        self.assertEqual(result["reply"]["intent"], "recommendation")
        self.assertEqual(result["teaching_note"]["binding"], result["reply"]["binding"])
        self.assertIn("supporting_fact_ids", result["teaching_note"])
        self.assertEqual(len(self.selector.calls), 1)
        bundle, question, detail, audience = self.selector.calls[0]
        self.assertEqual((question, detail, audience), ("Why?", "technical", "beginner"))
        self.assertEqual(bundle.binding.hand_id, self.game["id"])
        self.assertTrue(all(f.source_pointer.startswith(("/analysis", "/choice"))
                            for f in bundle.facts))
        encoded = json.dumps(result)
        for forbidden in ("opponent_hole_cards", "raw_event", "database_path", "api_key"):
            self.assertNotIn(forbidden, encoded)

    def test_strict_question_body_evidence_binding_legacy_missing_and_corrupt_records(self):
        status, payload = self.failed_post(self.coach_path(),
                                           self.body(unexpected="no"))
        self.assertEqual(status, 400)
        self.assertIn("invalid", payload["error"].lower())
        status, _ = self.failed_post(self.coach_path(), self.body(evidence_id="wrong"),
                                     external=True)
        self.assertEqual(status, 409)
        status, _ = self.failed_post(self.coach_path("unknown"), self.body(), external=True)
        self.assertEqual(status, 404)
        status, _ = self.failed_post(self.coach_path(), self.body(question=" " * 501),
                                     external=True)
        self.assertEqual(status, 400)
        status, _ = self.failed_post(self.coach_path(), self.body(question=""), external=True)
        self.assertEqual(status, 400)

        store = Store(self.database)
        legacy = store.save_decision("legacy-session", {"chosen_action": "call"})
        legacy_reply = self.post_raw(self.coach_path(legacy["decision_id"]), {
            "evidence_id": "old", "question": "Explain", "detail": "normal",
            "audience": "standard"})
        self.assertEqual(legacy_reply["status"], "unavailable")

        with store.connect() as db:
            db.execute("UPDATE coach_decision_evidence SET envelope=? WHERE decision_id=?",
                       ("not-json", self.decision["decision_id"]))
        status, payload = self.failed_post(self.coach_path(), self.body(), external=True)
        self.assertEqual(status, 500)
        self.assertEqual(payload, {"status": "failed",
                                   "error": "Stored decision evidence is invalid."})
        self.assertEqual(self.selector.calls, [])

    def test_invalid_provider_plans_refusal_and_network_errors_use_safe_fallback(self):
        for mode, code in (("unknown_fact", "invalid_plan"),
                           ("wrong_binding", "invalid_plan"),
                           ("invented_target", "invalid_plan"),
                           ("provider_error", "timeout"),
                           ("unexpected_error", "provider_error")):
            with self.subTest(mode=mode):
                self.selector.mode = mode
                result = self.post_raw(self.coach_path(), self.body(), external=True)
                self.assertEqual(result["status"], "fallback")
                self.assertEqual(result["source"], "local_fallback")
                self.assertEqual(result["fallback_reason"], code)
                self.assertTrue(result["retryable"])
                self.assertNotIn("sensitive fake exception", json.dumps(result))
        self.assertEqual(self.selector.mode, "unexpected_error")

    def test_coach_gate_is_separate_from_gameplay_admission(self):
        self.selector.mode = "block"
        first = {}

        def request_first():
            first["result"] = self.post_raw(self.coach_path(), self.body(), external=True,
                                             timeout=5)

        worker = threading.Thread(target=request_first)
        worker.start()
        self.assertTrue(self.selector.started.wait(2))
        status, payload = self.failed_post(self.coach_path(), self.body(), external=True)
        self.assertEqual(status, 429)
        self.assertIn("coach request", payload["error"].lower())
        next_game = self.post_raw("/api/game", {"stacks": [100, 100],
                                                "names": ["New Hero", "New Villain"],
                                                "button": 0, "seed": 62}, timeout=2)
        self.assertEqual(next_game["revision"], 0)
        self.selector.release.set()
        worker.join(5)
        self.assertFalse(worker.is_alive())
        self.assertEqual(first["result"]["status"], "ready")


if __name__ == "__main__":
    unittest.main()
