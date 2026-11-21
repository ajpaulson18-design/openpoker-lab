"""Independent numerical/session-wire replay; no native forecast or rank calls."""
from fractions import Fraction
import struct

from scripts.matrix_free_certificate_budget import Budget
from tests.virtual_frozen_grid_envelope_reference import envelope
from tests.virtual_frozen_grid_preflight_reference import geometry
from tests.virtual_frozen_policy_session_reference import session_forecast
from tests.virtual_grid_update_reference import admit_sampled_board,freeze_grid,sampled_grid_update


def require(value,message):
    if not value:raise ValueError(message)


def verify_session_wire(fixture,context,policy,selectors,raw):
    require(type(raw) is bytes and 136<=len(raw)<=2_100_000,'session bounded wire')
    require(len(selectors)==2 and raw[:8]==b'OPLGEP01','session version/selector count')
    (board0,law0),(board1,law1)=selectors
    f=session_forecast(board0,law0,board1,law1)
    require(f['feasible'],'session independently feasible request')
    staged=sum(b['payload_raw'] for b in f['boards'])
    expected=(1,2,24420,58164,1<<52,f['work'],f['entries'],f['payload'],f['state'],f['history'],
        f['chance'],f['parent'],f['output'],staged,f['reads'],1040000)
    require(struct.unpack_from('<16Q',raw,8)==expected and len(raw)==f['output'],'session cumulative header')
    position=136
    def take(n):
        nonlocal position
        require(n<=len(raw)-position,'session wire truncation');body=raw[position:position+n];position+=n;return body
    def words(n):return struct.unpack('<'+'Q'*n,take(8*n))
    def integer(n,signed,bits):
        value=int.from_bytes(take(n),'little',signed=signed)
        require(abs(value).bit_length()<=bits,'session integer magnitude');return value
    offsets={};offset=0
    for key in fixture.ordered_rows():
        actor,holding,ordinal,slot,count=words(5)
        require((actor,holding,slot,count)==(key[0],key[1],offset,len(fixture.menus[key])),'session complete policy order/menu')
        require(fixture.compact_key(ordinal,actor,holding)==key,'session policy full-history identity')
        require(words(count)==policy[key],'session immutable policy units')
        offsets[key]=(slot,count);offset+=count
    require(offset==58164 and len(offsets)==24420,'session single complete policy echo')
    g=geometry();phases=tuple(g['by_street'].values())
    decisions=sum(sum(x['decision_occurrences']) for x in phases)
    edges=sum(x['decision_action_slots'] for x in phases);reveals=sum(x['reveals'] for x in phases)
    families=[];deltas=[];results=[]
    frozen=freeze_grid(fixture,policy)
    for index,(board,law) in enumerate(selectors):
        e=envelope(board);start=position
        require(take(8)==b'OPLGBD01','session board record version')
        header=(1,24420,58164,e[0],e[1],int(law=='river_weighted'),*board,1<<52,
            e[12],e[13],e[14],e[3],e[4],e[5],e[6],e[7],e[8],e[9],e[10],e[11],e[15]-1442112,e[16],e[2],704,11,12,e[17])
        require(words(31)==header,'session board reference schedule/header')
        denominator=integer(88,False,638)
        numerator=1 if law=='uniform' else 1+tuple(sorted(fixture.deck)).index(board[4])
        require(denominator==(580*numerator)<<625,'session proposal denominator')
        roots=tuple(Fraction(integer(88,True,647),denominator) for _ in range(2))
        admission=admit_sampled_board(context,board,law)
        reference,root=sampled_grid_update(context,admission,frozen,Budget())
        require(roots==(root,-root),'session independent roots')
        seen=set();slots=0;nonzero_average=False
        for _ in range(e[0]):
            actor,holding,ordinal,slot,count=words(5);key=fixture.compact_key(ordinal,actor,holding)
            require(key in reference and key not in seen and offsets[key]==(slot,count),'session raw row full-history identity')
            seen.add(key);slots+=count
            avgden=integer(48,False,381);mass=integer(48,False,383)
            require(avgden>0,'session average denominator')
            regrets=[];averages=[];total=0
            for _ in range(count):
                regret=integer(88,True,648);average=integer(48,False,383)
                regrets.append(Fraction(regret,denominator));averages.append(Fraction(average,avgden));total+=average
            require(tuple(regrets)==tuple(reference[key][0]) and tuple(averages)==tuple(reference[key][1]),'session independent raw regret/average')
            require(total==mass and Fraction(mass,avgden)==sum(reference[key][1]),'session average partition')
            nonzero_average|=any(averages)
        require(seen==set(reference) and slots==e[1],'session complete raw row coverage')
        values=words(26)
        ready,rows,slots,parent,peak,reads,visits,actions,revealed,terminals,sd,hd,cd,ranks,queries,sweeps,staged_rows,quantizer=values[:18]
        actual_families=values[18:24]
        expected_families=(*e[6:8],e[8]-2*decisions*(23+23),*e[9:12])
        require(actual_families==expected_families and parent==sum(actual_families),'session exact board parent families')
        require((ready,rows,slots,reads,visits,actions,revealed,terminals)==(1,e[0],e[1],2*e[0],2210,2078,130,1212),
                'session two-seat board traversal/read census')
        require(sd==2*e[0]*(128+16*(24421).bit_length())+8*e[1],'session exact State read delta')
        require(hd==16+80*edges+144*reveals+80*e[0],'session exact History walk/read delta')
        require(cd<=e[5]-65536 and ranks<=4 and queries==1220 and peak<=699,'session bounded board chance/arithmetic')
        require((sweeps,staged_rows,quantizer)==(0,0,0) and values[24:]==(index,f['reads']),'session immutable owner lifetime')
        require(position-start==e[15]-1442112,'session exact board record bytes')
        if not e[17]:require(root==0 and nonzero_average,'session zero-target prefix averages')
        families.append(parent);deltas.append((sd,hd,cd,ranks,queries));results.append({'board':board,'law':law,
            'rows':rows,'slots':slots,'root':[str(root.numerator),str(root.denominator)],'peak_integer_bits':peak})
    footer=words(26);require(position==len(raw),'session trailing bytes')
    ready,R,S,count,actual,template,catalog,state,history,chance,parent,input_bytes,output_bytes,peak,ranks,queries,sweeps,quantizer,staged_rows,imports,reads,visits,actions,reveals,passes,complete=footer
    require((ready,R,S,count,input_bytes,output_bytes)==(1,24420,58164,2,3545022,len(raw)),'session global completion/input/output')
    require((sweeps,quantizer,staged_rows,imports,reads,visits,actions,reveals,passes,complete)==
        (0,0,0,24420,f['reads'],4420,4156,260,4,1),'session shared epoch/scope counters')
    require(parent==1024+sum(families) and ranks==sum(x[3] for x in deltas) and queries==2440,'session cumulative parent/chance counts')
    require(peak==max(x['peak_integer_bits'] for x in results),'session retained integer peak')
    require(template<=43_000_000 and catalog<=5114536 and catalog+parent<=f['parent'] and
            state<=f['state'] and history<=f['history'] and chance<=f['chance'],'session cumulative component allowances')
    require(actual==template+catalog+state+history+chance+parent+16*input_bytes+16*output_bytes and actual<=f['work'],
            'session one cumulative request work')
    return {'status':'both-raw-results-exact','boards':results,'work_actual':actual,'work_forecast':f['work'],
        'output_bytes':len(raw),'policy_imports':1,'policy_echoes':1,'state_reads':reads,'rank_calls':ranks,
        'chance_contractions':queries,'training_iterations':0,'state_updates':0,
        'scope':'one immutable two-board raw session only; no policy transition, sampled training or quality'}
