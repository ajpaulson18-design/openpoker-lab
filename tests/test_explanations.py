import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import threading
import time
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

def _browser_binary(environment, candidates):
    configured = os.environ.get(environment)
    if configured:
        return configured if Path(configured).is_file() else None
    return next((path for name in candidates if (path := shutil.which(name))), None)


CHROME_BINARY = _browser_binary(
    "OPENPOKER_CHROME_BINARY",
    ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable", "chrome"))
CHROMEDRIVER_BINARY = _browser_binary(
    "OPENPOKER_CHROMEDRIVER_BINARY", ("chromedriver",))
if (os.environ.get("OPENPOKER_REQUIRE_BROWSER_TEST") == "true"
        and not (CHROME_BINARY and CHROMEDRIVER_BINARY)):
    raise RuntimeError("The required Chromium browser smoke-test tools are unavailable.")


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

    @unittest.skipUnless(CHROMEDRIVER_BINARY and CHROME_BINARY,
                         "Chromium and ChromeDriver are required for the browser smoke test")
    def test_chromium_submits_river_form_renders_and_handles_errors(self):
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        driver_process = subprocess.Popen(
            [CHROMEDRIVER_BINARY, f"--port={port}", "--allowed-ips=127.0.0.1"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        session_id = None

        def webdriver(method, path, data=None):
            request = Request(
                f"http://127.0.0.1:{port}{path}",
                json.dumps(data).encode() if data is not None else None,
                {"Content-Type": "application/json"} if data is not None else {},
                method=method)
            return json.load(urlopen(request, timeout=5))

        def execute(script, args=()):
            return webdriver(
                "POST", f"/session/{session_id}/execute/sync",
                {"script": script, "args": list(args)})["value"]

        def wait_for_state(final_states, timeout=20):
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                state = execute(
                    "return document.querySelector('#river-explanation-result').dataset.state")
                if state in final_states:
                    return state
                time.sleep(.1)
            self.fail(f"Browser explanation did not reach {final_states}.")

        try:
            for _ in range(100):
                try:
                    webdriver("GET", "/status")
                    break
                except Exception:
                    if driver_process.poll() is not None:
                        self.fail("ChromeDriver exited before becoming ready.")
                    time.sleep(.1)
            created = webdriver("POST", "/session", {
                "capabilities": {"alwaysMatch": {
                    "browserName": "chrome",
                    "goog:chromeOptions": {
                        "binary": CHROME_BINARY,
                        "args": ["--headless=new", "--no-sandbox",
                                 "--disable-dev-shm-usage"],
                    },
                }},
            })
            session_id = created["value"]["sessionId"]
            webdriver("POST", f"/session/{session_id}/url", {"url": self.root})
            for _ in range(100):
                if execute("return document.readyState") == "complete":
                    break
                time.sleep(.1)
            execute("document.querySelector('.tab[data-tab=solver]').click()")
            for _ in range(100):
                if execute("return document.querySelector('#river-explanation-opponent').options.length > 1"):
                    break
                time.sleep(.1)

            inputs = self.river_request()
            expected = self.post("/api/exploit", inputs)
            expected_payload = self.post("/api/explain", {
                "analysis": expected,
                "recommended_action": expected["best_response"]["action"],
                "level": "beginner",
            })
            execute("""
              for (const [name, value] of Object.entries(arguments[0])) {
                const field = document.querySelector(`#solver-form [name="${name}"]`);
                if (field) field.value = value;
              }
              document.querySelector('#river-explanation-form [name=hero_hand]').value = arguments[0].hero_hand;
              document.querySelector('#river-explanation-opponent').value = arguments[0].opponent_id;
              document.querySelector('#river-explanation-form [name=decision]').value = arguments[0].decision;
              document.querySelector('#river-explanation-form [name=level]').value = 'beginner';
              document.querySelector('#river-explanation-form').requestSubmit();
            """, [inputs])
            self.assertEqual(wait_for_state({"ready", "error"}), "ready")
            rendered = execute("""
              const report = document.querySelector('[data-testid=river-explanation-report]');
              const contract = arguments[0];
              const differences = Object.fromEntries(
                contract.ev_differences.map(item => [item.action, item.value]));
              const baseline = Object.fromEntries(
                contract.baseline_strategy.map(item => [item.action, item.frequency]));
              const exploit = Object.fromEntries(
                contract.exploitative_strategy.map(item => [item.action, item.frequency]));
              const rows = selector => [...report.querySelectorAll(`${selector} tbody tr`)]
                .map(row => [...row.cells].map(cell => cell.textContent));
              return {
                id: report.dataset.analysisId,
                level: report.dataset.level,
                recommendation: report.querySelector('[data-testid=explanation-recommendation] strong').textContent,
                summary: report.querySelector('[data-testid=explanation-summary]').textContent,
                confidence: report.querySelector('[data-testid=explanation-confidence]').dataset.confidence,
                evs: rows('[data-testid=action-evs]'),
                strategies: rows('[data-testid=strategy-comparison]'),
                evRowCount: report.querySelectorAll('[data-testid=action-evs] tbody tr').length,
                strategyRowCount: report.querySelectorAll('[data-testid=strategy-comparison] tbody tr').length,
                expectedEvs: contract.action_evs.map(item => [
                  item.action, String(item.value), String(differences[item.action])
                ]),
                expectedStrategies: contract.legal_actions.map(action => [
                  action, String(baseline[action]), String(exploit[action])
                ]),
                uncertainty: report.querySelector('[data-testid=explanation-uncertainty]').textContent,
                assumptions: [...report.querySelectorAll('[data-testid=model-assumptions] li')]
                  .map(item => item.textContent),
                caveats: [...report.querySelectorAll('.warnings li')].map(item => item.textContent),
                requests: performance.getEntriesByType('resource')
                  .map(item => new URL(item.name).pathname)
                  .filter(path => path === '/api/exploit' || path === '/api/explain'),
              };
            """, [expected])
            self.assertEqual(rendered["id"], expected["analysis_id"])
            self.assertEqual(rendered["level"], "beginner")
            self.assertEqual(rendered["recommendation"],
                             expected["best_response"]["action"])
            self.assertEqual(rendered["summary"], expected_payload["summary"])
            self.assertEqual(rendered["confidence"], expected["confidence"])
            self.assertIn(expected["uncertainty"]["method"], rendered["uncertainty"])
            self.assertEqual(rendered["evRowCount"], len(expected["action_evs"]))
            self.assertEqual(rendered["strategyRowCount"], len(expected["legal_actions"]))
            self.assertEqual(rendered["evs"], rendered["expectedEvs"])
            self.assertEqual(rendered["strategies"], rendered["expectedStrategies"])
            self.assertTrue(any(
                item["tendency_id"].replace("_", " ") in assumption
                and f"{item['evidence_count']} observed opportunities" in assumption
                for item in expected["opponent_assumptions"]
                for assumption in rendered["assumptions"]))
            self.assertEqual(rendered["caveats"], expected_payload["caveats"])
            self.assertEqual(rendered["requests"][-2:],
                             ["/api/exploit", "/api/explain"])

            execute("""
              const originalFetch = window.fetch.bind(window);
              window.fetch = async (input, init) => {
                const response = await originalFetch(input, init);
                if (!String(input).endsWith('/api/explain')) return response;
                const payload = await response.json();
                payload.summary = '<img id="xss-payload" src=x onerror="window.__xss=true">';
                payload.caveats.push('<svg id="xss-caveat" onload="window.__xss=true">');
                return new Response(JSON.stringify(payload), {
                  status: response.status, headers: {'Content-Type': 'application/json'}
                });
              };
              document.querySelector('#river-explanation-form').requestSubmit();
            """)
            self.assertEqual(wait_for_state({"ready", "error"}), "ready")
            safe_render = execute("""
              return {
                image: !!document.querySelector('#xss-payload'),
                svg: !!document.querySelector('#xss-caveat'),
                executed: !!window.__xss,
                escapedText: document.querySelector('[data-testid=river-explanation-report]')
                  .textContent.includes('<img id="xss-payload"'),
              };
            """)
            self.assertEqual(safe_render,
                             {"image": False, "svg": False,
                              "executed": False, "escapedText": True})

            execute("""
              document.querySelector('#river-explanation-form [name=hero_hand]').value = 'As As';
              document.querySelector('#river-explanation-form').requestSubmit();
            """)
            self.assertEqual(wait_for_state({"ready", "error"}), "error")
            error_state = execute("""
              return {
                alert: document.querySelector('#river-explanation-result [role=alert]').textContent,
                busy: document.querySelector('#river-explanation-result').getAttribute('aria-busy'),
              };
            """)
            self.assertIn("same card", error_state["alert"])
            self.assertEqual(error_state["busy"], "false")
        finally:
            if session_id:
                try:
                    webdriver("DELETE", f"/session/{session_id}")
                except Exception:
                    pass
            driver_process.terminate()
            try:
                driver_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                driver_process.kill()
                driver_process.wait()


if __name__ == "__main__":
    unittest.main()
