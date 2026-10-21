"""Tests for immutable alternating-flop publication authentication."""
from contextlib import ExitStack
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from scripts import benchmark_flop_alternating as study
from scripts import verify_flop_alternating_publication as publication
from tests.test_weighted_flop_publication import local_temp


class FlopAlternatingPublicationTests(unittest.TestCase):
    def test_full_candidate_corpus_and_historical_baselines_replay_without_authority(self):
        alternating, postflop, _, _, _ = study._source_modules()
        from pokerlab import preflop_delayed_cfrplus, public_cfr
        with ExitStack() as stack:
            for name in (
                "solve_postflop", "rank_hand", "_enumerate_worlds", "train", "train_plus",
                "train_planned", "train_public_batched", "evaluate", "best_response",
                "evaluate_profile",
            ):
                if hasattr(postflop, name):
                    stack.enter_context(patch.object(
                        postflop, name,
                        side_effect=AssertionError("Production authority called: " + name)))
            for name in ("train_public_lcfr", "train_public_alternating_dcfr",
                         "_cfrplus_target_deltas", "_aggregate_prefixes"):
                stack.enter_context(patch.object(
                    alternating, name,
                    side_effect=AssertionError("Alternating trainer helper called: " + name)))
            stack.enter_context(patch.object(
                preflop_delayed_cfrplus, "train_delayed_public_cfrplus",
                side_effect=AssertionError("Delayed trainer called")))
            for name in ("_cfrplus_target_deltas", "_aggregate_prefixes"):
                stack.enter_context(patch.object(
                    public_cfr, name,
                    side_effect=AssertionError("Public training helper called: " + name)))
            checked = publication.verify_saved()

        self.assertEqual(checked["timed_and_allocation_policies_replayed"], 12)
        self.assertEqual(checked["worlds_reenumerated"], 5940)
        self.assertEqual(checked["file_count"], 15)
        self.assertEqual(checked["source_revision"], publication.SOURCE_REVISION)
        self.assertEqual(checked["source_files"], publication.SOURCE_FILES)
        report = json.loads((publication.PUBLICATION / "index.json").read_bytes())
        self.assertEqual(len(report["samples"]), 9)
        self.assertEqual(len(report["separate_allocation_calls"]), 3)
        self.assertEqual(len(report["final_quality"]), 3)
        self.assertEqual(report["quality_gate_met"], all(row["met"] for row in report["final_quality"]))
        self.assertEqual({row["method"] for row in report["final_quality"]},
                         {"cfrplus-control", "lcfr", "alternating-dcfr-3/2-0-2"})
        self.assertEqual(checked["quality_gate_met"], report["quality_gate_met"])

        if report["quality_gate_met"] is not True:
            with self.assertRaisesRegex(ValueError, "quality gates remain unmet"):
                publication.verify_saved(require_quality=True)

    def test_git_lf_sidecar_and_source_snapshot_are_jointly_authenticated(self):
        report = json.loads((publication.PUBLICATION / "index.json").read_bytes())
        source = report["source_before"]
        sidecar_raw = publication.SOURCE_SIDECAR.read_bytes()
        sidecar = json.loads(sidecar_raw)
        raw_map, lf_map = publication._validate_source_record(
            source, report["source_after"], sidecar_raw, sidecar)
        self.assertEqual(raw_map, publication.SOURCE_HASHES_SHA256)
        self.assertEqual(lf_map, publication.SOURCE_GIT_LF_MANIFEST_SHA256)
        self.assertEqual(sidecar["matched_git_lf_files"], 626)

        bad_revision = deepcopy(sidecar)
        bad_revision["source_revision"] = "0" * 40
        with self.assertRaisesRegex(ValueError, "sidecar does not attest"):
            publication._validate_source_record(
                source, report["source_after"], json.dumps(bad_revision).encode(), bad_revision)

        bad_lf_map = deepcopy(sidecar)
        first_path = next(iter(bad_lf_map["git_lf_source_hashes"]))
        bad_lf_map["git_lf_source_hashes"][first_path] = "0" * 64
        with self.assertRaisesRegex(ValueError, "sidecar does not attest"):
            publication._validate_source_record(
                source, report["source_after"], json.dumps(bad_lf_map).encode(), bad_lf_map)

    def test_resigned_index_changes_still_fail_the_external_raw_pin(self):
        report = json.loads((publication.PUBLICATION / "index.json").read_bytes())
        report["quality_gate_met"] = not report["quality_gate_met"]
        with local_temp() as temp:
            directory = Path(temp)
            study._write_index(directory, report)
            with self.assertRaisesRegex(ValueError, "Immutable published alternating index"):
                publication.verify_saved(directory)

    def test_changed_git_lf_sidecar_fails_its_external_raw_pin(self):
        sidecar = json.loads(publication.SOURCE_SIDECAR.read_bytes())
        sidecar["method"] += "; altered"
        changed = json.dumps(sidecar, sort_keys=True).encode()
        with local_temp() as temp:
            source_sidecar = Path(temp) / "changed-git-source.json"
            source_sidecar.write_bytes(changed)
            with self.assertRaisesRegex(ValueError, "Immutable Git-LF source sidecar"):
                publication.verify_saved(source_sidecar=source_sidecar)

    def test_changed_scratch_incident_fails_its_external_raw_pin(self):
        incident = json.loads(publication.INCIDENT_SIDECAR.read_bytes())
        incident["timing_limit"] += " altered"
        changed = json.dumps(incident, sort_keys=True).encode()
        with local_temp() as temp:
            incident_sidecar = Path(temp) / "changed-scratch-incident.json"
            incident_sidecar.write_bytes(changed)
            with self.assertRaisesRegex(ValueError, "Immutable scratch-incident sidecar"):
                publication.verify_saved(incident_sidecar=incident_sidecar)


if __name__ == "__main__":
    unittest.main()
