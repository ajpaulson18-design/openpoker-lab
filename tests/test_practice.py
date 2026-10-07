import json
import shutil
import threading
import unittest
import uuid
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from pokerlab.game import Game
from pokerlab.models import Store
from pokerlab.practice import (advance_to_hero, analyze_decision,
                               analyze_recorded_decision, decision_event,
                               render_coach_personality, summarize, visible_state)
from pokerlab.server import make_server


BASE = Path(__file__).resolve().parents[1] / "work"
BASE.mkdir(exist_ok=True)


class WorkspaceDirectory:
    """Workspace-safe test directory for Windows sandbox ACL compatibility."""

    def __init__(self):
        self.name = str(BASE / f"test-{uuid.uuid4().hex}")
        Path(self.name).mkdir()

    def __enter__(self):
        return self.name

    def __exit__(self, *_):
        self.cleanup()

    def cleanup(self):
        path = Path(self.name)
        if path.exists():
            shutil.rmtree(path)


class PracticeUnitTests(unittest.TestCase):
    def test_visible_state_never_leaks_other_hole_cards(self):
        game = Game([30, 30, 30], seed=3)
        state = visible_state(game)
        self.assertIsNotNone(state["hands"][0])
        self.assertTrue(all(hand is None for hand in state["hands"][1:]))

    def test_non_hero_actions_are_deterministic_and_not_coached(self):
        game = Game([30, 30, 30], seed=3)
        advance_to_hero(game)
        self.assertTrue(game.done or game.actor == 0)
        self.assertTrue(all(entry["seat"] != 0 for entry in game.log))

    def test_event_uses_actual_analysis_for_ev_loss(self):
        game = Game([30, 30], seed=7)
        analysis = analyze_decision(game)
        chosen = min(analysis["actions"], key=analysis["actions"].get)
        amount = game.legal()["raise_min"] if chosen == "raise" else None
        event = decision_event(game, analysis, chosen, amount=amount)
        expected = analysis["actions"][analysis["recommended"]] - analysis["actions"][chosen]
        self.assertAlmostEqual(event["ev_loss"], expected)
        self.assertEqual(event["analysis_at_time"]["analysis_id"], analysis["analysis_id"])

    def test_analysis_id_covers_evidence_confidence_and_snapshot(self):
        def opponent(observations, confidence, interval):
            return {
                "id": "same-opponent", "profile": "balanced", "street": "preflop",
                "model_version": "beta-opportunity-v2",
                "metrics": {"fold_to_bet": {
                    "mean": .45, "confidence": confidence,
                    "observations": observations, "successes": 0,
                    "prior_strength": 10, "interval95": interval,
                    "interval_method": "test interval",
                }},
            }
        first = analyze_decision(Game([30, 30], seed=7), opponent(0, "low", [.1, .8]))
        second = analyze_decision(
            Game([30, 30], seed=7), opponent(100, "higher", [.4, .5]))
        self.assertEqual(first["actions"], second["actions"])
        self.assertNotEqual(first["analysis_id"], second["analysis_id"])

    def test_multiway_analysis_models_every_live_opponent(self):
        heads_up = analyze_decision(Game([30, 30], seed=7))
        three_way = analyze_decision(Game([30, 30, 30], seed=7))
        self.assertEqual(heads_up["analysis_inputs"]["opponent_ranges"], ["random"])
        self.assertEqual(three_way["analysis_inputs"]["opponent_ranges"],
                         ["random", "random"])
        self.assertEqual(len(three_way["equity"]["range_combos"]), 2)
        self.assertNotEqual(heads_up["equity"]["equity"], three_way["equity"]["equity"])

    def test_event_persists_complete_inputs_and_recalculates_identically(self):
        game = Game([30, 30, 20], seed=9)
        analysis = analyze_decision(game)
        chosen = analysis["recommended"]
        event = decision_event(game, analysis, chosen,
                               amount=game.legal()["raise_min"] if chosen == "raise" else None)
        self.assertEqual(event["actor"], game.actor)
        self.assertEqual(event["button"], game.button)
        self.assertEqual(event["legal_action_details"], game.legal())
        self.assertEqual(event["committed"], game.committed)
        self.assertEqual(event["street_bets"], game.street_bets)
        self.assertEqual(event["current_bet"], game.current_bet)
        self.assertEqual(event["min_raise"], game.min_raise)
        replay = analyze_recorded_decision(event["analysis_inputs"])
        self.assertEqual(replay["analysis_id"], analysis["analysis_id"])
        self.assertEqual(replay["actions"], analysis["actions"])
        self.assertEqual(replay["equity"], analysis["equity"])

    def test_review_uses_recorded_decisions(self):
        game = Game([30, 30], seed=4)
        analysis = analyze_decision(game)
        chosen = analysis["recommended"]
        event = {**decision_event(game, analysis, chosen,
                                  amount=game.legal()["raise_min"] if chosen == "raise" else None),
                 "decision_order": 1}
        review = summarize([event])
        self.assertEqual(review["analyzed_decisions"], 1)
        self.assertEqual(review["matched_recommendation"], 1)
        self.assertEqual(review["total_ev_loss"], 0)

    def test_review_ranks_errors_and_successful_exploits(self):
        base = {"matched_recommendation": False, "successful_exploit": False,
                "analysis_at_time": {"recommended": "raise", "baseline_recommended": "check"}}
        events = [
            {**base, "decision_order": 1, "ev_loss": 2.0, "exploit_gain": 0.0},
            {**base, "decision_order": 2, "ev_loss": 8.0, "exploit_gain": 0.0},
            {**base, "decision_order": 3, "ev_loss": 0.0, "exploit_gain": 3.0,
             "matched_recommendation": True, "successful_exploit": True},
            {**base, "decision_order": 4, "ev_loss": 0.0, "exploit_gain": 9.0,
             "matched_recommendation": True, "successful_exploit": True},
        ]
        review = summarize(events)
        self.assertEqual([item["ev_loss"] for item in review["biggest_errors"]], [8.0, 2.0])
        self.assertEqual([item["exploit_gain"] for item in review["biggest_successful_exploits"]],
                         [9.0, 3.0])

    def test_personality_changes_only_presentation(self):
        analysis = analyze_decision(Game([30, 30], seed=7))
        grinder = render_coach_personality(analysis, "grinder")
        math = render_coach_personality(analysis, "math_guy")
        self.assertEqual(grinder["analysis_id"], analysis["analysis_id"])
        self.assertEqual(math["analysis_id"], analysis["analysis_id"])
        self.assertEqual(grinder["facts_fingerprint"], math["facts_fingerprint"])
        self.assertNotEqual(grinder["text"], math["text"])
        with self.assertRaises(ValueError):
            render_coach_personality(analysis, "invalid")

    def test_historical_record_is_not_recalculated(self):
        with WorkspaceDirectory() as directory:
            store = Store(Path(directory) / "practice.sqlite3")
            game = Game([30, 30], seed=4)
            opponent = store.add_opponent("Changing model")
            old_model = store.get_opponent(opponent["id"], game.street)
            old_model["model_version"] = "beta-opportunity-v1"
            analysis = analyze_decision(game, old_model)
            stored = store.save_decision("session-1", decision_event(game, analysis, "call", old_model))
            before = store.session("session-1")["decisions"][0]
            store.observe(opponent["id"], "fold_to_bet", True, game.street)
            self.assertEqual(store.get_opponent(opponent["id"], game.street)["metrics"]["fold_to_bet"]["observations"], 1)
            after = store.session("session-1")["decisions"][0]
            self.assertEqual(before, after)
            self.assertEqual(after["opponent_model_snapshot"]["metrics"]["fold_to_bet"]["observations"], 0)
            self.assertEqual(after["analysis_at_time"]["analysis_id"], stored["analysis_at_time"]["analysis_id"])


class PracticeBrowserFlowTests(unittest.TestCase):
    def setUp(self):
        self.temp = WorkspaceDirectory()
        self.server = make_server(0, Path(self.temp.name) / "browser.sqlite3")
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.root = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(); self.temp.cleanup()

    def post(self, path, data):
        request = Request(self.root + path, json.dumps(data).encode(), {"Content-Type": "application/json"})
        return json.load(urlopen(request))

    def finish(self, game, coach_visible=False):
        while not game["done"]:
            legal = game["legal"]
            action = "call" if legal["call"] else "check"
            game = self.post("/api/act", {"id": game["id"], "action": action,
                                           "coach_visible": coach_visible})
        return game

    def test_hidden_coach_still_records_identical_analysis(self):
        hidden = self.post("/api/game", {"stacks": [20, 20], "names": ["Hero", "Villain"], "seed": 12})
        self.assertIsNone(hidden["hands"][1 - hidden["actor"]])
        action = "call" if hidden["legal"]["call"] else "check"
        result = self.post("/api/act", {"id": hidden["id"], "action": action, "coach_visible": False})
        self.assertNotIn("coach", result)
        result = self.finish(result)
        review = json.load(urlopen(self.root + "/api/session/" + hidden["id"]))
        self.assertGreaterEqual(review["review"]["analyzed_decisions"], 1)
        saved = review["decisions"][0]["analysis_at_time"]

        shown = self.post("/api/game", {"stacks": [20, 20], "names": ["Hero", "Villain"], "seed": 12})
        result2 = self.post("/api/act", {"id": shown["id"], "action": action, "coach_visible": True})
        self.assertEqual(result2["coach"]["analysis_id"], saved["analysis_id"])
        self.assertEqual(result2["coach"]["actions"], saved["actions"])

    def test_only_hero_decisions_are_recorded_and_villain_cards_never_serialize(self):
        game = self.post("/api/game", {"stacks": [20, 20, 20],
                                        "names": ["Hero", "V1", "V2"], "seed": 8})
        hero_decisions = 0
        while not game["done"]:
            self.assertEqual(game["actor"], 0)
            self.assertTrue(all(hand is None for hand in game["hands"][1:]))
            action = "call" if game["legal"]["call"] else "check"
            game = self.post("/api/act", {"id": game["id"], "action": action,
                                           "coach_visible": False})
            hero_decisions += 1
        self.assertTrue(all(hand is None for hand in game["hands"][1:]))
        review = json.load(urlopen(self.root + "/api/session/" + game["id"]))
        self.assertEqual(review["review"]["analyzed_decisions"], hero_decisions)

    def test_invalid_personality_cannot_advance_or_persist(self):
        game = self.post("/api/game", {"stacks": [20, 20], "names": ["Hero", "Villain"],
                                        "seed": 22})
        action = "call" if game["legal"]["call"] else "check"
        with self.assertRaises(HTTPError) as caught:
            self.post("/api/act", {"id": game["id"], "action": action,
                                    "coach_visible": True, "personality": "invalid"})
        self.assertEqual(caught.exception.code, 400)
        caught.exception.close()
        valid = self.post("/api/act", {"id": game["id"], "action": action,
                                        "coach_visible": True, "personality": "grinder"})
        self.assertEqual(valid["decision_order"], 1)

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
        self.assertIn("coachExplanation(result.explanation_payload)", script)

    def test_selected_offline_personality_is_returned_without_changing_analysis(self):
        game = self.post("/api/game", {"stacks": [20, 20], "names": ["Hero", "Villain"],
                                        "seed": 12})
        action = "call" if game["legal"]["call"] else "check"
        result = self.post("/api/act", {"id": game["id"], "action": action,
                                         "coach_visible": True,
                                         "personality": "old_school_pro"})
        voice = result["coach"]["personality"]
        self.assertEqual(voice["personality"], "old_school_pro")
        self.assertEqual(voice["source"], "deterministic")
        self.assertEqual(voice["analysis_id"], result["coach"]["analysis_id"])
        explanation = result["coach"]["explanation_payload"]
        self.assertEqual(explanation["analysis_id"], result["coach"]["analysis_id"])
        self.assertEqual(explanation["recommended_action"], result["coach"]["recommended"])
        self.assertIn("mathematical_reason", explanation)
        self.assertIn("alternative_actions", explanation)

    def test_malformed_persisted_decision_returns_controlled_json_error(self):
        database = Path(self.temp.name) / "browser.sqlite3"
        store = Store(database)
        store.start_session("corrupt-session")
        with store.connect() as db:
            db.execute("UPDATE sessions SET completed_at=CURRENT_TIMESTAMP WHERE id=?",
                       ("corrupt-session",))
            db.execute("""INSERT INTO decisions(id,session_id,decision_order,event)
                        VALUES (?,?,?,?)""",
                       ("bad-decision", "corrupt-session", 1, '{"not":"a decision"}'))
        with self.assertRaises(HTTPError) as caught:
            urlopen(self.root + "/api/session/corrupt-session")
        self.assertEqual(caught.exception.code, 400)
        with caught.exception as response:
            payload = json.load(response)
        self.assertIn("malformed decision data", payload["error"])

    def test_repeated_personality_switches_preserve_first_decision_facts(self):
        outputs = []
        for personality in ("grinder", "nit", "math_guy", "grinder"):
            game = self.post("/api/game", {"stacks": [20, 20],
                                            "names": ["Hero", "Villain"], "seed": 31})
            action = "call" if game["legal"]["call"] else "check"
            result = self.post("/api/act", {"id": game["id"], "action": action,
                                             "coach_visible": True,
                                             "personality": personality})
            outputs.append(result["coach"])
        self.assertEqual(len({item["analysis_id"] for item in outputs}), 1)
        self.assertEqual(len({item["personality"]["facts_fingerprint"]
                              for item in outputs}), 1)
        self.assertGreater(len({item["personality"]["text"] for item in outputs}), 1)

    def test_dom_assets_wire_selector_inside_practice_and_render_ranked_review(self):
        html = urlopen(self.root + "/").read().decode()
        script = urlopen(self.root + "/app.js").read().decode()
        self.assertIn('id="coach-voice-template"', html)
        self.assertIn("#table .coach-toolbar", script)
        self.assertIn("cloneNode(true)", script)
        self.assertIn("personality:$('#coach-personality').value", script)
        self.assertIn("Biggest errors", script)
        self.assertIn("Biggest successful exploits", script)
        self.assertIn("expected_revision:game.revision", script)
        self.assertIn("client_action_id:pendingAction.id", script)
        self.assertIn("RAISE SIZE NOT EVALUATED", script)
        self.assertIn("if(action==='raise')$('#raise-amount').value=amount", script)
        self.assertNotIn("result.actions[result.recommended]-result.actions[chosen]", script)


if __name__ == "__main__":
    unittest.main()
