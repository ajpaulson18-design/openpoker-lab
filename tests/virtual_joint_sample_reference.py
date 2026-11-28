"""Deterministic true-joint chance-sample expectation gate, fixed PROOF9 only.

There is no RNG, native operator, learner or quality calculation here. One
sample exhausts betting actions for one selected private pair and complete
board. The separate literal Fixture sweep is the expectation authority.
"""
from collections import Counter
from dataclasses import dataclass
from fractions import Fraction
from math import comb, lcm
from types import MappingProxyType

from scripts.matrix_free_certificate_budget import Budget
from scripts.preflop_validation import independent_rank
from tests.full_deck_public_chance_reference import PROOF9, card_name
from tests.virtual_dyadic_training_reference import Fixture, Q
from tests.virtual_frozen_update_reference import scaled_proof9_ranges
from tests.virtual_grid_update_reference import freeze_grid, raw_joint_update, validate_grid
# Reuse only the established frozen profile factory, never its public-board
# law, estimator, expectation calculation or result as a numerical authority.
from tests.virtual_target_board_reference import fixed_profile


REGRET_DENOMINATOR = 1 << 625
AVERAGE_DENOMINATOR = 1 << 364
MEAN_TICKETS = 580
MAX_SAMPLE_CALLS = 64
LIMITS = {'work': 500_000_000, 'entries': 8_000_000,
          'created_bits': 16_000_000_000, 'integer_bits': 4096}
# Fixture.sweep performs <=9 operations/action, 3/decision, 1/terminal,
# and 3/world: 9*62340 + 3*26040 + 36360 + 180 = 675720.
LITERAL_FRACTION_OPS = 675_720
SAMPLE_FRACTION_OPS = 500_000
WORK_UPPER = 250_000_000
ENTRIES_UPPER = 7_000_000
# Logical cells/descriptors, with borrowed immutable policy/menu references
# charged in the source snapshot. Per returned sample, 64 cells/row cover the
# row dictionary/key/descriptor and <=15 visible-history token references;
# 8 cells/action cover both integer numerators and their tuple containers.
# This covers callers retaining all 64 results (the hidden-information test
# retains three); complete_expectation itself streams one result at a time.
ENTRY_PARTITION = MappingProxyType({
    'fixture_grid_literal': 3_700_000,  # Existing reserve_joint_reference envelope.
    'retained_64_scalar_results': MAX_SAMPLE_CALLS * (64 * 434 + 8 * 1039),
    'two_integer_accumulators': 500_000,  # >=2*(4*24420+2*58164)=428016.
    'ticket_and_prefix_metadata': 100_000,  # Two <=480-key groups, <=60 worlds.
    'owner_recursion_comparison_scratch': 300_000,
})
# The existing source-reviewed Fixture/setup allowance is 200M work/2B bits.
# Reduced dyadic/joint operands have <=640-bit numerator/denominator; a
# cross-multiplied binary operation reserves <=8000 created bits and <2048
# intermediate bits. 64 scalar walks need <=64*(6*1039+434+606)=465536
# Fraction operations. The 4B tail covers <=134k sample integer conversions,
# <=125k weighted integer accumulations, row centering/factor checks, <=350k
# output Fraction constructors/comparisons, and <=24420*15 visible-key replay
# steps plus their <=7 own-policy integer products. Returned tables may remain
# retained within ENTRY_PARTITION. This is logical accounting, not Python/RSS.
CREATED_BITS_UPPER = 2_000_000_000 + 8000 * (LITERAL_FRACTION_OPS + SAMPLE_FRACTION_OPS) + 4_000_000_000
INTERMEDIATE_BITS_UPPER = 2048


def require(value, message):
    if not value:
        raise ValueError(message)


def board_count(deck_size):
    require(type(deck_size) is int and 9 <= deck_size <= 52, 'joint board deck size')
    n = deck_size - 4
    return comb(n, 3) * (n - 3) * (n - 4)


def unrank_board(deck, excluded, rank):
    """Lexicographic canonical flop, then ordered turn/river; no board table."""
    require(type(deck) is tuple and len(deck) == len(set(deck)) and
            tuple(sorted(deck)) == deck and all(type(c) is int and 0 <= c < 52 for c in deck),
            'joint board canonical deck')
    require(type(excluded) is tuple and len(excluded) == len(set(excluded)) == 4 and
            set(excluded) <= set(deck), 'joint board private cards')
    require(type(rank) is int and 0 <= rank < board_count(len(deck)), 'joint board rank')
    left = tuple(card for card in deck if card not in excluded)
    flop_rank, tail = divmod(rank, (len(left) - 3) * (len(left) - 4))
    chosen, start = [], 0
    for position in range(3):
        for index in range(start, len(left)):
            count = comb(len(left) - index - 1, 2 - position)
            if flop_rank < count:
                chosen.append(left[index]); start = index + 1
                break
            flop_rank -= count
        else:
            raise ValueError('joint flop unranking incomplete')
    rest = [card for card in left if card not in chosen]
    turn, river = divmod(tail, len(rest) - 1)
    turn_card = rest.pop(turn)
    return (*chosen, turn_card, rest[river])


@dataclass(frozen=True)
class JointLaw:
    ranges: tuple
    weights: tuple
    compatible: tuple
    normalizer: int
    _origin: tuple
    _seal: object


def build_law():
    """O(H0+H1) pair masses using total-minus-card-minus-card-plus-same.

    The ranges stay in original order. Duplicate physical holdings reject,
    matching the input contract; identical visible histories are not deduped.
    """
    ranges = scaled_proof9_ranges()
    require(tuple(map(len, ranges)) == (2, 2), 'joint fixed original holding counts')
    scale = lcm(*(weight.denominator for side in ranges for _hand, weight in side))
    weights = tuple(tuple(int(weight * scale) for _hand, weight in side) for side in ranges)
    require(weights == ((1, 6), (3, 8)), 'joint exact positive prior weights')
    for side in ranges:
        require(len({hand for hand, _weight in side}) == len(side) and
                all(type(hand) is tuple and len(hand) == 2 and hand[0] < hand[1] and
                    set(hand) <= set(PROOF9) and weight > 0 for hand, weight in side),
                'joint original holding identities')
    total = sum(weights[1]); cards = [0] * 52; same = {}
    for (hand, _weight), integer in zip(ranges[1], weights[1]):
        cards[hand[0]] += integer; cards[hand[1]] += integer; same[hand] = integer
    compatible = tuple(total - cards[hand[0]] - cards[hand[1]] + same.get(hand, 0)
                       for hand, _weight in ranges[0])
    normalizer = sum(a * mass for a, mass in zip(weights[0], compatible))
    require(compatible == (11, 3) and normalizer == 29, 'joint blocker-conditioned normalizer')
    origin = (ranges, weights, compatible, normalizer)
    return JointLaw(ranges, weights, compatible, normalizer, origin, object())


def validate_law(law):
    require(type(law) is JointLaw and len(law._origin) == 4 and
            all(a is b for a, b in zip((law.ranges, law.weights, law.compatible), law._origin[:3])) and
            law.normalizer == law._origin[3] == 29, 'joint law immutable snapshot')


@dataclass(frozen=True)
class JointSample:
    pair_ticket: int
    board_rank: int
    holdings: tuple
    board: tuple
    mass: int
    _seal: object


def ticket(law, pair_ticket, board_rank):
    """Decode an exact private-pair ticket and independent uniform board rank.

    One integer in [0,Z) suffices for both private selections. Within the SB
    interval divide the local offset by its integer weight, then scan compatible
    BB weights. This introduces neither an H0*H1 pair table nor conditional RNG.
    """
    validate_law(law)
    require(type(pair_ticket) is int and 0 <= pair_ticket < law.normalizer, 'joint pair ticket')
    require(type(board_rank) is int and 0 <= board_rank < 20, 'joint board rank')
    local = pair_ticket
    for i, (weight, compatible) in enumerate(zip(law.weights[0], law.compatible)):
        span = weight * compatible
        if local < span:
            break
        local -= span
    else:
        raise ValueError('joint private first interval')
    own = law.ranges[0][i][0]; remaining = local // weight
    for j, ((opposite, _raw), other_weight) in enumerate(zip(law.ranges[1], law.weights[1])):
        if set(own).isdisjoint(opposite):
            if remaining < other_weight:
                break
            remaining -= other_weight
    else:
        raise ValueError('joint private compatible interval')
    board = unrank_board(tuple(PROOF9), (*own, *opposite), board_rank)
    return JointSample(pair_ticket, board_rank, (i, j), board,
                       law.weights[0][i] * law.weights[1][j], law._seal)


def inventory(law):
    """60 unique worlds with multiplicities from all 580 deterministic tickets."""
    counts, representatives = Counter(), {}
    for private in range(29):
        for board in range(20):
            sample = ticket(law, private, board)
            key = sample.holdings, sample.board
            counts[key] += 1; representatives.setdefault(key, sample)
    require(len(counts) == 60 and sum(counts.values()) == MEAN_TICKETS and
            all(counts[key] == sample.mass for key, sample in representatives.items()) and
            Counter(counts.values()) == {3: 20, 8: 20, 18: 20}, 'joint full ticket multiplicities')
    return tuple((sample, counts[key]) for key, sample in representatives.items())


def _reveal(board, length):
    if length == 3:
        return 'flop@' + ''.join(card_name(card) for card in board[:3])
    if length in (4, 5):
        return ('turn@' if length == 4 else 'river@') + card_name(board[length - 1])
    raise ValueError('joint visible reveal length')


@dataclass(frozen=True)
class SampleRow:
    regrets: tuple
    averages: tuple
    units: tuple
    prior_own_actions: int


@dataclass(frozen=True)
class SampleResult:
    rows: object
    root: int
    visits: int
    actions: int
    reveals: int
    terminals: int
    zero_own_nonzero_regret_rows: int
    zero_policy_nonzero_regret_slots: int


class Request:
    """One preadmitted profile experiment, one literal sweep, <=64 scalar walks."""
    def __init__(self, profile='uniform', limits=None):
        require(profile in ('uniform', 'zero-skew'), 'joint fixed frozen profile')
        require(limits is None or type(limits) is dict and set(limits) <= set(LIMITS),
                'joint reduce-only request limits')
        chosen = dict(LIMITS)
        for name, value in (limits or {}).items():
            require(type(value) is int and 0 < value <= LIMITS[name], 'joint limits are reduce-only')
            chosen[name] = value
        require(WORK_UPPER <= chosen['work'] and ENTRIES_UPPER + 16 <= chosen['entries'] and
                sum(ENTRY_PARTITION.values()) <= ENTRIES_UPPER and
                CREATED_BITS_UPPER <= chosen['created_bits'] and
                INTERMEDIATE_BITS_UPPER <= chosen['integer_bits'], 'joint full request admission rejected')
        self.budget = Budget(chosen)
        self.budget.charge('joint_whole_request_reserved', WORK_UPPER)
        self.budget.entries(ENTRIES_UPPER, 'joint complete request tables and streamed scalar scratch')
        self.budget.created_bits = CREATED_BITS_UPPER
        self.budget.max_forecast_bits = INTERMEDIATE_BITS_UPPER
        # All source/private/rank/grid construction follows complete admission.
        self.fixture = Fixture()
        self.grid = freeze_grid(self.fixture, fixed_profile(self.fixture, profile))
        self.law = build_law(); self.profile = profile
        self.sample_calls = 0; self.fraction_ops = 0; self.expectation_entered = False
        require(self.fixture.deck == PROOF9 and len(self.fixture.paths) == 1105 and
                len(self.fixture.menus) == 24420 and sum(map(len, self.fixture.menus.values())) == 58164 and
                all(0 <= stake <= 8 and (2 * stake).denominator == 1
                    for stake in self.fixture.stakes.values()), 'joint fixed source and stake admission')

    def fraction(self, operation, a, b=None):
        require(self.fraction_ops < SAMPLE_FRACTION_OPS and type(a) is Fraction and
                (b is None or type(b) is Fraction), 'joint scalar Fraction operation cap')
        an, ad = max(1, abs(a.numerator).bit_length()), a.denominator.bit_length()
        if operation == 'neg':
            sizes = an, ad
        else:
            bn, bd = max(1, abs(b.numerator).bit_length()), b.denominator.bit_length()
            if operation in ('add', 'sub'):
                largest = max(an + bd, bn + ad) + 1
                sizes = an + bd, bn + ad, largest, ad + bd, largest, ad + bd
            else:
                require(operation == 'mul', 'joint scalar operation')
                sizes = an + bn, ad + bd, an + bn, ad + bd
        require(max(sizes) <= INTERMEDIATE_BITS_UPPER and sum(sizes) <= 8000,
                'joint scalar intermediate exceeds prepaid bit forecast')
        self.fraction_ops += 1
        if operation == 'add':
            return a + b
        if operation == 'sub':
            return a - b
        if operation == 'neg':
            return -a
        return a * b


def _scaled(value, power, magnitude):
    require(type(value) is Fraction and value.denominator & (value.denominator - 1) == 0 and
            value.denominator <= 1 << power, 'joint pure-power sample denominator')
    result = value.numerator << (power - (value.denominator.bit_length() - 1))
    require(abs(result).bit_length() <= magnitude, 'joint sample integer magnitude')
    return result


def one_sample(request, sample):
    require(type(request) is Request, 'joint admitted request owner')
    validate_grid(request.grid); validate_law(request.law)
    require(type(sample) is JointSample and sample._seal is request.law._seal and
            sample == ticket(request.law, sample.pair_ticket, sample.board_rank), 'joint sample owner or selector changed')
    require(request.sample_calls < MAX_SAMPLE_CALLS, 'joint scalar sample count cap')
    request.sample_calls += 1
    fixture, grid = request.fixture, request.grid
    hands = tuple(request.law.ranges[a][sample.holdings[a]][0] for a in (0, 1))
    ranks = tuple(independent_rank(tuple(card_name(c) for c in (*hand, *sample.board))) for hand in hands)
    sign = (ranks[0] > ranks[1]) - (ranks[0] < ranks[1])
    rows = {}; visits = actions = reveals = terminals = slots = 0
    zero_own = zero_policy = 0
    op = request.fraction

    def visit(node_id, history, r0, r1, own_depth):
        nonlocal visits, actions, reveals, terminals, slots, zero_own, zero_policy
        visits += 1; require(visits <= 1105, 'joint scalar visit cap')
        node = fixture.nodes[node_id]
        if node.phase in ('fold', 'showdown'):
            terminals += 1
            orient = sign if node.phase == 'showdown' else (1 if node.state.winner == 0 else -1)
            stake = fixture.stakes[node_id]
            return op('neg', stake) if orient < 0 else stake if orient else Fraction(0)
        if node.phase == 'reveal':
            reveals += 1
            return visit(node.edges[0].child, (*history, _reveal(sample.board, node.state.board_length)),
                         r0, r1, own_depth)
        actor = node.state.player
        key = actor, sample.holdings[actor], history
        menu = tuple(edge.token for edge in node.edges)
        require(key not in rows and grid.menus.get(key) == menu and 2 <= len(menu) <= 4,
                'joint own holding and visible information row')
        require(len(rows) < 434 and slots + len(menu) <= 1039, 'joint selected-row capacity')
        slots += len(menu)
        # The only policy lookup arguments are actor, its original own holding,
        # and visible history. Opponent/future cards never enter this key.
        units = grid.units[key]; probabilities = grid.probabilities[key]
        own, opposite = (r0, r1) if actor == 0 else (r1, r0)
        depth = own_depth[actor]
        require(0 <= depth <= 6, 'joint prior own-action depth')
        values = []
        for index, edge in enumerate(node.edges):
            actions += 1
            advanced = op('mul', own, probabilities[index])
            next_depth = list(own_depth); next_depth[actor] += 1
            values.append(visit(edge.child, (*history, edge.token),
                                advanced if actor == 0 else r0,
                                advanced if actor == 1 else r1, tuple(next_depth)))
        mixed = Fraction(0)
        for probability, value in zip(probabilities, values):
            mixed = op('add', mixed, op('mul', probability, value))
        cf = opposite if actor == 0 else op('neg', opposite)
        regrets = tuple(_scaled(op('mul', cf, op('sub', value, mixed)), 625, 630) for value in values)
        averages = tuple(_scaled(op('mul', own, probability), 364, 365) for probability in probabilities)
        require(sum(r * u for r, u in zip(regrets, units)) == 0 and
                all(r % (1 << (52 * depth)) == 0 for r in regrets) and
                all(a >= 0 and a % (1 << (312 - 52 * depth)) == 0 for a in averages),
                'joint row centering or certified factors')
        zero_own += int(own == 0 and any(regrets))
        zero_policy += sum(unit == 0 and regret != 0 for unit, regret in zip(units, regrets))
        rows[key] = SampleRow(regrets, averages, units, depth)
        return mixed

    try:
        root = visit(fixture.template.root, (), Fraction(1), Fraction(1), (0, 0))
    finally:
        # Break the recursive closure cycle promptly; otherwise each discarded
        # scalar walk could retain its entire row table until cyclic GC runs.
        visit = None
    require((visits, actions, reveals, terminals, len(rows), slots) == (1105, 1039, 65, 606, 434, 1039),
            'joint complete scalar betting coverage')
    return SampleResult(MappingProxyType(rows), _scaled(root, 625, 629), visits, actions, reveals,
                        terminals, zero_own, zero_policy)


def prefix_ticket_counts(law):
    counts = Counter()
    for private in range(29):
        for rank in range(20):
            sample = ticket(law, private, rank)
            for actor in (0, 1):
                for length in (0, 3, 4, 5):
                    counts[actor, sample.holdings[actor], sample.board[:length]] += 1
    require(all(0 < count <= MEAN_TICKETS for count in counts.values()), 'joint prefix ticket mass')
    return counts


def _own_product(fixture, grid, key):
    """Replay only the visible row key, without opponent or future cards."""
    actor, holding, history = key
    node_id = fixture.template.root; past = (); product = 1; depth = 0
    for token in history:
        node = fixture.nodes[node_id]
        if node.phase == 'reveal':
            require(token.startswith({3: 'flop@', 4: 'turn@', 5: 'river@'}[node.state.board_length]),
                    'joint prefix replay reveal')
            node_id = node.edges[0].child
        else:
            require(node.phase == 'decision', 'joint prefix replay decision')
            edge_index = next((i for i, edge in enumerate(node.edges) if edge.token == token), None)
            require(edge_index is not None, 'joint prefix replay legal edge')
            if node.state.player == actor:
                product *= grid.units[actor, holding, past][edge_index]; depth += 1
            node_id = node.edges[edge_index].child
        past += (token,)
    require(fixture.nodes[node_id].phase == 'decision' and fixture.nodes[node_id].state.player == actor and depth <= 6,
            'joint prefix replay terminal row')
    return product, depth


def complete_expectation(request):
    """Stream 60 scalar results; compare every mean coordinate to literal CFR."""
    require(type(request) is Request and not request.expectation_entered, 'joint complete expectation is one-shot')
    request.expectation_entered = True
    fixture, grid, law = request.fixture, request.grid, request.law
    worlds = inventory(law)
    ticket_prefix = prefix_ticket_counts(law)
    # Separate grouping authority: Fixture constructs its literal worlds from
    # numeric rules and physical combinations, not the ticket decoder above.
    literal_prefix = {}
    for world in fixture.worlds:
        for actor in (0, 1):
            for length in (0, 3, 4, 5):
                key = actor, world.holdings[actor], world.board[:length]
                literal_prefix[key] = literal_prefix.get(key, Fraction(0)) + world.mass
    require(set(ticket_prefix) == set(literal_prefix) and
            all(Fraction(ticket_prefix[key], MEAN_TICKETS) == mass for key, mass in literal_prefix.items()),
            'joint independently grouped prefix marginal')
    rsum = {key: [0] * len(menu) for key, menu in fixture.menus.items()}
    asum = {key: [0] * len(menu) for key, menu in fixture.menus.items()}
    root = 0; maximum_r = maximum_a = zero_own = zero_policy = 0
    for sample, multiplicity in worlds:
        result = one_sample(request, sample)
        root += multiplicity * result.root
        zero_own += result.zero_own_nonzero_regret_rows
        zero_policy += result.zero_policy_nonzero_regret_slots
        for key, row in result.rows.items():
            for index, value in enumerate(row.regrets):
                maximum_r = max(maximum_r, abs(value).bit_length())
                rsum[key][index] += multiplicity * value
            for index, value in enumerate(row.averages):
                maximum_a = max(maximum_a, value.bit_length())
                asum[key][index] += multiplicity * value
        del result  # Never retain the 60 raw row tables together.
    expected_r, expected_a, expected_root = raw_joint_update(fixture, grid)
    require(Fraction(root, MEAN_TICKETS * REGRET_DENOMINATOR) == expected_root, 'joint literal root expectation')
    for key, menu in fixture.menus.items():
        require(tuple(Fraction(value, MEAN_TICKETS * REGRET_DENOMINATOR) for value in rsum[key]) == expected_r[key],
                'joint all-row literal raw regret expectation')
        require(tuple(Fraction(value, MEAN_TICKETS * AVERAGE_DENOMINATOR) for value in asum[key]) == expected_a[key],
                'joint all-row literal raw average expectation')
        product, depth = _own_product(fixture, grid, key)
        prefix_mass = ticket_prefix[key[0], key[1], grid.prefixes[key]]
        direct = tuple(prefix_mass * product * unit << (312 - 52 * depth) for unit in grid.units[key])
        require(tuple(asum[key]) == direct, 'joint direct prefix-marginal average identity')
    require(request.sample_calls <= MAX_SAMPLE_CALLS and request.fraction_ops <= SAMPLE_FRACTION_OPS,
            'joint full request operation census')
    return {'profile': request.profile, 'literal_expectation_match': True, 'prefix_marginal_match': True,
            'rows': len(fixture.menus), 'slots': sum(map(len, fixture.menus.values())),
            'worlds': len(worlds), 'tickets': MEAN_TICKETS, 'sample_calls': request.sample_calls,
            'sample_rows': 434, 'sample_slots': 1039,
            'maximum_sample_regret_bits': maximum_r, 'maximum_sample_average_bits': maximum_a,
            'zero_own_nonzero_regret_rows': zero_own, 'zero_policy_nonzero_regret_slots': zero_policy,
            'root': expected_root, 'resource_accounting': request.budget.receipt(),
            'scalar_fraction_operations': request.fraction_ops, 'rng_calls': 0, 'native_calls': 0,
            'training_iterations': 0, 'quality_gate': None,
            'scope': 'deterministic fixed-PROOF9 frozen-Q52 joint-sample expectation; no RNG/native/full52 admission'}
