"""Contract and adapter tests for solver-grounded coach evidence."""
import copy
import json
import unittest
from dataclasses import FrozenInstanceError

from pokerlab.coach_analysis import (COACH_PRACTICE_ADAPTER_VERSION,
                                     adapt_practice_analysis)
from pokerlab.contracts import (CoachAnalysisError, CoachDecisionAnalysis,
                                CoachDecisionContext, CoachDecisionRef)
from pokerlab.game import Game
from pokerlab.practice import analyze_decision


def sample(seed=7, stacks=None):
    game = Game(stacks or [30, 30], seed=seed)
    analysis = analyze_decision(game)
    return game, analysis


def adapted(game, analysis, ref=None):
    ref = ref or CoachDecisionRef("hand-test", "decision-test", len(game.log))
    return adapt_practice_analysis(analysis, ref=ref)


class CoachAnalysisTests(unittest.TestCase):
    def test_real_practice_analysis_is_labeled_as_estimate(self):
        game, raw = sample()
        result = adapted(game, raw)
        self.assertEqual(result.source_kind, "practice_estimate")
        self.assertEqual(result.ev_basis, "incremental_decision_chips")
        self.assertEqual(result.analysis_id, raw["analysis_id"])
        self.assertEqual(result.adapter_version, COACH_PRACTICE_ADAPTER_VERSION)
        self.assertEqual(result.quality.equity_exact, raw["equity"]["exact"])
        self.assertEqual(result.quality.equity_standard_error, raw["equity"]["standard_error"])
        self.assertIsNone(result.quality.nash_conv)
        self.assertIsNone(result.quality.exploitability)
        self.assertIsNone(result.quality.iterations)
        self.assertEqual(result.reference_policy.kind, "illustrative_argmax")
        self.assertEqual(result.modeled_policy.kind, "estimate_argmax")
        self.assertTrue(all(item.origin != "solver_output" for item in result.provenance))
        self.assertTrue(any("not equilibrium solver output" in item for item in result.limitations))

    def test_ev_values_and_non_argmax_recommendations_are_copied(self):
        game, raw = sample()
        raw["recommended"] = "fold"
        raw["baseline_recommended"] = "call"
        result = adapted(game, raw)
        self.assertEqual(result.recommended_action_id, "fold")
        self.assertEqual(result.baseline_recommended_action_id, "call")
        self.assertEqual({item.action_id: item.value for item in result.action_evs},
                         {"fold": raw["actions"]["fold"],
                          "call": raw["actions"]["call"],
                          "raise:min": raw["actions"]["raise"]})
        frequencies = {item.action: item.frequency for item in result.modeled_policy.frequencies}
        self.assertEqual(frequencies["fold"], 1)
        self.assertEqual(sum(frequencies.values()), 1)

    def test_legal_raise_interval_is_distinct_from_minimum_raise_estimate(self):
        game, raw = sample(stacks=[30, 30])
        result = adapted(game, raw)
        legal_raise = next(item for item in result.legal_actions if item.name == "raise")
        modeled_raise = next(item for item in result.modeled_actions if item.name == "raise")
        self.assertIsNone(legal_raise.amount)
        self.assertEqual(legal_raise.amount_semantics, "street_total")
        self.assertEqual((legal_raise.minimum_total, legal_raise.maximum_total),
                         (game.legal()["raise_min"], game.legal()["raise_max"]))
        self.assertEqual(modeled_raise.action_id, "raise:min")
        self.assertEqual(modeled_raise.amount, game.legal()["raise_min"])
        self.assertIsNone(modeled_raise.minimum_total)
        self.assertIsNone(modeled_raise.maximum_total)

    def test_short_all_in_without_raise_does_not_claim_raise_analysis(self):
        game, raw = sample(stacks=[2, 200])
        self.assertFalse(game.legal()["raise"])
        result = adapted(game, raw)
        self.assertNotIn("raise", [item.name for item in result.legal_actions])
        self.assertNotIn("raise:min", [item.action_id for item in result.modeled_actions])
        self.assertEqual({item.action_id for item in result.action_evs}, {"fold", "call"})

    def test_multiplayer_ranges_are_kept_without_exposing_opponent_cards(self):
        game, raw = sample(seed=9, stacks=[30, 30, 20])
        result = adapted(game, raw)
        self.assertEqual(result.opponent_ranges, ("random", "random"))
        self.assertEqual(result.context.hero_cards, tuple(game.hands[game.actor]))
        self.assertNotIn("PRIVATE", result.to_json())
        self.assertNotIn("hands", result.to_dict())
        self.assertNotIn("seed", result.to_dict())

    def test_consumed_opponent_fact_carries_matching_uncertainty_and_count(self):
        game, raw = sample()
        inputs = raw["analysis_inputs"]
        metric = {"mean": inputs["fold_to_bet"], "confidence": "moderate",
                  "observations": 12, "interval95": [.25, .65],
                  "interval_method": "beta test interval"}
        inputs["opponent_id"] = "PRIVATE OPPONENT ID"
        inputs["opponent_model_snapshot"] = {
            "opponent_id": "PRIVATE SNAPSHOT ID", "prior_archetype": "PRIVATE PROFILE",
            "street": inputs["street"], "model_version": inputs["opponent_model_version"],
            "metrics": {"fold_to_bet": metric, "notes": "PRIVATE NOTE"}}
        result = adapted(game, raw)
        assumption, = result.opponent_assumptions
        self.assertEqual(assumption.tendency_id, "fold_to_bet")
        self.assertEqual(assumption.value, inputs["fold_to_bet"])
        self.assertEqual(assumption.evidence_count, 12)
        self.assertEqual(assumption.uncertainty.method, "beta test interval")
        encoded = result.to_json()
        for private in ("PRIVATE OPPONENT ID", "PRIVATE SNAPSHOT ID", "PRIVATE PROFILE", "PRIVATE NOTE"):
            self.assertNotIn(private, encoded)

    def test_opponent_assumption_is_omitted_when_raise_is_not_modeled(self):
        game, raw = sample(stacks=[2, 200])
        inputs = raw["analysis_inputs"]
        inputs["opponent_model_snapshot"] = {"poison": "must not escape"}
        result = adapted(game, raw)
        self.assertEqual(result.opponent_assumptions, ())
        self.assertIsNone(result.quality.opponent_uncertainty)
        self.assertNotIn("poison", result.to_json())

    def test_mismatched_snapshot_or_consumed_rate_fails_closed(self):
        for mismatch in ("street", "value"):
            game, raw = sample()
            inputs = raw["analysis_inputs"]
            mean = inputs["fold_to_bet"] if mismatch != "value" else .2
            inputs["opponent_model_snapshot"] = {
                "street": "river" if mismatch == "street" else inputs["street"],
                "model_version": inputs["opponent_model_version"],
                "metrics": {"fold_to_bet": {"mean": mean, "confidence": "moderate",
                    "observations": 1, "interval95": [.1, .8], "interval_method": "test"}}}
            with self.subTest(mismatch=mismatch), self.assertRaises(CoachAnalysisError):
                adapted(game, raw)

    def test_json_round_trip_preserves_all_fields_and_immutable_values(self):
        game, raw = sample()
        result = adapted(game, raw)
        decoded = CoachDecisionAnalysis.from_json(result.to_json())
        self.assertEqual(decoded, result)
        self.assertIsInstance(decoded.context.hero_cards, tuple)
        self.assertIsInstance(decoded.opponent_ranges, tuple)
        self.assertEqual(decoded.evidence_id, result.evidence_id)
        with self.assertRaises(FrozenInstanceError):
            decoded.context.pot = 0
        exported = result.to_dict()
        exported["context"]["hero_cards"].clear()
        self.assertEqual(len(result.context.hero_cards), 2)
        raw["analysis_inputs"]["known_cards"].clear()
        self.assertEqual(len(result.context.hero_cards), 2)

    def test_evidence_id_ignores_locator_but_covers_protected_facts(self):
        game, raw = sample()
        first = adapted(game, raw, CoachDecisionRef("h1", "d1", 1))
        second = adapted(game, raw, CoachDecisionRef("h2", "d2", 42))
        self.assertEqual(first.evidence_id, second.evidence_id)
        changed = first.to_dict()
        changed["quality"]["confidence_label"] = "edited"
        with self.assertRaises(CoachAnalysisError) as caught:
            CoachDecisionAnalysis.from_dict(changed)
        self.assertEqual(caught.exception.code, "fingerprint_mismatch")

    def test_dictionary_order_and_action_map_order_do_not_change_evidence(self):
        game, raw = sample()
        first = adapted(game, raw)
        reordered = copy.deepcopy(raw)
        reordered["actions"] = dict(reversed(list(reordered["actions"].items())))
        reordered["baseline_actions"] = dict(reversed(list(reordered["baseline_actions"].items())))
        reordered = dict(reversed(list(reordered.items())))
        second = adapted(game, reordered)
        self.assertEqual(first.evidence_id, second.evidence_id)
        self.assertEqual([item.action_id for item in first.action_evs],
                         [item.action_id for item in second.action_evs])

    def test_provenance_resolves_and_attributes_each_material_fact(self):
        game, raw = sample()
        result = adapted(game, raw)
        pointers = {item.path for item in result.provenance}
        self.assertIn("/context/hero_cards/0", pointers)
        self.assertIn("/action_evs/0/value", pointers)
        self.assertIn("/modeled_actions/2/amount", pointers)
        self.assertIn("/quality/equity_standard_error", pointers)
        self.assertIn("/recommended_action_id", pointers)
        self.assertEqual(len(pointers), len(result.provenance))

    def test_unsupported_versions_and_malformed_action_state_have_safe_codes(self):
        game, raw = sample()
        broken = copy.deepcopy(raw)
        broken["analysis_version"] = "practice-ev-v0"
        with self.assertRaises(CoachAnalysisError) as caught:
            adapted(game, broken)
        self.assertEqual(caught.exception.code, "unsupported_producer_version")
        for mutate in (
            lambda data: data["analysis_inputs"].update(pot=float("nan")),
            lambda data: data["analysis_inputs"].update(actor=True),
            lambda data: data["analysis_inputs"].update(public_cards=["As"]),
            lambda data: data["analysis_inputs"].update(committed=[1]),
            lambda data: data["actions"].update(unknown=0),
        ):
            game, source = sample()
            broken = copy.deepcopy(source)
            mutate(broken)
            with self.assertRaises(CoachAnalysisError):
                adapted(game, broken)

    def test_equity_boolean_and_model_counts_are_strict(self):
        game, raw = sample()
        broken = copy.deepcopy(raw)
        broken["equity"]["exact"] = 1
        with self.assertRaises(CoachAnalysisError):
            adapted(game, broken)
        game, raw = sample()
        raw["analysis_inputs"]["opponent_model_snapshot"] = {
            "street": raw["analysis_inputs"]["street"],
            "model_version": raw["analysis_inputs"]["opponent_model_version"],
            "metrics": {"fold_to_bet": {"mean": raw["analysis_inputs"]["fold_to_bet"],
                 "confidence": "low", "observations": True, "interval95": [.1, .8],
                 "interval_method": "test"}}}
        with self.assertRaises(CoachAnalysisError):
            adapted(game, raw)

    def test_raw_extra_personal_fields_are_ignored(self):
        game, raw = sample()
        raw.update(display_name="PRIVATE NAME", notes="PRIVATE NOTE", deck=["PRIVATE DECK"],
                   opponent_cards=["PRIVATE CARDS"], local_path="PRIVATE PATH", seed=888)
        raw["analysis_inputs"]["top_level_poison"] = "PRIVATE INPUT"
        result = adapted(game, raw)
        encoded = result.to_json()
        for private in ("PRIVATE NAME", "PRIVATE NOTE", "PRIVATE DECK", "PRIVATE CARDS",
                        "PRIVATE PATH", "PRIVATE INPUT", "888"):
            self.assertNotIn(private, encoded)

    def test_round_trip_rejects_unknown_schema_and_fields(self):
        game, raw = sample()
        exported = adapted(game, raw).to_dict()
        for key, value in (("schema_version", 2), ("unexpected", True)):
            broken = copy.deepcopy(exported)
            broken[key] = value
            with self.assertRaises(CoachAnalysisError):
                CoachDecisionAnalysis.from_dict(broken)
        broken = copy.deepcopy(exported)
        broken["modeled_actions"][0]["other"] = "untrusted"
        with self.assertRaises(CoachAnalysisError):
            CoachDecisionAnalysis.from_dict(broken)

    def test_direct_contract_rejects_mutable_inputs_and_invalid_revision(self):
        with self.assertRaises(CoachAnalysisError):
            CoachDecisionRef("h", "d", True)
        with self.assertRaises(CoachAnalysisError):
            CoachDecisionContext("preflop", ["As", "Kh"], (), 0,
                                 "current_committed", 0, None, 0,
                                 (1, 1), (1, 1), (1, 1), 1, 2)

    def test_bad_provenance_pointer_is_rejected(self):
        game, raw = sample()
        result = adapted(game, raw)
        broken = result.to_dict()
        broken["provenance"][0]["path"] = "/does/not/exist"
        # Use the original fingerprint so pointer validation is the failing guard.
        with self.assertRaises(CoachAnalysisError) as caught:
            CoachDecisionAnalysis.from_dict(broken)
        self.assertEqual(caught.exception.code, "invalid_contract")


if __name__ == "__main__":
    unittest.main()

