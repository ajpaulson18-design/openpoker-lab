"""Independent literal single-deal oracle for three changing-policy draws."""
import os
from fractions import Fraction
from itertools import combinations, permutations
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts.preflop_validation import independent_rank
from tests.full_deck_public_chance_reference import card_name
from tests.test_native_exact_reach import ROOT, authenticate
from tests.virtual_betting_template_reference import build_reference_template
from tests.virtual_frozen_run_control import run_bounded_child
from tests.virtual_frozen_sample_reference import _reveal_token, _snapshot_template
from tests.virtual_frozen_update_reference import _template_case


GRID = 1 << 52
HANDS = ((0, 1), (2, 3))
DRAWS = ((4, 5, 6, 7, 8), (4, 5, 6, 7, 8), (4, 5, 6, 7, 0))
EXECUTABLE = os.environ.get('OPENPOKER_NATIVE_SAMPLED_GRID_EXECUTABLE')


def _uniform_boards(cards):
    for flop in combinations(cards, 3):
        for turn, river in permutations(tuple(card for card in cards if card not in flop), 2):
            yield (*flop, turn, river)


def _grid(regrets):
    weights = tuple(max(0, value) for value in regrets)
    total = sum(weights)
    target = tuple(Fraction(weight, total) * GRID if total else Fraction(GRID, len(weights))
                   for weight in weights)
    units = [int(value) for value in target]
    order = sorted(range(len(units)), key=lambda a: (-(target[a] - units[a]), a))
    for action in order[:GRID - sum(units)]:
        units[action] += 1
    return tuple(units)


def _model():
    case = _template_case()
    case['config']['starting_stack'] = 2.0
    later = {'bet_sizes': [0.5], 'raise_sizes': [], 'max_raises': 0, 'include_all_in': True}
    for street in ('flop', 'turn', 'river'):
        case[f'{street}_config'] = dict(later)
    template = build_reference_template(case)
    return template.root, _snapshot_template(template)


def _literal_draw(root, nodes, board, committed):
    rows = {}
    deal = tuple(_uniform_boards(range(4, 9)))
    proposal = tuple(_uniform_boards(range(9)))
    prefix_scale = {}
    for n in (0, 3, 4, 5):
        physical = sum(candidate[:n] == board[:n] for candidate in deal)
        sampled = sum(candidate[:n] == board[:n] for candidate in proposal)
        prefix_scale[n] = Fraction(physical * len(proposal), len(deal) * sampled)

    sign = 0
    if prefix_scale[5]:
        one, two = (independent_rank(tuple(map(card_name, (*hand, *board)))) for hand in HANDS)
        sign = (one > two) - (one < two)

    def visit(index, history, reaches):
        node = nodes[index]
        if node.phase == 'showdown':
            return Fraction(node.matched) * sign * prefix_scale[5]
        if node.phase == 'fold':
            return Fraction(node.matched) * (1 if node.winner == 0 else -1) * prefix_scale[node.street]
        if node.phase == 'reveal':
            return visit(node.edges[0].child, (*history, _reveal_token(board, node.reveal_length)),
                         reaches)
        actor = node.actor
        key = (actor, HANDS[actor], history)
        actions = tuple(edge.token for edge in node.edges)
        units = _grid(committed.get(key, (0,) * len(actions)))
        probabilities = tuple(Fraction(unit, GRID) for unit in units)
        children = []
        for edge, probability in zip(node.edges, probabilities, strict=True):
            following = list(reaches)
            following[actor] *= probability
            children.append(visit(edge.child, (*history, edge.token), following))
        mixed = sum(child * probability for child, probability in zip(children, probabilities, strict=True))
        scale = prefix_scale[node.street]
        if scale:
            if key in rows:
                raise ValueError('independent model replaced a full-history row')
            average = scale * reaches[actor]
            orientation = 1 if actor == 0 else -1
            regrets = tuple((child - mixed) * reaches[1 - actor] * orientation for child in children)
            rows[key] = (actions, units, regrets, average, tuple(average * p for p in probabilities))
        return mixed

    visit(root, (), (Fraction(1), Fraction(1)))
    return rows


def _read_rows(lines, count, regret_d):
    rows = {}
    for _ in range(count):
        parts = next(lines).split()
        if parts[0] != 'ROW':
            raise ValueError('missing native row')
        actor, first, second, depth = map(int, parts[1:5])
        history = tuple(parts[5:5 + depth])
        count, denom, mass = map(int, parts[5 + depth:8 + depth])
        fields = parts[8 + depth:]
        if len(fields) != 4 * count:
            raise ValueError('inconsistent native row width')
        key = (actor, (first, second), history)
        if key in rows:
            raise ValueError('duplicate native row')
        rows[key] = (tuple(fields[::4]), tuple(map(int, fields[1::4])),
                     tuple(Fraction(int(x), regret_d) for x in fields[2::4]),
                     Fraction(mass, denom), tuple(Fraction(int(x), denom) for x in fields[3::4]))
    return rows


@unittest.skipUnless(EXECUTABLE, 'explicit source-built changing-policy controls required')
class NativeSampledGridTests(unittest.TestCase):
    def test_direct_draws_against_signed_literal_reference(self):
        self._check_draws('sampled-grid', 'direct')

    def test_prepared_draws_against_signed_literal_reference(self):
        self._check_draws('sampled-grid-prepared', 'prepared')

    def _check_draws(self, mode, suffix):
        executable = Path(EXECUTABLE).resolve()
        identity = authenticate(executable, ROOT, 'virtual-frozen-update-controls')
        destination = os.environ.get('OPENPOKER_NATIVE_SAMPLED_GRID_CONTROL_DIR')
        temporary = None
        if destination is None:
            temporary = TemporaryDirectory()
            self.addCleanup(temporary.cleanup)
            destination = temporary.name
        directory = Path(destination).resolve() / suffix
        directory.parent.mkdir(parents=True, exist_ok=True)
        receipt = run_bounded_child([str(executable), mode], b'', directory,
                                    stdout_limit=1 << 20, timeout=45)
        self.assertTrue(receipt['actual_exit_observed'])
        self.assertFalse(receipt['failures'])
        self.assertEqual(receipt['returncode'], 0, (directory / 'stderr.bin').read_bytes())
        self.assertEqual((directory / 'stderr.bin').read_bytes(), b'')
        self.assertEqual(authenticate(executable, ROOT, 'virtual-frozen-update-controls'), identity)
        lines = iter((directory / 'stdout.bin').read_text(encoding='ascii').splitlines())
        root, nodes = _model()
        committed = {}
        first_policy = None
        saw_changed = saw_zero_with_regret = saw_negative = False
        for draw, board in enumerate(DRAWS):
            fields = next(lines).split()
            self.assertEqual(fields[0], 'DRAW')
            index, rows, regret_d, bound, chance, history, arithmetic, average, quantizer, ranks = map(int, fields[1:])
            if mode == 'sampled-grid-prepared':
                self.assertEqual(ranks, 1 if draw == 2 else 2)
            else:
                self.assertEqual(ranks, 0)
            self.assertEqual(index, draw)
            self.assertLessEqual(chance + history + arithmetic + average + quantizer, bound)
            self.assertLessEqual(bound, 500_000_000)
            actual = _read_rows(lines, rows, regret_d)
            expected = _literal_draw(root, nodes, board, committed)
            self.assertEqual(actual, expected, f'draw {draw}')
            if draw == 0:
                first_policy = {key: row[1] for key, row in expected.items()}
            for key, row in expected.items():
                _, policy, regrets, _, _ = row
                saw_changed |= draw > 0 and key in first_policy and policy != first_policy[key]
                saw_zero_with_regret |= any(p == 0 and r != 0 for p, r in zip(policy, regrets, strict=True))
                old = committed.get(key, (0,) * len(regrets))
                committed[key] = tuple(a + b for a, b in zip(old, regrets, strict=True))
                saw_negative |= any(r < 0 for r in committed[key])
        self.assertIsNone(next(lines, None))
        self.assertTrue(saw_changed and saw_zero_with_regret and saw_negative)
