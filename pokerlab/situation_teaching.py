"""Plain-language situation facts derived from validated visible cards."""
from __future__ import annotations

from .cards import NAMES, RANKS, rank_hand
from .contracts import CoachDecisionAnalysis


def _preflop_situation(hero_cards: tuple[str, str]) -> str:
    ranks = tuple(RANKS.index(card[0]) + 2 for card in hero_cards)
    if ranks[0] == ranks[1]:
        hand = f"{hero_cards[0][0]}–{hero_cards[1][0]}"
        return (f"Your starting hand is {hand}, a pocket pair. Your cards share a rank; "
                "suitedness and connectedness do not apply. This describes your cards, "
                "not whether your action was right.")

    labels = ["both low ranks" if max(ranks) <= 9 else
              "includes a high card" if max(ranks) >= 11 else "middle ranks",
              "unpaired",
              "suited" if hero_cards[0][1] == hero_cards[1][1] else "offsuit"]
    distance = abs(ranks[0] - ranks[1])
    if distance == 1:
        labels.append("connected")
    elif set(ranks) == {2, 14}:
        labels.append("not consecutive by rank")
    elif distance == 2:
        labels.append("one rank apart")
    else:
        labels.append("not connected")
    hand = "–".join(sorted((card[0] for card in hero_cards),
                            key=lambda rank: RANKS.index(rank), reverse=True))
    suffix = " offsuit" if hero_cards[0][1] != hero_cards[1][1] else " suited"
    description = f"Your starting hand is {hand}{suffix}: {', '.join(labels)}. "
    if set(ranks) == {2, 14}:
        description += "An ace can also count low in an A-2-3-4-5 straight. "
    if max(ranks) <= 9 and distance > 2 and hero_cards[0][1] != hero_cards[1][1]:
        description += ("That is a challenging starting hand; the best action still "
                        "depends on this spot. ")
        description += ("Because the ranks are far apart, they do not offer an easy "
                        "straight connection. Since they are different suits, they cannot "
                        "both help make a flush in one suit. ")
    return (description + "These are features of the cards you were dealt; "
            "they do not decide whether your action was right.")


def _postflop_situation(hero_cards: tuple[str, str], board: tuple[str, ...]) -> str:
    visible = hero_cards + board
    rank = rank_hand(visible)
    category = NAMES[rank[0]].lower()

    if rank[0] == 0:
        return ("On the visible board, you have no pair or stronger made hand "
                "(high card). This describes your hand only; it does not tell us what "
                "an opponent holds or whether you are ahead.")

    if len(board) == 5 and rank_hand(board) == rank:
        return (f"Your visible made hand is {category}, and the board already provides "
                "that hand category. Your private cards do not improve it. This does not "
                "tell us what an opponent holds or whether you are ahead.")

    if rank[0] == 1:
        board_ranks = [RANKS.index(card[0]) + 2 for card in board]
        hero_ranks = {RANKS.index(card[0]) + 2 for card in hero_cards}
        if rank[1] in board_ranks and rank[1] not in hero_ranks:
            pair_name = RANKS[rank[1] - 2]
            return (f"The board itself pairs the {pair_name}s, so your visible made hand "
                    f"includes a pair of {pair_name}s. Your private cards do not make "
                    "that pair; they may affect your kickers. This describes your cards "
                    "only and does not tell us what an opponent holds or whether you are ahead.")
        if (len(set(board_ranks)) == len(board_ranks)
                and rank[1] in hero_ranks and rank[1] in board_ranks):
            ordered = sorted(board_ranks, reverse=True)
            position = ordered.index(rank[1])
            pair_position = ("top" if position == 0 else
                             "bottom" if position == len(ordered) - 1 else "middle")
            return (f"You have {pair_position} pair: one of your cards matches the "
                    f"{pair_position} rank on this unpaired board. A pair is a made hand; "
                    + ("Your pair ranks below a pair made with a higher rank on the "
                       "board. " if pair_position == "bottom" else "")
                    + "An opponent may or may not have a better hand. Whether a particular "
                    "action fits depends on the current model and this spot.")

    return (f"Your visible cards make {category}. This describes your made hand only; "
            "it does not tell us what an opponent holds or whether you are ahead.")


def build_situation_teaching(analysis: CoachDecisionAnalysis) -> dict[str, str]:
    """Describe only visible hero cards and board; never infer opponent strength."""
    if not isinstance(analysis, CoachDecisionAnalysis):
        raise TypeError("Situation teaching requires validated decision analysis.")
    context = analysis.context
    if context.street == "preflop":
        text = _preflop_situation(context.hero_cards)
    else:
        text = _postflop_situation(context.hero_cards, context.board)
    return {
        "title": "Your situation",
        "text": text,
        "note": "This describes the cards and board, not whether your action was right.",
    }
