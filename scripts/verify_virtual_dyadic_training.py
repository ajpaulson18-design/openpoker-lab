"""Read one saved PROOF9 T2 binary and verify its complete numerical lifecycle."""
import argparse
from contextlib import contextmanager, ExitStack
from fractions import Fraction
import hashlib
import json
import os
from pathlib import Path
import stat
import struct
import time

from tests.virtual_dyadic_training_reference import D, OCCURRENCES, Q, ROWS, SLOTS, Fixture, require
from tests.virtual_frozen_saved_review import unlinked_path
from tests.virtual_frozen_update_reference import scaled_proof9_ranges

WORD = struct.Struct('<Q')
UINT64_MAX = (1<<64)-1
INT_WORDS = 11
VALUE_BITS = 642
PHASE = {'decision':0,'reveal':1,'fold':2,'showdown':3}
MAGIC = b'OPLDYA01'
END = b'OPLDEND1'
SPLIT_MAGIC = b'OPLDSP01'
SPLIT_END = b'OPLDSP02'
SPLIT_IMAGE_NAMES = ('staged.bin','committed.bin')
SPLIT_IMAGE_BYTES = 606_730*8
TOTAL_BYTES = (8+16*8+INT_WORDS*8+96*OCCURRENCES+24*ROWS
               +2*(8*SLOTS+2*INT_WORDS*8*SLOTS+4*(1+INT_WORDS)*8)
               +8*SLOTS+ROWS+8+64*8)
SPLIT_BYTES = TOTAL_BYTES-4*INT_WORDS*8*SLOTS
FAMILIES = ('template','chance','history','state','quantizer','parent')
PARENT = ('geometry','visit','support','reach','value_add','terminal_scale','average','route','output')
CHANCE = ('prior_work','setup_work','input_work','cache_lookup_work','rank_work','sort_work',
          'contraction_work','completed_contractions','rank_calls','cache_hits','cache_misses',
          'cache_evictions','peak_live_entries','peak_integer_payload_bits','peak_integer_bits')
SHAPE = ('visits','actions','reveals','candidates','folds','showdowns','rows','slots')
EXPECTED_SHAPE = (61099,57363,3735,15662,16631,17356,ROWS,SLOTS)
EXPECTED_TERMINAL_COMPLETIONS = (18180,22168)


class Reader:
    def __init__(self, stream, limit=TOTAL_BYTES):
        self.stream=stream
        self.limit=limit
        self.bytes=0
        self.digest=hashlib.sha256()

    def read(self,n):
        require(0<=n<=self.limit-self.bytes,'saved output read allowance')
        data=self.stream.read(n)
        require(len(data)==n,'truncated saved output')
        self.bytes+=n
        self.digest.update(data)
        return data

    def words(self,n):
        return tuple(x[0] for x in WORD.iter_unpack(self.read(8*n)))

    def natural(self):
        value=int.from_bytes(self.read(INT_WORDS*8),'little')
        require(value.bit_length()<=VALUE_BITS,'saved fixed integer width')
        return value

    def signed(self):
        sign,=self.words(1)
        magnitude=self.natural()
        require(sign in (0,1) and (magnitude or not sign),'saved signed magnitude framing')
        return -magnitude if sign else magnitude

    def finish(self,expected_sha256):
        require(self.bytes==self.limit and not self.stream.read(1),'saved trailing or missing output bytes')
        require(self.digest.hexdigest()==expected_sha256,'saved parsed digest differs')


@contextmanager
def authenticated_reader(path,expected_sha256,limit,*,private=False):
    path=unlinked_path(path)
    require(path.is_file(),'saved input must be a regular file')
    require(type(expected_sha256) is str and len(expected_sha256)==64
            and all(c in '0123456789abcdef' for c in expected_sha256),'expected retained sha256')
    with path.open('rb') as stream:
        info=os.fstat(stream.fileno())
        require(stat.S_ISREG(info.st_mode) and info.st_size==limit,'saved input byte count')
        require(not private or info.st_nlink==1,'split input must have one link')
        digest=hashlib.sha256()
        remaining=limit
        while remaining:
            block=stream.read(min(1<<20,remaining))
            require(bool(block),'saved hash read truncation')
            remaining-=len(block);digest.update(block)
        require(not stream.read(1) and digest.hexdigest()==expected_sha256,'saved input sha256 differs')
        stream.seek(0)
        yield Reader(stream,limit),(info.st_dev,info.st_ino)


def compact_scales(fixture):
    actors=[]
    depths=[]
    suffix=[0]*OCCURRENCES
    for node_id,parent,_,_,_ in fixture.paths:
        node=fixture.nodes[node_id]
        depth=[0,0] if parent is None else depths[parent].copy()
        if parent is not None and actors[parent] is not None:
            depth[actors[parent]]+=1
        depths.append(depth)
        actors.append(node.state.player if node.phase=='decision' else None)
    for i in reversed(range(OCCURRENCES)):
        suffix[i]+=int(actors[i] is not None)
        parent=fixture.paths[i][1]
        if parent is not None:
            suffix[parent]=max(suffix[parent],suffix[i])
    require(suffix[0]==12,'split reference decision horizon')
    return [(625-52*(depths[i][actor]+1),52*(12-depths[i][1-actor]-suffix[i])) if actor is not None else None
            for i,actor in enumerate(actors)]


def check_compact_checkpoint(reader,ordered,row_scales,regrets,average,sweep):
    # The compact file stores average limbs before regret limbs.
    for field,(family,values) in enumerate((('average',average),('regret',regrets))):
        for (key,menu),scales in zip(ordered,row_scales,strict=True):
            shift=scales[field]
            require(0<=shift<VALUE_BITS,'split reference compact shift')
            width=8*((VALUE_BITS-shift+63)//64)
            compact=tuple(int.from_bytes(reader.read(width),'little') for _ in range(menu))
            require(all(value.bit_length()<=VALUE_BITS-shift for value in compact),'saved compact integer width')
            require(tuple(value<<shift for value in compact)==values[key],
                    f'saved split {family} mismatch sweep {sweep}: {key}')


def replay(path,expected_sha256,*,paired=False,rank_sets=False,images=None):
    """Verify the exact retained grid/updates/BR; no native solver is invoked."""
    started=time.perf_counter()
    split=images is not None
    if split:
        images=tuple(images)
    require(not rank_sets or paired,'rank-set replay requires paired training')
    require(not split or (rank_sets and tuple(Path(p).name for p,_ in images)==SPLIT_IMAGE_NAMES),
            'split replay requires the ordered pair of rank-set sweep images')
    size=SPLIT_BYTES if split else TOTAL_BYTES
    with ExitStack() as stack:
        r,identity=stack.enter_context(authenticated_reader(path,expected_sha256,size,private=split))
        checkpoints=[]
        identities={identity}
        for page,digest in images or ():
            reader,identity=stack.enter_context(authenticated_reader(page,digest,SPLIT_IMAGE_BYTES,private=True))
            require(identity not in identities,'split inputs alias')
            identities.add(identity)
            checkpoints.append((reader,digest))
        require(r.read(8)==(SPLIT_MAGIC if split else MAGIC),'saved training magic')
        require(r.words(16)==(1,52,INT_WORDS,ROWS,SLOTS,OCCURRENCES,2,12,1,635,VALUE_BITS,size,2,2,29,20),
                'saved fixed fixture or integer contract')
        require(r.natural()==D,'saved fixed game denominator')
        fixture=Fixture()
        for i,(node_id,parent,token,street,edge) in enumerate(fixture.paths):
            node=fixture.nodes[node_id]
            actor=node.state.player if node.phase=='decision' else 255
            next_street=node.state.board_length if node.phase=='reveal' else 0
            winner=node.state.winner if node.phase=='fold' else 255
            shape=(PHASE[node.phase]|street<<8|actor<<16|next_street<<24|winner<<32|len(node.edges)<<40)
            expected=(token or '').encode('ascii')
            record=r.words(4)
            require(record==(UINT64_MAX if parent is None else parent,UINT64_MAX if edge is None else edge,shape,len(expected)),
                    f'saved literal skeleton mismatch at {i}')
            require(r.read(64)==expected.ljust(64,b'\0'),f'saved literal token mismatch at {i}')
        ordered=[]
        shifts=compact_scales(fixture) if split else None
        row_scales=[]
        offset=0
        for i,key in enumerate(fixture.ordered_rows()):
            require(i<ROWS,'reference ordered row cap')
            history,packed,at=r.words(3)
            actor,holding,menu=packed&255,(packed>>8)&255,(packed>>16)&255
            require(packed>>24==0 and menu==len(fixture.menus[key]) and at==offset,'saved row metadata or offset')
            require(fixture.compact_key(history,actor,holding)==key,f'saved row key/order mismatch at {i}')
            if split:
                row_scales.append(shifts[history>>33])
            ordered.append((key,menu));offset+=menu
        require(len(ordered)==ROWS and offset==SLOTS,'saved complete ordered row inventory')
        regrets=average=first=None
        changes=0
        sweeps=[]
        for t in (1,2):
            expected=fixture.grid(regrets)
            policy={}
            for key,menu in ordered:
                units=r.words(menu)
                require(units==expected[key],f'saved current grid mismatch sweep {t}: {key}')
                policy[key]=units
            if t==1:first=policy
            else:changes=sum(first[k]!=policy[k] for k in first)
            regrets,average,root=fixture.sweep(policy,regrets,average,root_holding_values=True)
            if split:
                page,digest=checkpoints[t-1]
                check_compact_checkpoint(page,ordered,row_scales,regrets,average,t)
                page.finish(digest)
            else:
                for family,values in [('regret',regrets),('average',average)]:
                    for key,menu in ordered:
                        require(tuple(r.natural() for _ in range(menu))==values[key],f'saved {family} mismatch sweep {t}: {key}')
            require(tuple(Fraction(r.signed(),D) for _ in range(4))==root,f'saved four root values mismatch sweep {t}')
            require(sum(root)==0,'replayed root value is not zero sum')
            sweeps.append({'sweep':t,'root_holding_values':[fraction(x) for x in root],
                           'row_count':ROWS,'regret_comparisons':SLOTS,'average_comparisons':SLOTS})
        require(changes>0,'saved T2 feedback missing')
        expected=fixture.grid(average,average=True)
        saved={}
        for key,menu in ordered:
            units=r.words(menu)
            require(units==expected[key],f'saved exported average grid mismatch: {key}')
            saved[key]=units
        require(r.read(ROWS)==bytes(not any(average[key]) for key,_ in ordered),'saved average fallback flags')
        require(r.read(8)==(SPLIT_END if split else b'OPLDEND2' if paired else END),'saved complete footer magic')
        plan=dict(zip(FAMILIES,r.words(6)));actual=dict(zip(FAMILIES,r.words(6)))
        parent_plan=dict(zip(PARENT,r.words(9)));parent_actual=dict(zip(PARENT,r.words(9)))
        shape=r.words(8)
        entries,payload,expected_rank_calls=r.words(3)
        chance=dict(zip(CHANCE,r.words(15)))
        feedback,=r.words(1)
        completed,passes,invocations,history_entries,history_bytes,state_entries,state_payload=r.words(7)
        r.finish(expected_sha256)
    require(shape==EXPECTED_SHAPE and (completed,passes,invocations)==(2,2 if paired else 4,1),
            'saved run shape/iteration counters')
    require(feedback==changes,'saved feedback receipt differs')
    require(sum(plan.values())<=500_000_000 and all(0<actual[k]<=plan[k] for k in plan),'saved composed work receipt')
    require(sum(parent_plan.values())==plan['parent'] and sum(parent_actual.values())==actual['parent']
            and all(parent_actual[k]<=parent_plan[k] for k in parent_plan),'saved parent family composition')
    require(sum(chance[k] for k in CHANCE[:7])==actual['chance'],'saved chance category composition')
    ranges=scaled_proof9_ranges()
    boards={w.board for w in fixture.worlds}
    if rank_sets:
        boards={frozenset(board) for board in boards}
    ranks=sum(set(hand).isdisjoint(board) for board in boards for side in ranges for hand,_ in side)
    ranked,hidden=fixture.terminal_completion_counts()
    require((ranked,hidden)==EXPECTED_TERMINAL_COMPLETIONS,'independent all-in completion census')
    require(chance['rank_calls']==expected_rank_calls==ranks and chance['cache_misses']==len(boards)
            and chance['cache_evictions']==0 and chance['cache_hits']+chance['cache_misses']==4*ranked,
            'saved rank-plane reuse accounting')
    if rank_sets:
        planes=len(boards)
        require(chance['rank_work']==4096*ranks and chance['sort_work']==512*planes and
                chance['cache_lookup_work']<=2*planes*4*ranked+planes*(4*planes+64),
                'saved rank-set work exceeds cache accounting')
    require(chance['completed_contractions']==4*(shape[4]+ranked+shape[2]+1),'saved terminal and marginal call accounting')
    require(0<history_bytes<=32<<20 and 0<chance['peak_integer_bits']<=65536
            and 0<history_entries+state_entries+chance['peak_live_entries']<=entries<=2_000_000
            and 0<state_payload+chance['peak_integer_payload_bits']<=payload<=1<<30,'saved composed storage receipt')
    quality=fixture.quality(saved)
    result={'status':'saved_two_sweep_exact_replay_pass','scope':'PROOF9 only; saved grid quality, no wider game or target pass',
            'saved_output_sha256':expected_sha256,'bytes':size,'sweeps':sweeps,'changed_current_rows':changes,
            'profile_and_br':{k:[fraction(x) for x in v] if isinstance(v,tuple) else fraction(v) for k,v in quality.items()},
            'shape':dict(zip(SHAPE,shape)),'work_plan':plan,'work_actual':actual,'chance_actual':chance,
            'showdown_contractions_per_pass':ranked,'hidden_completion_candidates_per_pass':hidden,
            'parent_work_plan':parent_plan,'parent_work_actual':parent_actual,
            'planned_entries':entries,'planned_payload_bits':payload,
            'native_producer_calls':0,'quality_gate':None,'duration_seconds':time.perf_counter()-started,
            'public_walks_per_sweep':passes//completed,
            'source_and_observed_producer_exit':'separate mandatory acceptance checks'}
    if split:
        result['checkpoint_images']=[{'name':Path(p).name,'sha256':sha,'bytes':SPLIT_IMAGE_BYTES}
                                     for p,sha in images]
    return result


def fraction(value):
    return {'numerator':str(value.numerator),'denominator':str(value.denominator),'approx':float(value)}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--saved',type=Path,required=True)
    parser.add_argument('--sha256',required=True)
    parser.add_argument('--paired',action='store_true')
    parser.add_argument('--rank-sets',action='store_true')
    parser.add_argument('--page-images',type=Path)
    parser.add_argument('--sweep-image-sha256',nargs=2,metavar=('SWEEP1','SWEEP2'))
    args=parser.parse_args()
    if (args.page_images is None)!=(args.sweep_image_sha256 is None):
        parser.error('page image directory and both sweep digests are required together')
    images=tuple((args.page_images/name,digest) for name,digest in
                 zip(SPLIT_IMAGE_NAMES,args.sweep_image_sha256,strict=True)) if args.page_images is not None else None
    print(json.dumps(replay(args.saved,args.sha256,paired=args.paired,rank_sets=args.rank_sets,images=images),sort_keys=True))


if __name__=='__main__':main()
