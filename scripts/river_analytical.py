"""Independent polarised river oracle: exact rational EV and pure-policy BRs.

The oracle explicitly enumerates the five terminal histories, without using
production trees, terminal utilities, ranking, traversal or BR helpers.
Both players may bet once; there are no raises. OOP has nuts or air; IP has
one bluffcatcher. IP's policy cannot depend on OOP's hidden hand.
"""
from fractions import Fraction as F
from itertools import product


OOP_KEYS = ((0, "nuts", ()), (0, "air", ()),
            (0, "nuts", ("check", "bet")),
            (0, "air", ("check", "bet")))
IP_KEYS = ((1, "catcher", ("check",)), (1, "catcher", ("bet",)))


def equilibrium(nut_mass=F(1, 2), pot=100, bet=100):
    """One equilibrium in the unsaturated bluff region, with IP checking back."""
    nut_mass, pot, bet = F(nut_mass), F(pot), F(bet)
    if not 0 < nut_mass < 1 or pot <= 0 or bet <= 0:
        raise ValueError("Positive pot/bet and interior nut mass required.")
    bluff = nut_mass / (1 - nut_mass) * bet / (pot + bet)
    if bluff > 1:
        raise ValueError("Analytical anchor requires unsaturated bluffs.")
    # Rows in the independent oracle are [check,bet] or [fold,call].
    profile = {
        OOP_KEYS[0]: (F(0), F(1)), OOP_KEYS[1]: (1 - bluff, bluff),
        OOP_KEYS[2]: (F(0), F(1)), OOP_KEYS[3]: (F(1), F(0)),
        IP_KEYS[0]: (F(1), F(0)),
        IP_KEYS[1]: (bet / (pot + bet), pot / (pot + bet)),
    }
    value = (2 * nut_mass - 1) * pot / 2 + nut_mass * bet * pot / (pot + bet)
    return profile, value


def replay(profile, nut_mass=F(1, 2), pot=100, bet=100):
    """OOP's zero-sum EV from independently written terminal histories."""
    nut_mass, pot, bet = F(nut_mass), F(pot), F(bet)
    total = F(0)
    for hand, weight, sign in (("nuts", nut_mass, 1), ("air", 1 - nut_mass, -1)):
        check, wager = profile[(0, hand, ())]
        ip_fold, ip_call = profile[IP_KEYS[1]]
        ip_check, ip_bet = profile[IP_KEYS[0]]
        oop_fold, oop_call = profile[(0, hand, ("check", "bet"))]
        total += weight * (
            wager * (ip_fold * pot / 2 + ip_call * sign * (pot / 2 + bet)) +
            check * (ip_check * sign * pot / 2 +
                     ip_bet * (-oop_fold * pot / 2 + oop_call * sign * (pot / 2 + bet)))
        )
    return total


def metrics(profile, nut_mass=F(1, 2), pot=100, bet=100):
    """Exact BRs enumerate 16 OOP and 4 IP pure visible-information policies."""
    responses = []
    for player, keys in enumerate((OOP_KEYS, IP_KEYS)):
        values = []
        for choices in product((0, 1), repeat=len(keys)):
            candidate = dict(profile)
            for key, action in zip(keys, choices):
                candidate[key] = (F(action == 0), F(action == 1))
            value = replay(candidate, nut_mass, pot, bet)
            values.append(value if player == 0 else -value)
        responses.append(max(values))
    value = replay(profile, nut_mass, pot, bet)
    return value, responses[0], responses[1]


def serialized_profile(result):
    """Translate only visible serialized decisions; never read reported EVs."""
    profile = {}
    for row in result["strategy"]:
        player = 0 if row["player"] == "oop" else 1
        holding = frozenset(row["hand"][i:i + 2] for i in (0, 2))
        hand = ({frozenset(("As", "Ah")): "nuts",
                 frozenset(("3c", "4c")): "air"}[holding] if player == 0 else
                {frozenset(("Qs", "Qh")): "catcher"}[holding])
        history = tuple(token.split("@")[0] for token in row["history"])
        by_name = {action["name"]: F(str(action["probability"]))
                   for action in row["actions"]}
        names = ("check", "bet") if "check" in by_name else ("fold", "call")
        # A capped bet is labelled all_in by production rules.
        if "all_in" in by_name:
            by_name["bet"] = by_name["all_in"]
        key = (player, hand, history)
        if key in profile:
            raise ValueError("Duplicate serialized information set.")
        profile[key] = tuple(by_name[name] for name in names)
    if set(profile) != set(OOP_KEYS + IP_KEYS):
        raise ValueError("Serialized policy does not match the one-bet oracle game.")
    return profile
