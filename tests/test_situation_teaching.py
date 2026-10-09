"""Focused beginner descriptions of facts visible in the hero cards and board."""
from dataclasses import fields, replace
import unittest

from pokerlab.coach_analysis import adapt_practice_analysis
from pokerlab.contracts import CoachDecisionAnalysis, CoachDecisionRef
from pokerlab.game import Game
from pokerlab.practice import analyze_decision
from pokerlab.situation_teaching import build_situation_teaching


def base_analysis():
    game = Game([30, 30], seed=113)
    return adapt_practice_analysis(
        analyze_decision(game),
        ref=CoachDecisionRef("situation-hand", "situation-decision", len(game.log)),
    )


def with_visible_cards(analysis, hero_cards, board):
    values = {item.name: getattr(analysis, item.name)
              for item in fields(CoachDecisionAnalysis) if item.name != "evidence_id"}
    values["context"] = replace(
        analysis.context, hero_cards=hero_cards, board=board,
        street={0: "preflop", 3: "flop", 4: "turn", 5: "river"}[len(board)])
    return CoachDecisionAnalysis.build(**values)


class SituationTeachingTests(unittest.TestCase):
    def setUp(self):
        self.analysis = base_analysis()

    def test_board_pair_is_named_as_board_made_on_flop_turn_and_river(self):
        boards = (
            ("9s", "9h", "Ac"),
            ("9s", "9h", "Ac", "Kd"),
            ("9s", "9h", "Ac", "Kd", "3c"),
        )
        for board in boards:
            with self.subTest(street=len(board)):
                analysis = with_visible_cards(self.analysis, ("7c", "2d"), board)
                text = build_situation_teaching(analysis)["text"]
                self.assertIn("board itself pairs the 9s", text)
                self.assertIn("Your private cards do not make that pair", text)
                self.assertIn("does not tell us what an opponent holds", text)
                self.assertNotIn("bottom pair", text)

    def test_unpaired_board_still_describes_hero_bottom_pair(self):
        analysis = with_visible_cards(
            self.analysis, ("4c", "2d"), ("Qh", "8c", "4s"))
        text = build_situation_teaching(analysis)["text"]
        self.assertIn("You have bottom pair", text)
        self.assertIn("one of your cards matches the bottom rank on this unpaired board", text)

    def test_seven_deuce_offsuit_starting_hand_description_is_preserved(self):
        analysis = with_visible_cards(self.analysis, ("7c", "2d"), ())
        text = build_situation_teaching(analysis)["text"]
        self.assertIn("7–2 offsuit", text)
        self.assertIn("challenging starting hand", text)


if __name__ == "__main__":
    unittest.main()

