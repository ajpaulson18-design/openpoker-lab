# Unified solver audit: validation record

Date: October 24, 2026. Repository: `ajpaulson18-design/openpoker-lab`.
Audited main: `ed0deba4a08fe3c9bb25f75eb41e73e2b3b4b251`.
Runtime: bundled CPython 3.12.14 on Windows. No solver implementation changed.

## Executed baseline

The following command passed **196 tests in 189.438 seconds**, exit 0:

```text
python -B -m unittest tests.test_preflop_solver tests.test_preflop_validation tests.test_preflop_monetary_replay tests.test_preflop_tree tests.test_preflop_convergence tests.test_preflop_public_batched tests.test_preflop_public_diagnostics tests.test_postflop_solver tests.test_turn_solver tests.test_configurable_solver tests.test_postflop_river_compatibility tests.test_cfr_known_quality tests.test_public_cfr tests.test_planned_cfr tests.test_matrix_free_turn tests.test_matrix_free_river tests.test_ranked_river tests.test_solver_validation tests.test_solver_variants -q
```

These cover the existing coupled preflop/postflop game, independent numeric
policy replay, monetary boundaries, blockers, hidden future reveals, configured
betting, known-game quality, traversal compatibility, and specialized later-street
paths. Passing them establishes this bounded baseline, not unrestricted Hold'em
accuracy or completion of the proposed unified interface.

An initial test invocation named nonexistent `tests.test_cfr_quality` instead
of `tests.test_cfr_known_quality`: 67 loader/test entries ran and that one import
failed. The corrected command above is the authoritative completed run. No
repository defect or test was changed to obtain the pass.

## Publication boundary

Live GitHub inspection found four open, unmerged PRs at the audited snapshot:

| PR | Head | Status and relevance |
| --- | --- | --- |
| [229](https://github.com/ajpaulson18-design/openpoker-lab/pull/229) | `3cf52df319dfea300f9fb7c58edc5d8c897a0a82` | Draft; AA/AK count transport and saved authentication. |
| [230](https://github.com/ajpaulson18-design/openpoker-lab/pull/230) | `3371fb609e51c8895f4adfc215dceeebcaaf826e` | Ready; retained matrix-free river quality evidence. |
| [231](https://github.com/ajpaulson18-design/openpoker-lab/pull/231) | `e94e3077f2eb0f8d6eea02812f02af7d5524b6ba` | Draft; AA/AK exact own-hand policy audits. |
| [232](https://github.com/ajpaulson18-design/openpoker-lab/pull/232) | `949060275f00bbd2f174a05a6de247ece1852e73` | Ready; independent ranked river certificate. |

Their contents are candidates for later reuse, not audited-main implementation.
Combined legacy commit-status lookups returned empty status lists; that alone
does not establish check-run success. This phase neither merges these PRs nor
renews their quality/publication claims.

## Limits

The full local unit suite, exhaustive evaluator sweep, native compilation and
historical timing studies were not rerun. No evaluator, backend, betting rule,
resource guard, policy or benchmark artifact was modified. Historical results
remain tied to their original sources and protocols. Documentation validation,
benchmark byte preservation and publication checks are recorded in the final
audit handoff after the review documents are assembled.

## Completed documentation and preservation checks

`python -B -m scripts.validate_docs` passed: 193 Markdown files, 1,070 local
links, 12 required entry points. `git diff --check` passed. A first docs check
found one relative inventory link using the output filename instead of the
repository filename; that link was corrected before the passing check.

All **623 benchmark artifacts** retain their initial raw SHA-256 hashes after
document assembly. Their Git-clean-filter object identities also match the
pinned main commit. Of these, 195 worktree byte streams differ from raw Git blob
bytes because of CRLF checkout conversion; this is recorded explicitly rather
than reported as a benchmark modification. The complete hash inventory is retained.

The architecture received a separate Sol review after adding the sequential
file-owned implementation tickets. Review clarified that completing the frozen
run with a miss or unknown does not satisfy its solver-quality gate. Terra's
implementation/debugging role and Sol's architectural decision role follow the
owner's requested workflow.
