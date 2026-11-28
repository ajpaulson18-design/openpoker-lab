"""Lossless representation audit of admitted T2 states; no new Store or training."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
from scripts.run_opponent_action_study import ROOT,closure,git,need


def compact(rr,aa):
    need(type(rr) is tuple and type(aa) is tuple and 2<=len(rr)<=4 and len(rr)==len(aa) and
         all(type(x) is int and abs(x).bit_length()<=631 and x%(1<<260)==0 for x in rr) and
         all(type(x) is int and 0<=x and x.bit_length()<=366 and x%(1<<312)==0 for x in aa),
         'role storage exact canonical carrier/sign/width')
    r=tuple(x//(1<<260) for x in rr);a=tuple(x//(1<<312) for x in aa)
    need(tuple(x<<260 for x in r)==rr and tuple(x<<312 for x in a)==aa and
         all(abs(x).bit_length()<=371 for x in r) and all(x.bit_length()<=54 for x in a),
         'role storage exact compact carrier roundtrip')
    return r,a


def audit(output):
    output=Path(output).resolve();need(output.parent==ROOT.parent.resolve() and not output.exists(),'role storage fresh external audit')
    names=closure(('scripts/audit_opponent_role_storage.py','scripts/replay_opponent_role_walk.py','tests/virtual_role_walk_wire_reference.py'))
    need(not git('status','--porcelain','--untracked-files=all','--',*names),'role storage complete audit source committed')
    head=git('rev-parse','HEAD').decode().strip();tree={line.split('\t',1)[1]:line.split('\t',1)[0].split()[2] for line in git('ls-tree','-r',head).decode().splitlines()}
    output.mkdir()
    for name,body in names.items():
        path=output/'source'/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(body)
    (output/'source-identity.json').write_text(json.dumps({'head':head,'raw_sha256':{n:sha256(b).hexdigest() for n,b in names.items()},
        'committed_blobs':{n:tree[n] for n in names}},indent=2)+'\n')
    # Admit original source/build/process closure and recompute all original
    # coordinates before interpreting their prospective storage representation.
    from scripts import replay_opponent_role_walk as saved,joint_evidence_archive as archive,replay_joint_two_epoch_packet as helper
    replay=saved.replay();(output/'independent-whole-walk-replay.json').write_text(json.dumps(replay,indent=2)+'\n')
    manifest,loaded,pins=archive.load(saved.PACKET,helper,pin=saved.PIN,version='opponent-role-walk',
        labels=('observations','builds','objects'),packager='package_opponent_role_walk1.py.txt')
    from tests.virtual_role_walk_wire_reference import parse,receipts,request_tapes
    # Separate bounded post-replay audit: at most24 snapshots, 7,344 rows,
    # 29,376 action slots and 58,752 canonical R/A coordinates. The native
    # lifetime and all original training/reference reservations stay unchanged.
    limits={'snapshots':24,'rows':7344,'slots':29376,'coordinates':58752,'integer_bits':1024}
    reports=[];rows=slots=coordinates=0;maximum_r=maximum_a=0
    totals={'canonical_numeric_bits':0,'compact_numeric_bits':0,'canonical_nonzero_limb_words':0,
        'compact_nonzero_limb_words':0,'canonical_logical_row_bits':0,'compact_same_descriptor_row_bits':0,
        'nonzero_regret_coordinates':0,'nonzero_average_coordinates':0}
    for profile in (0,1):
        for label in ('same-world','boundaries','shared-flop-future','sb-loss','sb-win','shared-board-distinct-holding'):
            prefix=f'matrix/normal/profile-{profile}-{label}';protocol=helper.decode(loaded['observations'][prefix+'/protocol.json'])
            selectors=tuple(tuple(x) for x in protocol['selectors']);request=loaded['observations'][prefix+'/request.bin']
            records=parse(loaded['observations'][prefix+'/native/stdout.bin'],profile,selectors,request_tapes(request,profile,selectors));receipts(records)
            for epoch,record in enumerate(records,1):
                count=len(record['snapshot']);action_slots=sum(len(x[0]) for x in record['snapshot'].values())
                values={key:0 for key in totals};snapshots=[]
                rows+=count;slots+=action_slots;coordinates+=2*action_slots
                need(rows<=limits['rows'] and slots<=limits['slots'] and coordinates<=limits['coordinates'],'role storage fixed batch geometry')
                for key,(rr,aa,units) in record['snapshot'].items():
                    r,a=compact(rr,aa)
                    # Common positive scaling preserves every pairwise ratio
                    # exactly, hence the existing same tie-ordered matching
                    # policy. No allocator, averaging law or approximation is
                    # substituted by this read-only prospective conversion.
                    canonical_bits=sum(abs(x).bit_length() for x in (*rr,*aa));small_bits=sum(abs(x).bit_length() for x in (*r,*a))
                    nz_r=sum(x!=0 for x in rr);nz_a=sum(x!=0 for x in aa)
                    need(canonical_bits-small_bits==260*nz_r+312*nz_a,'role storage exact removable-padding identity')
                    values['canonical_numeric_bits']+=canonical_bits;values['compact_numeric_bits']+=small_bits
                    values['canonical_nonzero_limb_words']+=sum((abs(x).bit_length()+63)//64 for x in (*rr,*aa))
                    values['compact_nonzero_limb_words']+=sum((abs(x).bit_length()+63)//64 for x in (*r,*a))
                    descriptor=2048+64*len(units)
                    values['canonical_logical_row_bits']+=descriptor+canonical_bits
                    values['compact_same_descriptor_row_bits']+=descriptor+small_bits
                    values['nonzero_regret_coordinates']+=nz_r;values['nonzero_average_coordinates']+=nz_a
                    maximum_r=max(maximum_r,*(abs(x).bit_length() for x in r));maximum_a=max(maximum_a,*(x.bit_length() for x in a))
                    snapshots.append({'identity':key,'compact_regrets':r,'compact_averages':a,'unchanged_units':units})
                for name in totals:totals[name]+=values[name]
                reports.append({'case':f'profile-{profile}-{label}','epoch':epoch,'rows':count,'slots':action_slots,**values})
                (output/f'profile-{profile}-{label}-epoch-{epoch}.json').write_text(json.dumps(snapshots,indent=2)+'\n')
    # Misaligned/negative/wide values must refuse rather than round/truncate.
    refused=0
    for rr,aa in (((1,0),(0,0)),((0,0),(1,0)),((0,0),(-(1<<312),0)),((1<<632,0),(0,0))):
        try:compact(rr,aa)
        except ValueError:refused+=1
        else:raise ValueError('role storage invalid carrier accepted')
    need(refused==4 and len(reports)==limits['snapshots'] and git('rev-parse','HEAD').decode().strip()==head and
         all((ROOT/n).read_bytes()==b for n,b in names.items()),'role storage controls/source drift')
    need(archive.load(saved.PACKET,helper,pin=saved.PIN,version='opponent-role-walk',labels=('observations','builds','objects'),
        packager='package_opponent_role_walk1.py.txt')[2]==pins,'role storage original packet drift')
    result={'status':'role-persistent-storage-representation-audited','source_head':head,'source_files':len(names),
        'original_packet_pin':saved.PIN,'original_numeric_replay_coordinates':replay['numeric_coordinates'],'limits':limits,
        'snapshots':len(reports),'rows_counted_with_repeated_epochs':rows,'slots':slots,'coordinates':coordinates,
        'compact_max_regret_bits':maximum_r,'compact_max_average_bits':maximum_a,'totals':totals,'cases':reports,
        'invalid_carrier_refusals':refused,'native_calls':0,'archived_source_executed':False,'compact_store_implemented':False,
        'quality_gate':None,'supported_native_epochs':2,
        'scope':'Exact lossless conversion of twelve separately trained saved T2 cases, both snapshots. Totals sum separate experiments and epochs, not one combined policy. Logical same-descriptor and nonzero-limb models, not allocator capacity/RSS, runtime or longer-lifetime admission.'}
    (output/'result.json').write_text(json.dumps(result,indent=2)+'\n');return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('output',type=Path)
    print(json.dumps(audit(p.parse_args().output),indent=2))
