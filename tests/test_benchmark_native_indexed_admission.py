"""Failure and provenance gates for the fixed capacity runner; no solver runs."""
import base64
from copy import deepcopy
import json
import hashlib
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from scripts import benchmark_native_indexed_admission as study


def b64(value):
    return base64.b64encode(value).decode('ascii')


class CapacityRunnerControls(unittest.TestCase):
    def deps(self):
        return SimpleNamespace(quotient=SimpleNamespace(_runtime=lambda:{'test':'runtime'}),
            old=SimpleNamespace(validate=Mock(),ITERATIONS={},OPTIONS={}), native=SimpleNamespace(executable_identity=lambda _:{'exe':'bound'}),
            equivariant=SimpleNamespace(METRICS=('value_sb','value_bb','sb_best_response_value','bb_best_response_value',
                'sb_gain','bb_gain','nash_conv','exploitability')))

    def rejected(self,entry,native=False):
        name,t,mode=entry
        return {'case':name,'iterations':t,'native_admission':mode,'routing':'indexed','sample':0,'traced':False,
            'request_case':{'fixture':name},'runtime':{'test':'runtime'},'seconds':1.,'process_peak_bytes':1,
            'python_allocation_peak_bytes':None,'counts':{'python_trainer':0,'native_invoke':int(native),
            'python_rank':0,'rank_before_native':0 if native else None,'pair':0,'world':0,'legacy':0},
            'payload':None,'failure':{'type':'NativeFailure' if native else 'ValueError','message':'whole-request work admission exceeded'},
            'status':'native-resource-rejected' if native else 'host-admission-rejected',
            'native_observations':{'learning_completed':None if native else False,'rank_calls':None if native else 0},
            'native_streams':[{'request':b64(b'OPENPOKER_NATIVE_EXACT_FOUR_STREET_INDEXED_ADMISSION_V3\n10'),
                'stdout':b64(b''),'stderr':b64(b'native exact four-street rejected: callback-work limit exceeded\n'),'returncode':2}] if native else []}

    def complete(self):
        entry=study.SCHEDULE[1];raw=self.rejected(entry,True)
        proof={'mode':'indexed-v1','plan_legacy_lookup_removed':1,'plan_legacy_action_removed':1,
            'trainer_legacy_history_removed':1,'plan_setup_work':10,'index_setup_work':2,'router_setup_work':3,
            'trainer_history_retained':1,'marginal_calls_upper':3,'marginal_calls_actual':1,'marginal_reuse':1,
            'combined_work':30,'combined_entries':100}
        route={'combined_work':30,'combined_entries':100,'router_work_upper':4,'index_work_upper':6,'caller_work':5}
        receipt={'rank_calls':2,'retained_entries_upper':100,'indexed_admission':proof,'indexed_routing':route}
        payload={'training_backend':'native-exact-four-street-indexed-admission-v3','native_routing':'indexed',
            'native_admission':'indexed-v1','operator_census':{'native_exact':receipt}}
        raw.update(status='complete',failure=None,payload=payload,native_observations={'learning_completed':True,'rank_calls':2})
        raw['counts']['python_rank']=1
        output=b'OPENPOKER_NATIVE_EXACT_FOUR_STREET_INDEXED_ADMISSION_RESULT_V3\n'+self.admission_line(proof)
        raw['native_streams'][0].update(stdout=b64(output),stderr=b64(b''),returncode=0)
        self.rehash(raw)
        return entry,raw

    @staticmethod
    def admission_line(proof):
        return ('ADMISSION\tindexed-v1\t'+'\t'.join(f'{k}={v}' for k,v in proof.items() if k!='mode')+'\n').encode()

    @staticmethod
    def rehash(raw):
        encoded=study.canonical(raw['payload']);raw.update(payload_sha256=study.sha(encoded),payload_bytes=len(encoded))

    def test_fixed_schedule_28_and_exact_alias(self):
        self.assertEqual(len(study.SCHEDULE),28)
        self.assertEqual(len(set(study.SCHEDULE)),28)
        self.assertEqual(study.SCHEDULE[:10],tuple((name,10,mode) for name in study.BASELINES for mode in ('legacy','indexed-v1')))
        self.assertEqual(study.SCHEDULE[10:14],tuple(('original-22-t10',t,mode) for t in (20,40) for mode in ('legacy','indexed-v1')))
        matrix={(name,t,'indexed-v1') for name in study.MATRIX for t in (10,100,1000)}
        self.assertEqual(set(study.SCHEDULE[14:])|{('original-weighted-2x2',10,'indexed-v1')},matrix)
        self.assertNotIn(('original-weighted-2x2',10,'indexed-v1'),study.SCHEDULE)

    def test_child_forwards_explicit_admission_and_reuses_capture_seam_after_auth(self):
        source={'commit':'fixture','status':'','sha256':{}}
        with patch.object(study,'_AUTH',source):
            deps=study._dependencies()
        entry=study.SCHEDULE[11];observed={}
        def solve(request,**kwargs):
            observed.update(kwargs)
            return {'operator_census':{'native_exact':{'rank_calls':1}}}
        def captured(name,routing,sample,traced,executable):
            observed['iterations']=deps.old.ITERATIONS[name]
            payload=deps.solver.solve_four_street_exact_selected(object(),native_routing=routing,native_executable=executable)
            return {'failure':None,'payload':payload,'counts':{'python_trainer':0,'native_invoke':1,
                'python_rank':1,'rank_before_native':0,'pair':0,'world':0,'legacy':0},'native_streams':[]}
        with patch.object(study,'_AUTH',source),patch.object(study,'_authenticate_source',return_value=source), \
             patch.object(study,'_identity',return_value=source),patch.object(study,'_dependencies',return_value=deps), \
             patch.object(study,'validate_cases',return_value={entry[0]:{'fixture':entry[0]}}), \
             patch.object(deps.native,'executable_identity',return_value={'build':'fixture'}), \
             patch.object(deps.solver,'solve_four_street_exact_selected',side_effect=solve), \
             patch.object(deps.old,'child',side_effect=captured) as calls:
            raw=study.child(entry,Path('native.exe'))
        self.assertEqual(calls.call_count,1);self.assertEqual(raw['native_admission'],'indexed-v1')
        self.assertEqual(observed['native_admission'],'indexed-v1');self.assertEqual(observed['native_routing'],'indexed')
        self.assertEqual(observed['native_executable'],Path('native.exe'));self.assertEqual(observed['iterations'],20)

    def test_import_does_not_import_project_math(self):
        process=subprocess.run([sys.executable,'-B','-c',
            'import sys; from scripts import benchmark_native_indexed_admission; assert not any(k.startswith("pokerlab") for k in sys.modules)'],
            cwd=study.ROOT,capture_output=True)
        self.assertEqual(process.returncode,0,process.stderr.decode())
        with patch.object(study,'_AUTH',None),self.assertRaisesRegex(ValueError,'authenticate source'):
            study._dependencies()

    def test_source_authentication_accepts_only_raw_or_git_normalized_committed_blob(self):
        with TemporaryDirectory() as folder:
            root=Path(folder);raw=b'x=1\r\n';normalized=b'x=1\n';(root/'x.py').write_bytes(raw)
            oid=hashlib.sha1(b'blob '+str(len(normalized)).encode()+b'\0'+normalized).hexdigest()
            source={'commit':'fixed','status':'','sha256':{'x.py':study.sha(raw)}}
            def git(*args,**kwargs):
                if args[0]=='ls-tree':return f'100644 blob {oid}\tx.py\0'.encode()
                if args[0]=='hash-object':return (oid+'\n').encode()
                raise AssertionError(args)
            with patch.object(study,'ROOT',root),patch.object(study,'_identity',return_value=source), \
                 patch.object(study,'git',side_effect=git),patch.object(study,'_AUTH',None):
                self.assertEqual(study._authenticate_source(),source)
            with patch.object(study,'ROOT',root),patch.object(study,'_identity',return_value=source), \
                 patch.object(study,'git',side_effect=[f'100644 blob {oid}\tx.py\0'.encode(),b'wrong\n']), \
                 self.assertRaisesRegex(ValueError,'blob mismatch'):
                study._authenticate_source()

    def test_unit_fixtures_do_not_coalesce_original_order_duplicates_or_weights(self):
        pool=('Ad','As','Qd','Qs','Ac','Ah','9c','9d')
        for size in (2,4,8,16):
            text=study._unit_range('AsAd:0.5,QsQd:0.25',pool,size)
            tokens=text.split(',');keys=[frozenset((h[:2],h[2:])) for h in tokens]
            self.assertEqual(len(tokens),size);self.assertEqual(len(set(keys)),size)
            self.assertNotIn(':',text)
            self.assertEqual(keys[:2],[frozenset(('As','Ad')),frozenset(('Qs','Qd'))])
        from pokerlab.cards import expand_range
        expanded=expand_range(study._unit_range('AsAd:0.5,QsQd:0.25',pool,16))
        self.assertEqual(len(expanded),16)
        self.assertTrue(all(v==1 for v in expanded.values()))

    def test_host_and_native_resource_rejections_keep_distinct_observation_scope(self):
        entry=study.SCHEDULE[-1];deps=self.deps();cases={entry[0]:{'fixture':entry[0]}}
        for native in (False,True):
            raw=self.rejected(entry,native);study.validate(raw,entry,deps,cases)
            if native:
                raw['native_observations']['rank_calls']=0
                with self.assertRaisesRegex(ValueError,'unobserved native'):
                    study.validate(raw,entry,deps,cases)
        self.assertEqual(deps.old.validate.call_count,0)

    def test_known_indexed_schedule_scan_floor_is_a_budget_rejection(self):
        entry=study.SCHEDULE[-1]
        raw=self.rejected(entry,True)
        message='indexed router whole-work limit is below its bounded schedule scan floor'
        raw['failure']['message']='Native exact computation rejected: native exact four-street rejected: '+message
        raw['native_streams'][0]['stderr']=b64(('native exact four-street rejected: '+message+'\n').encode())
        self.assertEqual(study._resource_outcome(raw),'native-resource-rejected')
        study.validate(raw,entry,self.deps(),{entry[0]:{'fixture':entry[0]}})
        self.assertFalse(study._bounded_resource('invalid indexed router whole-work limit is below its bounded schedule scan floor'))

    def test_known_index_input_scan_remaining_work_is_a_budget_rejection(self):
        entry=study.SCHEDULE[-1]
        raw=self.rejected(entry,True)
        message='history-index bounded input scan exceeds remaining combined work before token scan'
        raw['failure']['message']='Native exact computation rejected: native exact four-street rejected: '+message
        raw['native_streams'][0]['stderr']=b64(('native exact four-street rejected: '+message+'\n').encode())
        self.assertEqual(study._resource_outcome(raw),'native-resource-rejected')
        study.validate(raw,entry,self.deps(),{entry[0]:{'fixture':entry[0]}})

    def test_rejection_classifier_does_not_hide_unrelated_errors_or_post_native_failure(self):
        entry=study.SCHEDULE[-1]
        for message in ('argument parsing failed','escape failed','strategy key missing',
                        'Indexed admission profile is stale or already reserved',
                        'Indexed admission requires an explicit reservation',
                        'admission proof identity mismatch','Missing indexed proof budget',
                        'Limits cannot exceed 500 million modeled work units'):
            raw=self.rejected(entry);raw['failure']['message']=message
            self.assertIsNone(study._resource_outcome(raw))
        raw=self.rejected(entry,True);raw['native_streams'][0]['stderr']=b64(b'native exact four-street rejected: invalid admission mode\n')
        self.assertIsNone(study._resource_outcome(raw))
        raw=self.rejected(entry,True);raw['native_streams'][0]['returncode']=0
        self.assertIsNone(study._resource_outcome(raw))
        raw=self.rejected(entry,True);raw['counts']['python_rank']=1
        self.assertIsNone(study._resource_outcome(raw))

    def test_baseline_resource_rejection_is_regression(self):
        entry=study.SCHEDULE[1];raw=self.rejected(entry)
        with self.assertRaisesRegex(ValueError,'baseline regression'):
            study.validate(raw,entry,self.deps(),{entry[0]:{'fixture':entry[0]}})

    def test_raw_header_status_and_forbidden_count_negatives(self):
        entry=study.SCHEDULE[-1];cases={entry[0]:{'fixture':entry[0]}}
        for change in ('header','status','pair','runtime','fixture','boolcount'):
            raw=self.rejected(entry,True)
            if change=='header':raw['native_streams'][0]['request']=b64(b'WRONG\n')
            if change=='status':raw['status']='unknown'
            if change=='pair':raw['counts']['pair']=1
            if change=='runtime':raw['runtime']={}
            if change=='fixture':raw['request_case']={}
            if change=='boolcount':raw['counts']['rank_before_native']=False
            with self.subTest(change=change),self.assertRaises(ValueError):study.validate(raw,entry,self.deps(),cases)

    def test_original_v3_metadata_hash_and_exact_setup_ledger_bound(self):
        entry,raw=self.complete();deps=self.deps();cases={entry[0]:raw['request_case']}
        study.validate(raw,entry,deps,cases)
        self.assertEqual(deps.old.validate.call_count,1)
        for field in ('plan_setup_work','index_setup_work','router_setup_work','combined_work'):
            forged=deepcopy(raw);proof=forged['payload']['operator_census']['native_exact']['indexed_admission'];proof[field]+=1
            self.rehash(forged)
            forged['native_streams'][0]['stdout']=b64(b'OPENPOKER_NATIVE_EXACT_FOUR_STREET_INDEXED_ADMISSION_RESULT_V3\n'+self.admission_line(proof))
            with self.subTest(field=field),self.assertRaisesRegex(ValueError,'ledger'):
                study.validate(forged,entry,deps,cases)
        forged=deepcopy(raw);forged['payload']['training_backend']='wrong';self.rehash(forged)
        with self.assertRaisesRegex(ValueError,'backend'):study.validate(forged,entry,deps,cases)

    def test_raw_admission_proof_cannot_differ_from_payload(self):
        entry,raw=self.complete();raw['native_streams'][0]['stdout']=b64(base64.b64decode(raw['native_streams'][0]['stdout']).replace(b'plan_setup_work=10',b'plan_setup_work=11'))
        with self.assertRaisesRegex(ValueError,'raw admission'):
            study.validate(raw,entry,self.deps(),{entry[0]:raw['request_case']})

    def test_first_child_failure_preserves_raw_status_manifest_and_never_retries(self):
        source={'commit':'fixture','status':'','sha256':{}};deps=self.deps()
        failed=SimpleNamespace(returncode=17,stdout=b'first raw stdout',stderr=b'first raw stderr')
        with TemporaryDirectory() as folder,patch.object(study,'_authenticate_source',return_value=source), \
             patch.object(study,'_identity',return_value=source),patch.object(study,'_dependencies',return_value=deps), \
             patch.object(study,'validate_cases',return_value={}),patch.object(study,'_run_child',return_value=failed) as calls:
            output=Path(folder)/'evidence';result=study.run(output,Path('native.exe'))
            self.assertEqual(result['outcome'],'failed');self.assertEqual(calls.call_count,1)
            first=study.label(study.SCHEDULE[0])
            self.assertEqual((output/(first+'.stdout.bin')).read_bytes(),failed.stdout)
            self.assertEqual((output/(first+'.stderr.bin')).read_bytes(),failed.stderr)
            self.assertEqual(json.loads((output/(first+'-status.json')).read_bytes())['returncode'],17)
            report=json.loads((output/'report.json').read_bytes());self.assertEqual(report['calls_attempted'],1)
            self.assertEqual(report['calls_captured'],0);self.assertTrue((output/'manifest.json').is_file())

    def test_auth_failure_still_finalizes_empty_report_and_prevents_imports(self):
        with TemporaryDirectory() as folder,patch.object(study,'_authenticate_source',side_effect=ValueError('source drift')), \
             patch.object(study,'_dependencies') as imports,patch.object(study,'_run_child') as child:
            output=Path(folder)/'evidence';result=study.run(output,Path('native.exe'))
            self.assertEqual(result['outcome'],'failed');imports.assert_not_called();child.assert_not_called()
            self.assertTrue((output/'manifest.json').is_file())
            self.assertEqual(json.loads((output/'report.json').read_bytes())['calls_attempted'],0)

    def test_source_drift_stops_before_first_child_and_retains_failure(self):
        source={'commit':'fixture','status':'','sha256':{}};deps=self.deps()
        with TemporaryDirectory() as folder,patch.object(study,'_authenticate_source',return_value=source), \
             patch.object(study,'_identity',return_value={**source,'commit':'changed'}),patch.object(study,'_dependencies',return_value=deps), \
             patch.object(study,'validate_cases',return_value={}),patch.object(study,'_run_child') as child:
            output=Path(folder)/'evidence';result=study.run(output,Path('native.exe'))
            self.assertEqual(result['outcome'],'failed');child.assert_not_called()
            self.assertTrue((output/'first-failure.json').is_file())

    def test_verifier_cap_is_unverified_and_unrelated_error_propagates(self):
        deps=self.deps();q=deps.quotient;e=deps.equivariant
        q._verify_payload=None
        q._protected_verification=lambda case,payload:q._verify_payload(case,payload)
        e.replay_policy=Mock(side_effect=ValueError('physical replay is capped at four hands'))
        e.evaluate_exact=Mock(side_effect=ValueError('physical exact model limit exceeded'))
        case={k:'' for k in ('sb_range','bb_range','config','runouts','flop_config','turn_config','river_config')}
        result=study._verify(case, {}, deps)
        self.assertIsNone(result['quality_gate']);self.assertEqual(result['numeric']['status'],'resource-unverified')
        self.assertEqual(result['exact']['status'],'resource-unverified')
        e.evaluate_exact=Mock(side_effect=ValueError('policy row is missing'))
        with self.assertRaisesRegex(ValueError,'row is missing'):study._verify(case, {}, deps)

    def test_pair_gates_check_every_metric_and_probability_bits(self):
        deps=self.deps();left={'chance_input_snapshot':{},'strategy':[{'actions':[{'probability':0.0}]}],
            **{k:1.0 for k in deps.equivariant.METRICS}}
        capped={'exact':{'status':'resource-unverified'}}
        result=study._pair(left,deepcopy(left),[capped,capped],deps)
        self.assertFalse(result['exact_comparison_verified'])
        for key in deps.equivariant.METRICS:
            right=deepcopy(left);right[key]+=2**-52
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'metric bits'):
                study._pair(left,right,[capped,capped],deps)
        right=deepcopy(left);right['strategy'][0]['actions'][0]['probability']=-0.0
        with self.assertRaisesRegex(ValueError,'policy/input'):study._pair(left,right,[capped,capped],deps)

    def test_complete_fixed_driver_has_28_children_seven_pairs_and_no_quality_inference(self):
        source={'commit':'fixed','status':'','sha256':{}};deps=self.deps()
        payload={'chance_input_snapshot':{},'strategy':[],**{k:0. for k in deps.equivariant.METRICS}}
        checked={'numeric':{'status':'resource-unverified'},'exact':{'status':'resource-unverified'},'quality_gate':None}
        calls=[]
        def child(command):
            index=int(command[command.index('--child')+1]);calls.append(index);entry=study.SCHEDULE[index]
            return SimpleNamespace(returncode=0,stdout=json.dumps({'payload':payload,'native_streams':[],
                'case':entry[0],'status':'complete','native_admission':entry[2]}).encode(),stderr=b'')
        with TemporaryDirectory() as folder,patch.object(study,'_authenticate_source',return_value=source), \
             patch.object(study,'_identity',return_value=source),patch.object(study,'_dependencies',return_value=deps), \
             patch.object(study,'validate_cases',return_value={k:{} for k in (*study.BASELINES,*study.MATRIX)}), \
             patch.object(study,'_run_child',side_effect=child),patch.object(study,'validate') as validate, \
             patch.object(study,'_verify',return_value=checked) as replay:
            output=Path(folder)/'evidence';result=study.run(output,Path('native.exe'))
            self.assertEqual(result['outcome'],'complete');self.assertEqual(calls,list(range(28)))
            self.assertEqual(validate.call_count,28);self.assertEqual(replay.call_count,28)
            report=json.loads((output/'report.json').read_bytes())
            self.assertEqual(report['calls_attempted'],28);self.assertEqual(len(report['paired_identities']),7)
            self.assertTrue(all(v['quality_gate'] is None for v in report['verification_status'].values()))
            self.assertEqual(len(list(output.glob('*.stdout.bin'))),28)

    def test_protected_math_failure_stops_after_preserving_completed_raw_call(self):
        source={'commit':'fixed','status':'','sha256':{}};deps=self.deps()
        raw={'payload':{},'native_streams':[],'case':study.SCHEDULE[0][0],'status':'complete'}
        process=SimpleNamespace(returncode=0,stdout=json.dumps(raw).encode(),stderr=b'raw retained stderr')
        with TemporaryDirectory() as folder,patch.object(study,'_authenticate_source',return_value=source), \
             patch.object(study,'_identity',return_value=source),patch.object(study,'_dependencies',return_value=deps), \
             patch.object(study,'validate_cases',return_value={study.SCHEDULE[0][0]:{}}),patch.object(study,'validate'), \
             patch.object(study,'_run_child',return_value=process) as calls, \
             patch.object(study,'_verify',side_effect=AssertionError('production path during replay')):
            output=Path(folder)/'evidence';result=study.run(output,Path('native.exe'))
            self.assertEqual(result['outcome'],'failed');self.assertEqual(calls.call_count,1)
            report=json.loads((output/'report.json').read_bytes());self.assertEqual(report['calls_captured'],1)
            self.assertEqual((output/(study.label(study.SCHEDULE[0])+'.stdout.bin')).read_bytes(),process.stdout)

    def test_protected_math_cannot_mutate_captured_raw_or_policy(self):
        source={'commit':'fixed','status':'','sha256':{}};deps=self.deps()
        raw={'payload':{'original':1},'native_streams':[],'case':study.SCHEDULE[0][0],'status':'complete'}
        process=SimpleNamespace(returncode=0,stdout=json.dumps(raw).encode(),stderr=b'')
        for target in ('raw','policy'):
            with self.subTest(target=target),TemporaryDirectory() as folder:
                output=Path(folder)/'evidence'
                def mutate(case,payload,dependencies):
                    if target=='raw':(output/(study.label(study.SCHEDULE[0])+'.stdout.bin')).write_bytes(b'changed')
                    else:payload['original']=2
                    return {'numeric':{'status':'resource-unverified'},'exact':{'status':'resource-unverified'},'quality_gate':None}
                with patch.object(study,'_authenticate_source',return_value=source),patch.object(study,'_identity',return_value=source), \
                     patch.object(study,'_dependencies',return_value=deps),patch.object(study,'validate_cases',return_value={study.SCHEDULE[0][0]:{}}), \
                     patch.object(study,'validate'),patch.object(study,'_run_child',return_value=process) as calls,patch.object(study,'_verify',side_effect=mutate):
                    result=study.run(output,Path('native.exe'))
                self.assertEqual(result['outcome'],'failed');self.assertEqual(calls.call_count,1)
                self.assertTrue((output/'first-failure.json').is_file())


if __name__=='__main__':unittest.main()
