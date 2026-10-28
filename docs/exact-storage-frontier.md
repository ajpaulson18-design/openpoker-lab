# Exact selected-game strategy and history storage frontier

Status: shared preparation and rank-free census implementation with independent
small-game checks; source-frozen growth study and publication are pending.
This addresses the storage dependency left open by the
[foundation audit](foundation-first-audit.md), [direct topology](direct-shared-topology.md)
and [integer query integration](exact-dyadic-arithmetic.md). Removing private
worlds and pair output does not remove explicit information/action/history rows.

## Shared admitted boundary

`exact_selected_solver._prepare_exact_selected` is the same preparation called
by the actual four-street solve and `census_exact_selected_storage`. It validates
inputs, computes exact rank-free support, builds the direct immutable public DAG,
snapshots original terminal scales and admits the complete requested solve before
information rows, pair queries, ranking or training. The wrapper is a frozen
context containing aliases and counters; the solve unpacks and deletes it before
growing pair/row buffers. No cap, guard/counter order, probability or payoff
arithmetic changes. The census explicitly requests compact diagnostics.

Independent mechanical AST comparison against
`96e9fb1af560ad6ccf9c851679b0708c50bc74f4` confirms exact equivalence/in-order
placement of all 32 original setup statements and 34 remaining solve statements,
plus argument signatures. Separate same-runtime pre/post complete-output captures
match. Portable CI checks the shared helper is used exactly once, live default
and explicit-expanded outputs match completely, and integer policies/eight metrics
match the Fraction path. Cross-version bitwise policy hashes are not asserted.

## Measured quantities and extra admission

The census queries actual legal own-hand support for each decision prefix and
streams full logical occurrences. It counts:

- Retained DAG vertices/edges, vertex-plus-public-prefix contexts and context
  edges, logical visits and maximum depth.
- Supported information rows and action slots by street/global player, dense
  hand-slot holes, full-history token entries and UTF-8 token bytes.
- Serialized policy/action rows and the pure `4 * action_slots * 8` packed
  numeric-buffer payload, separately from dictionaries, history keys and output.
- The actual solve's modeled overlapping retained phases, bit forecasts and
  complete requested-work admission, distinct from the census's extra storage.

An optional separately admitted structural witness exports only unique public
vertices/actions/child IDs, original terminal contributions and canonical private
inputs/selected boards: O(V+E+H+B), with no expanded information histories,
policies or hidden worlds. A separate saved reviewer can reconstruct support and
stream histories without the production cursor/kernel. This verifies structural
counts conditional on the exported public graph; it is not an independent proof
that a larger betting graph obeys all poker rules. The small independent physical
controls and existing whole-game quality gates remain separate.

Before suit-group/support/orbit allocations, a separate bounded census reserves
logical entries for prefix support, unique contexts/edges, orbit keys with full
histories, prior/board transforms and bounded scratch. It reserves work for up to
24 transformations of every supported history and hand, and checks history-byte
upper bounds. The ceilings are 2,000,000 additional entries, 500,000,000 modeled
work and 16,000,000 token bytes, with smaller caller limits permitted. These are
conservative logical models, not measurements of Python allocation/RSS or CPU
guarantees. Native calls, ranking, pair queries and training are forbidden by
executed controls and the formal runner's actual call spies.

Requests rejected by either original full-solve admission or additional census
admission retain that rejection and leave downstream counts unknown. A census
does not relax a solver limit merely because no training is requested. It has no
quality gate or policy and must never be reported as a solved case. Independent
certificate shape screening, when reported by a development study, is only a
necessary-limit screen; even a shape pass is not full work/bit admission or an
accuracy certificate.

## Conservative exact suit-symmetry opportunity

Enumerate all 24 global suit bijections. Retain only maps preserving both
role-ordered exact parsed private-range weight maps and the entire selected
canonical-flop/ordered-turn/river set. Betting actions, chip rules and player
identity remain fixed. For each supported actor/hand/full-visible-history row,
transform private cards and revealed card tokens under that same map; canonicalize
flop cards while preserving turn/river reveal order and every betting token.
Count the resulting orbit representatives without altering any solver row.

This gives a sufficient conservative whole-game symmetry subgroup and potential
row reduction. Requiring the whole selected set may miss symmetries involving
unreachable branches; an identity-only subgroup does not prove no quotient
exists. Orbit counts are not a proof of realization/best-response equivalence,
approved policy compression, trained symmetric policies, or measured memory
savings. Distinct action histories at the same shared DAG vertex remain distinct
under every suit map. Whole-game weighted invariance and reach/sequence mapping
must be proved before integrating an actual strategy quotient.

## Executed checks and next gate

The original game reproduces 99 vertices, 259 contexts/321 context edges, 1,462
logical visits, 1,200 supported information rows and 2,402 action slots without
ranking, training or pair queries. Live small solves independently match every
supported row, action slot, full-history token count and token byte. Tests retain
ordered reveal mapping, no shared-vertex history merge, deterministic repeats,
orbit-disabled count parity and rejection before support/orbit allocation.

Terra independently reconstructs physical support and all 24 suit transformations
for symmetric and weight-asymmetric small games. Complete supported row/slot/
history counts, stabilizer permutations and row-orbit counts match. These are
bounded structural checks. The fixed source-frozen range/board/menu/symmetry
frontier, preserved first misses and independent saved census replay remain
required before selecting a compression frontier. The eventual choice must make
the complete solver's storage scalable; another standalone probability result
would not resolve this dependency.
