"""Authenticate and independently replay the frozen full-future flop CFR+ study."""
import argparse
import hashlib
import json
from pathlib import Path
from scripts import benchmark_flop_cfrplus as experiment
from scripts import verify_weighted_flop_publication as baseline
from scripts.benchmark_preflop_covered_counts import checksum

PUBLICATION = experiment.ROOT / 'benchmarks/results/weighted-full-deck-flop-cfrplus-v1'
INDEX_SHA256 = '6308cf6c9f5636123014355a328279fbc037c5ab0366ba3378909d52086ddaef'
SOURCE_REVISION = '06616039f4fea3904614132f31c91c406ca90c1a'
SOURCE_MANIFEST_SHA256 = '411777c7df5f78623ce760e14d384c9e5f451e5527205662ea0be3ee666a64b7'


def verify_saved(directory=PUBLICATION, *, baseline_directory=baseline.PUBLICATION, require_quality=False):
    directory=Path(directory);path=directory/'index.json'
    if path.is_symlink() or not path.is_file() or path.stat().st_size>4*1024*1024:
        raise ValueError('Invalid bounded published CFR+ index')
    raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=INDEX_SHA256:
        raise ValueError('Immutable published CFR+ index changed')
    report=json.loads(raw);before=report['source_before']
    if (before!=report['source_after'] or before['status'] or before['revision']!=SOURCE_REVISION
            or len(before['source_hashes'])!=593
            or checksum(before['source_hashes'])!=SOURCE_MANIFEST_SHA256):
        raise ValueError('Published frozen CFR+ source identity changed')
    if require_quality and not report['quality_gate_met']:
        raise ValueError('Original final quality target remains unmet')
    checked=experiment.verify_saved(directory,baseline_directory,require_quality=require_quality)
    if path.read_bytes()!=raw:
        raise ValueError('Published CFR+ index changed during independent reconstruction')
    return dict(checked,source_revision=SOURCE_REVISION,source_files=593,raw_index_sha256=INDEX_SHA256)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory',type=Path,default=PUBLICATION)
    parser.add_argument('--baseline-directory',type=Path,default=baseline.PUBLICATION)
    parser.add_argument('--require-quality',action='store_true')
    args=parser.parse_args()
    print(json.dumps(verify_saved(args.directory,baseline_directory=args.baseline_directory,
                                require_quality=args.require_quality),sort_keys=True))


if __name__=='__main__':
    main()
