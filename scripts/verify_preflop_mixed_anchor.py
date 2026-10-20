"""Recheck immutable mixed-game training evidence against the new exact value.

This derives logical anchor checks from already published policies; it does
not rerun training, change the original experiment or add a measured gate.
"""
from fractions import Fraction
import json
from pathlib import Path
from scripts import benchmark_preflop_mixed_range as training
from scripts import certify_preflop_mixed_sequence as exact
from scripts.benchmark_preflop_covered_counts import checksum

ROOT=Path(__file__).resolve().parents[1]
TRAINING=ROOT/'benchmarks/results/preflop-mixed-physical-range-v1.json'
EXACT=ROOT/'benchmarks/results/preflop-mixed-exact-witness-v1.json'
TRAINING_SHA='907bccab88fff5e58d41c404ecd20aa4fcd5a5e9dd70fe2cb10b571244210930'
EXACT_SHA='ed3512d35f03e2e7ed9e7440b73923670ca2412779a3e2dee97e79ad478d1ebb'


def derive():
    data=json.loads(TRAINING.read_bytes());proof=json.loads(EXACT.read_bytes())
    if data.get('artifact_sha256')!=TRAINING_SHA or proof.get('artifact_sha256')!=EXACT_SHA:
        raise ValueError('Pinned mixed trainer or exact proof identity changed')
    fresh_training=training.verify_saved(TRAINING);fresh_proof=exact.verify_saved(EXACT)
    value=Fraction(fresh_proof['profile_value_sb_fraction']);rows=[]
    for row in data['profiles']:
        for sample in row['samples']:
            metrics=sample['assessment']['independent_replay']
            profile=Fraction(*metrics['value_sb_fraction']);sb=Fraction(*metrics['sb_best_response_fraction'])
            bb=Fraction(*metrics['bb_best_response_fraction']);gap=Fraction(*metrics['nash_conv_fraction'])
            error=abs(profile-value)
            if not -bb<=value<=sb or error>gap or sb+bb!=gap:
                raise ValueError('Exact mixed anchor is inconsistent with the independent profile response bracket')
            rows.append({'iterations':row['iterations'],'backend':sample['backend'],'repeat':sample['repeat'],
                         'policy_payload_sha256':sample['payload_sha256'],'profile_value_sb_fraction':str(profile),
                         'exact_value_error_fraction':str(error),'nash_conv_fraction':str(gap),
                         'bracket_sb_fraction':[str(-bb),str(sb)],'exact_anchor_contained':True,
                         'value_error_within_nash_conv':True,
                         'original_quality_target_met':sample['assessment']['quality_pass']})
    if len(rows)!=10:raise ValueError('Expected all ten unchanged published policies')
    result={'schema_version':1,'artifact_id':'preflop-mixed-training-exact-anchor-v1','status':'passed',
            'training_artifact_sha256':TRAINING_SHA,'exact_proof_artifact_sha256':EXACT_SHA,
            'fresh_training_verification':fresh_training,'fresh_exact_proof_verification':fresh_proof,
            'exact_value_sb_fraction':str(value),'policies':rows,
            'scope':'Derived strict anchor/value-error checks of ten unchanged published policies. No new training, timing or original acceptance-gate change.'}
    result['artifact_sha256']=checksum(result)
    return result
