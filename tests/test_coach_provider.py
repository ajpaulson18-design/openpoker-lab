"""OpenAI Responses adapter tests without live credentials or network access."""
from io import BytesIO
import json
import socket
import unittest
from urllib.error import HTTPError, URLError
from unittest.mock import patch

from pokerlab.coach_analysis import adapt_practice_analysis
from pokerlab.coach_grounding import CoachReplyPlan, build_grounding_bundle
from pokerlab.coach_provider import CoachProviderError, OpenAIPlanSelector
from pokerlab.contracts import CoachDecisionRef
from pokerlab.game import Game
from pokerlab.practice import analyze_decision


def sample_bundle():
    game = Game([30, 30], seed=71)
    analysis = adapt_practice_analysis(
        analyze_decision(game),
        ref=CoachDecisionRef("provider-test-hand", "provider-test-decision", len(game.log)))
    legal = next(item for item in analysis.legal_actions if item.name == "call")
    values = {item.action_id: item.value for item in analysis.action_evs}
    choice = {"name": "call", "amount": legal.amount,
              "amount_semantics": "chips_added", "assessed_modeled_action_id": "call",
              "assessment_status": "assessed",
              "ev_loss": max(0.0, values[analysis.recommended_action_id] - values["call"])}
    return build_grounding_bundle(analysis, choice)


def api_response(text=None, *, status="completed", content_type="output_text"):
    content = []
    if text is not None:
        content.append({"type": content_type, "text": text})
    return {"status": status, "output": [{"type": "message", "content": content}]}


class CoachProviderTests(unittest.TestCase):
    def setUp(self):
        self.bundle = sample_bundle()
        self.plan = CoachReplyPlan(self.bundle.binding, "recommendation", (), None,
                                   "normal", "standard")

    def test_request_is_strict_bounded_stateless_and_contains_only_allowlisted_inputs(self):
        selector = OpenAIPlanSelector("test-key-never-real", "test-enabled-model",
                                      timeout=1.25, max_output_tokens=80)
        response = BytesIO(json.dumps(api_response(self.plan.to_json())).encode())
        with patch("pokerlab.coach_provider.urlopen", return_value=response) as mocked:
            selected = selector.select_plan(self.bundle, "Why this saved estimate?",
                                             "normal", "standard")
        self.assertEqual(selected, self.plan)
        request, = mocked.call_args.args
        timeout = mocked.call_args.kwargs["timeout"]
        self.assertEqual(timeout, 1.25)
        self.assertEqual(request.get_header("Authorization"), "Bearer test-key-never-real")
        payload = json.loads(request.data)
        self.assertEqual(payload["store"], False)
        self.assertEqual(payload["tools"], [])
        self.assertEqual(payload["max_output_tokens"], 80)
        self.assertEqual(payload["text"]["format"]["type"], "json_schema")
        self.assertTrue(payload["text"]["format"]["strict"])
        schema = payload["text"]["format"]["schema"]
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(schema["properties"]["schema_version"]["enum"], [1])
        self.assertNotIn("const", json.dumps(schema))
        supplied = json.loads(payload["input"])
        self.assertEqual(supplied["question"], "Why this saved estimate?")
        self.assertEqual(supplied["grounding_bundle"], self.bundle.to_dict())
        serialized = json.dumps(supplied)
        for forbidden in ("raw_event", "opponent_hole_cards", "database_path", "api_key"):
            self.assertNotIn(forbidden, serialized)
        self.assertNotIn("store", supplied)

    def test_default_output_budget_uses_bounded_reasoning_model_headroom(self):
        selector = OpenAIPlanSelector("test-key", "test-model")
        self.assertEqual(selector.max_output_tokens, 1024)

    def test_prior_context_is_bounded_validated_metadata_and_optional_for_one_shot(self):
        selector = OpenAIPlanSelector("test-key", "test-model")
        prior = ({"question": "First question", "intent": "recommendation",
                  "target_action_id": "call", "detail": "normal", "audience": "standard"},
                 {"question": "Second question", "intent": "limits",
                  "target_action_id": None, "detail": "short", "audience": "beginner"})
        with patch("pokerlab.coach_provider.urlopen",
                   return_value=BytesIO(json.dumps(api_response(self.plan.to_json())).encode())) as mocked:
            selector.select_plan(self.bundle, "Follow up", "short", "beginner",
                                 prior_turns=prior)
        request, = mocked.call_args.args
        supplied = json.loads(json.loads(request.data)["input"])
        self.assertEqual(supplied["prior_turns"], list(prior))
        with patch("pokerlab.coach_provider.urlopen",
                   return_value=BytesIO(json.dumps(api_response(self.plan.to_json())).encode())) as mocked:
            selector.select_plan(self.bundle, "One shot", "normal", "standard")
        request, = mocked.call_args.args
        self.assertNotIn("prior_turns", json.loads(json.loads(request.data)["input"]))
        with self.assertRaises(ValueError):
            selector.select_plan(self.bundle, "Follow up", "short", "beginner",
                                 prior_turns=prior + prior[:1])

    def test_refusal_incomplete_invalid_plan_http_timeout_and_network_failures_are_typed(self):
        selector = OpenAIPlanSelector("test-key", "test-model", timeout=0.5)
        cases = (
            (api_response("No", content_type="refusal"), "refusal"),
            (api_response(status="incomplete"), "incomplete"),
            (api_response("not JSON"), "invalid_plan"),
            (HTTPError(OpenAIPlanSelector.endpoint, 503, "sensitive body", {}, BytesIO(b"private")),
             "http_error"),
            (TimeoutError("private timeout detail"), "timeout"),
            (URLError(socket.gaierror("private host detail")), "network_error"),
        )
        for effect, code in cases:
            with self.subTest(code=code):
                if isinstance(effect, dict):
                    mocked = patch("pokerlab.coach_provider.urlopen",
                                   return_value=BytesIO(json.dumps(effect).encode()))
                else:
                    mocked = patch("pokerlab.coach_provider.urlopen", side_effect=effect)
                with mocked:
                    with self.assertRaises(CoachProviderError) as caught:
                        selector.select_plan(self.bundle, "Question", "normal", "standard")
                self.assertEqual(caught.exception.code, code)
                self.assertNotIn("private", str(caught.exception))

    def test_response_must_have_one_completed_output_text(self):
        selector = OpenAIPlanSelector("test-key", "test-model")
        for payload in (api_response(None),
                        {"status": "completed", "output": [
                            {"type": "message", "content": [
                                {"type": "output_text", "text": self.plan.to_json()},
                                {"type": "output_text", "text": self.plan.to_json()}]}]}):
            with self.subTest(payload=payload):
                with patch("pokerlab.coach_provider.urlopen",
                           return_value=BytesIO(json.dumps(payload).encode())):
                    with self.assertRaises(CoachProviderError) as caught:
                        selector.select_plan(self.bundle, "Question", "normal", "standard")
                self.assertEqual(caught.exception.code, "invalid_response")


if __name__ == "__main__":
    unittest.main()
