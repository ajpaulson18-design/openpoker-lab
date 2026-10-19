# Global suit equivariance of blocker turn policies

This development audit checks one selected-river configured turn game under all
24 global suit bijections. Its independently proved value is 115/7 chips. The
board, both weighted private ranges, selected rivers and visible policy histories
move together; collision conditioning, action amounts and probabilities stay fixed.
The model has six worlds, three compatible private pairs, 63 public nodes and
56 own-hand policy rows. See the [source proof](turn-blocker-sequence-equilibrium.md).

## Fixed experiment

Before new training, independent physical-world, best-five showdown and public
tree reconstruction established the same game for all 24 maps. Every transported
rational witness retains value and both response bounds 115/7, exact NashConv 0
and river-decision reach 1. A one-sided private-hand map deliberately creates an
extra compatible AA pair: eight worlds and four pairs, with new pair mass 1/8.
A stale future-card history marker must fail policy identity validation.

All six [archived CFR+ policies](turn-blocker-cfrplus.md) are transported through
24 maps and independently replayed with exact row normalization and own-hand
responses: 144 archived-data checks. These checks do not run new training.

Eight new complete calls are fixed in target order dcsh, hscd, shdc, cdhs,
with materialized then matrix-free CFR+ at 1,000 iterations for each target.
The source suit order is cdhs; cdhs is the identity control. Every exact metric
must differ from the same-backend archived 1,000-iteration policy by at most
1/1,000,000,000 chip, and its exact response interval must include 115/7.
The quality target remains 1/1,000-chip NashConv. Every miss is retained.
Per-action differences compare normalized probabilities, without requiring
identical off-path mixtures.

## Reproduction and limits

Run python -m scripts.turn_suit_validation to execute the fixed experiment,
and python -m scripts.verify_turn_suit_equivariance to accept saved results.
The independent verifier imports neither the candidate transport helper nor
trainers, LP code or the exact-policy evaluator. It reconstructs all 24 exact
policies, all 144 archived transports and all eight complete fresh policies.
Source/input hashes and Git HEAD are guarded before and after execution.
Publication checks staged data before atomic replacement and restores owned
files on failure. Complete policies are immutable. Report/policy byte limits
are 2,000,000/1,000,000; existing solver and exact-work limits are unchanged.

Exact response bounds apply to row-normalized saved binary64 probabilities and
configured binary64 terminal constants. This fixed selected-river game does not
establish unrestricted Hold'em equilibrium or commercial-solver equivalence.
Complete-call and replay timings are individual observations on one host;
no general speed, memory or RSS claim follows.

## Verified saved results

The saved `turn-suit-equivariance-v1.json` report is pinned to baseline
`9391445d4ae8e8f186d73ee1edfd449e06020d26`. Independent acceptance established
24 exact-map certificates and 144 archived-policy transports. All eight fresh
1,000-iteration calls (materialized and matrix-free at each of dcsh, hscd, shdc
and cdhs) met the 1e-9 exact-metric symmetry bound against their archived
same-backend source. Their maximum action-probability difference was zero.

All eight calls retain their quality-target misses. Materialized NashConv was
0.0035295963922469683 for each map, and matrix-free NashConv was
0.0035295963922472758 for each map; neither meets the unchanged 0.001 target.
The misses are recorded as results, not treated as a reason to change the
threshold or discard a target. The configured equilibrium reference remains
115/7 chips.

Focused regression validation ran all four suit modules
(`test_turn_suit_reference`, `test_turn_suit_transport`,
`test_turn_suit_validation` and `test_verify_turn_suit_equivariance`) with the
bundled Python runtime. Normal mode passed 32 tests in 42.898 seconds; optimized
mode (`-O`) passed 32 tests in 56.779 seconds. Both runs required execution
outside the sandbox because temporary-file tests otherwise hit Windows
`PermissionError`/`WinError 5` ACL failures. The failures were environmental;
no test or source changes were needed.
