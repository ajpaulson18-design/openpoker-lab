"""Independent symbolic ledger for the proposed fixed-board update schedule.

This verifies an architecture reservation, not the behavior of an implemented
update. Geometry and physical support come only from independent numeric rules.
"""
from tests.virtual_frozen_grid_preflight_reference import boards,census,dense_public_census,geometry
from tests.virtual_frozen_update_reference import scaled_proof9_ranges


def words(bits):return max(1,(bits+63)//64)
def copy(bits):return 1+2*words(bits)
def add(bits):return 2+3*words(bits)
def multiply(a,b):return 2+2*(words(a)+words(b))+words(a)*words(b)


def _prepared_query(showdown,own,opponent):
    # Count the existing blocker's input inspections and bucket operations.
    input_work=12+11+sum(4+2*words(365) for _ in range(2))+4
    dynamic=12
    if own and opponent:
        bucket=4+365+(opponent-1).bit_length()+4;output=4+bucket
        dynamic+=sum(multiply(4,365) for _ in range(opponent))
        dynamic+=53*(2+own if showdown else 1)
        dynamic+=sum((9 if showdown else 3)*add(bucket) for _ in range(opponent))
        dynamic+=sum((12 if showdown else 3)*add(bucket)+multiply(4,bucket)+copy(output)+2*words(bucket) for _ in range(own))
        dynamic+=128
    return input_work+dynamic+(384 if showdown else 0)


_DENSE=None
def envelope(board):
    global _DENSE
    if _DENSE is None:_DENSE=dense_public_census()['shape']
    dense=_DENSE;g=geometry();case=census(board)
    phases=tuple(g['by_street'].values())
    edges=sum(x['decision_action_slots'] for x in phases)
    reveals=sum(x['reveals'] for x in phases)
    folds=sum(x['folds'] for x in phases);showdowns=sum(x['showdowns'] for x in phases)
    decisions=sum(sum(x['decision_occurrences']) for x in phases)
    r,s=case['supported_rows'],case['supported_action_slots']
    R,S=dense['rows'],dense['slots'];reads=R+2*r;log=R.bit_length()
    import_work=1088+130*R+258*S
    state=1024+8*R+16*S+44+R*(128+16*log)+256*S+import_work+(208+16*log)*reads
    history=(4096*g['literal_occurrences']+1280+40*dense['actions']+72*dense['reveals']+48*dense['visits']+40*R+
        8*R+72*249662+56*R+16*S+40*reads+288*R+2*(48*edges+80*reveals+8))
    hands=scaled_proof9_ranges();blocked=set(board)
    live=[sum(not blocked.intersection(hand) for hand,_ in side) for side in hands]
    chance=65536+sum(folds*_prepared_query(False,live[p],live[1-p])+showdowns*_prepared_query(True,live[p],live[1-p]) for p in (0,1))
    chance+=4*4096+512+64+256
    chance+=8*_prepared_query(False,2,2)
    reach=2*edges*(24+2*(multiply(365,53)+copy(365)))
    scale=4*(folds+showdowns)*(32+multiply(378,4)+multiply(382,14)+copy(647)+2*words(699))
    mix=4*edges*(8+multiply(647,53)+add(699)+copy(699))+s*(8+add(648)+copy(648))+4*decisions*(copy(699)+copy(648))
    average=r*(64+multiply(5,14)+multiply(313,19)+copy(381)+copy(383))+s*(16+multiply(332,53)+copy(383))
    stage=1024+64*r+16*s;walk=512+256*g['literal_occurrences']
    catalog=3_000_000+8*dense['visits']+64*dense['candidates']+16*R+4*S
    parent=catalog+reach+scale+mix+average+stage+walk
    work=43_000_000+chance+history+state+1+parent+16*(8<<20)+16*2_100_000
    entries=1024+16*R+10*S+131072+32*g['literal_occurrences']+1+12000+16384+8*r+2*s+64*19+64
    staged_payload=r*(2*(383+58)+512)+s*((648+58)+(383+58))+64*19*(704+58)+16*(5+58)+4096
    payload=(5*S+256)*(648+58)+128*S+512*S+16*R+(1<<20)+8*(1<<20)+(1<<22)+32*181+8*16384+staged_payload
    output=1442320+256+88+176+136*r+136*s
    feasible=int(work<=500_000_000 and history<=42_000_000 and state+1<=75_000_000 and chance<=110_000_000 and
                 parent<=115_000_000 and entries<=2_000_000 and payload<=1<<30 and output<=2_100_000)
    return (r,s,reads,state,history,chance,reach,scale,mix,average,stage,walk,work,entries,payload,output,
            staged_payload,int(case['full_target_positive']),feasible,0,704)


def verify_wire(raw):
    def require(value,message):
        if not value:raise ValueError(message)
    require(type(raw) is bytes and len(raw)<=2_100_000 and raw.endswith(b'\n'),'envelope output byte ceiling/framing')
    lines=raw.decode('ascii').splitlines()
    require(len(lines)==5043 and lines[0]=='FROZEN_GRID_ENVELOPE_V2','complete envelope frame')
    g=geometry();phases=tuple(g['by_street'].values())
    expected=(1105,sum(x['decision_action_slots'] for x in phases),sum(x['reveals'] for x in phases),
              sum(x['folds'] for x in phases),sum(x['showdowns'] for x in phases),
              sum(sum(x['decision_occurrences']) for x in phases),6,7,12,11)
    require(lines[1]=='GEOMETRY '+' '.join(map(str,expected)),'independent literal route geometry')
    maxima={};minima={};total_rows=total_slots=0
    for line,(law,board) in zip(lines[2:-1],((law,board) for board in boards() for law in (0,1))):
        fields=line.split()
        require(len(fields)==28 and fields[0]=='F' and all(x.isascii() and x.isdigit() and len(x)<=10 for x in fields[1:]),'envelope scalar grammar')
        values=tuple(map(int,fields[1:]));require(values[:6]==(law,*board),'envelope ordered outcome identity')
        values=values[6:];require(values==envelope(board),'independent architecture equation mismatch')
        total_rows+=values[0];total_slots+=values[1]
        for name,index in (('work',12),('chance',5),('state',3),('history',4),('entries',13),('payload_bits',14),('output_bytes',15)):
            maxima[name]=max(maxima.get(name,0),values[index]);minima[name]=min(minima.get(name,values[index]),values[index])
    require((total_rows,total_slots)==(214160,535080),'complete prefix row/slot coverage')
    require(lines[-1]=='END 5040 0 0 0 0 0','envelope scope footer')
    return {'status':'provisional-envelope-equations-exact','forecasts':5040,'maximum':maxima,'minimum':minima,
            'update_admitted':False,'policy_imports':0,'native_rank_calls':0,'native_contractions':0,'native_updates':0,'training_iterations':0,
            'scope':'proposed logical ledger only; implementing and metering the raw-update producer remains required'}
