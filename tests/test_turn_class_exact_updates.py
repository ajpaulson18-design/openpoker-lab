"""Independent rational alternating half-steps and own-reach class scaling."""
from fractions import Fraction as F
from collections import Counter
import unittest
from unittest.mock import patch
from scripts import turn_three_hand_classes as classes, turn_river_validation as rules

def nodes(root):
    return {(node.player, node.history): node for node in rules._collect_nodes(root)}

def legal_policy(root, worlds):
    result = {}
    for node in nodes(root).values():
        rivers = [t[6:] for t in node.history if t.startswith('river@')]
        for hand in sorted({w['hands'][node.player] for w in worlds if not rivers or w['river'] == rivers[0]}):
            result[node.player, ''.join(hand), node.history] = tuple((F(1, len(node.actions)) for _ in node.actions))
    return result

def target_deltas(root, worlds, policy, player, pot):
    deltas = {}
    meter = Counter()

    def visit(node, group, hand):
        meter['visits'] += 1
        meter['weighted_visits'] += len(group)
        if meter['weighted_visits'] > 500000:
            raise ValueError('bounded exact first-sweep limit')
        if not group:
            return F(0)
        if isinstance(node, rules._Chance):
            return sum((visit(child, [(w, r) for w, r in group if w['river'] == card], hand) for card, child in node.branches.items()), F(0))
        if isinstance(node, rules._Terminal):
            magnitude = F.from_float(pot / 2 + min(node.contributions))
            return sum((w['weight'] * reach * magnitude * ((1 if node.winner == 0 else -1) if node.kind == 'fold' else w['sign']) for w, reach in group), F(0)) * (1 if player == 0 else -1)
        if node.player == player:
            values = tuple((visit(child, group, hand) for child in node.children))
            key = (player, ''.join(hand), node.history)
            expected = sum((p * v for p, v in zip(policy[key], values)), F(0))
            if key in deltas:
                raise ValueError('duplicate own-hand information traversal')
            deltas[key] = tuple((v - expected for v in values))
            return expected
        return sum((visit(child, [(w, reach * policy[node.player, ''.join(w['hands'][node.player]), node.history][index]) for w, reach in group], hand) for index, child in enumerate(node.children)), F(0))
    for hand in sorted({w['hands'][player] for w in worlds}):
        visit(root, [(w, F(1)) for w in worlds if w['hands'][player] == hand], hand)
    return (deltas, dict(meter))

def rematch(policy, deltas):
    out = dict(policy)
    for key, values in deltas.items():
        positive = tuple((max(F(0), v) for v in values))
        total = sum(positive, F(0))
        out[key] = tuple((v / total for v in positive)) if total else tuple((F(1, len(values)) for _ in values))
    return out

def mapped_key(key, mapping):
    return (key[0], key[1], tuple(('river@' + mapping[t[6:]] if t.startswith('river@') else t for t in key[2])))

def exact_first_sweep():
    fixed = classes.build_model()
    physical = fixed.physical
    proot, pworlds = (physical[5], physical[3])
    croot, cworlds = (fixed.class_root, fixed.class_worlds)
    policies = [legal_policy(proot, pworlds), legal_policy(croot, cworlds)]
    if not [len(p) for p in policies] == [3606, 486]:
        raise AssertionError('Exact class-update invariant failed')
    multiplicity = {rep: len(cards) for rep, cards in fixed.class_members}
    records = []
    for player in (0, 1):
        pd, pc = target_deltas(proot, pworlds, policies[0], player, physical[2].pot)
        cd, cc = target_deltas(croot, cworlds, policies[1], player, physical[2].pot)
        if not (len(pd) == 1803 and len(cd) == 243):
            raise AssertionError('Exact class-update invariant failed')
        for key, values in pd.items():
            mapped = mapped_key(key, fixed.river_class)
            revealed = [t[6:] for t in mapped[2] if t.startswith('river@')]
            scale = multiplicity[revealed[0]] if revealed else 1
            if not tuple((v * scale for v in values)) == cd[mapped]:
                raise AssertionError('Exact class-update invariant failed')
        policies = [rematch(policies[0], pd), rematch(policies[1], cd)]
        for key, row in policies[0].items():
            if not row == policies[1][mapped_key(key, fixed.river_class)]:
                raise AssertionError('Exact class-update invariant failed')
        records.append(dict(player=player, physical_regret_rows=len(pd), class_regret_rows=len(cd), physical_meter=pc, class_meter=cc, exact_regret_scaling=True, exact_rematched_policy_identity=True))

    def increments(policy, worlds):
        result = {}
        index_nodes = nodes(proot if policy is policies[0] else croot)
        for key, row in policy.items():
            player, hand, history = key
            reach = F(1)
            prefix = []
            for token in history:
                prior = policy.get((player, hand, tuple(prefix)))
                if prior is not None:
                    parent = index_nodes[player, tuple(prefix)]
                    index = [a.token for a in parent.actions].index(token)
                    reach *= prior[index]
                prefix.append(token)
            river = [t[6:] for t in history if t.startswith('river@')]
            marginal = sum((w['weight'] for w in worlds if ''.join(w['hands'][player]) == hand and (not river or w['river'] == river[0])), F(0))
            result[key] = tuple((marginal * reach * p for p in row))
        return result
    ip, ic = (increments(policies[0], pworlds), increments(policies[1], cworlds))
    for key, values in ip.items():
        mapped = mapped_key(key, fixed.river_class)
        river = [t[6:] for t in mapped[2] if t.startswith('river@')]
        scale = multiplicity[river[0]] if river else 1
        if not tuple((v * scale for v in values)) == ic[mapped]:
            raise AssertionError('Exact class-update invariant failed')
    result = dict(status='EXACT_FIRST_SWEEP_AND_OWN_REACH_SCALING_VERIFIED', training_calls=0, half_steps=records, average_rows_checked=len(ip), scope='Independent rational first sweep in fixed396-world game; exact arithmetic class regret and marginal-average scaling, not binary64 bitwise equality or convergence')
    return result

class ExactClassUpdatesTests(unittest.TestCase):

    def test_first_sweep_matches_all_physical_regrets_and_average_flows(self):
        with patch('pokerlab.turn_class_tail_adapter.solve_turn_class_tail', side_effect=AssertionError('Candidate solver forbidden')), patch('pokerlab.turn_tail_adapter._train_original_weight_tail', side_effect=AssertionError('Trainer forbidden')), patch('pokerlab.public_cfr._cfrplus_target_deltas', side_effect=AssertionError('Production regret evaluator forbidden')), patch('pokerlab.postflop_solver._build_postflop_tree', side_effect=AssertionError('Production tree forbidden')):
            result = exact_first_sweep()
        self.assertEqual(result['average_rows_checked'], 3606)
        self.assertEqual(result['training_calls'], 0)
        self.assertEqual(len(result['half_steps']), 2)
        self.assertTrue(all((r['exact_regret_scaling'] and r['exact_rematched_policy_identity'] for r in result['half_steps'])))
if __name__ == '__main__':
    unittest.main()
