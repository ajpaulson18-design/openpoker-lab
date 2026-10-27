"""Rank-free plan and wire controls for the direct selected-DAG backend."""
import os
import subprocess
import unittest
from unittest.mock import patch

from pokerlab.native_selected_dag import (
    PROTOCOL, _Context, executable_identity, prepare, train_native_selected_dag, wire,
)
from pokerlab.selected_operator_solver import _prepare
from pokerlab.shared_topology_view import SharedPublicView
from tests.test_selected_operator_solver import CASE, request


def direct_prepared(case=CASE):
    req = request(case)
    operator, topology, infos, _metadata, _specs, _census = _prepare(
        req, strategy_storage="packed", public_topology="direct")
    view = SharedPublicView(topology)
    operator.pot = 2 * view.anchor
    return req, operator, view, infos


class NativeSelectedDagPlanTests(unittest.TestCase):
    def test_rank_free_plan_contexts_rows_and_header(self):
        req, operator, view, infos = direct_prepared()
        with patch("pokerlab.selected_runout_operator.rank_hand",
                   side_effect=AssertionError("rank during prepare")):
            plan, receipt = prepare(view, infos, req.iterations, operator)
        self.assertEqual(receipt["version"], "native-selected-dag-work-v1")
        self.assertEqual(receipt["vertices"], len(view.topology.vertices))
        self.assertEqual(receipt["logical_visits"], view.topology.census.expanded_logical_visits)
        self.assertEqual(plan.preorder_keys, tuple(infos))
        self.assertEqual(receipt["rows"], len(infos))
        self.assertEqual(receipt["action_slots"], sum(infos.values()))
        self.assertEqual(receipt["contexts"], len(plan.contexts))
        self.assertEqual(receipt["context_edges"], sum(
            len(context.child_contexts) for context in plan.contexts))
        self.assertLessEqual(receipt["vertices"], receipt["contexts"])
        self.assertLessEqual(receipt["edges"], receipt["context_edges"])
        self.assertLess(receipt["modeled_heap_bytes"], receipt["heap_limit"])

        payload, keys, wire_receipt = wire(plan)
        self.assertEqual(keys, list(infos))
        self.assertEqual(wire_receipt["input_bytes"], len(payload))
        lines = payload.decode("ascii").splitlines()
        self.assertEqual(lines[0], PROTOCOL)
        self.assertEqual(len(lines[1].split()), 21)
        fields = list(map(int, lines[1].split()))
        self.assertEqual(fields[:6], [receipt[name] for name in
                         ("vertices", "edges", "contexts", "context_edges", "rows", "action_slots")])
        self.assertEqual(fields[6:8], receipt["hands"])
        self.assertEqual(fields[8:15], [receipt[name] for name in
                         ("selected_boards", "prefixes", "iterations", "mode", "root",
                          "logical_visits", "dense_decision_hand_slots")])
        self.assertEqual(fields[15:], receipt["structural_counters"])
        self.assertEqual(len(lines), 3 + sum(receipt["hands"]) +
                         2 * receipt["selected_boards"] + receipt["vertices"] +
                         receipt["edges"])

    def test_menu_alias_orphan_and_chance_partition_reject(self):
        req, operator, view, infos = direct_prepared()
        bad_infos = dict(infos)
        first_key = next(iter(bad_infos))
        bad_infos[first_key] += 1
        with self.assertRaisesRegex(ValueError, "information row|preorder|row/action"):
            prepare(view, bad_infos, req.iterations, operator)
        del bad_infos[first_key]
        with self.assertRaisesRegex(ValueError, "orphan|row/action"):
            prepare(view, bad_infos, req.iterations, operator)

        from dataclasses import replace
        from pokerlab.shared_public_topology import ChanceVertex
        vertices = list(view.topology.vertices)
        chance_id = next(index for index, vertex in enumerate(vertices)
                         if isinstance(vertex, ChanceVertex))
        vertex = vertices[chance_id]
        vertices[chance_id] = replace(vertex, branches=vertex.branches[:-1])
        topology = replace(view.topology, vertices=tuple(vertices))
        bad_view = SharedPublicView(topology)
        with self.assertRaisesRegex(ValueError, "partition|census"):
            prepare(bad_view, infos, req.iterations, operator)

    def test_wire_rank_vectors_and_native_output_mapping(self):
        req, operator, view, infos = direct_prepared()
        plan, _ = prepare(view, infos, req.iterations, operator)
        payload, keys, receipt = wire(plan)
        self.assertGreater(operator.rank_calls, 0)
        self.assertLessEqual(receipt["rank_entries"], 8192)
        counts = plan.row_counts
        output = [PROTOCOL, str(receipt["action_slots"]), "0", "0", "0"]
        for count in counts:
            output.extend([float(1 / count).hex()] * count)
        output.extend(["RSS", "1234"])
        completed = subprocess.CompletedProcess([], 0,
                                               (" ".join(output) + "\n").encode(), b"")
        manifest = {"protocol": PROTOCOL, "executable": "native-selected-dag-train.exe"}
        with patch("pokerlab.native_selected_dag.executable_identity", return_value=manifest), \
             patch("pokerlab.native_selected_dag.subprocess.run", return_value=completed) as run, \
             patch("pokerlab.native_selected_dag.Path.resolve", return_value=__import__("pathlib").Path("native-selected-dag-train.exe")):
            averages, trained = train_native_selected_dag(
                plan, executable="native-selected-dag-train.exe")
        run.assert_called_once()
        self.assertEqual(tuple(averages), tuple(keys))
        self.assertEqual(trained["calls"], 1)
        self.assertEqual(trained["native_process_lifetime_peak_working_set_bytes"], 1234)
        for key, probabilities in averages.items():
            self.assertEqual(len(probabilities), infos[key])

    def test_no_information_rows_authenticates_without_training(self):
        case = dict(CASE, config={"starting_stack": [0.5, 1]})
        req, operator, view, infos = direct_prepared(case)
        self.assertFalse(infos)
        plan, _ = prepare(view, infos, req.iterations, operator)
        with patch("pokerlab.native_selected_dag.executable_identity",
                   return_value={"protocol": PROTOCOL}) as identity, \
             patch("pokerlab.native_selected_dag.subprocess.run",
                   side_effect=AssertionError("empty game spawned")):
            averages, receipt = train_native_selected_dag(
                plan, executable="native-selected-dag-train.exe")
        identity.assert_called_once()
        self.assertEqual(averages, {})
        self.assertEqual(receipt["calls"], 0)

    def test_resource_caps_and_changed_inputs_reject_before_ranking_or_spawn(self):
        req, operator, view, infos = direct_prepared()
        with patch("pokerlab.selected_runout_operator.rank_hand", side_effect=AssertionError("rank")), \
             patch("pokerlab.native_selected_dag.subprocess.run", side_effect=AssertionError("spawn")):
            for name in ("MAX_WORK", "MAX_HEAP_BYTES", "MAX_RANK_ENTRIES", "MAX_CONTEXTS", "MAX_DEPTH"):
                with self.subTest(name=name), patch("pokerlab.native_selected_dag." + name, 1):
                    with self.assertRaises(ValueError):
                        prepare(view, infos, req.iterations, operator)
            plan, _ = prepare(view, infos, req.iterations, operator)
            operator.normalizer *= 2
            with self.assertRaisesRegex(ValueError, "changed after admission"):
                wire(plan)

    def test_identity_rejects_wrong_helper_name_and_manifest(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as temp:
            wrong = Path(temp) / "native-selected-train.exe"
            wrong.write_bytes(b"wrong helper")
            with self.assertRaisesRegex(ValueError, "protocol-specific"):
                executable_identity(wrong)
            right = Path(temp) / "native-selected-dag-train.exe"
            right.write_bytes(b"untrusted helper")
            (Path(temp) / "native-selected-dag-manifest.json").write_text('{"schema_version":1}')
            with self.assertRaisesRegex(ValueError, "identity|manifest|changed"):
                executable_identity(right)


if __name__ == "__main__":
    unittest.main()
