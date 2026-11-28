"""Check experimental native trainers against immutable ten-card evidence.

This is finite-game regression validation, with no timing acceptance or wider
capacity claim. Historical independent mathematical replay remains separate.
"""
from argparse import ArgumentParser
from pathlib import Path
import hashlib
import json
import os
import subprocess
import traceback

from scripts.build_native_exact_four_street import TARGETS
from tests.test_native_exact_reach import authenticate
from tests.virtual_frozen_run_control import run_bounded_dyadic_probe
from tests.virtual_dyadic_sweep_capture import sweep_stream_contract

ROOT = Path(__file__).resolve().parents[1]
PREFIX = "benchmarks/results/native-dyadic-"
WIRE_BYTES = 50_507_464
RETAINED_BYTES = 3_103_848
IMAGE_BYTES = 23_701_776
# Complete streamed bytes, including resource footer, from the preserved studies.
EXPECTED_WIRES = {
    "virtual-dyadic-training":
        "7fde396c4c2e645087d9fd8abdc373a97a485265bf157e537e3cfd181c538945",
    "virtual-dyadic-training-staged-pages":
        "bc0496571953a80fd6b1a0f321ed903e11691c5ae5328ed532853ded264ffa49",
    "virtual-dyadic-training-terminal-buffer":
        "bc0496571953a80fd6b1a0f321ed903e11691c5ae5328ed532853ded264ffa49",
    "virtual-dyadic-training-allin-reach":
        "d00004c1f2dc2a87efacc52d9b08cfe7c0c5f0bf4e2bd81b95bdafc524704ead",
    "virtual-dyadic-training-mixed-policy-cache":
        "ab27fc16c9321108806c1cc7e0061ed34459381795bedd2026d697fee91379a7",
    "virtual-dyadic-training-factored-average":
        "52bb0aece041eb99aa2dbcb37b28e43e2725d4e8cfc5d3d112a1b22272458da3",
}
FIRST_IMAGE = "b9b1f88d1ed333908e3b49aec481ebe394e02a5f01281370eba4eafe6295f14a"
SECOND_IMAGE = "fba2b68d8bfb1a4d624d626794e1917c2527a79fc2ee413029205796eb85923e"
SIDECARS = {
    "compact-wire.json", "equal-quantizer.json", "factored-execution.json",
    "page-images-rows/rows.bin", "page-images-rows/rows.json",
    "page-images/committed.bin", "page-images/staged.bin",
    "page-images/policy.bin", "page-images/policy.json",
    "page-images/quantizer.json", "page-images/rank-index.json",
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_once(path, record):
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(record, indent=2, sort_keys=True) + "\n")


def verify_observation(record, target):
    require(target in EXPECTED_WIRES, "unknown study target")
    require(record.get("status") == "exited" and
            record.get("actual_exit_observed") is True and
            type(record.get("returncode")) is int and record["returncode"] == 0 and
            record.get("failures") == [] and
            type(record.get("automatic_retries")) is int and
            record["automatic_retries"] == 0, "native process did not exit cleanly")
    streams = record.get("streams")
    require(type(streams) is list and len(streams) == 2, "missing bounded streams")
    stdout, stderr = streams
    require(type(stdout.get("observed_bytes")) is int and
            stdout["observed_bytes"] == WIRE_BYTES and
            type(stdout.get("saved_bytes")) is int and
            stdout["saved_bytes"] == RETAINED_BYTES and
            stdout.get("wire_sha256") == EXPECTED_WIRES[target],
            "complete historical training wire differs")
    require(type(stderr.get("observed_bytes")) is int and
            type(stderr.get("saved_bytes")) is int and
            stderr["observed_bytes"] == stderr["saved_bytes"] == 0,
            "native stderr was not empty")
    capture = record.get("sweep_capture")
    require(type(capture) is dict, "missing checkpoint stream proof")
    require(capture.get("contract") == sweep_stream_contract(compact_wire=True) and
            capture.get("wire_sha256") == stdout["wire_sha256"] and
            capture.get("retained_sha256") == stdout.get("sha256"),
            "checkpoint transport receipts disagree")
    frames = capture.get("frames")
    expected = [
        {"sweep": 1, "slot": 1, "bytes": IMAGE_BYTES, "sha256": FIRST_IMAGE},
        {"sweep": 2, "slot": 0, "bytes": IMAGE_BYTES, "sha256": SECOND_IMAGE},
    ]
    require(frames == expected and all(
        type(frame[key]) is int for frame in frames for key in ("sweep", "slot", "bytes")),
        "streamed checkpoint identity differs")
    return {"target": target, "complete_wire_sha256": stdout["wire_sha256"],
            "wire_bytes": WIRE_BYTES, "checkpoint_frames": frames}


def git_identity():
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    require(not subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT),
            "study checks require clean committed source")
    return head


def run(builds, output):
    builds, output = builds.resolve(), output.resolve()
    require(not output.is_relative_to(ROOT) and not builds.is_relative_to(ROOT),
            "native builds and captures must be external to source")
    head = git_identity()
    protocol = json.loads((ROOT / (PREFIX + "staged-pages-v1/protocol.json")).read_bytes())
    sidecars = protocol["stable_sidecars"]
    require(type(sidecars) is dict and set(sidecars) == SIDECARS,
            "preserved sidecar inventory differs")
    executables = {
        target: builds / target / (TARGETS[target][0] + (".exe" if os.name == "nt" else ""))
        for target in EXPECTED_WIRES
    }
    identities = {target: authenticate(exe, ROOT, target) for target, exe in executables.items()}
    baseline_sources = identities["virtual-dyadic-training"][1]["source_sha256"]
    require(all(identity[1]["source_sha256"] == baseline_sources
                for identity in identities.values()), "study builds used different source bytes")
    output.mkdir()
    write_once(output / "source.json", {
        "head": head, "operator_sha256": sha(__file__),
        "build_manifest_sha256": {
            target: hashlib.sha256(identity[0]).hexdigest()
            for target, identity in identities.items()
        },
        "scope": "six complete fixed ten-card T2 regression calls; no timing gate",
    })
    results = []
    try:
        for target, exe in executables.items():
            case = output / target
            record = run_bounded_dyadic_probe(
                [str(exe), str(case / "page-images")], "TRAIN_TEN_BOUNDED_DIVISION", case)
            result = verify_observation(record, target)
            expected = dict(sidecars)
            if target == "virtual-dyadic-training-mixed-policy-cache":
                expected["page-images/quantizer.json"] = hashlib.sha256(
                    b'{"combined_divisions":33795}\n').hexdigest()
                require(json.loads((case / "mixed-policy-cache.json").read_bytes()) ==
                        {"hits": 24119, "misses": 21231, "divisions": 33795},
                        "independently predicted mixed cache census differs")
            require(all(sha(case / name) == digest for name, digest in expected.items()),
                    "historical checkpoint, policy, row or arithmetic sidecar differs")
            if target != "virtual-dyadic-training":
                require(json.loads((case / "page-images/paging.json").read_bytes()) ==
                        protocol["expected_candidate_pager"], "staged-page schedule differs")
            require(sha(case / "stdout.bin") == record["streams"][0]["sha256"],
                    "saved numerical capture drift")
            result["historical_owner_sidecars_equal"] = True
            write_once(case / "verified.json", result)
            results.append(result)
            print(json.dumps({"target": target, "verified": True}), flush=True)
        require(git_identity() == head, "committed source changed during checks")
        require(all(authenticate(executables[target], ROOT, target) == identity
                    for target, identity in identities.items()), "source or executable drift")
        write_once(output / "verified.json", {
            "status": "complete", "source_head": head, "cases": results,
            "new_quality_claim": False, "new_capacity_claim": False,
        })
    except BaseException as error:
        write_once(output / "failure.json", {
            "status": "failed", "error_type": type(error).__name__,
            "error": str(error), "completed_targets": [r["target"] for r in results],
            "traceback": traceback.format_exc(), "automatic_retries": 0,
        })
        raise


if __name__ == "__main__":
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--builds", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.builds, args.output)
