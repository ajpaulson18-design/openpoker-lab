"""Direct postflop DAG construction against the independent literal path."""
from dataclasses import replace
import gc
import json
from pathlib import Path
import unittest
import weakref
from unittest.mock import patch

from pokerlab import preflop_solver
from pokerlab.cards import cards
from pokerlab.direct_shared_topology import build_direct_shared_topology
from pokerlab.preflop_tree import PreflopConfig, build_preflop_tree
from pokerlab.shared_public_topology import (
    ChanceVertex,
    DecisionVertex,
    TerminalVertex,
    TopologyLimits,
    compile_shared_public_topology,
)
from tests.test_shared_public_topology import (
    REPO,
    _build_literal_tree,
    _dag_events,
    _fixture_case,
    _heldout_96_case,
    _node_events,
)


class DirectSharedTopologyTests(unittest.TestCase):
    def _direct_inputs(self, case):
        root, worlds, _support, _counts = _build_literal_tree(case)
        reachable = {("".join(cards(world[4], 3)), world[5], world[6])
                     for world in worlds}
        requested = preflop_solver._requested_runouts(case["runouts"])
        selected = tuple((flop, turn, river) for flop, turn, river in requested
                         if ("".join(flop), turn, river) in reachable)
        specs = preflop_solver._stage_configs(
            case["flop_config"], case["turn_config"], case["river_config"])
        return root, specs, selected

    def _compare_case(self, case):
        literal_root, specs, selected = self._direct_inputs(case)
        expected_events = _node_events(literal_root)
        expected = compile_shared_public_topology(literal_root)
        with patch("pokerlab.preflop_solver._merge_preflop_tree",
                   side_effect=AssertionError("literal merge invoked")), \
             patch("pokerlab.preflop_solver._build_public_tree",
                   side_effect=AssertionError("literal postflop builder invoked")), \
             patch("pokerlab.river_tree._build_tree",
                   side_effect=AssertionError("literal river builder invoked")), \
             patch("pokerlab.preflop_solver._clone_template",
                   side_effect=AssertionError("literal template clone invoked")), \
             patch("pokerlab.shared_public_topology.compile_shared_public_topology",
                   side_effect=AssertionError("topology compiler invoked")):
            actual, receipt = build_direct_shared_topology(
                PreflopConfig.from_dict(case["config"]), specs, selected)
        self.assertEqual(_dag_events(expected), expected_events)
        self.assertEqual(_dag_events(actual), expected_events)
        for field in (
                "unique_vertices", "unique_edges", "expanded_logical_visits",
                "decision_occurrences", "chance_occurrences", "terminal_occurrences",
                "logical_history_token_work", "logical_history_token_bytes",
                "maximum_depth"):
            self.assertEqual(getattr(actual.census, field),
                             getattr(expected.census, field), field)
        self.assertEqual(actual.census.expanded_logical_visits, len(expected_events))
        self.assertEqual(receipt["expanded_logical_visits"],
                         actual.census.expanded_logical_visits)
        self.assertEqual(receipt["decision_occurrences"], actual.census.decision_occurrences)
        self.assertEqual(receipt["chance_occurrences"], actual.census.chance_occurrences)
        self.assertEqual(receipt["terminal_occurrences"], actual.census.terminal_occurrences)
        self.assertEqual(receipt["maximum_depth"], actual.census.maximum_depth)
        self.assertEqual(receipt["logical_history_token_work"],
                         actual.census.logical_history_token_work)
        self.assertEqual(receipt["logical_history_token_bytes"],
                         actual.census.logical_history_token_bytes)
        self.assertEqual(receipt["materialized_postflop_nodes"], 0)
        self.assertEqual(receipt["compiler_snapshots"], 0)
        self.assertEqual(receipt["unique_dag_vertices"], actual.census.unique_vertices)
        self.assertEqual(receipt["unique_dag_edges"], actual.census.unique_edges)
        self.assertGreater(receipt["canonical_context_ids"], 0)
        self.assertGreater(receipt["canonical_support_shape_ids"], 0)
        self.assertGreater(receipt["canonical_prefix_ids"], 0)
        self.assertGreater(receipt["support_shape_hash_entries"], 0)
        self.assertEqual(receipt["completed_subtree_summaries"],
                         actual.census.unique_vertices)
        self.assertEqual(receipt["reserved_recurrence_transitions"],
                         receipt["memoized_betting_edges"])
        self.assertEqual(receipt["reserved_global_logical_states"],
                         actual.census.expanded_logical_visits)
        self.assertEqual(receipt["reserved_global_logical_decisions"],
                         actual.census.decision_occurrences)
        self.assertEqual(receipt["selected_input_records"], len(selected))
        self.assertGreater(receipt["materialized_preflop_source_continuations"], 0)
        self.assertGreater(receipt["memoized_betting_states"], 0)
        self.assertGreater(receipt["memoized_betting_edges"], 0)
        self.assertLess(actual.census.unique_vertices,
                        actual.census.expanded_logical_visits)
        return actual, receipt, expected_events

    def test_22_world_fixture_complete_ordered_occurrences(self):
        topology, receipt, events = self._compare_case(_fixture_case())
        self.assertEqual(sum(event[0] == "chance" for event in events),
                         topology.census.chance_occurrences)
        preflop = build_preflop_tree(PreflopConfig.from_dict(_fixture_case()["config"]))
        self.assertEqual(receipt["materialized_preflop_source_states"],
                         preflop.public_state_count)

    def test_96_world_weighted_blockers_and_shared_future_controls(self):
        heldout = _heldout_96_case()
        self._compare_case(heldout)
        weighted = dict(_fixture_case(),
                        sb_range="AsAd:1,AhAc:0.25,2c3c:0.5",
                        bb_range="KsKd:0.75,JhJd:0.25")
        self._compare_case(weighted)

    def test_fractional_asymmetric_refund_tie_and_raise_reopening(self):
        actions = {"bet_sizes": [0.25, 0.5], "raise_sizes": [0.5, 1.0],
                   "max_raises": 2, "include_all_in": True}
        case = {
            "sb_range": "2d3d", "bb_range": "4h5h",
            "runouts": ["TcJcQcKcAc"],
            "config": {"small_blind": 0.3, "big_blind": 0.8,
                       "starting_stack": [2.5, 2.0], "raise_sizes": [0.5, 1.0],
                       "max_raises": 2, "include_all_in": True},
            "flop_config": actions, "turn_config": actions, "river_config": actions,
        }
        topology, _receipt, events = self._compare_case(case)
        names = {action.name for vertex in topology.vertices
                 if isinstance(vertex, DecisionVertex) for action in vertex.actions}
        self.assertIn("all_in", names)
        terminals = [vertex for vertex in topology.vertices
                     if isinstance(vertex, TerminalVertex)]
        self.assertTrue(any(a != b for item in terminals for a, b in [item.contributions]))
        self.assertTrue(any(value != round(value) for item in terminals
                            for value in item.contributions))
        self.assertTrue(any(event[0] == "chance" and event[2] == "river"
                            for event in events))

    def test_logical_limit_rejects_a_compact_shared_dag(self):
        case = _fixture_case()
        root, specs, selected = self._direct_inputs(case)
        baseline, _ = build_direct_shared_topology(
            PreflopConfig.from_dict(case["config"]), specs, selected)
        self.assertLess(baseline.census.unique_vertices,
                        baseline.census.expanded_logical_visits)
        limits = replace(TopologyLimits(),
                         max_logical_visits=baseline.census.expanded_logical_visits - 1)
        with self.assertRaisesRegex(ValueError, "logical-visit"):
            build_direct_shared_topology(
                PreflopConfig.from_dict(case["config"]), specs, selected, limits=limits)

    def test_partial_logical_admission_stops_before_full_memo_growth(self):
        case = _fixture_case()
        _root, specs, selected = self._direct_inputs(case)
        config = PreflopConfig.from_dict(case["config"])
        baseline, receipt = build_direct_shared_topology(config, specs, selected)
        self.assertGreater(receipt["memoized_betting_states"], 100)
        rejected_at = []
        original = __import__(
            "pokerlab.direct_shared_topology", fromlist=["_DirectBuilder"]
        )._DirectBuilder._reserve_logical

        def observe(self, *, states=0, decisions=0, template=True):
            try:
                return original(self, states=states, decisions=decisions,
                                template=template)
            except ValueError:
                rejected_at.append((len(self.betting_states), len(self.vertices),
                                    self.global_logical_states + states))
                raise

        limits = replace(TopologyLimits(), max_logical_visits=500)
        with patch("pokerlab.direct_shared_topology._DirectBuilder._reserve_logical",
                   new=observe):
            with self.assertRaisesRegex(ValueError, "logical-visit"):
                build_direct_shared_topology(config, specs, selected, limits=limits)
        self.assertTrue(rejected_at)
        self.assertLess(rejected_at[0][0], receipt["memoized_betting_states"])
        self.assertLess(rejected_at[0][1], baseline.census.unique_vertices)

    def test_streaming_selected_input_reserves_before_consuming_more(self):
        case = _fixture_case()
        _root, specs, selected = self._direct_inputs(case)
        consumed = []

        def rows():
            for row in selected:
                consumed.append(row)
                yield row

        limits = replace(TopologyLimits(), max_build_scratch_entries=10)
        with self.assertRaisesRegex(ValueError, "build-scratch"):
            build_direct_shared_topology(
                PreflopConfig.from_dict(case["config"]), specs, rows(), limits=limits)
        self.assertEqual(len(consumed), 1)

    def test_malformed_inputs_and_source_tree_lifetime(self):
        case = _fixture_case()
        _root, specs, selected = self._direct_inputs(case)
        config = PreflopConfig.from_dict(case["config"])
        with self.assertRaises(ValueError):
            build_direct_shared_topology(config, specs, [(('2c', '3c', '4d'), '2c', '8h')])
        with self.assertRaises(ValueError):
            build_direct_shared_topology(config, {"flop": specs["flop"]}, selected)
        with self.assertRaises(TypeError):
            build_direct_shared_topology({}, specs, selected)

        original = preflop_solver.build_preflop_tree
        roots = []

        def capture(*args, **kwargs):
            tree = original(*args, **kwargs)
            roots.append(weakref.ref(tree.root))
            return tree

        with patch("pokerlab.direct_shared_topology.build_preflop_tree", side_effect=capture):
            topology, _receipt = build_direct_shared_topology(config, specs, selected)
        gc.collect()
        self.assertIsNone(roots[-1]())
        forbidden = (preflop_solver.PreflopContinuation,
                     preflop_solver._Node, preflop_solver._Terminal,
                     preflop_solver._Chance)
        self.assertFalse(any(isinstance(vertex, forbidden)
                            for vertex in topology.vertices))


if __name__ == "__main__":
    unittest.main()
