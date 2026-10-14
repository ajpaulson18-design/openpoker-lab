"""Source-frozen full-board push/fold measurements and independent replay.

Run production, oracle, then verify. Oracle pair files make completed exhaustive
pair counts recoverable; no partial pair is accepted as full-deck evidence.
"""
import argparse
from datetime import datetime, timezone
from fractions import Fraction
import gc
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys
from time import perf_counter
import tracemalloc

from pokerlab.cards import expand_range
from pokerlab.preflop_push_fold import prepare_preflop_equities, solve_prepared_push_fold
from scripts.preflop_push_fold_validation import (
    independent_counts, replay, weighted_equilibrium_certificate,
)

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "benchmarks/preflop-push-fold-v1.json"
RESULTS = ROOT / "benchmarks/results"
PREFIX = "preflop-push-fold-v1"


def hashes():
    paths = sorted((ROOT / "pokerlab").glob("*.py")) + [
        ROOT / "scripts/preflop_validation.py",
        ROOT / "scripts/preflop_push_fold_validation.py",
        Path(__file__).resolve(), CONFIG,
    ]
    return {str(p.relative_to(ROOT)).replace("\\", "/"):
            hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def provenance(source):
    return {"git_revision": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
            "git_status": subprocess.check_output(
                ["git", "status", "--short"], cwd=ROOT, text=True).splitlines(),
            "python": sys.version, "executable": sys.executable,
            "platform": platform.platform(), "source_sha256": source,
            "created_utc": datetime.now(timezone.utc).isoformat()}


def write(path, data, source):
    if hashes() != source:
        raise RuntimeError("Source changed during measurement; refusing publication")
    path.parent.mkdir(parents=True, exist_ok=True)
    data["artifact_sha256"] = hashlib.sha256(json.dumps(
        {k: v for k, v in data.items() if k != "artifact_sha256"},
        sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def read(path, source):
    data = json.loads(path.read_text(encoding="utf-8"))
    digest = hashlib.sha256(json.dumps(
        {k: v for k, v in data.items() if k != "artifact_sha256"},
        sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    if data.get("artifact_sha256") != digest:
        raise ValueError(f"Edited or incomplete measurement artifact: {path}")
    if data.get("schema_version") != 1 or data.get("benchmark_id") != PREFIX:
        raise ValueError(f"Wrong measurement schema or fixture: {path}")
    if data["provenance"]["source_sha256"] != source:
        raise ValueError(f"Stale measurement source: {path}")
    return data


def progress(pair, done, total):
    print(f"pair {pair}: {done:,}/{total:,} full boards", flush=True)


def configuration():
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    # This runner deliberately implements one predeclared finite fixture.
    if (config["schema_version"] != 1 or config["benchmark_id"] != PREFIX
            or config["sb_range"] != "AsAd:1,QsQd:0.5"
            or config["bb_range"] != "AsKh:0.25,KsKd:1"
            or config["iterations"] != [100, 1000, 3000]
            or config["algorithms"] != ["vanilla", "dcfr", "cfrplus"]
            or [x["starting_stack"] for x in config["configs"]] != [2, [3, 2], [2, 3]]
            or any(x["small_blind"] != .5 or x["big_blind"] != 1 for x in config["configs"])
            or config["final_exploitability_chip_limit"] != .005
            or config["final_value_error_chip_limit"] != .005
            or config["metric_absolute_tolerance"] != 1e-10):
        raise ValueError("Runner requires the frozen v1 fixture and gates")
    return config


def production(config, source):
    started = perf_counter()
    table = prepare_preflop_equities(config["sb_range"], config["bb_range"], progress=progress)
    preparation_seconds = perf_counter() - started
    rows = []
    first_complete_seconds = None
    for setting in config["configs"]:
        money = {k: v for k, v in setting.items() if k != "id"}
        for algorithm in config["algorithms"]:
            for iterations in config["iterations"]:
                gc.collect()
                solve_started = perf_counter()
                result = solve_prepared_push_fold(table, config=money,
                    iterations=iterations, algorithm=algorithm)
                json.dumps(result, allow_nan=False)
                elapsed = perf_counter() - solve_started
                if first_complete_seconds is None:
                    first_complete_seconds = perf_counter() - started
                rows.append({"config_id": setting["id"], "algorithm": algorithm,
                             "iterations": iterations, "prepared_solve_seconds": elapsed,
                             "result": result})
                print(f"{setting['id']} {algorithm} {iterations}: "
                      f"exploitability={result['exploitability']:.9g}", flush=True)
    # Separate trace: the complete prepared solve includes training, diagnostics
    # and serialization, but excludes the expensive one-time equity preparation.
    gc.collect()
    tracemalloc.start()
    try:
        memory_result = solve_prepared_push_fold(table,
            config={k: v for k, v in config["configs"][0].items() if k != "id"},
            iterations=config["iterations"][-1], algorithm="cfrplus")
        json.dumps(memory_result, allow_nan=False)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    data = {"schema_version": 1, "benchmark_id": PREFIX, "phase": "production",
            "provenance": provenance(source), "config": config,
            "preparation_seconds": preparation_seconds,
            "preparation_plus_first_solve_seconds": first_complete_seconds,
            "pair_counts": table.metadata()["counts"],
            "preparation_budget": table.budget,
            "prepared_solve_traced_peak_bytes": peak,
            "memory_scope": "One complete 3,000-iteration CFR+ prepared solve with diagnostics and JSON serialization. Excludes one-time full-board equity preparation; Python traced allocation peak, not process RSS.",
            "timing_scope": "Single measurements, no backend comparison or speedup claim. Preparation enumerates every board once. Prepared solve timings include training, exact production diagnostics and JSON serialization; they exclude preparation. First composed-call elapsed includes preparation and the first 100-iteration vanilla solve.",
            "results": rows}
    write(RESULTS / f"{PREFIX}-production.json", data, source)


def oracle(config, source):
    ranges = [expand_range(config[k]) for k in ("sb_range", "bb_range")]
    pairs = [(a, b, Fraction.from_float(x) * Fraction.from_float(y))
             for a, x in ranges[0].items() for b, y in ranges[1].items()
             if set(a).isdisjoint(b)]
    total = sum((weight for _, _, weight in pairs), Fraction())
    for index, (a, b, weight) in enumerate(pairs):
        path = RESULTS / f"{PREFIX}-oracle-pair-{index}.json"
        if path.exists():
            existing = read(path, source)
            prior = weight / total
            if (existing["phase"] != "independent-full-board-oracle"
                    or existing["private_pair"] != ["".join(a), "".join(b)]
                    or existing["pair_probability_fraction"] != [prior.numerator, prior.denominator]):
                raise ValueError("Oracle pair checkpoint identity mismatch")
            print(f"Reusing completed source-matched oracle pair {index}", flush=True)
            continue
        started = perf_counter()
        counts = independent_counts("".join(a), "".join(b), progress=progress)
        if len(counts) != 1:
            raise AssertionError("Single-pair oracle must return exactly one pair")
        row = dict(counts[0])
        row["pair_probability"] = float(weight / total)
        write(path, {"schema_version": 1, "benchmark_id": PREFIX,
                     "phase": "independent-full-board-oracle",
                     "provenance": provenance(source),
                     "private_pair": ["".join(a), "".join(b)],
                     "pair_probability_fraction": [
                         (weight / total).numerator, (weight / total).denominator],
                     "elapsed_seconds": perf_counter() - started, "counts": row}, source)


def verify(config, source):
    measured = read(RESULTS / f"{PREFIX}-production.json", source)
    oracle_rows = [read(RESULTS / f"{PREFIX}-oracle-pair-{i}.json", source)
                   for i in range(3)]
    identities = [("AdAs", "KdKs"), ("QdQs", "AsKh"), ("QdQs", "KdKs")]
    for row, identity, prior in zip(oracle_rows, identities,
                                   (Fraction(8, 13), Fraction(1, 13), Fraction(4, 13))):
        if (row["phase"] != "independent-full-board-oracle"
                or row["private_pair"] != list(identity)
                or row["pair_probability_fraction"] != [prior.numerator, prior.denominator]
                or (row["counts"]["sb_hand"], row["counts"]["bb_hand"]) != identity):
            raise ValueError("Oracle checkpoint identity/prior mismatch")
    counts = [row["counts"] for row in oracle_rows]
    output, failures, certificates = [], [], {}
    for row in measured["results"]:
        result = row["result"]
        checked = replay(result, config["sb_range"], config["bb_range"],
                         result["config"], counts, config["metric_absolute_tolerance"])
        certificate, exact = weighted_equilibrium_certificate(result, counts)
        certificate_replay = replay(certificate, config["sb_range"], config["bb_range"],
                                    result["config"], counts, config["metric_absolute_tolerance"])
        error = abs(checked["value_sb"] - certificate_replay["value_sb"])
        certificates[row["config_id"]] = exact
        item = {k: row[k] for k in ("config_id", "algorithm", "iterations", "prepared_solve_seconds")}
        item.update(independent=checked, value_error_against_certificate=error)
        output.append(item)
        if row["iterations"] == config["iterations"][-1]:
            if checked["exploitability"] > config["final_exploitability_chip_limit"]:
                failures.append(f"{row['config_id']} {row['algorithm']}: exploitability target missed")
            if error > config["final_value_error_chip_limit"]:
                failures.append(f"{row['config_id']} {row['algorithm']}: known-value target missed")
    reference = {}
    for row in output:
        key = row["algorithm"], row["iterations"]
        metrics = row["independent"]
        if key in reference:
            for field in ("value_sb", "sb_best_response_value", "bb_best_response_value", "nash_conv"):
                if abs(reference[key][field] - metrics[field]) > config["metric_absolute_tolerance"]:
                    failures.append(f"Effective-stack/refund invariance failed: {key} {field}")
        else:
            reference[key] = metrics
    report = {"schema_version": 1, "benchmark_id": PREFIX,
              "phase": "independently-verified", "provenance": provenance(source),
              "config": config, "source_unchanged": True,
              "independent_counts": counts, "exact_equilibrium_certificates": certificates,
              "oracle_seconds": sum(row["elapsed_seconds"] for row in oracle_rows),
              "preparation_seconds": measured["preparation_seconds"],
              "prepared_solve_traced_peak_bytes": measured["prepared_solve_traced_peak_bytes"],
              "memory_scope": measured["memory_scope"], "timing_scope": measured["timing_scope"],
              "results": output, "passed": not failures, "failures": failures}
    write(RESULTS / f"{PREFIX}.json", report, source)
    print(json.dumps({"passed": report["passed"], "failures": failures}, indent=2), flush=True)
    return 0 if report["passed"] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("production", "oracle", "verify"))
    args = parser.parse_args()
    config, source = configuration(), hashes()
    result = {"production": production, "oracle": oracle, "verify": verify}[args.phase](config, source)
    if hashes() != source:
        raise RuntimeError("Source changed during run")
    return result or 0


if __name__ == "__main__":
    raise SystemExit(main())
