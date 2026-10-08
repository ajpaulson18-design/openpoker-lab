"""HTTP regressions for explicit pre-action study previews."""
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
from pokerlab.contracts import CoachDecisionRef
from pokerlab.current_study import CurrentStudyPreviewCache, build_current_study_view
from pokerlab.game import Game
from pokerlab.practice import _calculate_analysis, advance_to_hero, analyze_decision
from pokerlab.server import make_server


BASE = Path(__file__).resolve().parents[1] / "work"
BASE.mkdir(exist_ok=True)


class CurrentStudyHTTPTests(unittest.TestCase):
    def setUp(self):
        self.directory = BASE / f"current-study-{uuid.uuid4().hex}"
        self.directory.mkdir()
        self.server = make_server(0, self.directory / "study.sqlite3")
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.root = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        shutil.rmtree(self.directory, ignore_errors=True)

    def request(self, method, path, payload=None):
        body = None if payload is None else json.dumps(payload).encode()
        request = Request(self.root + path, body,
                          {"Content-Type": "application/json"} if body is not None else {},
                          method=method)
        try:
            with urlopen(request, timeout=8) as response:
                return response.status, json.load(response)
        except HTTPError as error:
            with error:
                return error.code, json.load(error)

    def post(self, path, payload):
        status, result = self.request("POST", path, payload)
        self.assertEqual(status, 200, result)
        return result

    def new_game(self):
        return self.post("/api/game", {
            "names": ["Hero", "Private Villain"], "stacks": [100, 100], "seed": 41,
        })

    @staticmethod
    def endpoint(game):
        return f"/api/v1/hands/{game['id']}/current-study"

    def test_preview_is_explicit_safe_and_idempotent_without_changing_hand(self):
        game = self.new_game()
        payload = {"expected_revision": game["revision"], "opponent_id": None}
        status, first = self.request("POST", self.endpoint(game), payload)
        self.assertEqual(status, 200, first)
        self.assertEqual(first["status"], "ready")
        self.assertEqual(first["binding"]["hand_id"], game["id"])
        self.assertEqual(first["binding"]["state_revision"], 0)
        self.assertEqual(first["context"]["hero_cards"], game["hands"][0])
        self.assertNotIn("Private Villain", json.dumps(first))
        self.assertNotIn("chosen_action", json.dumps(first))
        self.assertTrue(any("illustrative 45%" in item for item in first["assumptions"]))
        self.assertEqual(first["binding"]["decision_id"], self.request(
            "POST", self.endpoint(game), payload)[1]["binding"]["decision_id"])
        modeled_names = {item["name"] for item in first["modeled_actions"]}
        self.assertEqual(modeled_names, {name for name, legal in game["legal"].items()
                                         if name in ("fold", "check", "call", "raise") and legal})
        raise_action = next((item for item in first["modeled_actions"]
                             if item["name"] == "raise"), None)
        if raise_action:
            self.assertEqual(raise_action["amount"], game["legal"]["raise_min"])
            self.assertEqual(raise_action["maximum_legal_total"], game["legal"]["raise_max"])
            self.assertIn("minimum legal raise only", raise_action["size_note"])
        status, action = self.request("POST", "/api/act", {
            "id": game["id"], "action": "call", "expected_revision": 0,
            "coach_visible": False,
        })
        self.assertEqual(status, 200, action)
        self.assertEqual(action["revision"], 1)

    def test_optional_opponent_is_resolved_locally_and_changes_cache_identity(self):
        game = self.new_game()
        opponent = self.post("/api/opponents", {"name": "Practice model", "profile": "calling_station"})
        path = self.endpoint(game)
        first_status, first = self.request("POST", path, {
            "expected_revision": 0, "opponent_id": opponent["id"],
        })
        second_status, second = self.request("POST", path, {
            "expected_revision": 0, "opponent_id": None,
        })
        self.assertEqual((first_status, second_status), (200, 200))
        self.assertNotEqual(first["binding"]["decision_id"], second["binding"]["decision_id"])
        self.assertTrue(any("Fold-to-bet estimate" in item for item in first["assumptions"]))
        self.assertTrue(any("illustrative 45%" in item for item in second["assumptions"]))
        self.assertNotIn("Practice model", json.dumps(first))

    def test_unknown_malformed_and_stale_requests_have_specific_statuses(self):
        game = self.new_game()
        self.assertEqual(self.request("POST", "/api/v1/hands/missing/current-study", {
            "expected_revision": 0, "opponent_id": None,
        })[0], 404)
        self.assertEqual(self.request("POST", self.endpoint(game), {
            "expected_revision": True, "opponent_id": None,
        })[0], 400)
        self.assertEqual(self.request("POST", self.endpoint(game), {
            "expected_revision": 0, "opponent_id": None, "extra": 1,
        })[0], 400)
        self.assertEqual(self.request("POST", self.endpoint(game), {
            "expected_revision": 1, "opponent_id": None,
        })[0], 409)

    def test_calculation_does_not_hold_game_lock_or_gameplay_slot_and_rechecks_revision(self):
        game = self.new_game()
        entered, release = threading.Event(), threading.Event()
        from pokerlab.practice import analyze_decision as real_analyze
        calls = 0
        calls_lock = threading.Lock()

        def delayed(snapshot, opponent=None):
            nonlocal calls
            with calls_lock:
                calls += 1
                ordinal = calls
            if ordinal == 1:
                entered.set()
                release.wait(5)
            return real_analyze(snapshot, opponent)

        preview_result = {}

        def preview():
            preview_result["response"] = self.request("POST", self.endpoint(game), {
                "expected_revision": 0, "opponent_id": None,
            })

        with patch("pokerlab.server.analyze_decision", side_effect=delayed):
            worker = threading.Thread(target=preview, daemon=True)
            worker.start()
            self.assertTrue(entered.wait(4), "preview calculation did not start")
            status, action = self.request("POST", "/api/act", {
                "id": game["id"], "action": "call", "expected_revision": 0,
                "coach_visible": False,
            })
            self.assertEqual(status, 200, action)
            release.set()
            worker.join(6)
        self.assertFalse(worker.is_alive())
        self.assertEqual(preview_result["response"][0], 409)

    def test_preview_admission_is_separate_and_bounded(self):
        game = self.new_game()
        entered, release = threading.Event(), threading.Event()
        from pokerlab.practice import analyze_decision as real_analyze

        def delayed(snapshot, opponent=None):
            entered.set()
            release.wait(5)
            return real_analyze(snapshot, opponent)

        first_result = {}
        with patch("pokerlab.server.analyze_decision", side_effect=delayed):
            worker = threading.Thread(target=lambda: first_result.setdefault(
                "response", self.request("POST", self.endpoint(game), {
                    "expected_revision": 0, "opponent_id": None,
                })), daemon=True)
            worker.start()
            self.assertTrue(entered.wait(4))
            self.assertEqual(self.request("POST", self.endpoint(game), {
                "expected_revision": 0, "opponent_id": None,
            })[0], 429)
            status, action = self.request("POST", "/api/act", {
                "id": game["id"], "action": "call", "expected_revision": 0,
                "coach_visible": False,
            })
            self.assertEqual(status, 200, action)
            release.set()
            worker.join(6)
        self.assertFalse(worker.is_alive())
        self.assertEqual(first_result["response"][0], 409)


class CurrentStudyEvidenceTests(unittest.TestCase):
    @staticmethod
    def evidence(*, exact_river=False):
        game = Game(stacks=[100, 100], names=["Hero", "Villain"], seed=41)
        advance_to_hero(game)
        raw = analyze_decision(game)
        if exact_river:
            inputs = json.loads(json.dumps(raw["analysis_inputs"]))
            hero_cards = set(inputs["known_cards"])
            from pokerlab.cards import DECK
            inputs["public_cards"] = [card for card in DECK if card not in hero_cards][:5]
            inputs["street"] = "river"
            inputs["opponent_ranges"] = ["random"]
            raw = _calculate_analysis(inputs)
        return adapt_practice_analysis(
            raw, ref=CoachDecisionRef("test-hand", uuid.uuid4().hex, 0))

    def test_view_uses_validated_exactness_for_exact_and_sampled_equity(self):
        sampled = build_current_study_view(self.evidence())
        exact_evidence = self.evidence(exact_river=True)
        exact = build_current_study_view(exact_evidence)
        self.assertTrue(exact_evidence.quality.equity_exact)
        self.assertTrue(any("exactly enumerated" in item for item in exact["limitations"]))
        self.assertFalse(any("Equity is sampled" in item for item in exact["limitations"]))
        self.assertTrue(any("Equity is sampled" in item for item in sampled["limitations"]))

    def test_preview_cache_retains_resolvable_evidence_with_its_view_until_expiry(self):
        now = [10.0]
        cache = CurrentStudyPreviewCache(ttl_seconds=5, clock=lambda: now[0])
        evidence = self.evidence()
        view = build_current_study_view(evidence)
        key = ("test-hand", 0, "illustrative-default")
        cache.put(key, evidence, view)

        cached_evidence, cached_view = cache.get(key)
        self.assertIs(cached_evidence, evidence)
        self.assertEqual(cached_view, view)
        binding = view["binding"]
        self.assertIs(cache.resolve(**binding), evidence)

        now[0] += 5
        self.assertIsNone(cache.get(key))
        self.assertIsNone(cache.resolve(**binding))

    def test_browser_rejects_a_preview_response_with_a_wrong_or_missing_binding(self):
        source_path = Path(__file__).resolve().parents[1] / "pokerlab" / "web" / "app.js"
        source = source_path.read_text(encoding="utf-8")
        request = source[source.index("async function requestCurrentStudy"):
                         source.index("function coachExplanation")]
        for required in (
                "binding.hand_id!==handId", "binding.state_revision!==revision",
                "typeof binding.decision_id!=='string'", "!binding.decision_id.trim()",
                "typeof binding.evidence_id!=='string'", "!binding.evidence_id.trim()"):
            self.assertIn(required, request)


if __name__ == "__main__":
    unittest.main()

