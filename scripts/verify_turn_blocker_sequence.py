"""Independent selected-river turn proof; no LP/search or exact-evaluator imports."""
from collections import Counter, defaultdict
from fractions import Fraction as F
from itertools import combinations
import argparse
import hashlib
import json
from pathlib import Path
from scripts.historical_foundation_sources import BRIDGE_INPUTS, foundation_source_accepts
import subprocess
from scripts import turn_river_validation as rules
from scripts.turn_blocker_sequence_fixture import FIXTURE
ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'benchmarks/results/turn-blocker-sequence-equilibrium-v1.json'
REQUIRED_SOURCES = ["scripts/river_sequence_form.py","scripts/turn_blocker_sequence_fixture.py","scripts/turn_blocker_sequence_equilibrium.py","scripts/turn_sequence_compact_lp.py","scripts/verify_turn_blocker_sequence.py","scripts/turn_river_validation.py","scripts/turn_rational_certificate.py","scripts/audit_river_rational_certificate.py","pokerlab/cards.py","scripts/preflop_validation.py","tests/test_turn_blocker_sequence.py","benchmarks/results/turn-blocker-sequence-model-v1.json","benchmarks/results/turn-blocker-sequence-hidden-information-v1.json","benchmarks/results/turn-blocker-sequence-legacy-preflight.json"]

def require(condition, message):
    if not condition:
        raise ValueError(message)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def five(cards):
    ranks = sorted(("23456789TJQKA".index(c[0]) + 2 for c in cards), reverse=True)
    counts = Counter(ranks)
    groups = sorted(((count, rank) for rank, count in counts.items()), reverse=True)
    flush = len({c[1] for c in cards}) == 1
    unique = sorted(counts, reverse=True)
    straight = (unique[0] if len(unique) == 5 and unique[0] - unique[-1] == 4
                else 5 if unique == [14, 5, 4, 3, 2] else 0)
    if flush and straight: return (8, straight)
    if groups[0][0] == 4: return (7, groups[0][1], groups[1][1])
    if [g[0] for g in groups] == [3, 2]: return (6, groups[0][1], groups[1][1])
    if flush: return (5, *ranks)
    if straight: return (4, straight)
    if groups[0][0] == 3: return (3, groups[0][1], *sorted((r for r in counts if counts[r] == 1), reverse=True))
    if [g[0] for g in groups[:2]] == [2, 2]:
        return (2, *sorted((r for r in counts if counts[r] == 2), reverse=True),
                next(r for r in counts if counts[r] == 1))
    if groups[0][0] == 2:
        return (1, groups[0][1], *sorted((r for r in counts if counts[r] == 1), reverse=True))
    return (0, *ranks)


def rank(cards):
    return max(five(hand) for hand in combinations(cards, 5))


def terminal(node, world, pot):
    sign = (1 if node.winner == 0 else -1) if node.kind == "fold" else world["sign"]
    return F.from_float(float(sign * (pot / 2 + min(node.contributions))))


def profile(node, world, policies, pot):
    if isinstance(node, rules._Terminal):
        return terminal(node, world, pot)
    if isinstance(node, rules._Chance):
        return profile(node.branches[world["river"]], world, policies, pot)
    key = node.player, "".join(world["hands"][node.player]), node.history
    return sum((p * profile(child, world, policies, pot)
                for p, child in zip(policies[key], node.children)), F(0))


def response(root, worlds, policies, pot, player, peek=False):
    def visit(node, group):
        if isinstance(node, rules._Terminal):
            return sum((weight * terminal(node, world, pot) for world, weight in group), F(0))
        if isinstance(node, rules._Chance):
            return sum((visit(child, [(world, weight) for world, weight in group
                                      if world["river"] == river])
                        for river, child in node.branches.items()), F(0))
        if node.player == player:
            choices = [visit(child, group) for child in node.children]
            return max(choices) if player == 0 else min(choices)
        return sum((visit(child, [(world, weight * policies[
            node.player, "".join(world["hands"][node.player]), node.history][i])
            for world, weight in group]) for i, child in enumerate(node.children)), F(0))
    grouped = defaultdict(list)
    for world in worlds:
        key = (world["hands"][player], world["river"] if peek else None)
        grouped[key].append((world, world["weight"]))
    return sum((visit(root, group) for group in grouped.values()), F(0))



_require = require

def model(fixture):
    FIXTURE = fixture
    board = rules.cards(FIXTURE["board"])
    config = rules._config(FIXTURE["config"], "config")
    worlds, selected = rules._worlds(
        board, tuple(rules.expand_range(FIXTURE[p], board) for p in ("oop", "ip")),
        FIXTURE["runouts"])
    expected = {("AhAs", "QhQs", "8d"): (F(1,14),1),
                ("AhAs", "QhQs", "Kd"): (F(1,14),1),
                ("6hTh", "QhQs", "8d"): (F(3,14),1),
                ("6hTh", "QhQs", "Kd"): (F(3,14),-1),
                ("6hTh", "AdAs", "8d"): (F(3,14),1),
                ("6hTh", "AdAs", "Kd"): (F(3,14),-1)}
    law = {("".join(w["hands"][0]), "".join(w["hands"][1]), w["river"]):
           (w["weight"], w["sign"]) for w in worlds}
    require(law == expected and sum(w["weight"] for w in worlds) == 1, "Physical law differs")
    for world in worlds:
        left = rank(world["board"] + world["hands"][0])
        right = rank(world["board"] + world["hands"][1])
        require((left > right) - (left < right) == world["sign"], "Independent best-five rank disagrees")
        if "".join(world["hands"][0]) == "6hTh" and world["river"] == "8d":
            require(left == (4, 11), "Draw must make JACK-high straight")
    root = rules._public_tree(board, config, config, selected, worlds)
    flows = ({}, {})
    payoffs = defaultdict(F)
    uniform = {}
    nodes = {}
    depths = []

    # Public-node traversal carries all compatible worlds together, unlike
    # candidate construction's separate per-world traversal.
    def visit(node, entries, depth):
        require(id(node) not in nodes, "Expected a tree, not a reused public node")
        nodes[id(node)] = node
        depths.append(depth)
        require(len(nodes) <= 63 and depth <= 8, "Predeclared public model admission changed")
        if isinstance(node, rules._Terminal):
            for world, last in entries:
                payoffs[last] += world["weight"] * terminal(node, world, config.pot)
            return
        if isinstance(node, rules._Chance):
            for river, child in node.branches.items():
                group = [(world, last) for world, last in entries if world["river"] == river]
                require(group, "Empty physical chance branch")
                visit(child, group, depth + 1)
            return
        require(isinstance(node, rules._Decision), "Unknown node")
        require(len(node.actions) == len(node.children) == 2, "Two-action fixture changed")
        player = node.player
        for world, last in entries:
            hand = "".join(world["hands"][player])
            key = hand, node.history
            children = tuple((hand, node.history, action.token) for action in node.actions)
            record = last[player], children
            require(key not in flows[player] or flows[player][key] == record, "Perfect recall or hidden-future policy split")
            flows[player][key] = record
            uniform[player, hand, node.history] = (F(1, 2), F(1, 2))
        for i, child in enumerate(node.children):
            group = []
            for world, last in entries:
                updated = list(last)
                updated[player] = ("".join(world["hands"][player]), node.history, node.actions[i].token)
                group.append((world, tuple(updated)))
            visit(child, group, depth + 1)
    visit(root, [(world, (None, None)) for world in worlds], 1)
    sequences = tuple([None] + sorted({seq for parent, children in info.values() for seq in children}, key=canonical)
                      for info in flows)
    census = dict(public_nodes=len(nodes), depth=max(depths),
        public_decisions=sum(isinstance(n, rules._Decision) for n in nodes.values()),
        public_chance_nodes=sum(isinstance(n, rules._Chance) for n in nodes.values()),
        information_sets=[len(f) for f in flows], sequences=[len(s) for s in sequences])
    require(census == dict(public_nodes=63, depth=8, public_decisions=28,
        public_chance_nodes=3, information_sets=[28, 28], sequences=[57, 57]), "Independent census changed")
    positions = tuple({seq: i for i, seq in enumerate(side)} for side in sequences)
    matrices, realizations = [], []
    for player in (0, 1):
        equations = [[F(i == 0) for i in range(len(sequences[player]))]]
        for key in sorted(flows[player], key=canonical):
            parent, children = flows[player][key]
            equation = [F(0)] * len(sequences[player])
            equation[positions[player][parent]] = -1
            for child in children:
                equation[positions[player][child]] = 1
            equations.append(equation)
        matrices.append(equations)
        values, pending = {None: F(1)}, dict(flows[player])
        while pending:
            progressed = False
            for key, (parent, children) in list(pending.items()):
                if parent not in values:
                    continue
                for child in children:
                    values[child] = values[parent] / 2
                del pending[key]
                progressed = True
            require(progressed, "Flow graph is not acyclic")
        vector = [values[seq] for seq in sequences[player]]
        require([sum((a*b for a,b in zip(eq, vector)), F(0)) for eq in equations]
                == [F(1)] + [F(0)] * len(flows[player]), "Uniform flow residual")
        realizations.append(vector)
    nx, ny = map(len, sequences)
    me, mf = map(len, matrices)
    lp = dict(lower=dict(rows=me+ny, columns=nx+2*mf+ny+me+ny),
              upper=dict(rows=mf+nx, columns=ny+2*me+nx+mf+nx))
    for item in lp.values():
        item["cells_including_rhs_and_objective"] = (item["rows"]+1)*(item["columns"]+1)
    print(json.dumps(dict(status="LEGACY_LP_PREFLIGHT",census=census,lp=lp),sort_keys=True),flush=True)
    # This is a finite physical matrix oracle, not an LP search admission.
    # Preserve and assert the original solver's rejected dimensions.
    require(all(item == dict(rows=86, columns=258, cells_including_rhs_and_objective=22533) for item in lp.values()), "Legacy dimensions differ")
    require(all(item["columns"] > 256 for item in lp.values()), "Expected unchanged legacy column rejection")
    require(nx == ny == 57 and me == mf == 29, "Physical reference matrix shape differs")
    matrix = [[F(0) for _ in sequences[1]] for _ in sequences[0]]
    for (left, right), value in payoffs.items():
        matrix[positions[0][left]][positions[1][right]] += value
    value = sum((w["weight"] * profile(root, w, uniform, config.pot) for w in worlds), F(0))
    matrix_value = sum((realizations[0][i]*matrix[i][j]*realizations[1][j]
                        for i in range(nx) for j in range(ny)), F(0))
    upper = response(root, worlds, uniform, config.pot, 0)
    lower = response(root, worlds, uniform, config.pot, 1)
    require(value == matrix_value == F(4175,224), "Literal uniform EV differs")
    require(upper == F(400,7) and lower == F(-200,7) and upper-lower == F(600,7), "Literal uniform responses differ")
    checkcall = dict(uniform)
    for node in nodes.values():
        if isinstance(node, rules._Decision) and node.player == 1:
            row = tuple(F(action.name in ("check", "call")) for action in node.actions)
            require(sum(row) == 1, "Check/call policy is not complete")
            for hand in sorted({"".join(w["hands"][1]) for w in worlds}):
                checkcall[1, hand, node.history] = row
    legal = response(root, worlds, checkcall, config.pot, 0)
    illegal = response(root, worlds, checkcall, config.pot, 0, peek=True)
    require(legal == F(300,7) and illegal == F(450,7) and illegal-legal == F(150,7), "Future-peeking negative oracle differs")
    output = dict(scenario=FIXTURE["id"], fixture=FIXTURE, census=census, lp_preflight=lp,
        worlds=[dict(hands=["".join(h) for h in w["hands"]], river=w["river"],
                     weight=str(w["weight"]), sign=w["sign"]) for w in worlds],
        sequence_keys=sequences, E=[[str(v) for v in row] for row in matrices[0]],
        F=[[str(v) for v in row] for row in matrices[1]],
        A=[[str(v) for v in row] for row in matrix],
        uniform_realizations=[[str(v) for v in row] for row in realizations],
        uniform_metrics=dict(value=str(value), lower=str(lower), upper=str(upper), nash_conv=str(upper-lower)),
        check_call_ip_reference=dict(legal_oop_br=str(legal), illegal_future_peek=str(illegal), illicit_gain=str(illegal-legal)),
        nonzero_payoff_cells=sum(v != 0 for row in matrix for v in row),
        legacy_lp_admitted=False, legacy_column_limit=256,
        empty_payoff_row_and_column_zero=all(v == 0 for v in matrix[0]) and all(row[0] == 0 for row in matrix))
    return output





def verify_hidden_information_reference():
    board=rules.cards(FIXTURE['board'])
    config=rules._config(FIXTURE['config'],'config')
    worlds,selected=rules._worlds(board,tuple(rules.expand_range(FIXTURE[p],board) for p in ('oop','ip')),FIXTURE['runouts'])
    tree=rules._public_tree(board,config,config,selected,worlds)
    policies={}
    for node in rules._collect_nodes(tree):
        for world in worlds:
            if world['board'][:len(node.board)]==node.board:
                policies[node.player,''.join(world['hands'][node.player]),node.history]=tuple(F(1,len(node.actions)) for _ in node.actions)
    legal=response(tree,worlds,policies,100,1)
    pairs=sorted({w['hands'] for w in worlds})
    illegal=sum((response(tree,[w for w in worlds if w['hands']==pair],policies,100,1) for pair in pairs),F(0))
    joint={pair:sum((w['weight'] for w in worlds if w['hands']==pair),F(0)) for pair in pairs}
    left={h:sum((v for pair,v in joint.items() if pair[0]==h),F(0)) for h in {p[0] for p in pairs}}
    right={h:sum((v for pair,v in joint.items() if pair[1]==h),F(0)) for h in {p[1] for p in pairs}}
    blocked=left[('Ah','As')]*right[('Ad','As')]
    products={pair:left[pair[0]]*right[pair[1]] for pair in pairs}
    total=sum(products.values(),F(0))
    record=dict(fixture=FIXTURE,worlds=len(worlds),information_sets=len(policies),uniform_legal_ip_lower=str(legal),illegal_hidden_opponent_ip_lower=str(illegal),illegal_ip_gain=str(legal-illegal),product_mass_on_impossible_pair=str(blocked),joint_pairs=[dict(oop=''.join(pair[0]),ip=''.join(pair[1]),weight=str(joint[pair]),wrong_product_renormalized=str(products[pair]/total)) for pair in pairs])
    raw=json.dumps(record,sort_keys=True,indent=2,allow_nan=False).encode()+b'\n'
    require((len(worlds),len(policies),legal,illegal,legal-illegal,blocked)==(6,56,F(-200,7),F(-1725,56),F(125,56),F(3,49)),'Independent hidden-opponent negative anchors differ')
    require(hashlib.sha256(raw).hexdigest()=='80b0d161b9943e4fbcd0e5c609febdcefafc15d2665d895bd01400da264ab5b3','Hidden-information reference identity differs')
    require((ROOT/'benchmarks/results/turn-blocker-sequence-hidden-information-v1.json').read_bytes()==raw,'Frozen hidden-information reference differs')
    return record


def equilibrium_reach(report):
    game=report['results'][0]
    fixture=game['fixture']
    board=rules.cards(fixture['board'])
    config=rules._config(fixture['config'],'config')
    worlds,selected=rules._worlds(board,tuple(rules.expand_range(fixture[p],board) for p in ('oop','ip')),fixture['runouts'])
    root=rules._public_tree(board,config,config,selected,worlds)
    policies={(0 if r['player']=='oop' else 1,r['hand'],tuple(r['history'])):tuple(F(a['probability_fraction']) for a in r['actions']) for r in game['rational_strategy']}
    chance=defaultdict(F)
    terminal=F(0)
    early=F(0)
    river_root=F(0)
    def visit(node,world,reach,revealed=False):
        nonlocal terminal,early,river_root
        if not reach:return
        if isinstance(node,rules._Terminal):
            terminal+=reach
            if not revealed:early+=reach
            return
        if isinstance(node,rules._Chance):
            chance[node.history]+=reach
            child=node.branches[world['river']]
            if isinstance(child,rules._Decision):river_root+=reach
            visit(child,world,reach,True)
            return
        row=policies[node.player,''.join(world['hands'][node.player]),node.history]
        if sum(row,F(0))!=1 or any(v<0 for v in row):raise ValueError('Bad behavioral row')
        for child,probability in zip(node.children,row):visit(child,world,reach*probability,revealed)
    for world in worlds:visit(root,world,world['weight'])
    if terminal!=1 or early+sum(chance.values(),F(0))!=1:raise ValueError('Reach mass not conserved')
    return dict(chance_reach=str(sum(chance.values(),F(0))),river_decision_reach=str(river_root),turn_terminal_reach=str(early),terminal_reach=str(terminal),chance_histories=[dict(history=list(key),reach=str(value)) for key,value in sorted(chance.items())])

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
    return {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in (*REQUIRED_SOURCES, *(path.relative_to(ROOT).as_posix() for path in BRIDGE_INPUTS))}

def _hash_candidates(path):
    raw = path.read_bytes()
    if path.suffix == '.json':
        return {hashlib.sha256(raw).hexdigest()}
    lf = raw.replace(b'\r\n', b'\n')
    return {hashlib.sha256(value).hexdigest() for value in (raw, lf, lf.replace(b'\n',b'\r\n'))}

def _provenance(report):
    value = report.get('baseline_git_commit')
    _require(type(value) is str and len(value)==40 and all(c in '0123456789abcdef' for c in value), 'Invalid generation HEAD')
    sources = report.get('source_sha256')
    _require(type(sources) is dict and set(sources)==set(REQUIRED_SOURCES), 'Source inventory differs')
    for name in REQUIRED_SOURCES:
        _require(foundation_source_accepts(ROOT / name, sources[name], _hash_candidates(ROOT / name)), 'Source provenance differs: '+name)
    _require(report.get('generator_sha256') in _hash_candidates(ROOT / 'scripts/turn_blocker_sequence_equilibrium.py'), 'Generator identity differs')

def verify_saved_artifact(path=OUTPUT):
    path = Path(path)
    report = load(path)
    before = _inputs()
    head = subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    _require(type(report.get('schema_version')) is int and report['schema_version']==1 and report.get('certificate_id')=='turn-blocker-sequence-equilibrium-v1', 'Unsupported certificate')
    _require(report.get('status')=='exact-mutual-response-witnesses', 'Unsupported certificate status')
    _require(report.get('scope')=="Exact rational mutual-response witness for one blocker-conditioned selected-river configured binary64-terminal turn game; no unrestricted Hold'em claim.", 'Scope changed')
    _require(report.get('caps')=={'rows':96,'columns':256,'cells':25000,'pivots':512,'updates':10000000,'bits':4096,'exact_work':100000,'exact_depth':64,'exact_bits':65536}, 'Caps changed')
    _provenance(report)
    _require(type(report.get("results")) is list and len(report["results"]) == 1, "Expected one fixed game")
    _check_fraction_encodings(report)
    _require(report.get('model_reference_sha256') == '4ac32d6eb0103695d9137982a5c82f52e1a5c595491940b33e8993b96776d832', 'Model provenance differs')
    verify_hidden_information_reference()
    fresh_models = [model(FIXTURE)]
    raw = json.dumps(fresh_models, indent=2, sort_keys=True, allow_nan=False).encode() + b'\n'
    _require(hashlib.sha256(raw).hexdigest() == '4ac32d6eb0103695d9137982a5c82f52e1a5c595491940b33e8993b96776d832', 'Independent pre-candidate model identity differs')
    frozen = {row['scenario']: row for row in fresh_models}
    _require(len(report['results']) == 1, 'Invalid sequence-form witness at verification line 161')
    _require({row['scenario'] for row in report['results']} == set(frozen), 'Invalid sequence-form witness at verification line 162')
    _require((ROOT / "benchmarks/results/turn-blocker-sequence-model-v1.json").read_bytes() == raw, "Frozen model bytes differ")
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
        worlds, selected = rules._worlds(board, (rules.expand_range(fixture['oop'], board), rules.expand_range(fixture['ip'], board)), fixture['runouts'])
        _require(selected == ('8d','Kd'), 'Selected river support differs')
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
                if world["board"][:len(node.board)] != node.board:
                    continue
                key = (node.player, ''.join(world['hands'][node.player]), node.history)
                if key in policies:
                    continue
                _require(key in strategy, "Missing legal own-hand/public-history strategy row")
                saved = strategy[key]
                _require(saved['board'] == list(node.board) and saved['street'] == ('turn' if len(node.board)==4 else 'river'), 'Invalid sequence-form witness at verification line 224')
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
        _require(U - L == 0, 'Independent physical best responses must have exact zero gap')
        _check_exact_details(row, policies, expected, board, config, worlds, fixture)
        _check_record_metadata(row, ids, flow_ids, strategy, x, y, fixed)
        _check_terminal_ledger(row, tree, worlds, config.pot)
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
    print('Verified exact blocker-conditioned selected-river turn equilibrium witness')
    return 0


def _check_exact_details(row, policies, expected, board, config, worlds, fixture):
    exact = row["exact"]
    _require(type(exact["worlds"]) is int and exact["worlds"] == 6, "Physical world census differs")
    _require(F(exact["lower_value_bound"]) == expected["value_oop"] == F(exact["upper_value_bound"]), "Exact response interval differs")
    _require(F(exact["max_row_adjustment"]) == 0, "Rational rows must need no normalization correction")
    _require(exact["work_limit"] == 100000 and exact["depth_limit"] == 64 and exact["fraction_bit_limit"] == 65536, "Exact helper caps changed")
    _require(type(exact["work"]) is int and 0 < exact["work"] <= 100000, "Exact work counter invalid")
    _require(all(type(v) is int and v >= 0 for v in exact["work_by_kind"].values()) and sum(exact["work_by_kind"].values()) == exact["work"], "Exact work breakdown differs")
    _require(type(exact["maximum_fraction_bits"]) is int and 0 < exact["maximum_fraction_bits"] <= 65536, "Exact bit counter invalid")
    _require(exact["tree_nodes"] == 63, "Exact tree count differs")
    _require(exact["tree_depth"] == 8, "Exact tree depth differs")
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
    projected = dict(board=list(board),runouts=list(fixture["runouts"]),runout_mode="conditioned-subset",reachable_runouts=list(fixture["runouts"]),
                     config=config.to_dict(),strategy=float_rows,info_sets=len(float_rows),
                     compatible_world_count=6,worlds=6,compatible_pairs=3,deals=3)
    projected.update({name:float(value) for name,value in expected.items()})
    oracle = rules.replay_policy(projected,fixture["oop"],fixture["ip"],board=fixture["board"],config=fixture["config"],river_config=fixture["config"],runouts=fixture["runouts"])
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



def _check_terminal_ledger(row, tree, worlds, pot):
    seqs=row['sequences']
    lookup=[{(s['hand'],tuple(s['history']),s['action_token']):s['id'] for s in side if s['hand'] is not None} for side in seqs]
    expected=[]
    def visit(node, entries):
        if isinstance(node,rules._Terminal):
            for world,last in entries:
                utility=terminal(node,world,pot)
                expected.append(dict(world=dict(oop=''.join(world['hands'][0]),ip=''.join(world['hands'][1]),river=world['river']),oop_sequence=last[0],ip_sequence=last[1],kind=node.kind,winner=node.winner,contributions=[float(v) for v in node.contributions],matched_added_contribution=float(min(node.contributions)),world_mass=str(world['weight']),utility=str(utility),weighted_utility=str(world['weight']*utility)))
            return
        if isinstance(node,rules._Chance):
            for river,child in node.branches.items():
                visit(child,[(w,last) for w,last in entries if w['river']==river])
            return
        for action,child in zip(node.actions,node.children):
            updated=[]
            for world,last in entries:
                current=list(last)
                current[node.player]=lookup[node.player][''.join(world['hands'][node.player]),node.history,action.token]
                updated.append((world,tuple(current)))
            visit(child,updated)
    visit(tree,[(w,(seqs[0][0]['id'],seqs[1][0]['id'])) for w in worlds])
    require(len(expected)==102 and type(row.get('terminal_ledger')) is list and len(row['terminal_ledger'])==102,'Terminal ledger census differs')
    require(sorted(map(canonical,expected))==sorted(map(canonical,row['terminal_ledger'])),'Physical terminal utility/mass/sequence ledger differs')
    old={k:dict(rows=86,columns=258,tableau_cells_including_rhs_and_objective=22533) for k in ('oop_guarantee','ip_ceiling')}
    compact={k:dict(rows=85,columns=256,tableau_cells_including_rhs_and_objective=22102) for k in old}
    require(row.get('lp_admission')==dict(legacy_rejected=True,legacy_preflight=old,compact_preflight=compact,limits=dict(rows=96,columns=256,cells=25000)),'LP admission record differs')
    raw=(ROOT/'benchmarks/results/turn-blocker-sequence-legacy-preflight.json').read_bytes()
    require(hashlib.sha256(raw).hexdigest()=='87600bb1e7a8c99675203e2ddbc3352adc2bbace48d30a0db94977160533e909','Historical rejection receipt differs')


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
        _require(item["board"] == strategy[key]["board"] and item["street"] == strategy[key]["street"], "Information-set public metadata differs")
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
    _require(uniform["lower_value_fraction"]==fixed["uniform_metrics"]["lower"] and uniform["upper_value_fraction"]==fixed["uniform_metrics"]["upper"] and uniform["nash_conv_fraction"]==fixed["uniform_metrics"]["nash_conv"], "Uniform response anchors differ")
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
        own_labels,other_labels=(E,Flabels) if side==0 else (Flabels,E)
        own_seqs,other_seqs=seqs[side],seqs[1-side]
        prefix,dual=('x','q') if side==0 else ('y','p')
        variables=([prefix+':'+s['id'] for s in own_seqs[1:]]+
            [dual+'+:'+r['id'] for r in other_labels]+[dual+'-:'+r['id'] for r in other_labels]+
            ['surplus:'+s['id'] for s in other_seqs]+['artificial:'+r['id'] for r in own_labels[1:]]+
            ['artificial:cover:'+s['id'] for s in other_seqs])
        own_flow_rows=[coeffs for label,coeffs in zip(labels,row['flow_matrix']) if label['player']==side]
        constraints=[]
        for label,coeffs in zip(own_labels[1:],own_flow_rows[1:]):
            rhs=-F(coeffs[0])
            constraints.append(dict(id=label['id'],sense='=',raw_rhs=str(rhs),row_sign=-1 if rhs<0 else 1))
        for j,s in enumerate(other_seqs):
            rhs=-F(row['payoff_matrix'][0][j]) if side==0 else F(row['payoff_matrix'][j][0])
            constraints.append(dict(id='cover:'+s['id'],sense='>=',slack_variable='surplus:'+s['id'],raw_rhs=str(rhs),row_sign=-1 if rhs<0 else 1))
        _require(lp['variable_labels']==variables and lp['constraint_labels']==constraints,'Reduced search labels or affine RHS differ')
        _require(lp['empty_sequence_reduction']==dict(fixed_sequence=own_seqs[0]['id'],fixed_value='1',removed_root_constraint=own_labels[0]['id'],root_free_flow_coordinate_retained=True),'Empty-coordinate reduction metadata differs')
        _require(lp['initial_tableau_forecast']==dict(rows=85,columns=256,cells_including_rhs_and_objective=22102),'Initial reduced forecast differs')
        _require(len(constraints)==85 and len(variables)==256,'Reduced allocation dimensions differ')
        _require(lp['lp']==('oop_guarantee' if side==0 else 'ip_ceiling'),'Search role differs')
        for name in ('pivots','logical_cell_updates','maximum_fraction_bits','tableau_rows','tableau_columns','tableau_cells_including_rhs_and_objective'):
            _require(type(lp[name]) is int and lp[name]>0,'Search resource metadata must be a positive integer')
        _require(lp['tableau_columns']==len(variables) and lp['tableau_rows']<=len(constraints),'Search dimensions differ')
        _require(lp['tableau_cells_including_rhs_and_objective']==(lp['tableau_rows']+1)*(lp['tableau_columns']+1),'Search cell accounting differs')
        saved=lp['inequality_slacks']
        other=1-side
        _require(len(set(saved['sequence_labels']))==len(seqs[other]) and set(saved['sequence_labels'])==set(ids[other]),'Repeated or missing slack identities')


def _check_fraction_encodings(report):
    def scalar(value):
        _require(type(value) is str and len(value)<=8192,"Fraction must be a bounded canonical string")
        _require(str(F(value))==value,"Fraction string is not canonical")
    for row in report["results"]:
        for name in ("payoff_matrix","flow_matrix"):
            for line in row[name]:
                for value in line: scalar(value)
        for item in row["terminal_ledger"]:
            for name in ("world_mass","utility","weighted_utility"): scalar(item[name])
        for item in row["rational_strategy"]:
            _require(item["player"] in ("oop","ip"),"Invalid strategy player")
            for action in item["actions"]:
                scalar(action["probability_fraction"])
                _require(type(action["probability"]) is float,"Float projection requires binary64 numbers")
        for lp_name in ("lower_lp","upper_lp"):
            lp=row[lp_name]
            for constraint in lp["constraint_labels"]: scalar(constraint["raw_rhs"])
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

if __name__ == '__main__':
    raise SystemExit(main())
