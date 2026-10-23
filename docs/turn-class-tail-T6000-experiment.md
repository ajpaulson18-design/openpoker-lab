# Fixed T6000/D2000 three-hand TURN class experiment

This records the single T6000/D2000 call specified by the frozen
[protocol](turn-class-tail-T6000-experiment-spec.md). The protocol remains a
historical record of the state before the call; this report is the completed
result. [PR #200](https://github.com/ajpaulson18-design/openpoker-lab/pull/200)
merged at `617b1939317c2f5a76799d27892e8b2415852ced` after 24 checks
(21 passed, 3 skipped). The separate T6000 experiment branch was created
from that merge; its later frozen source commit was
`2aa02c4f2db75beb7bc8a229e3c36073a56c5118`, with 87 pinned inputs. CI for
that source head completed nine checks without failures.

## Fixed game and request

The game is the configured three-hand TURN fixture on board `Js8d4c2h`.
OOP's range is `AsAh:0.5,KsKh:1,QsQh:0.75`; IP's is
`AcAd:1,KcKd:0.75,QcQd:0.5`. The pot is 100, effective stack 220, first
bet and raise sizes are half-pot, one raise is allowed, and all-in sizing is
disabled. This finite game contains 396 compatible physical worlds, 3,606
physical information sets and 8,046 legal action slots. The compact trainer
uses seven exact public-river classes and then restores all physical policy
rows.

The one request was CFR+ with 6,000 iterations, discarding the first 2,000
sweeps from averaging, under `turn-seven-class-vector-v1`. The retained
4,000 sweeps use their original weights (sum 16,002,000), for 12,000 regret
passes and 4,000 average passes. No schedule or quality threshold was changed.

## Result and independent evidence

The serialized policy **met** the exact normalized-policy NashConv target of
1/1000 chip. Its exact rational NashConv is preserved in the report; its
decimal projection is approximately 0.00003025771159 chip. The two exact
response gains project to 0.00002863425670 for OOP and 0.00000162345489 for
IP. The profile value projects to -23.60976995497 chips. It lies inside the
legal response interval, approximately [-23.60977157843, -23.60974132071].
This is evidence about this one configured finite game and this serialized
policy, not a separately known equilibrium value.

The independent physical exact audit and both generic class traversals agree
on all eight exact metrics. Class scanning and partition checks also pass.
Fresh physical numeric replay agrees with exact metrics within the fixed
1e-9 gate (the maximum recorded class-audit full-physical numeric difference
is 1.24e-14). The accepted policy includes all 3,606 rows and 8,046 actions.
Staged and final independent saved-artifact acceptance succeeded. A separate
full saved replay exited 0, checking all 87 frozen Git/current source identities
with four production helpers disabled and zero training calls. Its maximum
exact/numeric difference was 1.2343551101222112e-14. Before publication on
October 23, both saved files were rehashed and matched their original sizes
and digests. The solve was not repeated.

Full CLI reproduction requires the matching 87-source checkout and reachable
frozen Git commit, together with the saved files. The separate saved-artifact
test replays the actual policy mathematics and checks its nine current math-source
pins. That test works in shallow CI checkouts and permits unrelated producer
sources to evolve; it does not replace the full historical Git identity check.

The previous T750 policy remains unchanged and remains a target miss:
NashConv 0.010695489887132394 chip against the same 0.001 target. The new
result does not establish a general convergence trend, a known exact game
value, an advantage over another backend, or commercial solver parity.

## Runtime and local checks

The complete API call plus canonical JSON serialization took 87.7159917
seconds; the separately timed independent mathematical audit took 7.6698325
seconds. These are single-host observations, not a controlled performance
comparison or an RSS/allocation claim.

The completed frozen-source validation ran 30 tests in 9.019 seconds under
normal Python and 16.213 seconds under optimized Python. Documentation
validation covered 158 Markdown files and 815 local links. CI for source head
`2aa02c4f2db75beb7bc8a229e3c36073a56c5118` completed nine checks without
failures. These checks are evidence for the frozen source; publication checks
also run against the artifact changes.

On October 23 the four saved-artifact regression tests passed in 10.337 seconds
normally and 8.232 seconds under optimized Python. They replayed the actual
saved policy with the four production helpers disabled, authenticated its nine
math-source pins and preserved the old miss. Documentation validation passed
for 159 Markdown files, 821 local links and 12 required entry points before
integration with later main-branch work.

## Saved files

- [Accepted report](../benchmarks/results/turn-class-tail-T6000-v1.json):
  57,338 bytes, SHA-256
  `b974a13afcc93cb862f835af44d37fcc296b971a486c4f6c39c89d27b0d9d207`.
- [Untouched serialized policy](../benchmarks/results/turn-class-tail-T6000-v1-policy.json):
  2,553,093 bytes, SHA-256
  `17e1e61135e4e4efd8757ad764ff532e0cda01757173172b8c584b556c611652`.

Saved verification independently checks the fixed mathematics, admission
metadata and committed source/input identities. Runtime, host, call count and
observed internal ledger entries remain producer-reported observations.
