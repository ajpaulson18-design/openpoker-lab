"""Regression tests for the saved full-physical audit wrapper."""
import json
from fractions import Fraction
from pathlib import Path
import unittest
from unittest import mock
from uuid import uuid4


REPO = Path(__file__).resolve().parents[1]
TEMP_ROOT = REPO / ".test_tmp" / "full-physical-wrapper-v2"

from scripts import audit_raised_turn_full_physical as audit


def canonical(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) +
            "\n").encode("utf-8")


class RaisedTurnFullPhysicalWrapperTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Cache one real exact reconstruction for fast tamper and publication
        # failure cases. Live HEAD, input bytes, and source fingerprints remain
        # guarded; only the commit-presence precondition is bypassed because
        # this test file may be staged before it is committed.
        cls.commit_precondition = mock.patch.object(
            audit, "_check_committed_sources", return_value=None)
        cls.commit_precondition.start()
        cls.addClassCleanup(cls.commit_precondition.stop)
        cls.template = audit._audit(REPO, require_committed=False)
        cls.template_raw = canonical(cls.template)

    def setUp(self):
        TEMP_ROOT.mkdir(parents=True, exist_ok=True)
        self.directory = TEMP_ROOT / ("owned-" + uuid4().hex)
        self.directory.mkdir()
        self.addCleanup(self._cleanup_owned_files)

    def _cleanup_owned_files(self):
        # Remove only names this test class creates; never recurse over a shared
        # temporary root or erase an unrelated sibling.
        for name in ("report.json", "report.json.staged",
                     "historical-report.json", "tampered-metric.json",
                     "tampered-counter.json", "new-report.json",
                     "new-report.json.staged", "replaced-report.json",
                     "replaced-report.json.staged", "keep.txt"):
            (self.directory / name).unlink(missing_ok=True)
        self.directory.rmdir()

    def test_real_generation_saved_verification_and_historical_replay(self):
        output = self.directory / "report.json"
        report = audit.generate(root=REPO, output_path=output)

        # generate() stages, fully verifies, publishes, then fully verifies the
        # immutable output. These assertions also pin the actual six-profile
        # report to its handwritten exact anchors and saved-policy outcomes.
        self.assertEqual(len(report["profiles"]), 6)
        self.assertEqual(report["profiles"][0]["metrics_fraction"]["value_oop"],
                         "-2500/231")
        self.assertEqual(report["profiles"][1]["metrics_fraction"]["value_oop"],
                         "-4925/462")
        self.assertEqual(report["controls"][
            "illegal_future_aware_check_call_control"]["oop_br_fraction"],
            "2825/231")
        self.assertEqual(report["controls"][
            "illegal_future_aware_check_call_control"]["ip_br_fraction"],
            "15325/231")
        tails = [case for case in report["profiles"]
                 if case["case"] == "original-saved-numeric-tail"]
        self.assertEqual(len(tails), 2)
        self.assertTrue(all(Fraction(case["metrics_fraction"]["nash_conv"]) > 0
                            for case in tails))
        witnesses = [case for case in report["profiles"]
                     if case["case"] == "saved-clean-witness"]
        self.assertEqual(len(witnesses), 2)
        for case in witnesses:
            self.assertEqual(case["metrics_fraction"]["value_oop"], "-400/21")
            self.assertEqual(case["metrics_fraction"]["nash_conv"], "0")
        self.assertEqual(audit.verify_report(output, root=REPO), report)

        # Reconstruct a report carrying an accepted historical input commit;
        # the live source/input/HEAD guards still run at the current checkout.
        historical_head = report["input_historical_generation_commits"][
            "numeric_report"]
        self.assertRegex(historical_head, r"^[0-9a-f]{40}$")
        old_report = dict(report)
        old_report["audit_head"] = historical_head
        historical = self.directory / "historical-report.json"
        historical.write_bytes(canonical(old_report))
        self.assertEqual(audit.verify_report(historical, root=REPO), old_report)

    def test_exact_metric_and_counter_tampering_rejected_without_replay(self):
        # Both malformed reports fail preflight against the pinned exact report
        # or fixed traversal bounds, before an expensive oracle audit begins.
        for field, value, filename in (
                ("nash_conv", "0", "tampered-metric.json"),
                ("structural_node_visits", 0, "tampered-counter.json")):
            with self.subTest(field=field):
                tampered = json.loads(self.template_raw)
                if field == "nash_conv":
                    tampered["profiles"][0]["metrics_fraction"][field] = value
                    expected = "Saved exact metric differs"
                else:
                    tampered["profiles"][0]["counters"][field] = value
                    expected = "Physical oracle counters violate"
                path = self.directory / filename
                path.write_bytes(canonical(tampered))
                with mock.patch.object(audit, "_audit",
                                       side_effect=AssertionError("replay started")):
                    with self.assertRaisesRegex(ValueError, expected):
                        audit.verify_report(path, root=REPO)

    def test_late_accepted_input_drift_stops_before_next_policy_audit(self):
        for target_kind in ("policy", "report"):
            with self.subTest(target=target_kind):
                loaded = audit._load_inputs(REPO)
                target = next(relpath for relpath in loaded["accepted"]
                              if ("-policies-v1/" in relpath) ==
                              (target_kind == "policy"))
                target_path = (REPO / target).resolve()
                original_reader = audit._read_capped
                reads = 0

                def changed_read(path, cap, label):
                    nonlocal reads
                    raw = original_reader(path, cap, label)
                    if Path(path).resolve() == target_path:
                        reads += 1
                        # Snapshot, initial guard, model guard, anchor-policy
                        # guard, then the post-anchor guard. Change returned
                        # bytes only; never write to an accepted input.
                        if reads == 5:
                            return raw + b" "
                    return raw

                with mock.patch.object(audit, "_read_capped",
                                      side_effect=changed_read), \
                        mock.patch.object(audit.oracle, "audit_policy",
                                          wraps=audit.oracle.audit_policy) as call:
                    with self.assertRaisesRegex(ValueError, "input changed"):
                        audit._audit(REPO, require_committed=False)
                self.assertEqual(call.call_count, 1)

    def test_rollback_removes_only_owned_stage_and_publication(self):
        output = self.directory / "new-report.json"
        staged = self.directory / "new-report.json.staged"
        sibling = self.directory / "keep.txt"
        sibling.write_text("unrelated", encoding="utf-8")
        payload = self.template
        raw = self.template_raw

        def reject_published(path, root=REPO):
            if Path(path).resolve() == output.resolve():
                raise ValueError("injected linked-report rejection")
            return payload

        with mock.patch.object(audit, "verify_report", side_effect=reject_published):
            with self.assertRaisesRegex(ValueError, "linked-report rejection"):
                audit._publish(REPO, output, raw, payload, lambda: None)
        self.assertFalse(output.exists())
        self.assertFalse(staged.exists())
        self.assertEqual(sibling.read_text(encoding="utf-8"), "unrelated")

    def test_replaced_foreign_publication_survives_owned_rollback(self):
        """A path replacement after link must not be mistaken for our inode."""
        output = self.directory / "replaced-report.json"
        staged = self.directory / "replaced-report.json.staged"
        raw = canonical({"draft": "minimal"})
        payload = {"draft": "minimal"}
        real_link = audit.os.link

        def link_then_replace(source, destination):
            real_link(source, destination)
            # Simulate another writer replacing the just-published directory
            # entry. The staged hard link remains owned by this invocation.
            Path(destination).unlink()
            Path(destination).write_bytes(b"foreign replacement")

        with mock.patch.object(audit, "verify_report", return_value=payload), \
                mock.patch.object(audit.os, "link", side_effect=link_then_replace):
            with self.assertRaisesRegex(ValueError, "not the staged file"):
                audit._publish(REPO, output, raw, payload, lambda: None)

        self.assertTrue(output.exists(), "rollback deleted a foreign replacement")
        self.assertEqual(output.read_bytes(), b"foreign replacement")
        self.assertFalse(staged.exists(), "owned staging link was not removed")


if __name__ == "__main__":
    unittest.main()
