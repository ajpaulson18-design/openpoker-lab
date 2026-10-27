# Compact exact-product policy output and bounded verification

Status: independently checked implementation; frozen cost/structural study and
final CI/publication remain separate acceptance gates. The existing expanded
output remains the default. This extends the explicit exact-product solver; it
does not change the legacy rounded or native protocols.

## Production output contract

`solve_four_street_exact_selected(request, pair_diagnostics="compact")` retains
the same complete own-hand/visible-history strategy and diagnostics while omitting
`private_pair_probabilities` and `compatible_private_pairs`. It returns
`pair_diagnostics="compact-exact-product-inputs-v1"` and a
`chance_input_snapshot` containing the exact parsed hand identities and canonical
binary64 weight-hex tokens for both ranges. Selected/reachable boards and the
physical world count retain their existing meanings. `candidate_private_pairs`
is only a product of input dimensions; `pair_runout_preflight_checks=0` records
zero pair-query work. No private-pair count is invented from repeated board mass.

The production compact path never calls `pair_probability_exact` or enumerates
private pairs. Its prefix support, exact mass/payoff sweeps, trainer and diagnostics
remain unchanged. Whole-request admission assigns zero pair-output work/storage
and separately charges O(H0+H1) input snapshot work/storage. The new snapshot
construction reserve is four times its 6H+32 retained-entry bound; expanded mode
keeps this additional charge at zero. Complete strategy,
history and numeric buffers remain explicit and can dominate. The result does
not establish linear full-game storage or remove public/action branching.

Expanded and compact modes have identical policies/metrics when both requests
are admitted. Expanded mode retains its strict positive pair-probability output
conversion and output caps. Compact mode has no individual pair-float output;
it can admit additional cases whose marginals/terminal vectors remain representable.
Every nonzero completed query component still rejects zero/subnormal/nonfinite
conversion. This is an explicit output/admission distinction, not silent repair
of the expanded contract or a guarantee against all binary64 training underflow.

## Independent certificate boundary

`scripts.exact_selected_compact_certificate.evaluate_exact(case, payload)` first
applies the unchanged exact payload row/JSON guards and validates the compact
hand/weight snapshot and selected boards against independently parsed case inputs.
It reconstructs pair metadata from the unchanged capped physical model solely
inside verification, then calls the unchanged v3 exact certificate. All oracle
hand/world/state/row/work/bit limits remain; this is not a scalable or pair-free
verifier. Three bounded physical model constructions occur: wrapper setup,
exact evaluator setup and its independent floating crosscheck. Their repeated
preparation is explicitly disclosed.

The certificate wrapper records both the raw compact payload canonical hash and
the reconstructed verification-payload canonical hash. Normalized-policy identity
and exact metrics are supplied by the original certificate. The verification
expansion is not returned as production solver output. Malformed snapshots,
duplicate holdings, wrong weights/boards, hidden future reveals, invalid actions
and oversized policies reject. Inputs to the verifier are trusted to identify
the requested finite game; the policy must independently satisfy that game's
complete numeric/rational checks and quality target.

## Executed controls and limits

Four focused controls and eight independent controls verify:

- Full compact/expanded policy, profile, both BRs, gains and pair-input consistency
  on weighted selected games, with production pair queries patched forbidden.
- Expanded default policies, pair probabilities and all metrics match the frozen
  [exact-product study](exact-selected-kernel-result.md) read as data only.
- Independent exact weighted/tiny-input certificate agreement and compact-to-
  verification hash binding, with all old oracle limits preserved.
- Oversized or forged compact metadata rejects before physical model construction.
- A full-range one-selected-board forced blind all-in has empty strategy and zero
  training calls, represents 1,070,190 deals, snapshots 1,326 hands/seat and uses only
  per-hand ranks. Identical priors imply zero mean payoff by seat-swap symmetry;
  numeric profile/NashConv agree within 1e-12. The old small-game verifier rejects
  these ranges before building its physical model, as required.

That last control has no decisions and is not full-range four-street training,
a larger exact certificate or a full-deck solve. Source-frozen complete calls,
retained misses and independent saved replays are still required before measured
performance or publication claims. Strategy/history growth and native exact
computation remain separate foundational barriers.
