"""Observational capture parity and lifetime tests for the research harness."""
from copy import deepcopy
import json
import unittest
from unittest.mock import patch

from pokerlab.cards import cards, expand_range
from scripts import benchmark_river_tail as experiment
from scripts.benchmark_turn_river_independent import CONFIG, solve
from scripts.turn_river_validation import compare_result, replay_policy


class RiverTailCaptureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        scenarios = json.loads(CONFIG.read_text(encoding='utf-8'))['scenarios']
        cls.cases = [case for case in scenarios if case['id'] in experiment.CASE_IDS]

    def test_observations_preserve_complete_result_and_off_interval_final_snapshot(self):
        for case in self.cases:
            for backend in ('materialized', 'matrix-free'):
                with self.subTest(scenario=case['id'], backend=backend):
                    full, prefix, evidence = experiment.capture(case, backend, 7, 20, interval=7)
                    self.assertEqual(evidence['callback_iterations'], [7, 14, 20])
                    self.assertEqual(evidence['trainer_calls'], 1)
                    self.assertTrue(evidence['final_snapshot_exactly_matches_returned_profile'])
                    self.assertEqual(full, solve(case, backend, 'cfrplus', 20))
                    self.assertEqual(prefix['iterations'], 7)
                    self.assertEqual(prefix['source_requested_iterations'], 20)
                    self.assertEqual(prefix['source_iteration_window'], [1, 7])
                    self.assertTrue(prefix['solver_version'].startswith('research-'))
                    oracle = replay_policy(prefix, case['oop'], case['ip'],
                                           board=case['board'], config=case['config'])
                    self.assertTrue(all(abs(value) <= 1e-9 for value in
                                        compare_result(prefix, oracle).values()))

    def test_hand_identity_preserves_range_insertion_order(self):
        case = next(case for case in self.cases if case['id'] == 'river-polarised-bluffcatcher')
        hands = tuple(expand_range(case['oop'], cards(case['board'])))
        self.assertNotEqual(hands[0], sorted(hands)[0])
        for backend in ('materialized', 'matrix-free'):
            with self.subTest(backend=backend):
                full, prefix, _ = experiment.capture(case, backend, 7, 20)
                first = next(row for row in full['strategy'] if row['player'] == 'oop')
                self.assertEqual(first['hand'], ''.join(hands[0]))
                self.assertEqual([row['hand'] for row in full['strategy']],
                                 [row['hand'] for row in prefix['strategy']])

    def test_function_restored_after_success_and_callback_exception(self):
        case = self.cases[0]
        for backend, module, name in (
                ('materialized', experiment.postflop_solver, 'train_public_batched'),
                ('matrix-free', experiment.matrix_free_river, 'train_ranked_river')):
            with self.subTest(backend=backend):
                original = getattr(module, name)
                experiment.capture(case, backend, 7, 20)
                self.assertIs(getattr(module, name), original)
                with patch.object(experiment, '_copy_snapshot', side_effect=RuntimeError('injected snapshot')):
                    with self.assertRaisesRegex(RuntimeError, 'injected snapshot'):
                        experiment.capture(case, backend, 7, 20)
                self.assertIs(getattr(module, name), original)
                with patch.object(module, name, side_effect=RuntimeError('injected trainer')) as broken:
                    with self.assertRaisesRegex(RuntimeError, 'injected trainer'):
                        experiment.capture(case, backend, 7, 20)
                    self.assertIs(getattr(module, name), broken)
                self.assertIs(getattr(module, name), original)

    def test_existing_target_callbacks_are_rejected_and_function_is_restored(self):
        case = self.cases[0]
        for backend, module, name in (
                ('materialized', experiment.postflop_solver, 'train_public_batched'),
                ('matrix-free', experiment.matrix_free_river, 'train_ranked_river')):
            with self.subTest(backend=backend):
                original = getattr(module, name)

                def conflicting_solve(*args):
                    trainer = getattr(module, name)
                    positional = ((None, [], {}, 20, 'cfrplus') if backend == 'materialized'
                                  else (None, {}, 20, 'cfrplus'))
                    return trainer(*positional, checkpoint_interval=1,
                                   checkpoint_callback=lambda *args: False)

                with patch.object(experiment, 'solve', conflicting_solve):
                    with self.assertRaisesRegex(ValueError, 'Existing target/checkpoint'):
                        experiment.capture(case, backend, 7, 20)
                self.assertIs(getattr(module, name), original)

    def test_snapshot_copy_does_not_alias_trainer_rows(self):
        key = (0, 0, ())
        raw = {key: [0.25, 0.75]}
        saved = experiment._copy_snapshot(raw, (key,), {key: 2})
        raw[key][0] = 0.5
        self.assertEqual(saved[key], (0.25, 0.75))
        with self.assertRaisesRegex(ValueError, 'keys changed'):
            experiment._copy_snapshot({}, (key,), {key: 2})
        with self.assertRaisesRegex(ValueError, 'action count'):
            experiment._copy_snapshot(raw, (key,), {key: 3})

    def test_capture_rejects_invalid_checkpoints_and_other_streets(self):
        case = self.cases[0]
        for discard, total, interval in ((True, 20, 1), (7, False, 1), (0, 20, 1),
                                         (20, 20, 1), (7, 10001, 1), (7, 20, False),
                                         (7, 20, 2), (7, 20, 0)):
            with self.subTest(discard=discard, total=total, interval=interval):
                with self.assertRaises(ValueError):
                    experiment.capture(case, 'materialized', discard, total, interval)
        turn = deepcopy(case)
        turn['board'] = turn['board'][:-2]
        with self.assertRaises(ValueError):
            experiment.capture(turn, 'materialized', 7, 20)
        with self.assertRaises(ValueError):
            experiment.capture(case, 'unsupported', 7, 20)


if __name__ == '__main__':
    unittest.main()
