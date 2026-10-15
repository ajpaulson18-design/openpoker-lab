"""Admission regressions for solves using already prepared full-board counts."""
from copy import deepcopy
from fractions import Fraction
import inspect
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from pokerlab import preflop_full_board_equity as equity
from pokerlab import preflop_push_fold as push_fold

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "benchmarks" / "results" / "preflop-suit-remap-v1.json"
SB_RANGE = "AsAd:1,QsQd:0.5"
BB_RANGE = "AsKh:0.125,AsKc:0.125,KsKd:1"
CONFIG = {"small_blind": 0.5, "big_blind": 1, "starting_stack": [3, 2]}
BOARDS = 1_712_304
_LIMITS = {
    "candidate_pairs": 4_096,
    "compatible_pairs": 4,
    "board_evaluations": 6_849_216,
    "rank_calls": 13_698_432,
    "categorical_rows": 12,
}
_PREPARATION = {
    "candidate_pairs": 6,
    "compatible_pairs": 4,
    "boards_per_pair": BOARDS,
    "physical_worlds_upper_bound": 4 * BOARDS,
    "board_evaluations_upper_bound": 4 * BOARDS,
    "rank_calls_upper_bound": 8 * BOARDS,
    "categorical_rows_upper_bound": 12,
    "limits": _LIMITS,
    "scope": "Exact unordered five-card boards per compatible private pair; logical counts, not time or memory guarantees.",
}
_LEGACY_SCOPE = (
    "Conservative bookkeeping and generic-CFR/reference diagnostic loop entries "
    "for the fixed two-decision tree; source preparation is charged even when an "
    "immutable table is reused. Internal ranking instructions and caller progress "
    "callbacks are excluded; total rank calls have a separate pre-enumeration cap. "
    "Not bytecode, elapsed time, allocated bytes or RSS bounds."
)
_PREPARED_SCOPE = (
    "Prepared-table solve only. The existing immutable table is structurally "
    "validated and its category rows are consumed; this call charges a conservative "
    "bounded table census, validation, setup and result-row bookkeeping, plus the "
    "unchanged training and diagnostic envelopes. Historical full-board enumeration "
    "metadata is recorded for provenance but not charged again; current rank calls "
    "and board combinations are zero. Internal ranking instructions and caller "
    "progress callbacks are excluded. Not bytecode, elapsed time, allocated bytes "
    "or RSS bounds."
)


def _trusted_fixture_rows():
    """Load the frozen historical W/T/L rows; never read Git or rank a board."""
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    match = next(row for row in report["results"]
                 if row["id"] == "split-ak-four-pairs-three-bb-hands")
    return tuple(match["input"]["counts"])


def _trusted_golden_result():
    """Return the committed frozen pre-change full solver payload."""
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    case = report["results"][-1]
    if case["id"] != "split-ak-four-pairs-three-bb-hands":
        raise AssertionError("Frozen report no longer ends with the split-AK golden")
    return case["result"]


def _prepared_table():
    """Assemble a valid immutable table around the local physical count fixture."""
    plan = equity.plan_preflop_equities(SB_RANGE, BB_RANGE)
    counts_by_pair = {
        (row["sb_hand"], row["bb_hand"]):
            (row["wins"], row["ties"], row["losses"])
        for row in _trusted_fixture_rows()
    }
    counts, worlds = [], []
    for sb_index, bb_index, prior in plan.pairs:
        key = ("".join(plan.hands[0][sb_index]),
               "".join(plan.hands[1][bb_index]))
        count = counts_by_pair[key]
        counts.append(count)
        wins, ties, losses = count
        for sign, amount in zip((-1, 0, 1), (losses, ties, wins)):
            if amount:
                mass = float(prior * Fraction(amount, BOARDS))
                worlds.append((sb_index, bb_index, mass, sign))
    table = equity.FullBoardEquities(
        hands=plan.hands,
        pairs=plan.pairs,
        counts=tuple(counts),
        worlds=tuple(worlds),
        _budget_items=plan._budget_items,
    )
    table.validate()
    return table


def _independent_shape(table):
    candidate_pairs = len(table.hands[0]) * len(table.hands[1])
    pair_count = len(table.pairs)
    categorical_rows = 3 * pair_count
    active_hands = [
        {pair[player] for pair in table.pairs}
        for player in (0, 1)
    ]
    info_action_slots = 2 * sum(len(hands) for hands in active_hands)
    return candidate_pairs, pair_count, categorical_rows, info_action_slots


def _expected_common(iterations, algorithm, table):
    candidates, pairs, rows, slots = _independent_shape(table)
    training = (1024 + 64 * rows + 128 * slots
                + iterations * (256 + 2048 * rows + 256 * slots))
    diagnostics = 1024 + 512 * rows + 256 * slots
    return candidates, pairs, rows, slots, training, diagnostics


def _expected_legacy_budget(iterations, algorithm, table):
    candidates, pairs, rows, slots, training, diagnostics = _expected_common(
        iterations, algorithm, table)
    source = 128 + 8 * candidates + 128 * pairs + 64 * BOARDS * pairs
    return {
        "budget_version": "preflop-push-fold-work-v1",
        "requested_iterations": iterations,
        "compatible_pairs": pairs,
        "categorical_rows_upper_bound": rows,
        "information_action_slots": slots,
        "public_states": 5,
        "algorithm": algorithm,
        "training_loop_entries_upper_bound": training,
        "diagnostic_loop_entries_upper_bound": diagnostics,
        "source_bookkeeping_loop_entries_upper_bound": source,
        "total_loop_entries_upper_bound": training + diagnostics + source,
        "total_loop_entry_limit": 500_000_000,
        "equity_preparation": _PREPARATION,
        "scope": _LEGACY_SCOPE,
    }


def _expected_prepared_budget(iterations, algorithm, table):
    candidates, pairs, rows, slots, training, diagnostics = _expected_common(
        iterations, algorithm, table)
    setup = 128 + 32 * candidates + 256 * pairs + 128 * rows + 128 * slots
    return {
        "budget_version": "preflop-push-fold-prepared-count-v1",
        "requested_iterations": iterations,
        "compatible_pairs": pairs,
        "categorical_rows_upper_bound": rows,
        "information_action_slots": slots,
        "public_states": 5,
        "algorithm": algorithm,
        "training_loop_entries_upper_bound": training,
        "diagnostic_loop_entries_upper_bound": diagnostics,
        "prepared_setup_loop_entries_upper_bound": setup,
        "source_bookkeeping_loop_entries_upper_bound": 0,
        "current_rank_calls": 0,
        "current_board_combinations": 0,
        "source_enumeration_charged": False,
        "total_loop_entries_upper_bound": setup + training + diagnostics,
        "total_loop_entry_limit": 500_000_000,
        "historical_equity_preparation": _PREPARATION,
        "scope": _PREPARED_SCOPE,
    }


def _uniform_average(root, worlds, infos, iterations, *args, **kwargs):
    return {key: (0.5, 0.5) for key in infos}


class PreflopPreparedCountsBudgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.table = _prepared_table()
        cls.table_snapshot = (cls.table.hands, cls.table.pairs,
                              cls.table.counts, cls.table.worlds,
                              cls.table._budget_items)

    def _run_mocked(self, *, iterations, algorithm="cfrplus", model="prepared-counts",
                    averaging_delay=0):
        with patch.object(push_fold.cfr, "train", side_effect=_uniform_average), \
             patch.object(push_fold, "train_cfrplus", side_effect=_uniform_average), \
             patch.object(push_fold.cfr, "evaluate", return_value=0.0), \
             patch.object(push_fold.cfr, "best_response", return_value=0.0):
            return push_fold.solve_prepared_push_fold(
                self.table, config=CONFIG, iterations=iterations,
                algorithm=algorithm, averaging_delay=averaging_delay,
                resource_model=model)

    def test_default_source_inclusive_payload_matches_independent_legacy_formula(self):
        for algorithm in ("vanilla", "dcfr", "cfrplus"):
            with self.subTest(algorithm=algorithm):
                result = self._run_mocked(iterations=2000, algorithm=algorithm,
                                          model="source-inclusive")
                self.assertEqual(result["work_budget"],
                                 _expected_legacy_budget(2000, algorithm, self.table))
                self.assertNotIn("resource_model", result)

    def test_prepared_mode_changes_only_budget_and_preserves_real_solver_output(self):
        with patch.object(equity, "rank_hand",
                          side_effect=AssertionError("prepared solve must not rank")), \
             patch.object(equity, "_board_combinations",
                          side_effect=AssertionError("prepared solve must not enumerate")):
            for iterations in (100, 2000):
                for algorithm in ("vanilla", "dcfr", "cfrplus"):
                    with self.subTest(iterations=iterations, algorithm=algorithm):
                        legacy = push_fold.solve_prepared_push_fold(
                            self.table, config=CONFIG, iterations=iterations,
                            algorithm=algorithm)
                        prepared = push_fold.solve_prepared_push_fold(
                            self.table, config=CONFIG, iterations=iterations,
                            algorithm=algorithm, resource_model="prepared-counts")
                        self.assertEqual(prepared["work_budget"],
                                         _expected_prepared_budget(iterations, algorithm,
                                                                   self.table))
                        legacy_payload = deepcopy(legacy)
                        prepared_payload = deepcopy(prepared)
                        legacy_payload.pop("work_budget")
                        prepared_payload.pop("work_budget")
                        self.assertEqual(prepared_payload, legacy_payload)
                        if iterations == 2000 and algorithm == "cfrplus":
                            golden = _trusted_golden_result()
                            self.assertEqual(
                                json.dumps(legacy, sort_keys=True, separators=(",", ":")),
                                json.dumps(golden, sort_keys=True, separators=(",", ":")))
        self.assertEqual((self.table.hands, self.table.pairs, self.table.counts,
                          self.table.worlds, self.table._budget_items),
                         self.table_snapshot)

    def test_prepared_mode_admits_three_and_ten_thousand_requested_iterations(self):
        for iterations in (3000, 10000):
            for algorithm in ("vanilla", "dcfr", "cfrplus"):
                delay = iterations - 1 if algorithm == "cfrplus" else 0
                with self.subTest(iterations=iterations, algorithm=algorithm):
                    with patch.object(push_fold.cfr, "train",
                                      side_effect=_uniform_average) as train, \
                         patch.object(push_fold, "train_cfrplus",
                                      side_effect=_uniform_average) as train_plus, \
                         patch.object(push_fold.cfr, "evaluate", return_value=0.0), \
                         patch.object(push_fold.cfr, "best_response", return_value=0.0):
                        result = push_fold.solve_prepared_push_fold(
                            self.table, config=CONFIG, iterations=iterations,
                            algorithm=algorithm, averaging_delay=delay,
                            resource_model="prepared-counts")
                    self.assertEqual(result["work_budget"],
                                     _expected_prepared_budget(iterations, algorithm,
                                                               self.table))
                    expected_call = train_plus if algorithm == "cfrplus" else train
                    self.assertEqual(expected_call.call_args.args[3], iterations)
                    if algorithm == "cfrplus":
                        self.assertEqual(expected_call.call_args.kwargs["delay"], delay)
                    else:
                        self.assertEqual(expected_call.call_args.args[4], algorithm)

    def test_prepared_budget_accepts_exact_limit_and_rejects_one_below_before_work(self):
        expected = _expected_prepared_budget(10, "vanilla", self.table)
        limit = expected["total_loop_entries_upper_bound"]
        with patch.object(push_fold, "MAX_MODELED_LOOP_ENTRIES", limit):
            result = self._run_mocked(iterations=10, algorithm="vanilla")
        self.assertEqual(result["work_budget"]["total_loop_entry_limit"], limit)
        with patch.object(push_fold, "MAX_MODELED_LOOP_ENTRIES", limit - 1), \
             patch.object(push_fold, "_Action",
                          side_effect=AssertionError("tree built before budget rejection")), \
             patch.object(push_fold, "_Node",
                          side_effect=AssertionError("tree built before budget rejection")), \
             patch.object(push_fold, "_Terminal",
                          side_effect=AssertionError("tree built before budget rejection")), \
             patch.object(push_fold.cfr, "train",
                          side_effect=AssertionError("trainer called before rejection")), \
             patch.object(push_fold, "train_cfrplus",
                          side_effect=AssertionError("trainer called before rejection")), \
             patch.object(push_fold.cfr, "evaluate",
                          side_effect=AssertionError("evaluator called before rejection")), \
             patch.object(push_fold.cfr, "best_response",
                          side_effect=AssertionError("BR called before rejection")):
            with self.assertRaisesRegex(ValueError, "full-requested prepared work"):
                push_fold.solve_prepared_push_fold(
                    self.table, config=CONFIG, iterations=10, algorithm="vanilla",
                    resource_model="prepared-counts")

    def test_legacy_four_pair_three_thousand_rejects_before_tree_or_training(self):
        with patch.object(push_fold, "_Action",
                          side_effect=AssertionError("tree built before budget rejection")), \
             patch.object(push_fold, "_Node",
                          side_effect=AssertionError("tree built before budget rejection")), \
             patch.object(push_fold, "_Terminal",
                          side_effect=AssertionError("tree built before budget rejection")), \
             patch.object(push_fold.cfr, "train",
                          side_effect=AssertionError("trainer called before rejection")), \
             patch.object(push_fold, "train_cfrplus",
                          side_effect=AssertionError("trainer called before rejection")), \
             patch.object(push_fold.cfr, "evaluate",
                          side_effect=AssertionError("evaluator called before rejection")), \
             patch.object(push_fold.cfr, "best_response",
                          side_effect=AssertionError("BR called before rejection")), \
             patch.object(equity, "rank_hand",
                          side_effect=AssertionError("ranked before rejection")):
            with self.assertRaisesRegex(ValueError, "full-requested work"):
                push_fold.solve_prepared_push_fold(
                    self.table, config=CONFIG, iterations=3000,
                    algorithm="cfrplus", averaging_delay=2999)

    def test_full_solve_three_thousand_rejects_before_preparation_build(self):
        plan = equity.plan_preflop_equities(SB_RANGE, BB_RANGE)
        with patch.object(push_fold, "plan_preflop_equities", return_value=plan), \
             patch.object(type(plan), "build") as build, \
             patch.object(equity, "rank_hand",
                          side_effect=AssertionError("ranked before source-inclusive rejection")), \
             patch.object(push_fold.cfr, "train",
                          side_effect=AssertionError("trainer called before rejection")), \
             patch.object(push_fold, "train_cfrplus",
                          side_effect=AssertionError("trainer called before rejection")):
            with self.assertRaisesRegex(ValueError, "full-requested work"):
                push_fold.solve_preflop_push_fold(
                    SB_RANGE, BB_RANGE, config=CONFIG, iterations=3000,
                    algorithm="cfrplus")
            build.assert_not_called()
        self.assertNotIn("resource_model",
                         inspect.signature(push_fold.solve_preflop_push_fold).parameters)

    def test_invalid_resource_model_rejects_before_table_validation(self):
        with patch.object(type(self.table), "validate",
                          side_effect=AssertionError("table validation preceded selector")):
            with self.assertRaisesRegex(ValueError, "resource_model"):
                push_fold.solve_prepared_push_fold(
                    self.table, config=CONFIG, iterations=10,
                    resource_model="unrecognized")


if __name__ == "__main__":
    unittest.main()
