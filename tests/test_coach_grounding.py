"""Tests for the provider-safe facts and deterministic reply-plan boundary."""
from dataclasses import FrozenInstanceError, fields
import hashlib
import json
import unittest
from unittest.mock import patch

from pokerlab.coach_analysis import adapt_practice_analysis
from pokerlab.coach_grounding import (
    CoachGroundingError, CoachReplyPlan, GroundFact, GroundingBinding,
    GroundingBundle, build_grounding_bundle, render_coach_reply,
    validate_coach_reply_plan,
)
from pokerlab.contracts import CoachActionValue, CoachDecisionAnalysis, CoachDecisionRef
from pokerlab.game import Game
from pokerlab.practice import analyze_decision


def sample_analysis(decision_id="decision-grounding", seed=61):
    game = Game([30, 30], seed=seed)
    raw = analyze_decision(game)
    ref = CoachDecisionRef("synthetic-hand", decision_id, len(game.log))
    return adapt_practice_analysis(raw, ref=ref)


def sample_choice(analysis, name="call", amount=None):
    legal = next(item for item in analysis.legal_actions if item.name == name)
    if name == "raise":
        amount = int(legal.minimum_total if amount is None else amount)
        assessed = amount == legal.minimum_total
        action_id = "raise:min" if assessed else None
        status = "assessed" if assessed else "unassessed_size"
    else:
        amount = int(legal.amount)
        action_id = name
        status = "assessed"
    loss = None
    if status == "assessed":
        values = {item.action_id: item.value for item in analysis.action_evs}
        loss = max(0.0, values[analysis.recommended_action_id] - values[action_id])
    return {"name": name, "amount": amount,
            "amount_semantics": "street_total" if name == "raise" else "chips_added",
            "assessed_modeled_action_id": action_id,
            "assessment_status": status, "ev_loss": loss}


def new_plan(bundle, intent, *, target_action_id=None, fact_ids=(), detail="normal",
             audience="standard"):
    return CoachReplyPlan(bundle.binding, intent, tuple(fact_ids), target_action_id,
                          detail, audience)


class CoachGroundingTests(unittest.TestCase):
    def setUp(self):
        self.analysis = sample_analysis()
        self.choice = sample_choice(self.analysis)
        self.bundle = build_grounding_bundle(self.analysis, self.choice)

    def test_versioned_round_trips_are_canonical_and_values_are_immutable_copies(self):
        encoded = self.bundle.to_json()
        restored = GroundingBundle.from_json(encoded)
        self.assertEqual(restored, self.bundle)
        self.assertEqual(restored.to_json(), encoded)
        fact = next(item for item in self.bundle.facts if item.kind == "hero_cards")
        self.assertIsInstance(fact.value, tuple)
        with self.assertRaises(FrozenInstanceError):
            fact.value = ("2c", "3c")
        exported = self.bundle.to_dict()
        exported_fact = next(item for item in exported["facts"] if item["kind"] == "hero_cards")
        exported_fact["value"][0] = "2c"
        self.assertNotEqual(self.bundle.to_dict(), exported)

    def test_fact_ids_bind_full_sha256_to_decision_evidence_and_canonical_pointer(self):
        fact = next(item for item in self.bundle.facts if item.kind == "street")
        expected = "f_" + hashlib.sha256(
            f"{self.analysis.ref.decision_id}\n{self.analysis.evidence_id}\n"
            f"{fact.source_pointer}".encode("utf-8")).hexdigest()
        self.assertEqual(fact.fact_id, expected)
        other = sample_analysis(decision_id="another-decision")
        other_bundle = build_grounding_bundle(other, sample_choice(other))
        other_street = next(item for item in other_bundle.facts if item.kind == "street")
        self.assertEqual(fact.source_pointer, other_street.source_pointer)
        self.assertEqual(self.analysis.evidence_id, other.evidence_id)
        self.assertNotEqual(fact.fact_id, other_street.fact_id)

    def test_projection_is_allowlisted_and_does_not_include_raw_or_identity_data(self):
        encoded = self.bundle.to_json()
        for forbidden in ("opponent_ranges", "opponent_hands", "deck", "seed",
                          "PRIVATE NOTE", "database", "local_path"):
            self.assertNotIn(forbidden, encoded)
        pointers = [fact.source_pointer for fact in self.bundle.facts]
        self.assertTrue(all(pointer.startswith(("/analysis", "/choice")) for pointer in pointers))
        self.assertEqual(self.bundle.binding.hand_id, "synthetic-hand")
        self.assertEqual(self.bundle.binding.decision_id, "decision-grounding")

    def test_choice_validation_rejects_event_fields_and_tampered_loss_before_projection(self):
        for edit in (
            lambda value: value.update(event={"notes": "private"}),
            lambda value: value.update(amount=True),
            lambda value: value.update(name=[]),
            lambda value: value.update(assessment_status=[]),
            lambda value: value.update(amount=value["amount"] + 1),
            lambda value: value.update(ev_loss=99),
        ):
            broken = dict(self.choice)
            edit(broken)
            with self.subTest(broken=broken), self.assertRaises(CoachGroundingError) as caught:
                build_grounding_bundle(self.analysis, broken)
            self.assertEqual(caught.exception.code, "invalid_grounding")

    def test_null_ev_remains_unavailable_while_zero_remains_available(self):
        values = {item.name: getattr(self.analysis, item.name)
                  for item in fields(CoachDecisionAnalysis) if item.name != "evidence_id"}
        first, second = self.analysis.action_evs[:2]
        values["action_evs"] = (
            CoachActionValue(first.action_id, None),
            CoachActionValue(second.action_id, 0.0),
            *self.analysis.action_evs[2:],
        )
        revised = CoachDecisionAnalysis.build(**values)
        selected_choice = sample_choice(revised)
        bundle = build_grounding_bundle(revised, selected_choice)
        evs = {fact.value[0]: fact for fact in bundle.facts if fact.kind == "action_ev"}
        self.assertIsNone(evs[first.action_id].value[1])
        self.assertEqual(evs[first.action_id].availability, "unavailable")
        self.assertEqual(evs[second.action_id].value[1], 0.0)
        self.assertEqual(evs[second.action_id].availability, "available")
        self.assertIn(f"action_ev:{first.action_id}", bundle.unavailable_fields)

    def test_all_five_intents_render_only_server_owned_fact_blocks(self):
        target = next(item.action_id for item in self.analysis.modeled_actions
                      if item.action_id != self.choice["assessed_modeled_action_id"])
        plans = (
            new_plan(self.bundle, "recommendation"),
            new_plan(self.bundle, "choice"),
            new_plan(self.bundle, "compare", target_action_id=target),
            new_plan(self.bundle, "limits"),
            new_plan(self.bundle, "unavailable"),
        )
        replies = [render_coach_reply(self.bundle, plan) for plan in plans]
        self.assertEqual([reply.intent for reply in replies],
                         ["recommendation", "choice", "compare", "limits", "unavailable"])
        self.assertEqual(replies[0].source_label, "Practice estimate")
        self.assertEqual(replies[3].caveats, self.bundle.limitations)
        self.assertEqual(replies[3].blocks[0].caveats, self.bundle.limitations)
        for reply in replies:
            exported = json.dumps(reply.to_dict(), allow_nan=False)
            self.assertNotIn("answer_text", exported)
            self.assertTrue(all(block.label and all(item.fact_id for item in block.facts)
                                for block in reply.blocks))

    def test_plan_citations_are_optional_support_not_required_facts(self):
        recommendation = new_plan(self.bundle, "recommendation")
        cited_plan = new_plan(self.bundle, "recommendation",
                              fact_ids=(next(f.fact_id for f in self.bundle.facts
                                             if f.kind == "board"),))
        base_reply = render_coach_reply(self.bundle, recommendation)
        cited_reply = render_coach_reply(self.bundle, cited_plan)
        self.assertEqual(base_reply.blocks[0].facts, cited_reply.blocks[0].facts)
        self.assertEqual(cited_reply.blocks[-1].kind, "supporting")

    def test_compare_requires_modeled_target_and_same_basis_values(self):
        with self.assertRaises(CoachGroundingError):
            validate_coach_reply_plan(
                new_plan(self.bundle, "compare", target_action_id="raise:999"), self.bundle)
        target = next(item.action_id for item in self.analysis.modeled_actions
                      if item.action_id != self.choice["assessed_modeled_action_id"])
        answer = render_coach_reply(
            self.bundle, new_plan(self.bundle, "compare", target_action_id=target))
        self.assertEqual(answer.intent, "compare")
        self.assertEqual(answer.blocks[0].kind, "comparison")
        ev_facts = [fact for fact in answer.blocks[0].facts
                    if fact.kind == "action_ev"]
        self.assertEqual(len(ev_facts), 2)
        self.assertTrue(all(fact.unit == self.bundle.ev_basis for fact in ev_facts))

    def test_unassessed_raise_and_missing_ev_render_unavailable_without_substitute(self):
        legal_raise = next(item for item in self.analysis.legal_actions if item.name == "raise")
        if legal_raise.maximum_total <= legal_raise.minimum_total:
            self.skipTest("Synthetic stack does not allow a larger legal raise.")
        raised = sample_choice(self.analysis, "raise", int(legal_raise.minimum_total) + 1)
        bundle = build_grounding_bundle(self.analysis, raised)
        target = next(item.action_id for item in self.analysis.modeled_actions
                      if item.name != "raise")
        compare = render_coach_reply(bundle, new_plan(bundle, "compare", target_action_id=target))
        self.assertEqual(compare.intent, "unavailable")
        self.assertEqual(compare.blocks[0].kind, "unavailable")
        self.assertFalse(any(fact.kind == "action_ev" for block in compare.blocks
                             for fact in block.facts))
        choice = render_coach_reply(bundle, new_plan(bundle, "choice"))
        self.assertEqual(choice.intent, "choice")
        choice_facts = choice.blocks[0].facts
        self.assertTrue(any(fact.kind == "choice_loss" and fact.value is None
                            and fact.availability == "unavailable" for fact in choice_facts))

    def test_plan_round_trip_binding_unknown_keys_and_duplicate_ids_fail_closed(self):
        plan = new_plan(self.bundle, "limits", fact_ids=(self.bundle.facts[0].fact_id,))
        self.assertEqual(CoachReplyPlan.from_json(plan.to_json()), plan)
        broken = plan.to_dict()
        broken["freeform_text"] = "call"
        with self.assertRaises(CoachGroundingError) as caught:
            CoachReplyPlan.from_dict(broken)
        self.assertEqual(caught.exception.code, "invalid_reply_plan")
        duplicated = plan.to_dict()
        duplicated["fact_ids"] = [self.bundle.facts[0].fact_id] * 2
        with self.assertRaises(CoachGroundingError):
            validate_coach_reply_plan(CoachReplyPlan.from_dict(duplicated), self.bundle)
        other = sample_analysis(decision_id="other-decision")
        other_bundle = build_grounding_bundle(other, sample_choice(other))
        with self.assertRaises(CoachGroundingError):
            render_coach_reply(other_bundle, plan)

        malformed_binding = plan.to_dict()
        malformed_binding["binding"]["hand_id"] = []
        with self.assertRaises(CoachGroundingError) as caught:
            CoachReplyPlan.from_dict(malformed_binding)
        self.assertEqual(caught.exception.code, "invalid_reply_plan")

    def test_optional_detail_and_audience_do_not_change_saved_recommendation_values(self):
        short = render_coach_reply(
            self.bundle, new_plan(self.bundle, "recommendation", detail="short",
                                  audience="beginner"))
        technical = render_coach_reply(
            self.bundle, new_plan(self.bundle, "recommendation", detail="technical",
                                  audience="standard"))
        short_facts = [(fact.kind, fact.value, fact.unit, fact.availability)
                       for fact in short.blocks[0].facts]
        technical_facts = [(fact.kind, fact.value, fact.unit, fact.availability)
                           for fact in technical.blocks[0].facts
                           if fact.kind in {"recommendation", "modeled_action", "action_ev"}]
        self.assertEqual(short_facts, technical_facts[:len(short_facts)])
        self.assertEqual(short.blocks[0].label, "Saved action")
        self.assertEqual(technical.blocks[0].label, "Saved recommendation")
        self.assertEqual(short.caveats, technical.caveats)

    def test_strict_bundle_reader_rejects_versions_unknown_keys_duplicate_ids_bad_pointers_and_nan(self):
        broken = self.bundle.to_dict()
        broken["schema_version"] = True
        with self.assertRaises(CoachGroundingError):
            GroundingBundle.from_dict(broken)
        broken = self.bundle.to_dict()
        broken["extra"] = 1
        with self.assertRaises(CoachGroundingError):
            GroundingBundle.from_dict(broken)
        broken = self.bundle.to_dict()
        broken["facts"][0]["source_pointer"] = "/event/chosen_action"
        with self.assertRaises(CoachGroundingError):
            GroundingBundle.from_dict(broken)
        duplicate_json = self.bundle.to_json().replace('"schema_version":1',
                                                        '"schema_version":1,"schema_version":1', 1)
        with self.assertRaises(CoachGroundingError):
            GroundingBundle.from_json(duplicate_json)
        non_finite = self.bundle.to_json().replace('"pot"', '"pot"', 1)
        non_finite = non_finite.replace('"value":', '"value":NaN,"ignored":', 1)
        with self.assertRaises(CoachGroundingError):
            GroundingBundle.from_json(non_finite)

    def test_fact_contract_rejects_boolean_numbers_oversized_arrays_and_text(self):
        pointer = "/analysis/context/pot"
        fact_id = "f_" + hashlib.sha256(
            f"{self.bundle.binding.decision_id}\n{self.bundle.binding.evidence_id}\n{pointer}"
            .encode()).hexdigest()
        with self.assertRaises(CoachGroundingError):
            GroundFact(fact_id, "current_pot", pointer, True, "chips", "available")
        with self.assertRaises(CoachGroundingError):
            GroundFact(fact_id, "hero_cards", pointer, tuple(range(17)), "cards", "available")
        with self.assertRaises(CoachGroundingError):
            GroundFact(fact_id, "street", pointer, "x" * 257, "street", "available")

    def test_pure_boundary_does_not_call_solver_store_or_legacy_provider(self):
        with (patch("pokerlab.solver.solve", side_effect=AssertionError("solver called")),
              patch("pokerlab.models.Store", side_effect=AssertionError("store called")),
              patch("pokerlab.personalities.ConversationalExplanationProvider.explain",
                    side_effect=AssertionError("provider called"))):
            bundle = build_grounding_bundle(self.analysis, self.choice)
            reply = render_coach_reply(bundle, new_plan(bundle, "recommendation"))
        self.assertEqual(reply.intent, "recommendation")


if __name__ == "__main__":
    unittest.main()
