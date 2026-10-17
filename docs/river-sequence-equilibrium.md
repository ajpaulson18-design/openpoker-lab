# Exact equilibrium witnesses for two fixed river games

## Result and scope

The development sequence-form search produces complete rational equilibrium
witnesses for the two small fixed-board games used in the
[river policy certificate audit](river-rational-certificate.md):

| Configured game | Exact OOP value | Exact NashConv |
| --- | ---: | ---: |
| Polarised nuts/air versus bluff-catcher | 25 | 0 |
| Weighted raised game | -43339/2163 (about -20.0365233472 chips) | 0 |

This establishes the value of the weighted raised configured game, previously
known only inside saved-policy response intervals. It does not change the
production solver, its finite-iteration profiles, their target outcomes, or
earlier-street code. These are standard-library development tools and fixed
finite heads-up games, not an unrestricted Hold'em equilibrium API.

The model is the unchanged independent numeric validator's physical worlds,
ranks, legal action tree and binary64 terminal constants. Exact Fractions
represent those constants and the supplied rational policy. This does not
prove that arbitrary decimal sizing intent equals those constants. The float
projection of a rational witness is checked separately and is not claimed to
have an exactly zero binary64 gap.

## Why sequence form

The weighted game's 36 information sets give 14,745,600 complete OOP and
84,934,656 complete IP pure policies. The sequence representation instead has
49 OOP and 53 IP coordinates, including one empty sequence per player.
Its flow matrices have 17 and 21 rows and its payoff matrix is 49 by 53 with
98 nonzero entries. The polarised game has 9/5 sequence coordinates, 5/3 flow
rows and 10 nonzero payoff entries.

A nonempty sequence identifies an own private hand, a full public history and
an action token. Each information set has one parent own sequence; all its
child realization probabilities sum to that parent's probability. The empty
sequence has realization one. Opponent actions and unknown opponent cards do
not create new private policy variables. Private chance probabilities enter
the payoff matrix, not the behavioral flow constraints.

Each payoff coefficient sums exact world mass times the configured terminal
OOP payoff over leaves with the same pair of own sequences. The four weighted
worlds have masses/signs AA/AA = 4/21, 0; AA/KK = 1/7, +1; KK/AA = 8/21, -1;
KK/KK = 2/7, 0. These are checked against hand-derived constants.

For the general sequence-form construction and perfect-recall flow equations,
see [Koller, Megiddo and von Stengel, section 2](https://ai.stanford.edu/~koller/Papers/Koller%2Bal%3AGEB96.pdf).
The zero-sum programs below specialize those flow/payoff relations. No
third-party implementation or general-sum equilibrium algorithm is included.

## Exact proof, separate from candidate search

Write OOP/IP realization plans as x/y, their flow equations as Ex=e and Fy=f,
and the OOP payoff matrix as A. Both plans are nonnegative. The candidate
search solves these rational programs, with free dual vectors q/p represented
by positive and negative parts:

```text
maximize f^T q:  Ex=e, x>=0, A^T x-F^T q>=0
minimize e^T p:  Fy=f, y>=0, E^T p-A y>=0
```

The first objective gives a guaranteed OOP lower value L; the second gives an
upper value U. For any legal opposing realization, nonnegative dual slack
and the flow equations imply that x secures at least L and y permits at most
U. When the supplied profile's value V satisfies L=V=U, both players are
mutual best responses. This conclusion uses the checked feasible vectors and
equal objectives; a successful pivot termination alone is insufficient.

The [independent verifier](../scripts/verify_river_sequence.py) imports neither
the candidate search nor the bounded exact-policy evaluator. It freshly
rebuilds the sequence/payoff/flow model using a different traversal, compares
the model identity frozen by Sol before candidate output, validates all primal
flows and dual slacks, checks complementary slackness and reconstructs the
complete rational behavior from child/parent realizations. Zero-parent rows
remain complete legal distributions.

A separate own-hand profile/min/max recursion integrates unknown opposing
hands and optimizes the full legal response. All eight metrics must agree,
both gains must be exactly zero, and the polarised value must equal 25.
Every candidate value must also remain inside every earlier exact response
interval for that fixture. Complete action metadata, normalization rows and
ledgers, uniform-policy references, saved residuals and float-projection
replay are checked as part of the proof record. Runtime checks remain active
under Python optimization.

## Bounded search and provenance

The [candidate generator](../scripts/river_sequence_form.py) uses exact
two-phase simplex with a feasible artificial basis and Bland entering/leaving
order. Artificial variables must be zero and removed from the basis before
phase two; redundant rows require a zero-row proof. Infeasibility,
unboundedness and limit exhaustion reject explicitly.

Each complete LP, including phase one, artificial cleanup and phase two, is
limited to 96 rows, 256 columns, 25,000 tableau cells including RHS/objective
storage, 512 pivots, 10,000,000 modeled cell updates and accepted Fraction
numerator/denominator widths of 4,096 bits. Dimensions are checked before
dense LP allocation; objective setup, pivot updates and ratio scans are
charged. These are declared logical search and accepted-operand limits, not
CPU-instruction, transient-allocation, elapsed-time or RSS bounds.

The unchanged exact-policy evaluator independently checks the candidate
rational rows under its existing 100,000-work, depth-64 and 65,536-bit limits.
Its counters and the search's pivot/work counters are generation observations;
saved-file proof verification recomputes the mathematics without rerunning
simplex.

The report pins its generation context and relevant input/source bytes.
Generation and verification require stable current HEAD/source snapshots
during each operation. Later verification preserves the original generation
context, permits ordinary checkout line-ending differences and unrelated
production inventory changes, and still enforces pinned model/witness sources.
No historical trained policy or earlier report is rewritten.

## Reproduction

```text
python -m scripts.river_sequence_form
python -m scripts.verify_river_sequence
python -m unittest tests.test_river_sequence_form -v
python -O -m unittest tests.test_river_sequence_form -v
python -m scripts.validate_docs
```

Generation writes and reloads the
[saved witness report](../benchmarks/results/river-sequence-equilibrium-v1.json),
then invokes independent proof verification. Verification alone replays the
saved mathematical witness without repeating the candidate search.

## Executed evidence

The final report was generated at `5f69bc0c1ebba7415ed1eaa7cf661d11571497b1`, then
reloaded and independently verified. Its 371,669 bytes have SHA256
`34339978294625a8fcb104e6e4492b7059db1cfe8a54a97fe1faadac26c2ca82`. It retains 87 source/input fingerprints.

| Fixed game / program | Pivots | Logical cell updates | Maximum accepted Fraction bits |
| --- | ---: | ---: | ---: |
| river-polarised-bluffcatcher / lower_lp | 14 | 6094 | 8 |
| river-polarised-bluffcatcher / upper_lp | 24 | 13752 | 8 |
| river-weighted-raises / lower_lp | 228 | 3576268 | 53 |
| river-weighted-raises / upper_lp | 243 | 3668383 | 55 |

All 16 focused tests passed normally (11.905 seconds) and with `python -O`
(12.016 seconds). The untouched certificate is positively verified before
tamper cases run. Tests reject forged zero values, altered coefficient/flow/
dual/normalization/topology data, invalid typed counters, missing/duplicate
records and changed prior-certificate bytes. Tiny LP cases exercise degeneracy,
redundant rows, infeasibility, unboundedness and work/pivot/bit/allocation
exhaustion. Full generation and verification reject simulated mid-run source
or HEAD changes; a failed guarded generation preserves the saved report.
Historical generation commits need not exist in a shallow verifying checkout.

The documentation check passed 111 Markdown files, 445 local links and 12
required entry points. These results establish the two recorded finite-game
witnesses and tested failure paths; they do not establish generic LP coverage
or a general runtime, memory or convergence improvement.
