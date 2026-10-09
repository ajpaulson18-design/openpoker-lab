"""Benchmark public-vector diagnostics against world-wise diagnostics.

This measures only profile evaluation plus both best responses. It deliberately
does not train a policy or time complete solver calls.
"""

import argparse
import hashlib
import json
import statistics
import time
import tracemalloc
from pathlib import Path

from pokerlab.cfr import best_response, evaluate
from pokerlab.postflop_solver import (
    _Chance,
    _build_postflop_tree,
    _chance_child,
    _chance_partitions,
    _enumerate_worlds,
    _node_key,
    _prefix_hand_index,
    _public_reveals,
    _terminal_value,
)
from pokerlab.public_diagnostics import evaluate_profile
from pokerlab.river_config import RiverConfig


ROOT = Path(__file__).resolve().parents[1]
SOURCE_FILES = (
    "pokerlab/cards.py",
    "pokerlab/cfr.py",
    "pokerlab/postflop_solver.py",
    "pokerlab/public_cfr.py",
    "pokerlab/public_diagnostics.py",
    "pokerlab/river_config.py",
    "pokerlab/river_tree.py",
)
REPETITIONS = 20
VALUE_TOLERANCE = 1e-10


def _sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _source_hashes():
    return {name: _sha256(ROOT / name) for name in SOURCE_FILES}


def _fixture(name, board, oop_range, ip_range, runouts, config):
    _, worlds, selected, compatible_pairs = _enumerate_worlds(
        board, oop_range, ip_range, runouts, 1,
    )
    root, nodes, chance_nodes, visited_nodes, _ = _build_postflop_tree(
        board, config, worlds=worlds,
    )
    legal_hands = _prefix_hand_index(worlds)
    infos = {}
    for (player, history), node in nodes.items():
        for hand in legal_hands.get((player, _public_reveals(history)), ()):
            infos[(player, hand, history)] = len(node.actions)
    # One fixed uniform policy is shared by both diagnostic implementations.
    averages = {
        key: [1.0 / count] * count
        for key, count in infos.items()
    }
    payoff = lambda node, world: _terminal_value(node, world[3], config.pot)

    def generic():
        value = evaluate(root, worlds, averages, payoff, _node_key, _chance_child)
        br0 = best_response(0, root, worlds, averages, payoff, _node_key,
                            _chance_partitions)
        br1 = best_response(1, root, worlds, averages, payoff, _node_key,
                            _chance_partitions)
        return value, br0, br1

    def vector():
        return evaluate_profile(root, worlds, averages, pot=config.pot,
                                chance_type=_Chance)

    policy_description = [
        [key[0], key[1], list(key[2]), row]
        for key, row in sorted(averages.items())
    ]
    policy_hash = hashlib.sha256(json.dumps(
        policy_description, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")).hexdigest()
    return {
        "name": name,
        "board": list(board),
        "oop_range": oop_range,
        "ip_range": ip_range,
        "runouts": None if runouts is None else list(runouts),
        "config": config.to_dict(),
        "selected_runouts": list(selected),
        "compatible_hand_pairs": compatible_pairs,
        "worlds": len(worlds),
        "information_sets": len(infos),
        "public_nodes": len(nodes),
        "chance_nodes": chance_nodes,
        "world_traversal_nodes": visited_nodes,
        "policy": "fixed uniform probabilities at every information set",
        "policy_sha256": policy_hash,
        "profile_values": None,
        "generic_seconds_samples": [],
        "public_vector_seconds_samples": [],
        "generic_median_seconds": None,
        "public_vector_median_seconds": None,
        "median_speedup_generic_over_vector": None,
        "generic_peak_bytes_one_call": None,
        "public_vector_peak_bytes_one_call": None,
        "generic": generic,
        "vector": vector,
    }


def _measure_peak(call):
    tracemalloc.start()
    try:
        call()
        _current, peak = tracemalloc.get_traced_memory()
        return peak
    finally:
        tracemalloc.stop()


def _run_fixture(fixture):
    generic, vector = fixture.pop("generic"), fixture.pop("vector")
    g_samples, v_samples = [], []
    first_values = {}
    max_difference = 0.0
    for index in range(REPETITIONS):
        iteration_values = {}
        order = (("generic", generic), ("public_vector", vector))
        if index % 2:
            order = tuple(reversed(order))
        for label, call in order:
            start = time.perf_counter()
            values = call()
            elapsed = time.perf_counter() - start
            if label == "generic":
                g_samples.append(elapsed)
            else:
                v_samples.append(elapsed)
            first_values.setdefault(label, values)
            iteration_values[label] = values
            if len(iteration_values) == 2:
                difference = max(abs(a - b) for a, b in zip(
                    iteration_values["generic"], iteration_values["public_vector"],
                ))
                max_difference = max(max_difference, difference)
                if difference > VALUE_TOLERANCE:
                    raise RuntimeError(
                        f"{fixture['name']}: diagnostic values differ by more than "
                        f"{VALUE_TOLERANCE:g} at repetition {index + 1}: "
                        f"{iteration_values!r}"
                    )

    fixture["profile_values"] = {
        "generic": list(first_values["generic"]),
        "public_vector": list(first_values["public_vector"]),
        "max_abs_difference": max_difference,
        "tolerance": VALUE_TOLERANCE,
    }
    fixture["generic_seconds_samples"] = g_samples
    fixture["public_vector_seconds_samples"] = v_samples
    fixture["generic_median_seconds"] = statistics.median(g_samples)
    fixture["public_vector_median_seconds"] = statistics.median(v_samples)
    fixture["median_speedup_generic_over_vector"] = (
        fixture["generic_median_seconds"] / fixture["public_vector_median_seconds"]
    )
    # Memory is measured in distinct, single-call tracemalloc sessions outside
    # the timed repetitions so instrumentation cannot affect runtime samples.
    fixture["generic_peak_bytes_one_call"] = _measure_peak(generic)
    fixture["public_vector_peak_bytes_one_call"] = _measure_peak(vector)


def run_benchmark():
    before = _source_hashes()
    river_config = RiverConfig(
        pot=40, effective_stack=80, bet_sizes=(0.5,), raise_sizes=(0.5,),
        max_raises=1, include_all_in=False,
    )
    turn_config = RiverConfig(
        pot=40, effective_stack=80, bet_sizes=(0.5,), raise_sizes=(),
        max_raises=0, include_all_in=False,
    )
    fixtures = [
        _fixture(
            "river-weighted-raises",
            ("2c", "5d", "9h", "Jc", "Qs"),
            "AsAh:0.75,KsKh:0.25",
            "AcAd:0.4,KcKd:0.6",
            None,
            river_config,
        ),
        _fixture(
            "turn-full-physical-two-by-four-combos",
            ("As", "Kd", "7c", "2h"),
            "QhQs,JhJs",
            "AcQc,TcTh,9c9d,8c8d",
            None,
            turn_config,
        ),
    ]
    for fixture in fixtures:
        _run_fixture(fixture)
    after = _source_hashes()
    if before != after:
        changed = [name for name in SOURCE_FILES if before[name] != after[name]]
        raise RuntimeError(f"Benchmark source changed while running: {changed}")
    return {
        "benchmark": "public-diagnostics-phase-v1",
        "purpose": "profile evaluation plus exact BR0/BR1 only; no policy training or full solve call",
        "repetitions_per_method_per_fixture": REPETITIONS,
        "interleaving": "alternate generic-first and public-vector-first order",
        "source_sha256_before": before,
        "source_sha256_after": after,
        "source_unchanged": True,
        "fixtures": fixtures,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path,
                        help="Optional path for the JSON report; stdout is the default.")
    args = parser.parse_args()
    report = run_benchmark()
    rendered = json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
