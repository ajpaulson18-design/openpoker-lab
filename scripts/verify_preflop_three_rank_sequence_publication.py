"""Authenticate the saved physical three-rank witness without candidate search."""
import hashlib
import json
from pathlib import Path
import re

from scripts import certify_preflop_three_rank_sequence as formal
from scripts import preflop_three_rank_pure_response as independent
from scripts import verify_preflop_three_rank_transport_publication as transport
from scripts import preflop_publication_source_history as history

ROOT = Path(__file__).resolve().parents[1]
PUBLICATION = ROOT / "benchmarks/results/preflop-three-rank-exact-witness-v1"
GENERATION = "58ccc8d886a22428efe26c8ba9447a596659db29"
BASELINE = "23beb4b8983d8c6549c33ff0b07a741c2674555b"
VALUE = "1464215/2330174"
PINS = {
    "candidate.json": {"bytes": 84_330,
                       "raw": "dd0345efdf388638ad3e359baeb84b0872f1701ab942549f4a0d257b0d141e85",
                       "artifact": "18933598b5410e926440773351cf53d9c1990835b68fa8c2129f7c82e99cb6c4"},
    "report.json": {"bytes": 112_057,
                    "raw": "3f3aacce30283e3db474771fa396fa92f566b39332399358b8680830a772239b",
                    "artifact": "792820c701099e02213e715e777224405572e719e114555a9fae3d7485c0202a"},
}
SOURCES = (*formal.transport_run.SOURCE_PATHS, *formal.EXTRA_SOURCES)
GUARDS = (*formal.transport_run.FORBIDDEN,
          "scripts.preflop_three_rank_transport.build_candidate",
          "pokerlab.preflop_covered_equity.pool_preflop_equities_by_suit",
          "pokerlab.preflop_covered_equity._ranges",
          "scripts.preflop_three_rank_sequence_candidate.build_candidate",
          "scripts.preflop_checkdown_validation._build",
          "scripts.river_sequence_form._solve_lp")
REPORT_KEYS = {"artifact_sha256", "baseline_commit", "benchmark_id", "candidate",
               "candidate_attempts", "cleanup_errors", "created_at_utc", "elapsed_seconds",
               "errors", "forbidden_calculation_calls", "independent_verification_calls",
               "lp_solve_calls", "memory_verification", "quality_target_met", "request_sha256",
               "runtime", "saved_file_verification", "schema_version", "scope", "source_after",
               "source_before", "source_unchanged", "status"}


def _need(condition, message):
    if not condition:
        raise ValueError(message)


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _artifact(value):
    return hashlib.sha256(_canonical({key: item for key, item in value.items()
                                    if key != "artifact_sha256"})).hexdigest()


def _inventory(directory):
    _need(directory.is_dir() and not directory.is_symlink(), "Missing or symlinked witness corpus")
    _need({path.name for path in directory.iterdir()} == set(PINS), "Witness corpus inventory differs")
    return {name: transport._bounded_read(directory / name, pin["bytes"],
                                         expected_bytes=pin["bytes"], expected_sha256=pin["raw"])
            for name, pin in PINS.items()}


def _frozen_source(source):
    _need(type(source) is dict and set(source) == {"revision", "status", "source_hashes"},
          "Historical witness source schema differs")
    _need(source["revision"] == GENERATION and type(source["status"]) is list
          and source["status"] == [], "Historical witness source was not the clean frozen generation")
    hashes = source["source_hashes"]
    _need(type(hashes) is dict and len(SOURCES) == 15 and set(hashes) == set(SOURCES),
          "Historical witness source inventory differs")
    for name, row in hashes.items():
        _need(type(row) is dict and set(row) == {"raw_sha256", "lf_sha256"}
              and all(type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value)
                      for value in row.values()), "Malformed historical source digest: " + name)
    return source


def _current_source(source):
    current = formal._snapshot()
    _need(type(current["revision"]) is str
          and re.fullmatch(r"[0-9a-f]{40}", current["revision"]), "Malformed current witness HEAD")
    _need(type(current["status"]) is list and current["status"] == [],
          "Current witness publication checkout must be clean")
    _need(set(current["source_hashes"]) == set(SOURCES), "Current witness source inventory differs")
    transitions = {}
    for name in SOURCES:
        old = source["source_hashes"][name]["lf_sha256"]
        new = current["source_hashes"][name]["lf_sha256"]
        if new != old:
            transition = history.authenticate_transition(name, old, new)
            _need(transition is not None, "Current witness LF source differs: " + name)
            transitions[name] = transition
    return {**current, "publication_source_transitions": transitions}


def _quality(receipt):
    _need(type(receipt) is dict and receipt.get("status") == "passed"
          and receipt.get("exact_mutual_response_verified") is True
          and receipt.get("claimed_profile_value_matches") is True,
          "Saved physical mutual-response receipt did not pass")
    expected = {"physical_private_pair_count": 108, "sb_private_hand_count": 18,
                "bb_private_hand_count": 6, "information_set_count": 96, "source_rows_authenticated": 9}
    for key, value in expected.items():
        _need(type(receipt.get(key)) is int and receipt[key] == value,
              "Physical witness receipt count differs: " + key)
    _need(transport._typed_equal(receipt.get("pure_response_policies_enumerated"),
                                 {"sb": 864, "bb": 216, "total": 1080}),
          "Physical own-hand response census differs")
    for key, value in (("profile_value_sb_fraction", VALUE),
                       ("sb_best_response_own_utility_fraction", VALUE),
                       ("bb_best_response_own_utility_fraction", "-" + VALUE),
                       ("sb_best_response_gain_fraction", "0"),
                       ("bb_best_response_gain_fraction", "0"), ("nash_conv_fraction", "0")):
        _need(type(receipt.get(key)) is str and receipt[key] == value,
              "Exact witness value or response gain differs: " + key)
    _need(receipt.get("candidate_artifact_sha256") == PINS["candidate.json"]["artifact"]
          and receipt.get("candidate_request_sha256") == independent.REQUEST_SHA256,
          "Physical receipt candidate/request linkage differs")


def _report(raw):
    report = independent.sources._load_json(raw)
    _need(type(report) is dict and set(report) == REPORT_KEYS, "Witness report schema differs")
    _need(report["artifact_sha256"] == PINS["report.json"]["artifact"]
          and _artifact(report) == PINS["report.json"]["artifact"], "Witness report canonical pin differs")
    _need(type(report["schema_version"]) is int and report["schema_version"] == 1
          and report["benchmark_id"] == "preflop-three-rank-sequence-witness-v1"
          and report["status"] == "physically-verified", "Witness report identity or status differs")
    _need(report["baseline_commit"] == BASELINE
          and report["request_sha256"] == independent.REQUEST_SHA256,
          "Witness baseline or complete-request identity differs")
    _need(type(report["errors"]) is list and report["errors"] == []
          and type(report["cleanup_errors"]) is list and report["cleanup_errors"] == [],
          "Witness report contains errors")
    _need(report["quality_target_met"] is True and report["source_unchanged"] is True,
          "Witness quality or source stability did not pass")
    for key, value in (("candidate_attempts", 1), ("lp_solve_calls", 2),
                       ("independent_verification_calls", 2)):
        _need(type(report[key]) is int and report[key] == value, "Witness attempt/call census differs")
    source = _frozen_source(report["source_before"])
    _need(transport._typed_equal(source, report["source_after"]), "Witness historical source changed")
    calls = report["forbidden_calculation_calls"]
    _need(type(calls) is dict and set(calls) == set(GUARDS)
          and all(type(value) is int and value == 0 for value in calls.values()),
          "Witness forbidden-call receipt differs")
    _need(transport._typed_equal(report["candidate"],
                                 {"artifact_sha256": PINS["candidate.json"]["artifact"],
                                  "raw_sha256": PINS["candidate.json"]["raw"],
                                  "bytes": PINS["candidate.json"]["bytes"], "status": "candidate-only"}),
          "Witness candidate file linkage differs")
    _quality(report["memory_verification"])
    _quality(report["saved_file_verification"])
    _need(transport._typed_equal(report["memory_verification"], report["saved_file_verification"]),
          "Witness original memory and saved receipts differ")
    return report, source


def verify(directory=None):
    directory = PUBLICATION if directory is None else Path(directory)
    raw = _inventory(directory)  # Both raw pins precede every JSON parse.
    report, source = _report(raw["report.json"])
    candidate = independent.sources._load_json(raw["candidate.json"])
    _need(type(candidate) is dict and candidate.get("artifact_sha256") == PINS["candidate.json"]["artifact"]
          and _artifact(candidate) == PINS["candidate.json"]["artifact"], "Candidate canonical pin differs")
    _need(sum(len(row["actions"]) for row in candidate["policies"]) == 258,
          "Witness physical action-slot census differs")
    before = _current_source(source)
    calls = {}
    with formal.transport_run.no_calculation(calls, independent_phase=True), formal._independent_only_guard(calls):
        checked = independent.verify_candidate(directory / "candidate.json")
    _quality(checked)
    _need(transport._typed_equal(checked, report["memory_verification"])
          and transport._typed_equal(checked, report["saved_file_verification"]),
          "Fresh physical responses differ from the frozen receipts")
    _need(set(calls) == set(GUARDS) and all(type(value) is int and value == 0 for value in calls.values()),
          "Forbidden computation during witness publication authentication")
    after = _current_source(source)
    _need(transport._typed_equal(before, after), "Current witness source changed during authentication")
    _need(_inventory(directory) == raw, "Witness corpus changed during authentication")
    return {"status": "authenticated-saved-exact-witness", "source_revision": GENERATION,
            "candidate_artifact_sha256": PINS["candidate.json"]["artifact"],
            "report_artifact_sha256": PINS["report.json"]["artifact"],
            "physical_private_pair_count": 108, "policy_rows": 96, "action_slots": 258,
            "legal_own_hand_responses": 1080, "exact_value_sb_fraction": VALUE,
            "nash_conv_fraction": "0", "fresh_candidate_searches": 0,
            "board_enumerations": 0, "rank_calls": 0, "training_calls": 0,
            "current_source_attestation": after,
            "scope": "saved exact witness for one finite preflop/checkdown game only"}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", nargs="?")
    args = parser.parse_args()
    print(json.dumps(verify(args.directory), sort_keys=True), flush=True)
