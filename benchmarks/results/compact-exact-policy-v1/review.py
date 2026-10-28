"""Read-only compact-policy study authentication and independent saved replay."""
import argparse
from contextlib import ExitStack
import hashlib
import importlib.util
import itertools
import json
import math
from pathlib import Path
import statistics
import sys
from unittest.mock import patch

AUTH_SHA = "8171ead3ba108f8200f15e85696f40d109ed894209fa7d77598780b83c1401c5"
MODES = ("expanded", "compact")
FORMATS = {"expanded": "expanded-private-pairs-v1", "compact": "compact-exact-product-inputs-v1"}
METRICS = ("value_sb", "value_bb", "sb_best_response_value", "bb_best_response_value",
           "sb_gain", "bb_gain", "nash_conv", "exploitability")
SCHEDULE = (("original", "expanded", 0, False), ("original", "compact", 0, False),
    ("original", "compact", 1, False), ("original", "expanded", 1, False),
    ("original", "expanded", 2, False), ("original", "compact", 2, False),
    ("original", "expanded", "traced", True), ("original", "compact", "traced", True),
    ("full-range-blind-all-in", "expanded", 0, False),
    ("full-range-blind-all-in", "compact", 0, False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("repo", "study", "receipt", "archive"):
        parser.add_argument("--" + key, type=Path, required=True)
    for key in ("source-commit", "manifest-sha256", "archive-sha256", "confirmed-terminal-handle"):
        parser.add_argument("--" + key, required=True)
    parser.add_argument("--terminal-exit-code", type=int, required=True)
    args = parser.parse_args()
    auth_path = Path(__file__).with_name("exact-selected-independent-review.py")
    if hashlib.sha256(auth_path.read_bytes()).hexdigest() != AUTH_SHA:
        raise ValueError("External source-authentication helper changed")
    spec = importlib.util.spec_from_file_location("saved_source_auth", auth_path)
    auth = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(auth)
    auth.FROZEN = args.source_commit
    need, sha, parse = auth.need, auth.sha, auth.parse
    repo, study, receipt = args.repo.resolve(), args.study.resolve(), args.receipt.resolve()
    need(args.terminal_exit_code == 0 and args.confirmed_terminal_handle,
         "Lead-confirmed successful producer terminal required")
    need(not receipt.exists() and repo not in receipt.parents and study not in receipt.parents,
         "Use a new external receipt")
    saved = {p.relative_to(study).as_posix(): p.read_bytes() for p in study.rglob("*") if p.is_file()}
    need(sha(saved["manifest.json"]) == args.manifest_sha256, "External manifest pin mismatch")
    manifest = parse(saved["manifest.json"])
    need(manifest["source_commit"] == args.source_commit, "Manifest source mismatch")
    need(set(saved) == set(manifest["sha256"]) | {"manifest.json"}, "Incomplete manifest inventory")
    for name, digest in manifest["sha256"].items():
        need(Path(name).name == name and sha(saved[name]) == digest, "Artifact drift: " + name)
    source = parse(saved["source-before.json"])
    authenticated = auth.source_identity(repo, source)  # Before repository mathematics imports.
    need(parse(saved["source-after.json"]) == source, "Source snapshots differ")
    archive = auth.archive_check(args.archive, args.archive_sha256, saved)
    protocol, report = parse(saved["protocol.json"]), parse(saved["report.json"])
    need(report["outcome"] == "complete" and report["failure"] is None, "Producer failed")
    need(protocol == report["protocol"] and protocol["source_commit"] == report["source_commit"] == args.source_commit,
         "Protocol/report source mismatch")
    need(protocol["version"] == "compact-exact-policy-complete-call-v1" and protocol["iterations"] == 10 and
         protocol["rank_cache_boards"] == 64, "Wrong fixed study")
    need(protocol["output_formats"] == FORMATS and protocol["chance_contract"] == "exact-product-selected-v1" and
         protocol["conversion_contract"] == "exact-product-vectors-binary64-v1", "Study format/arithmetic contracts changed")
    need(protocol["source_sha256"] == source["sha256"] and
         protocol["runner_sha256"] == source["sha256"]["scripts/benchmark_compact_exact_policy.py"],
         "Runner/source pin mismatch")
    need(protocol["schedule"] == [dict(case=c, mode=m, sample=s, traced=t) for c, m, s, t in SCHEDULE],
         "Fixed schedule changed")
    need(len(report["samples"]) == report["complete_child_calls"] == 10, "Incomplete fixed schedule")
    payloads, records = {}, []
    for row, (case, mode, sample, traced) in zip(report["samples"], SCHEDULE):
        label = f"{case}-{mode}-{sample}"
        name = label + ".json"
        raw = parse(saved[name])
        need(row["artifact"] == name and row["raw_sha256"] == sha(saved[name]) and row["sample"] == sample,
             "Raw sample/report binding mismatch")
        need({k: v for k, v in row.items() if k not in ("artifact", "raw_sha256", "sample")} ==
             {k: v for k, v in raw.items() if k != "payload"}, "Report differs from raw sample")
        for key, expected in (("case", case), ("mode", mode), ("output_format", FORMATS[mode]), ("iterations", 10),
                              ("rank_cache_boards", 64), ("traced", traced)):
            need(type(raw[key]) is type(expected) and raw[key] == expected, "Wrong child request metadata")
        need(type(raw["seconds"]) in (int, float) and math.isfinite(raw["seconds"]) and raw["seconds"] > 0,
             "Invalid elapsed time")
        need(type(raw["python_process_peak_bytes"]) is int and raw["python_process_peak_bytes"] > 0,
             "Invalid process peak")
        allocation = raw["python_allocation_peak_bytes"]
        need((type(allocation) is int and allocation > 0) if traced else allocation is None,
             "Trace scope mismatch")
        for key in ("training_calls", "pair_query_calls", "rank_calls", "native_calls"):
            need(type(raw[key]) is int and raw[key] >= 0, "Invalid actual call counter")
        need(raw["native_calls"] == 0, "Unexpected native call")
        if case != "original" and mode == "expanded":
            need(raw["status"] == "pretraining-rejected" and raw["payload"] is None and
                 all(raw[k] == 0 for k in ("training_calls", "pair_query_calls", "rank_calls")),
                 "Expanded full-range rejection entered computation")
            need(raw["error"]["type"] == "ValueError" and
                 "output entry limit" in raw["error"]["message"].lower(), "Wrong expanded rejection")
            records.append(row)
            continue
        need(raw["status"] == "complete" and raw["error"] is None, "Expected complete solver call")
        payload = raw["payload"]
        need(payload["chance_contract"] == "exact-product-selected-v1" and
             payload["conversion_contract"] == "exact-product-vectors-binary64-v1" and
             payload["execution_backend"] == "exact-product-selected-direct-packed-python", "Arithmetic/backend drift")
        need(len(payload["strategy"]) == payload["info_sets"], "Incomplete strategy")
        need(all(type(payload[k]) in (int, float) and math.isfinite(payload[k]) for k in METRICS),
             "Invalid floating diagnostic")
        census = payload["operator_census"]
        admitted = census["whole_request_admission"]
        need(census["stored_complete_worlds"] == census["stored_prefix_pair_edges"] == 0,
             "Materialized hidden worlds")
        need(census["training"]["calls"] == raw["training_calls"] and
             census["kernel"]["rank_calls"] == raw["rank_calls"], "Actual counters/census mismatch")
        need(census["kernel"]["work_units_cumulative"] <= admitted["kernel"]["whole_request_upper_work"] <=
             admitted["kernel"]["configured_limit"], "Kernel work admission exceeded")
        need(census["float_adapter"]["modeled_work_entries"] <= admitted["adapter"]["whole_request_work_upper"] <=
             admitted["adapter"]["configured_work_limit"], "Adapter work admission exceeded")
        need(admitted["combined_modeled_work_upper"] <= admitted["whole_request_limit"] and
             admitted["retained_storage"]["whole_request_peak_upper"] <= admitted["retained_storage"]["entry_limit"],
             "Whole request admission exceeded")
        pairs = census["exact_pair_output"]
        if mode == "compact":
            need(payload["pair_diagnostics"] == "compact-exact-product-inputs-v1" and
                 "private_pair_probabilities" not in payload and "compatible_private_pairs" not in payload,
                 "Compact output contains pair table")
            need(raw["pair_query_calls"] == payload["pair_runout_preflight_checks"] ==
                 pairs["candidate_pairs_scanned"] == pairs["board_scan_work_upper"] == pairs["output_entry_upper"] == 0 and
                 pairs["quadratic_diagnostic_stage"] is False, "Compact pair work not zero")
        else:
            need("pair_diagnostics" not in payload and "chance_input_snapshot" not in payload and
                 raw["pair_query_calls"] == payload["candidate_private_pairs"] == pairs["candidate_pairs_scanned"] == 4 and
                 payload["compatible_private_pairs"] == len(payload["private_pair_probabilities"]),
                 "Expanded pair diagnostics changed")
        if case == "original":
            need(raw["training_calls"] == 1 and raw["rank_calls"] > 0 and
                 payload["worlds"] == 22 and payload["info_sets"] == 1200, "Wrong choice-bearing game")
        else:
            need(raw["training_calls"] == 0 and raw["rank_calls"] == 2162 and payload["strategy"] == [] and
                 payload["worlds"] == math.comb(47, 2) * math.comb(45, 2) == 1070190,
                 "Wrong forced full-range game")
            need(all(abs(payload[k]) <= 1e-12 for k in METRICS), "Forced identical-prior symmetry failed")
            deck = [r+s for r in "23456789TJQKA" for s in "cdhs"]
            expected = {"".join(sorted(hand)): "0x1.0000000000000p+0" for hand in itertools.combinations(deck, 2)}
            snapshot = payload["chance_input_snapshot"]
            need(type(snapshot) is dict and set(snapshot) == {"contract", "ranges"} and
                 snapshot["contract"] == "exact-product-selected-v1" and type(snapshot["ranges"]) is list and
                 len(snapshot["ranges"]) == 2, "Malformed full-range compact snapshot")
            for side in snapshot["ranges"]:
                need(type(side) is list and all(type(r) is dict and set(r) == {"hand", "weight_hex"}
                     and type(r["hand"]) is str and type(r["weight_hex"]) is str for r in side),
                     "Malformed full-range compact input row")
                need(len(side) == 1326 and {r["hand"]: r["weight_hex"] for r in side} == expected,
                     "Full-range compact snapshot differs from all equally weighted holdings")
        payloads[label] = payload
        records.append(row)
    need(report["training_calls"] == sum(r["training_calls"] for r in records) == 8 and
         report["pair_query_calls"] == sum(r["pair_query_calls"] for r in records) == 16 and
         report["native_calls"] == 0, "Aggregate actual counters mismatch")
    reference = payloads["original-expanded-0"]
    compact_snapshot = payloads["original-compact-0"]["chance_input_snapshot"]
    for label, payload in payloads.items():
        if label.startswith("original-"):
            need(payload["strategy"] == reference["strategy"] and all(payload[k] == reference[k] for k in METRICS),
                 "Complete paired strategy or diagnostic differs")
            if "-compact-" in label:
                need(payload["chance_input_snapshot"] == compact_snapshot, "Repeated compact input witness differs")
    for mode in MODES:
        times = [r["seconds"] for r in records if r["case"] == "original" and r["mode"] == mode and not r["traced"]]
        need(len(times) == 3 and report["medians_seconds"][mode] == statistics.median(times), "Median mismatch")
    comparisons = []
    for sample, traced in ((0, False), (1, False), (2, False), ("traced", True)):
        left, right = (payloads[f"original-{mode}-{sample}"] for mode in MODES)
        comparisons.append({"sample": sample, "traced": traced,
            "complete_strategy_identical": left["strategy"] == right["strategy"],
            "all_eight_metrics_identical": all(left[k] == right[k] for k in METRICS),
            "same_game_counts": all(left[k] == right[k] for k in ("worlds", "public_states", "decisions", "info_sets"))})
    need(report["paired_comparisons"] == comparisons, "Reported paired comparisons differ from raw policies")
    expected_checks = {key: True for key in ("all_paired_complete_strategies_identical",
        "all_paired_eight_metrics_identical", "all_paired_game_counts_identical",
        "all_normal_samples_match_sample_zero", "sample_zero_exact_metrics_identical",
        "sample_zero_normalized_policy_hash_identical", "sample_zero_exact_threshold_and_flag_identical",
        "full_range_compact_certificate_rejected_before_physical_model")}
    need(report["checks"] == expected_checks and all(type(v) is bool for v in report["checks"].values()),
         "Reported acceptance checks missing or false")
    for mode, label in (("expanded", "original-expanded-0"), ("compact", "original-compact-0"),
                        ("full_range_compact", "full-range-blind-all-in-compact-0")):
        census = payloads[label]["operator_census"]
        admission = census["whole_request_admission"]
        expected_structure = {"pair_output": census["exact_pair_output"],
            "kernel_actual_work": census["kernel"]["work_units_cumulative"],
            "kernel_requested_work_upper": admission["kernel"]["whole_request_upper_work"],
            "combined_requested_work_upper": admission["combined_modeled_work_upper"],
            "compact_input_snapshot_work_upper": admission["compact_input_snapshot_work_upper"],
            "modeled_retained_peak_entries": admission["retained_storage"]["whole_request_peak_upper"],
            "compact_prior_snapshot_entries_upper": admission["retained_storage"]["compact_prior_snapshot_entries_upper"]}
        need({k: v for k, v in report["structural_comparison"][mode].items() if k != "scope"} == expected_structure,
             "Reported structural census differs from raw sample")
    rejection = parse(saved["full-range-compact-certificate-rejection.json"])
    need(report["full_range_certificate_rejection"] == rejection and rejection["status"] == "rejected" and
         rejection["error_type"] == "ValueError" and rejection["error"] == "each range must contain at most 4 hands" and
         rejection["physical_model_builds"] == rejection["training_calls"] == rejection["native_calls"] == 0,
         "Reported full-range verifier rejection differs from saved record")
    # Every current source and saved artifact byte has authenticated above.
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(repo))
    from fractions import Fraction
    from scripts import four_street_validation as physical
    from scripts.preflop_validation import compare_result
    from scripts.four_street_certificate_v3 import evaluate_exact as expanded_exact
    from scripts.exact_selected_compact_certificate import evaluate_exact as compact_exact
    base = parse((repo/"benchmarks/four-street-integration-v1.json").read_bytes())["case"]
    forbidden = ("pokerlab.exact_selected_solver.solve_four_street_exact_selected",
        "pokerlab.exact_selected_solver.train_packed", "pokerlab.packed_operator_cfr.train_packed",
        "pokerlab.exact_selected_kernel.ExactSelectedRunoutKernel.terminal_values_exact",
        "pokerlab.exact_selected_kernel.ExactSelectedRunoutKernel.joint_marginals_exact",
        "pokerlab.exact_selected_kernel.ExactSelectedRunoutKernel.pair_probability_exact",
        "pokerlab.selected_operator_solver.solve_four_street_operator", "pokerlab.preflop_solver.solve_preflop",
        "pokerlab.native_selected_dag.train_native_selected_dag", "pokerlab.native_selected_operator.train_native_selected",
        "pokerlab.native_public_cfr.train_native_public", "pokerlab.public_cfr._train_prepared", "pokerlab.cfr.train", "subprocess.Popen")
    replayed, exacts = [], {}
    with ExitStack() as stack:
        for target in forbidden:
            stack.enter_context(patch(target, side_effect=AssertionError("Forbidden saved-review call: " + target)))
        model = physical.build_model(base)
        pair_rows = [{"sb_hand": r["sb_hand"], "bb_hand": r["bb_hand"], "probability": float(Fraction(r["fraction"]))}
                     for r in model.counts["pair_probabilities"]]
        def pair_map(rows):
            need(type(rows) is list and all(type(row) is dict and set(row) == {"sb_hand", "bb_hand", "probability"}
                 for row in rows), "Malformed pair table")
            result = {(row["sb_hand"], row["bb_hand"]): row["probability"] for row in rows}
            need(len(result) == len(rows), "Duplicate pair row")
            return result
        need(pair_map(pair_rows) == pair_map(reference["private_pair_probabilities"]),
             "Independent physical pair probabilities differ")
        for label, payload in payloads.items():
            if not label.startswith("original-"):
                continue
            expanded = (dict(payload, private_pair_probabilities=pair_rows,
                             compatible_private_pairs=model.counts["compatible_pairs"])
                        if "-compact-" in label else payload)
            replay = physical.replay_policy(expanded, base)
            gaps = compare_result(expanded, replay)
            auth.numeric_gaps(gaps)
            need(replay["checked_information_sets"] == payload["info_sets"] and replay["worlds"] == payload["worlds"],
                 "Independent numeric replay incomplete")
            replayed.append({"artifact": label + ".json", "numeric_gaps": gaps, "rows": payload["info_sets"]})
            if label.endswith("-0"):
                mode = "compact" if "-compact-" in label else "expanded"
                builds = []
                original_build = physical.build_model
                def counted_build(*a, **kw):
                    builds.append(1)
                    return original_build(*a, **kw)
                with patch.object(physical, "build_model", new=counted_build):
                    fresh = compact_exact(base, payload) if mode == "compact" else expanded_exact(base, payload)
                stored = parse(saved[label + "-certificate.json"])
                need(fresh == stored, "Fresh exact certificate differs from saved certificate")
                certificate = fresh["exact_certificate"] if mode == "compact" else fresh
                need(report["certificates"][mode] == {"artifact": label + "-certificate.json",
                     "metrics": certificate["metrics"], "threshold": certificate["threshold"],
                     "threshold_met": certificate["threshold_met"],
                     "normalized_policy_sha256": certificate["normalized_policy_sha256"]},
                     "Reported certificate differs from fresh saved replay")
                if mode == "compact":
                    need(len(builds) == fresh["physical_model_builds"] == 3 and
                         fresh["compact_input_canonical_sha256"] == auth.canonical(payload), "Compact receipt binding/count mismatch")
                else:
                    need(certificate["input_policy_canonical_sha256"] == auth.canonical(payload), "Expanded receipt binding mismatch")
                metrics = auth.metrics(certificate["metrics"])
                need(auth.bounded_fraction(certificate["threshold"]) == Fraction(1, 1000) and
                     certificate["threshold_met"] == (metrics["nash_conv"] <= Fraction(1, 1000)), "Exact threshold mismatch")
                need(certificate["fraction_bit_limit"] == 65536 and certificate["maximum_fraction_bits"] <= 65536,
                     "Exact arithmetic cap changed")
                exacts[mode] = {"metrics": certificate["metrics"], "threshold_met": certificate["threshold_met"],
                    "normalized_policy_sha256": certificate["normalized_policy_sha256"], "actual_model_builds": len(builds)}
        full = dict(base, id="compact-exact-full-range-forced-blind-all-in-v1", sb_range="random", bb_range="random",
                    runouts=["2c3d4h5s6c"], config=dict(base["config"], starting_stack=[.5, 1]))
        with patch.object(physical, "build_model", side_effect=AssertionError("Full-range verifier entered physical construction")):
            try:
                compact_exact(full, payloads["full-range-blind-all-in-compact-0"])
            except ValueError as exc:
                need(str(exc) == "each range must contain at most 4 hands", "Unexpected verifier rejection")
            else:
                raise ValueError("Full-range verification unexpectedly admitted")
    need(exacts["expanded"]["metrics"] == exacts["compact"]["metrics"] and
         exacts["expanded"]["normalized_policy_sha256"] == exacts["compact"]["normalized_policy_sha256"],
         "Paired exact mathematics differs")
    need(auth.source_identity(repo, source) == authenticated, "Source drift during independent replay")
    need({p.relative_to(study).as_posix(): p.read_bytes() for p in study.rglob("*") if p.is_file()} == saved,
         "Artifact drift during independent replay")
    result = {"outcome": "accepted", "reviewer": "lead Sol independent saved replay; Terra/Luna quota substitution disclosed",
        "source_commit": args.source_commit, "authenticated_source_files": authenticated["files"],
        "raw_committed_blob_files": authenticated["raw_committed_blob_files"],
        "normalized_committed_blob_files": authenticated["normalized_committed_blob_files"],
        "source_and_artifacts_unchanged_after_review": True, "source_raw_sha256": authenticated["raw_sha256"],
        "artifact_sha256": {name: sha(raw) for name, raw in saved.items()}, "manifest_sha256": args.manifest_sha256,
        "archive": archive, "confirmed_terminal_handle": args.confirmed_terminal_handle, "terminal_exit_code": 0,
        "producer_training_calls": 8, "producer_pair_query_calls": 16, "producer_native_calls": 0,
        "review_training_calls": 0, "review_native_calls": 0, "review_exact_kernel_callback_calls": 0,
        "forbidden_entry_points": forbidden, "fresh_numeric_replays": replayed, "fresh_exact": exacts,
        "full_range_certificate_rejected_before_model": True, "full_range_forced_game_training_calls": 0,
        "review_helper_sha256": sha(Path(__file__).read_bytes()), "authentication_helper_sha256": AUTH_SHA,
        "preserved_review_history": {name: sha(Path(__file__).with_name(name).read_bytes()) for name in
            ("compact-exact-independent-review-attempt1.py", "compact-exact-independent-review.log")},
        "review_repair": "First review stopped on pair-row ordering only; compare unique ordered-hand keys. Producer source, archive and all study bytes remain unchanged; failed helper and log preserved.",
        "memory_scope": "Allocation trace and process lifetime peak stay separate; modeled entries are not bytes.",
        "scope": "22-world four-street complete policies; full-range single-board forced all-in is a zero-decision control, not full-range choice training or an exact certificate."}
    receipt.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"outcome": "accepted", "receipt_sha256": sha(receipt.read_bytes()),
        "source_files": authenticated["files"], "numeric_replays": len(replayed), "exact_recomputations": len(exacts),
        "exact_threshold_flags": {mode: value["threshold_met"] for mode, value in exacts.items()}}))


if __name__ == "__main__":
    main()
