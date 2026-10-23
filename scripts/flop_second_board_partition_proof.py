"""Pure-data joint-mass and partition audit for the fixed second flop.

This module validates supplied physical rows against a candidate partition. It
does not prepare or rank a physical model, inspect a betting tree, or certify a
class-policy quotient.
"""
from collections import Counter, defaultdict
from fractions import Fraction

from scripts import flop_public_classes_candidate as candidate
from scripts.flop_second_board_plan import BOARD, plan_second_board


MAX_PAIRS = 3
MAX_WORLDS = 5_940
MAX_TURNS = 49
MAX_RUNOUTS = MAX_TURNS * 48
MAX_CLASS_WORLDS = MAX_WORLDS
MAX_PARTITION_ITEMS = 100_000
MAX_PARTITION_DEPTH = 12
MAX_STRING_CHARS = 2_048
MAX_INTEGER_BITS = 384


def _need(condition, message):
    if not condition:
        raise ValueError(message)


def _check_fraction(value, message):
    _need(type(value) is Fraction
          and value.numerator.bit_length() <= MAX_INTEGER_BITS
          and value.denominator.bit_length() <= MAX_INTEGER_BITS, message)


def _add_fraction(left, right, message):
    _check_fraction(left, message)
    _check_fraction(right, message)
    result = left + right
    _check_fraction(result, message)
    return result


def _sum_fractions(values, message):
    total = Fraction()
    for value in values:
        total = _add_fraction(total, value, message)
    return total


def _typed(value):
    """Typed comparison so bool/int and list/tuple aliases cannot pass."""
    if type(value) is dict:
        return ("dict", tuple((key, _typed(value[key])) for key in sorted(value)))
    if type(value) is list:
        return ("list", tuple(_typed(item) for item in value))
    if type(value) is tuple:
        return ("tuple", tuple(_typed(item) for item in value))
    return (type(value).__name__, value)


def _bounded_partition(partition):
    """Bound nested input before typed comparison or schema-driven traversal."""
    _need(type(partition) is dict, "Partition must be an exact dictionary")
    pending = [(partition, 0)]
    seen_containers = set()
    count = 0
    while pending:
        value, depth = pending.pop()
        count += 1
        _need(count <= MAX_PARTITION_ITEMS and depth <= MAX_PARTITION_DEPTH,
              "Partition exceeds its item or depth bound")
        if type(value) is dict:
            ident = id(value)
            _need(ident not in seen_containers, "Partition contains a cycle or container alias")
            seen_containers.add(ident)
            _need(len(value) <= 64 and all(type(key) is str and
                  len(key) <= 256 for key in value), "Partition mapping exceeds its bound")
            _need(count + len(pending) + len(value) <= MAX_PARTITION_ITEMS,
                  "Partition pending-item reservation exceeds its bound")
            pending.extend((child, depth + 1) for child in value.values())
        elif type(value) is list:
            ident = id(value)
            _need(ident not in seen_containers, "Partition contains a cycle or container alias")
            seen_containers.add(ident)
            _need(len(value) <= MAX_CLASS_WORLDS,
                  "Partition list exceeds the physical-world bound")
            _need(count + len(pending) + len(value) <= MAX_PARTITION_ITEMS,
                  "Partition pending-item reservation exceeds its bound")
            pending.extend((child, depth + 1) for child in value)
        else:
            _need(type(value) in (str, int, bool, type(None)),
                  "Partition contains an unsupported scalar")
            if type(value) is str:
                _need(len(value) <= MAX_STRING_CHARS, "Partition string exceeds its bound")
            elif type(value) is int:
                _need(value.bit_length() <= MAX_INTEGER_BITS,
                      "Partition integer exceeds its exact-mass bound")


def _canonical_hand(label):
    _need(type(label) is str and len(label) == 4,
          "Private hand label must contain exactly two cards")
    cards = (label[:2], label[2:])
    _need(all(card in candidate._DECK_INDEX for card in cards) and cards[0] != cards[1],
          "Private hand contains an invalid or repeated card")
    canonical = "".join(sorted(cards))  # matches physical._hand_rows identity order
    _need(label == canonical, "Physical hand label is not parser-canonical")
    return cards


def _world_input(worlds, board):
    _need(type(board) is tuple and len(board) == 3 and
          all(type(card) is str and card in candidate._DECK_INDEX for card in board)
          and len(set(board)) == 3, "Board must be an exact three-card tuple")
    _need(board == BOARD, "This proof module is restricted to the admitted second board")
    _need(type(worlds) in (tuple, list) and 0 < len(worlds) <= MAX_WORLDS,
          "Physical worlds exceed the admitted container or row bound")

    rows = []
    pair_cards = {}
    pair_totals = {}
    per_pair = defaultdict(dict)
    global_total = Fraction()
    turns = set()
    runouts = set()
    for index, row in enumerate(worlds):
        _need(type(row) in (tuple, list) and len(row) == 5,
              f"World row {index} has an invalid shape")
        oop, ip, mass, sign, full_board = row
        oop_cards, ip_cards = _canonical_hand(oop), _canonical_hand(ip)
        _need(set(oop_cards).isdisjoint(ip_cards)
              and set(oop_cards + ip_cards).isdisjoint(board),
              "Private cards collide with each other or the board")
        _check_fraction(mass, "World mass exceeds the exact fraction bit bound")
        _need(mass > 0 and type(sign) is int and sign in (-1, 0, 1),
              "World mass/sign has an invalid exact type")
        _need(type(full_board) in (tuple, list) and len(full_board) == 5
              and all(type(card) is str and card in candidate._DECK_INDEX
                      for card in full_board), "World board has an invalid shape")
        full_board = tuple(full_board)
        _need(full_board[:3] == board and len(set(full_board)) == 5,
              "World does not contain the exact flop and five distinct cards")
        future = full_board[3:]
        _need(set(future).isdisjoint(oop_cards + ip_cards),
              "Future board collides with a private hand")
        pair = (oop, ip)
        cards = (oop_cards, ip_cards)
        if pair not in pair_cards and len(pair_cards) >= MAX_PAIRS:
            raise ValueError("World rows contain more than three private pairs")
        _need(pair not in pair_cards or pair_cards[pair] == cards,
              "A private-pair label maps to inconsistent cards")
        pair_cards[pair] = cards
        _need(future not in per_pair[pair], "Duplicate ordered private-pair runout")
        per_pair[pair][future] = (mass, sign)
        pair_totals[pair] = _add_fraction(
            pair_totals.get(pair, Fraction()), mass,
            "Private-pair mass accumulation exceeds the exact fraction bit bound")
        global_total = _add_fraction(
            global_total, mass, "Global mass accumulation exceeds the exact fraction bit bound")
        turns.add(future[0])
        runouts.add(future)
        rows.append((oop, ip, mass, sign, full_board))

    _need(0 < len(pair_cards) <= MAX_PAIRS and len(pair_cards) == 3,
          "World rows must contain exactly the three admitted private pairs")
    _need(len(turns) == MAX_TURNS and len(runouts) <= MAX_RUNOUTS,
          "Physical turn/runout support exceeds or omits the admitted deck support")
    for pair, cards in pair_cards.items():
        dead = set(board + cards[0] + cards[1])
        remaining = tuple(card for card in candidate.DECK if card not in dead)
        _need(len(remaining) == 45, "Private pair does not leave 45 future cards")
        support = {(turn, river) for turn in remaining for river in remaining if turn != river}
        _need(len(per_pair[pair]) == 45 * 44 and set(per_pair[pair]) == support,
              "A private pair does not cover every ordered legal two-card runout")
        expected_mass = pair_totals[pair] / (45 * 44)
        _check_fraction(expected_mass, "Conditional world mass exceeds the exact fraction bit bound")
        _need(expected_mass > 0 and all(mass == expected_mass
              for mass, _sign in per_pair[pair].values()),
              "Conditional runout masses are not uniform within a private pair")
    plan = plan_second_board()
    expected_pair_totals = {
        ("".join(sorted((oop[:2], oop[2:]))),
         "".join(sorted((ip[:2], ip[2:])))): prior
        for oop, ip, prior in plan.exact_pair_priors
    }
    _need(dict(pair_totals) == expected_pair_totals,
          "Physical pair marginals differ from the exact blocker-conditioned plan")
    _need(len(rows) == 5_940 and global_total == 1,
          "Physical worlds do not have the complete normalized joint mass")
    return rows, pair_cards, pair_totals, per_pair, turns, runouts


def _partition_maps(partition, turns, runouts):
    turn_groups, river_groups, class_worlds = (
        partition.get("turn_classes"), partition.get("river_classes"),
        partition.get("class_worlds"))
    _need(type(turn_groups) is list and 0 < len(turn_groups) <= MAX_TURNS
          and type(river_groups) is list and 0 < len(river_groups) <= MAX_RUNOUTS
          and type(class_worlds) is list and 0 < len(class_worlds) <= MAX_CLASS_WORLDS,
          "Partition class containers exceed admitted support")

    turn_map = {}
    for expected_id, group in enumerate(turn_groups):
        _need(type(group) is dict and type(group.get("id")) is int
              and group["id"] == expected_id and type(group.get("members")) is list
              and 0 < len(group["members"]) <= MAX_TURNS,
              "Turn class has malformed ID or members")
        for card in group["members"]:
            _need(type(card) is str and card in turns and card not in turn_map,
                  "Turn classes duplicate or add a physical turn")
            turn_map[card] = "T%02d" % expected_id
    _need(set(turn_map) == turns, "Turn classes omit physical turn support")

    river_map = {}
    for expected_id, group in enumerate(river_groups):
        _need(type(group) is dict and type(group.get("id")) is int
              and group["id"] == expected_id and type(group.get("members")) is list
              and 0 < len(group["members"]) <= MAX_RUNOUTS,
              "River class has malformed ID or members")
        for member in group["members"]:
            _need(type(member) is dict and set(member) == {"turn", "river"}
                  and type(member["turn"]) is str and type(member["river"]) is str,
                  "River class member is malformed")
            runout = (member["turn"], member["river"])
            _need(runout in runouts and runout not in river_map,
                  "River classes duplicate or add a physical runout")
            river_map[runout] = "R%02d" % expected_id
    _need(set(river_map) == runouts, "River classes omit physical runout support")
    return turn_map, river_map


def _verify_river_signatures(river_groups, runouts, pair_order, per_pair, river_map):
    signatures = {}
    for runout in runouts:
        signatures[runout] = tuple(
            (per_pair[pair][runout][0], per_pair[pair][runout][1])
            if runout in per_pair[pair] else None
            for pair in pair_order)
    for group in river_groups:
        members = [(row["turn"], row["river"]) for row in group["members"]]
        reference = signatures[members[0]]
        _need(all(signatures[member] == reference for member in members),
              "River class changes pair support, exact mass, or showdown sign")
    return signatures


def _verify_turn_classes(turn_groups, turns, runouts, turn_map, river_map,
                         pair_order, per_pair, signatures):
    turn_mass = {
        turn: tuple(_sum_fractions(
            (mass for future, (mass, _sign) in per_pair[pair].items()
             if future[0] == turn),
            "Turn marginal exceeds the exact fraction bit bound")
            for pair in pair_order)
        for turn in turns
    }
    transports_checked = 0
    for group in turn_groups:
        members = group["members"]
        representative = group.get("representative")
        _need(type(representative) is str and representative in members,
              "Turn-class representative is not a member")
        ref_counts = Counter(river_map[runout] for runout in runouts
                             if runout[0] == representative)
        ref_runouts = {runout for runout in runouts if runout[0] == representative}
        _need(ref_runouts, "Turn representative has no physical river support")
        transports = group.get("river_transports")
        _need(type(transports) is list and len(transports) <= MAX_RUNOUTS,
              "Turn transport exceeds the runout bound")
        for turn in members:
            _need(turn_mass[turn] == turn_mass[representative],
                  "Turn class changes exact pairwise posterior mass")
            member_runouts = {runout for runout in runouts if runout[0] == turn}
            counts = Counter(river_map[runout] for runout in member_runouts)
            _need(counts == ref_counts and len(member_runouts) == len(ref_runouts),
                  "Turn class changes river-class transition multiplicities")
            rows = [row for row in transports if type(row) is dict and row.get("turn") == turn]
            source = {(row.get("turn"), row.get("river")) for row in rows}
            destination = {(row.get("representative_turn"), row.get("representative_river"))
                           for row in rows}
            _need(len(rows) == len(source) == len(destination)
                  and source == member_runouts and destination == ref_runouts,
                  "River transport is not a complete per-turn bijection")
            for row in rows:
                src = (row["turn"], row["river"])
                dst = (row["representative_turn"], row["representative_river"])
                _need(type(row.get("river_class_id")) is int
                      and river_map[src] == river_map[dst]
                      and river_map[src] == "R%02d" % row["river_class_id"]
                      and signatures[src] == signatures[dst],
                      "River transport changes joint signatures or class identity")
                transports_checked += 1
        expected_count = sum(len([runout for runout in runouts if runout[0] == turn])
                             for turn in members)
        _need(len(transports) == expected_count,
              "Turn class contains extra or omitted transport rows")
        marginal_rows = group.get("turn_mass_by_pair")
        _need(type(marginal_rows) is list and len(marginal_rows) == len(pair_order),
              "Turn class pair-marginal rows have the wrong shape")
        marginals = {}
        for row in marginal_rows:
            _need(type(row) is dict and set(row) == {"oop_hand", "ip_hand", "mass"}
                  and type(row["oop_hand"]) is str and type(row["ip_hand"]) is str
                  and type(row["mass"]) is list and len(row["mass"]) == 2
                  and type(row["mass"][0]) is int and row["mass"][0] >= 0
                  and type(row["mass"][1]) is int and row["mass"][1] > 0,
                  "Turn class pair-marginal row is malformed")
            pair = (row["oop_hand"], row["ip_hand"])
            _need(pair in pair_order and pair not in marginals,
                  "Turn class duplicates or adds a pair marginal")
            marginals[pair] = Fraction(*row["mass"])
        expected_marginals = {pair: turn_mass[representative][index]
                              for index, pair in enumerate(pair_order)}
        _need(marginals == expected_marginals,
            "Turn class descriptive pair marginals differ from physical rows")
    return transports_checked


def _aggregate_worlds(partition, rows, turn_map, river_map, board):
    aggregate = {}
    counts = Counter()
    signs = {}
    for row in rows:
        oop, ip, mass, sign, full_board = row
        key = (oop, ip, turn_map[full_board[3]], river_map[full_board[3:]])
        if key in signs:
            _need(signs[key] == sign, "Aggregated class world combines different signs")
        else:
            signs[key] = sign
            aggregate[key] = Fraction()
        aggregate[key] = _add_fraction(
            aggregate[key], mass, "Class-world mass exceeds the exact fraction bit bound")
        counts[key] += 1

    compact_worlds = []
    observed = set()
    for row in partition["class_worlds"]:
        _need(type(row) is dict and set(row) == {
            "oop_hand", "ip_hand", "turn_class_id", "river_class_id",
            "mass", "sign", "physical_world_count"}, "Class-world row fields differ")
        oop, ip = row["oop_hand"], row["ip_hand"]
        turn_id, river_id = row["turn_class_id"], row["river_class_id"]
        key = (oop, ip, "T%02d" % turn_id if type(turn_id) is int else "",
               "R%02d" % river_id if type(river_id) is int else "")
        _need(key in aggregate and key not in observed, "Class-world support duplicates or adds a row")
        observed.add(key)
        mass = row["mass"]
        _need(type(mass) is list and len(mass) == 2
              and all(type(value) is int and value > 0 for value in mass)
              and type(row["sign"]) is int and type(row["physical_world_count"]) is int
              and row["physical_world_count"] == counts[key]
              and row["sign"] == signs[key] and Fraction(*mass) == aggregate[key],
              "Class-world sign, mass, or physical multiplicity differs")
        compact_worlds.append((oop, ip, aggregate[key], signs[key], board + (key[2], key[3])))
    _need(observed == set(aggregate), "Class-world table omits aggregate support")
    pair_totals = {}
    global_total = Fraction()
    for oop, ip, mass, _sign, _board in rows:
        pair = (oop, ip)
        pair_totals[pair] = _add_fraction(
            pair_totals.get(pair, Fraction()), mass,
            "Physical pair marginal exceeds the exact fraction bit bound")
        global_total = _add_fraction(
            global_total, mass, "Physical global mass exceeds the exact fraction bit bound")
    output_totals = defaultdict(Fraction)
    for oop, ip, mass, _sign, _board in compact_worlds:
        pair = (oop, ip)
        output_totals[pair] = _add_fraction(
            output_totals[pair], mass,
            "Class pair marginal exceeds the exact fraction bit bound")
    output_global = _sum_fractions(
        (world[2] for world in compact_worlds),
        "Class global mass exceeds the exact fraction bit bound")
    _need(dict(output_totals) == dict(pair_totals)
          and global_total == 1 and output_global == 1
          and sum(row["physical_world_count"] for row in partition["class_worlds"]) == len(rows),
          "Class aggregation changes exact pair/global mass or source-row coverage")
    return tuple(compact_worlds), aggregate, counts, signs


def verify_partition(partition, worlds, *, board=BOARD):
    """Independently audit exact joint support and a candidate partition.

    Returns turn/runout-to-class maps, exact aggregated worlds and a measured
    census. No first-board class counts, physical tree, policy, or response
    claim is assumed.
    """
    _need(type(board) is tuple and board == BOARD,
          "Partition proof is restricted to the admitted second board tuple")
    _bounded_partition(partition)
    rows, pair_cards, pair_totals, per_pair, turns, runouts = _world_input(worlds, board)
    pair_order = sorted(pair_cards)
    turn_groups, river_groups = partition.get("turn_classes"), partition.get("river_classes")
    turn_map, river_map = _partition_maps(partition, turns, runouts)
    signatures = _verify_river_signatures(river_groups, runouts, pair_order,
                                          per_pair, river_map)
    transports = _verify_turn_classes(turn_groups, turns, runouts, turn_map,
                                      river_map, pair_order, per_pair, signatures)
    compact_worlds, _aggregate, _counts, _signs = _aggregate_worlds(
        partition, rows, turn_map, river_map, board)

    # Rebuild only the descriptive candidate record from the bounded supplied
    # rows. This authenticates deterministic IDs and every presentation field;
    # the independent checks above establish the mass/sign invariants.
    candidate_rows = [[oop, ip, str(mass), sign, list(full_board)]
                      for oop, ip, mass, sign, full_board in rows]
    rebuilt = candidate.build_candidate(candidate_rows, board=board)
    _need(_typed(partition) == _typed(rebuilt),
          "Candidate descriptive partition differs from independently checked rows")

    census = {
        "board": list(board), "compatible_pairs": len(pair_cards),
        "physical_worlds": len(rows), "turn_cards": len(turns),
        "ordered_runouts": len(runouts),
        "turn_classes": len(turn_groups), "river_signatures": len(river_groups),
        "class_worlds": len(compact_worlds), "river_transports_checked": transports,
        "joint_mass": "1/1",
        "pair_marginals": [
            {"oop_hand": pair[0], "ip_hand": pair[1],
             "mass": f"{pair_totals[pair].numerator}/{pair_totals[pair].denominator}"}
            for pair in pair_order],
    }
    return turn_map, river_map, compact_worlds, census
