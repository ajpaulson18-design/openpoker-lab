# Delayed averaging for flop-start CFR+

`solve_postflop(..., algorithm="cfrplus", averaging_delay=d)` accepts a positive
exact integer `d < iterations` for flop starts. Both recursive and public-batched
training keep every requested regret sweep; only the completed-sweep average
weight becomes `max(t-d, 0)`. The default `d=0` retains the established dispatch
and payload. Positive delay is rejected for other algorithms, turn/river starts,
and planned traversal before physical-world enumeration. Flop public diagnostics
and target stopping remain unsupported.

The recursive path reuses the existing CFR+ delay argument. The public path
reuses the isolated [delayed public trainer](../pokerlab/preflop_delayed_cfrplus.py),
which traverses both public-card prefixes and accumulates own-hand mass times
own reach times action probability. Shared trainer kernels and defaults are
unchanged. The result identifies `averaging_delay`, `averaging_positive_sweeps`,
and `delayed-linear-post-sweep-own-reach`; the public path also identifies its
isolated kernel. All old resource admissions remain, including three full
training passes per requested sweep: delay cannot reduce its reservation.

[The integration tests](../tests/test_flop_delayed_cfrplus.py) independently
replay weighted raised selected runouts and both full-deck training backends.
Both full-deck replays pass in the 27-test focused suite. A separate
[hand-computed averaging control](../tests/test_flop_delayed_averaging_control.py)
checks completed profiles and own-reach weighting across two chance reveals.
A [frozen original adapter](../benchmarks/sources/postflop-before-delayed-flop-cfrplus-v1.py.gz)
from commit `06616039f4fea3904614132f31c91c406ca90c1a`, LF SHA256
`e0af827215f4731ac249345f067d8d18d9721ddcf43f563c15991eefa9c37b6f`,
authenticates full omitted/explicit-zero payload comparisons in the
[default compatibility tests](../tests/test_flop_cfrplus.py). This compressed
source belongs to this project and is used only as a regression reference.

## Conditional rows at zero reach

The raised selected-runout control intentionally retains a raw conditional
probability difference of at least 0.5 between trainers. One backend has exactly
zero average own reach and returns a uniform fallback; the other retains a tiny
floating-point residue and normalizes it. This is not full conditional-policy
agreement. Tests compare every information/action key, every action's own-reach
realization weight, and independently reconstructed value and legal-response
metrics. No row is excluded by a reach threshold and no production rounding is
changed to force parity. Future experiments must preserve these raw differences
as well as realization and scalar comparisons.

This is an opt-in averaging capability, not a convergence improvement claim.
It does not establish the unchanged 0.005-chip target on the weighted full-future
flop fixture. Any quality comparison needs a separately frozen delay protocol,
source identities, full profiles, independent physical/action/response replay,
complete-call observations and preserved misses. The configured finite game
remains distinct from unrestricted no-limit Hold'em.

The averaging schedule follows concepts in
[Tammelin's CFR+ paper](https://arxiv.org/abs/1407.5042); this project uses its
existing completed-sweep own-reach convention and incorporates no external code.
Historical turn artifacts retain their generation hashes; only the adapter's
reviewed current endpoint changes in the
[exact source transition registry](../scripts/historical_turn_sources.py).
