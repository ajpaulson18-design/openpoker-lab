import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from pokerlab.contracts import (ActionFrequency, ActionValue,
                                OpponentAssumption, StrategyAnalysisResult,
                                TendencyContext, Uncertainty)
from pokerlab.explanations import (DecisionExplanation, ExplanationLevel,
                                   analysis_from_dict, explain)
from pokerlab.models import Store
from pokerlab.server import make_server


class ExplanationTests(unittest.TestCase):
    def setUp(self):
        context = TendencyContext("river", "button", "facing_bet",
                                  (("size", "half-pot"),))
        uncertainty = Uncertainty(.30, .55, .95, "beta interval", "moderate")
        assumption = OpponentAssumption("fold_to_bet", context, .4125, 30,
                                        uncertainty)
        self.analysis = StrategyAnalysisResult(
            "analysis-example", ("check", "bet"),
            (ActionFrequency("check", .6), ActionFrequency("bet", .4)),
            (ActionFrequency("check", .3), ActionFrequency("bet", .7)),
            (ActionValue("check", 48), ActionValue("bet", 55)),
            (ActionValue("check", 0), ActionValue("bet", 7)),
            (assumption,), "moderate", uncertainty, "example-solver-v1",
            "beta-opportunity-v1", ("Heads-up only.",),
            ("Range uncertainty is additional.",))

    def test_recommendation_is_copied_not_recalculated(self):
        result = explain(self.analysis, "check", "short")
        self.assertEqual(result.recommended_action, "check")
        self.assertEqual(result.facts.recommended_action, "check")
        self.assertEqual(result.facts.analysis_id, self.analysis.analysis_id)
        self.assertGreater(dict((x.action, x.value) for x in result.action_evs)["bet"],
                           dict((x.action, x.value) for x in result.action_evs)["check"])

    def test_ev_numbers_exactly_match_analysis(self):
        result = explain(self.analysis, "bet")
        self.assertEqual(result.action_evs, self.analysis.action_evs)
        self.assertEqual(result.ev_differences, self.analysis.ev_differences)
        self.assertEqual(result.alternative_actions[0].ev, 48)
        self.assertEqual(result.alternative_actions[0].ev_difference, 0)

    def test_evidence_counts_match_opponent_assumptions(self):
        result = explain(self.analysis, "bet")
        self.assertEqual(result.evidence[0].evidence_count,
                         self.analysis.opponent_assumptions[0].evidence_count)
        self.assertEqual(result.evidence[0].value,
                         self.analysis.opponent_assumptions[0].value)

    def test_low_confidence_language_is_cautious(self):
        low = StrategyAnalysisResult(
            self.analysis.analysis_id, self.analysis.legal_actions,
            self.analysis.baseline_strategy, self.analysis.exploitative_strategy,
            self.analysis.action_evs, self.analysis.ev_differences,
            self.analysis.opponent_assumptions, "low", self.analysis.uncertainty,
            self.analysis.solver_version, self.analysis.model_version)
        result = explain(low, "bet")
        self.assertIn("tentative", result.plain_language_reason)
        self.assertNotIn("certain", result.plain_language_reason.casefold())

    def test_baseline_and_exploit_remain_distinct(self):
        result = explain(self.analysis, "bet")
        self.assertNotEqual(result.baseline_strategy, result.exploitative_strategy)
        self.assertEqual(result.exploitative_adjustment.baseline_frequency, .4)
        self.assertEqual(result.exploitative_adjustment.exploitative_frequency, .7)

    def test_beginner_mode_expands_technical_concepts(self):
        result = explain(self.analysis, "bet", ExplanationLevel.BEGINNER)
        terms = {item.term for item in result.glossary}
        self.assertTrue({"expected value", "range", "pot odds", "action frequency",
                         "bluff-catching", "value betting", "opponent tendency",
                         "uncertainty"}.issubset(terms))
        self.assertIn("Expected value means", result.summary)

    def test_serialization_round_trip(self):
        result = explain(self.analysis, "bet", "beginner")
        decoded = DecisionExplanation.from_json(result.to_json())
        self.assertEqual(decoded, result)
        self.assertEqual(json.loads(result.to_json())["analysis_id"],
                         self.analysis.analysis_id)
        self.assertEqual(analysis_from_dict(self.analysis.to_dict()), self.analysis)

    def test_server_serializes_explanation_payload(self):
        with tempfile.TemporaryDirectory() as directory:
            server = make_server(0, Path(directory) / "db.sqlite3")
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                body = json.dumps({"analysis": self.analysis.to_dict(),
                                   "recommended_action": "bet",
                                   "level": "short"}).encode()
                request = Request(
                    f"http://127.0.0.1:{server.server_port}/api/explain", body,
                    {"Content-Type": "application/json"})
                decoded = json.load(urlopen(request))
                self.assertEqual(decoded["analysis_id"], self.analysis.analysis_id)
                self.assertEqual(decoded["recommended_action"], "bet")
                self.assertEqual(decoded["level"], "short")
            finally:
                server.shutdown()
                server.server_close()
                thread.join()

    def test_identical_inputs_produce_identical_facts(self):
        first = explain(self.analysis, "bet", "normal")
        second = explain(self.analysis, "bet", "normal")
        self.assertEqual(first, second)
        self.assertEqual(first.to_json(), second.to_json())

    def test_no_unsupported_opponent_psychology(self):
        encoded = explain(self.analysis, "bet", "beginner").to_json().casefold()
        for unsupported in ("scared", "angry", "tilted", "nervous", "afraid"):
            self.assertNotIn(unsupported, encoded)
        self.assertIn("30 recorded opportunities", encoded)

    def test_missing_optional_data_degrades_gracefully(self):
        sparse = StrategyAnalysisResult(
            "analysis-sparse", ("fold", "call"),
            (ActionFrequency("fold", .5), ActionFrequency("call", .5)),
            (ActionFrequency("fold", .5), ActionFrequency("call", .5)),
            (ActionValue("fold", 0), ActionValue("call", 0)),
            (ActionValue("fold", 0), ActionValue("call", 0)), (),
            "not available", None, "solver-v1", "model-v1")
        result = explain(sparse, "fold")
        self.assertEqual(result.evidence, ())
        self.assertIsNone(result.uncertainty)
        self.assertIn("No opponent-specific tendency", result.plain_language_reason)
        self.assertIn("no tendency-based cause", result.caveats[-1])


class RiverExplanationBrowserFlowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.database = Path(self.temp.name) / "river-explanation.sqlite3"
        store = Store(self.database)
        opponent = store.add_opponent("Synthetic river profile", "balanced")
        store.record_observation(
            opponent["id"], "fold_to_bet", 95, 100,
            TendencyContext("river", action_context="facing_bet"),
            observation_id="synthetic-river-folds")
        self.opponent_id = opponent["id"]
        self.server = make_server(0, self.database)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.root = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def post(self, path, data):
        request = Request(self.root + path, json.dumps(data).encode(),
                          {"Content-Type": "application/json"})
        return json.load(urlopen(request))

    def river_request(self):
        return {
            "board": "2c3d7h8sJc", "oop_range": "AsAh,6s6h",
            "ip_range": "KsKh,QsQh", "hero_hand": "6s6h",
            "opponent_id": self.opponent_id, "pot": 100, "bet": 50,
            "iterations": 100, "decision": "root",
        }

    def test_browser_explanation_replays_and_renders_backend_analysis(self):
        html = urlopen(self.root + "/").read().decode()
        script = urlopen(self.root + "/app.js").read().decode()
        self.assertIn('data-testid="river-explanation-form"', html)
        self.assertIn('data-state="idle"', html)
        self.assertIn("api('exploit'", script)
        self.assertIn("api('explain'", script)
        self.assertIn('data-testid="river-explanation-report"', script)
        self.assertIn('data-testid="action-evs"', script)
        self.assertIn('data-testid="strategy-comparison"', script)
        self.assertIn("setRiverExplanationState('error'", script)
        self.assertIn('role="alert"', script)

        analysis = self.post("/api/exploit", self.river_request())
        repeated = self.post("/api/exploit", self.river_request())
        self.assertEqual(analysis["analysis_id"], repeated["analysis_id"])
        self.assertNotEqual(analysis["baseline_strategy"],
                            analysis["exploitative_strategy"])
        self.assertIsNotNone(analysis["uncertainty"])
        self.assertTrue(analysis["opponent_assumptions"])

        payload = self.post("/api/explain", {
            "analysis": analysis,
            "recommended_action": analysis["best_response"]["action"],
            "level": "beginner",
        })
        self.assertEqual(payload["analysis_id"], analysis["analysis_id"])
        self.assertEqual(payload["level"], "beginner")
        self.assertEqual(payload["recommended_action"],
                         analysis["best_response"]["action"])
        self.assertEqual(payload["action_evs"], analysis["action_evs"])
        self.assertEqual(payload["ev_differences"], analysis["ev_differences"])
        self.assertEqual(payload["baseline_strategy"], analysis["baseline_strategy"])
        self.assertEqual(payload["exploitative_strategy"],
                         analysis["exploitative_strategy"])
        self.assertIsNotNone(payload["uncertainty"])
        self.assertTrue(payload["caveats"])
        self.assertTrue(payload["provenance"])

    def test_explain_endpoint_returns_controlled_errors_for_invalid_data(self):
        requests = (
            {},
            {"analysis": {}, "recommended_action": "bet"},
            {"analysis": self.post("/api/exploit", self.river_request()),
             "recommended_action": "not-legal"},
            {"analysis": self.post("/api/exploit", self.river_request()),
             "recommended_action": "bet", "level": "unsupported"},
        )
        for data in requests:
            with self.subTest(data=data):
                request = Request(
                    self.root + "/api/explain", json.dumps(data).encode(),
                    {"Content-Type": "application/json"})
                with self.assertRaises(HTTPError) as caught:
                    urlopen(request)
                self.assertEqual(caught.exception.code, 400)
                with caught.exception as response:
                    self.assertTrue(json.load(response)["error"])

    def test_exploit_rejects_unsupported_river_request(self):
        data = {**self.river_request(), "board": "AsAh"}
        request = Request(
            self.root + "/api/exploit", json.dumps(data).encode(),
            {"Content-Type": "application/json"})
        with self.assertRaises(HTTPError) as caught:
            urlopen(request)
        self.assertEqual(caught.exception.code, 400)
        with caught.exception as response:
            self.assertTrue(json.load(response)["error"])


if __name__ == "__main__":
    unittest.main()
