# Share suit-row history work across a decision's hands

Status: opt-in implementation with a [frozen twelve-call result](batched-suit-row-lookup-result.md)
and saved-only independent mathematical replay. A later separate Luna source
review and focused rerun find no blocker; final CI remains an acceptance gate.
Observed fixed-game timing gains do not establish
universal speed or memory improvements.

The [quotient profiles](suit-quotient-storage-result.md) show repeated full-history
route validation, suit transformation and public-prefix parsing in the
strategy-row lookup. Original 22-world T10 Q training performed 38,400 route
validations and history transformations despite unchanged public histories
across a decision's own hands. This is measured instrumentation, not a causal
claim that every repeated call should be removed.

Explicit `quotient_lookup="per-decision"` on the exact-product solver requires
`strategy_storage="suit-quotient"` and the existing explicit equivariant
training reduction. `quotient_lookup="per-row"` remains the reference/default.
The plan authenticates a complete decision route, actor and immutable action
menu once, transforms the full history once per group element, and parses those
public prefixes once. It then generates each supported hand's distinct images,
representative, ordinal mask bit and Q location using those temporary histories.
Unsupported hand holes remain explicit. Member bits, action values, sorted
chance reduction, staged phase checks, regret timing and averaging are unchanged.

Each call retains only transient hand/group/history scratch. No R member table,
decision cache or expanded set of histories is introduced. The old conservative
per-row whole-request work and storage admission remain in force; this option
does not credit savings or reopen a rejected game. Public per-row lookup and
its malformed-history checks remain available. Invalid actors, routes, menus,
support images and lookup selections reject explicitly. Trainer input also
checks the plan type before accessing its owner.

Executed controls compare every supported member and blocker hole with the
per-row reference, while instrumentation verifies exactly one route check and
G history transforms per batched decision. Complete private-flush and asymmetric
policies/eight metrics and independent exact BR certificates match. Injected
duplicate member bits still abort the responder phase. The 62-control combined
new/old quotient and solver selection passes optimized (29.193 s). Real-child
protocol and first-failure evidence controls are separately recorded before the
prescribed twelve-call study: three alternating original T10 pairs, a separate
traced pair, private-flush T100 and blocker T10 pairs.

These controls establish mapping and bounded full-game parity, not general
scalability, convergence or an overall memory benefit. Native exact computation,
asymmetric strategy growth, expanded diagnostics/output and scalable independent
certification remain separate foundation work.
