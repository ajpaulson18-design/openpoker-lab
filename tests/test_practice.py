import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import Request, urlopen

from pokerlab.game import Game
from pokerlab.models import Store
from pokerlab.practice import analyze_decision, decision_event, summarize, visible_state
from pokerlab.server import make_server


BASE = Path(__file__).resolve().parents[1] / "work"
BASE.mkdir(exist_ok=True)


class PracticeUnitTests(unittest.TestCase):
    def test_visible_state_never_leaks_other_hole_cards(self):
        game = Game([30, 30, 30], seed=3)
        state = visible_state(game)
        self.assertIsNotNone(state["hands"][state["actor"]])
        self.assertTrue(all(hand is None for seat, hand in enumerate(state["hands"])
                            if seat != state["actor"]))

    def test_event_uses_actual_analysis_for_ev_loss(self):
        game = Game([30, 30], seed=7)
        analysis = analyze_decision(game)
        chosen = min(analysis["actions"], key=analysis["actions"].get)
        event = decision_event(game, analysis, chosen)
        expected = analysis["actions"][analysis["recommended"]] - analysis["actions"][chosen]
        self.assertAlmostEqual(event["ev_loss"], expected)
        self.assertEqual(event["analysis_at_time"]["analysis_id"], analysis["analysis_id"])

    def test_review_uses_recorded_decisions(self):
        game = Game([30, 30], seed=4)
        analysis = analyze_decision(game)
        event = {**decision_event(game, analysis, analysis["recommended"]), "decision_order": 1}
        review = summarize([event])
        self.assertEqual(review["analyzed_decisions"], 1)
        self.assertEqual(review["matched_recommendation"], 1)
        self.assertEqual(review["total_ev_loss"], 0)

    def test_historical_record_is_not_recalculated(self):
        with tempfile.TemporaryDirectory(dir=BASE) as directory:
            store = Store(Path(directory) / "practice.sqlite3")
            game = Game([30, 30], seed=4)
            analysis = analyze_decision(game)
            stored = store.save_decision("session-1", decision_event(game, analysis, "call"))
            before = store.session("session-1")["decisions"][0]
            # A later calculation cannot rewrite the JSON captured at decision time.
            game2 = Game([30, 30], seed=9)
            analyze_decision(game2)
            after = store.session("session-1")["decisions"][0]
            self.assertEqual(before, after)
            self.assertEqual(after["analysis_at_time"]["analysis_id"], stored["analysis_at_time"]["analysis_id"])


class PracticeBrowserFlowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=BASE)
        self.server = make_server(0, Path(self.temp.name) / "browser.sqlite3")
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.root = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(); self.temp.cleanup()

    def post(self, path, data):
        request = Request(self.root + path, json.dumps(data).encode(), {"Content-Type": "application/json"})
        return json.load(urlopen(request))

    def test_hidden_coach_still_records_identical_analysis(self):
        hidden = self.post("/api/game", {"stacks": [20, 20], "names": ["Hero", "Villain"], "seed": 12})
        self.assertIsNone(hidden["hands"][1 - hidden["actor"]])
        action = "call" if hidden["legal"]["call"] else "check"
        result = self.post("/api/act", {"id": hidden["id"], "action": action, "coach_visible": False})
        self.assertNotIn("coach", result)
        review = json.load(urlopen(self.root + "/api/session/" + hidden["id"]))
        self.assertEqual(review["review"]["analyzed_decisions"], 1)
        saved = review["decisions"][0]["analysis_at_time"]

        shown = self.post("/api/game", {"stacks": [20, 20], "names": ["Hero", "Villain"], "seed": 12})
        result2 = self.post("/api/act", {"id": shown["id"], "action": action, "coach_visible": True})
        self.assertEqual(result2["coach"]["analysis_id"], saved["analysis_id"])
        self.assertEqual(result2["coach"]["actions"], saved["actions"])

    def test_completed_session_review_and_static_ui(self):
        game = self.post("/api/game", {"stacks": [10, 10], "names": ["Hero", "Villain"], "seed": 5})
        while not game["done"]:
            legal = game["legal"]
            action = "call" if legal["call"] else "check"
            game = self.post("/api/act", {"id": game["id"], "action": action, "coach_visible": True})
        review = json.load(urlopen(self.root + "/api/session/" + game["id"]))
        self.assertIsNotNone(review["session"]["completed_at"])
        self.assertGreater(review["review"]["analyzed_decisions"], 0)
        html = urlopen(self.root + "/").read().decode()
        script = urlopen(self.root + "/app.js").read().decode()
        self.assertIn("coach-toggle", html)
        self.assertIn("loadReview", script)


if __name__ == "__main__":
    unittest.main()
