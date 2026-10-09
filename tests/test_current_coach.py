"""Tests for one evidence-bound question about an unplayed decision."""
import json
from pathlib import Path
import shutil
import threading
import unittest
import uuid
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch

from pokerlab.coach_analysis import adapt_practice_analysis
from pokerlab.coach_grounding import (
    CoachGroundingError, CoachReplyPlan, build_current_preview_grounding_bundle,
    build_grounding_bundle, render_coach_reply, validate_current_coach_reply_plan,
)
from pokerlab.coach_provider import CoachProviderError
from pokerlab.contracts import CoachDecisionRef
from pokerlab.game import Game
from pokerlab.practice import analyze_decision
from pokerlab.server import make_server


BASE = Path(__file__).resolve().parents[1] / "work" / "current-coach-tests"
BASE.mkdir(parents=True, exist_ok=True)


class FakeSelector:
    def __init__(self):
        self.calls = []
        self.mode = "valid"
        self.started = threading.Event()
        self.release = threading.Event()

    def select_plan(self, bundle, question, detail, audience, *, prior_turns=(), current_preview=False):
        self.calls.append((bundle, question, detail, audience, tuple(prior_turns), current_preview))
        self.started.set()
        if self.mode == "block":
            self.release.wait(4)
        if self.mode == "provider_error":
            raise CoachProviderError("timeout")
        if self.mode == "choice":
            intent, target = "choice", None
        elif self.mode == "compare":
            intent = "compare"
            target = next(f.value[0] for f in bundle.facts if f.kind == "modeled_action")
        elif self.mode == "limits":
            intent, target = "limits", None
        elif self.mode == "unavailable":
            intent, target = "unavailable", None
        else:
            intent, target = "recommendation", None
        return CoachReplyPlan(bundle.binding, intent, (), target, detail, audience)


class CurrentCoachHTTPTests(unittest.TestCase):
    def setUp(self):
        self.directory = BASE / f"run-{uuid.uuid4().hex}"
        self.directory.mkdir()
        self.selector = FakeSelector()
        self.server = make_server(0, self.directory / "coach.sqlite3",
                                  coach_selector=self.selector, coach_enabled=True,
                                  coach_timeout=0.25)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.root = f"http://127.0.0.1:{self.server.server_port}"
        self.game = self.post("/api/game", {
            "stacks": [100, 100], "names": ["Hero", "Private Villain"], "seed": 91,
        })
        self.preview = self.post(self.preview_path(), {
            "expected_revision": self.game["revision"], "opponent_id": None,
        })

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

    def post(self, path, payload, *, external=False):
        status, result = self.request(path, payload, external=external)
        self.assertEqual(status, 200, result)
        return result

    def preview_path(self, hand_id=None):
        return f"/api/v1/hands/{hand_id or self.game['id']}/current-study"

    def current_path(self, hand_id=None):
        return f"/api/v1/hands/{hand_id or self.game['id']}/current-coach"

    def current_body(self, **updates):
        body = {
            "target": self.preview["binding"],
            "question": "What does the current estimate say about the modeled actions?",
            "detail": "normal", "audience": "standard",
        }
        body.update(updates)
        return body

    def test_opt_in_preview_answer_is_bound_and_contains_no_choice_or_loss(self):
        result = self.post(self.current_path(), self.current_body(question="Why this estimate?"),
                           external=True)
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["source"], "openai")
        self.assertEqual(result["binding"], self.preview["binding"])
        self.assertEqual(result["reply"]["intent"], "recommendation")
        self.assertEqual(result["reply"]["source_label"], "Practice estimate · current decision preview")
        self.assertIn("choice", result["reply"]["unavailable_fields"])
        self.assertIn("choice_loss", result["reply"]["unavailable_fields"])
        fact_kinds = {fact["kind"] for block in result["reply"]["blocks"]
                      for fact in block["facts"]}
        self.assertNotIn("choice", fact_kinds)
        self.assertNotIn("choice_loss", fact_kinds)
        self.assertNotIn("Private Villain", json.dumps(result))
        self.assertEqual(len(self.selector.calls), 1)
        bundle, question, detail, audience, prior_turns, current_preview = self.selector.calls[0]
        self.assertEqual((question, detail, audience, prior_turns, current_preview),
                         ("Why this estimate?", "normal", "standard", (), True))
        self.assertFalse(any(fact.kind in {"choice", "choice_loss"} for fact in bundle.facts))

    def test_local_fallback_summarizes_current_recommendation_without_calling_provider(self):
        result = self.post(self.current_path(), self.current_body())
        self.assertEqual(result["status"], "fallback")
        self.assertEqual(result["fallback_reason"], "external_ai_not_selected")
        self.assertEqual(result["reply"]["intent"], "recommendation")
        self.assertEqual(result["source_label"], "Practice estimate · current decision preview")
        self.assertIn("local summary", result["local_scope"])
        self.assertIn("not an interpretation of arbitrary question wording", result["local_scope"])
        self.assertIn("current recommendation", result["teaching_note"]["text"])
        self.assertIn("current preview's EV basis", result["teaching_note"]["text"])
        fact_kinds = {fact["kind"] for block in result["reply"]["blocks"]
                      for fact in block["facts"]}
        self.assertIn("recommendation", fact_kinds)
        self.assertNotIn("choice", fact_kinds)
        self.assertNotIn("choice_loss", fact_kinds)
        self.assertEqual(self.selector.calls, [])

    def test_beginner_starter_questions_have_grounded_local_answers(self):
        prompts = (
            ("What is the current modeled recommendation?", "recommendation"),
            ("What assumptions limit this estimate?", "limits"),
        )
        for question, expected_intent in prompts:
            with self.subTest(question=question):
                result = self.post(self.current_path(), self.current_body(question=question))
                self.assertEqual(result["status"], "fallback")
                self.assertEqual(result["fallback_reason"], "external_ai_not_selected")
                self.assertEqual(result["reply"]["intent"], expected_intent)
                self.assertIn("current decision preview", result["reply"]["source_label"].lower())
                self.assertNotIn("choice", {
                    fact["kind"] for block in result["reply"]["blocks"]
                    for fact in block["facts"]
                })
        limits = self.post(self.current_path(), self.current_body(
            question="What assumptions limit this estimate?"))
        limit_facts = {fact["kind"] for block in limits["reply"]["blocks"]
                       for fact in block["facts"]}
        self.assertIn("source_kind", limit_facts)
        self.assertTrue(limit_facts.intersection({"confidence_label", "opponent_uncertainty",
                                                  "equity_standard_error", "equity_exact",
                                                  "opponent_assumption"}))
        self.assertIn("validated assumptions and limits", limits["local_scope"])
        self.assertEqual(self.selector.calls, [])

    def test_choice_and_loss_questions_stay_unavailable_without_provider_call(self):
        for question in ("What did I choose and how much did I lose?",
                         "Was my recorded action a mistake?", "Was my call wrong?",
                         "Did I make a bad call?"):
            with self.subTest(question=question):
                result = self.post(self.current_path(), self.current_body(question=question),
                                   external=True)
                self.assertEqual(result["status"], "fallback")
                self.assertEqual(result["fallback_reason"], "current_choice_unavailable")
                self.assertEqual(result["reply"]["intent"], "unavailable")
                self.assertIn("choice", result["reply"]["unavailable_fields"])
                self.assertIn("choice_loss", result["reply"]["unavailable_fields"])
                self.assertIn("No action has been taken", result["local_scope"])
                self.assertIn("No action has been taken", result["teaching_note"]["text"])
                fact_kinds = {fact["kind"] for block in result["reply"]["blocks"]
                              for fact in block["facts"]}
                self.assertNotIn("choice", fact_kinds)
                self.assertNotIn("choice_loss", fact_kinds)
        self.assertEqual(self.selector.calls, [])

    def test_ambiguous_local_questions_fail_closed_instead_of_guessing_recommendation(self):
        for question in ("Explain this preview.", "Why is this estimate interesting?"):
            with self.subTest(question=question):
                result = self.post(self.current_path(), self.current_body(question=question))
                self.assertEqual(result["reply"]["intent"], "unavailable")
                self.assertIn("cannot interpret that question", result["local_scope"])
                self.assertIn("Ask about the current modeled recommendation", result["local_scope"])
                self.assertEqual(self.selector.calls, [])

    def test_disabled_provider_and_provider_failure_use_local_fallback(self):
        disabled_selector = FakeSelector()
        disabled = make_server(0, self.directory / "disabled.sqlite3",
                               coach_selector=disabled_selector, coach_enabled=False)
        thread = threading.Thread(target=disabled.serve_forever, daemon=True)
        thread.start()
        root = f"http://127.0.0.1:{disabled.server_port}"
        try:
            def disabled_post(path, payload):
                request = Request(root + path, json.dumps(payload).encode(), {
                    "Content-Type": "application/json",
                    "X-OpenPoker-External-AI": "1",
                })
                return json.load(urlopen(request, timeout=6))
            game = disabled_post("/api/game", {
                "stacks": [100, 100], "names": ["Hero", "Villain"], "seed": 92,
            })
            preview = disabled_post(f"/api/v1/hands/{game['id']}/current-study", {
                "expected_revision": 0, "opponent_id": None,
            })
            result = disabled_post(f"/api/v1/hands/{game['id']}/current-coach", {
                "target": preview["binding"], "question": "Explain this preview.",
                "detail": "normal", "audience": "standard",
            })
            self.assertEqual(result["fallback_reason"], "external_ai_not_configured")
            self.assertEqual(result["reply"]["intent"], "unavailable")
            self.assertIn("cannot interpret that question", result["local_scope"])
            self.assertEqual(disabled_selector.calls, [])
        finally:
            disabled.shutdown()
            disabled.server_close()
            thread.join()

        self.selector.mode = "provider_error"
        failed = self.post(self.current_path(), self.current_body(), external=True)
        self.assertEqual(failed["status"], "fallback")
        self.assertEqual(failed["fallback_reason"], "timeout")
        self.assertEqual(failed["reply"]["intent"], "recommendation")
        self.assertIn("local summary", failed["local_scope"])

    def test_limits_and_unavailable_are_supported_live_safe_intents(self):
        for mode in ("limits", "unavailable"):
            with self.subTest(mode=mode):
                self.selector.mode = mode
                result = self.post(self.current_path(), self.current_body(), external=True)
                self.assertEqual(result["status"], "ready")
                self.assertEqual(result["reply"]["intent"], mode)

    def test_choice_and_comparison_plans_are_rejected_for_live_preview(self):
        for mode in ("choice", "compare"):
            with self.subTest(mode=mode):
                self.selector.mode = mode
                result = self.post(self.current_path(), self.current_body(), external=True)
                self.assertEqual(result["status"], "fallback")
                self.assertEqual(result["fallback_reason"], "invalid_plan")
                self.assertEqual(result["reply"]["intent"], "recommendation")
                self.assertIn("local summary", result["local_scope"])

    def test_missing_expired_wrong_and_malformed_targets_have_controlled_results(self):
        self.assertEqual(self.request(self.current_path("unknown"), self.current_body(
            target={**self.preview["binding"], "hand_id": "unknown"}))[0], 404)
        status, expired = self.request(self.current_path(), self.current_body(
            target={**self.preview["binding"], "decision_id": "not-retained"}))
        self.assertEqual(status, 409)
        self.assertEqual(expired["code"], "preview_expired")
        self.assertTrue(expired["refresh_required"])
        self.assertEqual(self.request(self.current_path(), self.current_body(
            target={**self.preview["binding"], "hand_id": "other-hand"}))[0], 400)
        self.assertEqual(self.request(self.current_path(), self.current_body(
            extra="not-allowed"))[0], 400)
        self.assertEqual(self.request(self.current_path(), self.current_body(
            question=" " * 501))[0], 400)

    def test_current_route_never_recalculates_and_rejects_a_stale_revision(self):
        with patch("pokerlab.server.analyze_decision") as calculate:
            result = self.post(self.current_path(), self.current_body())
            self.assertEqual(result["status"], "fallback")
            calculate.assert_not_called()
        action = "call" if self.game["legal"].get("call") else "check"
        self.post("/api/act", {"id": self.game["id"], "action": action,
                                "expected_revision": 0, "coach_visible": False})
        status, stale = self.request(self.current_path(), self.current_body(), external=True)
        self.assertEqual(status, 409)
        self.assertEqual(stale["code"], "stale_context")
        self.assertEqual(stale["status"], "stale_context")

    def test_provider_wait_does_not_block_action_and_returns_stale_context(self):
        self.selector.mode = "block"
        result = {}
        worker = threading.Thread(target=lambda: result.setdefault(
            "response", self.request(self.current_path(), self.current_body(), external=True)),
            daemon=True)
        worker.start()
        self.assertTrue(self.selector.started.wait(3), "provider request did not start")
        action = "call" if self.game["legal"].get("call") else "check"
        status, accepted = self.request("/api/act", {
            "id": self.game["id"], "action": action,
            "expected_revision": 0, "coach_visible": False,
        })
        self.assertEqual(status, 200, accepted)
        decision = accepted.get("decision")
        if decision:
            coach_path = f"/api/v1/decisions/{decision['decision_id']}/coach"
            status, busy = self.request(coach_path, {
                "evidence_id": decision["evidence_id"], "question": "Explain this decision.",
                "detail": "normal", "audience": "standard",
            }, external=True)
            self.assertEqual(status, 429)
            self.assertIn("already running", busy["error"])
        self.selector.release.set()
        worker.join(5)
        self.assertFalse(worker.is_alive())
        status, stale = result["response"]
        self.assertEqual(status, 409)
        self.assertEqual(stale["code"], "stale_context")


class CurrentCoachGroundingTests(unittest.TestCase):
    def analysis(self):
        game = Game([50, 50], seed=81)
        raw = analyze_decision(game)
        return adapt_practice_analysis(
            raw, ref=CoachDecisionRef("live-hand", uuid.uuid4().hex, 0))

    def test_choice_free_bundle_marks_action_and_loss_unavailable_without_choice_facts(self):
        analysis = self.analysis()
        bundle = build_current_preview_grounding_bundle(analysis)
        self.assertEqual(bundle.binding.hand_id, "live-hand")
        self.assertIn("choice", bundle.unavailable_fields)
        self.assertIn("choice_loss", bundle.unavailable_fields)
        self.assertFalse(any(fact.kind in {"choice", "choice_loss"} for fact in bundle.facts))

    def test_current_renderer_rejects_choice_and_compare_but_saved_renderer_stays_available(self):
        analysis = self.analysis()
        bundle = build_current_preview_grounding_bundle(analysis)
        modeled = analysis.modeled_actions[0]
        for plan in (
            CoachReplyPlan(bundle.binding, "choice", (), None, "normal", "standard"),
            CoachReplyPlan(bundle.binding, "compare", (), modeled.action_id, "normal", "standard"),
        ):
            with self.subTest(intent=plan.intent), self.assertRaises(CoachGroundingError):
                validate_current_coach_reply_plan(plan, bundle)
        recommendation = CoachReplyPlan(bundle.binding, "recommendation", (), None,
                                        "normal", "standard")
        rendered = render_coach_reply(bundle, recommendation, current_preview=True)
        self.assertIn("current decision preview", rendered.source_label)
        self.assertIn("Current modeled", rendered.blocks[0].label)

        values = {item.action_id: item.value for item in analysis.action_evs}
        loss = max(0.0, values[analysis.recommended_action_id] - values[modeled.action_id])
        choice = {
            "name": modeled.name, "amount": modeled.amount,
            "amount_semantics": modeled.amount_semantics,
            "assessed_modeled_action_id": modeled.action_id,
            "assessment_status": "assessed", "ev_loss": loss,
        }
        saved_bundle = build_grounding_bundle(analysis, choice)
        saved_plan = CoachReplyPlan(saved_bundle.binding, "choice", (), None,
                                    "normal", "standard")
        saved = render_coach_reply(saved_bundle, saved_plan)
        self.assertEqual(saved.blocks[0].label, "Recorded choice")
