"""Read-only authentication and independent saved-policy review of frozen DAG study.

Execution requires a lead-confirmed terminal process handle and explicit audit pins.
This helper never trains policies, launches native code, changes source, or rewrites
saved study artifacts. Its JSON receipt lives outside both source and study trees.
"""
import argparse
import ast
import re
import zipfile
from contextlib import ExitStack
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import statistics
import subprocess
import sys
from unittest.mock import patch

FROZEN = "90ede1ce2770c2e5872bd12c44abe2f2f50a66e3"
NUMERIC = ("value_sb", "value_bb", "sb_best_response_value", "bb_best_response_value", "nash_conv")
EXACT = frozenset(("value_sb", "value_bb", "sb_best_response_value", "bb_best_response_value",
    "sb_best_response_gain", "bb_best_response_gain", "nash_conv", "exploitability",
    "lower_value_bound", "upper_value_bound"))
THRESHOLD = Fraction(1, 1000)
MAX_RATIONAL_BITS = 65_536
SCHEDULE = ((100,"python",0,False),(100,"native",0,False),
    (100,"native",1,False),(100,"python",1,False),(100,"python",2,False),
    (100,"native",2,False),(100,"python","traced",True),(100,"native","traced",True),
    (1000,"python",0,False),(1000,"native",0,False))


def need(condition, message):
    if not condition:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def no_duplicates(pairs):
    result = {}
    for key, value in pairs:
        need(key not in result, "duplicate JSON key: " + key)
        result[key] = value
    return result


def parse(raw):
    return json.loads(raw, object_pairs_hook=no_duplicates,
        parse_constant=lambda value: (_ for _ in ()).throw(ValueError("nonfinite JSON: " + value)))


def canonical(value):
    return sha(json.dumps(value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=True, allow_nan=False).encode("ascii"))


def git(repo, *args, data=None):
    return subprocess.check_output(["git", *args], cwd=repo, input=data)


def source_identity(repo, source):
    need(source["commit"] == FROZEN and source["status"] == "", "wrong or dirty source snapshot")
    need(git(repo, "rev-parse", "HEAD").decode().strip() == FROZEN, "live source HEAD drift")
    need(not git(repo, "status", "--porcelain", "--untracked-files=all").strip(), "live source is dirty")
    tracked = git(repo, "ls-files", "-z").decode().rstrip("\0").split("\0")
    need(set(tracked) == set(source["sha256"]), "incomplete tracked source closure")
    observed = {}
    for name in tracked:
        path = repo / name
        need(path.is_file() and not path.is_symlink(), "nonordinary source file: " + name)
        observed[name] = sha(path.read_bytes())
    need(observed == source["sha256"], "raw source bytes differ from frozen study closure")
    # Git applies the checked-in attributes and configured text conversion. This
    # independently ties all raw-pinned working files to frozen committed blobs.
    entries = git(repo, "ls-tree", "-rz", "--full-tree", FROZEN).rstrip(b"\0").split(b"\0")
    blobs = {}
    for entry in entries:
        metadata, name = entry.split(b"\t", 1)
        mode, kind, digest = metadata.split()
        need(kind == b"blob" and mode in (b"100644", b"100755"), "nonordinary committed source entry")
        blobs[name.decode()] = digest.decode()
    need(set(blobs) == set(tracked), "commit source closure differs from tracked closure")
    need(all("\n" not in name and '"' not in name and "\\" not in name for name in tracked), "unsupported source filename")
    content = ("\n".join(tracked) + "\n").encode()
    normalized = git(repo, "hash-object", "--stdin-paths", data=content).decode().splitlines()
    need(len(normalized) == len(tracked), "incomplete committed-blob authentication")
    exact_raw, normalized_only = [], []
    for name, digest in zip(tracked, normalized):
        raw = (repo/name).read_bytes()
        raw_git_object = hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()
        if raw_git_object == blobs[name]:
            exact_raw.append(name)
        else:
            need(digest == blobs[name], "working source differs from committed raw/normalized blob: " + name)
            normalized_only.append(name)
    return {"commit": FROZEN, "files": len(tracked), "raw_sha256": observed,
            "git_raw_or_normalized_committed_blobs_match": True,
            "raw_committed_blob_files": len(exact_raw),
            "normalized_committed_blob_files": len(normalized_only)}


def bounded_fraction(text):
    need(type(text) is str and re.fullmatch(r"[+-]?[0-9]+(?:/[0-9]+)?", text), "invalid bounded rational text")
    parts = text.split("/")
    # 30103/100000 is an upper decimal-digit approximation to log10(2).
    digits = (MAX_RATIONAL_BITS * 30103) // 100000 + 1
    def integer(part):
        negative = part.startswith("-")
        unsigned = part.lstrip("+-")
        need(len(unsigned) <= digits, "exact rational decimal length exceeds unchanged bit limit")
        value = 0
        for at in range(0, len(unsigned), 9):
            chunk = unsigned[at:at+9]
            value = value * (10 ** len(chunk)) + int(chunk)
            need(value.bit_length() <= MAX_RATIONAL_BITS, "exact rational exceeds unchanged bit limit")
        return -value if negative else value
    numerator = integer(parts[0])
    denominator = integer(parts[1]) if len(parts) == 2 else 1
    need(denominator > 0, "nonpositive exact denominator")
    return Fraction(numerator, denominator)


def metrics(value):
    need(type(value) is dict and set(value) == EXACT, "wrong exact metric fields")
    need(all(type(v) is str and v for v in value.values()), "exact metrics must be rational strings")
    result = {key: bounded_fraction(item) for key, item in value.items()}
    need(result["nash_conv"] >= 0 and result["exploitability"] >= 0, "negative exact quality metric")
    return result


def numeric_gaps(value):
    need(type(value) is dict and set(value) == set(NUMERIC), "wrong numeric replay gap fields")
    need(all(type(v) in (int,float) and math.isfinite(v) and 0 <= v <= 1e-10
             for v in value.values()), "numeric replay gap outside unchanged tolerance")


def game(payload):
    census = payload["operator_census"]
    return {"counts": {key: payload[key] for key in (
        "candidate_private_pairs", "compatible_private_pairs", "worlds", "pair_runout_preflight_checks",
        "public_states", "decisions", "info_sets")},
        "construction": census["direct_public_topology"], "layout": census["shared_strategy_storage"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--study", required=True, type=Path)
    parser.add_argument("--receipt", required=True, type=Path)
    parser.add_argument("--confirmed-terminal-handle", required=True)
    parser.add_argument("--terminal-exit-code", required=True, type=int)
    parser.add_argument("--t100-manifest", required=True)
    parser.add_argument("--t1000-manifest", required=True)
    parser.add_argument("--fresh-exact", action="store_true")
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--archive-sha256")
    args = parser.parse_args()
    need(args.confirmed_terminal_handle and args.terminal_exit_code == 0,
         "requires lead-confirmed successful terminal study handle")
    repo, study, receipt = args.repo.resolve(), args.study.resolve(), args.receipt.resolve()
    need(receipt != repo and repo not in receipt.parents and study not in receipt.parents,
         "receipt must stay outside source and immutable study")
    need(not receipt.exists(), "refuse to overwrite independent receipt")
    initial_files = sorted(path for path in study.rglob("*") if path.is_file())
    saved = {path.relative_to(study).as_posix(): path.read_bytes() for path in initial_files}
    all_hashes = {name: sha(raw) for name, raw in saved.items()}
    report = parse(saved["report.json"])
    protocol = parse(saved["protocol.json"])
    source = parse(saved["source-before.json"])
    authenticated = source_identity(repo, source)  # BEFORE any repository math import.
    certificate_ast = ast.parse((repo/"scripts/four_street_certificate.py").read_text())
    pinned_bit_limits = [ast.literal_eval(node.value) for node in certificate_ast.body
        if isinstance(node,ast.Assign) and any(isinstance(target,ast.Name) and target.id == "MAX_FRACTION_BITS" for target in node.targets)]
    need(pinned_bit_limits == [MAX_RATIONAL_BITS], "independent rational parser bit limit differs from unchanged source")
    need(parse(saved["source-after.json"]) == source == report["source_before"] == report["source_after"], "source snapshot mismatch")
    need(report["protocol"] == protocol and protocol["source_commit"] == FROZEN,
         "report/protocol source mismatch")
    need(protocol["source_sha256"] == source["sha256"], "protocol source closure mismatch")
    need(protocol["runner_sha256"] == source["sha256"]["scripts/benchmark_native_selected_dag.py"], "runner source pin mismatch")
    need(report["outcome"] == "complete" and report["failures"] == [], "study did not complete successfully")
    need(report["training_calls"] == 10 and report["native_calls"] == 5 and len(report["samples"]) == 10,
         "wrong complete-call or native call counts")
    need(protocol["worlds"] == 22 and protocol["rank_cache_boards"] == 64 and protocol["strategy_storage"] == "packed",
         "protocol fixture/mode drift")
    expected_schedule = [{"iterations": t, "backend": b, "sample": s, "traced": tr} for t,b,s,tr in SCHEDULE]
    need(protocol["schedule"] == expected_schedule, "fixed schedule drift")
    native_identity = protocol["native_build_identity"]
    cpp = (repo / "native/selected_dag_train.cpp").read_bytes()
    need(native_identity["source_sha256"] == sha(cpp) and native_identity["source_lf_sha256"] == sha(cpp.replace(b"\r\n",b"\n")),
         "native raw/LF source guard mismatch")
    pins = {100: args.t100_manifest, 1000: args.t1000_manifest}
    audits = {}
    for iterations, pin in pins.items():
        base = f"audit-t{iterations}/"
        need(report["externally_pinnable_manifest_sha256"][str(iterations)] == pin, "external audit pin differs from report")
        need(sha(saved[base+"manifest.json"]) == pin, "audit manifest pin mismatch")
        manifest = parse(saved[base+"manifest.json"])
        for name, digest in manifest["sha256"].items():
            need(Path(name).name == name and sha(saved[base+name]) == digest, "audit sample hash mismatch: " + name)
        need(parse(saved[base+"source.json"]) == source, "audit source closure mismatch")
        need(parse(saved[base+"protocol.json"]) == protocol | {"audit_iterations":iterations}, "audit protocol mismatch")
        for backend, alias in (("python","reference-0.json"),("native","operator-0.json")):
            name = f"t{iterations}-{backend}-0.json"
            need(saved[name] == saved[base+name] == saved[base+alias], "raw alias byte mismatch")
        audit = parse(saved[base+"saved-replay.json"])
        need(audit == report["saved_independent_audit"][str(iterations)], "saved audit/report mismatch")
        need(audit["training_calls"] == audit["native_calls"] == 0 and audit["source_unchanged"] is True,
             "saved audit executed training or lacked source authentication")
        need(audit["manifest_sha256"] == pin and len(audit["audits"]) == 2, "saved audit identity mismatch")
        for row in audit["audits"]:
            alias = row["artifact"]
            need(alias in ("reference-0.json","operator-0.json") and row["sha256"] == sha(saved[base+alias]), "saved audit alias hash mismatch")
            numeric_gaps(row["numeric_differences"])
            exact = metrics(row["exact_metrics"])
            certificate = parse(saved[base+alias[:-5]+"-certificate.json"])
            need(metrics(certificate["metrics"]) == exact and bounded_fraction(certificate["threshold"]) == THRESHOLD,
                 "exact certificate metric/threshold mismatch")
            passed = exact["nash_conv"] <= THRESHOLD
            need(type(row["exact_target_met"]) is bool and row["exact_target_met"] == passed == certificate["threshold_met"], "exact target flag mismatch")
            need(passed == (iterations == 1000), "expected T100 miss/T1000 pass changed")
            payload = parse(saved[base+alias])["payload"]
            need(certificate["input_policy_canonical_sha256"] == canonical(payload), "certificate policy input hash mismatch")
        need(metrics(audit["audits"][0]["exact_metrics"]) == metrics(audit["audits"][1]["exact_metrics"]), "paired exact metrics differ")
        audits[iterations] = audit
    payloads, raw_records = {}, []
    for row, (iterations,backend,sample,traced) in zip(report["samples"],SCHEDULE):
        name = f"t{iterations}-{backend}-{'traced' if traced else sample}.json"
        raw = parse(saved[name]); payload = raw["payload"]
        need(row["artifact"] == name and row["raw_sha256"] == sha(saved[name]), "report raw sample pin mismatch")
        for field, expected in (("backend",backend),("iterations",iterations),("traced",traced),
                ("public_topology","direct"),("rank_cache_boards",64),("strategy_storage","packed")):
            need(raw[field] == expected and row[field] == expected, "sample metadata mismatch: " + field)
        need(raw["seconds"] == row["seconds"] and type(raw["seconds"]) in (int,float) and math.isfinite(raw["seconds"]) and raw["seconds"]>0,
             "sample timing invalid")
        need(payload["worlds"] == 22 and payload["iterations"] == iterations and payload["info_sets"] == 1200 and len(payload["strategy"]) == 1200,
             "sample game counts drift")
        need(raw["native_calls"] == row["native_calls"] == int(backend=="native"), "sample native count drift")
        peak = raw["native_process_lifetime_peak_working_set_bytes"]
        if backend == "native":
            training = payload["native_training"]
            need(training["identity"] == native_identity and training["calls"] == 1, "sample native identity drift")
            need(type(peak) is int and peak>0 and peak == training["native_process_lifetime_peak_working_set_bytes"], "native process peak mismatch")
        else:
            need(peak is None and payload.get("native_training") is None, "Python sample unexpectedly has native peak/call")
        allocation = raw["python_tracemalloc_peak_bytes"]
        need((type(allocation) is int and allocation>0) if traced else allocation is None, "Python trace peak scope mismatch")
        need(type(raw["python_process_lifetime_peak_working_set_bytes"]) is int and raw["python_process_lifetime_peak_working_set_bytes"]>0,
             "invalid Python process peak")
        need(row["python_tracemalloc_peak_bytes"] == allocation and row["native_process_lifetime_peak_working_set_bytes"] == peak,
             "memory report differs from raw sample")
        payloads[(iterations,backend,sample,traced)] = payload
        raw_records.append({"artifact":name,"sha256":sha(saved[name]),"backend":backend,"iterations":iterations,
            "sample":sample,"traced":traced,"seconds":raw["seconds"],"python_trace_peak":allocation,
            "python_process_peak":raw["python_process_lifetime_peak_working_set_bytes"],"native_process_peak":peak})
    for iterations, backend, sample, traced in SCHEDULE:
        if backend != "python": continue
        left = payloads[(iterations,"python",sample,traced)]
        right = payloads[(iterations,"native",sample,traced)]
        for field in ("strategy","private_pair_probabilities",*NUMERIC,"value_bb","sb_gain","bb_gain","exploitability","public_batched_training_pot_anchor"):
            need(left[field] == right[field], "paired policy/diagnostic mismatch: " + field)
        need(game(left) == game(right), "paired game census mismatch")
    for iterations in (100,1000):
        for backend in ("python","native"):
            seconds = [r["seconds"] for r in raw_records if r["iterations"] == iterations and r["backend"] == backend and not r["traced"]]
            need(report["medians_seconds"][str(iterations)][backend] == statistics.median(seconds), "reported median mismatch")
    # All source/artifact authentication above precedes math imports/execution.
    sys.dont_write_bytecode = True
    sys.path.insert(0,str(repo))
    from scripts.preflop_validation import replay_policy, compare_result
    from scripts.four_street_certificate_v3 import evaluate_exact
    case = parse((repo/"benchmarks/four-street-integration-v1.json").read_bytes())["case"]
    need(Fraction(str(case["config"].get("big_blind",1))) == 1, "threshold requires unchanged one-BB fixture units")
    replay_receipts, fresh_exact = [], {}
    forbidden = ("pokerlab.selected_operator_solver.solve_four_street_operator",
        "pokerlab.packed_operator_cfr.train_packed", "pokerlab.native_selected_dag.train_native_selected_dag",
        "pokerlab.native_selected_operator.train_native_selected", "pokerlab.public_cfr._train_prepared",
        "pokerlab.preflop_solver.solve_preflop", "pokerlab.cfr.train", "subprocess.Popen")
    with ExitStack() as stack:
        for target in forbidden:
            stack.enter_context(patch(target,side_effect=AssertionError("forbidden saved review call: "+target)))
        for key, payload in payloads.items():
            iterations,backend,sample,traced = key
            numeric = replay_policy(payload,case["sb_range"],case["bb_range"],config=case["config"],runouts=case["runouts"],
                flop_config=case["flop_config"],turn_config=case["turn_config"],river_config=case["river_config"])
            gaps = compare_result(payload,numeric)
            numeric_gaps(gaps)
            need(numeric["checked_information_sets"] == 1200 and numeric["worlds"] == 22, "fresh replay incomplete")
            replay_receipts.append({"iterations":iterations,"backend":backend,"sample":sample,"traced":traced,"numeric_gaps":gaps})
        if args.fresh_exact:
            for iterations in (100,1000):
                result = evaluate_exact(case,payloads[(iterations,"python",0,False)])
                need(metrics(result["metrics"]) == metrics(audits[iterations]["audits"][0]["exact_metrics"]), "fresh exact metrics differ")
                need(bounded_fraction(result["threshold"]) == THRESHOLD and result["threshold_met"] == (iterations==1000), "fresh exact threshold changed")
                fresh_exact[str(iterations)] = {"metrics":result["metrics"],"threshold":result["threshold"],
                    "threshold_met":result["threshold_met"],"normalized_policy_sha256":result["normalized_policy_sha256"]}
    # Read-only stability checks include the full tree of saved certificates/reports.
    need(sorted(path.relative_to(study).as_posix() for path in study.rglob("*") if path.is_file()) == sorted(saved), "study file inventory changed")
    need(all((study/name).read_bytes() == raw for name,raw in saved.items()), "saved artifacts changed during review")
    need(source_identity(repo,source) == authenticated, "source changed during review")
    archive = None
    if args.archive:
        need(args.archive_sha256 and sha(args.archive.read_bytes()) == args.archive_sha256, "archive pin mismatch")
        with zipfile.ZipFile(args.archive) as zipped:
            entries = {item.filename:zipped.read(item) for item in zipped.infolist() if not item.is_dir()}
            need(len(entries) == len([item for item in zipped.infolist() if not item.is_dir()]), "duplicate archive file names")
            for name, raw in saved.items():
                candidates = [key for key in entries if key == name or key.endswith("/"+name)]
                need(len(candidates) == 1 and entries[candidates[0]] == raw, "archive saved-study byte mismatch: "+name)
        archive = {"path":str(args.archive.resolve()),"sha256":args.archive_sha256,
            "saved_study_files_authenticated":len(saved),"archive_file_entries":len(entries)}
    result = {"outcome":"accepted", "reviewer":"independent Sol substitute for unavailable Terra",
        "confirmed_terminal_handle":args.confirmed_terminal_handle,"terminal_exit_code":args.terminal_exit_code,
        "source_commit":FROZEN,"authenticated_source_files":authenticated["files"],
        "independent_rational_parser_bit_limit":MAX_RATIONAL_BITS,
        "preserved_second_helper_sha256":sha(Path(__file__).with_name("native-dag-independent-review-v2-preserved.py").read_bytes()),
        "preserved_second_parser_failure_log_sha256":sha(Path(__file__).with_name("native-dag-independent-review-v2-integer-parser-failure.log").read_bytes()),
        "source_raw_sha256":authenticated["raw_sha256"],"git_raw_or_normalized_committed_blobs_match":True,
        "raw_committed_blob_files":authenticated["raw_committed_blob_files"],
        "normalized_committed_blob_files":authenticated["normalized_committed_blob_files"],
        "review_helper_sha256":sha(Path(__file__).read_bytes()),
        "preserved_first_helper_sha256":sha(Path(__file__).with_name("native-dag-independent-review-v1-preserved.py").read_bytes()),
        "preserved_first_auth_failure_log_sha256":sha(Path(__file__).with_name("native-dag-independent-review-v1-first-auth-failure.log").read_bytes()),
        "source_and_artifacts_unchanged_after_review":True,"audit_manifest_sha256":{str(k):v for k,v in pins.items()},
        "artifact_sha256":all_hashes,"raw_samples":raw_records,"training_calls":0,"native_calls":0,
        "forbidden_entry_points":list(forbidden),"fresh_numeric_replay":replay_receipts,"fresh_exact":fresh_exact,
        "archive":archive,"archive_pin_pending":archive is None,
        "memory_scope":"Three separate observations; no Python/native peak addition or general memory claim.",
        "scope":"One conditioned22-world game; two exact sample-zero iteration policies plus all10numeric saved policies. No training/native execution; no unrestricted/full-deck claim."}
    receipt.write_text(json.dumps(result,indent=2,sort_keys=True,allow_nan=False)+"\n",encoding="utf-8")
    print(json.dumps({"outcome":result["outcome"],"receipt":str(receipt),"receipt_sha256":sha(receipt.read_bytes()),
        "source_files":authenticated["files"],"raw_samples":len(raw_records),"fresh_numeric_replays":len(replay_receipts),
        "fresh_exact_policies":len(fresh_exact),"max_numeric_gap":max(max(x["numeric_gaps"].values()) for x in replay_receipts)}))


if __name__ == "__main__":
    main()
