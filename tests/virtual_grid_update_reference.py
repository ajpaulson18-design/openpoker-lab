"""Frozen Q52 update bridge, deliberately outside production training.

The proposal oracle walks an immutable card-free template with exact Fraction
reaches. The expectation oracle is the separate literal-world trainer reference.
Neither oracle calls native routing, payoff, policy or state code.
"""
from dataclasses import dataclass
from fractions import Fraction
from hashlib import sha256
import json
from types import MappingProxyType

from scripts.matrix_free_certificate_budget import Budget
from scripts.preflop_validation import independent_rank
from tests.full_deck_public_chance_reference import PROOF9, card_name
from tests.virtual_dyadic_training_reference import D, Q, Fixture
from tests.virtual_frozen_sample_reference import (
    admit_sampled_board, build_sampled_reference_context, _reveal_token,
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


@dataclass(frozen=True)
class FrozenGrid:
    units: object
    probabilities: object
    menus: object
    prefixes: object
    digest: str
    _origin: object


@dataclass(frozen=True)
class _GridOrigin:
    maps: tuple
    digest: str


def validate_grid(grid):
    require(type(grid) is FrozenGrid and type(grid._origin) is _GridOrigin,
            'grid must originate from the complete snapshot factory')
    require(all(a is b for a,b in zip(grid._origin.maps,
            (grid.units,grid.probabilities,grid.menus,grid.prefixes))) and
            grid.digest == grid._origin.digest, 'grid snapshot fields changed')


def freeze_grid(fixture, policy):
    """Copy every visible row, including zero policy/reach rows, exactly once."""
    require(type(fixture) is Fixture and fixture.deck == PROOF9,
            'grid bridge supports only the unchanged PROOF9 fixture')
    require(type(policy) is dict, 'grid input must be a plain complete mapping')
    probabilities = fixture._probabilities(policy)
    units = {k: tuple(v) for k, v in policy.items()}
    menus = {k: tuple(v) for k, v in fixture.menus.items()}
    names = {card_name(c): c for c in PROOF9}
    prefixes = {}
    for key in menus:
        prefix = ()
        for token in key[2]:
            if token.startswith('flop@'):
                require(not prefix and len(token) == 11, 'grid flop grammar')
                prefix = tuple(names[token[i:i+2]] for i in (5, 7, 9))
            elif token.startswith('turn@'):
                require(len(prefix) == 3 and len(token) == 7, 'grid turn grammar')
                prefix += (names[token[5:]],)
            elif token.startswith('river@'):
                require(len(prefix) == 4 and len(token) == 8, 'grid river grammar')
                prefix += (names[token[6:]],)
        prefixes[key] = prefix
    digest = sha256(b'opl-frozen-q52-grid-v1\n')
    for k in sorted(menus):
        payload = [k[0], k[1], k[2], menus[k], units[k]]
        digest.update(json.dumps(payload, separators=(',', ':'), ensure_ascii=True).encode() + b'\n')
    maps = tuple(MappingProxyType(x) for x in (units, probabilities, menus, prefixes))
    digest = digest.hexdigest()
    return FrozenGrid(*maps,digest,_GridOrigin(maps,digest))


def raw_joint_update(fixture, grid):
    """Recover signed deltas without changing the independently written sweep.

    Every terminal utility lies in [-8,8], so |v(a)-v| <= 16.
    Each world visits a given full-history/own-hand row at most once; summing
    its nonnegative world mass times opposite reach over a subset of worlds
    is <=1. Thus each aggregate delta >= -16. Adding 16D prevents CFR+ clipping; subtracting it
    afterwards recovers the raw update. This is NOT a sampled CFR+ proof.
    """
    validate_grid(grid)
    require(fixture.deck == PROOF9 and fixture.denominator == D and
            len(fixture.worlds) == 60 and sum(w.mass for w in fixture.worlds) == 1 and
            all(w.mass > 0 for w in fixture.worlds) and
            all(0 <= v <= 8 for v in fixture.stakes.values()), 'translation lemma preconditions')
    bias = 16 * D
    previous = {k: (bias,) * len(v) for k, v in fixture.menus.items()}
    empty = {k: (0,) * len(v) for k, v in fixture.menus.items()}
    regrets, averages, root = fixture.sweep(grid.units, previous, empty)
    return ({k: tuple(Fraction(v-bias, D) for v in values) for k, values in regrets.items()},
            {k: tuple(Fraction(v, D) for v in values) for k, values in averages.items()}, root)


def reserve_joint_reference(budget):
    """Source-reviewed operation bound for Fixture construction and one sweep.

    At most 66,300 visits and 62,340 action visits: nine Fraction operations
    per action, three per decision, one per terminal, three per world, one per
    grid slot, plus four per output slot and conservative slack. Reduced exact
    operands fit 768 bits (Q52 depth <=12, D642, utilities <=8). An unreduced
    binary operation reserves <=9,222 bits; 10,000 is the reservation per op.
    These are modeled charges, not elapsed time, RSS or CPython allocations.
    """
    operations = 9*62_340 + 4*66_300 + 5*58_164 + 3*60
    budget.charge('joint_reference_reserved', operations + 200_000_000)
    # Existing q-free setup/output envelope <2M, plus 1.7M for Fixture's
    # literal paths/worlds, copied Q52 snapshot and translated input/outputs.
    budget.entries(3_700_000, 'joint reference and frozen snapshot reservation')
    reserved_bits = operations * 10_000 + 2_000_000_000
    require(budget.created_bits + reserved_bits <= budget.limits['created_bits'], 'joint reference bit reservation')
    require(budget.limits['integer_bits'] >= 4096, 'joint reference integer reservation')
    budget.created_bits += reserved_bits
    budget.max_forecast_bits = max(budget.max_forecast_bits, 1537)


def sampled_grid_update(context, admission, grid, budget):
    """One full board estimate; average support depends only on visible cards."""
    validate_grid(grid)
    require(admission.context is context and admission._seal is context._seal,
            'grid admission/context mismatch')
    budget.charge('grid_sample_admission_reserved',4096)
    # Recompute admission, rather than trusting a replaceable dataclass seal.
    require(admission == admit_sampled_board(context, admission.board, admission.proposal_law),
            'grid admission fields changed')
    zero = Fraction(0)
    rows = {}
    root = zero

    def row_for(actor, hand, history, edges):
        key = actor, hand, history
        menu = tuple(e.token for e in edges)
        require(grid.menus.get(key) == menu, 'grid visible row/menu mismatch')
        if key not in rows:
            budget.entries(16 + 4*len(menu) + len(history), 'grid sample row')
            # Also establish policy equality locally. The origin record is an
            # internal provenance guard, not a Python object security boundary.
            units = grid.units[key]
            probabilities = grid.probabilities[key]
            require(len(units)==len(menu)==len(probabilities) and
                    all(type(u) is int and 0<=u<=Q for u in units) and sum(units)==Q,
                    'grid row unit partition')
            for u,p in zip(units,probabilities):
                require(type(p) is Fraction,'grid probability scalar')
                expected = budget.div(budget.input(u,'grid unit'),Fraction(Q),'grid unit probability')
                require(budget.compare(p,expected,'grid same frozen probability')==0,
                        'grid probabilities disagree with frozen units')
            rows[key] = [[zero]*len(menu), [zero]*len(menu)]
        return key, rows[key], grid.probabilities[key]

    def visit(i, history, reaches, chance, sign, holdings):
        budget.charge('grid_regret_visit')
        node = context.nodes[i]
        if node.phase in ('fold', 'showdown'):
            amount = budget.input(node.matched, 'grid terminal stake')
            orient = sign if node.phase == 'showdown' else (1 if node.winner == 0 else -1)
            return budget.mul(amount, Fraction(orient), 'grid terminal orientation')
        if node.phase == 'reveal':
            return visit(node.edges[0].child, (*history, _reveal_token(admission.board, node.reveal_length)),
                         reaches, chance, sign, holdings)
        actor = node.actor
        _, row, probabilities = row_for(actor, holdings[actor], history, node.edges)
        values = []
        for edge, probability in zip(node.edges, probabilities):
            updated = list(reaches)
            updated[actor] = budget.mul(updated[actor], probability, 'grid action reach')
            values.append(visit(edge.child, (*history, edge.token), tuple(updated), chance, sign, holdings))
        mixed = zero
        for probability, value in zip(probabilities, values):
            mixed = budget.add(mixed, budget.mul(probability, value, 'grid mixed value'), 'grid value sum')
        cf = budget.mul(chance, reaches[1-actor], 'grid opposite reach')
        if actor == 1:
            cf = budget.neg(cf, 'grid BB sign')
        for a, value in enumerate(values):
            delta = budget.mul(cf, budget.sub(value, mixed, 'grid advantage'), 'grid raw regret')
            row[0][a] = budget.add(row[0][a], delta, 'grid regret sum')
        return mixed

    for h0, h1 in admission.compatible_pairs:
        hand0, w0 = context.ranges[0][h0]
        hand1, w1 = context.ranges[1][h1]
        ranks = [independent_rank(tuple(card_name(c) for c in (*hand, *admission.board)))
                 for hand in (hand0, hand1)]
        budget.charge('grid_independent_rank', 2*4096)
        chance = budget.div(budget.div(budget.mul(w0, w1, 'grid pair prior'), context.normalizer,
                                      'grid normalized pair'), Fraction(20), 'grid board mass')
        chance = budget.div(chance, admission.board_probability, 'grid inverse board proposal')
        value = visit(context.root, (), (Fraction(1), Fraction(1)), chance,
                      (ranks[0] > ranks[1]) - (ranks[0] < ranks[1]), (h0, h1))
        root = budget.add(root, budget.mul(chance, value, 'grid root mass'), 'grid root sum')

    def average(i, history, player, holding, length, scale, own):
        budget.charge('grid_average_visit')
        node = context.nodes[i]
        if node.phase in ('fold', 'showdown'):
            return
        if node.phase == 'reveal':
            if node.reveal_length <= length:
                average(node.edges[0].child, (*history, _reveal_token(admission.board, node.reveal_length)),
                        player, holding, length, scale, own)
            return
        probabilities = None
        if node.actor == player:
            _, row, probabilities = row_for(player, holding, history, node.edges)
            if node.street == length:
                mass = budget.mul(scale, own, 'grid prefix own reach')
                for a, probability in enumerate(probabilities):
                    row[1][a] = budget.add(row[1][a], budget.mul(mass, probability, 'grid average action'),
                                             'grid average accumulation')
        for a, edge in enumerate(node.edges):
            updated = budget.mul(own, probabilities[a], 'grid average own reach') if probabilities else own
            average(edge.child, (*history, edge.token), player, holding, length, scale, updated)

    for length, player, holding in admission.average_runs:
        scale = budget.div(context.physical.mass(admission.board[:length], player, holding),
                           admission.prefix_probabilities[length], 'grid inverse prefix proposal')
        average(context.root, (), player, holding, length, scale, Fraction(1))
    # Rows from traversal before the requested averaging street can be present
    # with zero contributions. They remain ordinary complete visible rows.
    return rows, root


def complete_expectation(context, grid, law, budget):
    """Exhaust all proposals algebraically, retaining zero-target prefix mass.

    Regret is nonzero only on the 60 compatible boards. Average contribution
    at visible P depends on P alone and carries 1/q(P). Sum q(B) over EVERY
    completion before cancellation. A zero-target B is never redrawn.
    """
    validate_grid(grid)
    require(law in ('uniform', 'river_weighted'), 'unknown grid proposal law')
    proposal = context.physical.proposal_laws[law]
    require(len(context.physical.proposals) == 2520, 'proposal inventory')
    budget.charge('grid_admission_reserved', 2520*4096)
    budget.entries(40_000, 'grid proposal census reservation')
    prefix_q = {}
    positive = []
    for board in context.physical.proposals:
        budget.charge('grid_proposal_census')
        admission = admit_sampled_board(context, board, law)
        q = admission.board_probability
        require(q > 0, 'proposal lost support')
        for length in (0, 3, 4, 5):
            prefix = board[:length]
            prefix_q[prefix] = budget.add(prefix_q.get(prefix, Fraction(0)), q, 'grid proposal prefix sum')
        if admission.compatible_pairs:
            positive.append(admission)
    require(prefix_q == dict(proposal['prefix']) and prefix_q[()] == 1,
            'proposal marginal mismatch')
    require(len(positive) == 60, 'positive full-board census')
    # Count structural proof bookkeeping in addition to Fraction operations.
    regrets = {k: [Fraction(0)]*len(menu) for k, menu in grid.menus.items()}
    averages = {}
    budget.entries(8*58_164 + 8*24_420, 'grid expectation and prefix representatives')
    root = Fraction(0)
    for admission in positive:
        rows, sampled_root = sampled_grid_update(context, admission, grid, budget)
        q = admission.board_probability
        root = budget.add(root, budget.mul(q, sampled_root, 'grid expected root'), 'grid expected root sum')
        for key, (raw, avg) in rows.items():
            for a, value in enumerate(raw):
                regrets[key][a] = budget.add(regrets[key][a], budget.mul(q, value, 'grid expected regret'),
                                             'grid expected regret sum')
            prefix = grid.prefixes[key]
            # A row registered by an earlier reach walk may have no update in
            # this board's prefix runs; only use matching, positive target P.
            if admission.board[:len(prefix)] != prefix:
                continue
            if not context.physical.mass(prefix, key[0], key[1]):
                continue
            value = tuple(budget.mul(prefix_q[prefix], x, 'grid expected prefix average') for x in avg)
            if key in averages:
                require(averages[key] == value, 'average depends on hidden future')
            else:
                averages[key] = value
    require(averages.keys() == grid.menus.keys(), 'positive prefix representatives incomplete')
    return {k: tuple(v) for k, v in regrets.items()}, averages, root


def new_experiment_budget(context, limits=None):
    budget = Budget(limits)
    setup = context.setup_receipt
    budget.charge('grid_context_reserved', setup['work'])
    budget.entries(setup['entries'], 'grid context reservation')
    budget.created_bits = setup['created_bits']
    budget.max_forecast_bits = setup['max_integer_bits']
    reserve_joint_reference(budget)
    return budget
