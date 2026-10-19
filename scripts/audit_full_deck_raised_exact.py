"""Exact normalized-policy audit for one fixed full-deck raised turn game.

No training is imported. A checked public-chance quotient retains all physical
mass; this is not conditioning the game on five selected river cards.
"""
import argparse
from collections import defaultdict
from copy import deepcopy
from fractions import Fraction as F
from hashlib import sha256
import json
from math import isfinite
import os
from pathlib import Path
import tempfile

from scripts import full_deck_raised_reference as reference
from scripts import turn_rational_certificate as exact
from scripts import turn_river_validation as rules


ROOT = reference.ROOT
BASELINE = ROOT / 'benchmarks/results/full-deck-raised-turn-benchmark-v1.json'
POLICIES = ROOT / 'benchmarks/results/full-deck-raised-turn-policies-v1'
REPORT = ROOT / 'benchmarks/results/full-deck-raised-turn-exact-audit-v1.json'
BASELINE_SHA256 = '4381b2fbb7008572ff0993d005ee6d2d8dd00c6f9a38621d65b9621b469a9669'
REFERENCE_SHA256 = 'bff6aaf4d2bf6038503645787d66cff9f57bcb1385e334364f72126a67211165'
MAX_REPORT_BYTES = 8_000_000
MAX_POLICY_BYTES = 2_000_000
CLASSES = {'3c': (), 'As': ('As', 'Ah'), 'Ac': ('Ac', 'Ad'),
           'Ks': ('Ks', 'Kh'), 'Kc': ('Kc', 'Kd')}
SOURCES = tuple(sorted(set(reference.SOURCE_PATHS) | {
    'scripts/turn_rational_certificate.py', 'scripts/audit_full_deck_raised_exact.py',
    'tests/test_full_deck_raised_exact.py'}))


def need(ok, message):
    if not ok:
        raise ValueError(message)


def canonical(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()


def bounded(path, cap):
    path = Path(path)
    need(path.stat().st_size <= cap, 'Artifact exceeds pre-read byte cap')
    raw = path.read_bytes()
    need(len(raw) <= cap, 'Artifact grew beyond byte cap')
    return raw


def fingerprints():
    return {p: sha256((ROOT / p).read_bytes().replace(b'\r\n', b'\n')).hexdigest()
            for p in SOURCES}


def guard(sources, head):
    need(fingerprints() == sources and reference.head() == head,
         'Audit source or HEAD changed')


def representative(card):
    need(type(card) is str and card in rules.DECK and card not in rules.cards(reference.FIXTURE['board']),
         'Invalid physical river for fixed quotient')
    return next((key for key, members in CLASSES.items() if card in members), '3c')


def projected_history(history):
    return tuple('river@' + representative(token[6:]) if token.startswith('river@')
                 else token for token in history)


def projected_shape(root):
    """Check every original action/terminal, including off-policy branches."""
    visits = 0

    def visit(node, depth):
        nonlocal visits
        visits += 1
        need(visits <= 3039 and depth <= 9, 'Fixed quotient tree envelope exceeded')
        if isinstance(node, rules._Terminal):
            return ['terminal', node.kind, node.winner, list(node.contributions)]
        if isinstance(node, rules._Chance):
            groups = {}
            for card, child in sorted(node.branches.items()):
                value, key = visit(child, depth + 1), representative(card)
                need(key not in groups or groups[key] == value,
                     'Public subtrees are not class-isomorphic')
                groups[key] = value
            return ['chance', list(projected_history(node.history)), sorted(groups.items())]
        need(isinstance(node, rules._Decision), 'Unknown quotient public node')
        need(len(node.actions) == len(node.children) and len(node.actions) > 0,
             'Malformed public action/child coverage')
        board = list(node.board)
        if len(board) == 5:
            board[-1] = representative(board[-1])
        return ['decision', node.player, list(projected_history(node.history)), board,
                [[a.name, a.token, a.amount, a.raise_to, visit(c, depth + 1)]
                 for a, c in zip(node.actions, node.children)]]

    return visit(root, 1)


def quotient_model(model):
    f, board, config, worlds, selected, root, _ = model
    need(f == reference.FIXTURE and tuple(board) == rules.cards(f['board']) and
         config.to_dict() == rules._config(f['config'], 'config').to_dict() and
         len(worlds) == 176 and len(selected) == 48 and
         set(selected) == set(rules.DECK) - set(board), 'Wrong fixed physical model')
    groups, support, seen = {}, defaultdict(set), set()
    for world in worlds:
        hands, river = world['hands'], world['river']
        identity = hands, river
        need(identity not in seen, 'Duplicate original physical world')
        seen.add(identity)
        pair = tuple(''.join(h) for h in hands)
        need(pair in reference.EXPECTED_PAIRS and
             world['weight'] == reference.EXPECTED_PAIRS[pair][0] / 44 and
             world['board'] == tuple(board) + (river,) and
             not (set(board) | set(hands[0]) | set(hands[1])) & {river},
             'Original physical law or card support changed')
        rank0, rank1 = (reference.best_five_rank(world['board'] + hand) for hand in hands)
        need(type(world['sign']) is int and world['sign'] == (rank0 > rank1) - (rank0 < rank1),
             'Physical showdown sign differs from exhaustive best-five ranking')
        key = hands, representative(river)
        support[key].add(river)
        if key not in groups:
            reduced = deepcopy(world)
            reduced.update(river=key[1], board=tuple(board) + (key[1],), weight=F(0))
            groups[key] = reduced
        reduced = groups[key]
        need(reduced['sign'] == world['sign'], 'A class changes showdown sign')
        reduced['weight'] += world['weight']
    class_support = defaultdict(list)
    for (_, card), rivers in support.items():
        class_support[card].append(rivers)
    need(set(class_support) == set(CLASSES), 'Quotient class set changed')
    for card, sets in class_support.items():
        need(all(s == sets[0] for s in sets),
             'Within-class card reveals additional private-pair information')
        need(len(sets[0]) == (40 if card == '3c' else 2), 'Class multiplicity changed')
    reduced_worlds = list(groups.values())
    need(len(reduced_worlds) == 12 and sum((w['weight'] for w in reduced_worlds), F(0)) == 1,
         'Quotient does not retain complete normalized mass')
    reduced_root = rules._public_tree(board, config, config, tuple(sorted(CLASSES)), reduced_worlds)
    need(projected_shape(root) == projected_shape(reduced_root),
         'Quotient public action/terminal structure differs')
    return reduced_worlds, reduced_root


def project_policy(result, policies, reduced_worlds, reduced_root):
    mapped, rows = {}, {}
    for (player, hand, history), probabilities in policies.items():
        key = player, hand, projected_history(history)
        need(key not in mapped or mapped[key] == probabilities,
             'Policy probabilities are not exactly class-constant')
        mapped[key] = probabilities
    for source in result['strategy']:
        row = deepcopy(source)
        row['history'] = list(projected_history(row['history']))
        if len(row['board']) == 5:
            row['board'][-1] = representative(row['board'][-1])
        key = row['player'], row['hand'], tuple(row['history'])
        need(key not in rows or rows[key] == row, 'Class policy metadata differs')
        rows[key] = row
    expected = set()
    for node in rules._collect_nodes(reduced_root):
        for world in reduced_worlds:
            if world['board'][:len(node.board)] == node.board:
                hand = world['hands'][node.player]
                if not set(hand) & set(node.board):
                    expected.add((node.player, ''.join(hand), node.history))
    need(set(mapped) == expected and len(mapped) == len(rows) == 220,
         'Quotient policy lost complete legal information rows')
    # Only strategy rows are needed by exact normalization. No artificial
    # conditioned-subset solve payload or changed production metadata is created.
    return mapped, {'strategy': list(rows.values())}


def audit_policy(result, *, model=None, max_work=exact.MAX_EXACT_WORK):
    model = reference.model() if model is None else model
    f, board, config, worlds, selected, root, _ = model
    numeric = rules.replay_policy(result, f['oop'], f['ip'], board=f['board'], config=f['config'])
    rules.compare_result(result, numeric, tolerance=1e-9)
    policies = rules._validate_policy(result, root, rules._collect_nodes(root), worlds,
                                     board, selected, runouts_were_omitted=True)
    reduced_worlds, reduced_root = quotient_model(model)
    projected, serialized = project_policy(result, policies, reduced_worlds, reduced_root)
    certificate = exact.evaluate_exact(reduced_root, reduced_worlds, projected, config.pot,
                                       result=serialized, chance_grouping='partition', max_work=max_work)
    differences = {name: float(certificate['metrics'][name]) - numeric[name]
                   for name in reference.METRICS}
    need(max(map(abs, differences.values())) <= 1e-9, 'Exact quotient contradicts full numeric replay')
    return {'physical_worlds': 176, 'physical_rows': 2404, 'quotient_worlds': 12,
            'quotient_rows': 220, 'class_multiplicities': {'3c': 40, 'As': 2, 'Ac': 2, 'Ks': 2, 'Kc': 2},
            'full_numeric_metrics': {k: numeric[k] for k in reference.METRICS},
            'exact_minus_numeric': differences, 'certificate': certificate}


def fraction_json(value):
    if isinstance(value, F):
        return str(value)
    if isinstance(value, dict):
        return {key: fraction_json(v) for key, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [fraction_json(v) for v in value]
    return value


def reconstruct():
    source_map, head = fingerprints(), reference.head()
    raw_baseline = bounded(BASELINE, 1_000_000)
    need(sha256(raw_baseline).hexdigest() == BASELINE_SHA256, 'Frozen numeric report differs')
    raw_reference = bounded(reference.REPORT, reference.MAX_REPORT_BYTES)
    need(sha256(raw_reference).hexdigest() == REFERENCE_SHA256,
         'Frozen physical reference differs')
    reference.verify_saved_artifact()
    baseline, model, rows, observed = json.loads(raw_baseline), reference.model(), [], {}
    jobs = [(t, b) for t in (100, 1000, 1500) for b in ('materialized', 'matrix-free')]
    need(len(baseline['results']) == 6, 'Six baseline profiles required')
    for row, (iterations, backend) in zip(baseline['results'], jobs):
        guard(source_map, head)
        name = f'full-deck-raised-turn-v1-{backend}-{iterations}.json'
        need(row['policy_file'] == name and row['backend'] == backend and
             row['iterations_completed'] == iterations, 'Fixed numeric grid differs')
        raw = bounded(POLICIES / name, MAX_POLICY_BYTES)
        need(sha256(raw).hexdigest() == row['policy_sha256'], 'Frozen policy bytes differ')
        observed[name] = raw
        result = json.loads(raw)
        audited = audit_policy(result, model=model)
        exact_gap = audited['certificate']['metrics']['nash_conv']
        rows.append({'backend': backend, 'iterations': iterations, 'policy_file': name,
                     'policy_sha256': row['policy_sha256'], 'threshold_fraction': '1/1000',
                     'threshold_met': exact_gap <= F(1, 1000), **fraction_json(audited)})
        guard(source_map, head)
    need(bounded(BASELINE, 1_000_000) == raw_baseline and
         bounded(reference.REPORT, reference.MAX_REPORT_BYTES) == raw_reference and
         all(bounded(POLICIES / name, MAX_POLICY_BYTES) == raw for name, raw in observed.items()),
         'Baseline policy/report changed during exact audit')
    guard(source_map, head)
    return {'baseline_report_sha256': BASELINE_SHA256, 'reference_sha256': REFERENCE_SHA256,
            'scope': 'Exact explicitly normalized binary64 policies for one fixed full-deck raised game; no equilibrium claim.',
            'quotient_rule': 'All physical mass retained; identical class posterior, public subtrees and exact policy rows.',
            'work_scope': 'Exact helper work excludes separately bounded full physical validation, quotient preparation and numeric replay.',
            'preparation_envelope': {'physical_worlds': 176, 'physical_rows': 2404,
                                     'full_public_nodes': 3039, 'tree_depth': 9},
            'results': rows}


def verify_saved_artifact(path=REPORT):
    raw = bounded(path, MAX_REPORT_BYTES)
    source_map, head = fingerprints(), reference.head()
    report = json.loads(raw)
    need(canonical(report) == raw and set(report) == {'schema_version', 'generation_git_commit', 'source_sha256', 'audit'},
         'Unsupported exact audit envelope')
    need(type(report['schema_version']) is int and report['schema_version'] == 1,
         'Unsupported exact audit version')
    generation = report['generation_git_commit']
    need(type(generation) is str and len(generation) == 40 and
         all(c in '0123456789abcdef' for c in generation), 'Invalid historical generation HEAD')
    need(report['source_sha256'] == source_map, 'Exact audit source pin differs')
    expected, saved = reconstruct(), deepcopy(report['audit'])
    need(type(saved) is dict and set(saved) == set(expected) and
         type(saved.get('results')) is list and len(saved['results']) == 6,
         'Saved exact audit result envelope differs')
    # Fraction certificates/ledgers remain exact. Numeric replay observations
    # have a stated tolerance across supported Python versions/platforms.
    for actual_row, expected_row in zip(saved['results'], expected['results']):
        need(type(actual_row) is dict and set(actual_row) == set(expected_row),
             'Saved exact audit profile fields differ')
        for field in ('full_numeric_metrics', 'exact_minus_numeric'):
            actual, wanted = actual_row.pop(field), expected_row.pop(field)
            need(type(actual) is dict and set(actual) == set(wanted) and
                 all(type(actual[k]) in (int, float) and isfinite(actual[k]) and
                     abs(actual[k] - wanted[k]) <= 1e-12 for k in wanted),
                 'Saved numeric replay observations differ')
    need(canonical(saved) == canonical(expected), 'Saved exact audit differs from reconstruction')
    need(bounded(path, MAX_REPORT_BYTES) == raw, 'Exact audit report changed during verification')
    guard(source_map, head)
    return {'status': 'VERIFIED_EXACT_FULL_DECK_RAISED_POLICIES', 'training_calls': 0,
            'profiles': 6, 'report_sha256': sha256(raw).hexdigest()}


def generate():
    if REPORT.exists():
        return verify_saved_artifact(REPORT)
    source_map, head = fingerprints(), reference.head()
    payload = canonical({'schema_version': 1, 'generation_git_commit': head,
                         'source_sha256': source_map, 'audit': reconstruct()})
    need(len(payload) <= MAX_REPORT_BYTES, 'Exact audit exceeds report byte cap')
    guard(source_map, head)
    created = []
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.exact-raised-', suffix='.candidate', dir=REPORT.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        verify_saved_artifact(Path(temporary))
        try:
            os.link(temporary, REPORT)
            created.append(REPORT)
        except FileExistsError:
            need(bounded(REPORT, MAX_REPORT_BYTES) == payload,
                 'Refusing to replace a differing immutable exact audit')
        checked = verify_saved_artifact(REPORT)
        guard(source_map, head)
        return checked
    except BaseException:
        for path in reversed(created):
            path.unlink(missing_ok=True)
        raise
    finally:
        Path(temporary).unlink(missing_ok=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--generate', action='store_true')
    args = parser.parse_args()
    print(json.dumps(generate() if args.generate else verify_saved_artifact(), sort_keys=True))
