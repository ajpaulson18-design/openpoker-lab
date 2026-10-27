"""Independent controls for direct construction admission."""
from dataclasses import replace
import unittest

from pokerlab.direct_shared_topology import _DirectBuilder, build_direct_shared_topology
from pokerlab.preflop_solver import _stage_configs
from pokerlab.preflop_tree import PreflopConfig
from pokerlab.river_config import RiverConfig
from pokerlab.shared_public_topology import TopologyLimits


class DirectIndependentAdmissionTests(unittest.TestCase):
    def test_cached_template_is_charged_per_logical_occurrence_before_reuse(self):
        config = RiverConfig(pot=2, effective_stack=(2, 2), bet_sizes=(0.5,),
                             raise_sizes=(), max_raises=0, include_all_in=False)
        configs = {stage: config for stage in ('flop', 'turn', 'river')}
        support = (('5c', ('6c',)),)
        builder = _DirectBuilder(TopologyLimits())
        sid = builder.register_support(support, dict(support))
        builder.initialize_preflop_ledger(0, 0)
        first = builder.build_template(configs, sid, '2c3c4c', 1.0)
        states, decisions = builder.summaries[first][:2]
        second = builder.build_template(configs, sid, '2c3c4c', 1.0)
        self.assertEqual(first, second)
        self.assertEqual(builder.global_logical_states, 2 * states)
        self.assertEqual(builder.global_logical_decisions, 2 * decisions)
        builder.limits = replace(builder.limits, max_logical_visits=3 * states - 1)
        before = (builder.global_logical_states, len(builder.vertices), len(builder.template_roots))
        with self.assertRaisesRegex(ValueError, 'logical-visit'):
            builder.build_template(configs, sid, '2c3c4c', 1.0)
        self.assertEqual(before, (builder.global_logical_states, len(builder.vertices),
                                  len(builder.template_roots)))

    def test_parser_refuses_to_advance_iterator_when_no_scratch_is_available(self):
        advances = []
        def records():
            advances.append(1)
            yield (('2c', '3c', '4c'), '5c', '6c')
        specs = _stage_configs({}, None, None)
        limits = replace(TopologyLimits(), max_build_scratch_entries=6)
        with self.assertRaisesRegex(ValueError, 'build-scratch'):
            build_direct_shared_topology(PreflopConfig(), specs, records(), limits=limits)
        self.assertEqual(advances, [])


if __name__ == '__main__':
    unittest.main()
