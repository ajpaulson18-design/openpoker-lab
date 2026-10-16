# Optional native full-board preflop equity preparation

The separate native entry point accelerates bounded full-board counting. The
ordinary Python preparation and solver remain the default/reference. This is a
source-checkout development feature: explicitly build the project-owned C helper
with an installed compiler, then choose it. Compilation, installation and
fallback are never automatic.

```sh
python -m scripts.build_native_preflop --output-dir build/native-preflop
```

POSIX requires `cc`; Windows requires an installed x64 MSVC developer environment.
See Microsoft's [command-line setup](https://learn.microsoft.com/en-us/cpp/build/building-on-the-command-line?view=msvc-170).
The builder uses argument arrays, fixed recorded flags and explicit failures.
There is no new Python dependency.

```python
from pokerlab.native_preflop_equity import prepare_native_preflop_equities
from pokerlab.preflop_push_fold import solve_prepared_push_fold

prepared = prepare_native_preflop_equities(
    "AsAd:1,QsQd:.5", "AsKh:.25,KsKd:1",
    build_directory="build/native-preflop",
)
result = solve_prepared_push_fold(
    prepared.equities, config={"starting_stack": [3, 2]},
    iterations=2000, algorithm="cfrplus",
)
provenance = prepared.metadata
```

Normal expansion, exact binary64-weight fractions, collision conditioning and
all fixed caps run before binary lookup/execution: 4,096 candidate pairs, four
compatible pairs, 6,849,216 unordered boards and 13,698,432 logical hand-rank
evaluations. Each pair still counts all 1,712,304 final boards. Native output
supplies only integer W/T/L counts; Python constructs and validates the same
immutable `FullBoardEquities`, exact category masses and world ordering.
Downstream source-inclusive solver admission is unchanged. Preparation alone
does not admit an arbitrary training request.

This separate API has no progress callback; existing Python callbacks retain
their established behavior. Native preparation has a 120-second process timeout,
rejects changed source/binary identities and malformed output, and never silently
substitutes Python. The bounded ASCII protocol validates all input before work,
caps COUNT at four pairs and conformance RANK at 4,096 hands, and rejects invalid
cards, duplicate cards and trailing input. Invalid requests emit no partial
result. Python caps response reads; temporary files are not a hard storage cap
against a faulty or untrusted executable.

Build provenance records compiler path/version, flags, platform, raw and
LF-normalized C-source SHA-256 and executable SHA-256. Preparation returns it
separately from the ordinary solver payload, with actual logical board and rank
counts, and checks current source/executable bytes before and after execution.
These identities and structural checks are reproducibility information, not
authentication of arbitrary local binaries or caller-supplied counts.

## Implementation and distribution

`native/preflop_equity.c` implements this repository's own category/kicker rules
with small rank-count/suit-mask arrays and ascending board loops. No imported
evaluator, lookup table, third-party source or binary is used. No executable or
object file is committed, and the repository license remains unchanged.

Local MSVC builds use `/MT`; see Microsoft's [runtime linkage documentation](https://learn.microsoft.com/en-us/cpp/build/reference/md-mt-ld-use-run-time-library?view=msvc-170).
This slice distributes source. Shipping compiled applications would require a
separate packaging/runtime-notice review under the applicable toolchain terms;
these build facts are not legal clearance.

## Validation and measured status

Focused local MSVC checks pass independent best-five vectors, deterministic
seven-card samples, malformed-input cases, published full-board counts and
own-hand best-response replay. Dedicated CI builds with installed MSVC on Windows
and `cc` on Linux; ordinary Python-only CI requires no compiler.

The planned frozen benchmark retains three complete cold Python/native samples
for the same three-pair game, exact solver-payload equality, independent published
counts and numeric-rule replay, separate four-pair coverage, unchanged admission
and every timing observation. The exhaustive validator compares every five-card
rank tuple with the independent oracle and known category totals; this does not
exhaust six- or seven-card hands. Python allocation traces exclude native-process
allocations and RSS. Exploratory results are not final measurements.

The game remains heads-up SB fold/shove and BB fold/call with forced showdown.
Calculation speed adds no betting branches, multiway support or equilibrium
guarantee.
