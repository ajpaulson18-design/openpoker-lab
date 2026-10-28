"""Authenticate current source, then replay saved lookup policies without solving."""
import argparse
from contextlib import ExitStack
from fractions import Fraction
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import statistics
import sys
from unittest.mock import patch

AUTH = "8171ead3ba108f8200f15e85696f40d109ed894209fa7d77598780b83c1401c5"
METRICS = ("value_sb", "value_bb", "sb_best_response_value", "bb_best_response_value",
           "sb_gain", "bb_gain", "nash_conv", "exploitability")
SCHEDULE = (("original-22-t10", "per-row", 0, False), ("original-22-t10", "per-decision", 0, False),
    ("original-22-t10", "per-decision", 1, False), ("original-22-t10", "per-row", 1, False),
    ("original-22-t10", "per-row", 2, False), ("original-22-t10", "per-decision", 2, False),
    ("original-22-t10", "per-row", "traced", True), ("original-22-t10", "per-decision", "traced", True),
    ("payoff-varied-t100", "per-row", 0, False), ("payoff-varied-t100", "per-decision", 0, False),
    ("blocker-18", "per-row", 0, False), ("blocker-18", "per-decision", 0, False))


def main():
    parser = argparse.ArgumentParser()
    for key in ("repo", "study", "archive", "receipt"):
        parser.add_argument("--" + key, type=Path, required=True)
    for key in ("source-commit", "manifest-sha256", "archive-sha256", "terminal-handle"):
        parser.add_argument("--" + key, required=True)
    parser.add_argument("--terminal-exit-code", type=int, required=True)
    args = parser.parse_args()
    auth_path = Path(__file__).with_name("exact-selected-independent-review.py")
    if hashlib.sha256(auth_path.read_bytes()).hexdigest() != AUTH:
        raise ValueError("External authenticator changed")
    spec = importlib.util.spec_from_file_location("lookup_source_auth", auth_path)
    auth = importlib.util.module_from_spec(spec); spec.loader.exec_module(auth)
    auth.FROZEN = args.source_commit
    need, sha, parse = auth.need, auth.sha, auth.parse
    repo, study, receipt = args.repo.resolve(), args.study.resolve(), args.receipt.resolve()
    need(args.terminal_handle == "28640" and args.terminal_exit_code == 0, "Producer completion not authenticated")
    need(not receipt.exists() and repo not in receipt.parents and study not in receipt.parents, "Use new external receipt")
    saved = {path.name: path.read_bytes() for path in study.iterdir() if path.is_file()}
    need(sha(saved["manifest.json"]) == args.manifest_sha256, "Manifest pin changed")
    manifest = parse(saved["manifest.json"])
    need(manifest["source_commit"] == args.source_commit and set(saved) == set(manifest["sha256"]) | {"manifest.json"}, "Manifest inventory mismatch")
    for name, digest in manifest["sha256"].items():
        need(Path(name).name == name and sha(saved[name]) == digest, "Artifact drift " + name)
    source = parse(saved["source-before.json"])
    source_auth = auth.source_identity(repo, source)  # Before repository math imports.
    need(parse(saved["source-after.json"]) == source, "Producer source drift")
    archive = auth.archive_check(args.archive, args.archive_sha256, saved)
    protocol, report = parse(saved["protocol.json"]), parse(saved["report.json"])
    need(protocol["version"] == "batched-suit-lookup-fixed-study-v1" and protocol["schedule"] == [list(x) for x in SCHEDULE], "Fixed protocol changed")
    need(protocol["source_commit"] == report["source_commit"] == args.source_commit and report["failure"] is None and
         report["calls_planned"] == report["calls_completed"] == len(report["samples"]) == 12, "Incomplete report")
    prior_cases = parse((repo / "benchmarks/results/suit-quotient-storage-v1/protocol.json").read_bytes())["cases"]
    need(protocol["cases"] == {name:prior_cases[name] for name in
         ("original-22-t10", "payoff-varied-t100", "blocker-18")},
         "Requested games differ from previously independently authenticated quotient cases")
    raw_by_label, payloads = {}, {}
    for entry, rec in zip(SCHEDULE, report["samples"]):
        name, mode, sample, traced = entry
        identifier = "-".join(str(value) for value in entry[:3])
        raw = parse(saved[identifier + ".json"])
        need(rec["artifact"] == identifier + ".json" and {k:v for k,v in rec.items() if k != "artifact"} ==
             {k:v for k,v in raw.items() if k != "payload"}, "Raw/report mismatch")
        need((raw["case"],raw["lookup"],raw["sample"],raw["traced"]) == entry and raw["runtime"] == protocol["runtime"], "Raw identity mismatch")
        need(type(raw["seconds"]) in (int,float) and math.isfinite(raw["seconds"]) and raw["seconds"] > 0 and
             type(raw["process_peak_bytes"]) is int and raw["process_peak_bytes"] > 0, "Invalid timing/process observation")
        need((type(raw["python_allocation_peak_bytes"]) is int and raw["python_allocation_peak_bytes"] > 0) if traced else raw["python_allocation_peak_bytes"] is None, "Trace scope mismatch")
        counts = raw["counts"]
        need(all(type(v) is int and v >= 0 for v in counts.values()) and counts["trainer"] == counts["plan"] == 1 and
             counts["rank"] > 0 and not any(counts[k] for k in ("pair","world","native","popen")), "Forbidden/missing producer path")
        raw_by_label[identifier], payloads[identifier] = raw, raw["payload"]
    # Mathematical replay uses unchanged independent physical rules/rank/BR code.
    sys.path.insert(0, str(repo))
    from scripts import four_street_validation as physical, exact_selected_compact_certificate as compact
    from scripts.preflop_validation import compare_result
    forbidden = ["pokerlab.exact_selected_solver.solve_four_street_exact_selected",
        "pokerlab.suit_quotient_plan.SuitQuotientPlan.__init__", "pokerlab.suit_quotient_plan.SuitQuotientPlan.locate",
        "pokerlab.suit_quotient_plan.SuitQuotientPlan.locate_decision_rows", "pokerlab.suit_quotient_cfr.train_suit_quotient",
        "pokerlab.equivariant_packed_cfr.train_equivariant_packed", "pokerlab.exact_selected_kernel.ExactSelectedRunoutKernel.__init__",
        "pokerlab.exact_selected_kernel.rank_hand", "pokerlab.exact_selected_kernel.ExactSelectedRunoutKernel.pair_probability_exact",
        "pokerlab.dyadic_selected_arithmetic.DyadicSelectedArithmeticPlan.__init__", "pokerlab.preflop_solver._enumerate_physical_worlds",
        "pokerlab.selected_runout_operator.SelectedRunoutOperator._iter_worlds", "pokerlab.native_selected_operator.train_native_selected",
        "pokerlab.native_selected_dag.train_native_selected_dag", "pokerlab.native_public_cfr.train_native_public", "subprocess.Popen"]
    checked, exact = [], {}
    with ExitStack() as guards:
        for target in forbidden:
            guards.enter_context(patch(target, side_effect=AssertionError("Production path in saved replay: " + target)))
        for identifier, value in payloads.items():
            raw = raw_by_label[identifier]; name = raw["case"]; case = protocol["cases"][name]
            model = physical.build_model(case)
            expanded = dict(value, compatible_private_pairs=model.counts["compatible_pairs"], private_pair_probabilities=[
                {"sb_hand":row["sb_hand"],"bb_hand":row["bb_hand"],"probability":float(Fraction(row["fraction"]))}
                for row in model.counts["pair_probabilities"]])
            replay = physical.replay_policy(expanded, case); compare_result(expanded, replay)
            profile, br0, br1 = replay["value_sb"], replay["sb_best_response_value"], replay["bb_best_response_value"]
            g0, g1 = max(0.,br0-profile), max(0.,br1+profile)
            metrics = dict(value_sb=profile,value_bb=-profile,sb_best_response_value=br0,bb_best_response_value=br1,
                sb_gain=g0,bb_gain=g1,nash_conv=g0+g1,exploitability=(g0+g1)/2)
            gaps = {key:abs(value[key]-metrics[key]) for key in METRICS}
            need(all(math.isfinite(gap) and gap <= 1e-10 for gap in gaps.values()), "Numeric replay mismatch")
            fresh = compact.evaluate_exact(case, value)
            saved_verification = parse(saved[identifier + "-verification.json"])
            ec, old = fresh["exact_certificate"], saved_verification["exact_compact_certificate"]["exact_certificate"]
            need(all(ec[key] == old[key] for key in ("metrics","threshold","threshold_met","normalized_policy_sha256")), "Exact certificate mismatch")
            need(fresh["compact_input_canonical_sha256"] == auth.canonical(value) and
                 ec["source_identity"] == "four-street-independent-exact-v3" and ec["threshold"] == "1/1000", "Certificate scope mismatch")
            rows = len(model.expected_infos); decisions = len({(key[0],key[2]) for key in model.expected_infos})
            group = value["operator_census"]["suit_quotient_storage"]["group_size"];T = raw["iterations"]
            expected_routes = (3*T+2)*rows if raw["lookup"] == "per-row" else 2*rows+3*T*decisions
            need(raw["counts"]["row_route"] == expected_routes and raw["counts"]["history_transform"] == group*expected_routes,
                 "Independent physical route/transform count mismatch")
            checked.append({"artifact":identifier,"numeric_gaps":gaps,"physical_rows":rows,"physical_decisions":decisions,
                "expected_routes":expected_routes,"history_transforms":group*expected_routes,"threshold_met":ec["threshold_met"]})
            exact[identifier] = ec
    for name, mode, sample, traced in SCHEDULE:
        if mode != "per-row": continue
        left, right = (name+"-"+m+"-"+str(sample) for m in ("per-row","per-decision"))
        x,y = payloads[left],payloads[right]
        need(x["strategy"] == y["strategy"] and all(float(x[k]).hex() == float(y[k]).hex() for k in METRICS) and
             exact[left]["metrics"] == exact[right]["metrics"] and exact[left]["normalized_policy_sha256"] == exact[right]["normalized_policy_sha256"], "Paired policy/metric/certificate drift")
        need(x["operator_census"]["whole_request_admission"] == y["operator_census"]["whole_request_admission"], "Admission drift")
    medians = {mode:statistics.median(raw_by_label['original-22-t10-'+mode+'-'+str(i)]["seconds"] for i in range(3))
               for mode in ("per-row","per-decision")}
    need(medians == report["medians_seconds"], "Report median mismatch")
    need(auth.source_identity(repo, source)["raw_sha256"] == source_auth["raw_sha256"] and
         {path.name:path.read_bytes() for path in study.iterdir() if path.is_file()} == saved, "Source/artifact drift during replay")
    result = {"status":"passed","source_commit":args.source_commit,"source_files":source_auth["files"],"archive":archive,
        "helper_sha256":sha(Path(__file__).read_bytes()),"checks":checked,"medians_seconds":medians,
        "exact_certificates":exact,"source_and_artifacts_unchanged":True,
        "authorship_scope":"Root authored both implementation and this orchestration audit while workers were usage-limited. Mathematical replay uses unchanged independent physical and exact-BR oracle code; no second reviewer author is claimed.",
        "scope":"Saved-only bounded physical policy/BR and route-count reconstruction; no production plan, lookup, trainer, kernel or native execution. Not general scalability or speed proof."}
    receipt.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps({"status":"passed","policies":len(checked),"pairs":6,"receipt_sha256":sha(receipt.read_bytes())}))


if __name__ == "__main__":
    main()
