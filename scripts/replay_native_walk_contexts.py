"""Replay normalized owned-child wall-time contexts without running a producer.

Return PCs were adjusted before module selection during normalization. These
counts are nested observations, not CPU percentages or exclusive owner costs.
"""
from argparse import ArgumentParser
from bisect import bisect_right
from collections import Counter
import gzip
import json
from pathlib import Path
import re

MAX_BYTES=16<<20
TRACKED={
    "walk":(("?visit@?$Walk@",),""),
    "terminal":(("?terminal@?$Walk@",),""),
    "state_stage_row":(("??$stage_row_impl@",),"@State@virtual_dyadic_state@"),
    "state_stage_direct":(("??$stage_direct_row@",),"@State@virtual_dyadic_state@"),
    "pager_stage":(("?stage_impl@Image@",),"@virtual_dyadic_paged_image@"),
    "pager_flush_dirty":(("?flush_dirty@Image@",),"@virtual_dyadic_paged_image@"),
    "chance_contract":(("?contract@PreparedPublicChance@","??$contract@"),"@PreparedPublicChance@prepared_public_chance@"),
    "chance_contraction":(("?contraction@PreparedPublicChance@",),"@prepared_public_chance@"),
}
TOP={"format","native_image_sha256","image_size","raw_report_sha256","map_sha256",
     "return_pc_adjusted_before_module_lookup","interval_ms","external_seed_samples",
     "unknown_seed_samples","ranges","samples"}
SAMPLE={"elapsed_ms","seed_rva","native_return_rvas","external_return_frames",
        "unknown_return_frames","status","stop_reason"}

def require(ok,message):
    if not ok: raise ValueError(message)

def natural(n,maximum,label):
    require(type(n) is int and 0<=n<=maximum,label+" range")
    return n

def labels(aliases):
    return {label for label,(prefixes,owner) in TRACKED.items()
            if any(any(alias["name"].startswith(p) for p in prefixes) and owner in alias["name"]
                   for alias in aliases)}

def analyze(record):
    require(type(record) is dict and set(record)==TOP,"normalized schema")
    require(record["format"]=="owned-child-wall-contexts-v1" and
            record["return_pc_adjusted_before_module_lookup"] is True,"normalized identity")
    for key in ("native_image_sha256","raw_report_sha256","map_sha256"):
        require(type(record[key]) is str and re.fullmatch("[0-9a-f]{64}",record[key]),"hash identity")
    size=natural(record["image_size"],16<<20,"image size")
    require(size>0,"empty image")
    interval=natural(record["interval_ms"],1000,"interval")
    require(interval>0,"zero interval")
    ranges=record["ranges"]
    require(type(ranges) is list and 0<len(ranges)<=65536,"range inventory")
    starts=[]
    markers=[]
    previous=0
    matching=Counter({key:0 for key in TRACKED})
    for item in ranges:
        require(type(item) is dict and set(item)=={"begin_rva","end_rva","unwind_rva","aliases"},"range schema")
        begin=natural(item["begin_rva"],size-1,"function begin")
        end=natural(item["end_rva"],size,"function end")
        natural(item["unwind_rva"],size-1,"unwind RVA")
        require(previous<=begin<end,"function order or overlap")
        previous=end
        aliases=item["aliases"]
        require(type(aliases) is list and 0<len(aliases)<=256,"alias inventory")
        for alias in aliases:
            require(type(alias) is dict and set(alias)=={"name","flags","object"},"alias schema")
            require(type(alias["name"]) is str and 0<len(alias["name"])<=32768 and
                    type(alias["object"]) is str and len(alias["object"])<=32768 and
                    type(alias["flags"]) is list and all(type(x) is str for x in alias["flags"]),"alias text")
        found=labels(aliases)
        matching.update(found)
        starts.append(begin)
        markers.append(found)
    def at(rva):
        natural(rva,size-1,"sample RVA")
        i=bisect_right(starts,rva)-1
        return markers[i] if i>=0 and rva<ranges[i]["end_rva"] else set()
    samples=record["samples"]
    require(type(samples) is list and len(samples)<=1024,"sample inventory")
    require(all(type(s) is dict and set(s)==SAMPLE for s in samples),"sample schema")
    require(natural(record["external_seed_samples"],len(samples),"external seed")+
            natural(record["unknown_seed_samples"],len(samples),"unknown seed")==
            sum(s["seed_rva"] is None for s in samples),"seed coverage accounting")
    counts=Counter({key:0 for key in TRACKED})
    prior=0
    unresolved_native=0
    for sample in samples:
        require(type(sample) is dict and set(sample)==SAMPLE,"sample schema")
        stamp=natural(sample["elapsed_ms"],60000,"sample time")
        require(stamp>=prior,"time reversal")
        prior=stamp
        require(type(sample["status"]) is str and type(sample["stop_reason"]) is str and
                len(sample["status"])<=128 and len(sample["stop_reason"])<=256,"sample status text")
        native=sample["native_return_rvas"]
        require(type(native) is list and len(native)<=64,"frame inventory")
        external=natural(sample["external_return_frames"],64,"external frame")
        unknown=natural(sample["unknown_return_frames"],64,"unknown frame")
        require(len(native)+external+unknown<=64,"combined frame cap")
        seen=set()
        if sample["seed_rva"] is not None:
            resolved=at(sample["seed_rva"])
            seen.update(resolved)
            unresolved_native+=not resolved
        for rva in native:
            seen.update(at(rva))
        if "walk" in seen:
            counts.update(seen)
    return {"samples":len(samples),"walk_observations":counts["walk"],
            "nested_walk_context_counts":dict(counts),"matching_public_ranges":dict(matching),
            "seed_without_tracked_label":unresolved_native,
            "external_seed_samples":record["external_seed_samples"],
            "unknown_seed_samples":record["unknown_seed_samples"],
            "scope":"periodic primary-thread wall-time observations; nested labels and aliases"}

def pairs(items):
    result={}
    for key,value in items:
        require(key not in result,"duplicate JSON key")
        result[key]=value
    return result

def replay(path):
    with gzip.open(path,"rb") as f: raw=f.read(MAX_BYTES+1)
    require(0<len(raw)<=MAX_BYTES,"normalized byte bound")
    return analyze(json.loads(raw,object_pairs_hook=pairs))

if __name__=="__main__":
    parser=ArgumentParser(description=__doc__)
    parser.add_argument("captures",type=Path,nargs="+")
    args=parser.parse_args()
    print(json.dumps({p.name:replay(p) for p in args.captures},indent=2,sort_keys=True))

