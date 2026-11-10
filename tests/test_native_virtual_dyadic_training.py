"""Compiled rank-free admission and fail-closed controls; never launch TRAIN."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from scripts.run_virtual_dyadic_training_cohort import compare_buffered_ten, exact_json, validate_admission
from scripts.run_virtual_frozen_source_only import source_only_command
from scripts.verify_virtual_dyadic_training import SPLIT_BYTES, SPLIT_IMAGE_BYTES, replay
from tests.test_native_exact_reach import authenticate, sha
from tests.virtual_dyadic_training_reference import Fixture
from tests.virtual_frozen_run_control import run_bounded_child, run_bounded_dyadic_probe


ROOT=Path(__file__).resolve().parents[1]
ENV='OPENPOKER_NATIVE_VIRTUAL_DYADIC_TRAINING_EXE'


class DyadicTrainingHarnessControls(unittest.TestCase):
    def test_virtual_zero_comparison_consumes_the_published_buffered_schema(self):
        baseline=ROOT/'benchmarks/results/native-dyadic-buffered-ten-card-accepted-v1'
        manifest,archive=(baseline/name for name in ('manifest.json','evidence.zip'))
        binding={'files':{path.relative_to(ROOT).as_posix():{'raw_sha256':sha(path)}
                          for path in (manifest,archive)}}
        accepted=exact_json(manifest.read_bytes())
        images=accepted['checkpoint_inputs']['sweep_images']
        paging=dict(accepted['paging']['counts'],physical_read_requests=1498,physical_write_requests=18836)
        with TemporaryDirectory(dir=ROOT.parent) as temporary:
            stream=Path(temporary)/'stdout.bin'
            with ZipFile(archive) as bundle, bundle.open('cohort/train_ten_buffered/stdout.bin') as saved:
                with stream.open('xb') as copied:
                    shutil.copyfileobj(saved,copied)
            comparison=compare_buffered_ten(stream,binding,{'counts':paging},images,virtual_zero=True)
        self.assertEqual(comparison['exact_checkpoint_images'],images)
        self.assertEqual(comparison['numeric_sha256'],accepted['buffered_comparison']['numeric_sha256'])
        self.assertEqual(comparison['baseline_stream_sha256'],accepted['checkpoint_inputs']['stream']['sha256'])

    def test_ten_card_reference_preserves_ordered_physical_support(self):
        fixture=Fixture(ten_card=True)
        self.assertEqual(len(fixture.worlds),360)
        self.assertEqual(len({world.board for world in fixture.worlds}),340)
        self.assertEqual(fixture.terminal_completion_counts(),(103_020,70_912))
        self.assertEqual(sum(1 for _ in fixture.ordered_rows()),119_196)

    def test_split_replay_rejects_incomplete_or_unauthenticated_inputs_before_math(self):
        with TemporaryDirectory(dir=ROOT.parent) as temporary:
            root=Path(temporary)
            stream,first,second=(root/name for name in ('stdout.bin','staged.bin','committed.bin'))
            stream.write_bytes(bytes(SPLIT_BYTES))
            first.write_bytes(bytes(SPLIT_IMAGE_BYTES))
            second.write_bytes(b'')
            ordered=((first,sha(first)),(second,sha(second)))
            with patch('scripts.verify_virtual_dyadic_training.Fixture',side_effect=AssertionError('early replay')):
                with self.assertRaisesRegex(ValueError,'ordered pair'):
                    replay(stream,sha(stream),paired=True,rank_sets=True,images=ordered[::-1])
                with self.assertRaisesRegex(ValueError,'input byte count'):
                    replay(stream,sha(stream),paired=True,rank_sets=True,images=ordered)
                with self.assertRaisesRegex(ValueError,'input sha256'):
                    replay(stream,sha(stream),paired=True,rank_sets=True,images=((first,'0'*64),ordered[1]))

    def test_large_training_stream_is_only_available_to_fixed_transport(self):
        command=[sys.executable,'-B','-c',
                 'import sys;request=sys.stdin.buffer.read();sys.stdout.buffer.write(request+b"x"*3000000)']
        with TemporaryDirectory(dir=ROOT.parent) as temporary:
            root=Path(temporary)
            with self.assertRaisesRegex(ValueError,'reduce-only child bounds'):
                run_bounded_child(command,b'',root/'old',stdout_limit=3000100)
            with self.assertRaisesRegex(ValueError,'invalid fixed dyadic'):
                run_bounded_dyadic_probe(command,'TRAIN extra',root/'foreign')
            self.assertFalse((root/'old').exists())
            self.assertFalse((root/'foreign').exists())
            target=root/'training'
            observed=run_bounded_dyadic_probe(command,'TRAIN',target)
            self.assertEqual((observed['status'],observed['returncode'],observed['actual_exit_observed']),('exited',0,True))
            self.assertEqual((target/'request.bin').read_bytes(),b'DYADIC_T2_V1 TRAIN\n')
            self.assertEqual((target/'stdout.bin').stat().st_size,3_000_019)

    def test_source_only_launcher_accepts_named_dyadic_entries(self):
        with TemporaryDirectory(dir=ROOT.parent) as temporary:
            root=Path(temporary)
            scripts=root/'scripts'
            scripts.mkdir()
            (scripts/'__init__.py').touch()
            script=scripts/'run_virtual_frozen_source_only.py'
            script.write_bytes((ROOT/'scripts'/script.name).read_bytes())
            for module in ('scripts.run_virtual_dyadic_training_cohort','scripts.verify_virtual_dyadic_training',
                           'scripts.pack_virtual_dyadic_checkpoints'):
                with self.subTest(module=module):
                    name=module.replace('.','/')+'.py'
                    entry=root/name
                    entry.write_text('print("dyadic entry loaded")\n',encoding='ascii')
                    receipt=root/(entry.stem+'.json')
                    process=subprocess.run(source_only_command(script,sha(script),module,receipt,[]),
                        capture_output=True,check=False,timeout=30)
                    self.assertEqual(process.returncode,0,process.stderr)
                    self.assertIn(b'dyadic entry loaded',process.stdout)
                    self.assertEqual(json.loads(receipt.read_bytes())['compiled'][name],sha(entry))


@unittest.skipUnless(os.environ.get(ENV),'explicit source-built PROOF9 T2 probe required')
class NativeDyadicAdmissionControls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.exe=Path(os.environ[ENV]).resolve()
        cls.identity=authenticate(cls.exe,ROOT,'virtual-dyadic-training')
        directory=os.environ.get('OPENPOKER_NATIVE_VIRTUAL_DYADIC_TRAINING_CONTROL_DIR')
        if directory is None:
            temporary=TemporaryDirectory(dir=ROOT.parent)
            cls.addClassCleanup(temporary.cleanup)
            directory=temporary.name
        cls.output=Path(directory)

    @classmethod
    def tearDownClass(cls):
        if authenticate(cls.exe,ROOT,'virtual-dyadic-training')!=cls.identity:
            raise AssertionError('PROOF9 T2 source/build drift during controls')

    def observe(self,name,call):
        directory=self.output/name
        before=sha(self.exe)
        self.assertEqual(before,self.identity[1]['executable_sha256'])
        process=call(directory)
        after=sha(self.exe)
        (directory/'binary-identity.json').write_text(json.dumps({'before_sha256':before,'after_sha256':after,
            'manifest_sha256':hashlib.sha256(self.identity[0]).hexdigest()})+'\n')
        self.assertEqual(before,after)
        self.assertEqual((process['status'],process['actual_exit_observed'],process['automatic_retries']),('exited',True,0))
        return directory,process

    def test_admission_covers_all_in_hidden_payoffs_without_training(self):
        plans=[]
        for mode in ('ADMIT','ADMIT_PAIRED','ADMIT_PACKED','ADMIT_COMPACT','ADMIT_SCALED','ADMIT_SEALED','ADMIT_PAGED',
                     'ADMIT_DIRECTORY','ADMIT_RANK_SETS','ADMIT_SPLIT'):
            with self.subTest(mode=mode):
                directory,process=self.observe(mode.lower(),lambda p:run_bounded_dyadic_probe([str(self.exe)],mode,p))
                self.assertEqual(process['returncode'],0,(directory/'stderr.bin').read_text())
                self.assertEqual((directory/'stderr.bin').read_bytes(),b'')
                plan=validate_admission(exact_json((directory/'stdout.bin').read_bytes()),
                    paired=mode=='ADMIT_PAIRED',packed=mode=='ADMIT_PACKED',compact=mode=='ADMIT_COMPACT',
                    scaled=mode=='ADMIT_SCALED',sealed=mode=='ADMIT_SEALED',paged=mode=='ADMIT_PAGED',
                    directory=mode=='ADMIT_DIRECTORY',rank_sets=mode=='ADMIT_RANK_SETS',split=mode=='ADMIT_SPLIT')
                self.assertEqual(plan['training_invocations'],0)
                self.assertEqual(plan['rank_calls'],0)
                self.assertGreater(plan['showdown_contractions_per_pass'],plan['showdowns'])
                plans.append(plan)
        legacy,paired,packed,compact,scaled,sealed,paged,directory,rank_sets,split=plans
        self.assertLess(paired['planned_total_work'],legacy['planned_total_work'])
        self.assertEqual(packed['planned_total_work']-paired['planned_total_work'],packed['packed_average_work'])
        self.assertEqual(packed['parent_work']['average']-paired['parent_work']['average'],packed['packed_average_work'])
        self.assertEqual(packed['actual_admission_work'],paired['actual_admission_work'])
        self.assertEqual(compact['planned_total_work']-packed['planned_total_work'],compact['packed_regret_work'])
        self.assertEqual(compact['parent_work']['route']-packed['parent_work']['route'],compact['packed_regret_work'])
        self.assertEqual(compact['actual_admission_work']-packed['actual_admission_work'],8*388)
        self.assertEqual(compact['packed_average_limbs'],packed['packed_average_limbs'])
        with self.assertRaisesRegex(ValueError,'compact strategy allowance'):
            validate_admission(dict(compact,parent_allowance=compact['parent_allowance']+1),compact=True)
        self.assertEqual(compact['planned_total_work']-scaled['planned_total_work'],17_296_156)
        self.assertEqual(compact['parent_work']['average']-scaled['parent_work']['average'],17_296_156)
        self.assertEqual(compact['actual_admission_work'],scaled['actual_admission_work'])
        self.assertEqual(compact['entries'],scaled['entries'])
        with self.assertRaisesRegex(ValueError,'fixed admission census'):
            validate_admission(dict(scaled,scaled_average_build_work=0),scaled=True)
        self.assertEqual(scaled['planned_total_work']-sealed['planned_total_work'],14_669_904)
        self.assertEqual(scaled['component_work']['state']-sealed['component_work']['state'],14_483_984)
        self.assertEqual(scaled['component_work']['history']-sealed['component_work']['history'],185_920)
        self.assertEqual(sealed['actual_admission_work']-scaled['actual_admission_work'],8*388)
        self.assertEqual(sealed['parent_work'],scaled['parent_work'])
        self.assertEqual(sealed['entries'],scaled['entries'])
        with self.assertRaisesRegex(ValueError,'fixed admission census'):
            validate_admission(dict(sealed,sealed_token_count=370),sealed=True)
        self.assertEqual(paged['planned_total_work']-sealed['planned_total_work'],30_508_644)
        self.assertEqual(paged['parent_work']['route']-sealed['parent_work']['route'],30_508_644)
        self.assertEqual(paged['actual_admission_work'],sealed['actual_admission_work'])
        self.assertEqual(paged['entries'],841_925)
        self.assertEqual(directory['planned_total_work']-paged['planned_total_work'],2_344_320)
        self.assertEqual(directory['parent_work']['route']-paged['parent_work']['route'],2_344_320)
        self.assertEqual(directory['actual_admission_work'],paged['actual_admission_work'])
        self.assertEqual(directory['entries'],500_045)
        self.assertEqual(directory['planned_total_work']-rank_sets['planned_total_work'],28_490_684)
        self.assertEqual(directory['parent_work'],rank_sets['parent_work'])
        self.assertEqual(directory['entries'],rank_sets['entries'])
        self.assertEqual(rank_sets['expected_rank_calls'],7)
        self.assertEqual(rank_sets['planned_total_work']-split['planned_total_work'],9_771_552)
        self.assertEqual(rank_sets['parent_work']['route']-split['parent_work']['route'],3_722_496)
        self.assertEqual(rank_sets['parent_work']['output']-split['parent_work']['output'],6_049_056)
        self.assertEqual(rank_sets['actual_admission_work'],split['actual_admission_work'])
        self.assertEqual(split['output_bytes'],SPLIT_BYTES)
        self.assertEqual(split['checkpoint_image_bytes'],SPLIT_IMAGE_BYTES)

    def test_ten_card_admission_is_rank_free_and_profile_specific(self):
        directory,process=self.observe('admit_ten',lambda p:run_bounded_dyadic_probe([str(self.exe)],'ADMIT_TEN',p))
        self.assertEqual(process['returncode'],0,(directory/'stderr.bin').read_text())
        self.assertEqual((directory/'stderr.bin').read_bytes(),b'')
        receipt=exact_json((directory/'stdout.bin').read_bytes())
        plan=validate_admission(receipt,ten_card=True)
        self.assertEqual(plan['planned_total_work'],2_102_190_180)
        self.assertEqual((plan['rank_calls'],plan['training_invocations']), (0,0))
        with self.assertRaisesRegex(ValueError,'earlier profile'):
            validate_admission(receipt,split=True)
        with self.assertRaisesRegex(ValueError,'independent fixed census'):
            validate_admission(dict(receipt,page_request_limit=3_091_727),ten_card=True)

    def test_foreign_unframed_and_multirecord_requests_fail_closed(self):
        for index,raw in enumerate((b'DYADIC_T2_V1 TRAIN 3\n',b'DYADIC_T2_V1 ADMIT\r\n',
                b'DYADIC_T2_V1 ADMIT',b'DYADIC_T2_V1 ADMIT\nDYADIC_T2_V1 TRAIN\n',
                b'DYADIC_T2_V1 TRAIN_PAGED\n',b'DYADIC_T2_V1 TRAIN_DIRECTORY\n',
                b'DYADIC_T2_V1 TRAIN_RANK_SETS\n',b'DYADIC_T2_V1 TRAIN_SPLIT\n',
                b'DYADIC_T2_V1 TRAIN_TEN\n',b'DYADIC_T2_V1 TRAIN_TEN_BUFFERED\n',
                b'DYADIC_T2_V1 TRAIN_TEN_VIRTUAL_ZERO\n',b'DYADIC_T2_V1 TRAIN_TEN_ORDERED_STATE\n',
                b'DYADIC_T2_V1 TRAIN_TEN_ROW_COVERAGE\n',b'DYADIC_T2_V1 TRAIN_TEN_SHARED_POLICY\n',
                b'DYADIC_T2_V1 TRAIN_TEN_PAGED_DIRECTORY\n',b'DYADIC_T2_V1 TRAIN_TEN_SWEEP_STREAM\n',
                b'DYADIC_T3_V1 TRAIN_PROOF9_T3\n',b'DYADIC_T2_V1 ADMIT_PROOF9_T3\n',
                b'DYADIC_T4_V1 TRAIN_PROOF9_T4\n',b'DYADIC_T3_V1 ADMIT_PROOF9_T4\n',
                b'DYADIC_T4_V1 ADMIT_PROOF9_T3\n',
                b'DYADIC_T2_V1 TRAIN_TEN_SPARSE_CHANCE\n',b'DYADIC_T4_V1 ADMIT_TEN_SPARSE_CHANCE\n',
                b'DYADIC_T2_V1 TRAIN_TEN_SINGLE_DIVISION\n',b'DYADIC_T4_V1 ADMIT_TEN_SINGLE_DIVISION\n',
                b'DYADIC_T2_V1 TRAIN_TEN_PHASE_PAYLOAD\n',b'DYADIC_T4_V1 ADMIT_TEN_PHASE_PAYLOAD\n',
                b'DYADIC_T2_V1 TRAIN_TEN_ROW_BATCHED\n',b'DYADIC_T4_V1 ADMIT_TEN_ROW_BATCHED\n',
                b'DYADIC_T32_V1 TRAIN_PROOF9_Q32\n', b'DYADIC_T4_V1 ADMIT_PROOF9_Q32\n',
                b'DYADIC_T32_V1 ADMIT_PROOF9_T4\n', b'DYADIC_T31_V1 ADMIT_PROOF9_Q32\n',
                b'DYADIC_T33_V1 ADMIT_PROOF9_Q32\n',b'x'*65+b'\n')):
            with self.subTest(raw=raw):
                directory,process=self.observe(f'reject-{index}',lambda p:run_bounded_child(
                    [str(self.exe)],raw,p,stdout_limit=65536))
                self.assertEqual(process['returncode'],2)
                self.assertEqual((directory/'stdout.bin').read_bytes(),b'')
                self.assertTrue((directory/'stderr.bin').read_bytes().startswith(b'DYADIC_T2_V1 ERROR '))

    def test_buffered_ten_admission_reserves_its_own_work_and_write_cap(self):
        directory,process=self.observe('admit_ten_buffered',
            lambda p:run_bounded_dyadic_probe([str(self.exe)],'ADMIT_TEN_BUFFERED',p))
        self.assertEqual(process['returncode'],0,(directory/'stderr.bin').read_text())
        self.assertEqual((directory/'stderr.bin').read_bytes(),b'')
        receipt=exact_json((directory/'stdout.bin').read_bytes())
        plan=validate_admission(receipt,ten_buffered=True)
        self.assertEqual(plan['planned_total_work'],2_126_173_102)
        self.assertEqual((plan['rank_calls'],plan['training_invocations']), (0,0))
        with self.assertRaisesRegex(ValueError,'independent fixed census'):
            validate_admission(receipt,ten_card=True)
        with self.assertRaisesRegex(ValueError,'independent fixed census'):
            validate_admission(dict(receipt,page_write_request_limit=19_559),ten_buffered=True)

    def test_virtual_zero_ten_admission_reserves_physical_and_logical_work(self):
        directory,process=self.observe('admit_ten_virtual_zero',
            lambda p:run_bounded_dyadic_probe([str(self.exe)],'ADMIT_TEN_VIRTUAL_ZERO',p))
        self.assertEqual(process['returncode'],0,(directory/'stderr.bin').read_text())
        self.assertEqual((directory/'stderr.bin').read_bytes(),b'')
        receipt=exact_json((directory/'stdout.bin').read_bytes())
        plan=validate_admission(receipt,ten_virtual_zero=True)
        self.assertEqual(plan['planned_total_work'],2_126_045_678)
        self.assertEqual((plan['rank_calls'],plan['training_invocations']), (0,0))
        with self.assertRaisesRegex(ValueError,'independent fixed census'):
            validate_admission(receipt,ten_buffered=True)

    def test_ordered_state_admission_reserves_distinct_path_work_and_less_storage(self):
        directory,process=self.observe('admit_ten_ordered_state',
            lambda p:run_bounded_dyadic_probe([str(self.exe)],'ADMIT_TEN_ORDERED_STATE',p))
        self.assertEqual(process['returncode'],0,(directory/'stderr.bin').read_text())
        self.assertEqual((directory/'stderr.bin').read_bytes(),b'')
        receipt=exact_json((directory/'stdout.bin').read_bytes())
        plan=validate_admission(receipt,ten_ordered_state=True)
        self.assertEqual(plan['planned_total_work'],2_129_859_950)
        self.assertEqual((plan['entries'],plan['directory_index_slots']), (1_159_382,0))
        self.assertEqual((plan['rank_calls'],plan['training_invocations']), (0,0))
        with self.assertRaisesRegex(ValueError,'independent fixed census'):
            validate_admission(receipt,ten_virtual_zero=True)

    def test_row_coverage_admission_removes_only_the_pager_bitmap_budget(self):
        directory,process=self.observe('admit_ten_row_coverage',
            lambda p:run_bounded_dyadic_probe([str(self.exe)],'ADMIT_TEN_ROW_COVERAGE',p))
        self.assertEqual(process['returncode'],0,(directory/'stderr.bin').read_text())
        self.assertEqual((directory/'stderr.bin').read_bytes(),b'')
        receipt=exact_json((directory/'stdout.bin').read_bytes())
        plan=validate_admission(receipt,ten_row_coverage=True)
        self.assertEqual(plan['planned_total_work'],2_129_489_606)
        self.assertEqual((plan['entries'],plan['page_resident_bytes']), (1_113_089,591_008))
        self.assertEqual((plan['rank_calls'],plan['training_invocations']), (0,0))
        with self.assertRaisesRegex(ValueError,'independent fixed census'):
            validate_admission(receipt,ten_ordered_state=True)

    def test_shared_policy_admission_covers_an_all_mixed_sweep(self):
        directory,process=self.observe('admit_ten_shared_policy',
            lambda p:run_bounded_dyadic_probe([str(self.exe)],'ADMIT_TEN_SHARED_POLICY',p))
        self.assertEqual(process['returncode'],0,(directory/'stderr.bin').read_text())
        self.assertEqual((directory/'stderr.bin').read_bytes(),b'')
        receipt=exact_json((directory/'stdout.bin').read_bytes())
        plan=validate_admission(receipt,ten_shared_policy=True)
        self.assertEqual((plan['planned_total_work'],plan['entries']), (2_144_546_582,832_287))
        self.assertEqual(plan['policy_spill_word_limit'],plan['slots']-plan['rows'])
        self.assertEqual(plan['policy_spill_read_call_limit'],3*plan['rows'])
        self.assertEqual((plan['rank_calls'],plan['training_invocations']), (0,0))
        with self.assertRaisesRegex(ValueError,'independent fixed census'):
            validate_admission(receipt,ten_row_coverage=True)

    def test_paged_directory_reserves_copied_frames_and_independent_read_trace(self):
        from tests.virtual_dyadic_directory_trace import directory_trace
        directory,process=self.observe('admit_ten_paged_directory',
            lambda p:run_bounded_dyadic_probe([str(self.exe)],'ADMIT_TEN_PAGED_DIRECTORY',p))
        self.assertEqual(process['returncode'],0,(directory/'stderr.bin').read_text())
        self.assertEqual((directory/'stderr.bin').read_bytes(),b'')
        receipt=exact_json((directory/'stdout.bin').read_bytes())
        plan=validate_admission(receipt,ten_paged_directory=True)
        self.assertEqual((plan['planned_total_work'],plan['entries']), (2_129_413_526,360_303))
        self.assertEqual((plan['component_work']['state'],plan['directory_work']), (261_025_384,24_916_800))
        self.assertEqual((plan['row_directory_entries'],plan['row_directory_page_limit'],
                          plan['row_directory_read_call_limit']), (4608,7656,10*plan['rows']))
        trace=directory_trace()
        self.assertEqual(trace['misses'],plan['row_directory_page_limit'])
        self.assertEqual((plan['rank_calls'],plan['training_invocations']), (0,0))
        for altered in (dict(receipt,row_directory_page_limit=7655),
                        dict(receipt,row_directory_read_call_limit=10*plan['rows']-1)):
            with self.assertRaisesRegex(ValueError,'independent fixed census'):
                validate_admission(altered,ten_paged_directory=True)
        with self.assertRaisesRegex(ValueError,'independent fixed census'):
            validate_admission(receipt,ten_shared_policy=True)

    def test_sweep_stream_admits_both_frames_and_transport_work_without_training(self):
        directory,process=self.observe('admit_ten_sweep_stream',
            lambda p:run_bounded_dyadic_probe([str(self.exe)],'ADMIT_TEN_SWEEP_STREAM',p))
        self.assertEqual(process['returncode'],0,(directory/'stderr.bin').read_text())
        self.assertEqual((directory/'stderr.bin').read_bytes(),b'')
        receipt=exact_json((directory/'stdout.bin').read_bytes())
        plan=validate_admission(receipt,ten_sweep_stream=True)
        stream=plan['sweep_stream']
        self.assertEqual((stream['wire_bytes'],stream['retained_bytes'],stream['read_bytes']),
                         (57_236_692,9_833_076,47_403_552))
        self.assertEqual(plan['planned_total_work']+stream['copy_work'],2_141_357_150)
        self.assertEqual((plan['rank_calls'],plan['training_invocations']), (0,0))
        for field in ('wire_bytes','copy_work','image_bytes','frames'):
            altered=dict(stream,**{field:stream[field]-1})
            with self.assertRaisesRegex(ValueError,'independent fixed census'):
                validate_admission(dict(receipt,sweep_stream=altered),ten_sweep_stream=True)
        with self.assertRaisesRegex(ValueError,'independent fixed census'):
            validate_admission(receipt,ten_paged_directory=True)

    def test_proof9_t3_admits_all_epochs_without_training(self):
        self.check_bounded_proof9_admission(3)

    def test_sparse_chance_admits_the_same_game_with_lower_chance_work(self):
        directory,process=self.observe('admit_ten_sparse_chance',
            lambda p:run_bounded_dyadic_probe([str(self.exe)],'ADMIT_TEN_SPARSE_CHANCE',p))
        self.assertEqual(process['returncode'],0,(directory/'stderr.bin').read_text())
        self.assertEqual((directory/'stderr.bin').read_bytes(),b'')
        receipt=exact_json((directory/'stdout.bin').read_bytes())
        plan=validate_admission(receipt,ten_sparse_chance=True)
        self.assertEqual((plan['component_work']['chance'],plan['planned_total_work'],
                          plan['planned_total_work']+plan['sweep_stream']['copy_work']),
                         (127_793_144,1_810_140_094,1_822_083_718))
        self.assertEqual((plan['rank_calls'],plan['training_invocations']), (0,0))
        altered=dict(receipt,component_work=dict(receipt['component_work'],chance=127_793_143))
        with self.assertRaises(ValueError):
            validate_admission(altered,ten_sparse_chance=True)
        with self.assertRaises(ValueError):
            validate_admission(receipt,ten_sweep_stream=True)

    def test_quality32_admits_full_owner_lifetimes_without_training(self):
        directory,process=self.observe('admit_proof9_q32',
            lambda p:run_bounded_dyadic_probe([str(self.exe)],'ADMIT_PROOF9_Q32',p))
        self.assertEqual(process['returncode'],0,(directory/'stderr.bin').read_text())
        receipt=exact_json((directory/'stdout.bin').read_bytes())
        plan=validate_admission(receipt,proof9_quality32=True)
        self.assertEqual((plan['rank_calls'],plan['training_invocations'],plan['requested_sweeps']),(0,0,32))
        self.assertEqual((plan['value_bits'],plan['D_bits']),(644,635))
        self.assertEqual(plan['page_request_limit'],3_931_620)
        self.assertEqual(plan['planned_total_work']+plan['sweep_stream']['copy_work'],5_647_841_797)
        for key in ('requested_sweeps','value_bits','entries','payload_bits','page_request_limit'):
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_admission(dict(receipt,**{key:receipt[key]-1}),proof9_quality32=True)
        for key in ('frames','wire_bytes','copy_work','retained_bytes'):
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_admission(dict(receipt,sweep_stream=dict(receipt['sweep_stream'],
                    **{key:receipt['sweep_stream'][key]-1})),proof9_quality32=True)
        with self.assertRaises(ValueError):
            validate_admission(receipt,proof9_t4=True)

    def test_proof9_t4_admits_all_epochs_without_training(self):
        self.check_bounded_proof9_admission(4)

    def test_single_division_admits_the_same_game_with_lower_quantizer_work(self):
        directory,process=self.observe('admit_ten_single_division',
            lambda p:run_bounded_dyadic_probe([str(self.exe)],'ADMIT_TEN_SINGLE_DIVISION',p))
        self.assertEqual(process['returncode'],0,(directory/'stderr.bin').read_text())
        self.assertEqual((directory/'stderr.bin').read_bytes(),b'')
        receipt=exact_json((directory/'stdout.bin').read_bytes())
        plan=validate_admission(receipt,ten_single_division=True)
        self.assertEqual((plan['component_work']['quantizer'],plan['planned_total_work'],
                          plan['planned_total_work']+plan['sweep_stream']['copy_work']),
                         (433_472_328,1_730_311_006,1_742_254_630))
        self.assertEqual((plan['rank_calls'],plan['training_invocations']), (0,0))
        altered=dict(receipt,quantizer_terms=[51_633_888,156_086_913,225_751_528])
        with self.assertRaises(ValueError):
            validate_admission(altered,ten_single_division=True)
        with self.assertRaises(ValueError):
            validate_admission(receipt,ten_sparse_chance=True)

    def test_phase_payload_admits_exact_paged_state_without_dense_reservations(self):
        directory,process=self.observe('admit_ten_phase_payload',
            lambda p:run_bounded_dyadic_probe([str(self.exe)],'ADMIT_TEN_PHASE_PAYLOAD',p))
        self.assertEqual(process['returncode'],0,(directory/'stderr.bin').read_text())
        self.assertEqual((directory/'stderr.bin').read_bytes(),b'')
        receipt=exact_json((directory/'stdout.bin').read_bytes())
        plan=validate_admission(receipt,ten_phase_payload=True)
        self.assertEqual((plan['state_payload_bits'],plan['payload_bits'],plan['entries']),
                         (6_398_880,20_036_160,360_303))
        self.assertEqual((plan['rank_calls'],plan['training_invocations']), (0,0))
        for key in ('state_payload_bits','payload_bits'):
            with self.assertRaisesRegex(ValueError,'phase payload differs'):
                validate_admission(dict(receipt,**{key:receipt[key]-1}),ten_phase_payload=True)
        with self.assertRaises(ValueError):
            validate_admission(receipt,ten_single_division=True)

    def test_row_batched_admission_charges_contiguous_requests_and_codec(self):
        directory,process=self.observe('admit_ten_row_batched',
            lambda p:run_bounded_dyadic_probe([str(self.exe)],'ADMIT_TEN_ROW_BATCHED',p))
        self.assertEqual(process['returncode'],0,(directory/'stderr.bin').read_text())
        self.assertEqual((directory/'stderr.bin').read_bytes(),b'')
        receipt=exact_json((directory/'stdout.bin').read_bytes())
        plan=validate_admission(receipt,ten_row_batched=True)
        self.assertEqual((plan['state_payload_bits'],plan['payload_bits'],plan['entries']),
                         (6_400_992,20_038_272,360_336))
        self.assertEqual((plan['page_request_limit'],plan['paging_work'],plan['planned_total_work']),
                         (1_311_156,120_030_330,1_696_642_046))
        self.assertEqual((plan['rank_calls'],plan['training_invocations']), (0,0))
        for key in ('page_request_limit','paging_work','state_payload_bits','entries'):
            with self.assertRaisesRegex(ValueError,'row-batched admission differs'):
                validate_admission(dict(receipt,**{key:receipt[key]-1}),ten_row_batched=True)
        with self.assertRaises(ValueError):
            validate_admission(receipt,ten_phase_payload=True)

    def test_indexed_cache_admission_reserves_search_updates_and_storage(self):
        directory,process=self.observe('admit_ten_indexed_cache',
            lambda p:run_bounded_dyadic_probe([str(self.exe)],'ADMIT_TEN_INDEXED_CACHE',p))
        self.assertEqual(process['returncode'],0,(directory/'stderr.bin').read_text())
        self.assertEqual((directory/'stderr.bin').read_bytes(),b'')
        receipt=exact_json((directory/'stdout.bin').read_bytes())
        plan=validate_admission(receipt,ten_indexed_cache=True)
        self.assertEqual((plan['rank_lookup_work_per_query'],plan['rank_index_entries'],
                          plan['rank_index_update_work'],plan['rank_index_setup_work']),(46,66,248,84))
        self.assertEqual((plan['component_work']['chance'],plan['planned_total_work'],plan['parent_allowance']),
                         (132_742_404,1_701_591_306,1_180_448_724))
        self.assertEqual((plan['rank_calls'],plan['training_invocations']),(0,0))
        for key in ('rank_lookup_work_per_query','rank_index_entries','rank_index_update_work',
                    'rank_index_setup_work','planned_total_work','parent_allowance'):
            with self.assertRaisesRegex(ValueError,'sorted rank index admission differs'):
                validate_admission(dict(receipt,**{key:receipt[key]-1}),ten_indexed_cache=True)
        with self.assertRaises(ValueError):
            validate_admission(receipt,ten_row_batched=True)

    def check_bounded_proof9_admission(self,sweeps):
        from tests.virtual_dyadic_directory_trace import directory_trace
        from tests.virtual_dyadic_stage_schedule import stage_schedule
        directory,process=self.observe(f'admit_proof9_t{sweeps}',
            lambda p:run_bounded_dyadic_probe([str(self.exe)],f'ADMIT_PROOF9_T{sweeps}',p))
        self.assertEqual(process['returncode'],0,(directory/'stderr.bin').read_text())
        self.assertEqual((directory/'stderr.bin').read_bytes(),b'')
        receipt=exact_json((directory/'stdout.bin').read_bytes())
        flags={f'proof9_t{sweeps}':True}
        plan=validate_admission(receipt,**flags)
        self.assertEqual((plan['rank_calls'],plan['training_invocations'],plan['requested_sweeps']), (0,0,sweeps))
        schedule=stage_schedule(virtual_zero=True,sweeps=sweeps)
        trace=directory_trace(ten_card=False,sweeps=sweeps)
        self.assertEqual(plan['page_request_limit'],schedule['logical_read_calls']+sweeps*schedule['per_sweep_stage_calls'])
        self.assertEqual(plan['page_write_word_limit'],schedule['written_words'])
        self.assertEqual((plan['row_directory_page_limit'],plan['row_directory_read_call_limit']),
                         (trace['misses'],trace['logical_reads']))
        for field in ('requested_sweeps','general_quantizer_work','page_request_limit'):
            with self.assertRaisesRegex(ValueError,'independent fixed census'):
                validate_admission(dict(receipt,**{field:receipt[field]-1}),**flags)
        with self.assertRaisesRegex(ValueError,'fixed admission census'):
            validate_admission(receipt,split=True)


if __name__=='__main__':unittest.main()
