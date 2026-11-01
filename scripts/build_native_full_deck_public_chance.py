"""Build the source-authenticated exact full-deck public-chance probe.

This target is a probability-query test helper. It is not a sampler, trainer,
or accepted whole-game backend. The underlying shared builder authenticates the
source and pinned Boost header closure and requires an output directory outside
the checkout.
"""
import argparse
import json
from pathlib import Path

from scripts import build_native_exact_four_street as _builder


def build(output_directory: Path, *, sanitize: bool = False):
    """Build only the full-deck public-chance probe target."""
    return _builder.build(output_directory, target="full-deck-chance", sanitize=sanitize)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--sanitize", action="store_true")
    args = parser.parse_args()
    print(json.dumps(build(args.output_dir, sanitize=args.sanitize), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
