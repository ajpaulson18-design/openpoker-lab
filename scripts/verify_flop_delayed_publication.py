"""Authenticate the immutable delayed-CFR+ study and its original quality decisions."""
import argparse
import hashlib
import json
from pathlib import Path
from scripts import benchmark_flop_delayed_cfrplus as study
from scripts.benchmark_preflop_covered_counts import checksum

PUBLICATION = study.ROOT / 'benchmarks/results/weighted-full-deck-flop-delayed-cfrplus-v1'
INDEX_SHA256 = '6acb8dc5744fd8e544440b7204dc8d9962b915adeb4a26764c9dfdab22abc85b'
SOURCE_REVISION = '676d805106f05e654c5b2d0782ca2e16213c7f26'
SOURCE_FILES = 602
SOURCE_MANIFEST_SHA256 = '296696179d3d3480bdce25e42edac9872c9ed13ac40d029b1d10e134c773ef56'


def verify_saved(directory=PUBLICATION, *, baseline_directory=study.baseline_publication.PUBLICATION,
                 require_quality=False):
    directory=Path(directory);path=directory/'index.json'
    if path.is_symlink() or not path.is_file() or path.stat().st_size>study.MAX_INDEX_BYTES:
        raise ValueError('Invalid bounded published delayed-CFR+ index')
    raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=INDEX_SHA256:
        raise ValueError('Immutable published delayed-CFR+ observation changed')
    report=json.loads(raw);before=report['source_before']
    if (before!=report['source_after'] or before['status']
            or before['revision']!=SOURCE_REVISION
            or len(before['source_hashes'])!=SOURCE_FILES
            or checksum(before['source_hashes'])!=SOURCE_MANIFEST_SHA256):
        raise ValueError('Published delayed-CFR+ source identity changed')
    if require_quality and not report['quality_gate_met']:
        raise ValueError('Original complete-study final quality target remains unmet')
    checked=study.verify_saved(directory,baseline_directory)
    if path.read_bytes()!=raw:
        raise ValueError('Published delayed-CFR+ index changed during reconstruction')
    return dict(checked,source_revision=SOURCE_REVISION,source_files=SOURCE_FILES,
                raw_index_sha256=INDEX_SHA256)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory',type=Path,default=PUBLICATION)
    parser.add_argument('--baseline-directory',type=Path,default=study.baseline_publication.PUBLICATION)
    parser.add_argument('--require-quality',action='store_true')
    args=parser.parse_args()
    print(json.dumps(verify_saved(args.directory,baseline_directory=args.baseline_directory,
                                 require_quality=args.require_quality),sort_keys=True))


if __name__=='__main__':
    main()
