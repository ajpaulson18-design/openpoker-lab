import tempfile
import unittest
from contextlib import contextmanager
from contextlib import nullcontext
from fractions import Fraction
from pathlib import Path
from unittest.mock import patch

from scripts import benchmark_flop_class_owned_fingerprint as harness
from scripts.flop_class_reweight_proof import WeightedClassModel
from scripts.flop_multistreet_validation import _Chance, _Decision, _Terminal


class FingerprintHarnessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.output = Path(self.temp.name) / "evidence"
        self.plan = harness.trainer.case_plan("baseline")
        self.world = ("AsAd", "AsKh", Fraction(1, 3), ("5s", "6s"),
                      ("2c", "3d", "4h"))
        worlds0 = [self.world] * 5940
        worlds1 = [self.world] * 5940
        terminal = _Terminal((), "showdown", (0.0, 2.0), 0)
        action = {"name": "bet", "amount": 1.0}
        root = _Decision((), 0, "flop", ("2c", "3d", "4h"),
                         (action,), (terminal, terminal))
        key = (root.player, root.history)
        nodes = {key: root}
        chance = _Chance((), 0, "turn", (("5s", root),))
        self.model = WeightedClassModel(
            self.plan,
            {"worlds": worlds0, "public_states": 3, "tree": chance,
             "signs": {"AsAd|AsKh": (1, -1, 0)}},
            {"worlds": worlds1, "public_states": 3, "nodes": nodes,
             "root": root, "tree": chance,
             "pair_probabilities": {"AsAd|AsKh": Fraction(1, 3)}},
            {"turn_classes": ("t",), "river_classes": ("r",),
             "maps": {"t": ("5s", "6s")}, "infos": {"info": 2},
             "node_index": {"info": root}},
            {"t": ("5s", "6s")}, {"r": ("7s",)}, (self.world,), root,
            dict(harness.reweighted.EXPECTED_CENSUS))
        self.root = root
        self.nodes = nodes
        self.node_key = key
        self.original_action = action["amount"]
        self.original_node = nodes[key]
        self.guard = {f"authority_{i:02d}": 0 for i in range(40)}
        self.source_state = {"revision": "a" * 40, "status": "",
                             "source_lf_sha256": {f"source-{i}": f"{i:064x}"
                                                   for i in range(39)}}

    def _patches(self, *, snapshot=None, build=None, validate=None, verify=None,
                 real_guard=False, guard_context=None):
        stack = []
        stack.append(patch.object(harness, "_output_directory",
                                  side_effect=lambda _: self.output.mkdir() or self.output))
        stack.append(patch.object(harness, "_snapshot",
                                  side_effect=snapshot or (lambda: dict(self.source_state))))
        stack.append(patch.object(harness.prerequisite, "verify",
                                  side_effect=verify or (lambda: {
                                      "status": "saved-baseline-diagnostic-authenticated",
                                      "samples": 2, "recorded_training_calls": 2,
                                      "training_calls": 0, "phase_events": 13,
                                      "index_sha256": harness.prerequisite.INDEX_SHA256})))
        stack.append(patch.object(harness.trainer, "case_plan", return_value=self.plan))
        stack.append(patch.object(harness.reweighted, "build_model",
                                  side_effect=build or (lambda plan: self.model)))
        stack.append(patch.object(harness.reweighted, "validate_model",
                                  side_effect=validate or (lambda model: None)))
        if not real_guard:
            @contextmanager
            def guard():
                try:
                    yield self.guard
                finally:
                    self.guard["authority_40"] = 0
            stack.append(patch.object(harness.proof, "independent_guard",
                                      guard_context or guard))
        return stack

    def _run_with(self, **kwargs):
        stack = self._patches(**kwargs)
        entered = []
        try:
            for item in stack:
                entered.append(item.__enter__())
            return harness.run(self.output)
        finally:
            for item in reversed(stack[:len(entered)]):
                item.__exit__(None, None, None)

    def _run_with_real_guard(self):
        stack = self._patches(real_guard=True)
        entered = []
        try:
            for item in stack:
                entered.append(item.__enter__())
            return harness.run(self.output)
        finally:
            for item in reversed(stack[:len(entered)]):
                item.__exit__(None, None, None)

    def test_real_protocol_reader_and_admission(self):
        raw, spec = harness._protocol()
        admission = harness._preflight(spec)
        self.assertGreater(len(raw), 0)
        self.assertEqual(admission["fingerprint_calls"], 6)
        self.assertEqual(admission["total_named_objects_and_edges"], 48_000_000)
        self.assertEqual(admission["batch_named_cap"], 50_000_000)

    def test_success_runs_six_probes_validates_twice_and_restores_mutations(self):
        validate_calls = []
        with patch.object(harness, "fingerprint", wraps=harness.fingerprint) as calls:
            report = self._run_with(validate=lambda model: validate_calls.append(
                (model.physical["root"].actions[0]["amount"],
                 model.physical["nodes"][self.node_key] is self.original_node)))
        self.assertEqual(calls.call_count, 6)
        expected_limits = harness._preflight(harness._protocol()[1])["limits"]
        for call in calls.call_args_list:
            self.assertEqual({name: getattr(call.kwargs["limits"], name)
                              for name in harness.Limits.__slots__}, expected_limits)
        self.assertEqual(report["status"], "complete")
        self.assertEqual([row["sample_id"] for row in report["fingerprints"]],
                         list(harness.SAMPLES))
        self.assertEqual(report["fingerprint_calls"], 6)
        self.assertEqual(report["full_validations"], 2)
        self.assertEqual(report["training_calls"], 0)
        self.assertEqual(report["authority_calls"], self.guard)
        self.assertEqual(validate_calls, [(self.original_action, True)] * 2)
        self.assertEqual(self.root.actions[0]["amount"], self.original_action)
        self.assertIs(self.nodes[self.node_key], self.original_node)

    def test_admission_failure_precedes_authentication_and_model_build(self):
        with patch.object(harness, "_preflight", side_effect=ValueError("admission")), \
             patch.object(harness.prerequisite, "verify",
                          side_effect=AssertionError("auth called")), \
             patch.object(harness.reweighted, "build_model",
                          side_effect=AssertionError("model built")):
            report = harness.run(self.output)
        self.assertEqual(report["status"], "error")
        self.assertIn("admission", report["errors"][0]["message"])
        self.assertEqual(report["fingerprint_calls"], 0)

    def test_source_failure_precedes_authentication_and_model_build(self):
        with patch.object(harness, "_snapshot", side_effect=ValueError("dirty source")), \
             patch.object(harness.prerequisite, "verify",
                          side_effect=AssertionError("auth called")), \
             patch.object(harness.reweighted, "build_model",
                          side_effect=AssertionError("model built")):
            report = harness.run(self.output)
        self.assertEqual(report["status"], "error")
        self.assertIn("dirty source", report["errors"][0]["message"])
        self.assertIsNone(report["prerequisite"])
        self.assertEqual(report["fingerprint_calls"], 0)

    def test_fingerprint_failure_retains_partial_census_restores_action_and_stops(self):
        real = harness.fingerprint
        calls = 0
        def fail_third(value, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 3:
                error = harness.owned_fingerprint.FingerprintError("bounded failure")
                error.partial_census = {"objects": 7, "edges": 9, "partial": True}
                raise error
            return real(value, **kwargs)
        report = self._run_with()
        # Repeat with the injected failure after the ordinary success setup.
        self.output = Path(self.temp.name) / "failure"
        with patch.object(harness, "fingerprint", side_effect=fail_third):
            failed = self._run_with()
        self.assertEqual(report["status"], "complete")
        self.assertEqual(failed["status"], "error")
        self.assertEqual(failed["fingerprint_calls"], 3)
        self.assertEqual(len(failed["fingerprints"]), 3)
        self.assertEqual(failed["fingerprints"][-1]["partial_census"],
                         {"objects": 7, "edges": 9, "partial": True})
        self.assertEqual(self.root.actions[0]["amount"], self.original_action)
        self.assertIs(self.nodes[self.node_key], self.original_node)
        self.assertEqual(calls, 3)

    def test_alias_fingerprint_failure_restores_node_index_and_stops(self):
        real = harness.fingerprint
        calls = 0
        def fail_fifth(value, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 5:
                raise harness.owned_fingerprint.FingerprintError("alias probe failed")
            return real(value, **kwargs)
        with patch.object(harness, "fingerprint", side_effect=fail_fifth):
            report = self._run_with()
        self.assertEqual(report["status"], "error")
        self.assertEqual(report["fingerprint_calls"], 5)
        self.assertIs(self.nodes[self.node_key], self.original_node)
        self.assertEqual(self.root.actions[0]["amount"], self.original_action)
        self.assertEqual(report["fingerprints"][-1]["sample_id"], "node-index-alias")

    def test_initial_validation_failure_is_not_retried_or_followed_by_probes(self):
        calls = []
        def fail_validation(model):
            calls.append(model)
            raise ValueError("initial validation failed")
        report = self._run_with(validate=fail_validation)
        self.assertEqual(report["status"], "error")
        self.assertEqual(report["full_validations"], 1)
        self.assertEqual(report["fingerprint_calls"], 0)
        self.assertEqual(len(calls), 1)
        self.assertIn("initial validation failed", report["errors"][0]["message"])

    def test_probe_and_cleanup_validation_failures_preserve_primary_error(self):
        validation_calls = 0
        def fail_cleanup_only(model):
            nonlocal validation_calls
            validation_calls += 1
            if validation_calls == 2:
                raise RuntimeError("cleanup validation failed")
        def fail_first_fingerprint(value, **kwargs):
            error = harness.owned_fingerprint.FingerprintError("primary probe failed")
            error.partial_census = {"partial": True}
            raise error
        with patch.object(harness, "fingerprint", side_effect=fail_first_fingerprint):
            report = self._run_with(validate=fail_cleanup_only)
        self.assertEqual(report["status"], "error")
        self.assertEqual(report["fingerprint_calls"], 1)
        self.assertEqual(report["full_validations"], 2)
        self.assertIn("primary probe failed", report["errors"][0]["message"])
        self.assertEqual(report["errors"][1]["phase"], "final-model-validation")
        self.assertIn("cleanup validation failed", report["errors"][1]["message"])
        self.assertEqual(report["fingerprints"][0]["partial_census"], {"partial": True})

    def test_cli_uses_reversible_execution_context_and_returns_failure_status(self):
        with patch.object(harness.sys, "platform", "win32"), \
             patch.object(harness.power, "measurement_execution_state",
                          return_value=nullcontext({"mode": "windows-benchmark-thread",
                              "system_required": True, "requested_flags": 0x80000001,
                              "previous_flags": 1})), \
             patch.object(harness, "run", return_value={
                 "status": "error", "fingerprint_calls": 2, "full_validations": 1,
                 "training_calls": 0, "report_sha256": "a" * 64}) as run:
            result = harness.main(["--output", str(self.output)])
        self.assertEqual(result, 1)
        self.assertEqual(run.call_args.kwargs["execution_state"]["mode"],
                         "windows-benchmark-thread")

    def test_probe_failure_with_real_independent_guard_merges_full_inventory(self):
        def fail_fingerprint(value, **kwargs):
            error = harness.owned_fingerprint.FingerprintError("synthetic real-guard failure")
            error.partial_census = {"partial": True}
            raise error
        with patch.object(harness, "fingerprint", side_effect=fail_fingerprint):
            report = self._run_with_real_guard()
        self.assertEqual(report["status"], "error")
        self.assertIn("synthetic real-guard failure", report["errors"][0]["message"])
        self.assertEqual(len(report["authority_calls"]), 41)
        self.assertTrue(all(type(value) is int and value == 0
                            for value in report["authority_calls"].values()))
        self.assertEqual(report["fingerprints"][0]["partial_census"], {"partial": True})

    def test_nonzero_guard_counts_are_retained_in_failed_report(self):
        @contextmanager
        def forbidden_guard():
            calls = {f"authority_{i:02d}": 0 for i in range(40)}
            try:
                yield calls
            finally:
                calls["authority_40"] = 0
                calls["authority_00"] = 1
        report = self._run_with(guard_context=forbidden_guard)
        self.assertEqual(report["status"], "error")
        self.assertEqual(len(report["authority_calls"]), 41)
        self.assertEqual(report["authority_calls"]["authority_00"], 1)
        self.assertTrue(any("not zero" in item["message"]
                            for item in report["errors"]))


if __name__ == "__main__":
    unittest.main()
