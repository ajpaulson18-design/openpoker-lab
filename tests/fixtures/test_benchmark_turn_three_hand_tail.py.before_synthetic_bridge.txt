"""Bounded lifecycle tests; solver calls are explicit synthetic stubs."""
import copy
import hashlib
import json
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch


from scripts import benchmark_turn_three_hand_tail as runner
from scripts import turn_three_hand_reference as reference
from scripts import turn_three_hand_exact_oracle as exact_oracle
from scripts import turn_river_validation as validator
from pokerlab import turn_tail_adapter


def _payload():
    game = reference.model()
    result = reference.make_check_call_policy(game)
    metrics = exact_oracle.audit_policy(result, game)["metrics"]
    result.update(runner._expected_metadata())
    result.pop("compatible_world_count", None)
    result.update({key: float(value) for key, value in metrics.items()})
    result["scope"] = (
        "Research profile for a configured heads-up turn/river game; no preflop, "
        "multiway play, rake, or general exact-equilibrium claim."
    )
    result["diagnostic_provenance"] = (
        "Metrics recomputed from the direct original-weight tail policy using "
        "public-batched diagnostics; numeric convergence diagnostics are not an "
        "exact equilibrium certificate."
    )
    return result


def _fake_maps(root):
    head = "a" * 40
    producer_names = runner._source_paths(root, True)
    producer = {name: hashlib.sha256(name.encode()).hexdigest() for name in producer_names}
    verification = {name: producer[name] for name in runner.VERIFY_PATHS}
    return head, producer, verification


class TurnThreeHandTailTests(unittest.TestCase):
    def setUp(self):
        self.root = runner.ROOT / "work" / ".test_tmp" / uuid.uuid4().hex
        self.root.mkdir(parents=True)
        self._extra_files = []
        original_preserve = runner._preserve_rejected

        def track_preserved(*args, **kwargs):
            path = original_preserve(*args, **kwargs)
            self._extra_files.append(path)
            return path

        tracker = patch.object(runner, "_preserve_rejected", side_effect=track_preserved)
        tracker.start()
        self.addCleanup(tracker.stop)

    def tearDown(self):
        # Each test owns this UUID directory. Remove its known targets/rejection
        # files and explicitly tracked source fixtures, then only empty dirs.
        self.assertEqual(self.root.resolve().parent,
                         (runner.ROOT / "work" / ".test_tmp").resolve())
        for path in (*runner._targets(self.root).values(), *self._extra_files):
            if path.exists():
                path.unlink()
        rejected = self.root / "work" / "turn_three_hand_tail_rejected"
        if rejected.exists():
            rejected.rmdir()
        known_dirs = [self.root / "benchmarks" / "results",
                      self.root / "benchmarks",
                      self.root / "fixture_repo" / "pokerlab",
                      self.root / "fixture_repo" / "scripts",
                      self.root / "fixture_repo" / "tests",
                      self.root / "fixture_repo", self.root / "work"]
        for directory in sorted(known_dirs, key=lambda item: len(item.parts), reverse=True):
            if directory.exists():
                directory.rmdir()
        if self.root.exists():
            self.root.rmdir()

    def test_real_control_anchor_and_fixed_preflight(self):
        control = runner._control(self.root)
        self.assertEqual(control["training_calls"], 0)
        self.assertEqual(control["metrics_fractions"]["value_oop"], "-9500/891")
        self.assertEqual(control["metrics_fractions"]["nash_conv"], "64475/891")
        self.assertEqual(control["counters"]["rank_keys"], 276)
        self.assertEqual(control["counters"]["five_card_calls"], 5796)
        self.assertEqual(control["counters"]["structural_node_visits"], 27351)

    def test_metadata_fieldset_matches_saved_production_adapter_schema(self):
        repo = Path(reference.__file__).resolve().parents[1]
        source = repo / "benchmarks" / "results" / \
            "full-deck-raised-turn-direct-tail-v1-materialized.json"
        self.assertLessEqual(source.stat().st_size, runner.BYTE_CAP)
        with source.open("rb") as stream:
            raw = stream.read(runner.BYTE_CAP + 1)
        self.assertLessEqual(len(raw), runner.BYTE_CAP)
        saved = json.loads(raw)
        expected = set(runner.PROFILE_FIELDS) | set(runner.METRICS) | {
            "scope", "diagnostic_provenance", "strategy"
        }
        self.assertEqual(set(saved), expected)
        self.assertNotIn("compatible_world_count", saved)

    def test_synthetic_stub_full_fixed_call_and_saved_read_only_replay(self):
        """Synthetic API return exercises full publication, not a training result."""
        payload = _payload()
        actual_head, producer, verification = _fake_maps(self.root)
        events = []
        original_control = runner._control

        def controlled(root, guard=None):
            events.append("control")
            return original_control(root, guard)

        def solver(board, oop, ip, config, **kwargs):
            events.append("api")
            self.assertEqual((board, oop, ip, config),
                             (reference.FIXTURE["board"], reference.FIXTURE["oop"],
                              reference.FIXTURE["ip"], reference.FIXTURE["config"]))
            self.assertEqual(kwargs, {"iterations": 750, "discard": 250})
            return copy.deepcopy(payload)

        with patch.object(runner, "_source_context",
                          return_value=(actual_head, producer, verification)), \
             patch.object(runner, "_guard_generation", return_value=None), \
             patch.object(runner, "_control", side_effect=controlled), \
             patch.object(turn_tail_adapter, "_train_original_weight_tail",
                          side_effect=AssertionError("synthetic lifecycle reached trainer")), \
             patch.object(turn_tail_adapter, "solve_turn_tail", side_effect=solver):
            report = runner.generate(self.root)
        self.assertEqual(events[:2], ["control", "api"])
        self.assertEqual(report["completed_training_calls"], 1)
        self.assertEqual(report["control_before_training"]["training_calls"], 0)
        self.assertEqual(report["full_requested_world_node_work"], 28_512_000)
        self.assertEqual(report["full_requested_dense_hand_state_pass_work"], 20_540_601)
        self.assertEqual(report["results"]["exact_counters"]["structural_node_visits"], 27351)
        self.assertTrue(runner._targets(self.root)["report"].is_file())
        self.assertTrue(runner._targets(self.root)["policy"].is_file())
        with patch.object(runner, "_verification_context",
                          return_value=(actual_head, verification)), \
             patch.object(runner, "_guard_replay", return_value=None), \
             patch.object(turn_tail_adapter, "solve_turn_tail",
                          side_effect=AssertionError("verify must never train")):
            verified = runner.verify(self.root)
        self.assertEqual(runner._canonical(verified), runner._read_bounded(
            runner._targets(self.root)["report"]))

    def test_profile_rejects_boolean_and_altered_full_request_resource(self):
        good = _payload()
        runner._validate_profile_metadata(good)
        bool_tamper = copy.deepcopy(good)
        bool_tamper["iterations"] = True
        with self.assertRaises(ValueError):
            runner._validate_profile_metadata(bool_tamper)
        resource_tamper = copy.deepcopy(good)
        resource_tamper["resource_usage"]["full_requested_world_node_work"] -= 1
        with self.assertRaises(ValueError):
            runner._validate_profile_metadata(resource_tamper)

    def test_exact_numeric_disagreement_and_bad_report_delta_rejected(self):
        payload = _payload()
        runner._validate_profile_metadata(payload)
        metrics = exact_oracle.audit_policy(payload)["metrics"]
        numeric = validator.replay_policy(payload, reference.FIXTURE["oop"],
                                          reference.FIXTURE["ip"],
                                          board=reference.FIXTURE["board"],
                                          config=reference.FIXTURE["config"])
        self.assertLessEqual(max(abs(float(metrics[key]) - float(numeric[key]))
                                 for key in runner.METRICS), 1e-9)
        bad = dict(numeric)
        bad["value_oop"] += 1
        with self.assertRaises(ValueError):
            runner._compare_exact_numeric(metrics, bad)

    def test_source_guard_detects_new_top_level_producer_module(self):
        root = self.root / "fixture_repo"
        root.mkdir()
        names = set(runner.REQUIRED_PRODUCER) | set(runner.VERIFY_PATHS)
        names.add("pokerlab/current.py")
        for name in names:
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"# committed fixture\n")
            self._extra_files.append(path)
        producer = runner._hash_paths(root, runner._source_paths(root, True))
        verification = runner._hash_paths(root, runner.VERIFY_PATHS)
        with patch.object(runner, "_head", return_value="b" * 40):
            runner._guard_generation(root, "b" * 40, producer, verification)
            extra = root / "pokerlab" / "new_module.py"
            extra.write_bytes(b"# added after freeze\n")
            self._extra_files.append(extra)
            with self.assertRaisesRegex(RuntimeError, "source set changed"):
                runner._guard_generation(root, "b" * 40, producer, verification)

    def test_target_refusal_happens_before_control_or_api(self):
        target = runner._targets(self.root)["report"]
        target.parent.mkdir(parents=True)
        target.write_bytes(b"preserve")
        with patch.object(runner, "_source_context",
                          side_effect=AssertionError("must refuse before source work")), \
             patch.object(turn_tail_adapter, "solve_turn_tail",
                          side_effect=AssertionError("must refuse before trainer")):
            with self.assertRaises(FileExistsError):
                runner.generate(self.root)
        self.assertEqual(target.read_bytes(), b"preserve")

    def test_second_stage_write_failure_rolls_back_only_owned_stages(self):
        head, producer, verification = _fake_maps(self.root)
        targets = runner._targets(self.root)
        original = base_owned_write = runner.base._owned_write
        writes = []

        def fail_second(path, raw, owned):
            original(path, raw, owned)
            writes.append(path)
            if len(writes) == 2:
                raise OSError("injected stage write fault")

        with patch.object(runner, "_guard_generation", return_value=None), \
             patch.object(runner.base, "_owned_write", side_effect=fail_second):
            with self.assertRaisesRegex(OSError, "injected"):
                runner._publish(b"report", b"policy", root=self.root, head=head,
                                producer=producer, verification=verification)
        self.assertFalse(any(path.exists() for path in targets.values()))
        self.assertTrue(writes)
        for path in writes:
            self.assertFalse(path.exists())

    def test_none_return_is_preserved_after_completed_call(self):
        head, producer, verification = _fake_maps(self.root)
        with patch.object(runner, "_source_context",
                          return_value=(head, producer, verification)), \
             patch.object(runner, "_guard_generation", return_value=None), \
             patch.object(runner, "_control", return_value={"training_calls": 0}), \
             patch.object(turn_tail_adapter, "solve_turn_tail", return_value=None):
            with self.assertRaises(ValueError):
                runner.generate(self.root)
        rejected = list((self.root / "work" / "turn_three_hand_tail_rejected").glob("*.json"))
        self.assertEqual(len(rejected), 1)
        record = json.loads(rejected[0].read_bytes())
        self.assertIs(record["call_completed"], True)
        self.assertIsNotNone(record["raw_policy_base64"])


if __name__ == "__main__":
    unittest.main()
