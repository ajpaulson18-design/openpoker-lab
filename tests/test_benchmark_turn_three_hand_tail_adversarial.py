"""Adversarial checks for saved evidence and publication guards.

Fault-path checks use explicit audit/control stubs; the primary suite owns the
actual physical reference and exact-oracle exercise.
"""
import copy
import hashlib
import json
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from scripts import benchmark_turn_three_hand_tail as runner
from pokerlab import turn_tail_adapter


def _maps():
    verification = {name: hashlib.sha256(("v:" + name).encode()).hexdigest()
                    for name in runner.VERIFY_PATHS}
    producer = {name: hashlib.sha256(name.encode()).hexdigest()
                for name in runner.HISTORICAL_PRODUCER_REQUIRED}
    producer.update(verification)
    producer["pokerlab/future_module.py"] = hashlib.sha256(b"future").hexdigest()
    return producer, verification


def _audit():
    deltas = {name: 0.0 for name in runner.METRICS}
    return {
        "policy_metadata": {"method": "synthetic accepted policy"},
        "api_numeric_replay_deltas": dict(deltas),
        "exact_numeric_replay_deltas": dict(deltas),
        "exact_metrics_fractions": {name: f"exact:{name}" for name in runner.METRICS},
        "exact_counters": {"synthetic": 7},
        "target_nash_conv_fraction": "1/1000",
        "exact_threshold_met": False,
        "exact_nash_conv_zero": False,
        "oop_response_gain_fraction": "2/3",
        "ip_response_gain_fraction": "4/5",
        "legal_response_interval_fraction": ["-1/3", "2/3"],
        "profile_value_fraction": "1/7",
        "profile_strictly_inside_response_interval": True,
    }


def _control():
    return {"metrics_fractions": {name: "control" for name in runner.METRICS},
            "counters": {"synthetic": 3}, "training_calls": 0}


class TurnThreeHandTailAdversarialTests(unittest.TestCase):
    def setUp(self):
        self.root = runner.ROOT / "work" / ".adversarial_test_tmp" / uuid.uuid4().hex
        (self.root / "benchmarks" / "results").mkdir(parents=True)
        self.rejected_files = []
        original_preserve = runner._preserve_rejected

        def track_preserved(*args, **kwargs):
            path = original_preserve(*args, **kwargs)
            self.rejected_files.append(path)
            return path

        tracker = patch.object(runner, "_preserve_rejected", side_effect=track_preserved)
        tracker.start()
        self.addCleanup(tracker.stop)

    def tearDown(self):
        expected_parent = (runner.ROOT / "work" / ".adversarial_test_tmp").resolve()
        self.assertEqual(self.root.resolve().parent, expected_parent)
        for path in (*runner._targets(self.root).values(), *self.rejected_files):
            if path.exists():
                path.unlink()
        # Refuse unknown leftovers rather than recursively deleting the UUID.
        for path in (self.root / "work" / "turn_three_hand_tail_rejected",
                     self.root / "benchmarks" / "results", self.root / "work",
                     self.root / "benchmarks", self.root):
            if path.exists():
                path.rmdir()

    def _bundle(self, audit=None):
        producer, verification = _maps()
        payload = {"synthetic_policy": [0.25, 0.75]}
        policy_raw = runner._canonical(payload)
        audit = copy.deepcopy(audit or _audit())
        report = runner._build_report("a" * 40, producer, verification, payload,
                                      audit, 1.25, policy_raw, _control())
        return (runner._canonical(report), policy_raw, report, producer, verification)

    def test_historical_maps_are_typed_and_allow_only_future_producer_modules(self):
        producer, verification = _maps()
        runner._validate_historical_map(producer, runner.HISTORICAL_PRODUCER_REQUIRED,
                                        producer=True)
        runner._validate_historical_map(verification, set(runner.VERIFY_PATHS))
        # Historical producer context is syntax-checked, not looked up in Git.
        report = {"schema": runner.SCHEMA, "schema_version": 1,
                  "generation_head": "a" * 40,
                  "historical_producer_source_sha256": producer,
                  "verification_source_sha256": verification,
                  "actual_complete_call_seconds": 0.0}
        self.assertEqual(runner._validate_report(report, self.root), 0.0)
        mismatched = copy.deepcopy(report)
        mismatched["historical_producer_source_sha256"][runner.VERIFY_PATHS[0]] = "f" * 64
        with self.assertRaisesRegex(ValueError, "identities disagree"):
            runner._validate_report(mismatched, self.root)
        for bad in (123, "A" * 64, "0" * 63, None):
            changed = dict(producer)
            changed["pokerlab/future_module.py"] = bad
            with self.assertRaises(ValueError):
                runner._validate_historical_map(changed,
                    runner.HISTORICAL_PRODUCER_REQUIRED, producer=True)
        changed = dict(producer)
        changed["pokerlab/future-module.py"] = "0" * 64
        with self.assertRaises(ValueError):
            runner._validate_historical_map(changed,
                runner.HISTORICAL_PRODUCER_REQUIRED, producer=True)
        nested = dict(producer)
        nested["pokerlab/subdir/module.py"] = "0" * 64
        with self.assertRaises(ValueError):
            runner._validate_historical_map(nested,
                runner.HISTORICAL_PRODUCER_REQUIRED, producer=True)
        with self.assertRaises(ValueError):
            runner._validate_historical_map(producer, set(runner.VERIFY_PATHS))
        bad_head = dict(report, generation_head="A" * 40)
        with self.assertRaises(ValueError):
            runner._validate_report(bad_head, self.root)

    def test_saved_numeric_observations_have_tolerance_but_exact_metrics_do_not(self):
        raw_report, raw_policy, report, _, verification = self._bundle()
        mutable = copy.deepcopy(report)
        for name in ("api_numeric_replay_deltas", "exact_numeric_replay_deltas"):
            mutable["results"][name][runner.METRICS[0]] = 5e-10
        raw_report = runner._canonical(mutable)
        with patch.object(runner, "_control", return_value=_control()), \
             patch.object(runner, "_audit", return_value=_audit()):
            replayed = runner._verify_bundle(raw_report, raw_policy, root=self.root,
                                             head="b" * 40, verification=verification)
        self.assertEqual(replayed["results"]["exact_metrics_fractions"],
                         report["results"]["exact_metrics_fractions"])
        self.assertEqual(replayed["results"]["exact_numeric_replay_deltas"][runner.METRICS[0]],
                         5e-10)
        mutable["results"]["exact_numeric_replay_deltas"][runner.METRICS[0]] = 1.1e-9
        with patch.object(runner, "_control", return_value=_control()), \
             patch.object(runner, "_audit", return_value=_audit()):
            with self.assertRaisesRegex(ValueError, "tolerance"):
                runner._verify_bundle(runner._canonical(mutable), raw_policy,
                                      root=self.root, head="b" * 40,
                                      verification=verification)

    def test_complete_reconstruction_rejects_unknown_report_section(self):
        raw_report, raw_policy, report, _, verification = self._bundle()
        report["unverified_extra"] = {"claim": True}
        with patch.object(runner, "_control", return_value=_control()), \
             patch.object(runner, "_audit", return_value=_audit()):
            with self.assertRaisesRegex(ValueError, "complete independent reconstruction"):
                runner._verify_bundle(runner._canonical(report), raw_policy,
                                      root=self.root, head="b" * 40,
                                      verification=verification)
            report.pop("unverified_extra")
            report["results"]["exact_metrics_fractions"][runner.METRICS[0]] = "tampered"
            with self.assertRaisesRegex(ValueError, "complete independent reconstruction"):
                runner._verify_bundle(runner._canonical(report), raw_policy,
                                      root=self.root, head="b" * 40,
                                      verification=verification)

    def test_stage_same_inode_byte_rewrite_is_rejected_and_cleaned(self):
        producer, verification = _maps()
        original = runner.base._owned_write

        def rewrite_same_inode(path, raw, owned):
            original(path, raw, owned)
            if path.name.endswith(".stage"):
                path.write_bytes(raw + b"tamper")

        with patch.object(runner, "_guard_generation", return_value=None), \
             patch.object(runner.base, "_owned_write", side_effect=rewrite_same_inode):
            with self.assertRaisesRegex(RuntimeError, "bytes changed"):
                runner._publish(b"report", b"policy", root=self.root, head="a" * 40,
                                producer=producer, verification=verification)
        self.assertFalse(any(path.exists() for path in runner._targets(self.root).values()))
        self.assertFalse(list((self.root / "benchmarks" / "results").glob("*.stage")))

    def test_final_same_inode_byte_rewrite_is_rejected_and_cleaned(self):
        producer, verification = _maps()
        original_publish = runner.base._publish_staged
        final_report = runner._targets(self.root)["report"]

        def rewrite_after_publish(stages, targets, owned):
            original_publish(stages, targets, owned)
            final_report.write_bytes(b"same inode, changed bytes")

        with patch.object(runner, "_guard_generation", return_value=None), \
             patch.object(runner, "_verify_bundle", return_value={}), \
             patch.object(runner.base, "_publish_staged", side_effect=rewrite_after_publish):
            with self.assertRaisesRegex(RuntimeError, "bytes changed"):
                runner._publish(b"report", b"policy", root=self.root, head="a" * 40,
                                producer=producer, verification=verification)
        self.assertFalse(any(path.exists() for path in runner._targets(self.root).values()))

    def test_foreign_final_inode_replacement_is_preserved(self):
        producer, verification = _maps()
        original_publish = runner.base._publish_staged
        foreign = runner._targets(self.root)["report"]

        def replace_after_publish(stages, targets, owned):
            original_publish(stages, targets, owned)
            foreign.unlink()
            foreign.write_bytes(b"foreign replacement")

        with patch.object(runner, "_guard_generation", return_value=None), \
             patch.object(runner, "_verify_bundle", return_value={}), \
             patch.object(runner.base, "_publish_staged", side_effect=replace_after_publish):
            with self.assertRaisesRegex(RuntimeError, "inode"):
                runner._publish(b"report", b"policy", root=self.root, head="a" * 40,
                                producer=producer, verification=verification)
        self.assertEqual(foreign.read_bytes(), b"foreign replacement")
        self.assertFalse(runner._targets(self.root)["policy"].exists())

    def test_last_publish_guards_are_source_then_bundle_bytes(self):
        producer, verification = _maps()
        calls = []
        real_bundle_guard = runner._bundle_guard

        def source_guard(*args, **kwargs):
            calls.append("source")

        def bundle_guard(*args, **kwargs):
            calls.append("bundle")
            return real_bundle_guard(*args, **kwargs)

        with patch.object(runner, "_guard_generation", side_effect=source_guard), \
             patch.object(runner, "_bundle_guard", side_effect=bundle_guard), \
             patch.object(runner, "_verify_bundle", return_value={}):
            runner._publish(b"report", b"policy", root=self.root, head="a" * 40,
                            producer=producer, verification=verification)
        self.assertEqual(calls[-2:], ["source", "bundle"])

    def test_rejected_unserializable_return_and_nonfinite_elapsed_are_preserved_safely(self):
        class BadRepr:
            def __repr__(self):
                raise RuntimeError("repr denied")

        producer, verification = _maps()
        target = runner._preserve_rejected(self.root, BadRepr(), None, "a" * 40,
                                           producer, verification, float("inf"), True,
                                           ValueError("synthetic failure"))
        saved = json.loads(target.read_bytes())
        self.assertIs(saved["call_completed"], True)
        self.assertIsNone(saved["actual_complete_call_seconds"])
        self.assertEqual(saved["invalid_elapsed_repr"], "inf")
        self.assertIn("repr failed", saved["unserialized_returned_policy_repr"])

    def test_verify_is_read_only_and_never_calls_adapter(self):
        report_raw, policy_raw, report, _, verification = self._bundle()
        targets = runner._targets(self.root)
        targets["report"].write_bytes(report_raw)
        targets["policy"].write_bytes(policy_raw)
        head = "b" * 40
        with patch.object(runner, "_verification_context", return_value=(head, verification)), \
             patch.object(runner, "_guard_replay", return_value=None), \
             patch.object(runner, "_control", return_value=_control()), \
             patch.object(runner, "_audit", return_value=_audit()), \
             patch.object(turn_tail_adapter, "solve_turn_tail",
                          side_effect=AssertionError("verify called producer")), \
             patch.object(turn_tail_adapter, "_train_original_weight_tail",
                          side_effect=AssertionError("verify called trainer")):
            replayed = runner.verify(self.root)
        self.assertEqual(runner._canonical(replayed), report_raw)

    def test_generation_runs_context_guard_and_control_before_synthetic_api(self):
        producer, verification = _maps()
        events = []

        def guard(*args):
            events.append("guard")

        def control(*args, **kwargs):
            events.append("control")
            return _control()

        def invalid_api(*args, **kwargs):
            events.append("api")
            return None

        with patch.object(runner, "_source_context",
                          side_effect=lambda root: (events.append("context") or
                                                    ("a" * 40, producer, verification))), \
             patch.object(runner, "_guard_generation", side_effect=guard), \
             patch.object(runner, "_control", side_effect=control), \
             patch.object(turn_tail_adapter, "solve_turn_tail", side_effect=invalid_api):
            with self.assertRaises((ValueError, TypeError)):
                runner.generate(self.root)
        self.assertLess(events.index("guard"), events.index("control"))
        self.assertLess(events.index("context"), events.index("guard"))
        api_index = events.index("api")
        self.assertEqual(events[api_index - 1], "guard")
        self.assertLess(events.index("control"), api_index)

    def test_late_source_guard_blocks_the_api_before_invocation(self):
        producer, verification = _maps()
        calls = 0

        def guard(*args):
            nonlocal calls
            calls += 1
            if calls == 3:
                raise RuntimeError("late source drift")

        with patch.object(runner, "_source_context",
                          return_value=("a" * 40, producer, verification)), \
             patch.object(runner, "_guard_generation", side_effect=guard), \
             patch.object(runner, "_control", return_value=_control()), \
             patch.object(turn_tail_adapter, "solve_turn_tail") as api:
            with self.assertRaisesRegex(RuntimeError, "late source drift"):
                runner.generate(self.root)
        api.assert_not_called()

    def test_generation_preserves_each_completed_invalid_return(self):
        class Unserializable:
            def __repr__(self):
                raise RuntimeError("repr unavailable")

        producer, verification = _maps()
        for returned, end in ((Unserializable(), 2.0), ({"synthetic": True}, float("inf"))):
            with self.subTest(return_type=type(returned).__name__), \
                 patch.object(runner, "_source_context",
                              return_value=("a" * 40, producer, verification)), \
                 patch.object(runner, "_guard_generation", return_value=None), \
                 patch.object(runner, "_control", return_value=_control()), \
                 patch.object(runner, "_validate_profile_metadata", return_value={}), \
                 patch.object(runner, "_audit", return_value=_audit()), \
                 patch.object(runner.time, "perf_counter", side_effect=(1.0, end)), \
                 patch.object(turn_tail_adapter, "solve_turn_tail", return_value=returned) as api, \
                 patch.object(turn_tail_adapter, "_train_original_weight_tail",
                              side_effect=AssertionError("synthetic test reached trainer")):
                with self.assertRaises((ValueError, TypeError)):
                    runner.generate(self.root)
            api.assert_called_once()
            record = json.loads(self.rejected_files[-1].read_bytes())
            self.assertIs(record["call_completed"], True)
            if isinstance(returned, dict):
                self.assertIsNotNone(record["raw_policy_base64"])
                self.assertIsNone(record["actual_complete_call_seconds"])
            else:
                self.assertIn("repr failed", record["unserialized_returned_policy_repr"])


if __name__ == "__main__":
    unittest.main()
