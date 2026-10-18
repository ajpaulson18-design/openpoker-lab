# Exact selected-river turn equilibrium witness

This development-only witness proves value 50 OOP chips and zero exact
NashConv for one finite, conditioned turn-to-river game. It supplies an
independent two-street validation anchor; it does not expose a production
solver API or establish unrestricted Hold'em equilibrium accuracy.

## Fixed physical model

The [fixture](../scripts/turn_sequence_fixture.py) has board 2c7d9hJs,
OOP AsAh/Th6h with equal weights, IP QhQs, and selected rivers 8d/Kd.
Each of the four compatible private-hand/river worlds has joint mass 1/4.
OOP showdown signs are +1 for both ace worlds, +1 for Th6h on 8d and
-1 for Th6h on Kd. Independent best-five enumeration identifies a jack-high
straight on 8d, including the best five of six consecutive ranks.

Both streets use starting pot 100, total added-contribution caps 100/100,
one half-pot opening size, no raises and no extra all-in size. A configured
opening that reaches the stack cap is still named all_in. River decisions
retain matched turn contributions: a 50 turn bet/call and 50 river bet/call
settle at added contributions 100/100 and signed utility 150. A river fold
after the turn call returns the unmatched wager and transfers 100. A turn
fold transfers 50. Historical sunk pot investment is not added a second time.

Chance selects each world's river branch without multiplying or renormalizing
its joint mass again. Turn strategy rows use only own hand and public history;
the river card enters the history only after reveal. There are six turn rows
and 36 river rows, including all off-path information sets.

## Independent reference before candidate search

Sol froze a grouped-public-node construction before running the candidate.
Its [model reference](../benchmarks/results/turn-sequence-model-v1.json) has
67,825 bytes and SHA256
bf645923e5cbdd4bbffd4492f2ffe730c6780bb0c8ee1a430a7b2725c93c7d69.
Uniform strategies have exact V=2175/64, lower=25/16, upper=75 and
NashConv=1175/16. Against IP checking/calling on both streets, the legal
OOP response is 175/2. An explicitly illegal response that can peek at the
future river before its turn choice obtains 100, an illicit gain of 25/2.
This negative reference ensures the fixture detects hidden-future leakage.

The public tree has 63 nodes, 28 decisions, three chance nodes, 32 terminals
and eight node levels (seven edges on its longest path). The first proposed
depth estimate of seven levels failed independent preflight before search;
the structural estimate was corrected without changing the depth-64 cap.
There are 28/14 OOP/IP information sets, 57/29 sequences and 29/15 flow rows.
LP preflight admits 58x174 and 72x216 tableaus, respectively 10,325 and
15,841 cells including RHS/objective.

The [candidate](../scripts/turn_sequence_equilibrium.py) constructs each
physical world separately and reuses the unchanged bounded Fraction simplex.
The [independent verifier](../scripts/verify_turn_sequence.py) imports neither
candidate, LP search nor the exact-policy evaluator. It rebuilds A/E/F with
a grouped traversal, checks semantic sequence labels, every payoff/flow entry,
nonnegative realizations, exact dual inequalities and complementary slackness,
then independently recurses both legal own-hand responses. It validates the
complete policy's exact normalization record and separate binary64 projection.

## Result and limits

The accepted complete profile satisfies L=V=U=50, both response gains zero.
In this particular equilibrium both OOP hands bet the turn and IP folds.
River strategies are therefore off-path in the equilibrium profile, but all
river information sets remain covered by the primal/dual certificate and
unrestricted legal responses. Positive on-path river reach, larger hidden
supports, additional runouts and raises remain further validation work.

Lower/upper LPs use 110/197 pivots, 1,182,382/3,209,669 logical updates and
13/16 maximum accepted Fraction bits. Limits stay 96 rows, 256 columns,
25,000 tableau cells, 512 pivots, 10,000,000 updates and 4,096 Fraction bits.
Exact profile/response replay uses 1,370 work units under 100,000 work,
depth 64 and 65,536-bit caps. These counters do not bound CPU instructions,
elapsed time, temporary allocation or RSS. No speedup is claimed.

The [saved witness](../benchmarks/results/turn-sequence-equilibrium-v1.json)
has 326557 bytes and SHA256
4d5d1611d2d9fd76990fcb549f005e5bb631553e35534d5d5e374ec5ea2cae6c.
Generation stages and independently verifies bytes before replacing a report;
source/HEAD drift rejects publication, and a later failure restores prior bytes.
Saved verification checks current mathematical-source identities with only
LF/CRLF representation tolerance, accepts historical generation HEADs without
requiring those objects in shallow CI, and enforces a 2 MB file admission.
The frozen model's JSON bytes are checked exactly.

## Reproduction

    python -m scripts.turn_sequence_equilibrium
    python -m scripts.verify_turn_sequence
    python -m unittest tests.test_turn_sequence_equilibrium tests.test_turn_sequence_publication tests.test_river_sequence_form -v
    python -O -m unittest tests.test_turn_sequence_equilibrium tests.test_turn_sequence_publication -v
    python -m scripts.verify_river_blocker_equilibrium
    python -m scripts.verify_river_sequence
    python -m scripts.validate_docs

Sol specified the physical law and independent anchors, rejected candidate
construction/serialization mistakes, and executed validation. Luna implemented
the candidate and failure-preservation tests without executing tools that run
Python; no Luna execution is implied. All prior river witnesses, policies,
production sources and earlier-street implementations remain unchanged.

Executed local checks: 30 normal mathematical/legacy tests passed, plus five
publication tests; 14 optimized mathematical tests and five optimized
publication tests passed. All three current/earlier equilibrium verifiers pass.
Documentation checks pass for 116 Markdown files, 486 local links and 12
required entry points. Remote CI and merge status are separate publication
gates, not inferred from these local results.
