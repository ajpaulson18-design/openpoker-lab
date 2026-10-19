"""Research-only same-run CFR+ prefix capture for a fixed raised turn game."""
from copy import deepcopy
import time
from unittest.mock import patch


from pokerlab import matrix_free_turn, postflop_solver
from pokerlab.cards import cards, expand_range
from scripts.benchmark_turn_river_independent import solve
from scripts.full_deck_raised_fixture import FIXTURE as BASE_FIXTURE
from scripts.turn_river_validation import compare_result, replay_policy


FIXTURE = {**BASE_FIXTURE, "river_config": deepcopy(BASE_FIXTURE["config"])}
METRICS = (
    "value_oop", "value_ip", "oop_best_response_value", "ip_best_response_value",
    "oop_best_response_gain", "ip_best_response_gain", "nash_conv", "exploitability",
)


def _copy_snapshot(profile, keys, infos):
    if set(profile) != set(keys):
        raise ValueError("Checkpoint information-set keys changed")
    snapshot = {}
    for key in keys:
        row = profile[key]
        if len(row) != infos[key]:
            raise ValueError("Checkpoint action count changed")
        snapshot[key] = tuple(row)
    return snapshot


def _make_observer(original, backend, discard, total, interval, snapshots, callbacks, calls):
    info_position = 2 if backend == "materialized" else 1

    def observe(*args, **kwargs):
        calls[0] += 1
        if calls[0] != 1:
            raise ValueError("Expected exactly one fixed CFR+ trainer call")
        if (kwargs.get("checkpoint_interval") is not None or
                kwargs.get("checkpoint_callback") is not None):
            raise ValueError("Existing target/checkpoint mode is not observational capture")
        if len(args) <= info_position + 2:
            raise ValueError("Unexpected trainer call shape")
        if args[info_position + 1] != total or args[info_position + 2] != "cfrplus":
            raise ValueError("Unexpected trainer iteration budget or algorithm")
        infos = args[info_position]
        keys = tuple(sorted(infos))

        def checkpoint(iteration, profile):
            callbacks.append(iteration)
            if iteration in snapshots:
                raise ValueError("Duplicate requested checkpoint")
            if iteration in (discard, total):
                snapshots[iteration] = _copy_snapshot(profile, keys, infos)
            return False

        kwargs["checkpoint_interval"] = interval
        kwargs["checkpoint_callback"] = checkpoint
        return original(*args, **kwargs)

    return observe


def _case(case):
    if type(case) is not dict or case != FIXTURE:
        raise ValueError("Capture supports only the frozen full-deck raised-turn fixture")
    return deepcopy(FIXTURE)


def _replay(result, case):
    # No runouts parameter: all legal remaining river cards stay in the game.
    return replay_policy(
        result, case["oop"], case["ip"], board=case["board"],
        config=case["config"], river_config=case["river_config"],
    )


def _derived_prefix(full, discard, total):
    prefix = deepcopy(full)
    prefix["solver_version"] = "research-raised-turn-prefix-v1"
    prefix["source_solver_version"] = full.get("solver_version")
    prefix["method"] = "Same-run completed-sweep CFR+ prefix average"
    prefix["diagnostic_provenance"] = "Independent numeric-rule replay and legal BR"
    prefix["source_requested_iterations"] = total
    prefix["source_iteration_window"] = [1, discard]
    prefix["averaged_sweeps"] = discard
    prefix["iterations"] = discard
    prefix["average_schedule"] = "linear-prefix-own-reach"
    prefix["resource_metadata_scope"] = (
        "Inherited admission and resource metadata cover the full requested T-call; "
        "the prefix policy itself contains only sweeps 1 through D."
    )
    prefix["scope"] = "Research profile of one fixed full-deck raised turn/river game."
    return prefix


def capture(case, backend, discard, total, interval=None):
    """Capture D/T averages from one unchanged production training call.

    This wrapper adds callback snapshots only. It does not set a stop target,
    skip sweeps, change averaging, or alter solver admission and work checks.
    """
    case = _case(case)
    if (type(discard) is not int or type(total) is not int or
            not 1 <= discard < total or total < 10 or total > 1500):
        raise ValueError("Require integer 1 <= discard < total <= 1500 and total >= 10")
    interval = discard if interval is None else interval
    if type(interval) is not int or interval < 1 or discard % interval:
        raise ValueError("Positive interval must emit the discard checkpoint")
    if type(backend) is not str or backend not in ("materialized", "matrix-free"):
        raise ValueError("Unknown backend")

    module, trainer_name = (
        (postflop_solver, "train_public_batched") if backend == "materialized"
        else (matrix_free_turn, "train_ranked_turn")
    )
    original = getattr(module, trainer_name)
    snapshots, callbacks, calls = {}, [], [0]
    observer = _make_observer(original, backend, discard, total, interval,
                              snapshots, callbacks, calls)
    started = time.perf_counter()
    with patch.object(module, trainer_name, observer):
        full = solve(case, backend, "cfrplus", total)
    complete_seconds = time.perf_counter() - started

    if calls[0] != 1 or set(snapshots) != {discard, total}:
        raise ValueError("One training run did not supply both requested snapshots")
    expected_callbacks = list(range(interval, total + 1, interval))
    if expected_callbacks[-1] != total:
        expected_callbacks.append(total)
    if callbacks != expected_callbacks:
        raise ValueError("Unexpected completed-sweep callback schedule")

    hands = tuple(tuple(expand_range(case[side], cards(case["board"])))
                  for side in ("oop", "ip"))
    strategy = full.get("strategy")
    keys = tuple(sorted(snapshots[total]))
    if len(keys) != len(strategy):
        raise ValueError("Information-set count differs from serialized full policy")
    prefix = _derived_prefix(full, discard, total)
    for key, row, prefix_row in zip(keys, strategy, prefix["strategy"]):
        player, hand_index, history = key
        identity = ("oop" if player == 0 else "ip", "".join(hands[player][hand_index]),
                    tuple(history))
        if (row.get("player"), row.get("hand"), tuple(row.get("history", ()))) != identity:
            raise ValueError("Serialized hand/history identity differs from trainer key")
        final = snapshots[total][key]
        if tuple(action["probability"] for action in row["actions"]) != final:
            raise ValueError("Final callback differs from returned production policy")
        earlier = snapshots[discard][key]
        if len(earlier) != len(prefix_row["actions"]):
            raise ValueError("Prefix action count differs from serialized legal row")
        for action, probability in zip(prefix_row["actions"], earlier):
            action["probability"] = probability

    replay_started = time.perf_counter()
    full_oracle = _replay(full, case)
    full_differences = compare_result(full, full_oracle, tolerance=1e-9)
    prefix_oracle = _replay(prefix, case)
    prefix.update({name: prefix_oracle[name] for name in METRICS})
    prefix_differences = compare_result(prefix, prefix_oracle, tolerance=1e-9)
    replay_seconds = time.perf_counter() - replay_started
    if (full_oracle["worlds"] != 176 or full_oracle["compatible_pair_count"] != 4 or
            full_oracle["checked_information_sets"] != 2404 or
            prefix_oracle["worlds"] != 176 or prefix_oracle["checked_information_sets"] != 2404):
        raise ValueError("Independent replay did not validate the complete 2404-row game")
    return full, prefix, {
        "callback_iterations": callbacks,
        "trainer_calls": calls[0],
        "final_snapshot_exactly_matches_returned_profile": True,
        "complete_call_with_observations_seconds": complete_seconds,
        "independent_replay_seconds": replay_seconds,
        "full_scalar_differences": full_differences,
        "prefix_scalar_differences": prefix_differences,
        "full_independent_metrics": {name: full_oracle[name] for name in METRICS},
        "prefix_independent_metrics": {name: prefix_oracle[name] for name in METRICS},
        "verified_worlds": prefix_oracle["worlds"],
        "verified_compatible_pairs": prefix_oracle["compatible_pair_count"],
        "verified_information_sets": prefix_oracle["checked_information_sets"],
        "derived_profile_scope": prefix["scope"],
    }
