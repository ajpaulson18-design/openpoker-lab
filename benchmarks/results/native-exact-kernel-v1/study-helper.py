"""Fixed native exact vector evidence plus a separate zero-candidate saved replay.

External artifacts only. Authenticate full frozen source/build before importing
the explicitly authorized physical Fraction/best-five oracle. No training,
production rank/kernel or policy quality claim is made.
"""
import argparse
from contextlib import contextmanager, ExitStack
from fractions import Fraction
import hashlib
import importlib.abc
import importlib.util
import json
import math
from pathlib import Path
import platform
import random
import struct
import subprocess
import sys
from unittest.mock import patch
import zipfile

FROZEN = "204a1c3b1fa4ae22ecb93a04795324e5ede2d3bc"
AUTH_SHA = "8171ead3ba108f8200f15e85696f40d109ed894209fa7d77598780b83c1401c5"
BUILD_SHA = "f5fe6c85aed9fb747842a50252cee8eac60c9fa786253659f755788c93505737"
EXE_SHA = "13f559659fd9328884e2cec1098179e2b8b1df76449577bf30125fd7a1faa2cd"
DEP_SHA = "4d6f33341887e35a0c29e9dc5da2a326d546427940c2b16b485db0c61b042555"
ZIP_SHA = "33c422ab3ebfa9e86c62f41f372ec2b9c2cefa303f1885391aa4d8250ef2f831"
LICENSE_SHA = "c9bff75738922193e67fa726fa225535870d2aa1059f91452c411736284ad566"
DECK = tuple(rank+suit for rank in "23456789TJQKA" for suit in "cdhs")
PROTOCOL = "OPENPOKER_EXACT_SELECTED_VECTORS_V1"
LIMITS = (1326, 64, 65536, 500000000, 2000000)
COUNTERS = ("modeled_work", "retained_entries", "peak_scratch_entries", "peak_integer_bits", "rank_calls",
    "rank_cache_hits", "rank_cache_misses", "rank_cache_evictions", "conversion_calls",
    "peak_integer_payload_bits", "peak_conversion_scratch_bits")
BUILD_SOURCES = ("native/exact_binary64.hpp", "native/exact_selected_kernel.hpp", "native/exact_selected_kernel_probe.cpp",
    "scripts/build_native_exact_four_street.py", "third_party/boost-multiprecision-1.92.0/manifest.json",
    "third_party/boost-multiprecision-1.92.0/LICENSE_1_0.txt", "third_party/boost-multiprecision-1.92.0/headers.zip")
MATH_SOURCES = ("tests/test_native_exact_selected_vectors.py", "scripts/preflop_validation.py", "pokerlab/cards.py")
FORBIDDEN_MODULES = ("pokerlab.exact_selected_kernel", "pokerlab.dyadic_selected_arithmetic", "pokerlab.exact_selected_solver",
    "pokerlab.preflop_solver", "pokerlab.selected_runout_operator", "pokerlab.suit_quotient_cfr", "pokerlab.cfr")


def need(value, message):
    if not value:raise ValueError(message)


def sha(value):return hashlib.sha256(value).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False)+"\n", encoding="utf-8", newline="\n")


def git(repo, *args):return subprocess.check_output(["git", *args], cwd=repo)


def source_snapshot(repo):
    names = git(repo, "ls-files", "-z").decode().split("\0")[:-1]
    need(names and all((repo/name).is_file() and not (repo/name).is_symlink() for name in names), "nonordinary source inventory")
    return {"commit": git(repo, "rev-parse", "HEAD").decode().strip(),
        "status": git(repo, "status", "--porcelain", "--untracked-files=all").decode().strip(),
        "sha256": {name: sha((repo/name).read_bytes()) for name in names}}


def authenticate_build(repo, build_dir, source):
    manifest_raw = (build_dir/"native-exact-build-manifest.json").read_bytes()
    need(sha(manifest_raw) == BUILD_SHA, "development build manifest pin changed")
    manifest = json.loads(manifest_raw)
    need(manifest["contract"] == "native-exact-build-v1" and manifest["target"] == "kernel" and manifest["license"] == "BSL-1.0", "wrong build target/contract/license")
    expected = {name: source["sha256"][name] for name in BUILD_SOURCES}
    need(manifest["source_sha256"] == expected, "build full source keyset/hash mismatch")
    lf = {name: sha((repo/name).read_bytes().replace(b"\r\n", b"\n")) for name in BUILD_SOURCES if name.endswith((".hpp", ".cpp", ".py", ".json", ".txt"))}
    need(manifest["source_lf_sha256"] == lf, "build normalized source keyset/hash mismatch")
    need(expected["native/exact_selected_kernel.hpp"] == "9048f38e255738d82a9eb39c2d32562b06eb732590990a6612cfb4b6c87ce4bc", "unexpected kernel source")
    need(manifest["dependency_archive_sha256"] == ZIP_SHA and manifest["dependency_manifest_sha256"] == DEP_SHA and
         manifest["dependency_commit"] == "1f7acd34fe929573c131e869867dc1d12b8080b6" and manifest["dependency_headers"] == 198, "dependency build pins mismatch")
    dependency = repo/"third_party/boost-multiprecision-1.92.0"
    need(sha((dependency/"manifest.json").read_bytes()) == DEP_SHA and sha((dependency/"headers.zip").read_bytes()) == ZIP_SHA and
         sha((dependency/"LICENSE_1_0.txt").read_bytes()) == LICENSE_SHA, "pinned dependency/license changed")
    dep = json.loads((dependency/"manifest.json").read_bytes())
    need(dep["header_count"] == len(dep["headers_sha256"]) == 198, "dependency inventory changed")
    with zipfile.ZipFile(dependency/"headers.zip") as packed:
        files = {info.filename: packed.read(info) for info in packed.infolist() if not info.is_dir()}
        need(len(files) == 198 and {name: sha(raw) for name, raw in files.items()} == dep["headers_sha256"], "dependency archive closure mismatch")
        need(sum(map(len, files.values())) == dep["header_bytes"] == 3057611, "dependency byte count mismatch")
    include = build_dir/"boost-include"
    observed = {path.relative_to(include).as_posix(): sha(path.read_bytes()) for path in include.rglob("*") if path.is_file()}
    need(observed == dep["headers_sha256"], "actual build include closure mismatch")
    executable = (build_dir/"native-exact-selected-vectors.exe").resolve(strict=True)
    need(Path(manifest["executable"]).resolve() == executable and manifest["executable_sha256"] == sha(executable.read_bytes()) == EXE_SHA,
         "executable/source-build identity mismatch")
    need("/fp:strict" in manifest["flags"] and "/fp:fast" not in manifest["flags"], "unexpected floating build settings")
    return manifest, executable, {"manifest_sha256": BUILD_SHA, "executable_sha256": EXE_SHA,
        "dependency_manifest_sha256": DEP_SHA, "dependency_archive_sha256": ZIP_SHA, "actual_headers_verified": 198}


def hand(text):return tuple(text[index:index+2] for index in (0, 2))


def board(text):
    cards = tuple(text[index:index+2] for index in range(0, 10, 2))
    return tuple(sorted(cards[:3], key=DECK.index)) + cards[3:]


def schedule():
    result = []
    weighted = ([(hand("AsAh"), .7), (hand("KsKh"), .3), (hand("9s9h"), .2)],
                [(hand("AsAh"), .4), (hand("KdKc"), .6), (hand("8s8h"), .5)])
    outcomes = list(map(board, ("2c3d4h5s6c", "2c3d4h7s8c", "2c3d4h7s9c")))
    queries = []
    for mask in range(8):
        indexes = tuple(index for index in range(3) if mask & (1 << index))
        queries.extend((kind, 0, indexes, 0., ()) for kind in ("M", "S"))
        for player in (0, 1):
            queries.extend((kind, player, indexes, -1.5 if kind == "F" else 1.5, (.25, .75, 0.)) for kind in ("F", "D"))
    for cache in (1, 64):
        result.append({"id": "weighted-3x3-all-eight-subsets-cache-"+str(cache), "hands": weighted, "boards": outcomes, "queries": queries, "cache": cache})
    flush = ([(hand("AcQc"), 1.), (hand("AdQd"), .5)], [(hand("KcJc"), .75), (hand("KdJd"), 1.)])
    outcomes = list(map(board, ("2c3c7c9hTs", "2d3d7d9hTs")))
    queries = [(kind, 0, indexes, 0., ()) for indexes in ((), (0,), (1,), (0, 1)) for kind in ("M", "S")]
    queries += [(kind, player, indexes, -2.75 if kind == "F" else 2.75, (.125, .875)) for player in (0, 1)
                for indexes in ((0,), (1,), (0, 1)) for kind in ("F", "D")]
    result.append({"id": "meaningful-club-diamond-private-flush", "hands": flush, "boards": outcomes, "queries": queries, "cache": 1})
    ties = ([(hand("2c3c"), 1.), (hand("2d3d"), .5)], [(hand("2c3c"), .3), (hand("4d5d"), .7)])
    queries = [(kind, 0, (0,), 0., ()) for kind in ("M", "S")]
    queries += [(kind, player, (0,), -3. if kind == "F" else 3., (1., .5) if player == 0 else (.25, 1.)) for player in (0, 1) for kind in ("F", "D")]
    result.append({"id": "board-royal-tie-and-same-holding-addback", "hands": ties, "boards": [board("AcKcQcJcTc")], "queries": queries, "cache": 1})
    rng = random.Random(713259)
    for index in range(32):
        chosen = rng.sample(DECK, 13)
        holdings = ([(tuple(chosen[:2]), .3), (tuple(chosen[2:4]), .7)], [(tuple(chosen[4:6]), .4), (tuple(chosen[6:8]), .6)])
        selected = [tuple(sorted(chosen[8:11], key=DECK.index)) + tuple(chosen[11:13])]
        queries = [(kind, 0, (0,), 0., ()) for kind in ("M", "S")]
        queries += [(kind, player, (0,), -1.25 if kind == "F" else 1.25, (.125, .875) if player == 0 else (.25, .75))
                    for player in (0, 1) for kind in ("F", "D")]
        result.append({"id": f"seed713259-distinct-2x2-{index:02}", "hands": holdings, "boards": selected, "queries": queries, "cache": 1})
    fingerprints = [sha(json.dumps({key: value for key, value in case.items() if key not in ("id", "cache")}, sort_keys=True).encode()) for case in result[4:]]
    need(len(result) == 36 and len(set(fingerprints)) == 32, "fixed distinct seeded schedule changed")
    return result


def parse_saved_wire(raw):
    need(len(raw) <= 8 << 20 and raw.endswith(b"\n"), "invalid saved wire envelope")
    tokens = iter(raw.decode("ascii").split())
    def take():
        try:return next(tokens)
        except StopIteration as exc:raise ValueError("truncated saved input") from exc
    def nat():
        text = take();need(text.isdecimal() and len(text) <= 12, "invalid saved natural");return int(text)
    def floating():
        text = take();need(len(text) == 16 and all(c in "0123456789abcdef" for c in text), "invalid saved binary64 bits")
        value = struct.unpack(">d", bytes.fromhex(text))[0];need(math.isfinite(value), "nonfinite saved input");return value
    need(take() == PROTOCOL, "saved protocol mismatch")
    h0, h1, count, cache, nq = [nat() for _ in range(5)]
    need(0 < h0 <= 3 and 0 < h1 <= 3 and 0 < count <= 3 and 0 < nq <= 256 and cache in (1, 64), "saved study dimensions changed")
    need(tuple(nat() for _ in range(6)) == LIMITS + (1 << 30,), "saved caps changed")
    hands = []
    for length in (h0, h1):
        side = []
        for _ in range(length):
            a, b = nat(), nat();need(a < 52 and b < 52 and a != b, "invalid saved private cards")
            weight = floating();need(weight > 0, "nonpositive saved weight");side.append(((DECK[a], DECK[b]), weight))
        need(len({tuple(sorted(row[0])) for row in side}) == length, "duplicate saved holding")
        hands.append(side)
    boards = [tuple(DECK[nat()] for _ in range(5)) for _ in range(count)]
    queries = []
    for _ in range(nq):
        kind = take();player = nat();length = nat();need(kind in ("M", "S", "F", "D") and player in (0, 1) and length <= count, "invalid saved query")
        indexes = tuple(nat() for _ in range(length));need(len(set(indexes)) == len(indexes) and all(index < count for index in indexes), "invalid saved subset")
        payoff = floating() if kind in ("F", "D") else 0.
        reach = tuple(floating() for _ in range((h0, h1)[1-player])) if kind in ("F", "D") else ()
        need(all(0 <= value <= 1 for value in reach), "saved reach outside unit interval")
        queries.append((kind, player, indexes, payoff, reach))
    need(next(tokens, None) is None, "trailing saved input tokens")
    return {"hands": tuple(hands), "boards": boards, "queries": queries, "cache": cache}


class DenyProduction(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if any(fullname == name or fullname.startswith(name+".") for name in FORBIDDEN_MODULES):
            raise AssertionError("production module forbidden in oracle: "+fullname)
        return None


@contextmanager
def oracle_guard():
    guard = DenyProduction();sys.meta_path.insert(0, guard)
    try:
        with ExitStack() as stack:
            stack.enter_context(patch("subprocess.Popen", side_effect=AssertionError("process launch forbidden during oracle/saved-only replay")))
            stack.enter_context(patch("pokerlab.cards.rank_hand", side_effect=AssertionError("production rank forbidden")))
            yield
    finally:
        sys.meta_path.remove(guard)


def expected_counters(case):
    ranks = hits = misses = evictions = conversions = 0
    lru = []
    for kind, player, indexes, payoff, reach in case["queries"]:
        if kind == "M":conversions += sum(map(len, case["hands"]))
        elif kind in ("F", "D"):conversions += len(case["hands"][player])
        if kind != "D" or payoff == 0:continue
        for index in indexes:
            board_set = set(case["boards"][index])
            if not any(value and not board_set.intersection(hand) for (hand, _), value in zip(case["hands"][1-player], reach)):continue
            if index in lru:
                hits += 1;lru.remove(index)
            else:
                misses += 1
                ranks += sum(not board_set.intersection(hand) for side in case["hands"] for hand, _ in side)
                if len(lru) == case["cache"]:lru.pop(0);evictions += 1
            lru.append(index)
    return {"rank_calls": ranks, "rank_cache_hits": hits, "rank_cache_misses": misses,
        "rank_cache_evictions": evictions, "conversion_calls": conversions}


def expectation(case, oracle):
    worlds, total = oracle.physical(case["hands"], case["boards"])
    scales = []
    for side in case["hands"]:
        powers = []
        for _, weight in side:
            bits = struct.unpack(">Q", struct.pack(">d", weight))[0]
            exponent = (bits >> 52) & 2047
            powers.append(-1074 if exponent == 0 else int(exponent) - 1023 - 52)
        scales.append(min(powers))
    power = sum(scales)
    scaled = total / (Fraction(1 << power) if power >= 0 else Fraction(1, 1 << -power))
    need(scaled.denominator == 1 and scaled > 0, "oracle global integer scale is not integral/positive")
    outputs = []
    for query_index, query in enumerate(case["queries"]):
        kind, player, *_ = query
        answer = oracle.oracle(case["hands"], case["boards"], query)
        for side, values in zip((0, 1) if kind in ("M", "S") else (player,), answer):
            bits = []
            for value in values:
                result = float(value)
                need(math.isfinite(result) and (value == 0 or abs(result) >= sys.float_info.min), "positive study expected a rejected completed component")
                bits.append(f"{struct.unpack('>Q', struct.pack('>d', result))[0]:016x}")
            outputs.append({"kind": kind, "query_index": query_index, "side": side,
                "exact_fraction": [str(value) for value in values], "rounded_bits": bits,
                "support_targets": [int(value > 0) for value in values] if kind == "S" else None})
    return {"normalizer_fraction": str(total), "global_normalizer_integer_hex": format(scaled.numerator, "x"),
        "seat_weight_exponents": scales, "compatible_pair_board_occurrences": len(worlds), "vectors": outputs,
        "exact_semantic_counters": expected_counters(case)}


def check_stdout(raw, expected):
    lines = raw.decode("ascii").splitlines()
    need(lines.pop(0) == "READY\t"+PROTOCOL, "native protocol/READY mismatch")
    z = lines.pop(0).split("\t")
    need(len(z) == 4 and z[0] == "Z" and int(z[1], 16) == int(expected["global_normalizer_integer_hex"], 16) and
         list(map(int, z[2:])) == expected["seat_weight_exponents"], "exact global Z/seat scaling mismatch")
    for vector in expected["vectors"]:
        fields = lines.pop(0).split("\t")
        need(fields[:3] == [vector["kind"], str(vector["query_index"]), str(vector["side"])], "native vector tags/order mismatch")
        target = list(map(str, vector["support_targets"])) if vector["kind"] == "S" else vector["rounded_bits"]
        need(fields[3:] == target, "native full vector bit/support mismatch")
    need(len(lines) == 1, "truncated/extra native output records")
    fields = lines[0].split("\t");need(fields[0] == "COUNTS" and len(fields) == 12, "native counters schema mismatch")
    counters = dict(zip(COUNTERS, map(int, fields[1:])))
    need(all(value >= 0 for value in counters.values()), "negative native counter")
    for key, value in expected["exact_semantic_counters"].items():need(counters[key] == value, "native semantic counter mismatch: "+key)
    need(0 < counters["modeled_work"] <= 500000000 and 0 < counters["retained_entries"] <= 2000000 and
         counters["retained_entries"] + counters["peak_scratch_entries"] <= 2000000 and counters["peak_integer_bits"] <= 65536 and
         counters["peak_integer_payload_bits"] <= 1 << 30 and counters["peak_conversion_scratch_bits"] <= 65589, "native counter exceeds unchanged cap")
    return counters


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True);parser.add_argument("--build", type=Path, required=True)
    parser.add_argument("--study", type=Path, required=True)
    args = parser.parse_args();repo, build, study = args.repo.resolve(), args.build.resolve(), args.study.resolve()
    archive = study.with_suffix(".zip")
    need(not study.exists() and not archive.exists() and repo not in study.parents, "new external study/archive required; no retry")
    study.mkdir(parents=True)
    stage = "source-authentication";failure = None;records = [];saved_verification = []
    source = authenticated = build_receipt = None;candidate_calls = 0
    try:
        source = source_snapshot(repo);write(study/"source-before.json", source)
        auth_path = Path(__file__).with_name("exact-selected-independent-review.py")
        need(sha(auth_path.read_bytes()) == AUTH_SHA, "source authentication helper pin mismatch")
        spec = importlib.util.spec_from_file_location("native_kernel_frozen_auth", auth_path)
        auth = importlib.util.module_from_spec(spec);spec.loader.exec_module(auth);auth.FROZEN = FROZEN
        authenticated = auth.source_identity(repo, source)
        write(study/"source-authentication.json", authenticated)
        stage = "build-authentication"
        manifest, executable, build_receipt = authenticate_build(repo, build, source)
        (study/"development-build-manifest.json").write_bytes((build/"native-exact-build-manifest.json").read_bytes())
        (study/"study-helper.py").write_bytes(Path(__file__).read_bytes())
        (study/"source-authentication-helper.py").write_bytes(auth_path.read_bytes())
        for name in (*BUILD_SOURCES, *MATH_SOURCES):
            destination = study/"source"/name;destination.parent.mkdir(parents=True, exist_ok=True);destination.write_bytes((repo/name).read_bytes())
        # All source, dependency headers and executable authenticated BEFORE
        # the first project mathematics module import.
        sys.dont_write_bytecode = True;sys.path.insert(0, str(repo))
        from tests import test_native_exact_selected_vectors as oracle
        need(not any(name in sys.modules for name in FORBIDDEN_MODULES), "production mathematics unexpectedly imported")
        cases = schedule();write(study/"case-specifications.json", cases)
        write(study/"protocol.json", {"contract": "native-exact-kernel-fixed-vector-study-v1", "source_commit": FROZEN,
            "cases": [case["id"] for case in cases], "case_count": 36, "seed": 713259, "seeded_distinct_games": 32,
            "candidate_processes_per_case": 1, "retry_policy": "none; retain first output/status and stop first failure",
            "weighted_board_subsets": "all eight subsets, including empty and every visible-prefix subset",
            "runtime": {"python": sys.version, "platform": platform.platform()}, "limits": LIMITS,
            "integer_payload_bit_limit": 1 << 30, "build": build_receipt,
            "math_source_sha256": {name: source["sha256"][name] for name in MATH_SOURCES},
            "scope": "Native exact vectors only. No full-game training, public graph, Q storage, policy quality or performance evidence."})
        for case in cases:
            stage = "candidate-capture:"+case["id"]
            folder = study/"cases"/case["id"];folder.mkdir(parents=True)
            raw_input = oracle.wire(case["hands"], case["boards"], case["queries"], cache=case["cache"])
            (folder/"input.txt").write_bytes(raw_input)
            need(sha(executable.read_bytes()) == EXE_SHA, "candidate executable changed before invocation")
            candidate_calls += 1
            try:
                process = subprocess.run([str(executable)], input=raw_input, capture_output=True, timeout=30, check=False)
                stdout, stderr, status = process.stdout, process.stderr, {"returncode": process.returncode, "candidate_invocations": 1}
            except subprocess.TimeoutExpired as exc:
                stdout, stderr, status = exc.stdout or b"", exc.stderr or b"", {"returncode": None, "candidate_invocations": 1, "timeout": True}
            (folder/"stdout.txt").write_bytes(stdout);(folder/"stderr.txt").write_bytes(stderr);write(folder/"status.json", status)
            stage = "candidate-validate:"+case["id"]
            need(status["returncode"] == 0 and stderr == b"", "native candidate failed or emitted stderr")
            with oracle_guard():
                expected = expectation(case, oracle)
                write(folder/"expected.json", expected)
                counters = check_stdout(stdout, expected)
            record = {"case_id": case["id"], "input_sha256": sha(raw_input), "stdout_sha256": sha(stdout), "stderr_sha256": sha(stderr),
                "expected_sha256": sha((folder/"expected.json").read_bytes()), "queries": len(case["queries"]), "vector_records": len(expected["vectors"]),
                "counters": counters, "all_bits_support_Z_scales_match": True}
            records.append(record);print(case["id"]+" captured and matched", flush=True)
        stage = "source-before-saved-only-replay"
        need(source_snapshot(repo) == source and auth.source_identity(repo, source) == authenticated, "source changed before saved replay")
        need(authenticate_build(repo, build, source)[2] == build_receipt, "build changed before saved replay")
        # A separate pass re-parses saved raw inputs independently, rebuilds
        # physical Fractions/ranks, and checks outputs with Popen forbidden.
        stage = "saved-only-verification"
        saved_hashes = {path.relative_to(study).as_posix(): sha(path.read_bytes()) for path in study.rglob("*") if path.is_file()}
        with oracle_guard():
            need(json.loads((study/"case-specifications.json").read_bytes()) == json.loads(json.dumps(schedule())), "saved case specifications changed")
            for case in schedule():
                folder = study/"cases"/case["id"]
                parsed = parse_saved_wire((folder/"input.txt").read_bytes())
                need(json.loads(json.dumps(parsed)) == json.loads(json.dumps({key: case[key] for key in ("hands", "boards", "queries", "cache")})), "saved raw input differs from original fixed case")
                expected = expectation(parsed, oracle)
                need(expected == json.loads((folder/"expected.json").read_bytes()), "fresh saved-only physical exact targets differ")
                need(json.loads((folder/"status.json").read_bytes()) == {"returncode": 0, "candidate_invocations": 1} and
                     (folder/"stderr.txt").read_bytes() == b"", "saved candidate status/stderr changed")
                counters = check_stdout((folder/"stdout.txt").read_bytes(), expected)
                saved_verification.append({"case_id": case["id"], "fresh_exact_vectors": len(expected["vectors"]), "counters": counters,
                    "all_saved_inputs_exact_targets_bits_support_Z_scales_match": True, "candidate_invocations": 0})
        need(saved_hashes == {path.relative_to(study).as_posix(): sha(path.read_bytes()) for path in study.rglob("*") if path.is_file()}, "proof artifacts changed during saved-only replay")
        write(study/"saved-only-verification.json", {"outcome": "passed", "candidate_invocations": 0, "production_kernel_rank_training_calls": 0,
            "cases": saved_verification, "inputs_independently_parsed": True, "fresh_physical_fraction_best_five_replay": True})
        stage = "final-authentication"
        need(source_snapshot(repo) == source and auth.source_identity(repo, source) == authenticated, "source changed after saved replay")
        need(authenticate_build(repo, build, source)[2] == build_receipt, "build changed after saved replay")
        write(study/"source-after.json", source)
    except BaseException as exc:
        failure = {"stage": stage, "error_type": type(exc).__name__, "error": str(exc)}
        write(study/"first-failure.json", failure)
    report = {"outcome": "complete" if failure is None else "failed", "source_commit": FROZEN, "failure": failure,
        "candidate_invocations": candidate_calls, "case_count_completed": len(records), "records": records,
        "saved_only_recomputed_cases": len(saved_verification), "saved_only_candidate_invocations": 0,
        "production_kernel_rank_training_calls_during_oracle": 0, "build": build_receipt,
        "source_files_authenticated": None if authenticated is None else authenticated["files"],
        "study_helper_sha256": sha(Path(__file__).read_bytes()),
        "scope": "Kernel vector conformance only, independent literal Fraction and best-five expectations. No whole solver, Q training, quality result or speed claim.",
        "counter_scope": "Rank-call/LRU/conversion counts independently derived from fixed queries; work/entry/bit/payload counters checked against published caps, not independent allocator/CPU bounds. Probe omits query/boards/integer-operation counters; no missing counter is inferred."}
    write(study/"receipt.json", report)
    files = sorted(path for path in study.rglob("*") if path.is_file())
    write(study/"manifest.json", {"source_commit": FROZEN, "sha256": {path.relative_to(study).as_posix(): sha(path.read_bytes()) for path in files}})
    if failure is None:
        with zipfile.ZipFile(archive, "x", zipfile.ZIP_DEFLATED, compresslevel=9) as packed:
            for path in [*files, study/"manifest.json"]:packed.writestr(path.relative_to(study).as_posix(), path.read_bytes())
        print(json.dumps({"outcome": "complete", "receipt_sha256": sha((study/"receipt.json").read_bytes()),
            "manifest_sha256": sha((study/"manifest.json").read_bytes()), "archive_sha256": sha(archive.read_bytes()),
            "archive_bytes": archive.stat().st_size, "candidate_invocations": candidate_calls, "saved_only_cases": len(saved_verification)}), flush=True)
    else:
        print(json.dumps(report), flush=True)
    return 0 if failure is None else 1


if __name__ == "__main__":
    raise SystemExit(main())
