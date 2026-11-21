"""Independent binary/raw-row replay; never calls native model helpers."""
from fractions import Fraction
import struct

from tests.virtual_frozen_grid_envelope_reference import envelope
from tests.virtual_frozen_grid_preflight_reference import geometry
from tests.virtual_grid_update_reference import (
    admit_sampled_board,freeze_grid,sampled_grid_update,
)
from scripts.matrix_free_certificate_budget import Budget


def require(value,message):
    if not value:raise ValueError(message)


def verify_raw_wire(fixture,context,policy,board,law,raw):
    require(type(raw) is bytes and 256<=len(raw)<=2_100_000,'raw wire byte ceiling')
    require(raw[:8]==b'OPLGRW01','raw wire version')
    e=envelope(board)
    fields=struct.unpack_from('<31Q',raw,8)
    expected=(1,24420,58164,e[0],e[1],int(law=='river_weighted'),*board,1<<52,
        e[12],e[13],e[14],e[3],e[4],e[5],e[6],e[7],e[8],e[9],e[10],e[11],e[15],e[16],e[2],704,11,12,e[17])
    require(fields==expected and len(raw)==e[15],'independent raw header/reservation')
    position=256
    def take(n):
        nonlocal position
        require(n<=len(raw)-position,'raw wire truncation');body=raw[position:position+n];position+=n;return body
    def words(n):return struct.unpack('<'+'Q'*n,take(8*n))
    def integer(n,signed,bits):
        value=int.from_bytes(take(n),'little',signed=signed)
        require(abs(value).bit_length()<=bits,'raw wire integer magnitude');return value
    offsets={};offset=0
    for key in fixture.ordered_rows():
        actor,holding,ordinal,slot,count=words(5)
        require((actor,holding,slot,count)==(key[0],key[1],offset,len(fixture.menus[key])),'raw full-policy row identity/order')
        require(fixture.compact_key(ordinal,actor,holding)==key,'raw full-policy complete visible history')
        require(words(count)==policy[key],'raw full-policy unit drift')
        offsets[key]=(slot,count);offset+=count
    require(offset==58164 and len(offsets)==24420,'raw full-policy coverage')
    denominator=integer(88,False,638)
    numerator=1 if law=='uniform' else 1+tuple(sorted(fixture.deck)).index(board[4])
    require(denominator==(580*numerator)<<625,'raw common denominator identity')
    roots=tuple(Fraction(integer(88,True,647),denominator) for _ in range(2))
    admission=admit_sampled_board(context,board,law)
    reference,root=sampled_grid_update(context,admission,freeze_grid(fixture,policy),Budget())
    require(roots==(root,-root),'independent raw root values')
    seen=set();action_slots=0;nonzero_regret=False;nonzero_average=False
    for _ in range(e[0]):
        actor,holding,ordinal,slot,count=words(5)
        key=fixture.compact_key(ordinal,actor,holding)
        require(key in reference and key not in seen and offsets[key]==(slot,count),'raw staged row identity/uniqueness')
        seen.add(key);action_slots+=count
        avgden=integer(48,False,381);mass=integer(48,False,383)
        require(avgden>0,'raw average denominator')
        native_regret=[];native_average=[];average_units=0
        for _ in range(count):
            regret=integer(88,True,648);average=integer(48,False,383)
            native_regret.append(Fraction(regret,denominator));native_average.append(Fraction(average,avgden));average_units+=average
        require(tuple(native_regret)==tuple(reference[key][0]),'independent signed raw regret mismatch')
        require(tuple(native_average)==tuple(reference[key][1]),'independent prefix average mismatch')
        require(average_units==mass and Fraction(mass,avgden)==sum(reference[key][1]),'independent average mass/partition')
        nonzero_regret|=any(native_regret);nonzero_average|=any(native_average)
    require(seen==set(reference) and action_slots==e[1],'raw complete supported-prefix row coverage')
    footer=words(26);require(position==len(raw),'raw trailing bytes')
    ready,R,S,rows,slots,actual,template,catalog,state,history,chance,parent,input_bytes,output_bytes,peak,ranks,contractions,sweeps,quantizer,staged,imports,reads,visits,actions,reveals,passes=footer
    g=geometry();phases=tuple(g['by_street'].values())
    decisions=sum(sum(x['decision_occurrences']) for x in phases)
    expected_parent=sum(e[6:12])-2*decisions*(23+23)
    require((ready,R,S,rows,slots)==(1,24420,58164,e[0],e[1]),'raw footer row/slot coverage')
    require((sweeps,quantizer,staged,imports,reads,passes)==(0,0,0,24420,e[2],2),'raw scope/lifetime counters')
    require((visits,actions,reveals,contractions)==(2210,2078,130,1220) and ranks<=4,'raw executed traversal/query counters')
    require(input_bytes==3545022 and output_bytes==len(raw) and peak<=699,'raw byte/integer counters')
    require(parent==expected_parent and template<=43_000_000 and catalog<=5114536 and state<=e[3] and history<=e[4] and chance<=e[5],
            'raw component work reservation')
    require(actual==template+catalog+state+history+chance+parent+16*input_bytes+16*output_bytes and actual<=e[12],
            'raw cumulative request work')
    if not e[17]:require(not nonzero_regret and root==0 and nonzero_average,'zero-full-target prefix behavior')
    return {'status':'all-raw-rows-exact','board':board,'law':law,'rows':len(seen),'slots':action_slots,
        'root':[str(root.numerator),str(root.denominator)],'work_forecast':e[12],'work_actual':actual,
        'native_rank_calls':ranks,'native_contractions':contractions,'peak_integer_bits':peak,'policy_imports':1,
        'training_iterations':0,'state_regret_updates':0,'nonzero_regret':nonzero_regret,'nonzero_average':nonzero_average,
        'scope':'one immutable-policy raw-update case; no clipping, evolving-policy training, quality or wider capacity acceptance'}
