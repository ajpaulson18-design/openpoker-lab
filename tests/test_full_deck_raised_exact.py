"""Independent fixed-fixture tests for the saved-policy exact quotient audit."""
from copy import deepcopy
from dataclasses import replace
from fractions import Fraction as F
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from uuid import uuid4

from scripts import audit_full_deck_raised_exact as audit
from scripts import full_deck_raised_reference as reference

ROOT_TMP = reference.ROOT / "tmp-full-deck-raised-exact-tests"


class FullDeckRaisedExactAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture, cls.board, cls.config, cls.worlds, cls.selected, cls.root, _ = reference.model()
        cls.policy_rows = reference._policy_rows(reference._walk(cls.root), cls.worlds)
        cls.result = {
            "board": list(cls.board), "runouts": list(cls.selected),
            "runout_mode": "full-deck",
            "reachable_runouts": sorted({world["river"] for world in cls.worlds}),
            "strategy": deepcopy(cls.policy_rows), "info_sets": len(cls.policy_rows),
            "compatible_world_count": len(cls.worlds), "compatible_pairs": 4,
            "config": cls.config.to_dict(), "river_config": cls.config.to_dict(),
        }
        cls.result.update(audit.rules.replay_policy(
            cls.result, cls.fixture["oop"], cls.fixture["ip"],
            board=cls.fixture["board"], config=cls.fixture["config"]))
        cls.model = (cls.fixture, cls.board, cls.config, cls.worlds, cls.selected, cls.root, [])

    def test_check_call_policy_matches_independent_exact_anchors(self):
        result = audit.audit_policy(self.result, model=self.model)
        metrics = result["certificate"]["metrics"]
        anchors = {
            "value_oop": F(-2500, 231),
            "value_ip": F(2500, 231),
            "oop_best_response_value": F(2350, 231),
            "ip_best_response_value": F(14975, 231),
            "oop_best_response_gain": F(4850, 231),
            "ip_best_response_gain": F(12475, 231),
            "nash_conv": F(75),
            "exploitability": F(75, 2),
        }
        for name, expected in anchors.items():
            self.assertEqual(metrics[name], expected)
        self.assertEqual(result["physical_worlds"], 176)
        self.assertEqual(result["physical_rows"], 2404)
        self.assertEqual(result["quotient_worlds"], 12)
        self.assertEqual(result["quotient_rows"], 220)

    def test_actual_saved_policy_is_audited_without_training(self):
        report = json.loads(audit.bounded(audit.BASELINE, 1_000_000))
        row = report["results"][0]
        path = audit.POLICIES / row["policy_file"]
        saved = json.loads(audit.bounded(path, audit.MAX_POLICY_BYTES))
        with patch("pokerlab.postflop_solver.solve_postflop", side_effect=AssertionError("training/solver called")), \
             patch("pokerlab.matrix_free_turn.solve_matrix_free_turn", side_effect=AssertionError("training/solver called")):
            result = audit.audit_policy(saved)
        self.assertAlmostEqual(float(result["certificate"]["metrics"]["nash_conv"]),
                               row["metrics"]["nash_conv"], delta=1e-9)
        self.assertEqual(result["physical_worlds"], 176)

    def test_within_class_policy_difference_is_rejected_exactly(self):
        changed = deepcopy(self.result)
        row = next(row for row in changed["strategy"]
                   if row["street"] == "river" and row["board"][-1] != "3c"
                   and len(row["actions"]) > 1)
        row["actions"][0]["probability"] = 0.5
        row["actions"][1]["probability"] = 0.5
        changed.update(audit.rules.replay_policy(
            changed, self.fixture["oop"], self.fixture["ip"],
            board=self.fixture["board"], config=self.fixture["config"]))
        with self.assertRaisesRegex(ValueError, "exactly class-constant"):
            audit.audit_policy(changed, model=self.model)

    def test_physical_mass_sign_and_support_mutations_are_rejected(self):
        for field, replacement, message in (
            ("weight", F(1, 44), "physical law or card support"),
            ("sign", -1 if next(w["sign"] for w in self.worlds if w["sign"] != 0) == 1 else 1,
             "showdown sign"),
            ("river", "3c", "physical law or card support"),
        ):
            with self.subTest(field=field):
                worlds = deepcopy(self.worlds)
                worlds[0][field] = replacement
                model = (*self.model[:3], worlds, *self.model[4:])
                with self.assertRaisesRegex(ValueError, message):
                    audit.quotient_model(model)

    def test_equal_class_support_counts_do_not_hide_different_card_sets(self):
        # Move one legal neutral river within a private pair to another legal
        # neutral card. The count remains 40, but the exact physical card set
        # must still match the independent full-deck law.
        worlds = deepcopy(self.worlds)
        pair = worlds[0]["hands"]
        pair_worlds = [w for w in worlds if w["hands"] == pair]
        original = next(w["river"] for w in pair_worlds if audit.representative(w["river"]) == "3c")
        replacement = next(w["river"] for w in pair_worlds
                           if audit.representative(w["river"]) == "3c" and w["river"] != original)
        target = next(w for w in pair_worlds if w["river"] == original)
        target["river"] = replacement
        target["board"] = tuple(self.board) + (replacement,)
        model = (*self.model[:3], worlds, *self.model[4:])
        with self.assertRaisesRegex(ValueError, "Duplicate original physical world|physical law or card support"):
            audit.quotient_model(model)

    def test_full_tree_action_and_terminal_projection_are_checked(self):
        def mutate(node, mutation):
            if isinstance(node, audit.rules._Terminal):
                if mutation == "terminal":
                    return replace(node, contributions=(node.contributions[0] + 1, node.contributions[1])), True
                return node, False
            if isinstance(node, audit.rules._Chance):
                branches = dict(node.branches)
                for card, child in branches.items():
                    branches[card], changed = mutate(child, mutation)
                    if changed:
                        return replace(node, branches=branches), True
                return node, False
            if isinstance(node, audit.rules._Decision):
                if mutation == "action":
                    actions = list(node.actions)
                    actions[0] = replace(actions[0], name=actions[0].name + "-changed")
                    return replace(node, actions=tuple(actions)), True
                if mutation == "extra-child":
                    return replace(node, children=tuple(node.children) + (node.children[0],)), True
                children = list(node.children)
                for index, child in enumerate(children):
                    children[index], changed = mutate(child, mutation)
                    if changed:
                        return replace(node, children=tuple(children)), True
                return node, False
            return node, False
        for mutation in ("terminal", "action", "extra-child"):
            with self.subTest(mutation=mutation):
                root, changed = mutate(self.root, mutation)
                self.assertTrue(changed)
                model = (*self.model[:5], root, self.model[6])
                with self.assertRaisesRegex(ValueError, "class-isomorphic|public action/terminal structure|action/child coverage"):
                    audit.quotient_model(model)

    def test_malformed_full_row_metadata_is_rejected(self):
        changed = deepcopy(self.result)
        changed["strategy"][0]["actions"][0]["history_key"] = "wrong-token"
        with self.assertRaises(ValueError):
            audit.audit_policy(changed, model=self.model)

    def test_exact_work_below_requirement_and_cap_increases_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "work limit"):
            audit.audit_policy(self.result, model=self.model, max_work=1)
        with self.assertRaisesRegex(ValueError, "max_work"):
            audit.audit_policy(self.result, model=self.model,
                               max_work=audit.exact.MAX_EXACT_WORK + 1)
        with self.assertRaisesRegex(ValueError, "max_work"):
            audit.audit_policy(self.result, model=self.model, max_work=True)

    def test_byte_cap_is_checked_before_read(self):
        directory = ROOT_TMP
        directory.mkdir(exist_ok=True)
        path = directory / f"oversized-{uuid4().hex}.json"
        try:
            path.write_bytes(b"0123456789")
            with patch.object(Path, "read_bytes", side_effect=AssertionError("read before cap")):
                with self.assertRaisesRegex(ValueError, "pre-read byte cap"):
                    audit.bounded(path, 9)
        finally:
            path.unlink(missing_ok=True)

    def test_source_head_policy_and_report_drift_guards(self):
        source_map = {"source": "pinned"}
        with patch.object(audit, "fingerprints", return_value=source_map), \
             patch.object(reference, "head", return_value="head-a"):
            audit.guard(source_map, "head-a")
        with patch.object(audit, "fingerprints", return_value={"source": "changed"}), \
             patch.object(reference, "head", return_value="head-a"):
            with self.assertRaisesRegex(ValueError, "source or HEAD changed"):
                audit.guard(source_map, "head-a")
        with patch.object(audit, "fingerprints", return_value=source_map), \
             patch.object(reference, "head", return_value="head-b"):
            with self.assertRaisesRegex(ValueError, "source or HEAD changed"):
                audit.guard(source_map, "head-a")

        head_calls = 0
        def late_head_drift():
            nonlocal head_calls
            head_calls += 1
            return "a" * 40 if head_calls <= 2 else "b" * 40
        with patch.object(audit, "fingerprints", return_value=source_map), \
             patch.object(reference, "head", side_effect=late_head_drift), \
             patch.object(reference, "verify_saved_artifact", return_value={"verified": True}), \
             patch.object(reference, "model", return_value=self.model), \
             patch.object(audit, "audit_policy", return_value={
                 "certificate": {"metrics": {"nash_conv": F(1)}}}) as audited:
            # The real immutable baseline bytes are used; only HEAD changes after
            # the first policy has completed its mocked audit.
            with self.assertRaisesRegex(ValueError, "source or HEAD changed"):
                audit.reconstruct()
            self.assertEqual(audited.call_count, 1)

        directory = ROOT_TMP
        directory.mkdir(exist_ok=True)
        accepted = directory / f"report-{uuid4().hex}.json"
        try:
            expected = {"results": [{"profile": i, "certificate": {"fraction": "1/2"},
                                      "full_numeric_metrics": {}, "exact_minus_numeric": {}}
                                     for i in range(6)]}
            saved = deepcopy(expected)
            saved["results"][0]["certificate"]["fraction"] = "2/3"
            raw = audit.canonical({"schema_version": 1, "generation_git_commit": "a" * 40,
                                   "source_sha256": source_map,
                                   "audit": saved})
            accepted.write_bytes(raw)
            with patch.object(audit, "fingerprints", return_value=source_map), \
                 patch.object(reference, "head", return_value="a" * 40), \
                 patch.object(audit, "bounded", return_value=raw), \
                 patch.object(audit, "reconstruct", return_value=expected):
                with self.assertRaisesRegex(ValueError, "Saved exact audit differs"):
                    audit.verify_saved_artifact(accepted)
        finally:
            accepted.unlink(missing_ok=True)

    def test_saved_policy_and_immutable_report_byte_drift_are_rejected(self):
        baseline_bytes = audit.bounded(audit.BASELINE, 1_000_000)
        source_map = {"test-source": "stable"}
        original_bounded = audit.bounded

        reads = {}
        first_policy = audit.POLICIES / json.loads(baseline_bytes)["results"][0]["policy_file"]
        def drifted_policy(path, cap):
            path = Path(path)
            if path == audit.BASELINE:
                return baseline_bytes
            if path == reference.REPORT:
                return original_bounded(path, cap)
            reads[path] = reads.get(path, 0) + 1
            if path == first_policy and reads[path] > 1:
                return b"changed-on-late-read"
            return original_bounded(path, cap)

        with patch.object(audit, "fingerprints", return_value=source_map), \
             patch.object(reference, "head", return_value="a" * 40), \
             patch.object(audit, "bounded", side_effect=drifted_policy), \
             patch.object(reference, "verify_saved_artifact", return_value={"verified": True}), \
             patch.object(reference, "model", return_value=self.model), \
             patch.object(audit, "audit_policy", return_value={
                 "certificate": {"metrics": {"nash_conv": F(1)}}}) as audited:
            with self.assertRaisesRegex(ValueError, "policy/report changed during exact audit"):
                audit.reconstruct()
            self.assertEqual(audited.call_count, 6)

        raw_reference = original_bounded(reference.REPORT, reference.MAX_REPORT_BYTES)
        reference_reads = 0
        def drifted_reference(path, cap):
            nonlocal reference_reads
            if Path(path) == reference.REPORT:
                reference_reads += 1
                return raw_reference if reference_reads == 1 else raw_reference + b"drift"
            return original_bounded(path, cap)
        with patch.object(audit, "fingerprints", return_value=source_map), \
             patch.object(reference, "head", return_value="a" * 40), \
             patch.object(audit, "bounded", side_effect=drifted_reference), \
             patch.object(reference, "verify_saved_artifact", return_value={"verified": True}), \
             patch.object(reference, "model", return_value=self.model), \
             patch.object(audit, "audit_policy", return_value={
                 "certificate": {"metrics": {"nash_conv": F(1)}}}) as audited:
            with self.assertRaisesRegex(ValueError, "policy/report changed during exact audit"):
                audit.reconstruct()
            self.assertEqual(audited.call_count, 6)

        expected = {"results": [{"profile": i, "certificate": {"fraction": "1/2"},
                                  "full_numeric_metrics": {}, "exact_minus_numeric": {}}
                                 for i in range(6)]}
        report = {"schema_version": 1, "generation_git_commit": "a" * 40,
                  "source_sha256": source_map, "audit": expected}
        raw = audit.canonical(report)
        directory = ROOT_TMP
        directory.mkdir(exist_ok=True)
        path = directory / f"drifted-report-{uuid4().hex}.json"
        try:
            path.write_bytes(raw)
            def mutate_after_load():
                with path.open("ab") as stream:
                    stream.write(b" ")
                return expected
            with patch.object(audit, "fingerprints", return_value=source_map), \
                 patch.object(reference, "head", return_value="a" * 40), \
                 patch.object(audit, "reconstruct", side_effect=mutate_after_load):
                with self.assertRaisesRegex(ValueError, "report changed during verification"):
                    audit.verify_saved_artifact(path)
        finally:
            path.unlink(missing_ok=True)

    def test_staged_and_published_failures_roll_back_only_their_new_report(self):
        directory = ROOT_TMP
        directory.mkdir(exist_ok=True)
        nonce = uuid4().hex
        owned_files = [directory / f"new-report-staged-{nonce}.json",
                       directory / f"new-report-published-{nonce}.json",
                       directory / f"unrelated-{nonce}.txt"]
        try:
            sibling = owned_files[2]
            sibling.write_text("keep", encoding="utf-8")
            for failure_stage in ("staged", "published"):
                with self.subTest(failure_stage=failure_stage):
                    report = directory / f"new-report-{failure_stage}-{nonce}.json"
                    payload = {"test": "candidate"}
                    envelope = {"schema_version": 1, "generation_git_commit": "a" * 40,
                                "source_sha256": {"test": "source"}, "audit": payload}
                    calls = []

                    def verify(path=None):
                        path = report if path is None else path
                        calls.append(Path(path))
                        if failure_stage == "published" and len(calls) == 1:
                            self.assertEqual(json.loads(Path(path).read_bytes()), envelope)
                            return {"status": "staged"}
                        raise ValueError(f"{failure_stage} verification failure")

                    with patch.object(audit, "REPORT", report), \
                         patch.object(audit, "fingerprints", return_value={"test": "source"}), \
                         patch.object(reference, "head", return_value="a" * 40), \
                         patch.object(audit, "reconstruct", return_value=payload), \
                         patch.object(audit, "verify_saved_artifact", side_effect=verify):
                        with self.assertRaisesRegex(ValueError, f"{failure_stage} verification failure"):
                            audit.generate()
                    self.assertFalse(report.exists())
            self.assertEqual(sibling.read_text(encoding="utf-8"), "keep")
            self.assertTrue(all(not path.exists() for path in owned_files[:2]))
        finally:
            for path in owned_files:
                path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
