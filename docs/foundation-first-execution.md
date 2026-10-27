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

After freezing published source `aa06b46`, alternating-flop saved-only replay
passed. The class-proof check still rejected its frozen legacy source pin:
`scripts/preflop_validation.py` had intentionally evolved. That persistent
rejection was not a source race and must not be labeled one. The two-test run
finished in 207.233 seconds with one pass and that one source-pin rejection.

Historical proof-record inspection now has a distinct `authenticate_record()`
function. It checks unchanged external raw/artifact/interruption pins, physical
anchors, source manifest and saved policy data, without claiming today's code
can reconstruct the old proof. Existing `authenticate()`, `verify()` and the CLI
still require the exact original six-source closure before physical work;
reconstruction under evolved source remains rejected. Re-execute the historical
proof from its pinned historical revision, never by substituting metadata
authentication into an execution gate. No frozen record, hash or source guard
was changed. All six authentication/tampering/ordering tests pass normally
(0.183 seconds) and optimized (0.173 seconds); an initial restricted run hit
temporary-folder access errors and was rerun with required access. See the
[follow-up receipt](../benchmarks/results/foundation-audit-v1/record-authentication.json).

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

## Historical-source integration follow-up

The first full GitHub run at `aa06b46` executed 2,250 tests in 736.057 seconds
with 39 errors and eight failures. The failures exposed further whole-file
historical source coupling; they were not treated as a passing full suite.
A stable-source local integration pass then executed 179 tests in 635.593
seconds with 15 errors and one failure, narrowing the remaining work to
downstream source pins, committed-source requirements and one test's expected
input inventory. Both source and HEAD remained unchanged during that run.

The completed compatibility layer retains every frozen artifact and original
source pin. It authenticates inert archived files, exact reviewed current file
identities and unchanged mathematical ASTs; only named provenance functions
and three synthetic source-map fixtures differ. The independent rank bridge
has rank-only scope; it is not equivalence of the old/new chance laws. Current
source/HEAD/byte guards remain active, including introduced bridge/archive/guard
dependencies. LF/CRLF archive handling is tested explicitly. Source acceptance
still precedes mathematical reconstruction, with a regression that asserts the
reconstructor is never called after a source rejection.

Terra implemented the difficult integration after that model became available,
and root reviewed the diffs and corrected the authentication order and archive
line-ending handling before final acceptance. Focused bridge, rational, saved
native/held-out, raised-reference, blocker and suit checks pass. Public verifiers
that require committed source run after committing the integration; they were
never bypassed for local convenience. The exact scopes, intermediate failures,
reviewed transitions, source hashes and executed focused checks are preserved in
[the integration receipt](../benchmarks/results/foundation-audit-v1/provenance-integration.json).
Final clean-head CI remains required before merging.

## Synthetic-fixture integration correction

The full Python 3.11 matrix job at published head `e7717ae` ran 2,387 tests
in 965.278 seconds and failed with six errors and five failures (32 skipped).
The other matrix jobs were canceled by the workflow's failure policy; they are
not counted as completed passes. The seven other workflow runs passed.
The 25 public saved-policy replay tests and 198 optimized tests at that head
passed, but their coverage did not include four synthetic plumbing suites.

Those suites supplied invented verification digests and temporary artifact-only
roots. The new strict transition matcher correctly rejects those maps before
the tests reach their intended reconstruction, timing and ownership assertions.
This is a test-fixture integration issue, not a probability, ranking or frozen
policy failure. Production must continue rejecting unknown equal protected
hashes. The correction therefore isolates source-map stubs within the synthetic
plumbing tests and preserves the actual provenance adversarial checks. Any
changed pinned test file needs an inert archive and an explicitly reviewed
transition; no saved report is re-signed to accept the change.

The correction adds 12 explicitly scoped source-equality mocks around existing
synthetic audit/publication blocks in four suites. Removing only those exact
mock contexts reproduces each complete archived test AST; original assertion
bodies and actual provenance adversarial checks are preserved. The four
archives are included in current operation fingerprints. Production replay
scripts and frozen policies/reports are unchanged.

All 68 focused tests passed normally (47.659 seconds) and optimized (47.219
seconds), using a process-local shorter temporary directory for one existing
Windows path-length failure. With the original path, both modes passed 67/68;
the remaining staging path exceeded the Windows limit and had passed in Linux
CI. That environmental workaround changes no repository code and is not a
substitute for the final Linux matrix. Three real saved source maps also pass
their actual, unmocked source authentication. See the
[synthetic-fixture follow-up receipt](../benchmarks/results/foundation-audit-v1/synthetic-fixture-followup.json).

## Committed bridge closure correction

Independent final review accepted the synthetic isolation but reproduced a
predecessor P1 gap: a pre-existing edit to the compatibility helper could remain
stable throughout replay. The old source inventory's committed checks passed,
while the added helper was compared only against its operation-start bytes.
This was demonstrated without changing files by substituting an added comment
through `Path.read_bytes`; it is an evidence-provenance gap, not a changed poker
result. The final 2150452 local runs passed 199 optimized tests (74.919 seconds)
and 25 public saved replay tests (161.542 seconds), but did not discharge this
newly identified requirement.

`require_committed_bridge()` now authenticates every introduced bridge/archive
dependency, including both compatibility modules, against blobs from one captured
current HEAD before accepting source transitions or reconstructing evidence.
The check rejects missing/untracked inputs and malformed/truncated Git responses,
normalizes line endings only for committed text comparison, retains raw-byte
operation fingerprints, and rechecks HEAD before returning. Operation snapshots
also bind the revision, so revision drift cannot pass with unchanged file bytes.
The shared matchers and historical turn context use the same gate; rational,
profile, suit and sequence consumers are covered alongside direct replay.
Historical source-map inventories, all frozen records and production replay
script bytes are unchanged.

Regressions cover pre-existing helper edits before reconstruction, missing bridge
blobs, complete closure inventories and a HEAD change during snapshot collection.
Because this evidence-operation API requires committed helper source, acceptance
tests run after committing this correction. Clean-source focused/public replay
and final CI remain required. The
[closure follow-up receipt](../benchmarks/results/foundation-audit-v1/source-closure-followup.json)
preserves the finding, scope and implementation identities.

## Remaining work

### Contiguous strategy buffers and complete-call lifetime correction

The [packed operator strategy layout](packed-operator-strategy.md) connects
four contiguous binary64 buffers to actual unified four-street CFR+ without
merging information sets or changing the selected game. The first frozen study
passed policy/quality parity but **missed memory**: about 3.02 MB packed versus
2.79 MB row traced peaks. Phase tracing exposed avoidable key-copy validation
and output overlap. The correction preserves all coverage/cycle/menu checks
while reusing semantic-key references and releasing obsolete packed lookup,
policy and tree references during complete output construction.

At corrected source `c6090c891f3bbede6107c2a549e283b208d3852c`, the new study
retains identical complete policies, independent exact metrics and operator
work. Both T1000 policies meet <=1/1000 BB. T100 traced peaks are 2,793,147 bytes
rows and 2,337,517 packed (about 16.3% lower), while T100 medians are 7.51 s
and 8.60 s and single T1000 calls are 123.1 s and 134.1 s. The runtime cost,
T100 misses and complete first memory miss remain; no universal speed/RSS claim.

The [receipt and compressed raw studies](../benchmarks/results/packed-operator-storage-v1/receipt.json)
pin both source revisions, all raw policies/certificates/manifests, phase
diagnostics and actual commands/results. A separate no-training process repeats
saved-only independent numeric/exact replay. All 65 corrected controls pass
normally and optimized. Sol implemented/reviewed while worker usage limits
prevented final independent-agent engineering review; independent physical and
legal-BR/exact mathematical oracles remain in use. This is a measured bounded
storage integration, not a solution to exponential history/strategy growth or
completion of the overall foundation phase.

### Bounded rank reuse after the first integration

The [selected-board rank cache](selected-board-rank-cache.md) follows the
integrated operator's phase profile rather than changing solver scope. The
original 22-world game and one-board default remain intact. Capacity 64 reduces
T1000 rank calls from 991,485 to 23 with identical policies/exact metrics and
both independent <=1/1000 BB targets met. Recorded single complete calls are
119.0 s versus 80.8 s. Three-call T100 medians are 21.8 s versus 13.1 s; T100
accuracy misses remain. Traced allocation increases about 20 KB and process
peaks establish no general memory improvement. Pair/board scans and explicit
tree/action storage remain unchanged.

The [frozen study receipt](../benchmarks/results/selected-board-rank-cache-v1/receipt.json)
pins source `3ba64b386fad3ed5852182915220625232dee1bc`, compressed raw policies,
all independent certificates, misses, profiles and failure logs. A separate
no-training saved-only process compares the existing exact audits. Fifty-six
focused/independent/reference/contract tests pass normally and optimized. Terra
drafted independent tests before both workers hit usage limits; Sol completed
and reviewed the partial implementation. No final independent-agent engineering
review is claimed, and no full-deck or overall-goal completion follows.

### Subsequent selected-operator training milestone

The owner's next scalable-foundation goal now has a concrete
[non-materialized four-street integration](selected-operator-four-street.md),
measured at clean source `a3f289eeccff6f7357801d543872b11f632e3b61`. Sol defined
the globally conditioned selected-law/reach/payoff boundary; Luna implemented
the provider; Terra supplied independent physical tests and artifact scrutiny.
No model substitution was needed for this milestone.

Both the old and new paths produced identical complete strategies and exact
normalized metric maps on the 22-world T1000 game, meeting <=1/1000 BB with
numeric NashConv about 0.000399739 BB. The new producer/trainer/diagnostics store
no complete physical worlds or prefix/pair edges. Independent mathematical
validators may still materialize this bounded reference support deliberately.
The separate T10 miss, changed-reduction policy failure, restricted Windows
temporary-folder failures and interrupted first measurement are retained in
the [receipt and compressed raw studies](../benchmarks/results/selected-operator-four-street-v1/receipt.json).

Normal and optimized focused/reference/contract suites pass 46 tests; a committed
normal run excluding the three temporary-folder evidence tests passes 43. The
paired T10 runner records complete-call timings, traced Python allocation and
process working-set peaks, followed by numeric and exact saved replay. The
additional fixed T1000 orchestration makes one call per backend without retry.
A fresh process then repeats saved-only verification from the pinned manifest
with zero training. Complete artifact/source snapshots and manifests bind each
operation. Existing frozen historical artifacts and protected source modules
remain unchanged.

This is a representation and bounded accuracy milestone, with a measured runtime
regression (126.4 s vs 31.2 s T1000) and no tiny-game total-memory improvement.
Explicit tree/strategy storage and repeated pair/board/rank work are the next
limits. The rank-free 16/32/64-hand census rejections are preserved. The overall
foundation goal stays active; no full-deck trainer or commercial-scale claim.

The [ranked register](foundation-first-audit.md#ranked-improvement-register)
remains authoritative. No full-deck trainer integration, broad-game convergence,
storage solution, action-value coaching feed, corpus/query service, production
hosting or commercial readiness is claimed.
