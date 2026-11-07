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

from scripts.dyadic_checkpoint_transport import PageReader, packed_ceiling
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
TEN_CARD_SPLIT_MAGIC = b'OPLDTP01'
TEN_CARD_SPLIT_END = b'OPLDTP02'
TEN_CARD_ROWS = 119_196
TEN_CARD_SLOTS = 281_066
TEN_CARD_VALUE_BITS = 644
TEN_CARD_DENOMINATOR = 3480 << 625
TEN_CARD_SPLIT_BYTES = 9_833_076
TEN_CARD_IMAGE_BYTES = 2_962_722 * 8
TEN_CARD_SHAPE = (288946,270487,18458,49182,77857,88290,TEN_CARD_ROWS,TEN_CARD_SLOTS)
TEN_CARD_TERMINAL_COMPLETIONS = (103020,70912)
TEN_CARD_WORK_LIMIT = 2_150_000_000
TEN_CARD_PAYLOAD_LIMIT = 1_200_000_000
SPLIT_IMAGE_NAMES = ('staged.bin','committed.bin')
PACKED_IMAGE_NAMES = ('staged.pgi','committed.pgi')
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
    def __init__(self, stream, limit=TOTAL_BYTES, value_bits=VALUE_BITS):
        self.stream=stream
        self.value_bits=value_bits
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
        require(value.bit_length()<=self.value_bits,'saved fixed integer width')
        return value

    def signed(self):
        sign,=self.words(1)
        magnitude=self.natural()
        require(sign in (0,1) and (magnitude or not sign),'saved signed magnitude framing')
        return -magnitude if sign else magnitude

    def finish(self,expected_sha256):
        require(self.bytes==self.limit and not self.stream.read(1),'saved trailing or missing output bytes')
        require(self.digest.hexdigest()==expected_sha256,'saved parsed digest differs')


def check_digest(stream,expected_sha256,extent):
    stream.seek(0)
    digest=hashlib.sha256()
    remaining=extent
    while remaining:
        block=stream.read(min(1<<20,remaining))
        require(bool(block),'saved hash read truncation')
        remaining-=len(block);digest.update(block)
    require(not stream.read(1) and digest.hexdigest()==expected_sha256,'saved input sha256 differs')
    stream.seek(0)


@contextmanager
def authenticated_file(path,expected_sha256,limit,*,private=False,exact=True):
    path=unlinked_path(path)
    require(path.is_file(),'saved input must be a regular file')
    require(type(expected_sha256) is str and len(expected_sha256)==64
            and all(c in '0123456789abcdef' for c in expected_sha256),'expected retained sha256')
    with path.open('rb') as stream:
        info=os.fstat(stream.fileno())
        require(stat.S_ISREG(info.st_mode) and (info.st_size==limit if exact else 0<info.st_size<=limit),
                'saved input byte count')
        require(not private or info.st_nlink==1,'split input must have one link')
        check_digest(stream,expected_sha256,info.st_size)
        yield stream,info


@contextmanager
def authenticated_reader(path,expected_sha256,limit,*,private=False,value_bits=VALUE_BITS):
    with authenticated_file(path,expected_sha256,limit,private=private) as (stream,info):
        yield Reader(stream,limit,value_bits),(info.st_dev,info.st_ino)


@contextmanager
def authenticated_packed_reader(path,packed_sha256,decoded_sha256,raw_bytes,value_bits):
    with authenticated_file(path,packed_sha256,packed_ceiling(raw_bytes),private=True,exact=False) as (stream,info):
        pages=PageReader(stream,raw_bytes,info.st_size)
        require(pages.decoded_sha256()==decoded_sha256,'saved decoded checkpoint sha256 differs')
        yield (Reader(pages,raw_bytes,value_bits),(info.st_dev,info.st_ino),info.st_size)
        check_digest(stream,packed_sha256,info.st_size)


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


def check_compact_checkpoint(reader,ordered,row_scales,regrets,average,sweep,value_bits=VALUE_BITS):
    # The compact file stores average limbs before regret limbs.
    for field,(family,values) in enumerate((('average',average),('regret',regrets))):
        for (key,menu),scales in zip(ordered,row_scales,strict=True):
            shift=scales[field]
            require(0<=shift<value_bits,'split reference compact shift')
            width=8*((value_bits-shift+63)//64)
            compact=tuple(int.from_bytes(reader.read(width),'little') for _ in range(menu))
            require(all(value.bit_length()<=value_bits-shift for value in compact),'saved compact integer width')
            require(tuple(value<<shift for value in compact)==values[key],
                    f'saved split {family} mismatch sweep {sweep}: {key}')


def digest_compact_checkpoint(ordered,row_scales,regrets,average,expected_bytes,*,value_bits=VALUE_BITS):
    """Hash independently reconstructed fixed-width compact image without retaining it."""
    digest=hashlib.sha256()
    written=0
    for field,values in enumerate((average,regrets)):
        for (key,menu),scales in zip(ordered,row_scales,strict=True):
            shift=scales[field]
            require(type(shift) is int and 0<=shift<value_bits,'split reference compact shift')
            width=8*((value_bits-shift+63)//64)
            mask=(1<<shift)-1
            row=values[key]
            require(len(row)==menu,'independent compact menu extent')
            for value in row:
                require(type(value) is int and value>=0 and value.bit_length()<=value_bits
                        and (value & mask)==0,'independent compact value outside certified scale')
                compact=value>>shift
                require(width<=expected_bytes-written,'independent compact byte allowance')
                digest.update(compact.to_bytes(width,'little'))
                written+=width
    require(written==expected_bytes,'independent compact byte count')
    return digest.hexdigest()


def replay(path,expected_sha256,*,paired=False,rank_sets=False,images=None,packed_images=None,checkpoint_digests=None,ten_card=False):
    """Verify the exact retained grid/updates/BR; no native solver is invoked."""
    started=time.perf_counter()
    require(sum(x is not None for x in (images,packed_images,checkpoint_digests))<=1,
            'choose one checkpoint transport')
    if checkpoint_digests is not None:
        require(type(checkpoint_digests) in (list,tuple) and len(checkpoint_digests)==2 and
                all(type(d) is str and len(d)==64 and
                all(c in '0123456789abcdef' for c in d) for d in checkpoint_digests),
                'two ordered lowercase checkpoint SHA-256 digests required')
        checkpoint_digests=tuple(checkpoint_digests)
        require(paired and rank_sets,'checkpoint digest replay requires paired rank-set training')
    split=images is not None or packed_images is not None or checkpoint_digests is not None
    images=tuple(images) if images is not None else ()
    packed_images=tuple(packed_images) if packed_images is not None else None
    require(not rank_sets or paired,'rank-set replay requires paired training')
    if packed_images is not None:
        require(rank_sets and tuple(Path(p).name for p,_,_ in packed_images)==PACKED_IMAGE_NAMES,
                'split replay requires the ordered pair of packed rank-set sweep images')
    elif checkpoint_digests is None:
        require(not split or (rank_sets and tuple(Path(p).name for p,_ in images)==SPLIT_IMAGE_NAMES),
                'split replay requires the ordered pair of rank-set sweep images')
    require(not ten_card or (paired and rank_sets and split),
            'ten-card replay requires paired rank-set training and split images')
    rows = TEN_CARD_ROWS if ten_card else ROWS
    slots = TEN_CARD_SLOTS if ten_card else SLOTS
    bits = TEN_CARD_VALUE_BITS if ten_card else VALUE_BITS
    denominator = TEN_CARD_DENOMINATOR if ten_card else D
    image_bytes = TEN_CARD_IMAGE_BYTES if ten_card else SPLIT_IMAGE_BYTES
    size = TEN_CARD_SPLIT_BYTES if ten_card else (SPLIT_BYTES if split else TOTAL_BYTES)
    packed_details=[]
    with ExitStack() as stack:
        r,identity=stack.enter_context(authenticated_reader(path,expected_sha256,size,private=split,value_bits=bits))
        checkpoints=[]
        identities={identity}
        for page,digest in images:
            reader,identity=stack.enter_context(authenticated_reader(page,digest,image_bytes,private=True,value_bits=bits))
            require(identity not in identities,'split inputs alias')
            identities.add(identity)
            checkpoints.append((reader,digest))
        for page,encoded,digest in packed_images or ():
            reader,identity,extent=stack.enter_context(
                authenticated_packed_reader(page,encoded,digest,image_bytes,bits))
            require(identity not in identities,'split inputs alias')
            identities.add(identity)
            checkpoints.append((reader,digest))
            packed_details.append({'name':Path(page).name,'sha256':encoded,'bytes':extent})
        require(r.read(8)==(TEN_CARD_SPLIT_MAGIC if ten_card else SPLIT_MAGIC if split else MAGIC),'saved training magic')
        require(r.words(16)==(1,52,INT_WORDS,rows,slots,OCCURRENCES,2,12,1,637 if ten_card else 635,bits,size,2,2,29,120 if ten_card else 20),
                'saved fixed fixture or integer contract')
        require(r.natural()==denominator,'saved fixed game denominator')
        fixture=Fixture(ten_card=ten_card)
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
            require(i<rows,'reference ordered row cap')
            history,packed,at=r.words(3)
            actor,holding,menu=packed&255,(packed>>8)&255,(packed>>16)&255
            require(packed>>24==0 and menu==len(fixture.menus[key]) and at==offset,'saved row metadata or offset')
            require(fixture.compact_key(history,actor,holding)==key,f'saved row key/order mismatch at {i}')
            if split:
                row_scales.append(shifts[history>>33])
            ordered.append((key,menu));offset+=menu
        require(len(ordered)==rows and offset==slots,'saved complete ordered row inventory')
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
                if checkpoint_digests is not None:
                    digest=digest_compact_checkpoint(ordered,row_scales,regrets,average,image_bytes,value_bits=bits)
                    require(digest==checkpoint_digests[t-1],f'independent compact digest mismatch sweep {t}')
                else:
                    page,digest=checkpoints[t-1]
                    check_compact_checkpoint(page,ordered,row_scales,regrets,average,t,bits)
                    page.finish(digest)
            else:
                for family,values in [('regret',regrets),('average',average)]:
                    for key,menu in ordered:
                        require(tuple(r.natural() for _ in range(menu))==values[key],f'saved {family} mismatch sweep {t}: {key}')
            require(tuple(Fraction(r.signed(),denominator) for _ in range(4))==root,f'saved four root values mismatch sweep {t}')
            require(sum(root)==0,'replayed root value is not zero sum')
            sweeps.append({'sweep':t,'root_holding_values':[fraction(x) for x in root],
                           'row_count':rows,'regret_comparisons':slots,'average_comparisons':slots})
        require(changes>0,'saved T2 feedback missing')
        expected=fixture.grid(average,average=True)
        saved={}
        for key,menu in ordered:
            units=r.words(menu)
            require(units==expected[key],f'saved exported average grid mismatch: {key}')
            saved[key]=units
        require(r.read(rows)==bytes(not any(average[key]) for key,_ in ordered),'saved average fallback flags')
        require(r.read(8)==(TEN_CARD_SPLIT_END if ten_card else SPLIT_END if split else b'OPLDEND2' if paired else END),'saved complete footer magic')
        plan=dict(zip(FAMILIES,r.words(6)));actual=dict(zip(FAMILIES,r.words(6)))
        parent_plan=dict(zip(PARENT,r.words(9)));parent_actual=dict(zip(PARENT,r.words(9)))
        shape=r.words(8)
        entries,payload,expected_rank_calls=r.words(3)
        chance=dict(zip(CHANCE,r.words(15)))
        feedback,=r.words(1)
        completed,passes,invocations,history_entries,history_bytes,state_entries,state_payload=r.words(7)
        r.finish(expected_sha256)
    require(shape==(TEN_CARD_SHAPE if ten_card else EXPECTED_SHAPE) and (completed,passes,invocations)==(2,2 if paired else 4,1),
            'saved run shape/iteration counters')
    require(feedback==changes,'saved feedback receipt differs')
    work_limit=TEN_CARD_WORK_LIMIT if ten_card else 500_000_000
    payload_limit=TEN_CARD_PAYLOAD_LIMIT if ten_card else 1<<30
    require(sum(plan.values())<=work_limit and all(0<actual[k]<=plan[k] for k in plan),'saved composed work receipt')
    require(sum(parent_plan.values())==plan['parent'] and sum(parent_actual.values())==actual['parent']
            and all(parent_actual[k]<=parent_plan[k] for k in parent_plan),'saved parent family composition')
    require(sum(chance[k] for k in CHANCE[:7])==actual['chance'],'saved chance category composition')
    ranges=scaled_proof9_ranges()
    boards={w.board for w in fixture.worlds}
    if rank_sets:
        boards={frozenset(board) for board in boards}
    ranks=sum(set(hand).isdisjoint(board) for board in boards for side in ranges for hand,_ in side)
    ranked,hidden=fixture.terminal_completion_counts()
    require((ranked,hidden)==(TEN_CARD_TERMINAL_COMPLETIONS if ten_card else EXPECTED_TERMINAL_COMPLETIONS),'independent all-in completion census')
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
            and 0<state_payload+chance['peak_integer_payload_bits']<=payload<=payload_limit,'saved composed storage receipt')
    quality=fixture.quality(saved)
    result={'status':'saved_two_sweep_exact_replay_pass','scope':('named ten-card fixture' if ten_card else 'PROOF9')+' only; saved grid quality, no wider game or target pass',
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
        digests=checkpoint_digests if checkpoint_digests is not None else tuple(d for _,d in checkpoints)
        result['checkpoint_images']=[{'name':name,'sha256':digest,'bytes':image_bytes}
                                     for name,digest in zip(SPLIT_IMAGE_NAMES,digests,strict=True)]
        if checkpoint_digests is not None:
            result['checkpoint_verification']='independent_compact_digest'
    if packed_images is not None:
        result['packed_checkpoint_images']=packed_details
    return result


def fraction(value):
    return {'numerator':str(value.numerator),'denominator':str(value.denominator),'approx':float(value)}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--saved',type=Path,required=True)
    parser.add_argument('--sha256',required=True)
    parser.add_argument('--paired',action='store_true')
    parser.add_argument('--ten-card',action='store_true')
    parser.add_argument('--rank-sets',action='store_true')
    transport=parser.add_mutually_exclusive_group()
    transport.add_argument('--page-images',type=Path)
    transport.add_argument('--packed-page-images',type=Path)
    transport.add_argument('--sweep-checkpoint-digest',nargs=2,metavar=('SWEEP1','SWEEP2'))
    parser.add_argument('--sweep-image-sha256',nargs=2,metavar=('SWEEP1','SWEEP2'))
    parser.add_argument('--packed-sweep-image-sha256',nargs=2,metavar=('PACKED1','PACKED2'))
    args=parser.parse_args()
    if ((args.page_images is None and args.packed_page_images is None)!=(args.sweep_image_sha256 is None)
            or (args.packed_page_images is None)!=(args.packed_sweep_image_sha256 is None)):
        parser.error('the selected image directory and its sweep digests are required together')
    images=tuple((args.page_images/name,digest) for name,digest in
                 zip(SPLIT_IMAGE_NAMES,args.sweep_image_sha256,strict=True)) if args.page_images is not None else None
    packed_images=tuple((args.packed_page_images/name,encoded,digest) for name,encoded,digest in
                        zip(PACKED_IMAGE_NAMES,args.packed_sweep_image_sha256,args.sweep_image_sha256,strict=True)
                        ) if args.packed_page_images is not None else None
    print(json.dumps(replay(args.saved,args.sha256,paired=args.paired,rank_sets=args.rank_sets,images=images,
                            packed_images=packed_images,checkpoint_digests=args.sweep_checkpoint_digest,ten_card=args.ten_card),sort_keys=True))


if __name__=='__main__':main()
