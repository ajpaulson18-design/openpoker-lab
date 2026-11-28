"""Decompose the retained T2 quantizer forecast without ranking or training."""
from collections import defaultdict
import json
from math import comb

from scripts.census_virtual_dyadic_storage import supported_prefixes
from scripts.project_virtual_dyadic_eleven import decision_tail, forecast, ranges, tail, template, uniform_exp, words
from tests.full_deck_public_chance_reference import PROOF9

def decompose(n):
    deck = tuple(sorted((*PROOF9,*range(n-9))))
    base = (29*comb(n-4,3)*(n-7)*(n-8)).bit_length()
    bits = base+632
    support = {(street,seat):sum(supported_prefixes(deck,seat,hand,street,ranges) for hand,_ in ranges[seat])
               for street in (0,3,4,5) for seat in (0,1)}
    groups = defaultdict(lambda: [0,0,0,0,0])

    def walk(node_id, counts=(0,0), first=(0,0)):
        node = template.nodes[node_id]
        if node.phase == "decision":
            player = node.state.player
            menu = len(node.edges)
            rows = support[node.street,player]
            depth = decision_tail(node_id)
            scaled = 52*(counts[player]+1)
            cases = (
                ("regret",menu-1,base+7+first[1-player]+tail(node_id),
                 bits-52*(12-counts[1-player]-depth)),
                ("average",menu,base+2+scaled,bits-(625-scaled)),
            )
            for phase,positive,effective,storage in cases:
                sparse = 64+16*menu+256+32*menu
                sum_words = words(effective+(positive-1).bit_length()+1)
                scaled_words = words(effective+52)
                high = max(words(53),sum_words,scaled_words)
                scans = words(storage)+1
                nondivision = (64+16*menu+16+4*menu*scans+4*positive*scans+256+16*menu*(high+1)
                               +8*positive*(4*high+8)+4*menu*menu*(sum_words+1))
                division = 8*scaled_words*sum_words
                measures = ([sparse,sparse,sparse,0] if positive==1 else
                            [nondivision+positive*division,nondivision+(positive-1)*division,
                             nondivision,24+menu*(12+16*words(storage))])
                row = groups[phase,node.street,menu]
                row[0] += rows
                for i,amount in enumerate(measures,1):
                    row[i] += rows*amount
            counts = tuple(c+int(player==seat) for seat,c in enumerate(counts))
            first = tuple(e+(uniform_exp(menu) if player==seat else 0) for seat,e in enumerate(first))
        for edge in node.edges:
            walk(edge.child,counts,first)

    walk(template.root)
    names = ("rows","retained_forecast","one_fewer_division_term","without_division_charge","cache_probe_reserve")
    records = [{"phase":phase,"street":street,"menu":menu,**dict(zip(names,values,strict=True))}
               for (phase,street,menu),values in sorted(groups.items())]
    terms = {phase:{key:sum(row[key] for row in records if row["phase"]==phase) for key in names}
             for phase in ("regret","average")}
    if [0,terms["regret"]["retained_forecast"],terms["average"]["retained_forecast"]] != forecast(
            n,bits,base,1,first_regret_bound=True):
        raise ValueError("decomposition differs from the independent retained forecast")
    totals = {key:sum(phase[key] for phase in terms.values()) for key in names[1:]}
    totals["cache_probe_reserve"] += 1024
    return {"deck":n,"by_phase":terms,"by_phase_street_and_menu":records,"totals":totals}


if __name__=="__main__":
    print(json.dumps({"scope":"rank-free arithmetic accounting; no training or new admission",
                      "decks":[decompose(n) for n in (10,11)]},indent=2,sort_keys=True))
