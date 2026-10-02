import unittest

from pokerlab.contracts import (ActionFrequency, ActionValue, OpponentAssumption,
                                StrategyAnalysisResult, TendencyContext, Uncertainty)
from pokerlab.explanations import explain
from pokerlab.personalities import (CoachPersonality, OptionalAIAdapter,
                                    explanation_fingerprint, render_personality)


class PersonalityTests(unittest.TestCase):
    def setUp(self):
        uncertainty = Uncertainty(.25, .55, .95, "beta interval", "moderate")
        assumption = OpponentAssumption(
            "fold_to_bet", TendencyContext("river", "button", "facing_bet"),
            .4, 20, uncertainty)
        analysis = StrategyAnalysisResult(
            "analysis-personality", ("fold", "call", "raise"),
            (ActionFrequency("fold", .4), ActionFrequency("call", .4),
             ActionFrequency("raise", .2)),
            (ActionFrequency("fold", .6), ActionFrequency("call", .3),
             ActionFrequency("raise", .1)),
            (ActionValue("fold", 0), ActionValue("call", -2),
             ActionValue("raise", -8)),
            (ActionValue("fold", 0), ActionValue("call", -2),
             ActionValue("raise", -8)),
            (assumption,), "moderate", uncertainty, "solver-v1", "model-v1")
        self.explanation = explain(analysis, "fold")

    def test_every_personality_preserves_protected_facts_and_analysis_id(self):
        fingerprint = explanation_fingerprint(self.explanation)
        for personality in CoachPersonality:
            with self.subTest(personality=personality):
                rendered = render_personality(self.explanation, personality)
                self.assertIs(rendered.explanation, self.explanation)
                self.assertEqual(rendered.analysis_id, self.explanation.analysis_id)
                self.assertEqual(rendered.facts_fingerprint, fingerprint)
                self.assertEqual(rendered.explanation.recommended_action, "fold")
                self.assertEqual(rendered.explanation.action_evs,
                                 self.explanation.action_evs)
                self.assertEqual(rendered.explanation.exploitative_strategy,
                                 self.explanation.exploitative_strategy)
                self.assertEqual(rendered.explanation.confidence, "moderate")
                self.assertEqual(rendered.explanation.evidence,
                                 self.explanation.evidence)

    def test_personalities_change_presentation(self):
        texts = {render_personality(self.explanation, item).text
                 for item in CoachPersonality}
        self.assertEqual(len(texts), len(CoachPersonality))

    def test_bluffer_concedes_when_aggression_is_wrong(self):
        text = render_personality(
            self.explanation, CoachPersonality.CHRONIC_BLUFFER).text.casefold()
        self.assertIn("do not support", text)
        self.assertIn("fold", text)

    def test_offline_default_needs_no_provider_or_api_key(self):
        rendered = OptionalAIAdapter().render(self.explanation, "grinder")
        self.assertEqual(rendered.source, "deterministic")

    def test_disabled_adapter_never_calls_provider(self):
        class ExplodingProvider:
            def explain(self, payload, personality):
                raise AssertionError("provider should not be called")
        OptionalAIAdapter(ExplodingProvider()).render(self.explanation, "nit")

    def test_optional_provider_can_only_replace_text(self):
        class Provider:
            def explain(self, payload, personality):
                self.payload = payload
                return "Provider-written presentation."
        provider = Provider()
        rendered = OptionalAIAdapter(provider, enabled=True).render(
            self.explanation, "math_guy")
        self.assertEqual(rendered.text, "Provider-written presentation.")
        self.assertIs(rendered.explanation, self.explanation)
        self.assertEqual(rendered.facts_fingerprint,
                         explanation_fingerprint(self.explanation))
        self.assertEqual(provider.payload["recommended_action"], "fold")

    def test_provider_cannot_return_overwritten_fields(self):
        class MaliciousProvider:
            def explain(self, payload, personality):
                return {"recommended_action": "raise", "text": "Do it"}
        with self.assertRaises(TypeError):
            OptionalAIAdapter(MaliciousProvider(), enabled=True).render(
                self.explanation, "chronic_bluffer")


if __name__ == "__main__":
    unittest.main()
