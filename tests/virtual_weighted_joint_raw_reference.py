"""Independent selected-world four-street arithmetic with implicit policies.

No full-deck information universe is materialized. The numeric betting rules,
Fraction arithmetic and independent best-five ranks remain the authorities.
This reference executes at most two fixed joint observations, never RNG/BR or
convergence. The exact weighted law is admitted before numeric preparation.
"""
from dataclasses import dataclass
from fractions import Fraction
from types import MappingProxyType

from scripts.matrix_free_certificate_budget import Budget
from tests.full_deck_public_chance_reference import card_name
from tests.virtual_betting_template_reference import build_reference_template
from tests.virtual_frozen_update_reference import _template_case
from tests.virtual_sparse_epoch_reference import _largest_remainder, _uniform_row
from tests.virtual_weighted_joint_reference import LIMITS, World, build_law, forecast as law_forecast, require

Q = 1 << 52
DR = 1 << 625
DA = 1 << 364
SOURCE_WORK = 43_000_000
SOURCE_BITS = 1_000_000_000
RAW_WORK = 9_000_000
RAW_BITS = 227_840_000
FRACTION_OPERATIONS = 20_000


def reveal(board, length):
    return ('flop@' + ''.join(card_name(card) for card in board[:3]) if length == 3 else
            ('turn@' if length == 4 else 'river@') + card_name(board[length - 1]))


def scale(value, denominator, magnitude):
    require(type(value) is Fraction and denominator % value.denominator == 0, 'weighted raw exact dyadic scale')
    integer = value.numerator * (denominator // value.denominator)
    require(abs(integer).bit_length() <= magnitude, 'weighted raw integer magnitude')
    return integer


@dataclass(frozen=True)
class Row:
    menu: tuple
    regrets: tuple
    averages: tuple
    units: tuple
    prior_own_actions: int
    source: int
    ordinal: int


@dataclass(frozen=True, init=False)
class Policy:
    """Immutable sparse overlays with validated own-visible-history lookup."""
    request: object
    rows: object
    def __init__(self, request, rows):
        require(type(rows) is dict and len(rows) <= 868 and sum(map(len, rows.values())) <= 2078,
                'weighted frozen sparse policy shape')
        copied = {}
        for key, units in rows.items():
            menu, _source, _ordinal = request.locate(key)
            require(type(units) is tuple and len(units) == len(menu) and
                    all(type(unit) is int and 0 <= unit <= Q for unit in units) and sum(units) == Q,
                    'weighted frozen Q52 row partition')
            if units != _uniform_row(len(menu)):
                copied[key] = units
        object.__setattr__(self, 'request', request)
        object.__setattr__(self, 'rows', MappingProxyType(copied))

    def lookup(self, actor, holding, history):
        key = actor, holding, history
        menu, _source, _ordinal = self.request.locate(key)
        return self.rows.get(key, _uniform_row(len(menu)))


class Request:
    def __init__(self, deck, ranges, limits=None):
        require(type(ranges) is tuple and len(ranges) == 2 and all(type(side) is tuple for side in ranges),
                'weighted raw ordered ranges')
        require(type(deck) is tuple, 'weighted raw deck tuple')
        plan = law_forecast(len(deck), tuple(map(len, ranges)))
        complete = {'work': plan['work'] + SOURCE_WORK + RAW_WORK,
                    'created_bits': plan['created_bits'] + SOURCE_BITS + RAW_BITS,
                    'entries': plan['entries'] + 131072 + 500000, 'integer_bits': 4096}
        chosen = dict(LIMITS)
        require(limits is None or type(limits) is dict and set(limits) <= set(LIMITS), 'weighted raw limits')
        for key, value in (limits or {}).items():
            require(type(value) is int and 0 < value <= LIMITS[key], 'weighted raw reduce-only limits')
            chosen[key] = value
        require(all(complete[key] <= chosen[key] for key in LIMITS), 'weighted raw complete request rejected')
        self.forecast = MappingProxyType(complete)
        self.budget = Budget(chosen)
        self.budget.charge('weighted_law_source_two_walk_reserved', complete['work'])
        self.budget.entries(complete['entries'] - 2, 'weighted law/source/two raw outputs/overlays/scratch')
        self.budget.created_bits = complete['created_bits']; self.budget.max_forecast_bits = 4096
        self.law = build_law(deck, ranges)
        source_budget = Budget({'work': SOURCE_WORK, 'entries': 131072, 'created_bits': SOURCE_BITS, 'integer_bits': 4096})
        self.template = build_reference_template(_template_case(), rule_budget=source_budget)
        self.nodes = self.template.nodes
        require(len(self.nodes) == 388 and self.template.receipt['logical_occurrences'] == 1105,
                'weighted raw fixed betting source')
        self.stakes = {index: min(Fraction.from_float(float(x)) for x in node.state.state.committed)
                       for index, node in enumerate(self.nodes) if node.phase in ('fold', 'showdown')}
        require(all(0 <= stake <= 8 and (2 * stake).denominator == 1 for stake in self.stakes.values()),
                'weighted raw fixed stake geometry')
        # Structural literal path IDs only. No card/public/private world table.
        paths = [(self.template.root, None, None)]
        self.child_paths = {}
        for ordinal, (source, _parent, _edge) in enumerate(paths):
            for number, edge in enumerate(self.nodes[source].edges):
                self.child_paths[ordinal, number] = len(paths)
                paths.append((edge.child, ordinal, number))
                require(len(paths) <= 1105, 'weighted raw path reserve')
        require(len(paths) == 1105, 'weighted raw literal path census')
        self.calls = self.fraction_ops = self.lookups = 0

    def locate(self, key):
        # Up to4096 policy/menu/transport queries, each <=52 card-name entries,
        # 15 visible tokens and fixed descriptors: <7M logical units. Two
        # walks/numeric staging and Fraction operations fit the9M reservation.
        require(self.lookups < 4096, 'weighted raw cumulative lookup limit')
        self.lookups += 1
        require(type(key) is tuple and len(key) == 3 and type(key[0]) is int and key[0] in (0, 1) and
                type(key[1]) is int and 0 <= key[1] < len(self.law.ranges[key[0]]) and
                type(key[2]) is tuple and len(key[2]) <= 15, 'weighted policy own-visible key')
        actor, holding, history = key
        source, ordinal, board = self.template.root, 0, ()
        names = {card_name(card): card for card in self.law.deck}
        for token in history:
            require(type(token) is str and len(token) <= 64, 'weighted policy visible token')
            node = self.nodes[source]
            if node.phase == 'reveal':
                length = node.state.board_length
                if length == 3:
                    require(len(token) == 11 and token.startswith('flop@'), 'weighted policy flop token')
                    texts = tuple(token[index:index + 2] for index in (5, 7, 9))
                else:
                    prefix = 'turn@' if length == 4 else 'river@'
                    require(len(token) == len(prefix) + 2 and token.startswith(prefix), 'weighted policy suffix token')
                    texts = (token[len(prefix):],)
                require(all(text in names for text in texts), 'weighted policy declared card')
                board += tuple(names[text] for text in texts)
                require(len(board) == length and len(set(board)) == length and tuple(sorted(board[:3])) == board[:3] and
                        set(board).isdisjoint(self.law.ranges[actor][holding][0]), 'weighted policy own blockers or board order')
                number = 0
            else:
                require(node.phase == 'decision', 'weighted policy token after terminal')
                options = tuple(edge.token for edge in node.edges)
                require(token in options, 'weighted policy legal action token')
                number = options.index(token)
            ordinal = self.child_paths[ordinal, number]
            source = node.edges[number].child
        node = self.nodes[source]
        require(node.phase == 'decision' and node.state.player == actor and node.street == len(board),
                'weighted policy queried at visible decision')
        code = sum(card << (6 * index) for index, card in enumerate(board))
        encoded = (ordinal << 33) | (len(board) << 30) | code
        return tuple(edge.token for edge in node.edges), source, encoded

    def fraction(self, operation, left, right):
        require(self.fraction_ops < FRACTION_OPERATIONS and type(left) is Fraction and type(right) is Fraction,
                'weighted raw cumulative Fraction operation limit')
        an, ad = abs(left.numerator).bit_length(), left.denominator.bit_length()
        bn, bd = abs(right.numerator).bit_length(), right.denominator.bit_length()
        sizes = ((an + bn, ad + bd) if operation == 'mul' else
                 (an + bd, bn + ad, max(an + bd, bn + ad) + 1, ad + bd))
        require(max(sizes) <= 2048 and 2 * sum(sizes) <= 8192, 'weighted raw prepaid Fraction width')
        self.fraction_ops += 1
        return left * right if operation == 'mul' else left + right if operation == 'add' else left - right

    def one_sample(self, world, policy=None):
        require(self.calls < 2, 'weighted raw two observation limit')
        require(type(world) is World, 'weighted raw physical world type')
        # Independent law/rank re-decode seals the physical world before walk.
        expected = self.law.decode(world.private_ticket, world.board_rank)
        require(world == expected and world.showdown_sign in (-1, 0, 1), 'weighted raw foreign physical world')
        policy = Policy(self, {}) if policy is None else policy
        require(type(policy) is Policy and policy.request is self, 'weighted raw frozen policy owner')
        self.calls += 1
        rows = {}; counts = [0, 0, 0, 0]; slots = 0
        op = self.fraction
        def visit(source, history, reaches, depth):
            nonlocal slots
            counts[0] += 1; require(counts[0] <= 1105, 'weighted raw visit census')
            node = self.nodes[source]
            if node.phase in ('fold', 'showdown'):
                counts[3] += 1
                sign = world.showdown_sign if node.phase == 'showdown' else (1 if node.state.winner == 0 else -1)
                return self.stakes[source] * sign
            if node.phase == 'reveal':
                counts[2] += 1
                return visit(node.edges[0].child, (*history, reveal(world.board, node.state.board_length)), reaches, depth)
            actor = node.state.player; own, opposite = reaches[actor], reaches[1 - actor]
            key = actor, world.holding_indices[actor], history
            menu, original, ordinal = self.locate(key)
            units = policy.lookup(*key); probabilities = tuple(Fraction(unit, Q) for unit in units)
            require(key not in rows and original == source and len(rows) < 434 and slots + len(menu) <= 1039,
                    'weighted raw selected information identity or capacity')
            slots += len(menu); values = []
            for index, edge in enumerate(node.edges):
                counts[1] += 1
                next_reach, next_depth = list(reaches), list(depth)
                next_reach[actor] = op('mul', own, probabilities[index]); next_depth[actor] += 1
                values.append(visit(edge.child, (*history, edge.token), tuple(next_reach), tuple(next_depth)))
            mixed = Fraction(0)
            for probability, value in zip(probabilities, values):
                mixed = op('add', mixed, op('mul', probability, value))
            counterfactual = opposite if actor == 0 else -opposite
            regrets = tuple(scale(op('mul', counterfactual, op('sub', value, mixed)), DR, 630) for value in values)
            averages = tuple(scale(op('mul', own, probability), DA, 365) for probability in probabilities)
            require(sum(value * unit for value, unit in zip(regrets, units)) == 0 and
                    all(value % (1 << (52 * depth[actor])) == 0 for value in regrets), 'weighted raw centering/factors')
            rows[key] = Row(menu, regrets, averages, units, depth[actor], source, ordinal)
            return mixed
        try:
            root = visit(self.template.root, (), (Fraction(1), Fraction(1)), (0, 0))
        finally:
            visit = None
        require(counts == [1105, 1039, 65, 606] and len(rows) == 434 and slots == 1039, 'weighted raw complete scalar census')
        return MappingProxyType(rows), scale(root, DR, 629)


def two_epochs(request, selectors):
    require(type(request) is Request and request.calls == 0 and type(selectors) is tuple and len(selectors) == 2,
            'weighted raw fresh two-observation request')
    # Both selectors/ranks validate before any rank/decode/walk.
    for item in selectors:
        require(type(item) is tuple and len(item) == 2 and all(type(value) is int for value in item) and
                0 <= item[0] < request.law.normalizer and 0 <= item[1] < request.law.receipt()['forecast']['board_count'],
                'weighted raw complete selector admission')
    worlds = tuple(request.law.decode(*item) for item in selectors)
    policy = Policy(request, {}); numeric = {}; observations = []
    for world in worlds:
        rows, root = request.one_sample(world, policy)
        overlays = dict(policy.rows)
        for key, row in rows.items():
            old_r, old_a = numeric.get(key, ((0,) * len(row.menu), (0,) * len(row.menu)))
            current_r = tuple(a + b for a, b in zip(old_r, row.regrets))
            current_a = tuple(a + b for a, b in zip(old_a, row.averages))
            require(all(abs(value).bit_length() <= 631 for value in current_r) and
                    all(0 <= value and value.bit_length() <= 366 for value in current_a), 'weighted raw cumulative T2 width')
            if any(current_r) or any(current_a):
                numeric[key] = current_r, current_a
            else:
                numeric.pop(key, None)
            if any(row.regrets):
                overlays[key] = _largest_remainder(tuple(max(value, 0) for value in current_r))
        next_policy = Policy(request, overlays)
        require(len(numeric) <= 868 and sum(len(pair[0]) for pair in numeric.values()) <= 2078,
                'weighted raw retained union capacity')
        observations.append({'world': world, 'root': root, 'raw': rows, 'numeric': MappingProxyType(dict(numeric)),
                             'input_policy': policy, 'policy': next_policy})
        policy = next_policy
    return tuple(observations)
