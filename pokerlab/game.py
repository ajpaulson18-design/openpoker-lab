"""No-limit Hold'em hand sandbox with integer chips and side pots.

No rake, antes, straddles or tournament rules. Seat numbers go clockwise.
Raise amounts are street totals. Short all-ins reopen only after the cumulative
amount faced since a player's last action reaches a full raise.
"""
import random
from .cards import DECK, rank_hand


def settle(contributions, folded, hands, board, button=0):
    payouts = [0] * len(hands)
    pots = []
    previous = 0
    for level in sorted(set(contributions) - {0}):
        contributors = [i for i, c in enumerate(contributions) if c >= level]
        amount = (level-previous)*len(contributors)
        previous = level
        eligible = [i for i in contributors if not folded[i]]
        if len(contributors) == 1:
            winners = contributors  # Uncalled chips return even without showdown.
        elif len(eligible) == 1:
            winners = eligible
        else:
            ranks = {i: rank_hand(tuple(hands[i])+tuple(board)) for i in eligible}
            best = max(ranks.values())
            winners = [i for i in eligible if ranks[i] == best]
        winners.sort(key=lambda i: (i-button-1) % len(hands))
        for n, i in enumerate(winners):
            payouts[i] += amount//len(winners)+(n < amount % len(winners))
        pots.append({"amount": amount, "winners": winners})
    return payouts, pots


class Game:
    def __init__(self, stacks=None, names=None, button=0, small_blind=1, big_blind=2, seed=None):
        stacks = [200, 200] if stacks is None else stacks
        if not isinstance(stacks, list) or not 2 <= len(stacks) <= 6 or any(type(s) is not int or not 1 <= s <= 1_000_000 for s in stacks):
            raise ValueError("Provide 2–6 positive integer stacks, at most 1 million each.")
        if names is None:
            names = [f"Player {i+1}" for i in range(len(stacks))]
        if (not isinstance(names, list) or len(names) != len(stacks)
                or any(not isinstance(name, str) or not 1 <= len(name.strip()) <= 40 for name in names)):
            raise ValueError("Provide one player name per stack, each 1–40 characters.")
        names = [name.strip() for name in names]
        if len({name.casefold() for name in names}) != len(names):
            raise ValueError("Player names must be unique.")
        if type(button) is not int or not 0 <= button < len(stacks):
            raise ValueError("Invalid button seat.")
        if type(small_blind) is not int or type(big_blind) is not int or not 0 < small_blind < big_blind:
            raise ValueError("Blinds must be positive integers, small blind less than big blind.")
        self.stacks = stacks.copy()
        self.names = names
        self.initial = stacks.copy()
        self.button, self.big_blind = button, big_blind
        self.deck = list(DECK)
        random.Random(seed).shuffle(self.deck)
        self.hands = [tuple(self.deck.pop() for _ in range(2)) for _ in stacks]
        self.board = []
        self.folded = [False]*len(stacks)
        self.committed = [0]*len(stacks)
        self.street_bets = [0]*len(stacks)
        self.last_acted = [None]*len(stacks)
        self.street = "preflop"
        self.done = False
        self.log, self.pots = [], []
        sb = button if len(stacks) == 2 else (button+1) % len(stacks)
        bb = (sb+1) % len(stacks)
        self.pay(sb, min(small_blind, self.stacks[sb]))
        self.pay(bb, min(big_blind, self.stacks[bb]))
        self.current_bet = big_blind
        self.min_raise = big_blind
        self.pending = {i for i, s in enumerate(self.stacks) if s}
        self.actor = bb
        self.advance()

    def pay(self, seat, amount):
        self.stacks[seat] -= amount
        self.street_bets[seat] += amount
        self.committed[seat] += amount

    def legal(self):
        if self.done:
            return {}
        i = self.actor
        owe = max(0, self.current_bet-self.street_bets[i])
        prior = self.last_acted[i]
        other_can_act = any(s and not self.folded[j] for j, s in enumerate(self.stacks) if j != i)
        can_raise = other_can_act and self.stacks[i] > owe and (prior is None or self.current_bet-prior >= self.min_raise)
        maximum = self.street_bets[i]+self.stacks[i]
        return {"fold": bool(owe), "check": not owe, "call": min(owe, self.stacks[i]),
                "raise": can_raise, "raise_min": min(maximum, self.current_bet+self.min_raise),
                "raise_max": maximum}

    def act(self, action, amount=None):
        if self.done:
            raise ValueError("This hand has finished.")
        i, legal = self.actor, self.legal()
        if action == "fold" and legal["fold"]:
            self.folded[i] = True
        elif action == "check" and legal["check"]:
            pass
        elif action == "call" and legal["call"]:
            self.pay(i, legal["call"])
        elif action == "raise" and legal["raise"]:
            if type(amount) is not int or not legal["raise_min"] <= amount <= legal["raise_max"]:
                raise ValueError("Raise to a legal integer street total.")
            increase = amount-self.current_bet
            if increase >= self.min_raise:
                self.min_raise = increase
            self.pay(i, amount-self.street_bets[i])
            self.current_bet = amount
            self.pending |= {j for j, s in enumerate(self.stacks) if s and not self.folded[j] and j != i}
        else:
            raise ValueError("That action is not legal here.")
        self.last_acted[i] = self.current_bet
        self.pending.discard(i)
        self.log.append({"seat": i, "name": self.names[i], "street": self.street,
                         "action": action, "amount": amount})
        self.advance()
        return self.state()

    def advance(self):
        while True:
            alive = [i for i, f in enumerate(self.folded) if not f]
            if len(alive) == 1:
                self.finish()
                return
            self.pending = {i for i in self.pending if self.stacks[i] and not self.folded[i]}
            active = [i for i in alive if self.stacks[i]]
            # A lone player with chips need only resolve an outstanding call.
            if len(active) == 1 and self.street_bets[active[0]] >= max(self.street_bets[j] for j in alive):
                self.pending.clear()
            if self.pending:
                self.actor = next((self.actor+d) % len(self.stacks) for d in range(1, len(self.stacks)+1)
                                  if (self.actor+d) % len(self.stacks) in self.pending)
                return
            if self.street == "river":
                self.finish()
                return
            self.deck.pop()  # Burn card.
            count = 3 if self.street == "preflop" else 1
            self.board.extend(self.deck.pop() for _ in range(count))
            self.street = {"preflop": "flop", "flop": "turn", "turn": "river"}[self.street]
            self.street_bets = [0]*len(self.stacks)
            self.current_bet = 0
            self.min_raise = self.big_blind
            self.last_acted = [None]*len(self.stacks)
            self.pending = set(active) if len(active) > 1 else set()
            self.actor = self.button

    def finish(self):
        payouts, self.pots = settle(self.committed, self.folded, self.hands, self.board, self.button)
        self.stacks = [s+p for s, p in zip(self.stacks, payouts)]
        self.done = True
        self.pending.clear()

    def state(self):
        named_pots = [{**pot, "winner_names": [self.names[i] for i in pot["winners"]]}
                      for pot in self.pots]
        return {"stacks": self.stacks, "names": self.names, "hands": self.hands, "board": self.board,
                "button": self.button, "actor": None if self.done else self.actor,
                "actor_name": None if self.done else self.names[self.actor],
                "committed": self.committed, "street_bets": self.street_bets, "folded": self.folded,
                "pot": sum(self.committed), "street": self.street, "done": self.done,
                "legal": self.legal(), "log": self.log, "pots": named_pots,
                "net": [s-i for s, i in zip(self.stacks, self.initial)] if self.done else None}
