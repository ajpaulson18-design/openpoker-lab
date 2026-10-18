# Weighted turn equilibrium with on-path river decisions

This separate development witness proves exact value 30 OOP chips and zero
NashConv for a finite selected-river turn game. Both a hand-written policy and
a subsequently searched LP policy have exact river-decision reach one.
It extends the [first turn witness](turn-sequence-equilibrium.md), whose
equilibrium folded before the river. These are small configured-game anchors,
not unrestricted Hold'em solutions or a new production API.

## Fixed game and independent anchors

The [fixture](../scripts/turn_weighted_sequence_fixture.py) keeps board
2c7d9hJs, IP QhQs, selected rivers 8d/Kd, starting pot 100, added stack caps
100/100, half-pot opens, no raises and no extra all-in size. OOP AsAh has
weight 0.25 and Th6h weight 0.75. The four globally conditioned worlds have
masses 1/8,1/8,3/8,3/8 for AA8/AAK/draw8/drawK. Signs are +,+,+,-.
The draw makes a jack-high straight on 8d. Conditional sign means are 1 on
8d and -1/2 on Kd; the unconditional sign mean is 1/4.

A first input encoding using weights 1 and 3 was rejected before model/search
because range weights must lie within [0,1]. Exact proportional weights
0.25 and 0.75 preserve the predeclared physical law; no cap or anchor changed.
The original rejected source identity and failure are retained in the local
review evidence.

Before LP search, Sol froze a grouped-public-tree
[model reference](../benchmarks/results/turn-weighted-sequence-model-v1.json)
and a complete [hand-written policy](../benchmarks/results/turn-weighted-analytic-policy-v1.json).
Uniform V=2975/128, lower=-625/32, upper=125/2, NC=2625/32. Against IP
check/call, legal OOP BR=225/4 while illegal future peeking gives 75, a gap
75/4. Direct action-history equations agree with the separately executed
reference. One uniform river street with matched prior contribution c has
M=50+c, b=min(M,100-c), and value M/8+sign*(5M/8+3b/8). Integrating the
uniform turn actions gives 25/2+(1375/32)*meanSign.

The model reference has 67,938 bytes, SHA256
7059a28917fb04d2be6d846245160a61539da83456a26c534e5e34d3c1841f2a.
The hand-written policy has 30,249 bytes, SHA256
1a03b4de8625be17c016f7b87b4defd66be8fe1692b1559e8542cf11f292cf37.

## Hand-written equilibrium before search

Both OOP hands bet the turn; IP calls. If OOP instead checks, IP bets and
OOP's draw calls. At the river, IP checks after OOP checks. On 8d, OOP bets
and IP folds. On Kd after a turn call, AA bets, the draw bluffs 1/15, and IP
calls an opening 4/5. At the off-path check/check turn continuation, the
corresponding Kd bluff/call probabilities are 1/9 and 2/3. AA calls and the
draw folds against an IP river bet on Kd. All 42 own-hand/public-history rows
are fully specified in the artifact.

At the reached Kd river, IP is indifferent between folding for -100 and
calling a bet whose bluff fraction is 1/6. The draw's bet EV is
100-(250)*(4/5)=-100, equal to checking. AA's bet EV is 140. Thus OOP's
conditional Kd value is (1/4)*140-(3/4)*100=-40, and its 8d value is 100.
Their equal river mixture gives 30. Independent exact own-hand response
recursion proves L=V=U=30 for the complete policy, rather than inferring
Nash equilibrium from this local river calculation. All eight binary64 replay
differences were zero for this policy. Its joint-mass reach to the river is 1.

## Independent LP witness and verification

The [candidate](../scripts/turn_weighted_sequence_equilibrium.py) separately
constructs sequences per physical world and reuses the unchanged bounded
Fraction simplex. Its draw checks the turn with probability 8/15 and bets
7/15; AA bets. IP calls the turn bet, and bets after a turn check. The draw
calls that bet. Exact public chance reach is 3/5 through bet/call and 2/5
through check/bet/call. Total river-decision and terminal reach are both 1.
The separate complete policy again proves L=V=U=30 and both response gains 0.

The [independent verifier](../scripts/verify_turn_weighted_sequence.py) imports
neither LP/candidate nor the exact-policy evaluator. It reconstructs the
pre-search reference and hand-written policy bytes; rebuilds every A/E/F
entry using grouped public traversal; checks exact realization/flow, dual
inequalities, complementarity and objectives; and independently recurses
both legal responses. It validates exact normalization and separate float
projection, and rejects a proof without positive on-path river-decision reach.
Source/HEAD guards, staged replacement/rollback and 2 MB input admission remain
active under optimization. Historical generation HEAD objects need not exist
in a shallow verifying checkout.

Tree dimensions stay 63 nodes, eight levels, 28 decisions, three chance nodes,
32 terminals, 28/14 information sets and 57/29 sequences. Lower/upper LPs use
121/175 pivots, 1,298,509/2,854,831 logical updates and 15/16 maximum Fraction
bits. All earlier caps are unchanged: 96 rows, 256 columns, 25,000 tableau
cells, 512 pivots, 10,000,000 updates, 4,096 bits; exact replay 100,000 work,
depth 64, 65,536 bits. The exact replay uses 1,716 work. Logical counters do
not bound CPU, temporary allocations, elapsed time or RSS; no speedup is claimed.

The [LP artifact](../benchmarks/results/turn-weighted-sequence-equilibrium-v1.json)
has 327,067 bytes, SHA256
0c4b8c1dfaae1332504c05e798944021b1cd758e54dc224c9a213e01e5b5a541.

## Executed checks and reproduction

All 22 new mathematical/publication tests passed in normal Python (13.173s)
and optimized Python (16.999s). Tests establish a valid proof before adversarial
cases, and cover chance weights/rescaling, future peeking, cumulative wager
carry/refunds, analytical policy identity, zero river reach, A/E/F and both
primal/dual sides, source/HEAD drift, canonical fractions and typed resources,
publication rollback, file limits and bounded-fraction admission before path arithmetic. All three earlier equilibrium verifiers
also pass without changing their frozen source or artifacts.

    python -m scripts.turn_weighted_sequence_equilibrium
    python -m scripts.verify_turn_weighted_sequence
    python -m unittest tests.test_turn_weighted_sequence tests.test_turn_weighted_sequence_publication -v
    python -O -m unittest tests.test_turn_weighted_sequence tests.test_turn_weighted_sequence_publication -v
    python -m scripts.verify_turn_sequence
    python -m scripts.verify_river_blocker_equilibrium
    python -m scripts.verify_river_sequence
    python -m scripts.validate_docs

Sol designed and executed the independent references, analytical policy,
verification and tests; Luna implemented the bounded candidate without Python
execution. Production and earlier-street code remain unchanged. The next
priority is measuring complete production CFR+ policies against this proved
value and legal-response interval, retaining every fixed-budget target miss.
Larger ranges, additional rivers, raises and full-deck exact equilibrium
remain further work.
