# Staged-page training walk observations

The accepted staged-page layout changes the training baseline enough to require
fresh measurements. This study reuses the bounded owned-child observer from
[its historical branch](https://github.com/ajpaulson18-design/openpoker-lab/pull/323)
on the exact ten-card two-sweep staged-page trainer. It records periodic
wall-time observations of the owned primary thread, including I/O waits.
It supplies no CPU percentages or exclusive owner costs.

## Source, symbols and process boundary

The trainer source is `7c10ea680e2075e8592cb978f2a0fa09c0c6b867`; its unchanged
native closure was built for the staged-page target at `299b4ec`.
The observer and verifier source is `c3fe3535ce25e68db1ad946cc87305be460fb509`.
The observer launches only its own child, retains ownership through a Windows
job, and limits snapshots, pauses, image reads, frames and report size.
It preserves partial unwinds and natural exit-race events.

A map-only relink of the retained object yields 1,052 public function ranges
with verified unwind extents. The original and relinked images differ only in
their structurally located COFF and debug-directory timestamp fields.
Every other byte matches after that normalization. The map, command, compiler,
linker and object inspection identities are retained. The original build
manifest did not attest the object file bytes. This proves public address
correspondence; it supplies no source-line or inline-function attribution.
Folded aliases and native addresses outside proven extents remain visible.

## Complete-call controls

The protocol fixes eight alternating pairs for each comparison, with a median
paired ratio at most 1.01. It requires eight enabled calls and at least 50
valid observations from each. All 32 calls reproduced the complete numerical
stream, both checkpoint frames and State images, policy spill, full-history
row directory and arithmetic receipts. Source and executable checks agree
before and after the study.

| Comparison | Median paired ratio | Preset gate |
| --- | ---: | --- |
| Disabled observer over direct trainer | 1.00528 | Passed |
| Enabled over disabled observer | 0.99463 | Passed |

These are operational overhead controls for one Windows host. Host load was
uncontrolled, and the lower enabled ratio is not a causal speed improvement.
The prior observer study's 1.04891 wrapper miss remains preserved separately.

## Saved observations

Eight captures retain 811 valid observations, with 504 containing a tracked
walk frame. Terminal evaluation was the largest or tied-largest tracked walk
context in every capture.

| Nested walk context | Observations |
| --- | ---: |
| Walk | 504 |
| Terminal evaluation | 177 |
| State row staging | 119 |
| Prepared Chance contraction wrapper | 83 |
| Prepared Chance contract kernel | 82 |
| Direct packed State staging | 50 |
| Pager staging | 31 |
| Independently resolved dirty-page flush frame | 0 |

Nested contexts overlap and cannot be added as time shares. A caller can
include inlined work and system calls. Zero resolved flush frames does not
establish zero flush work. These observations use a different measurement
method from the earlier ETW packet and do not form a comparable CPU percentage
series.

The initial controller recognized the old non-template Chance contract
spelling and reported zero contract contexts. Saved-only replay also recognizes
the current template spelling and counts 82. The original summaries remain
unchanged. Eight mutation-control methods cover both spellings, aliases,
unproven address gaps, exclusive range ends, pre-adjusted return boundaries,
external seeds, resource limits, types and duplicate JSON keys.
[Saved-only replayer](../scripts/replay_native_walk_contexts.py)

## Architectural consequence

The [eleven-card decomposition](native-dyadic-storage-census.md#parent-work-inside-the-eleven-card-forecast)
still projects 5,954,402,351 combined units against 2,150,000,000.
State, terminal computation, transport and parent metadata remain substantial.
The recent terminal, policy-cache and average-coefficient timing misses give
no basis for accepting another narrowly chosen shortcut from these context
counts alone.

The next integration audit concerns traversal and State schedules that avoid
work on unvisited public branches. Existing frozen-update proposal proofs must
first accept the fixed-grid policy representation used by the accepted trainer.
Expected raw signed regret, value and own-reach average contributions must match
an independent q-free whole-game reference. Per-draw CFR+ clipping is nonlinear
and is a separate learning/convergence question. Zero-target final boards can
still have positive earlier-prefix average contributions, so final-board
support alone does not authorize pruning visible histories.

The [evidence packet](../benchmarks/results/native-dyadic-staged-walk-v1/manifest.json)
retains the executed operators, raw process/report evidence, normalized
observations, image/map binding, source identities, all timing observations
and the classification correction. No new training capacity or policy quality
claim follows.
