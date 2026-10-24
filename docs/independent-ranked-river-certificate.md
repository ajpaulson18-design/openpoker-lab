# Independent exact ranked river certificate

The development audit in [river_ranked_certificate.py](../scripts/river_ranked_certificate.py)
replays a complete serialized fixed-board policy and computes exact profile value
and legal own-hand best responses using independent numeric betting rules,
independent best-five ranks and Fraction arithmetic. It does not train or use
production payoff, tree, rank, evaluation or BR helpers. The established
[physical rational certificate](../scripts/turn_rational_certificate.py) remains
unchanged and is the bounded equivalence oracle.

## Interface and game boundary

Call evaluate_ranked_certificate(result, oop_range, ip_range, board=board,
config=config). The board must have five cards. The policy must use
postflop-strategy-v1 with complete actor/own-hand/public-history rows, exact
ordered legal actions, finite probabilities and consistent public/config/count
metadata. Positive globally compatible hands require every row; dead hands
require no row. Missing, duplicate, extra or contradictory rows are rejected.

Each binary64 input weight is converted exactly to Fraction. Compatible range
products are normalized globally once using per-card incidence and an identical
holding correction. No pair worlds are materialized. Each serialized probability
row is explicitly normalized as in the physical exact oracle, retaining complete
input/normalized Fraction ledgers and action rows. Terminal utilities first cross
the independent numeric model's binary64 pot/2+matched boundary and are then
converted exactly; a rational-decimal replacement would describe another game.

Rank-group totals and per-card rank-group totals implement exact blocker
inclusion-exclusion. An identical two-card opponent holding is added back once
for compatibility/fold mass; its showdown signed mass is zero because ranks tie.
The sign is lower-opponent-rank mass minus higher-opponent-rank mass from the
responding player's perspective. Both-player vectors include global physical
mass once. Opponent policies update opponent reach; profile own actions form
expectations, and best responses maximize separately per own holding and public
history. Opponent cards never enter the responding player's choice.

## Separate bounded work model

The new independent-rank-card-vectors-v1 model retains ceilings of 100,000 work,
64 depth and 65,536 Fraction bits. These are different work units from the old
world-scan oracle. A rejection remains a rejection; it does not imply accuracy
or authorize raising any old limit. The output exposes all counters, maximum
Fraction size, tree depth, legal response interval, all eight metrics, threshold,
normalization rows and zero materialized worlds.

Static rank/card order and query endpoints are reserved once. Per-reach exact
prefix masses are cached only inside one audit's law; exact terminal vectors
are keyed by player, terminal kind, winner, binary64 payoff scale and immutable
opponent reach. Key scans, sort/search bounds, vector entries, cache storage
slots and Fraction operations are charged before work or insertion. Caches
cannot cross boards, ranges or solves. They retain successful exact objects
only; no floating fallback or cancellation approximation is used. The work
counter is a logical reservation model, not CPU, runtime, allocations or RSS.
Independent tree construction retains its existing state/decision guards and
charges states as they are reserved, followed by exact depth preflight before
profile/BR recursion.

## Evidence and limits

[Dedicated controls](../tests/test_river_ranked_certificate.py) compare every
metric, normalized row and normalization ledger of all 16 retained compiled
Python/native policies against both physical exact scan and partition outputs.
Production helpers are disabled, and physical world construction is forbidden
during the new audit. Additional controls cover exact mass/sign vectors,
blockers, dead hands, identical holdings, rank ties, fold winners, unequal-stack
refunds, mutable caller reach, local cache isolation, malformed policy metadata
and work/depth/bit rejection.

A 100-hand-per-player uniform royal-flush-board control is admitted under the
new work ceiling and agrees with independent physical numeric replay. Its
known game value 0 lies in the response interval. The physical fixture's ranks
are identically tied by the public royal flush; it is a known-value capacity
control. The old physical exact 100,000-work rejection is explicitly preserved.
This proves neither equilibrium of that uniform profile nor admission/accuracy
for arbitrary100-hand supports, non-tied boards or richer betting trees. Such
studies still need frozen source, complete raw policies, independent numeric
replay and explicit admission/results. The ongoing16x16 study uses its original
physical auditor and is unaffected by this separate development.
