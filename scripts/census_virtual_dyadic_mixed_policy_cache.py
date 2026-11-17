"""Replay the exact mixed-policy cache on the frozen staged-page T2 inputs."""
from argparse import ArgumentParser
from collections import Counter
import hashlib
import json
from math import gcd
from pathlib import Path
from struct import Struct

ROW = Struct("<QIIIHHHBBI")
ROWS, SLOTS = 119196, 281066
AVERAGE_WORDS, REGRET_WORDS = 1295812, 1666910
IMAGE_BYTES = 8*(AVERAGE_WORDS+REGRET_WORDS)
MASK = (1 << 64) - 1
CACHE_SLOTS = 16


def words(bits):
    return (bits+63)//64


def signature(row):
    value = 14695981039346656037 ^ len(row)
    for number in row:
        length = max(1, words(number.bit_length()))
        value = ((value ^ length)*1099511628211) & MASK
        for offset in range(length):
            value = ((value ^ ((number >> (64*offset)) & MASK))*1099511628211) & MASK
    value = ((value ^ (value >> 32))*0xd6e8feb86659fd93) & MASK
    return value ^ (value >> 32)


def load(root, refs, path, limit):
    with (root/path).open("rb") as stream:
        data = stream.read(limit+1)
    if len(data)!=limit or hashlib.sha256(data).hexdigest()!=refs[path]:
        raise ValueError("archived source or extent differs: "+path)
    return data


def census(root, protocol):
    refs = json.loads(protocol.read_bytes())["stable_sidecars"]
    directory = load(root,refs,"page-images-rows/rows.bin",ROWS*ROW.size)
    records = list(ROW.iter_unpack(directory))
    raw_cache = [None]*CACHE_SLOTS
    phases = {}
    for field, path, shift_column, offset_column, start, end in (
            ("regret","page-images/staged.bin",6,3,AVERAGE_WORDS,AVERAGE_WORDS+REGRET_WORDS),
            ("average","page-images/committed.bin",5,2,0,AVERAGE_WORDS)):
        image = load(root,refs,path,IMAGE_BYTES)
        counts, classes = Counter(), Counter()
        exact, pow2, ratios = set(), set(), set()
        before = start
        for i,record in enumerate(records):
            next_offset = records[i+1][1] if i+1<len(records) else SLOTS
            menu = next_offset-record[1]
            bits = 644-record[shift_column]
            stride = words(bits)
            pos = start+record[offset_column]
            if pos!=before or not 2<=menu<=4 or not 1<=bits<=644 or record[-1]:
                raise ValueError("invalid directory row extent")
            before = pos+menu*stride
            row = tuple(int.from_bytes(image[8*(pos+a*stride):8*(pos+(a+1)*stride)],"little")
                        for a in range(menu))
            if any(x.bit_length()>bits for x in row):
                raise ValueError("checkpoint row leading padding differs")
            positive = [x for x in row if x>0]
            p = len(positive)
            if field=="regret" and p==menu:
                raise ValueError("first regret support certificate differs")
            counts["rows"] += 1
            sparse = 256+32*menu
            inspect = 64+16*menu
            counts["work_uncached"] += inspect
            counts["work_cached"] += inspect
            if p<=1:
                classes[(menu,"pure" if p else "zero")] += 1
                counts["work_uncached"] += sparse
                counts["work_cached"] += sparse
                continue
            w = words(max(positive).bit_length())
            eq = 16+4*menu*(w+1)
            counts["work_uncached"] += eq
            counts["work_cached"] += eq
            if len(set(positive))==1:
                classes[(menu,"equal")] += 1
                counts["work_uncached"] += sparse
                counts["work_cached"] += sparse
                continue
            classes[(menu,"mixed")] += 1
            exact.add(row)
            trailing = min((x&-x).bit_length()-1 for x in positive)
            common = gcd(*positive)
            pow2.add(tuple(x>>trailing for x in row))
            ratios.add(tuple(x//common for x in row))
            scaled = max(positive).bit_length()-trailing+52
            summation = scaled-52+(p-1).bit_length()+1
            high = words(max(53,scaled,summation))
            mixed = (sum(4*(words(x.bit_length())+1) for x in positive)+256+16*menu*(high+1)
                     +8*p*(words(scaled)*words(summation)+4*high+8)+4*menu*menu*(words(summation)+1))
            counts["work_uncached"] += mixed
            counts["divisions_uncached"] += p-1
            counts["work_cached"] += 24+menu*(12+16*w)
            slot = signature(row)%CACHE_SLOTS
            if raw_cache[slot]==row:
                counts["hits"] += 1
            else:
                raw_cache[slot] = row
                counts["misses"] += 1
                counts["divisions_cached"] += p-1
                counts["work_cached"] += mixed
        if before!=end or counts["rows"]!=ROWS:
            raise ValueError("checkpoint image coverage differs")
        phases[field] = dict(counts) | {
            "by_menu_and_category": {f"{menu}-{kind}":count for (menu,kind),count in sorted(classes.items())},
            "unique_exact_mixed_inputs":len(exact), "unique_power_of_two_reduced_mixed_inputs":len(pow2),
            "unique_rational_mixed_inputs":len(ratios),
        }
    totals = {key:sum(stage[key] for stage in phases.values())
              for key in ("hits","misses","divisions_uncached","divisions_cached","work_uncached","work_cached")}
    totals["work_cached"] += 1024
    return {"cache_slots":CACHE_SLOTS,"phases":phases,"totals":totals,"native_producer_calls":0}


if __name__=="__main__":
    parser=ArgumentParser(description=__doc__)
    parser.add_argument("checkpoint_directory",type=Path)
    parser.add_argument("staged_page_protocol",type=Path)
    args=parser.parse_args()
    print(json.dumps(census(args.checkpoint_directory,args.staged_page_protocol),indent=2,sort_keys=True))
