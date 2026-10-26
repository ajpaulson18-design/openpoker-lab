# Foundation-first execution record

Audit baseline: `901726e55caa0c45495b19668285162a04918cdc`, October 26, 2026.
See the [assessment, dependency map, ranked register and critical path](foundation-first-audit.md).

## Completed before publication

- Inspected live repository main and open PR inventory; main includes native
  four-street PR #243. Preserved the paused expanded-runner checkout and all
  historical benchmark artifacts.
- Retained [before-change underflow reproductions](../benchmarks/results/foundation-audit-v1/underflow-before.json),
  then contained zero/subnormal/nonfinite joint mass in four materialized
  producers without changing accepted arithmetic.
- Added independent public-route numerical regressions, the isolated exact
  full-deck prefix-mass prototype, and separate implementation/independent
  suites. Thirteen implementation controls and three independent seeded tests
  pass normally and with assertions disabled (worker execution).
- The independent test seed is 83441: 40 models, 160 public prefixes and 11,520
  pair comparisons, exact marginal and side-rescaling checks, plus physical
  sequential-deal and minimum-subnormal anchors.
- Measured four support sizes with three samples each. Exact prefix results
  matched independent physical-pair/sequential-deal or complete-deck symmetry
  controls. [Report](../benchmarks/results/foundation-audit-v1/prefix-mass.json)
  includes all timings, source hashes, platform and scope. Development measurement
  source status is recorded, rather than claiming a clean-source solver study.

## Intermediate failures and corrections

The first new regression run had one incorrect flop-runout test format; corrected
to an ordered two-card tuple, after which all six numerical regressions passed.
The first wider invocation included a nonexistent module name
`tests.test_native_public_selection`; 133 actual tests passed and the loader error
was not counted as a complete pass. The correct existing module is
`tests.test_four_street_native_selection`.

The corrected wider invocation passed 152 tests normally (21.051 seconds).
Its optimized run exposed the legacy replay's disabled assertion predicates:
151 passed and the hidden-future rejection test failed. This is retained as a
foundational finding, not dismissed as a test-mode issue. The verifier now uses
always-on checks and exact normalized chance products; 13 oracle/safety tests
then passed normally (0.717 seconds) and optimized (0.768 seconds), including an
actual optimized subprocess. Final combined results supersede these intermediate
counts below. No historical source-frozen result was regenerated.

The initial full-suite attempt was stopped during development after saved-policy
provenance guards correctly detected changing source snapshots. A separate
147.480-second reproduction showed `Source changed during benchmark or saved
verification` in the unchanged alternating-flop verifier. Another class-publication
replay also reported an error during this changing-source run. This interrupted
run is **not a full-suite pass**. Do not weaken provenance checks or rewrite
historical evidence to suppress a source-race rejection. Final clean-head GitHub
CI is the full-suite acceptance authority for this change.

## Final local checks

Using bundled CPython 3.12.14 and the existing authenticated MSVC native-public
executable (C++ source unchanged), the final combined invocation passed:

| Mode | Tests | Seconds | Result |
| --- | ---: | ---: | --- |
| Normal `python -B` | 175 | 40.922 | pass |
| Optimized `python -B -O` | 175 | 27.670 | pass |

Both invocations cover numerical underflow, both independent prefix suites,
preflop replay safety, optimized legacy replay, preflop/postflop/configured and
restricted river behavior, whole-game contracts/facade, public-batched training,
native compiled/selection controls, fixed-flop, shove/fold and monetary replay.
All 84 original assertion predicates across the four hardened validators now
remain active; the three mechanical conversions independently restore the
complete original module AST. No native rebuild or exhaustive evaluator sweep
was required locally because no native/ranking implementation changed; GitHub
native/sanitizer jobs independently build their normal controls.

The exact module lists, commands, source identities and log hashes are retained
in [the local validation receipt](../benchmarks/results/foundation-audit-v1/validation.json),
alongside [independent prefix review](../benchmarks/results/foundation-audit-v1/independent-prefix-review.json)
and [legacy review](../benchmarks/results/foundation-audit-v1/legacy-review.json).
Documentation validation and whitespace checks pass. Final PR checks are a
separate live publication requirement and are not inferred from these local runs.

## Remaining work

The [ranked register](foundation-first-audit.md#ranked-improvement-register)
remains authoritative. No full-deck trainer integration, broad-game convergence,
storage solution, action-value coaching feed, corpus/query service, production
hosting or commercial readiness is claimed.
