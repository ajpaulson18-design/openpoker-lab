"""HTTP and view-model tests for deterministic saved-decision study."""
from dataclasses import fields, replace
import json
from pathlib import Path
import shutil
import threading
import unittest
import uuid
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch

from pokerlab.contracts import (CoachActionValue, CoachAnalysisQuality,
                                CoachDecisionAnalysis)
from pokerlab.decision_study import build_decision_study
from pokerlab.models import Store
from pokerlab.server import make_server


BASE = Path(__file__).resolve().parents[1] / "work" / "decision-study-tests"
BASE.mkdir(parents=True, exist_ok=True)


class DecisionStudyTests(unittest.TestCase):
    def setUp(self):
        self.directory = BASE / f"run-{uuid.uuid4().hex}"
        self.directory.mkdir()
        self.database = self.directory / "study.sqlite3"
        self.store = Store(self.database)
        self.server = make_server(0, self.database)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.root = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        shutil.rmtree(self.directory, ignore_errors=True)

    def post(self, path, payload):
        request = Request(self.root + path, json.dumps(payload).encode(),
                          {"Content-Type": "application/json"})
        return json.load(urlopen(request))

    def get(self, path):
        return json.load(urlopen(self.root + path))

    def failed_get(self, path):
        with self.assertRaises(HTTPError) as caught:
            self.get(path)
        with caught.exception as response:
            return response.code, json.load(response)

    def new_game(self, button=0):
        return self.post("/api/game", {"stacks": [100, 100], "names": ["Hero", "Villain"],
                                       "button": button, "seed": 61})

    def capture(self, action="call", *, button=0, amount=None):
        game = self.new_game(button)
        if action == "raise" and amount is None:
            amount = game["legal"]["raise_min"]
        result = self.post("/api/act", {
            "id": game["id"], "action": action, "amount": amount,
            "coach_visible": False, "expected_revision": 0,
            "client_action_id": uuid.uuid4().hex,
        })
        return game, result

    def study_path(self, decision_id):
        return f"/api/v1/decisions/{decision_id}/study"

    def study_with_visible_cards(self, hero_cards, board, *, action="call", amount=None):
        game, accepted = self.capture(action, amount=amount)
        saved = self.get(f"/api/v1/decisions/{accepted['decision']['decision_id']}/analysis")
        analysis = CoachDecisionAnalysis.from_json(json.dumps(saved["analysis"]))
        values = {item.name: getattr(analysis, item.name)
                  for item in fields(CoachDecisionAnalysis) if item.name != "evidence_id"}
        values["context"] = replace(
            analysis.context, street={0: "preflop", 3: "flop", 4: "turn", 5: "river"}[len(board)],
            hero_cards=tuple(hero_cards), board=tuple(board),
        )
        return build_decision_study(CoachDecisionAnalysis.build(**values), saved["choice"])

    def test_study_projects_validated_facts_without_recalculation(self):
        game, accepted = self.capture("call")
        decision_id = accepted["decision"]["decision_id"]
        with (patch("pokerlab.server.analyze_decision", side_effect=AssertionError("recalculated")),
              patch("pokerlab.server.adapt_practice_analysis", side_effect=AssertionError("adapted")),
              patch("pokerlab.server.solve", side_effect=AssertionError("solved")),
              patch("pokerlab.server.analyze", side_effect=AssertionError("analyzed")),
              patch("pokerlab.server.simulate", side_effect=AssertionError("simulated"))):
            study = self.get(self.study_path(decision_id))
        self.assertEqual(study["schema_version"], 1)
        self.assertEqual(study["status"], "ready")
        self.assertEqual(study["binding"], {
            "hand_id": game["id"], "decision_id": decision_id,
            "evidence_id": self.get(f"/api/v1/decisions/{decision_id}/analysis")
            ["analysis"]["evidence_id"], "state_revision": 0,
        })
        self.assertEqual(study["source_label"], "Practice estimate")
        self.assertEqual([card["id"] for card in study["cards"]],
                         ["estimate", "my_choice", "limits"])
        self.assertIn("No opponent assumption was captured", study["cards"][2]["answer"])
        self.assertIsNotNone(study["baseline"])
        self.assertIn("estimated_ev_chips", study["baseline"])
        self.assertNotIn("estimated_ev", study["baseline"])
        self.assertTrue(all("estimated_ev_chips" in action
                            for action in study["modeled_actions"]))
        self.assertIn("estimated chips from this decision", study["cards"][0]["answer"])
        self.assertNotIn("incremental_decision_chips", " ".join(
            card["answer"] for card in study["cards"]))
        self.assertNotIn("Hero", json.dumps(study))
        self.assertNotIn("Villain", json.dumps(study))
        self.assertNotIn("hero_cards", study)

    def test_situation_teaches_72_offsuit_without_calling_it_the_worst_hand(self):
        study = self.study_with_visible_cards(("7c", "2d"), ())
        self.assertEqual(study["situation"]["title"], "Your situation")
        self.assertIn("challenging starting hand", study["situation"]["text"])
        self.assertIn("best action still depends on this spot", study["situation"]["text"])
        self.assertIn("7–2 offsuit", study["situation"]["text"])
        self.assertIn("both low ranks", study["situation"]["text"])
        self.assertIn("unpaired", study["situation"]["text"])
        self.assertIn("not connected", study["situation"]["text"])
        self.assertIn("do not offer an easy straight connection", study["situation"]["text"])
        self.assertIn("cannot both help make a flush in one suit", study["situation"]["text"])
        self.assertNotIn("worst", study["situation"]["text"].lower())
        self.assertNotIn("worst hand", study["situation"]["text"].lower())
        self.assertEqual(study["decision"]["title"], "Your decision")
        self.assertIn("quality of your cards does not by itself decide", study["decision"]["note"])

    def test_ev_basis_copy_is_plain_language_while_saved_values_stay_exact(self):
        _, accepted = self.capture("call")
        decision_id = accepted["decision"]["decision_id"]
        saved = self.get(f"/api/v1/decisions/{decision_id}/analysis")
        analysis = CoachDecisionAnalysis.from_json(json.dumps(saved["analysis"]))
        view = build_decision_study(analysis, saved["choice"])
        source_values = {item.action_id: item.value for item in analysis.action_evs}
        self.assertEqual(view["ev_basis"], "incremental_decision_chips")
        self.assertIn("estimated chips from this decision", view["cards"][0]["answer"])
        self.assertNotIn("incremental_decision_chips", " ".join(
            card["answer"] for card in view["cards"]))
        self.assertEqual(
            {item["action_id"]: item["estimated_ev_chips"]
             for item in view["modeled_actions"]},
            source_values,
        )

    def test_pocket_pair_does_not_get_suited_or_connected_labels(self):
        study = self.study_with_visible_cards(("Ac", "Ad"), ())
        text = study["situation"]["text"]
        self.assertIn("pocket pair", text)
        self.assertIn("suitedness and connectedness do not apply", text)
        self.assertNotIn("offsuit", text)
        self.assertNotIn("not connected", text)

    def test_ace_deuce_explains_ace_low_straight_in_beginner_language(self):
        study = self.study_with_visible_cards(("Ac", "2d"), ())
        self.assertIn("An ace can also count low in an A-2-3-4-5 straight",
                      study["situation"]["text"])

    def test_situation_labels_bottom_pair_on_an_unpaired_flop(self):
        study = self.study_with_visible_cards(("3d", "2c"), ("4c", "3h", "Th"))
        self.assertIn("bottom pair", study["situation"]["text"])
        self.assertIn("unpaired board", study["situation"]["text"])
        self.assertIn("pair ranks below a pair made with a higher rank on the board",
                      study["situation"]["text"])
        self.assertIn("An opponent may or may not have a better hand",
                      study["situation"]["text"])
        self.assertIn("current model and this spot", study["situation"]["text"])
        self.assertNotIn("opponent has", study["situation"]["text"].lower())

    def test_situation_uses_made_hand_category_without_claiming_relative_strength(self):
        study = self.study_with_visible_cards(("2s", "3d"), ("4c", "5h", "6s"))
        self.assertIn("straight", study["situation"]["text"])
        self.assertIn("does not tell us what an opponent holds or whether you are ahead",
                      study["situation"]["text"])

    def test_high_card_is_explained_without_poker_jargon_or_relative_claims(self):
        study = self.study_with_visible_cards(("2s", "3d"), ("4c", "8h", "Ts"))
        self.assertIn("no pair or stronger made hand (high card)",
                      study["situation"]["text"])
        self.assertIn("does not tell us what an opponent holds or whether you are ahead",
                      study["situation"]["text"])

    def test_unassessed_raise_guidance_does_not_claim_a_scored_comparison(self):
        game = self.new_game()
        amount = game["legal"]["raise_min"] + 1
        study = self.study_with_visible_cards(("7c", "2d"), (), action="raise", amount=amount)
        self.assertEqual(study["choice"]["assessment_status"], "unassessed_size")
        self.assertIn("does not score the size you chose", study["decision"]["text"])
        self.assertIn("raise size was not assessed", study["decision"]["note"])
        self.assertIn("Your cards alone do not decide", study["decision"]["note"])
        self.assertNotIn("Your action is assessed", study["decision"]["note"])

    def test_unassessed_raise_is_distinct_from_modeled_minimum(self):
        game = self.new_game()
        amount = game["legal"]["raise_min"] + 1
        accepted = self.post("/api/act", {
            "id": game["id"], "action": "raise", "amount": amount,
            "coach_visible": False, "expected_revision": 0,
            "client_action_id": uuid.uuid4().hex,
        })
        study = self.get(self.study_path(accepted["decision"]["decision_id"]))
        self.assertEqual(study["choice"]["assessment_status"], "unassessed_size")
        self.assertIsNone(study["choice"]["ev_loss"])
        raise_action = next(item for item in study["modeled_actions"] if item["name"] == "raise")
        self.assertLess(raise_action["amount"], amount)
        answer = study["cards"][1]["answer"]
        self.assertIn("exact raise to", answer)
        self.assertIn("separate alternative", answer)
        self.assertIn("does not score the chosen size", answer)

    def test_assessed_minimum_raise_has_saved_gap_and_action_families(self):
        for action, button in (("raise", 0), ("fold", 0), ("check", 1)):
            with self.subTest(action=action):
                game, accepted = self.capture(action, button=button)
                study = self.get(self.study_path(accepted["decision"]["decision_id"]))
                self.assertEqual(study["choice"]["name"], action)
                self.assertEqual(study["choice"]["assessment_status"], "assessed")
                self.assertIsNotNone(study["choice"]["ev_loss"])
                self.assertIn("recorded gap", study["cards"][1]["answer"])

    def test_solver_quality_uses_a_distinct_source_and_basis_label(self):
        _, accepted = self.capture("call")
        saved = self.get(f"/api/v1/decisions/{accepted['decision']['decision_id']}/analysis")
        analysis = CoachDecisionAnalysis.from_json(json.dumps(saved["analysis"]))
        values = {item.name: getattr(analysis, item.name)
                  for item in fields(CoachDecisionAnalysis) if item.name != "evidence_id"}
        values["source_kind"] = "restricted_equilibrium"
        values["ev_basis"] = "half_initial_pot_utility"
        values["quality"] = CoachAnalysisQuality(
            confidence_label="solver diagnostics", opponent_uncertainty=None,
            equity_standard_error=None, equity_exact=None, nash_conv=0.00001,
            exploitability=0.1, iterations=50, gap_semantics="per-player best-response gap",
        )
        solver_analysis = CoachDecisionAnalysis.build(**values)
        view = build_decision_study(solver_analysis, saved["choice"])
        self.assertEqual(view["source_label"], "Restricted equilibrium result")
        self.assertEqual(view["ev_basis"], "half_initial_pot_utility")
        self.assertIn("solver chip utility measured relative to half the starting pot",
                      view["cards"][0]["answer"])
        self.assertNotIn("half_initial_pot_utility", " ".join(
            card["answer"] for card in view["cards"]))
        self.assertIn("NashConv less than 0.01", view["cards"][2]["answer"])
        self.assertEqual(view["solver_quality"]["iterations"], 50)
        self.assertTrue(all("estimated_ev" in action and "estimated_ev_chips" not in action
                            for action in view["modeled_actions"]))

    def test_missing_ev_stays_null_and_missing_baseline_is_omitted(self):
        game = self.new_game()
        amount = game["legal"]["raise_min"] + 1
        accepted = self.post("/api/act", {
            "id": game["id"], "action": "raise", "amount": amount,
            "coach_visible": False, "expected_revision": 0,
            "client_action_id": uuid.uuid4().hex,
        })
        saved = self.get(f"/api/v1/decisions/{accepted['decision']['decision_id']}/analysis")
        analysis = CoachDecisionAnalysis.from_json(json.dumps(saved["analysis"]))
        values = {item.name: getattr(analysis, item.name)
                  for item in fields(CoachDecisionAnalysis) if item.name != "evidence_id"}
        values["baseline_recommended_action_id"] = None
        first_action_id = analysis.action_evs[0].action_id
        values["action_evs"] = tuple(
            CoachActionValue(item.action_id, None if item.action_id == first_action_id else item.value)
            for item in analysis.action_evs
        )
        without_value = CoachDecisionAnalysis.build(**values)
        view = build_decision_study(without_value, saved["choice"])
        self.assertIsNone(view["baseline"])
        self.assertTrue(any(item["estimated_ev_chips"] is None
                            for item in view["modeled_actions"]))

    def test_legacy_unknown_and_tampered_decisions_keep_controlled_statuses(self):
        legacy = self.store.save_decision("legacy-study", {"chosen_action": "call"})
        self.assertEqual(self.get(self.study_path(legacy["decision_id"]),), {
            "status": "unavailable",
            "reason": "Versioned coach evidence was not captured for this decision.",
        })
        status, payload = self.failed_get(self.study_path("unknown"))
        self.assertEqual(status, 404)
        self.assertEqual(payload, {"error": "Not found."})
        _, accepted = self.capture("call")
        decision_id = accepted["decision"]["decision_id"]
        with self.store.connect() as db:
            event = json.loads(db.execute("SELECT event FROM decisions WHERE id=?",
                                          (decision_id,)).fetchone()["event"])
            event["chosen_action_detail"]["amount"] += 1
            db.execute("UPDATE decisions SET event=? WHERE id=?",
                       (json.dumps(event), decision_id))
        status, payload = self.failed_get(self.study_path(decision_id))
        self.assertEqual(status, 500)
        self.assertEqual(payload, {"status": "failed",
                                   "error": "Stored decision evidence is invalid."})

    def test_browser_selection_has_hand_and_generation_guards(self):
        source = (Path(__file__).resolve().parents[1] / "pokerlab" / "web" / "app.js").read_text()
        self.assertIn("activeHandId!==handId||selectedDecisionId!==decisionId||generation!==selectionGeneration", source)
        self.assertIn("if(!game?.done)invalidateDecisionStudy()", source)
        self.assertIn("showDecisionStudy(data.decisions,", source)
        self.assertIn("${esc(active.answer)}", source)

    def test_action_response_is_scoped_to_hand_and_current_blind_toggle(self):
        source = (Path(__file__).resolve().parents[1] / "pokerlab" / "web" / "app.js").read_text()
        self.assertIn("const actingHandId=activeHandId,actingHandGeneration=handGeneration,actingGame=game", source)
        guard = "activeHandId!==actingHandId||handGeneration!==actingHandGeneration"
        self.assertGreaterEqual(source.count(guard), 2)
        self.assertIn("b.disabled=!game||game.done||!game.legal?.[action]", source)
        self.assertIn("showCoach($('#coach-toggle').checked?g.coach:null,g.decision)", source)
        self.assertIn("Live coaching was not requested for this decision.", source)
        self.assertIn("showCoach(latestCoachResult,latestCoachDecision);showDecisionStudy", source)

    def test_external_coach_opt_in_names_included_and_excluded_facts(self):
        root = Path(__file__).resolve().parents[1]
        source = (root / "pokerlab" / "web" / "app.js").read_text()
        setup = (root / "docs" / "ai-coach-setup.md").read_text()
        self.assertIn("your question, up to two recent questions about this same decision, hero cards, board", source)
        self.assertIn("Opponent hole cards, deck, names, and notes are excluded", source)
        self.assertIn("includes your hero cards, the board", setup)
        self.assertIn("opponent hole cards, the deck, names, notes", setup)

    def test_coach_reply_guard_binds_current_selection_and_response_evidence(self):
        source = (Path(__file__).resolve().parents[1] / "pokerlab" / "web" / "app.js").read_text()
        start = source.index("function coachRequestSelectionMatches(")
        end = source.index("async function askStudyCoach", start)
        guard = source[start:end]
        for condition in (
            "activeHandId===captured.handId",
            "selectedDecisionId===captured.decisionId",
            "handGeneration===captured.handGeneration",
            "selectionGeneration===captured.generation",
            "binding.hand_id===captured.handId",
            "binding.decision_id===captured.decisionId",
            "binding.evidence_id===captured.evidenceId",
            "binding.state_revision===captured.revision",
        ):
            with self.subTest(condition=condition):
                self.assertIn(condition, guard)

    def test_teaching_note_renders_before_facts_only_for_the_current_reply_binding(self):
        source = (Path(__file__).resolve().parents[1] / "pokerlab" / "web" / "app.js").read_text()
        self.assertIn("function coachTeachingNoteHtml(result)", source)
        self.assertIn("sameCoachBinding(note.binding,result.binding)", source)
        self.assertIn("sameCoachBinding(note.binding,reply.binding)", source)
        self.assertIn("${coachTeachingNoteHtml(result)}${blocks}", source)
        self.assertIn("LOCAL TEACHING NOTE", source)
        self.assertIn("note.supporting_fact_ids", source)
        self.assertIn('<summary>Evidence details</summary>', source)
        self.assertIn("coachFactUnit(fact.unit,result)", source)
        self.assertIn("AI-selected plan", source)
        self.assertIn("Local explanation", source)
        self.assertIn("fallbackMessages[reason]", source)
        self.assertNotIn("external_ai_not_selected:", source)
        self.assertNotIn("<small>Fact ${esc(fact.fact_id)}</small>", source)

    def test_current_unavailable_coach_response_clears_loading_without_reply_binding(self):
        source = (Path(__file__).resolve().parents[1] / "pokerlab" / "web" / "app.js").read_text()
        start = source.index("async function askStudyCoach")
        end = source.index("function showDecisionStudy", start)
        request = source[start:end]
        selection_guard = request.index("if(!coachRequestSelectionMatches(captured))return;")
        unavailable = request.index("result.status==='failed'||result.status==='unavailable'")
        exact_binding = request.index("!coachRequestMatches(captured,result)")
        loading_clear = request.index("coachQuestionLoading=false;", unavailable)
        self.assertLess(selection_guard, unavailable)
        self.assertLess(unavailable, exact_binding)
        self.assertLess(exact_binding, loading_clear)
        self.assertIn("if(!coachRequestSelectionMatches(captured))return;", request)
        self.assertIn("coachQuestionError=result.reason||result.error", request)
        self.assertIn("The answer did not match the selected decision", request)

    def test_follow_up_state_restores_turn_cap_and_recovers_expired_conversations(self):
        source = (Path(__file__).resolve().parents[1] / "pokerlab" / "web" / "app.js").read_text()
        selection = source[source.index("async function selectDecisionStudy"):source.index("function coachRequestSelectionMatches")]
        self.assertIn("coachConversation=coachConversations.get(key)", selection)
        self.assertIn("coachConversationFull=coachConversation.turns.length>=4", selection)
        self.assertIn("coachConversationExpired=false", selection)

        request = source[source.index("async function askStudyCoach"):source.index("function showDecisionStudy")]
        self.assertIn("if(coachQuestionLoading||coachConversationExpired||!studyPayload", request)
        self.assertIn("coachConversationExpired=error.code==='conversation_expired'", request)
        self.assertIn("data-reset-expired-coach", source)
        self.assertIn("if(e.target.closest('[data-reset-expired-coach]'))startNewCoachConversation()", source)
        self.assertIn("coachConversation={key:coachConversation.key,target:coachConversation.target,\n    conversationId:null,turns:[]}", request)
        self.assertIn("coachConversationFull||coachConversationExpired?' disabled':''", source)
        self.assertIn("const controls=coachConversationFull||coachConversationExpired?'':`<div class=\"coach-followups\"", source)

    def test_follow_up_controls_disable_during_a_request(self):
        source = (Path(__file__).resolve().parents[1] / "pokerlab" / "web" / "app.js").read_text()
        turn_list = source[source.index("function coachTurnListHtml"):source.index("function coachQuestionHtml")]
        self.assertEqual(turn_list.count("${coachQuestionLoading?' disabled':''}"), 2)
        self.assertIn("if(coachQuestionLoading||coachConversationExpired)return", source[source.index("$('#decision-study').addEventListener('click'"):])


if __name__ == "__main__":
    unittest.main()
