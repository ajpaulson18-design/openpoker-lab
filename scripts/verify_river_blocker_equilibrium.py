"""Independent exact fixed-river witness verification; no LP/search imports."""
from collections import defaultdict
from fractions import Fraction as F
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from scripts import turn_river_validation as rules
from scripts import audit_river_rational_certificate as audit
from scripts.river_blocker_fixture import FIXTURE
ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'benchmarks/results/river-blocker-equilibrium-v1.json'

PRIOR_CERTIFICATE_SHA256 = '5acb6b4a0f1fa9a05af36feb2c010ac0b005be0bf29629571d99738b7ba34a34'

def _require(condition, message):
    if not condition:
        raise ValueError(message)

def terminal_value(node, world, pot):
    sign = (1 if node.winner == 0 else -1) if node.kind == 'fold' else world['sign']
    return F.from_float(float(sign * (pot / 2 + min(node.contributions))))

def profile(node, world, normalized, pot):
    if isinstance(node, rules._Terminal):
        return terminal_value(node, world, pot)
    _require(isinstance(node, rules._Decision), 'Invalid sequence-form witness at verification line 23')
    row = normalized[node.player, ''.join(world['hands'][node.player]), node.history]
    return sum((p * profile(child, world, normalized, pot) for p, child in zip(row, node.children)), F(0))

def response(root, worlds, normalized, pot, player):

    def visit(node, entries):
        if isinstance(node, rules._Terminal):
            return sum((weight * terminal_value(node, world, pot) for world, weight in entries), F(0))
        _require(isinstance(node, rules._Decision), 'Invalid sequence-form witness at verification line 32')
        if node.player == player:
            choices = [visit(child, entries) for child in node.children]
            return max(choices) if player == 0 else min(choices)
        return sum((visit(child, [(world, weight * normalized[node.player, ''.join(world['hands'][node.player]), node.history][index]) for world, weight in entries]) for index, child in enumerate(node.children)), F(0))
    hands = sorted({world['hands'][player] for world in worlds})
    return sum((visit(root, [(world, world['weight']) for world in worlds if world['hands'][player] == hand]) for hand in hands), F(0))

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()

def model(fixture):
    board = rules.cards(fixture['board'])
    config = rules._config(fixture['config'], 'config')
    worlds, selected = rules._worlds(board, (rules.expand_range(fixture['oop'], board), rules.expand_range(fixture['ip'], board)), None)
    _require(selected == (), 'Invalid sequence-form witness at verification line 47')
    _require(all((world['river'] is None for world in worlds)), 'Invalid sequence-form witness at verification line 48')
    expected = {('AhAs', 'KcKd'): (F(3, 17), 1), ('KhKs', 'AdAs'): (F(8, 17), -1), ('KhKs', 'KcKd'): (F(6, 17), 0)}
    _require({tuple((''.join(hand) for hand in world['hands'])): (world['weight'], world['sign']) for world in worlds} == expected, 'Invalid sequence-form witness at verification line 50')
    tree = rules._public_tree(board, config, config, selected, worlds)
    flows = ({}, {})
    payoffs = defaultdict(F)
    uniform = {}

    def visit(node, world, last):
        if isinstance(node, rules._Terminal):
            payoffs[tuple(last)] += world['weight'] * terminal_value(node, world, config.pot)
            return
        _require(isinstance(node, rules._Decision), 'Invalid sequence-form witness at verification line 60')
        player = node.player
        hand = ''.join(world['hands'][player])
        key = (hand, node.history)
        children = tuple(((hand, node.history, action.token) for action in node.actions))
        record = (last[player], children)
        if key in flows[player]:
            _require(flows[player][key] == record, 'Invalid sequence-form witness at verification line 67')
        flows[player][key] = record
        uniform[player, hand, node.history] = tuple((F(1, len(children)) for _ in children))
        for sequence, child in zip(children, node.children):
            updated = list(last)
            updated[player] = sequence
            visit(child, world, updated)
    for world in worlds:
        visit(tree, world, [None, None])
    sequences = tuple(([None] + sorted((seq for parent, children in infos.values() for seq in children), key=canonical) for infos in flows))
    _require(all((len(set(seqs)) == len(seqs) for seqs in sequences)), 'Invalid sequence-form witness at verification line 77')
    indices = tuple(({seq: index for index, seq in enumerate(seqs)} for seqs in sequences))
    matrix = [[F(0) for _ in sequences[1]] for _ in sequences[0]]
    for (left, right), value in payoffs.items():
        matrix[indices[0][left]][indices[1][right]] = value
    matrices = []
    for player in (0, 1):
        rows = [[F(index == 0) for index in range(len(sequences[player]))]]
        for key in sorted(flows[player], key=canonical):
            parent, children = flows[player][key]
            row = [F(0)] * len(sequences[player])
            row[indices[player][parent]] -= 1
            for child in children:
                row[indices[player][child]] += 1
            rows.append(row)
        matrices.append(rows)
    realized = []
    for player in (0, 1):
        by_sequence = {None: F(1)}
        remaining = dict(flows[player])
        while remaining:
            progressed = False
            for key, (parent, children) in list(remaining.items()):
                if parent not in by_sequence:
                    continue
                for child in children:
                    by_sequence[child] = by_sequence[parent] / len(children)
                del remaining[key]
                progressed = True
            _require(progressed, 'Invalid sequence-form witness at verification line 106')
        vector = [by_sequence[seq] for seq in sequences[player]]
        _require([sum((a * b for a, b in zip(row, vector)), F(0)) for row in matrices[player]] == [F(1)] + [F(0)] * len(flows[player]), 'Invalid sequence-form witness at verification line 108')
        realized.append(vector)
    matrix_value = sum((realized[0][i] * matrix[i][j] * realized[1][j] for i in range(len(sequences[0])) for j in range(len(sequences[1]))), F(0))
    profile_value = sum((world['weight'] * profile(tree, world, uniform, config.pot) for world in worlds), F(0))
    _require(matrix_value == profile_value, 'Invalid sequence-form witness at verification line 112')
    upper = response(tree, worlds, uniform, config.pot, 0)
    lower = response(tree, worlds, uniform, config.pot, 1)

    def strings(rows):
        return [[str(value) for value in row] for row in rows]
    output = dict(scenario=fixture['id'], worlds=len(worlds), sequence_keys=sequences, E=strings(matrices[0]), F=strings(matrices[1]), A=strings(matrix), uniform_realizations=[[str(v) for v in row] for row in realized], uniform_metrics=dict(value=str(profile_value), lower=str(lower), upper=str(upper), nash_conv=str(upper - lower)), nonzero_payoff_cells=sum((value != 0 for row in matrix for value in row)))
    return output

def load(path):
    _require(path.stat().st_size <= 2000000, "Witness input file exceeds 2MB admission")
    payload = path.read_bytes()
    _require(len(payload) <= 2000000, "Witness input changed beyond file admission")
    return json.loads(payload)

def sequence_key(row):
    return None if row['hand'] is None else (row['hand'], tuple(row['history']), row['action_token'])

def old_key(row):
    return None if row is None else (row[0], tuple(row[1]), row[2])

def dot(left, right):
    _require(len(left) == len(right), 'Invalid sequence-form witness at verification line 132')
    return sum((a * b for a, b in zip(left, right)), F(0))

def _inputs():
    values = audit._source_fingerprints()
    for name in ('scripts/river_sequence_form.py', 'scripts/verify_river_sequence.py', 'tests/test_river_sequence_form.py', 'benchmarks/results/river-rational-certificate-v1.json', 'scripts/river_blocker_fixture.py', 'scripts/river_blocker_equilibrium.py', 'scripts/verify_river_blocker_equilibrium.py', 'tests/test_river_blocker_equilibrium.py', 'benchmarks/results/river-blocker-model-v1.json'):
        values[name] = hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
    return values

def verify_saved_artifact(path=OUTPUT):
    path = Path(path)
    report = load(path)
    before = _inputs()
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    _require(type(report.get('schema_version')) is int and report.get('schema_version') == 1 and report.get('certificate_id') == 'river-blocker-equilibrium-v1', 'Unsupported certificate')
    _require(report.get('status') == 'exact-mutual-response-witnesses', 'Unsupported certificate status')
    _require(report.get('scope') == "Exact rational mutual-response witness for one blocker-correlated fixed configured binary64-terminal river game; no unrestricted Hold'em claim.", 'Scope changed')
    _require(report.get('caps') == {'rows': 96, 'columns': 256, 'cells': 25000, 'pivots': 512, 'updates': 10000000, 'bits': 4096, 'exact_work': 100000, 'exact_depth': 64, 'exact_bits': 65536}, 'Resource caps changed')
    audit._validate_saved_provenance(report)
    for name in ('scripts/river_sequence_form.py', 'scripts/verify_river_sequence.py', 'tests/test_river_sequence_form.py', 'benchmarks/results/river-rational-certificate-v1.json', 'scripts/river_blocker_fixture.py', 'scripts/river_blocker_equilibrium.py', 'scripts/verify_river_blocker_equilibrium.py', 'tests/test_river_blocker_equilibrium.py', 'benchmarks/results/river-blocker-model-v1.json'):
        _require(report['source_sha256'].get(name) in audit._source_hash_candidates(ROOT / name), 'Saved witness-source provenance changed')
    _require(report.get('generator_sha256') in audit._source_hash_candidates(ROOT / 'scripts/river_blocker_equilibrium.py'), 'Generator provenance changed')
    _require(report.get('prior_certificate_sha256') == report['source_sha256'].get('benchmarks/results/river-rational-certificate-v1.json') == PRIOR_CERTIFICATE_SHA256, 'Prior certificate provenance differs')
    fresh_models = [model(FIXTURE)]
    raw = json.dumps(fresh_models, indent=2, sort_keys=True, allow_nan=False).encode() + b'\n'
    _require(hashlib.sha256(raw).hexdigest() == 'f588431086eb0672985a58d52a4a01401db292526d4a88f0b97c56a3410e0f01', 'Independent pre-candidate model identity differs')
    frozen = {row['scenario']: row for row in fresh_models}
    prior = _load_prior()
    _require(len(report['results']) == 1, 'Invalid sequence-form witness at verification line 161')
    _require({row['scenario'] for row in report['results']} == set(frozen), 'Invalid sequence-form witness at verification line 162')
    prior = _load_prior()
    _check_fraction_encodings(report)
    _require((ROOT / "benchmarks/results/river-blocker-model-v1.json").read_bytes() == raw, "Frozen model bytes differ")
    for row in report['results']:
        fixed = frozen[row['scenario']]
        _require(len(row['sequences']) == 2, 'Expected exactly two sequence groups')
        _require(len(row['rational_strategy']) == len(row['information_sets']) == len(fixed['E']) + len(fixed['F']) - 2, 'Fixed information-set count differs')
        _require(len(row['flow_matrix']) == len(row['flow_labels']), 'Flow matrix row count differs')
        sequences = [[old_key(k) for k in side] for side in fixed['sequence_keys']]
        position = [{key: i for i, key in enumerate(side)} for side in sequences]
        ids = []
        for p in (0, 1):
            side = row['sequences'][p]
            mapping = {entry['id']: position[p][sequence_key(entry)] for entry in side}
            _require(len(mapping) == len(side) == len(sequences[p]), 'Invalid sequence-form witness at verification line 172')
            _require(set(mapping.values()) == set(range(len(sequences[p]))), 'Invalid sequence-form witness at verification line 173')
            _require(all((entry['player'] == p for entry in side)), 'Invalid sequence-form witness at verification line 174')
            ids.append(mapping)
        A = [[F(v) for v in line] for line in fixed['A']]
        matrices = [[[F(v) for v in line] for line in fixed[name]] for name in ('E', 'F')]
        _require(len(row['payoff_matrix']) == len(sequences[0]) and all(len(line) == len(sequences[1]) for line in row['payoff_matrix']), 'Payoff dimensions differ before conversion')
        saved_A = [[F(v) for v in line] for line in row['payoff_matrix']]
        _require(len(saved_A) == len(sequences[0]), 'Invalid sequence-form witness at verification line 179')
        for i, entry0 in enumerate(row['sequences'][0]):
            _require(len(saved_A[i]) == len(sequences[1]), 'Invalid sequence-form witness at verification line 181')
            for j, entry1 in enumerate(row['sequences'][1]):
                _require(saved_A[i][j] == A[ids[0][entry0['id']]][ids[1][entry1['id']]], 'Invalid sequence-form witness at verification line 183')
        flow_ids = {}
        _require(len(row['flow_labels']) == sum((len(m) for m in matrices)), 'Invalid sequence-form witness at verification line 185')
        for label, coeffs in zip(row['flow_labels'], row['flow_matrix']):
            p = label['player']
            vec = [F(0)] * len(sequences[p])
            _require(len(coeffs) == len(vec), 'Invalid sequence-form witness at verification line 189')
            for coefficient, seq in zip(coeffs, row['sequences'][p]):
                vec[ids[p][seq['id']]] = F(coefficient)
            matches = [i for i, target in enumerate(matrices[p]) if target == vec]
            _require(len(matches) == 1 and label['id'] not in flow_ids, 'Invalid sequence-form witness at verification line 193')
            idx = matches[0]
            _require(label['rhs'] == ('1' if idx == 0 else '0'), 'Invalid sequence-form witness at verification line 195')
            children = {ids[p][name] for name in label['child_sequences']}
            if idx == 0:
                _require(not children and ids[p][label['parent_sequence']] == 0, 'Invalid sequence-form witness at verification line 198')
            else:
                _require(children == {i for i, v in enumerate(vec) if v == 1}, 'Invalid sequence-form witness at verification line 200')
                _require(ids[p][label['parent_sequence']] == next((i for i, v in enumerate(vec) if v == -1)), 'Invalid sequence-form witness at verification line 201')
            flow_ids[label['id']] = (p, idx)
        _require(set(flow_ids.values()) == {(p, i) for p in (0, 1) for i in range(len(matrices[p]))}, 'Invalid sequence-form witness at verification line 203')
        fixture = row['fixture']
        _require(fixture == FIXTURE, 'Fixed fixture metadata differs')
        board = rules.cards(fixture['board'])
        config = rules._config(fixture['config'], 'config')
        worlds, selected = rules._worlds(board, (rules.expand_range(fixture['oop'], board), rules.expand_range(fixture['ip'], board)), None)
        _require(not selected, 'Invalid sequence-form witness at verification line 209')
        tree = rules._public_tree(board, config, config, selected, worlds)
        strategy = {}
        for saved in row['rational_strategy']:
            p = 0 if saved['player'] == 'oop' else 1
            key = (p, saved['hand'], tuple(saved['history']))
            _require(key not in strategy, 'Invalid sequence-form witness at verification line 215')
            strategy[key] = saved
        policies = {}
        for node in rules._collect_nodes(tree):
            for world in worlds:
                key = (node.player, ''.join(world['hands'][node.player]), node.history)
                if key in policies:
                    continue
                saved = strategy[key]
                _require(saved['board'] == list(board) and saved['street'] == 'river', 'Invalid sequence-form witness at verification line 224')
                _require([a['history_key'] for a in saved['actions']] == [a.token for a in node.actions], 'Invalid sequence-form witness at verification line 225')
                values = tuple((F(a['probability_fraction']) for a in saved['actions']))
                _require(all((F(0) <= v <= 1 for v in values)) and sum(values, F(0)) == 1, 'Invalid sequence-form witness at verification line 227')
                _require(all((a['probability'] == float(v) for a, v in zip(saved['actions'], values))), 'Invalid sequence-form witness at verification line 228')
                policies[key] = values
        _require(set(policies) == set(strategy), 'Invalid sequence-form witness at verification line 230')

        def own_vector(p, lp):
            saved = lp['own_realization']
            _require(len(saved['sequence_labels']) == len(saved['fractions']) == len(sequences[p]), 'Invalid sequence-form witness at verification line 233')
            values = {}
            for label, value in zip(saved['sequence_labels'], saved['fractions']):
                idx = ids[p][label]
                _require(idx not in values, 'Invalid sequence-form witness at verification line 237')
                values[idx] = F(value)
            vector = [values[i] for i in range(len(values))]
            _require(all((v >= 0 for v in vector)), 'Invalid sequence-form witness at verification line 240')
            _require([dot(eq, vector) for eq in matrices[p]] == [F(1)] + [F(0)] * (len(matrices[p]) - 1), 'Invalid sequence-form witness at verification line 241')
            reconstructed = {0: F(1)}
            pending = list(matrices[p][1:])
            while pending:
                progressed = False
                for equation in list(pending):
                    parent = next((i for i, v in enumerate(equation) if v == -1))
                    if parent not in reconstructed:
                        continue
                    for idx, v in enumerate(equation):
                        if v == 1:
                            hand, history, token = sequences[p][idx]
                            source = strategy[p, hand, history]['actions']
                            probability = next((F(a['probability_fraction']) for a in source if a['history_key'] == token))
                            reconstructed[idx] = reconstructed[parent] * probability
                    pending.remove(equation)
                    progressed = True
                _require(progressed, 'Invalid sequence-form witness at verification line 258')
            _require(vector == [reconstructed[i] for i in range(len(vector))], 'Invalid sequence-form witness at verification line 259')
            return vector
        lower_lp, upper_lp = (row['lower_lp'], row['upper_lp'])
        x, y = (own_vector(0, lower_lp), own_vector(1, upper_lp))

        def dual_vector(p, lp):
            saved = lp['dual_flow_values']
            _require(len(saved['flow_labels']) == len(saved['fractions']) == len(matrices[p]), 'Invalid sequence-form witness at verification line 265')
            values = {}
            for label, v in zip(saved['flow_labels'], saved['fractions']):
                player, index = flow_ids[label]
                _require(player == p and index not in values, 'Invalid sequence-form witness at verification line 269')
                values[index] = F(v)
            return [values[i] for i in range(len(matrices[p]))]
        q, pdual = (dual_vector(1, lower_lp), dual_vector(0, upper_lp))
        slack_y = [dot([line[j] for line in A], x) - dot([line[j] for line in matrices[1]], q) for j in range(len(y))]
        slack_x = [dot([line[i] for line in matrices[0]], pdual) - dot(A[i], y) for i in range(len(x))]
        for side, lp, slacks in ((1, lower_lp, slack_y), (0, upper_lp, slack_x)):
            _require(all((v >= 0 for v in slacks)), 'Invalid sequence-form witness at verification line 278')
            stored = lp['inequality_slacks']
            _require(len(stored['sequence_labels']) == len(stored['fractions']) == len(slacks), 'Invalid sequence-form witness at verification line 280')
            for label, v in zip(stored['sequence_labels'], stored['fractions']):
                _require(F(v) == slacks[ids[side][label]], 'Invalid sequence-form witness at verification line 282')
        _require(dot(x, slack_x) == dot(y, slack_y) == 0, 'Invalid sequence-form witness at verification line 283')
        matrix_value = dot(x, [dot(line, y) for line in A])
        V = sum((w['weight'] * profile(tree, w, policies, config.pot) for w in worlds), F(0))
        U = response(tree, worlds, policies, config.pot, 0)
        L = response(tree, worlds, policies, config.pot, 1)
        _require(q[0] == L == V == U == pdual[0] == matrix_value, 'Invalid sequence-form witness at verification line 288')
        _require(F(lower_lp['objective']) == q[0] == F(lower_lp['objective_bound_fraction']), 'Invalid sequence-form witness at verification line 289')
        _require(F(upper_lp['objective']) == -pdual[0], 'Invalid sequence-form witness at verification line 290')
        _require(F(upper_lp['objective_bound_fraction']) == pdual[0], 'Invalid sequence-form witness at verification line 291')
        expected = dict(value_oop=V, value_ip=-V, oop_best_response_value=U, ip_best_response_value=-L, oop_best_response_gain=U - V, ip_best_response_gain=V - L, nash_conv=U - L, exploitability=(U - L) / 2)
        _require({key: F(v) for key, v in row['exact']['metrics'].items()} == expected, 'Invalid sequence-form witness at verification line 295')
        _require(U - L == 0, 'Invalid sequence-form witness at verification line 296')
        if row['scenario'] == 'river-polarised-bluffcatcher':
            _require(V == 25, 'Invalid sequence-form witness at verification line 298')
        for old in prior['results']:
            if old['scenario'] == row['scenario']:
                _require(F(old['lower_value_bound_fraction']) <= V <= F(old['upper_value_bound_fraction']), 'Invalid sequence-form witness at verification line 301')
        _check_exact_details(row, policies, expected, board, config, worlds, fixture)
        _check_record_metadata(row, ids, flow_ids, strategy, x, y, fixed)
        for lp in (lower_lp, upper_lp):
            _require(F(lp['phase_one_objective']) == 0, 'Invalid sequence-form witness at verification line 303')
            _require(lp['pivots'] <= 512 and lp['logical_cell_updates'] <= 10000000, 'Invalid sequence-form witness at verification line 304')
            _require(lp['maximum_fraction_bits'] <= 4096, 'Invalid sequence-form witness at verification line 305')
            _require(lp['tableau_rows'] <= 96 and lp['tableau_columns'] <= 256, 'Invalid sequence-form witness at verification line 306')
            _require(lp['tableau_cells_including_rhs_and_objective'] <= 25000, 'Invalid sequence-form witness at verification line 307')
    _require(_inputs() == before, 'Sources changed during witness verification')
    _require(subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip() == head, 'HEAD changed during witness verification')
    return report

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=OUTPUT)
    args = parser.parse_args()
    verify_saved_artifact(args.input)
    print('Verified exact blocker-correlated fixed-river equilibrium witness')
    return 0


def _check_exact_details(row, policies, expected, board, config, worlds, fixture):
    exact = row["exact"]
    _require(type(exact["worlds"]) is int and exact["worlds"] == 3, "Physical world census differs")
    _require(F(exact["lower_value_bound"]) == expected["value_oop"] == F(exact["upper_value_bound"]), "Exact response interval differs")
    _require(F(exact["max_row_adjustment"]) == 0, "Rational rows must need no normalization correction")
    _require(exact["work_limit"] == 100000 and exact["depth_limit"] == 64 and exact["fraction_bit_limit"] == 65536, "Exact helper caps changed")
    _require(type(exact["work"]) is int and 0 < exact["work"] <= 100000, "Exact work counter invalid")
    _require(all(type(v) is int and v >= 0 for v in exact["work_by_kind"].values()) and sum(exact["work_by_kind"].values()) == exact["work"], "Exact work breakdown differs")
    _require(type(exact["maximum_fraction_bits"]) is int and 0 < exact["maximum_fraction_bits"] <= 65536, "Exact bit counter invalid")
    _require(exact["tree_nodes"] == (9 if row["scenario"] == "river-polarised-bluffcatcher" else 51), "Exact tree count differs")
    _require(exact["tree_depth"] == (4 if row["scenario"] == "river-polarised-bluffcatcher" else 6), "Exact tree depth differs")
    _require(exact["threshold_met"] is True, "Zero-gap witness must meet its threshold")
    originals = {(0 if item["player"] == "oop" else 1, item["hand"], tuple(item["history"])): item
                 for item in row["rational_strategy"]}
    ledger = exact["normalization_ledger"]
    _require(len(ledger) == len(policies), "Missing normalization rows")
    seen = set()
    for item in ledger:
        key = (0 if item["player"] == "oop" else 1, item["hand"], tuple(item["history"]))
        _require(key in originals and key not in seen, "Duplicate or unknown normalization identity")
        seen.add(key)
        _require(F(item["input_row_sum_fraction"]) == 1, "Rational probability row sum differs")
        source = originals[key]["actions"]
        _require(len(item["actions"]) == len(source), "Normalization action count differs")
        for i,(entry, action, probability) in enumerate(zip(item["actions"],source,policies[key])):
            _require(entry["index"] == i and entry["name"] == action["name"] and entry["history_key"] == action["history_key"], "Normalization action identity differs")
            _require(F(entry["input_fraction"]) == probability == F(entry["normalized_fraction"]), "Normalization fraction differs")
            _require(F(entry["adjustment_fraction"]) == 0 and entry["adjustment_float"] == 0.0, "Nonzero rational normalization adjustment")
    normalized = []
    for key in sorted(originals):
        item = originals[key]
        normalized.append({name:item[name] for name in ("player","hand","street","board","history")} |
            {"actions":[{name:action[name] for name in ("name","amount","raise_to","history_key")} |
                        {"probability_fraction":str(probability)}
                        for action,probability in zip(item["actions"],policies[key])]})
    _require(exact["normalized_policy_rows"] == normalized, "Normalized policy rows differ")
    for name in ("normalized_policies","policies"):
        if name in exact:
            entries = exact[name]["key_value_entries"]
            mapping = {}
            for item in entries:
                p,hand,history = item["key"]
                key = (p,hand,tuple(history))
                _require(key not in mapping,"Repeated exact-policy identity")
                mapping[key] = tuple(F(v) for v in item["value"])
            _require(mapping == policies,"Exact policy mapping differs")
    float_rows = []
    for source in row["rational_strategy"]:
        result = {name:value for name,value in source.items() if name != "actions"}
        result["actions"] = [{name:value for name,value in action.items() if name != "probability_fraction"}
                             for action in source["actions"]]
        float_rows.append(result)
    projected = dict(board=list(board),runouts=[],runout_mode="none",reachable_runouts=[],
                     config=config.to_dict(),strategy=float_rows,info_sets=len(float_rows),
                     compatible_pairs=len(worlds),deals=len(worlds))
    projected.update({name:float(value) for name,value in expected.items()})
    oracle = rules.replay_policy(projected,fixture["oop"],fixture["ip"],board=fixture["board"],config=fixture["config"])
    delta = rules.compare_result(projected,oracle,tolerance=1e-9)
    saved_delta = row["float_projection_compare_differences"]
    _require(set(saved_delta) == set(delta),"Float projection comparison fields differ")
    for name,value in delta.items():
        _require(abs(saved_delta[name]-value) <= 1e-12,"Float projection difference changed")
    saved_oracle = row["float_projection_oracle"]
    _require(set(saved_oracle) == set(oracle),"Float oracle fields differ")
    for name,value in oracle.items():
        if type(value) is int:
            _require(type(saved_oracle[name]) is int and saved_oracle[name] == value,"Float oracle count differs")
        elif type(value) is float:
            _require(type(saved_oracle[name]) is float and abs(saved_oracle[name]-value) <= 1e-9,"Float oracle value differs")
        else:
            normalized = _saved_form(value)
            _require(saved_oracle[name] == normalized,"Float oracle metadata differs at " + name)



def _check_record_metadata(row, ids, flow_ids, strategy, x, y, fixed):
    source_sequences = [{entry["id"]:entry for entry in side} for side in row["sequences"]]
    for player,side in enumerate(row["sequences"]):
        empty = [entry for entry in side if entry["hand"] is None]
        _require(len(empty)==1 and empty[0]["history"]==[] and empty[0]["action_token"] is None and empty[0]["parent"] is None,"Empty sequence metadata differs")
    by_children = {}
    for label in row["flow_labels"]:
        if label["kind"] == "information_set":
            player=label["player"]
            children=tuple(label["child_sequences"])
            for child in children:
                _require(source_sequences[player][child]["parent"]==label["parent_sequence"],"Sequence parent metadata differs")
            by_children[player,frozenset(children)]=label["parent_sequence"]
    info_seen=set()
    for item in row["information_sets"]:
        key=(item["player"],item["hand"],tuple(item["history"]))
        _require(key in strategy and key not in info_seen,"Information-set metadata identity differs")
        info_seen.add(key)
        tokens=[action["history_key"] for action in strategy[key]["actions"]]
        _require(item["action_tokens"]==tokens,"Information-set action metadata differs")
        children=item["child_sequences"]
        _require(len(children)==len(tokens) and len(set(children))==len(children),"Information-set sequence count differs")
        for child,token in zip(children,tokens):
            record=source_sequences[key[0]][child]
            _require((record["hand"],tuple(record["history"]),record["action_token"])==(key[1],key[2],token),"Information-set child sequence differs")
        _require(item["parent_sequence"]==by_children[key[0],frozenset(children)],"Information-set parent differs")
    _require(info_seen==set(strategy),"Missing information-set metadata")
    _require(len(row["flow_residuals"])==2,"Missing saved flow residual groups")
    for player,records in enumerate(row["flow_residuals"]):
        expected={name:index for name,(p,index) in flow_ids.items() if p==player}
        _require(len(records)==len(expected),"Saved flow residual count differs")
        seen=set()
        for record in records:
            name=record["constraint"]
            _require(name in expected and name not in seen,"Saved flow residual identity differs")
            seen.add(name)
            value=1 if expected[name]==0 else 0
            _require(F(record["lhs"])==F(record["rhs"])==value and F(record["residual"])==0,"Saved flow residual differs")
    uniform=row["uniform_crosscheck"]
    _require(uniform["value_fraction"]==fixed["uniform_metrics"]["value"] and uniform["matrix_equals_independent_tree"] is True,"Uniform policy reference differs")
    _require(len(uniform["flow_residuals"])==len(flow_ids),"Uniform flow residual count differs")
    seen=set()
    for item in uniform["flow_residuals"]:
        name=item["constraint"]
        _require(name in flow_ids and name not in seen,"Uniform flow residual identity differs")
        seen.add(name)
        value=1 if flow_ids[name][1]==0 else 0
        _require(F(item["lhs"])==F(item["rhs"])==value and F(item["residual"])==0,"Uniform flow residual differs")
    seqs=row["sequences"]
    labels=row["flow_labels"]
    E=[entry for entry in labels if entry["player"]==0]
    Flabels=[entry for entry in labels if entry["player"]==1]
    for side,lp in ((0,row["lower_lp"]),(1,row["upper_lp"])):
        if side==0:
            variables=(["x:"+v["id"] for v in seqs[0]]+
                       ["q+:"+v["id"] for v in Flabels]+["q-:"+v["id"] for v in Flabels]+
                       ["surplus:"+v["id"] for v in seqs[1]]+
                       ["artificial:"+v["id"] for v in E]+["artificial:cover:"+v["id"] for v in seqs[1]])
            constraints=([{"id":v["id"],"sense":"="} for v in E]+
                         [{"id":"cover:"+v["id"],"sense":">=","slack_variable":"surplus:"+v["id"]} for v in seqs[1]])
        else:
            variables=(["y:"+v["id"] for v in seqs[1]]+
                       ["p+:"+v["id"] for v in E]+["p-:"+v["id"] for v in E]+
                       ["surplus:"+v["id"] for v in seqs[0]]+
                       ["artificial:"+v["id"] for v in Flabels]+["artificial:cover:"+v["id"] for v in seqs[0]])
            constraints=([{"id":v["id"],"sense":"="} for v in Flabels]+
                         [{"id":"cover:"+v["id"],"sense":">=","slack_variable":"surplus:"+v["id"]} for v in seqs[0]])
        _require(lp["variable_labels"]==variables and lp["constraint_labels"]==constraints,"Search matrix labels differ")
        _require(lp["lp"]==("oop_guarantee" if side==0 else "ip_ceiling"),"Search role differs")
        for name in ("pivots","logical_cell_updates","maximum_fraction_bits","tableau_rows","tableau_columns","tableau_cells_including_rhs_and_objective"):
            _require(type(lp[name]) is int and lp[name]>0,"Search resource metadata must be positive integer")
        _require(lp["tableau_columns"]==len(variables) and lp["tableau_rows"]<=len(constraints),"Search dimensions differ")
        _require(lp["tableau_cells_including_rhs_and_objective"]==(lp["tableau_rows"]+1)*(lp["tableau_columns"]+1),"Search cell accounting differs")
        saved=lp["inequality_slacks"]
        other=1-side
        _require(len(set(saved["sequence_labels"]))==len(seqs[other]) and set(saved["sequence_labels"])==set(ids[other]),"Repeated or missing slack identities")



def _check_fraction_encodings(report):
    def scalar(value):
        _require(type(value) is str and len(value)<=8192,"Fraction must be a bounded canonical string")
        _require(str(F(value))==value,"Fraction string is not canonical")
    for row in report["results"]:
        for name in ("payoff_matrix","flow_matrix"):
            for line in row[name]:
                for value in line: scalar(value)
        for item in row["rational_strategy"]:
            _require(item["player"] in ("oop","ip"),"Invalid strategy player")
            for action in item["actions"]:
                scalar(action["probability_fraction"])
                _require(type(action["probability"]) is float,"Float projection requires binary64 numbers")
        for lp_name in ("lower_lp","upper_lp"):
            lp=row[lp_name]
            for name in ("objective","objective_bound_fraction","phase_one_objective"):
                scalar(lp[name])
            for name in ("own_realization","dual_flow_values","inequality_slacks"):
                for value in lp[name]["fractions"]: scalar(value)
        exact=row["exact"]
        for value in exact["metrics"].values(): scalar(value)
        for name in ("lower_value_bound","upper_value_bound","max_row_adjustment"): scalar(exact[name])
        for ledger in exact["normalization_ledger"]:
            scalar(ledger["input_row_sum_fraction"])
            _require(ledger["player"] in ("oop","ip"),"Invalid normalization player")
            for action in ledger["actions"]:
                for name in ("input_fraction","normalized_fraction","adjustment_fraction"): scalar(action[name])
        for item in exact["normalized_policy_rows"]:
            for action in item["actions"]: scalar(action["probability_fraction"])



def _saved_form(value):
    if isinstance(value,F):
        return str(value)
    if isinstance(value,dict):
        if all(type(key) is str for key in value):
            return {key:_saved_form(item) for key,item in value.items()}
        return {"key_value_entries":[{"key":_saved_form(key),"value":_saved_form(item)}
                                     for key,item in value.items()]}
    if isinstance(value,(list,tuple)):
        return [_saved_form(item) for item in value]
    return value

def _load_prior():
    path=ROOT/"benchmarks/results/river-rational-certificate-v1.json"
    raw=path.read_bytes()
    _require(hashlib.sha256(raw).hexdigest()==PRIOR_CERTIFICATE_SHA256,"Prior river certificate hash differs")
    return json.loads(raw)

if __name__ == '__main__':
    raise SystemExit(main())
