# Independent weighted full-deck flop validation

The existing `solve_postflop` API supports finite flop-start games with both
future cards and later-street betting. Its previous full-deck example has one
private pair; its weighted examples use selected runouts. Existing generic tests
share production card/range/ranking helpers and trust returned action menus in
parts of their replay. They remain useful regression tests, but do not establish
fully independent weighted full-deck validation.

The new [validator](../scripts/flop_multistreet_validation.py) owns a spelled
physical deck, strict literal hand/weight parsing, exact rational global chance
normalization, numeric betting transitions, public reveals and legal own-hand
best responses. Only the project's existing independent best-five ranker is
reused. Production range parsing, ranking, tree construction, training and
value/response evaluation are disabled during independent preparation/replay.
Every reachable own-hand/public-history action menu, amount, target, token,
visible board and probability is checked, including off-policy zero-reach rows.
Private opponents and unrevealed cards remain summed before response maximization.

The information-set constraint follows the finite perfect-recall model described
in [Zinkevich et al., 2007](https://proceedings.neurips.cc/paper/2007/file/08d98638c6fcd194a4b1e6992063e944-Paper.pdf).
No external source code, solver dependency or proprietary result is incorporated.
A small adversarial control has legal response value zero versus 0.5 when the
future sign is exposed; a turn reveal alone cannot expose a hidden river.

## Frozen experiment

The [plan](../benchmarks/weighted-full-deck-flop-v1.json) fixes `2c3d4h`, OOP
`AsAd:1,QsQd:0.5` and IP `AsKh:0.25,KsKd:1`. Three compatible private pairs have
exact priors 8/13, 1/13 and 4/13; the raw joint weight normalizer is 13/8.
Each pair has all 45-by-44 ordered future deals: 5,940 physical worlds. The
pot is 10 chips and each remaining stack is 5, with a half-pot sizing and no
raises. Check-through lines retain real turn/river decisions. Called all-ins
settle through the hidden future deck. This is a small finite abstraction,
not unrestricted Hold'em or evidence for broader stacks/ranges/action menus.

Rank-free complete admission confirms 9,512 public decisions, 248 chance nodes,
21,052 terminals and 30,812 total public states. There are 12 decision visits
per world and 148,500 retained planned operations. The maximum 400-sweep request
charges 2,376,000 world iterations and 28,512,000 world-node iterations under the
unchanged three-million/30-million limits. No production cap or backend changes.

The [runner](../scripts/benchmark_weighted_full_deck_flop.py) compares recursive
and planned vanilla/DCFR at 10/100/400 sweeps, with three alternating paired
complete calls: 36 timing observations. Timers include world/rank/tree creation,
training, exact diagnostics and canonical JSON/hash. Independent enumeration,
replay, garbage collection and compression/storage are outside timing. Two
separate ten-sweep vanilla calls measure complete-call Python traced allocation
for each backend, excluding serialization and replay; these are not process RSS
or high-iteration memory bounds. They are excluded from timing medians.

The Windows command reserves `ES_SYSTEM_REQUIRED` for its benchmark thread and
restores the previous state on exit, avoiding automatic idle suspension during
measurement. It does not change persistent power settings or request an active
display; explicit user sleep can still interrupt it. This uses the documented
[Windows execution-state API](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-setthreadexecutionstate).
UTC boundaries and every elapsed observation remain recorded; interrupted or
slow calls are not silently discarded.

Every producer physical sign and normalized world mass is compared against a
fresh independent ordered-deck/best-five enumeration before timing. Every raw
policy is retained in a separate lossless gzip file with compressed/raw byte
lengths and SHA-256 digests. The index retains all observations, source hashes,
metric gaps, complete-call medians, separate allocation peaks, exact repeat
checks and cross-backend agreement. Gzip is storage only; canonical policy bytes
are reproduced exactly. Readers enforce bounded file sizes and local filenames.

Independent scalar agreement must be within 1e-10; cross-backend policy and metric
agreement within 1e-8. Same-profile repeated complete payloads must be identical.
Final NashConv must be at most 0.005 chips in each backend/algorithm. Earlier and
final misses remain visible. A faithful artifact with validated rules/chance but
an unmet final quality gate is explicitly `quality-miss`; it is not an equilibrium
success. Measurement results and GitHub publication are checked separately.

[Validator tests](../tests/test_flop_multistreet_validation.py) cover the full
weighted physical game, all-street configured menus, raises/asymmetric refunds,
global blocker-conditioned prior shifts, tampered rows/actions/amounts/probabilities,
future-card leakage and the adversarial response control. A decimal-boundary case
checks raw binary64 call targets separately from displayed nine-decimal amounts
and the cleanup applied only when a fresh street starts. [Harness tests](../tests/test_benchmark_weighted_full_deck_flop.py)
cover rank-free admission, dirty-source rejection, disabled producer aliases and
bounded lossless evidence. No presentation, coaching or later-street solver kernel
is changed by this validation slice.
