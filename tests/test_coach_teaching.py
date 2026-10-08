"""Tests for application-authored notes grounded in rendered coach facts."""
from dataclasses import replace
import unittest

from pokerlab.coach_analysis import adapt_practice_analysis
from pokerlab.coach_grounding import (CoachReplyPlan, build_grounding_bundle,
                                      render_coach_reply)
from pokerlab.coach_teaching import build_teaching_note
from pokerlab.contracts import CoachDecisionRef
from pokerlab.game import Game
from pokerlab.practice import analyze_decision


def choice_for(analysis):
    legal = next(item for item in analysis.legal_actions if item.name == "call")
    choice = {"name": "call", "amount": int(legal.amount),
              "amount_semantics": "chips_added", "assessed_modeled_action_id": "call",
              "assessment_status": "assessed",
              "ev_loss": max(0.0, next(item.value for item in analysis.action_evs
                                       if item.action_id == analysis.recommended_action_id)
                             - next(item.value for item in analysis.action_evs
                                    if item.action_id == "call"))}
    return choice


def fixture(seed=61):
    game = Game([30, 30], seed=seed)
    analysis = adapt_practice_analysis(
        analyze_decision(game),
        ref=CoachDecisionRef("teaching-hand", f"teaching-decision-{seed}", len(game.log)),
    )
    choice = choice_for(analysis)
    return analysis, choice, build_grounding_bundle(analysis, choice)


def plan(bundle, intent, target=None, detail="normal", fact_ids=()):
    return CoachReplyPlan(bundle.binding, intent, fact_ids, target, detail, "standard")


def replace_fact(bundle, kind, value, availability=None):
    facts = tuple(replace(fact, value=value,
                          availability=availability or fact.availability)
                  if fact.kind == kind else fact for fact in bundle.facts)
    return replace(bundle, facts=facts)


def change_source(bundle, source_kind):
    facts = tuple(replace(fact, value=source_kind)
                  if fact.kind == "source_kind" else fact for fact in bundle.facts)
    return replace(bundle, source_kind=source_kind, facts=facts)


class CoachTeachingTests(unittest.TestCase):
    def setUp(self):
        self.analysis, self.choice, self.bundle = fixture()

    def test_recommendation_note_is_source_limited_and_uses_exact_visible_citations(self):
        reply = render_coach_reply(self.bundle, plan(self.bundle, "recommendation", detail="short"))
        note = build_teaching_note(self.bundle, reply)
        self.assertEqual(note.template_id, "recommendation_scope_v1")
        self.assertEqual(note.source_label, "Practice estimate")
        self.assertIn("practice estimate", note.text.lower())
        self.assertIn("not equilibrium strategy", note.text.lower())
        self.assertTrue(set(note.supporting_fact_ids).issubset(
            {fact.fact_id for block in reply.blocks for fact in block.facts}))
        self.assertFalse(any(next(fact for fact in self.bundle.facts
                                  if fact.fact_id == fact_id).kind == "board"
                             for fact_id in note.supporting_fact_ids))
        self.assertEqual(note.to_dict()["schema_version"], 1)

    def test_optional_supporting_facts_do_not_change_teaching_prerequisites(self):
        short_recommendation = render_coach_reply(
            self.bundle, plan(self.bundle, "recommendation", detail="short"))
        baseline_note = build_teaching_note(self.bundle, short_recommendation)
        recommendation = next(fact for fact in self.bundle.facts
                              if fact.kind == "recommendation")
        unrelated_ev = next(fact for fact in self.bundle.facts
                            if fact.kind == "action_ev" and fact.value[0] != recommendation.value)
        cited_recommendation = render_coach_reply(
            self.bundle, plan(self.bundle, "recommendation", detail="short",
                              fact_ids=(unrelated_ev.fact_id,)))
        cited_note = build_teaching_note(self.bundle, cited_recommendation)
        self.assertTrue(any(block.kind == "supporting" for block in cited_recommendation.blocks))
        self.assertEqual(cited_note, baseline_note)

        short_limits = render_coach_reply(self.bundle, plan(self.bundle, "limits", detail="short"))
        baseline_limits = build_teaching_note(self.bundle, short_limits)
        diagnostic = replace_fact(self.bundle, "solver_iterations", 500, "available")
        diagnostic_fact = next(fact for fact in diagnostic.facts
                               if fact.kind == "solver_iterations")
        cited_limits = render_coach_reply(
            diagnostic, plan(diagnostic, "limits", detail="short",
                             fact_ids=(diagnostic_fact.fact_id,)))
        self.assertEqual(build_teaching_note(diagnostic, cited_limits), baseline_limits)

    def test_assessed_and_unassessed_choice_notes_do_not_transfer_raise_values(self):
        assessed = render_coach_reply(self.bundle, plan(self.bundle, "choice"))
        assessed_note = build_teaching_note(self.bundle, assessed)
        self.assertIn("saved loss", assessed_note.text)
        self.assertIn("choice_loss", {fact.kind for fact in self.bundle.facts
                                      if fact.fact_id in assessed_note.supporting_fact_ids})

        legal_raise = next(item for item in self.analysis.legal_actions if item.name == "raise")
        if legal_raise.maximum_total <= legal_raise.minimum_total:
            self.skipTest("Synthetic stack does not allow a larger legal raise.")
        larger = int(legal_raise.minimum_total) + 1
        unassessed_choice = {"name": "raise", "amount": larger,
                             "amount_semantics": "street_total",
                             "assessed_modeled_action_id": None,
                             "assessment_status": "unassessed_size", "ev_loss": None}
        unassessed_bundle = build_grounding_bundle(self.analysis, unassessed_choice)
        unassessed = render_coach_reply(unassessed_bundle, plan(unassessed_bundle, "choice"))
        note = build_teaching_note(unassessed_bundle, unassessed)
        self.assertEqual(note.template_id, "choice_unassessed_raise_v1")
        self.assertIn("not assessed", note.text)
        self.assertIn("not assigned", note.text)

    def test_compare_note_cites_both_saved_estimates_without_calculating_a_delta(self):
        target = next(item.action_id for item in self.analysis.modeled_actions
                      if item.action_id != self.choice["assessed_modeled_action_id"])
        reply = render_coach_reply(self.bundle, plan(self.bundle, "compare", target))
        note = build_teaching_note(self.bundle, reply)
        self.assertEqual(note.template_id, "comparison_shared_basis_v1")
        self.assertIn("same saved basis", note.text)
        self.assertIn("does not calculate", note.text)
        cited = [fact for fact in self.bundle.facts if fact.fact_id in note.supporting_fact_ids]
        self.assertEqual(sum(fact.kind == "action_ev" for fact in cited), 2)
        self.assertTrue(all(fact.unit == self.bundle.ev_basis for fact in cited
                            if fact.kind == "action_ev"))

    def test_limits_separate_present_diagnostics_and_omit_absent_diagnostics(self):
        practice_reply = render_coach_reply(self.bundle, plan(self.bundle, "limits"))
        practice_note = build_teaching_note(self.bundle, practice_reply)
        self.assertIn("practice estimate", practice_note.text.lower())
        self.assertNotIn("solver-gap diagnostics", practice_note.text)

        diagnostic = replace_fact(self.bundle, "equity_standard_error", 0.03, "available")
        diagnostic = replace_fact(diagnostic, "solver_nash_conv", 0.2, "available")
        diagnostic = replace_fact(diagnostic, "solver_exploitability", 0.1, "available")
        diagnostic = replace_fact(diagnostic, "solver_iterations", 500, "available")
        diagnostic = replace_fact(diagnostic, "solver_gap_semantics", "synthetic diagnostic", "available")
        diagnostic_reply = render_coach_reply(diagnostic, plan(diagnostic, "limits"))
        diagnostic_note = build_teaching_note(diagnostic, diagnostic_reply)
        self.assertIn("reports a standard error", diagnostic_note.text)
        self.assertIn("Solver-gap diagnostics", diagnostic_note.text)
        self.assertIn("separate measures", diagnostic_note.text)

        exact = replace_fact(self.bundle, "equity_exact", True, "available")
        exact = replace_fact(exact, "equity_standard_error", None, "unavailable")
        exact_reply = render_coach_reply(exact, plan(exact, "limits"))
        exact_note = build_teaching_note(exact, exact_reply)
        self.assertIn("marked exact", exact_note.text)
        self.assertNotIn("sampling uncertainty", exact_note.text)
        self.assertNotIn("standard error", exact_note.text)

    def test_opponent_uncertainty_without_assumptions_is_not_described_as_used(self):
        bundle = replace_fact(self.bundle, "opponent_uncertainty",
                              (0.2, 0.8, 0.95, "synthetic interval", "synthetic method"),
                              "available")
        self.assertFalse(any(fact.kind == "opponent_assumption" for fact in bundle.facts))
        reply = render_coach_reply(bundle, plan(bundle, "limits"))
        note = build_teaching_note(bundle, reply)
        self.assertIn("Opponent-model uncertainty", note.text)
        self.assertNotIn("opponent assumptions are model inputs", note.text)

    def test_iterations_only_diagnostic_does_not_claim_solver_gap(self):
        bundle = self.bundle
        for kind in ("solver_nash_conv", "solver_exploitability", "solver_gap_semantics"):
            bundle = replace_fact(bundle, kind, None, "unavailable")
        bundle = replace_fact(bundle, "solver_iterations", 500, "available")
        reply = render_coach_reply(bundle, plan(bundle, "limits"))
        note = build_teaching_note(bundle, reply)
        self.assertIn("Solver iteration count", note.text)
        self.assertNotIn("Solver-gap diagnostics", note.text)

    def test_source_scope_and_opponent_assumptions_are_not_claimed_as_truth(self):
        for source, label, expected in (
            ("restricted_equilibrium", "Restricted equilibrium result", "restricted equilibrium model"),
            ("restricted_exploit", "Restricted exploit estimate", "restricted exploit estimate"),
        ):
            with self.subTest(source=source):
                bundle = change_source(self.bundle, source)
                reply = render_coach_reply(bundle, plan(bundle, "limits"))
                note = build_teaching_note(bundle, reply)
                self.assertEqual(note.source_label, label)
                self.assertIn(expected, note.text)
        game = Game([30, 30], seed=71)
        raw = analyze_decision(game)
        inputs = raw["analysis_inputs"]
        metric = {"mean": inputs["fold_to_bet"], "confidence": "moderate",
                  "observations": 12, "interval95": [.25, .65],
                  "interval_method": "beta test interval"}
        inputs["opponent_model_snapshot"] = {
            "opponent_id": "private-id", "prior_archetype": "private-profile",
            "street": inputs["street"], "model_version": inputs["opponent_model_version"],
            "metrics": {"fold_to_bet": metric},
        }
        analysis = adapt_practice_analysis(
            raw, ref=CoachDecisionRef("teaching-hand", "teaching-opponent", len(game.log)))
        exploit = change_source(build_grounding_bundle(analysis, choice_for(analysis)),
                                "restricted_exploit")
        assumption = next(fact for fact in exploit.facts if fact.kind == "opponent_assumption")
        exploit_reply = render_coach_reply(exploit, plan(exploit, "limits"))
        exploit_note = build_teaching_note(exploit, exploit_reply)
        self.assertIn(assumption.fact_id, exploit_note.supporting_fact_ids)
        self.assertIn("not verified facts", exploit_note.text)

    def test_unavailable_notes_name_only_a_server_marker_and_never_offer_a_substitute(self):
        missing = replace_fact(self.bundle, "recommendation", None, "unavailable")
        missing = replace(missing, unavailable_fields=tuple(dict.fromkeys(
            (*missing.unavailable_fields, "recommendation"))))
        reply = render_coach_reply(missing, plan(missing, "recommendation"))
        note = build_teaching_note(missing, reply)
        self.assertEqual(note.template_id, "unavailable_recommendation_v1")
        self.assertIn("marker: recommendation", note.text)
        self.assertNotIn("try", note.text.lower())

        generic = render_coach_reply(self.bundle, plan(self.bundle, "unavailable"))
        generic_note = build_teaching_note(self.bundle, generic)
        self.assertEqual(generic_note.template_id, "unavailable_request_v1")
        self.assertNotIn("marker:", generic_note.text)

    def test_choice_unavailability_uses_its_own_marker_not_bundle_comparison_markers(self):
        no_choice = replace(
            self.bundle,
            facts=tuple(fact for fact in self.bundle.facts if fact.kind != "choice"),
            unavailable_fields=("comparison_ev",),
        )
        reply = render_coach_reply(no_choice, plan(no_choice, "choice"))
        self.assertEqual(reply.intent, "unavailable")
        self.assertIn("choice", reply.unavailable_fields)
        self.assertIn("comparison_ev", reply.unavailable_fields)
        note = build_teaching_note(no_choice, reply)
        self.assertEqual(note.template_id, "unavailable_choice_v1")
        self.assertIn("marker: choice", note.text)
        self.assertNotIn("requested comparison", note.text)

    def test_unassessed_comparison_is_cited_without_any_substitute_ev(self):
        legal_raise = next(item for item in self.analysis.legal_actions if item.name == "raise")
        if legal_raise.maximum_total <= legal_raise.minimum_total:
            self.skipTest("Synthetic stack does not allow a larger legal raise.")
        larger = int(legal_raise.minimum_total) + 1
        choice = {"name": "raise", "amount": larger, "amount_semantics": "street_total",
                  "assessed_modeled_action_id": None, "assessment_status": "unassessed_size",
                  "ev_loss": None}
        bundle = build_grounding_bundle(self.analysis, choice)
        target = next(item.action_id for item in self.analysis.modeled_actions
                      if item.name != "raise")
        reply = render_coach_reply(bundle, plan(bundle, "compare", target))
        note = build_teaching_note(bundle, reply)
        self.assertEqual(note.template_id, "unavailable_choice_v1")
        self.assertIn("choice_action_not_modeled", note.text)
        self.assertFalse(any(fact.kind in {"action_ev", "baseline_action_ev"}
                             for block in reply.blocks for fact in block.facts))
        self.assertEqual({fact.kind for fact in reply.blocks[0].facts}, {"choice"})

    def test_cross_binding_and_tampered_rendered_fact_fail_closed(self):
        reply = render_coach_reply(self.bundle, plan(self.bundle, "recommendation"))
        other_binding = replace(self.bundle.binding, decision_id="another-decision")
        self.assertIsNone(build_teaching_note(
            self.bundle, replace(reply, binding=other_binding)))
        first = reply.blocks[0]
        tampered_fact = replace(first.facts[0], value="invented")
        tampered = replace(reply, blocks=(replace(first, facts=(tampered_fact, *first.facts[1:])),))
        self.assertIsNone(build_teaching_note(self.bundle, tampered))


if __name__ == "__main__":
    unittest.main()
