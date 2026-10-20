"""Authenticate and independently reconstruct the immutable full-future flop study."""
import argparse
import hashlib
import json
from pathlib import Path
from scripts import benchmark_weighted_full_deck_flop as experiment
from scripts.benchmark_preflop_covered_counts import checksum

PUBLICATION = experiment.ROOT / 'benchmarks/results/weighted-full-deck-flop-v1'
INDEX_SHA256 = '8d259315fcc280020bf59039d5557620f0115efd05ee2996627dad14c28d7b88'
SOURCE_REVISION = '3963e3c366275ec31863049992acc1830ba17d4a'
SOURCE_MANIFEST_SHA256 = '8a482058567a779d3c781cb7a72f795c918898ecc01cdffe5fd91093582006b5'


def verify_saved(directory=PUBLICATION, *, require_quality=False):
    directory = Path(directory); path = directory / 'index.json'
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 4*1024*1024:
        raise ValueError('Invalid bounded published index')
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != INDEX_SHA256:
        raise ValueError('Immutable published index changed')
    report = json.loads(raw); before = report['source_before']
    if (before != report['source_after'] or before['status']
            or before['revision'] != SOURCE_REVISION or len(before['source_hashes']) != 584
            or checksum(before['source_hashes']) != SOURCE_MANIFEST_SHA256):
        raise ValueError('Published frozen source identity changed')
    if require_quality and not report['quality_gate_met']:
        raise ValueError('Original final quality target remains unmet')
    checked = experiment.verify_saved(directory, require_quality=require_quality)
    if path.read_bytes() != raw:
        raise ValueError('Published index changed during independent reconstruction')
    return dict(checked, source_revision=SOURCE_REVISION, source_files=584,
                raw_index_sha256=INDEX_SHA256)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory',type=Path,default=PUBLICATION)
    parser.add_argument('--require-quality',action='store_true')
    args = parser.parse_args()
    print(json.dumps(verify_saved(args.directory,require_quality=args.require_quality),sort_keys=True))


if __name__ == '__main__':
    main()
