# Full-physical raised-turn audit wrapper

`scripts/audit_raised_turn_full_physical.py` creates a separate, immutable
no-training report from the independent exact oracle in
`scripts/full_physical_exact_oracle.py`. It reads the fixed check/call anchor,
a constructed legal single-card policy control, the two saved original
numeric tails, and the two saved clean witnesses. It does not rebuild or clean
a saved policy. The anchor and illegal future-aware control are explicit checks.
The constructed control changes only IP's `KcKd` row at
`['check', 'check', 'river@2c', 'check']` from check to `bet@50`; its exact value
identity is `-2500/231 + 50/308 = -4925/462`.

The wrapper pins the numeric-tail report, exact-tail report, clean-witness
report, physical-reference report, and every saved policy byte. It rechecks
those bytes, current `HEAD`, and source fingerprints around every oracle call
and before and after publication. Source fingerprints include the wrapper,
oracle, tests, reference model, and physical card/tree/row-legality
dependencies. Historical generation commits in the accepted reports remain
provenance; they do not need to equal the current audit `HEAD`.

The output stores the eight exact metrics as canonical Fraction strings and
reports the physical traversal counters separately. It records 176 worlds, 48
physical runouts, full chance branches, and the oracle's own weighted-row
operation count. It does not relabel those counts as generic certificate work
or change any generic work cap. Saved clean witnesses must independently yield
OOP value `-400/21` and zero NashConv; original numeric tails keep their exact
positive gaps.

## Independent arithmetic and information boundary

The core imports neither candidate exact auditor, the generic Fraction
certificate helper nor a production best-response evaluator. It shares the
already independent [physical reference](full-deck-raised-turn.md), card/range
grammar, public tree and row-legality checker. It implements its own exact
probability normalization, terminal arithmetic and policy/response traversal.
Each binary64 probability becomes an exact Fraction and each complete row is
renormalized exactly; metrics therefore certify that normalized interpretation,
not raw floating sums. The report counts adjusted rows.

The traversal keeps original joint private-hand/river masses. Profile value
multiplies each world's mass by that acting hand's fixed strategy. At an
opponent decision in a response calculation, it multiplies by the opponent's
hand/history policy and sums action branches. At a responder decision, it
evaluates every action over the entire hidden-world batch before maximizing
(or minimizing OOP value for IP). Root response traversals are separate by the
responder's own hand. At an actual river reveal, it splits by that physical
card and sums branches, without renormalizing away their original masses.
Thus turn choices integrate the unknown future before optimization.

Terminals use independently implemented centered utility
`sign * (pot/2 + min(cumulative contributions))`. Fold winners determine fold
sign; showdown sign comes from this oracle's own best-five-of-seven evaluator,
with a cross-check against the physical reference. The utility preserves matched
wagers and refunds. The handwritten check/call anchor and a deliberately illegal
future-aware response provide separate known-value and information checks.

## Bounds and scope

This oracle is fixed to 176 worlds, 48 public river cards, 2,404 policy rows,
3,039 public nodes, 1,254 decisions and depth nine. Five chance nodes retain all
240 physical chance edges. Two own-hand profile traversals plus four own-hand
response traversals visit exactly `6 * 3,039 = 18,234` public nodes per case.
The separately bounded weighted-row counter increments once when a world at a
fixed-policy decision distributes its mass across that row's actions; it is a
row visit, not a count of every arithmetic operation. Its conservative bound is
`3 * 176 * 3,039 = 1,604,592`. Model construction, row legality, normalization
and hand ranking remain separately fixed preparation work.

Stored Fraction numerators and denominators are limited to 65,536 bits. These
structural/row counts differ from the old helper's 100,000 modeled exact-work
units; that helper and its caps remain unchanged. They do not bound elapsed
time, every temporary integer allocation or RSS. This is not an arbitrary-game
auditor. The single-card control deliberately violates chance-class policy
constancy while retaining the original full game, exercising the physical
oracle beyond the preceding projection's accepted policy family.

Generation is exclusive: a staged report is reconstructed and verified before
an exclusive hard-link publication. A failure removes only this invocation's
staging and published files. Existing reports are never replaced. Run
`python -m scripts.audit_raised_turn_full_physical` to generate or add
`--verify` to reconstruct an existing report without training.

## Validation

The four independent core tests passed in normal Python (9.542 seconds) and
optimized Python (9.380 seconds). They check all eight metrics against the
handwritten anchor and saved profiles, both illegal future-aware responses,
and the single-card control against complete independent numeric replay.
The five wrapper tests passed in normal Python (166.670 seconds) and optimized
Python (171.831 seconds), including full generation and historical-HEAD replay,
metric/counter tampering, late accepted-input drift, owned rollback and a
foreign path replacement after publication. The replacement regression failed
before the ownership fix and passed afterward.

## Immutable report

The [saved report](../benchmarks/results/full-deck-raised-turn-full-physical-v1.json)
is 39,230 bytes, SHA256
`b84527caeced27674d136479cc6700929309ed6677e8ee6bd10c9e93f35cbd11`.
Its generation HEAD is `7db92fea948a65b78b609f285cfb63e1ea6216d3`;
all ten source fingerprints match committed Git bytes. Staged and published
full reconstruction passed with no training.

| Profile | Exact NashConv | Weighted row visits | Maximum stored Fraction bits |
| --- | ---: | ---: | ---: |
| Handwritten check/call | 75 | 2,816 | 15 |
| Single-card row control | 75 | 2,820 | 15 |
| Original materialized tail | positive, about 2.290e-19 | 8,476 | 4,554 |
| Clean materialized witness | 0 | 3,756 | 399 |
| Original matrix-free tail | positive, about 4.367e-19 | 9,264 | 5,035 |
| Clean matrix-free witness | 0 | 3,756 | 395 |

Both clean witnesses have exact value OOP `-400/21`, IP `400/21` and both legal
response gains zero. All six cases retain 18,234 structural node visits and all
48 physical river cards. Original saved policies and input reports are unchanged.
The exact metrics agree with the preceding checked chance-class audit, while
this implementation uses its own full-physical arithmetic and best responses.

The accepted-report regression binds this report hash and disables the five
production capture/solve/trainer entry points. Complete saved reconstruction
passed in normal Python (16.779 seconds) and optimized Python (14.262 seconds).
