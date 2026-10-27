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

    def test_builder_released_at_real_trainer_entry_and_error(self):
        import gc
        import weakref
        from unittest.mock import patch
        from pokerlab import direct_shared_topology, packed_operator_cfr
        from pokerlab.selected_operator_solver import solve_four_street_operator
        from tests.test_selected_operator_solver import CASE, request

        original_builder = direct_shared_topology._DirectBuilder
        original_trainer = packed_operator_cfr.train_packed
        was_enabled = gc.isenabled()
        try:
            gc.disable()
            for fail in (False, True):
                refs, observed = [], []
                def capture(*args, **kwargs):
                    obj = original_builder(*args, **kwargs)
                    refs.append(weakref.ref(obj))
                    return obj
                def trainer(*args, **kwargs):
                    observed.append(refs[0]() is None)
                    if fail:
                        raise RuntimeError('injected trainer failure')
                    return original_trainer(*args, **kwargs)
                with patch.object(direct_shared_topology, '_DirectBuilder', side_effect=capture), \
                     patch.object(packed_operator_cfr, 'train_packed', side_effect=trainer):
                    if fail:
                        with self.assertRaisesRegex(RuntimeError, 'injected trainer failure'):
                            solve_four_street_operator(request(CASE), strategy_storage='packed',
                                                       public_topology='direct')
                    else:
                        result = solve_four_street_operator(request(CASE), strategy_storage='packed',
                                                            public_topology='direct')
                        self.assertTrue(result['strategy'])
                self.assertEqual(observed, [True])
                self.assertIsNone(refs[0]())
        finally:
            if was_enabled:
                gc.enable()


    def test_builder_released_after_build_and_injected_finish_failure(self):
        import gc
        import weakref
        from unittest.mock import patch
        from pokerlab import direct_shared_topology
        from tests.test_shared_public_topology import _fixture_case
        from tests.test_direct_shared_topology import DirectSharedTopologyTests

        case = _fixture_case()
        _, specs, selected = DirectSharedTopologyTests()._direct_inputs(case)
        config = PreflopConfig.from_dict(case['config'])
        original = direct_shared_topology._DirectBuilder
        was_enabled = gc.isenabled()
        try:
            gc.disable()
            for failure in (None, "finish", "transition"):
                refs = []
                def capture(*args, **kwargs):
                    obj = original(*args, **kwargs)
                    refs.append(weakref.ref(obj))
                    return obj
                def build():
                    with patch.object(direct_shared_topology, '_DirectBuilder', side_effect=capture):
                        if failure:
                            def fail_inside(*args, **kwargs):
                                raise RuntimeError('construction failure')
                            method = 'finish' if failure == 'finish' else '_reserve_transition'
                            with patch.object(original, method, new=fail_inside):
                                try:
                                    build_direct_shared_topology(config, specs, selected)
                                except RuntimeError as exc:
                                    self.assertEqual(str(exc), 'construction failure')
                                else:
                                    self.fail('expected finish failure')
                            return None
                        return build_direct_shared_topology(config, specs, selected)
                result = build()
                if not failure:
                    self.assertGreater(len(result[0].vertices), 0)
                self.assertEqual(len(refs), 1)
                self.assertIsNone(refs[0]())
        finally:
            if was_enabled:
                gc.enable()



if __name__ == '__main__':
    unittest.main()
