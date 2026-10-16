"""Exhaustively compare the native ranker with the independent five-card oracle."""
from __future__ import annotations

import argparse
from hashlib import sha256
from itertools import combinations, islice
import json
import os
from pathlib import Path
import tempfile
import time
import sys

from pokerlab.native_preflop_equity import _backend, rank_native_hands
from scripts.preflop_validation import _five_rank

# Deliberately spell the physical deck independently of pokerlab.cards.DECK.
_RANKS = "23456789TJQKA"
_SUITS = "cdhs"
_DECK = tuple(rank + suit for rank in _RANKS for suit in _SUITS)
_BATCH_SIZE = 4096
_EXPECTED_TOTAL = 2_598_960
_EXPECTED_CATEGORY_COUNTS = {
    0: 1_302_540,
    1: 1_098_240,
    2: 123_552,
    3: 54_912,
    4: 10_200,
    5: 5_108,
    6: 3_744,
    7: 624,
    8: 40,
}
_SOURCE_PATHS = {
    "cards": Path("pokerlab/cards.py"),
    "native_wrapper": Path("pokerlab/native_preflop_equity.py"),
    "native_source": Path("native/preflop_equity.c"),
    "independent_oracle": Path("scripts/preflop_validation.py"),
    "validator": Path(__file__).resolve().relative_to(Path(__file__).resolve().parents[1]),
}
_ROOT = Path(__file__).resolve().parents[1]


def _canonical_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def _file_hashes(path):
    raw = path.read_bytes()
    return {
        "sha256": sha256(raw).hexdigest(),
        "lf_sha256": sha256(raw.replace(b"\r\n", b"\n")).hexdigest(),
    }


def _source_identity(build_directory):
    executable, manifest = _backend(build_directory)
    sources = {}
    for name, relative_path in _SOURCE_PATHS.items():
        source_path = _ROOT / relative_path
        sources[name] = {"path": relative_path.as_posix(), **_file_hashes(source_path)}
    manifest_path = Path(build_directory) / "native-preflop-manifest.json"
    return {
        "sources": sources,
        "build_manifest": {
            "name": manifest_path.name,
            "sha256": sha256(manifest_path.read_bytes()).hexdigest(),
            "identity": manifest,
        },
        "executable": {
            "name": executable.name,
            "sha256": _file_hashes(executable)["sha256"],
        },
    }


def _pad_rank(rank):
    rank = tuple(rank)
    if not rank or len(rank) > 6:
        raise ValueError("Independent oracle returned an invalid five-card rank tuple.")
    return rank + (0,) * (6 - len(rank))


def _write_report(report, output_path):
    report["artifact_sha256"] = sha256(_canonical_bytes(report)).hexdigest()
    encoded = _canonical_bytes(report) + b"\n"
    if output_path is None:
        sys.stdout.buffer.write(encoded)
        sys.stdout.buffer.flush()
        return

    destination = Path(output_path).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=str(destination.parent))
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, destination)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def _run(build_directory):
    started = time.perf_counter()
    before = _source_identity(build_directory)
    hands = iter(combinations(_DECK, 5))
    checked = 0
    mismatches = 0
    first_mismatch = None
    oracle_categories = [0] * 9
    native_categories = [0] * 9
    batches = 0

    while True:
        batch = list(islice(hands, _BATCH_SIZE))
        if not batch:
            break
        native_ranks = rank_native_hands(batch, build_directory=build_directory)
        if len(native_ranks) != len(batch):
            raise ValueError("Native wrapper returned a rank count different from its request.")
        for hand, native_rank in zip(batch, native_ranks):
            expected = _pad_rank(_five_rank(hand))
            actual = tuple(native_rank)
            oracle_categories[expected[0]] += 1
            native_categories[actual[0]] += 1
            if actual != expected:
                mismatches += 1
                if first_mismatch is None:
                    first_mismatch = {
                        "index": checked,
                        "hand": list(hand),
                        "expected": list(expected),
                        "actual": list(actual),
                    }
            checked += 1
        batches += 1
        if batches % 100 == 0:
            print(f"validated {checked:,}/{_EXPECTED_TOTAL:,} five-card hands",
                  file=sys.stderr, flush=True)

    after = _source_identity(build_directory)
    stable = before == after
    oracle_hist = {str(category): oracle_categories[category] for category in range(9)}
    native_hist = {str(category): native_categories[category] for category in range(9)}
    expected_hist = {str(category): _EXPECTED_CATEGORY_COUNTS[category]
                     for category in range(9)}
    histogram_ok = oracle_hist == expected_hist
    native_histogram_ok = native_hist == oracle_hist
    report = {
        "schema_version": 1,
        "validator": "native-five-card-exhaustive-v1",
        "algorithm": "enumerate every five-card set; compare native six-value rank tuple with independently implemented _five_rank padded with zeros",
        "rank_scope": "all five-card combinations only; this does not claim exhaustive six- or seven-card conformance",
        "deck": {"ranks": _RANKS, "suits": _SUITS, "card_count": len(_DECK)},
        "batch_size": _BATCH_SIZE,
        "batches": batches,
        "total_combinations": _EXPECTED_TOTAL,
        "hands_checked": checked,
        "mismatch_count": mismatches,
        "first_mismatch": first_mismatch,
        "category_counts_oracle": oracle_hist,
        "category_counts_native": native_hist,
        "expected_category_counts": expected_hist,
        "checks": {
            "all_five_card_combinations_checked": checked == _EXPECTED_TOTAL,
            "oracle_category_counts_match_known_totals": histogram_ok,
            "native_category_counts_match_oracle": native_histogram_ok,
            "native_rank_tuples_match_oracle": mismatches == 0,
            "source_and_build_identity_stable": stable,
        },
        "elapsed_seconds": round(time.perf_counter() - started, 6),
        "source_identity_before": before,
        "source_identity_after": after,
        "passed": (checked == _EXPECTED_TOTAL and histogram_ok
                   and native_histogram_ok and mismatches == 0 and stable),
    }
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-dir", required=True,
                        help="Directory containing native-preflop-manifest.json and its pinned executable")
    parser.add_argument("--output", help="Optional report path; defaults to canonical JSON on stdout")
    args = parser.parse_args(argv)
    build_directory = Path(args.build_dir).resolve(strict=True)
    if args.output is not None:
        destination = Path(args.output).resolve()
        executable, _ = _backend(build_directory)
        protected = {_ROOT / relative_path for relative_path in _SOURCE_PATHS.values()}
        protected.add(build_directory / "native-preflop-manifest.json")
        protected.add(executable.resolve())
        if destination in {path.resolve() for path in protected}:
            parser.error("--output must not overwrite a source, build manifest, or native executable")
    report = _run(build_directory)
    _write_report(report, args.output)
    if not report["passed"]:
        raise SystemExit("native five-card conformance validation failed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
