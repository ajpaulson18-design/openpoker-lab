# Exact terminal and normalization operators for four-street validation

The seven-outcome game in the [expansion preflight](four-street-expansion-preflight.md)
was rejected at 113,078 exact work units against the unchanged 100,000 cap. Its
original receipt remains published. This correction reuses the independent
whole-game traversals and complete ledger; the production solver, physical
support, betting rules, ranges and training schedule are unchanged.

## Accepted reuse seam

The literal evaluator now extracts its terminal-group loop and uses a private
trusted operator boundary. Both fixed public functions retain their signatures:
`forecast_exact(case)` and `evaluate_exact(case, payload)`. Each builds a fresh
owned model. Callers cannot provide graphs, callbacks, operators or validator
choices. There is no global replacement, cache or mutable execution mode.

The default v2 path preserves arithmetic/counter order and all receipt fields.
Its new regression authenticates the original publication, report, raw return
and full certificate bytes before comparing the entire new certificate to the
published result: exact metrics, all normalized rows and signed adjustments,
hashes, forecast, realized work, observed widths, limits and preparation receipts.
All 15 certificate controls passed normally (11.940 seconds) and with Python
assertions disabled (12.430 seconds). Separate lead source review found no defect.
Historical reproduction continues to use the immutable original Git revision,
as documented in the [successful result](four-street-integration-result.md).

## Distinct v3 exact operators

A distinct `scripts.four_street_certificate_v3` entrypoint uses the same traversal
and output builder with two bounded exact operators.

At a terminal group, retain the first nonzero-sign reached mass and its sign,
then add equal-sign masses and subtract opposite-sign masses. Convert the signed
binary64 matched payoff once and multiply once. A real cancellation to zero does
not reset initialization. Every group entry remains scanned; fold winners override
showdown signs, and existing finite-money validation precedes tie-only zero returns.
The initially retained mass is checked against the original Fraction-width guard.

For a row with nonnegative raw probabilities p and positive sum s, the absolute
individual adjustment is p_i * abs(1/s - 1). The largest raw probability selects
the largest adjustment. Retain every signed adjustment in the existing ledger,
then apply one absolute value per row. This preserves the original maximum
individual metric.

The analytical census predicts 3,015 nonempty terminal groups with 6,760 entries:
228 tie-only groups, 520 zero-sign entries and 2,787 groups/6,240 entries with
nonzero signs. First-mass accumulation requires 3,453 additions/subtractions,
2,787 conversions and 2,787 multiplications. Normalization arithmetic is 3A+R
instead of the old conservative 4A+R envelope. The resulting proposed 99,119 total
is not executable admission evidence. New census setup, scans, references, frames
and output must have explicit bounded preparation accounting.

## Acceptance before a corrected preflight

Require full saved-policy metric/ledger/hash/max-adjustment parity, literal
per-world leaf controls, mixed/zero/subnormal row controls, public malformed-input
rejections, v2-to-v3-to-v2 receipt equality and all-positive plus pruned-policy
family dominance. Independent 26-world check/call and changed-river controls must
produce -1/20 and +1/20 BB, a 1/10 upstream difference. Keep the 100,000 exact-work,
65,536-bit, depth and preparation caps fixed. All 31 certificate/preflight controls passed normally (59.246 seconds) and with
assertions disabled (58.735 seconds). These include the byte-authenticated original
v2 preflight core, the complete original certificate, same-policy v3 parity,
positive/pruned candidate profiles, coupling anchors and public input guards.
Lead static review accepted the operators after fixing receipt aliasing and
removing a duplicate census classification pass. The census additionally reserves
32 fixed setup and 64 fixed output entries under its four named preparation
families, then guards the aggregate of census and two/three owned graph walks.

## Corrected no-training preflight

`scripts.four_street_expansion_preflight_v3` selects the v3 validator through a
private trusted seam in the existing preflight. The original public entrypoints
remain fixed to v2 and reproduce the entire original prepare receipt. The new
receipt uses a distinct schema, fixes source/schedule/validator identities, and
retains full support and false forecasts before any rejection. Public callers
can provide only the expected clean source commit and a fresh output directory.

The before/after inventory authenticates every committed Python source used by
the executable. Preparation disclosure separates production preparation, the
explicit independent support build, the forecaster's fresh independent build,
its own graph/census receipts and source captures. The forecaster's preparation
ceiling does not bound the whole preflight. No training occurs and quality
remains unknown. The actual frozen corrected receipt remains pending.

```powershell
python -B -m scripts.four_street_expansion_preflight_v3 --expected-source-commit <clean-40-character-commit> --output-directory <new-directory-outside-repository>
```

Keep the original rejected receipt and successful v1 corpus byte-identical.
The expanded-game quality runner and saved-only verifier require distinct fixed
experiment identities and full lifecycle/source-authentication checks before
a new frozen complete-game solve.
