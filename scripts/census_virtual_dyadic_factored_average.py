"""Independent saved-policy reach-width census and rank-free parent partition."""
from argparse import ArgumentParser
from collections import Counter, deque
from functools import lru_cache
from itertools import combinations, permutations
from math import comb
from pathlib import Path
from struct import Struct
import hashlib
import json

from scripts.project_virtual_dyadic_eleven import collect, ranges, template, uniform_exp
from scripts.census_virtual_dyadic_storage import supported_prefixes
from tests.full_deck_public_chance_reference import PROOF9

ROOT = Path(__file__).resolve().parents[1]
ROW = Struct("<QIIIHHHBBI")
GRID = 1 << 52
def need(ok, message):
    if not ok:
        raise ValueError(message)
def words(n): return max(1, (n+63)//64)
def mul(a,b): return 2+2*(words(a)+words(b))+words(a)*words(b)
def cp(n): return 1+2*words(n)
def avg(e,base,m):
    row=e+base
    return 32+mul(e+1,base)+cp(row)+m*(8+mul(row,53))

def forecast_saving(n):
    deck=tuple(sorted((*PROOF9,*range(n-9))))
    base=(29*comb(n-4,3)*(n-7)*(n-8)).bit_length()
    support={(k,p):sum(supported_prefixes(deck,p,h,k,ranges) for h,_ in ranges[p])
             for k in (0,3,4,5) for p in (0,1)}
    before=after=0
    def visit(i,past,first):
        nonlocal before,after
        node=template.nodes[i]
        if node.phase=="decision":
            p=node.state.player
            m=len(node.edges)
            before+=2*support[node.street,p]*avg(52*past[p],base,m)
            after+=support[node.street,p]*(avg(first[p],base,m)+avg(52*past[p],base,m))
            past=tuple(x+int(j==p) for j,x in enumerate(past))
            first=tuple(x+(uniform_exp(m) if j==p else 0) for j,x in enumerate(first))
        for edge in node.edges:
            visit(edge.child,past,first)
    visit(template.root,(0,0),(0,0))
    return {"before":before,"after":after,"reduction":before-after}

def grid(row):
    positive=[max(0,x) for x in row]
    total=sum(positive)
    if not total:
        q,r=divmod(GRID,len(row))
        return tuple(q+int(i<r) for i in range(len(row)))
    quotient=[]
    remainder=[]
    for i,x in enumerate(positive):
        q,r=divmod(x*GRID,total)
        quotient.append(q)
        remainder.append((r,-i))
    for _,neg in sorted(remainder,reverse=True)[:GRID-sum(quotient)]:
        quotient[-neg]+=1
    need(sum(quotient)==GRID,"independent grid does not partition one")
    return tuple(quotient)

def saved(root,protocol):
    refs=json.loads(protocol.read_bytes())["stable_sidecars"]
    def load(name,size):
        raw=(root/name).read_bytes()
        need(len(raw)==size and hashlib.sha256(raw).hexdigest()==refs[name],"saved identity differs: "+name)
        return raw
    records=list(ROW.iter_unpack(load("page-images-rows/rows.bin",119196*32)))
    image=load("page-images/staged.bin",23701776)
    policies=[]
    for i,r in enumerate(records):
        menu=(records[i+1][1] if i+1<len(records) else 281066)-r[1]
        stride=words(644-r[6])
        start=1295812+r[3]
        weights=tuple(int.from_bytes(image[8*(start+a*stride):8*(start+(a+1)*stride)],"little")
                      for a in range(menu))
        need(all(x.bit_length()<=644-r[6] for x in weights),"saved regret padding")
        need(sum(x>0 for x in weights)<menu,"first regret support certificate")
        policies.append(grid(weights))
    deck=tuple(sorted((*PROOF9,0)))
    pairs=[(i,j,set(a)|set(b)) for i,(a,_) in enumerate(ranges[0])
           for j,(b,_) in enumerate(ranges[1]) if set(a).isdisjoint(b)]
    @lru_cache(None)
    def support(board):
        live=[(i,j) for i,j,private in pairs if not set(board)&private]
        return tuple(tuple(sorted({x[p] for x in live})) for p in (0,1))
    @lru_cache(None)
    def reveals(board):
        candidates=combinations(deck,3) if not board else (board+(c,) for c in deck if c not in board)
        return tuple(b for b in candidates if support(b)[0])
    # Independent literal occurrences are breadth-first, with reveal edges retained.
    literal_children=[]
    source=[template.root]
    for i in source:
        children=[]
        for edge in template.nodes[i].edges:
            children.append(len(source))
            source.append(edge.child)
        literal_children.append(children)
    need(len(source)==1105,"literal history count")
    phases=[]
    for sweep in (0,1):
        next_row=0
        count=Counter()
        def visit(literal,board,past,exponents):
            nonlocal next_row
            node=template.nodes[source[literal]]
            if node.phase=="reveal":
                for b in reveals(board):
                    visit(literal_children[literal][0],b,past,exponents)
                return
            if node.phase!="decision":
                return
            p=node.state.player
            m=len(node.edges)
            own={}
            code=sum(card<<(6*k) for k,card in enumerate(board)) | (len(board)<<30)
            key=(literal<<33)|code
            for holding in support(board)[p]:
                row=next_row
                next_row+=1
                r=records[row]
                menu=(records[row+1][1] if row+1<len(records) else 281066)-r[1]
                need((r[0],r[7],r[8],menu,r[5])==(key,p,holding,m,625-52*(past[p]+1)),
                     "saved full-history row does not match independent traversal")
                q,rem=divmod(GRID,m)
                own[holding]=policies[row] if sweep else tuple(q+int(a<rem) for a in range(m))
                e=exponents[p]
                need(0<=e<=52*past[p],"reach exponent outside actor path")
                count["rows"]+=1
                count["before"]+=avg(52*past[p],12,m)
                count["after"]+=avg(e,12,m)
                count["nonzero_shift_rows"]+=int(e<52*past[p])
                count["implicit_zero_bits"]+=m*(52*past[p]-e)
            following=tuple(x+int(j==p) for j,x in enumerate(past))
            for action,child in enumerate(literal_children[literal]):
                active=[units[action] for units in own.values() if units[action]]
                e=exponents[p]+52-min((x&-x).bit_length()-1 for x in active) if active else 0
                advanced=tuple(e if j==p else x for j,x in enumerate(exponents))
                visit(child,board,following,advanced)
        visit(0,(),(0,0),(0,0))
        need(next_row==119196,"saved rows incompletely covered")
        count["reduction"]=count["before"]-count["after"]
        phases.append(dict(count))
    return {"phases":phases,
            "total":{k:sum(p[k] for p in phases) for k in phases[0]},
            "native_producer_calls":0,"hand_rank_calls":0}

def partition(path):
    native=json.loads(path.read_bytes())
    reference=json.loads((ROOT/"benchmarks/results/native-dyadic-eleven-native-forecast-v1/manifest.json").read_bytes())["forecast"]
    common={k:v for k,v in native.items() if k not in ("parent_work","parent_details")}
    need(common==reference,"native eleven-card common forecast changed")
    g,np,average_build,addition=collect(11,646,(29*420).bit_length())
    R,S=380172,892910
    A,G=4188150,5536052
    L=A+G
    paging=16*3801720+2*(5*A+6*G)+16*L+32*R+4*L+160*59328+2*(4096+64+1)
    details={"packed_average":32*R+36*A+(6*11+70)*S,
             "packed_regret":32*R+44*G+(16*11+88)*S,
             "paging":paging,"policy_spill":2*(32*R+16*(S-R)+4*S)+64,
             "directory":4*4608+176*R+4*24350*128,"average_build":average_build}
    parent={"geometry":3000000,"visit":32*g["visits"],
            "support":64*(3*g["candidates"]+2*g["hidden_candidates"]),
            "reach":2*g["actions"]*(24+2*(mul(365,53)+cp(365))),
            "value_add":addition,
            "terminal_scale":8*(g["folds"]+g["showdowns"])*(16+mul(646,4)+mul(646,6)+cp(646)),
            "average":average_build+96*(g["reveals"]+1)+details["packed_average"],
            "route":48*R+4*S+details["packed_regret"]+paging+details["directory"]+details["policy_spill"],
            "output":18*S+88*R+160*1105+65536}
    adds=addition//(2+3*words(646))
    details["factored_metadata"]=64*(8*(g["folds"]+g["showdown_contractions"])+
        8*(g["folds"]+g["showdowns"])+adds+2*S+8)+640*R
    need(list(parent.values())==native["parent_work"],"independent parent partition differs")
    need(details==native["parent_details"],"independent parent details differ")
    need(sum(parent.values())==2308449784,"parent total changed")
    return {"parent":parent,"details":details,"sum":sum(parent.values()),
            "hypothetical_average_saving":forecast_saving(11),"training_invocations":0,"hand_rank_calls":0}

if __name__=="__main__":
    p=ArgumentParser()
    p.add_argument("--capture",type=Path)
    p.add_argument("--protocol",type=Path)
    p.add_argument("--native-forecast",type=Path)
    a=p.parse_args()
    result={"forecast_average_build":{n:forecast_saving(n) for n in (10,11)}}
    if a.capture:
        result["saved"]=saved(a.capture,a.protocol)
    if a.native_forecast:
        result["eleven_parent_partition"]=partition(a.native_forecast)
    print(json.dumps(result,indent=2,sort_keys=True))

