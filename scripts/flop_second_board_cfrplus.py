"""Research-only CFR+ adapter for the proved fixed second-flop game."""
from fractions import Fraction
import hashlib
from itertools import islice
import math
import platform
from pathlib import Path
import traceback

from pokerlab import cfr_plus
from scripts import benchmark_flop_second_board_equivalence as evidence
from scripts import flop_second_board_cfrplus_budget as budget
from scripts import flop_second_board_equivalence as proof
from scripts import flop_class_policy as policy
from scripts import verify_flop_second_board_equivalence_publication as publication


ROOT = Path(__file__).resolve().parents[1]
ADAPTER = "fixed-second-board-cfrplus-v1"
MAX_SOURCE_BYTES = evidence.MAX_SOURCE_BYTES
MAX_ROWS = 608
_EXTRA = (
    ("scripts/verify_flop_second_board_equivalence_publication.py",
     ROOT / "scripts/verify_flop_second_board_equivalence_publication.py"),
    ("scripts/flop_second_board_cfrplus_budget.py", ROOT / "scripts/flop_second_board_cfrplus_budget.py"),
    ("scripts/flop_second_board_cfrplus.py", ROOT / "scripts/flop_second_board_cfrplus.py"),
    ("scripts/benchmark_flop_second_board_cfrplus.py", ROOT / "scripts/benchmark_flop_second_board_cfrplus.py"),
    ("benchmarks/flop-second-board-cfrplus-pilot-v1.json",
     ROOT / "benchmarks/flop-second-board-cfrplus-pilot-v1.json"),
)


def _need(condition, message):
    if not condition:
        raise ValueError(message)


def admit_request(iterations=560):
    """Admit before saved authentication, model preparation, or training."""
    forecast = budget.admit_second_board_request(iterations)
    _need(type(forecast) is dict and type(forecast.get("total_admitted_work")) is int,
          "Second-board logical-work admission differs")
    forecast = dict(forecast)
    forecast["fixed_proof_preparation_census"] = {
        "physical_oracle_builds": 1, "physical_world_rows": 5940,
        "maximum_live_physical_oracles": 1, "physical_public_states": 30812,
        "compact_worlds": 170, "compact_public_states": 1270,
        "compact_policy_rows": 608, "physical_policy_rows": 16912,
        "interpretation": (
            "Separate fixed model census only; not added CPU, arithmetic, memory, or RSS bounds.")}
    return forecast


def _source_snapshot():
    state = evidence._snapshot()
    hashes = dict(state["source_lf_sha256"])
    _need(len(hashes) == 49, "Inherited second-board source inventory differs")
    for relative, path in _EXTRA:
        try:
            if path.stat().st_size > MAX_SOURCE_BYTES:
                raise ValueError(f"Named source exceeds bound: {relative}")
            with path.open("rb") as stream:
                raw = stream.read(MAX_SOURCE_BYTES + 1)
        except OSError as exc:
            raise ValueError(f"Cannot read bounded source: {relative}") from exc
        _need(len(raw) <= MAX_SOURCE_BYTES, f"Named source exceeds bound: {relative}")
        hashes[relative] = hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest()
    _need(len(hashes) == 54 and state.get("status") == "",
          "Second-board source inventory is dirty or incomplete")
    return {**state, "source_lf_sha256": dict(sorted(hashes.items()))}


def source_hashes():
    return dict(_source_snapshot()["source_lf_sha256"])


def _node_key(node, world):
    return node.player, world[node.player], node.history


def _chance_child(node, world):
    if isinstance(node, proof.physical._Chance):
        return node.branches[world[4][node.card_index]]
    return None


def _terminal_value(node, world):
    sign = (1 if node.winner == 0 else -1) if node.kind == "fold" else world[3]
    return float(sign * (Fraction(5) + min(Fraction(v) for v in node.contributions)))


def _training_inputs(model):
    census = proof.validate_model(model)
    infos = {key: len(node.actions) for key, node in proof._class_rows(model).items()}
    _need(len(infos) == MAX_ROWS and sum(k[0] == 0 for k in infos) == 304 and
          sum(k[0] == 1 for k in infos) == 304 and
          all(type(count) is int and count == 2 for count in infos.values()),
          "Second-board compact information rows differ")
    for key in infos:
        policy._validate_key(key)
    _need(type(model.worlds) is tuple and len(model.worlds) == budget.WORLD_COUNT and
          all(type(w) is tuple and len(w) == 5 and type(w[2]) is Fraction and w[2] > 0
              for w in model.worlds) and
          sum((w[2] for w in model.worlds), Fraction()) == 1,
          "Second-board joint masses are not exact positive probabilities")
    worlds = tuple((w[0], w[1], float(w[2]), w[3], w[4]) for w in model.worlds)
    _need(all(math.isfinite(w[2]) and w[2] > 0 for w in worlds) and
          math.isclose(math.fsum(w[2] for w in worlds), 1.0, rel_tol=1e-12, abs_tol=1e-12),
          "Binary64 conversion loses support or joint normalization")
    max_visits = 0
    for world in worlds:
        pending, visits = [model.root], 0
        while pending:
            node = pending.pop()
            visits += 1
            _need(visits <= budget.MAX_WORLD_VISITS, "Per-world path exceeds admission")
            child = _chance_child(node, world)
            if child is not None:
                pending.append(child)
            elif isinstance(node, proof.physical._Decision):
                _need(_node_key(node, world) in infos, "Decision exposes a missing own-hand key")
                pending.extend(node.children)
        max_visits = max(max_visits, visits)
    budget.validate_observed_dimensions(census, max_visits, infos,
                                         require_compact_tree_hash=True)
    return worlds, infos, max_visits


def canonicalize_binary_rows(raw_rows):
    """Normalize two bounded 304-row batches without changing the shared helper."""
    _need(type(raw_rows) is dict and len(raw_rows) == MAX_ROWS,
          "Trainer must return exactly 608 policy rows")
    for key, values in raw_rows.items():
        policy._validate_key(key)
        _need(type(key) is tuple and len(key) == 3 and type(key[0]) is int and
              key[0] in (0, 1) and type(key[1]) is str and type(key[2]) is tuple and
              type(values) in (tuple, list) and len(values) == 2 and
              all(type(v) is float and math.isfinite(v) and 0 <= v <= 1 for v in values),
              "Raw second-board policy row is malformed")
    batches = {0: {}, 1: {}}
    for key, values in raw_rows.items():
        batches[key[0]][key] = values
    _need(len(batches[0]) == len(batches[1]) == 304,
          "Second-board raw policy split must be 304 rows per player")
    rows, audits = {}, []
    for player in (0, 1):
        canonical, audit = policy.canonicalize_binary_rows(batches[player])
        rows.update(canonical)
        audits.append(audit)
    max_norm = max(Fraction(a["max_normalized_probability_distance"]) for a in audits)
    max_raw = max(Fraction(a["max_raw_distance"]) for a in audits)
    return rows, {"rows_changed": sum(a["rows_changed"] for a in audits),
                  "max_normalized_probability_distance": str(max_norm),
                  "max_raw_distance": str(max_raw),
                  "zeroed_positive_probabilities": sum(a["zeroed_positive_probabilities"] for a in audits),
                  "grid_bits": policy.GRID_BITS, "normalizer_batches": 2,
                  "rows_per_batch": [304, 304]}


def _guard_receipt(calls):
    keys = publication.AUTHORITY_KEYS
    _need(type(keys) is frozenset and len(keys) == 41 and type(calls) is dict and
          set(calls) == set(keys) and
          all(type(k) is str and type(v) is int and v == 0 for k, v in calls.items()),
          "Independent authority inventory is incomplete or nonzero")
    return dict(sorted(calls.items()))


def _secondary(primary, other, attribute):
    if primary is not None:
        try:
            setattr(primary, attribute, f"{type(other).__name__}: {other}")
        except Exception:
            pass


def _policy_record(raw):
    """Boundedly retain JSON-safe trainer rows even when their schema is bad."""
    if type(raw) is not dict:
        return {"malformed_container_type": type(raw).__name__}
    result = []
    for key, values in islice(raw.items(), MAX_ROWS):
        if type(key) is tuple and len(key) == 3:
            key_record = [key[0], key[1], list(key[2]) if type(key[2]) is tuple else repr(key[2])[:256]]
        else:
            key_record = repr(key)[:256]
        if type(values) in (tuple, list) and len(values) <= 4:
            value_record = [
                (repr(value)[:128] if type(value) is float and not math.isfinite(value)
                 else value if type(value) in (str, int, float, bool) or value is None
                 else repr(value)[:128]) for value in values]
        else:
            value_record = repr(values)[:256]
        result.append([key_record, value_record])
    if len(raw) > MAX_ROWS:
        return {"retained_prefix": result, "retained_rows": MAX_ROWS,
                "reported_rows": len(raw), "complete_policy_retained": False}
    return result


def _cleanup_validate(model, observation, calls_key):
    calls, error = {}, None
    try:
        with proof.shared.independent_guard() as calls:
            try:
                observation["validation_attempts"] += 1
                proof.validate_model(model)
                observation["final_model_validation"] = "passed"
            except BaseException as exc:
                error = exc
                observation["final_model_validation"] = "failed"
                observation["cleanup_error"] = f"{type(exc).__name__}: {exc}"
    except BaseException as exc:
        if error is None:
            error = exc
        else:
            _secondary(error, exc, "second_board_cleanup_guard_error")
    try:
        observation[calls_key] = _guard_receipt(calls)
    except BaseException as exc:
        observation[calls_key] = dict(calls)
        observation["cleanup_guard_error"] = f"{type(exc).__name__}: {exc}"
        if error is None:
            error = exc
        else:
            _secondary(error, exc, "second_board_cleanup_receipt_error")
    return error


def solve_second_board(iterations=560, *, observation=None):
    """Train exactly once, retaining raw output and auditing its physical lift."""
    if observation is None:
        observation = {}
    _need(type(observation) is dict, "Observation must be an exact dict")
    observation.clear()
    observation.update(status="running", phase="admission", training_calls=0,
                       validation_attempts=0, primary_error=None, cleanup_error=None)
    before, model = None, None
    model_returned, final_validation_attempted = False, False
    source_after_attempted = False
    try:
        admission = admit_request(iterations)
        observation["admission"] = admission
        before = _source_snapshot()
        observation.update(source_before=before, phase="preparation")
        proof_receipt = publication.verify()
        observation["saved_equivalence_receipt"] = proof_receipt
        calls, first, progress, model = {}, None, {}, None
        try:
            with proof.shared.independent_guard() as calls:
                try:
                    model = proof.build_model(progress=progress)
                    model_returned = model is not None
                    observation["preparation_progress"] = dict(progress)
                    observation["phase"] = "pretraining-model-validation"
                    observation["validation_attempts"] += 1
                    worlds, infos, max_visits = _training_inputs(model)
                    observation.update(census=dict(model.census), training_worlds=len(worlds),
                                       information_rows=len(infos), maximum_world_path_states=max_visits)
                except BaseException as exc:
                    first = exc
                    observation["primary_error"] = f"{type(exc).__name__}: {exc}"
                    observation["preparation_traceback"] = traceback.format_exc()
        except BaseException as exc:
            if first is None:
                first = exc
            else:
                _secondary(first, exc, "second_board_preparation_guard_error")
            observation["preparation_guard_error"] = f"{type(exc).__name__}: {exc}"
        observation["preparation_progress"] = dict(progress)
        try:
            observation["preparation_forbidden_calls"] = _guard_receipt(calls)
        except BaseException as exc:
            observation["preparation_forbidden_calls"] = dict(calls)
            observation["preparation_guard_error"] = f"{type(exc).__name__}: {exc}"
            if first is None:
                first = exc
            else:
                _secondary(first, exc, "preparation_guard_error")
        if first is not None:
            if model_returned:
                final_validation_attempted = True
                cleanup = _cleanup_validate(model, observation, "diagnostic_forbidden_calls")
                if cleanup is not None:
                    _secondary(first, cleanup, "second_board_cleanup_error")
            raise first

        post_training_error = None
        raw_rows = rows = normalization = None
        try:
            observation["phase"] = "cfrplus-training"
            observation["training_calls"] += 1
            raw_rows = cfr_plus.train(model.root, worlds, infos, iterations,
                                      terminal_value=_terminal_value, node_key=_node_key,
                                      chance_child=_chance_child, delay=0)
            observation["raw_class_policy"] = _policy_record(raw_rows)
            _need(type(raw_rows) is dict and set(raw_rows) == set(infos),
                  "Trainer output omits or adds an information set")
            rows, normalization = canonicalize_binary_rows(raw_rows)
            observation.update(
                class_policy=[[p, h, list(history), list(v)]
                              for (p, h, history), v in sorted(rows.items())],
                normalization=normalization)
        except BaseException as exc:
            post_training_error = exc
            observation["primary_error"] = f"{type(exc).__name__}: {exc}"
            observation["training_traceback"] = traceback.format_exc()

        diag_calls, diag_error, payload, audit = {}, None, None, None
        try:
            with proof.shared.independent_guard() as diag_calls:
                try:
                    if post_training_error is not None:
                        raise post_training_error
                    observation["phase"] = "exact-metrics-and-lift"
                    compact = proof.shared._exact_metrics(model.root, model.worlds, rows)
                    observation["exact_compact_metrics"] = (
                        {k: str(v) for k, v in compact.items()} if type(compact) is dict
                        else {"malformed_type": type(compact).__name__})
                    _need(type(compact) is dict and set(compact) == set(proof.METRICS) and
                          all(type(value) is Fraction for value in compact.values()),
                          "Compact exact metric inventory differs")
                    payload = proof._lift(rows, model, compact)
                    payload.update(algorithm="cfrplus", iterations=iterations,
                                   research_adapter=ADAPTER, averaging_delay=0)
                    observation["physical_policy"] = payload
                    observation["phase"] = "lift-project-and-physical-responses"
                    projected, physical_rows = proof._project(payload, model)
                    _need(proof.shared._typed(projected) == proof.shared._typed(rows),
                          "Lift/project changed the output policy")
                    physical_exact = proof.shared._exact_metrics(
                        model.physical["root"], model.physical["worlds"], physical_rows)
                    observation["exact_physical_metrics"] = (
                        {k: str(v) for k, v in physical_exact.items()}
                        if type(physical_exact) is dict else
                        {"malformed_type": type(physical_exact).__name__})
                    _need(type(physical_exact) is dict and set(physical_exact) == set(proof.METRICS) and
                          all(type(value) is Fraction for value in physical_exact.values()),
                          "Physical exact metric inventory differs")
                    _need(compact == physical_exact,
                          "Compact and unrestricted physical exact metrics differ")
                    observation["phase"] = "independent-numeric-replay"
                    numeric = proof.physical.replay(payload, model.physical)
                    _need(type(numeric) is dict and set(numeric) == set(proof.METRICS),
                          "Numeric replay metric inventory differs")
                    _need(all(type(value) is float and math.isfinite(value)
                              for value in numeric.values()),
                          "Numeric replay values must be finite floats")
                    gaps = {key: abs(float(physical_exact[key]) - numeric[key])
                            for key in proof.METRICS}
                    gap = max(gaps.values())
                    _need(all(math.isfinite(v) for v in numeric.values()) and
                          math.isfinite(gap) and gap <= 1e-10,
                          "Numeric physical replay differs")
                    class_policy = [[p, hand, list(history), list(values)]
                                    for (p, hand, history), values in sorted(rows.items())]
                    audit = {"exact_metrics": {k: str(v) for k, v in physical_exact.items()},
                             "numeric_metrics": {k: numeric[k] for k in proof.METRICS},
                             "maximum_numeric_gap": gap, "exact_metric_count": len(proof.METRICS),
                             "physical_rows_lifted": len(physical_rows), "class_rows": len(rows),
                             "physical_strategy_sha256": proof._digest(payload["strategy"]),
                             "class_policy": class_policy}
                    observation["audit"] = audit
                except BaseException as exc:
                    diag_error = exc
                    observation["primary_error"] = f"{type(exc).__name__}: {exc}"
                    observation["diagnostic_traceback"] = traceback.format_exc()
                finally:
                    try:
                        observation["phase"] = "final-model-validation"
                        observation["validation_attempts"] += 1
                        final_validation_attempted = True
                        proof.validate_model(model)
                        observation["final_model_validation"] = "passed"
                    except BaseException as exc:
                        observation["final_model_validation"] = "failed"
                        observation["cleanup_error"] = f"{type(exc).__name__}: {exc}"
                        if diag_error is None:
                            diag_error = exc
                        else:
                            _secondary(diag_error, exc, "second_board_cleanup_error")
        except BaseException as exc:
            observation["diagnostic_guard_error"] = f"{type(exc).__name__}: {exc}"
            if diag_error is None:
                diag_error = exc
            else:
                _secondary(diag_error, exc, "second_board_diagnostic_guard_error")
        try:
            observation["diagnostic_forbidden_calls"] = _guard_receipt(diag_calls)
        except BaseException as exc:
            observation["diagnostic_forbidden_calls"] = dict(diag_calls)
            observation["diagnostic_guard_error"] = f"{type(exc).__name__}: {exc}"
            if diag_error is None:
                diag_error = exc
            else:
                _secondary(diag_error, exc, "second_board_diagnostic_guard_error")
        if diag_error is not None:
            raise diag_error

        _need(len(rows) == budget.INFO_ROWS and len(payload["strategy"]) == budget.PHYSICAL_POLICY_ROWS and
              audit["exact_metric_count"] == 8, "Second-board audit dimensions differ")
        nash = Fraction(audit["exact_metrics"]["nash_conv"])
        _need(nash >= 0, "Exact NashConv must be nonnegative")
        source_after_attempted = True
        try:
            after = _source_snapshot()
        except BaseException as source_error:
            observation["source_after_error"] = f"{type(source_error).__name__}: {source_error}"
            raise
        observation["source_after"] = after
        _need(before["revision"] == after["revision"] and before["status"] == after["status"] == "" and
              before["source_lf_sha256"] == after["source_lf_sha256"],
              "Source changed during second-board solve")
        report = {"schema_version": ADAPTER, "status": "trained-policy-physically-verified",
                  "source_revision": before["revision"], "source_lf_sha256": before["source_lf_sha256"],
                  "proof_receipt": proof_receipt,
                  "reference_receipt": progress.get("prerequisite"),
                  "runtime": {"python": platform.python_version(),
                              "implementation": platform.python_implementation()},
                  "admission": admission, "preparation_progress": dict(progress),
                  "maximum_world_path_states": max_visits, "census": dict(model.census),
                  "physical_worlds_sha256": proof._digest(
                      [[w[0], w[1], w[2].numerator, w[2].denominator, w[3], list(w[4])]
                       for w in model.physical["worlds"]]),
                  "normalization": normalization,
                  "raw_class_policy": [[p, h, list(hist), list(v)]
                                       for (p, h, hist), v in sorted(raw_rows.items())],
                  "class_policy": [[p, h, list(hist), list(v)]
                                   for (p, h, hist), v in sorted(rows.items())],
                  "physical_policy": payload, "audit": audit,
                  "preparation_forbidden_calls": observation["preparation_forbidden_calls"],
                  "diagnostic_forbidden_calls": observation["diagnostic_forbidden_calls"],
                  "training_calls": observation["training_calls"], "quality_target": 0.005,
                  "quality_target_met": nash <= Fraction(1, 200),
                  "scope": ("One finite fixed 7c8d9h second-board game. Output policy is checked against "
                            "unrestricted physical own-hand responses; no broader-game, speed, or memory claim.")}
        report["artifact_sha256"] = proof._digest(report)
        observation.update(status="complete", phase="complete", source_after=after, report=report)
        return report
    except BaseException as exc:
        observation["status"] = "error"
        observation["primary_error"] = observation.get("primary_error") or f"{type(exc).__name__}: {exc}"
        observation.setdefault("traceback", traceback.format_exc())
        if model_returned and not final_validation_attempted:
            final_validation_attempted = True
            cleanup = _cleanup_validate(model, observation, "diagnostic_forbidden_calls")
            if cleanup is not None:
                _secondary(exc, cleanup, "second_board_cleanup_error")
        if before is not None and not source_after_attempted:
            source_after_attempted = True
            try:
                after = _source_snapshot()
                observation["source_after"] = after
                _need(before["revision"] == after["revision"] and
                      before["status"] == after["status"] == "" and
                      before["source_lf_sha256"] == after["source_lf_sha256"],
                      "Source changed during failed second-board solve")
            except BaseException as source_error:
                observation["source_after_error"] = f"{type(source_error).__name__}: {source_error}"
                _secondary(exc, source_error, "second_board_source_after_error")
        raise
