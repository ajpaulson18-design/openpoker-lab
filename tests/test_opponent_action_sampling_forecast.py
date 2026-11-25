"""Independent literal histories, exact tiny occupancy and source-first refusal."""
from fractions import Fraction
from unittest.mock import patch
import unittest
from scripts.forecast_opponent_action_sampling import CAPS,RESERVED,forecast,occupancy


class OpponentActionForecastTests(unittest.TestCase):
    def test_both_target_dp_counts_match_independent_literal_history_inclusions(self):
        from tests.virtual_betting_template_reference import build_reference_template
        from tests.virtual_frozen_update_reference import _template_case
        tree=build_reference_template(_template_case())
        total={name:Fraction(0) for name in ('visits','reads','terminals','reveals','actions','target_update_rows')}
        union=Fraction(0);inverse=[1,1]
        def visit(node_id,proposal_probabilities):
            nonlocal union
            node=tree.nodes[node_id];p0,p1=proposal_probabilities
            total['visits']+=p0+p1
            if node.phase in ('fold','showdown'):total['terminals']+=p0+p1;return
            if node.phase=='reveal':
                total['reveals']+=p0+p1;visit(node.edges[0].child,proposal_probabilities);return
            actor=node.state.player;k=len(node.edges)
            total['reads']+=p0+p1;union+=p0+p1-p0*p1
            total['target_update_rows']+=proposal_probabilities[actor]
            total['actions']+=proposal_probabilities[actor]*k+proposal_probabilities[1-actor]
            for edge in node.edges:
                next_prob=list(proposal_probabilities);next_prob[1-actor]/=k
                visit(edge.child,tuple(next_prob))
        visit(tree.root,(Fraction(1),Fraction(1)))
        result=forecast((2,100))
        for name,value in total.items():
            saved=result['expected_two_target_counts'][name]
            self.assertEqual(value,Fraction(saved['numerator'],saved['denominator']))
            self.assertLessEqual(value,result['componentwise_two_target_worst_bounds'][name])
        saved=result['expected_unique_read_rows_one_world']
        self.assertEqual(union,Fraction(saved['numerator'],saved['denominator']))
        self.assertLess(union,434);self.assertLess(total['visits'],1105)
        self.assertFalse(result['attempted_training']);self.assertFalse(result['native_admission'])
        self.assertEqual((result['native_calls'],result['rng_calls']),(0,0));self.assertIsNone(result['quality_gate'])
        self.assertLessEqual(result['modeled_source_plus_scalar_work'],RESERVED['work'])
        self.assertEqual(result['resource_accounting'],RESERVED)

    def test_outward_bounds_contain_exact_small_occupancy(self):
        for cells in range(1,17):
            for p in (Fraction(1),Fraction(1,2),Fraction(1,3),Fraction(2,3),Fraction(5,6)):
                for count in range(1,17):
                    exact=cells*(1-(1-p/cells)**count);interval=occupancy(cells,p,count)
                    self.assertLessEqual(interval['lower'],exact);self.assertGreaterEqual(interval['upper'],exact)
        with self.assertRaises(ValueError):occupancy(3,Fraction(0),1)
        with self.assertRaises(ValueError):occupancy(3,Fraction(1),0)

    def test_refuses_before_source_and_cannot_raise_caps(self):
        with patch('tests.virtual_betting_template_reference.build_reference_template',side_effect=AssertionError('source entered')):
            for key in CAPS:
                with self.assertRaises(ValueError):forecast(limits={key:RESERVED[key]-1})
                with self.assertRaises(ValueError):forecast(limits={key:CAPS[key]+1})
            for observations in ((True,),(),(0,),(1_000_000_001,),tuple(range(1,18))):
                with self.assertRaises(ValueError):forecast(observations)
            with self.assertRaises(ValueError):forecast(deck_cards=8)

    def test_uniform_lifetime_intervals_preserve_scope_and_existing_widths(self):
        result=forecast((1,2,100,1000,1_000_000,1_000_000_000))
        for row in result['iid_uniform_joint_world_encounters']:
            for name in ('catalog_public_blocks','catalog_seen_rows','target_update_encounters','full_walk_seen_rows'):
                self.assertLessEqual(row[name]['lower'],row[name]['upper'])
            self.assertLessEqual(row['catalog_seen_rows']['lower'],row['full_walk_seen_rows']['upper'])
            self.assertLessEqual(row['target_update_encounters']['lower'],row['catalog_seen_rows']['upper'])
        width=result['hypothetical_carrier_magnitude_bits']
        self.assertLessEqual(width['single_regret'],648);self.assertLessEqual(width['two_regrets'],649)
        self.assertLessEqual(width['single_average'],383);self.assertLessEqual(width['two_averages'],382)
        self.assertEqual((width['regret_denominator_power'],width['average_denominator_power']),(625,364))


if __name__=='__main__':unittest.main()
