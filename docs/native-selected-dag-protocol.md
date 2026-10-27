# Native selected DAG protocol: implementation contract

This contract describes an implemented integration with [frozen independent
verification and complete-call evidence](native-selected-dag-result.md). Final
evidence-head CI and merge state remain separate publication gates.
The old native selected-tree protocol and source remain unchanged. The new backend
explicitly requires `public_topology="direct"`, packed zero-delay CFR+ and a
separately source-built helper. It shares one configured four-street game with
the existing Python path; it does not solve independent streets.

## Wire v1

Magic: `OPENPOKER_SELECTED_DAG_V1`. Work model:
`native-selected-dag-work-v1`. Helper name: `native-selected-dag-train[.exe]`;
manifest: `native-selected-dag-manifest.json`; source: `native/selected_dag_train.cpp`.

The next line has integer fields in this exact order:

`V E C CE R S H0 H1 B P T MODE ROOT N Q TC MC AH OH CH DC`

- V/E: retained unique postorder vertex/edge counts.
- C/CE: reachable `(vertex, incoming prefix)` context/edge counts, independently
  reconstructed in native code, not transmitted as an expanded tree.
- R/S: logical own-hand information rows/action slots in logical preorder.
- H0/H1, B, P: private dimensions, selected boards, globally supported prefix count.
- T/MODE: iterations and original 0=left-to-right/1=compensated reduction contract.
- ROOT: DAG root vertex index. Each child index must be lower than its parent.
- N/Q: unfolded logical visits and logical dense decision/hand slots; Q is a work
  charge, not a retained decision/hand map.
- TC/MC/AH/OH/CH/DC: original six logical counters: terminal pair/board candidates,
  marginal pair/board candidates, action/acting-hand entries, action/opponent-hand
  entries, chance children and decision children.

Then the original global normalizer as a binary64 hexadecimal token, followed by
H0 then H1 `hand_mask weight_hex` records. Then B selected board records, each
`flop_mask turn_bit river_bit` followed by H0+H1 integer rank codes on its next
line. These retain the original selected order and rank encoding/blocker sentinel.

Then V unique vertex records:

`KIND PLAYER FIRST COUNT STAGE TERMINAL PAYOFF_HEX`

Kind 0=terminal, 1=decision, 2=chance. FIRST/COUNT form contiguous spans covering
E ordered edges. Decision PLAYER is global 0/1, COUNT is 1..12, STAGE=0,
TERMINAL=-1 and payoff zero. A chance has PLAYER=-1, COUNT=1..64,
STAGE=1/2/3 for flop/turn/river, TERMINAL=-1, payoff zero. Terminals have
PLAYER=-1, COUNT=0, STAGE=0, TERMINAL=0 fold/1 showdown; payoff is the identical
shifted-view scale with fold sign. Absolute payoff <=1e12; showdown nonnegative.

Finally E ordered `CHILD REVEAL` records. Decision REVEAL is zero. Chance REVEAL
is a three-card flop mask or one-card turn/river bit. No rows, full histories,
expanded nodes, private-pair worlds, prefix-pair edges or per-decision dense hand
maps are transmitted. No trailing tokens are accepted.

Output uses the old selected-operator layout with the new magic: `PROTOCOL S terminal_checks marginal_checks normalization_checks`, then S binary64 hexadecimal probabilities in canonical row/action order and `RSS bytes`.

## Independently derived support and contexts

Native code repeats the exact positive-binary64 superaccumulator normalizer
check from the selected-tree backend, with the same rounded raw mass/division
law and positive-normal guard. During physical normalization it records per-board
active own-hand flags. A hand is active only if it occurs in a compatible deal.

Prefixes are deterministic: empty first; then each globally supported selected
board in original selected order contributes length 1, 2 and 3 token prefixes,
inserting only the first occurrence. Both implementations derive this table;
no caller-supplied prefix records are trusted. Active own-hand lists for each
prefix are the ascending-index union of compatible board hand flags. Prefix
hand-to-active-ordinal tables are retained and counted separately from marginal
vectors and strategy rows.

Build reachable contexts from `(ROOT, empty)`; decision children keep the prefix,
chance children append their reveal. Every context independently requires a
distinct, complete next-reveal partition over globally compatible selected deals,
including zero-strategy-reach branches. Wrong stage, duplicates, incomplete or
unsupported reveals reject. All unique vertices must occur in a reachable context.

Each context owns an exact subtree summary: logical visits, rows, slots, dense
holes Q, six counters and maximum remaining depth. Compose ordered child summaries
per occurrence, including repeated child contexts, with checked arithmetic and
incremental logical/work limits. Contexts and edges have explicit bounds even
though they can approach unfolded topology size. No asymptotic reduction of this
auxiliary structure is promised.

Assign rows deterministically in logical preorder. A decision first owns one row
per active acting hand in ascending private index, then its ordered children own
their subtree row/slot spans. Store each context edge's child-context index and
relative row/slot offsets; DFS adds these to occurrence bases. Each occurrence of
a shared vertex therefore gets distinct rows. Inactive own hands use the original
uniform fallback without a row. No cursor-object identity selects a policy.

Native row count/action count/player metadata may be initialized by one bounded
logical DFS; it is O(R), explicitly counted, and must cover every row/slot exactly
once. The Python adapter streams the same occurrence order and authenticates the
complete expected `(player, hand, full history)` key/menu set, rejecting duplicate
or orphan rows. Histories/complete output remain Python-side costs.

## Numerical kernel and admission

Retain original alternating CFR+ update/rematch/own-reach average order, literal
chance/action summation order, per-pair selected-board summation and the existing
versioned reduction arithmetic. Joint chance mass and opponent reach appear once.
Keep one prefix marginal cache and four numeric strategy arrays; rank input is
bounded O(B*(H0+H1)), not private-pair data. Depth arenas remain <=64 with fanout64.

Retain original Python candidate/world/scan/rank-cache/packed limits. New native
limits: N<=250000, Q<=2000000, S<=1000000, H0/H1<=128, B<=64, P<=193,
B*(H0+H1)<=8192, V<=C<=N, E<=CE<=N-1, T=10..10000. Counts are recomputed before
training. Both declared and recomputed envelopes must pass before allocation/use.

Let the old native selected-tree work formula use N/Q/R/S and the same six
counters. New work additionally charges:

`setup_extra = 256*(V+E+C+CE+R+P*(H0+H1)) + 128*P*B*(H0+H1) + 32*C*B`

`sweep_extra = 16*N*(H0+H1) + 8*Q`

Total native modeled work is old_work + setup_extra + T*sweep_extra, <=500million.
Python prefix-support preparation is separately billed twice (admission and wire)
at `2*(P+2)*(H0*H1*B + H0*H1 + B)` against the unchanged 500million scan limit,
in addition to the original Python envelope. This conservatively retains old
training charges even though native computation replaces Python training.

New modeled heap in bytes, with HS=H0+H1 and W=max(H0,H1):

`128MiB+1 +96V+16E+160C+32CE+24R+40S+64P +(2*P+B)*HS*8 +B*(32+8HS)+32HS +(65*66*W*16)`

Cap at256MiB. Input64MiB, accepted output32MiB, stderr8192bytes, timeout180s.
These are modeled logical/storage and accepted-data bounds, not hard allocator,
capture-allocation, CPU-time or process RSS guarantees. Native process lifetime
peak and Python allocation/process peaks are measured separately, never summed.

Build/source/binary identity is checked before and after execution; no automatic
build or silent fallback. Empty-information games authenticate identity but record
zero native training calls. Old literal/helper source and frozen evidence remain
unchanged. Exact physical policy/BR replay, malformed-wire controls, compiled
Python-version controls, sanitizers and paired complete calls are required before
acceptance. No full-deck, unrestricted-NLHE or commercial-scale claim follows.

## Reproduction and fixed study

Build explicitly outside the checkout:

```text
python -m scripts.build_native_selected_dag --output-dir <external-build-directory>
```

On Windows, use a configured MSVC developer environment. Set
`OPENPOKER_NATIVE_SELECTED_DAG_EXE` to the resulting protocol-specific helper.
Run compiled controls using `python -m unittest tests.test_native_selected_dag tests.test_native_selected_dag_compiled tests.test_native_selected_dag_independent tests.test_native_dag_review_controls -v`.
The dedicated CI workflow runs Python 3.11/3.12/3.13 and separate ASan/UBSan controls.

After committing and cleaning the source, run
`python -m scripts.benchmark_native_selected_dag --output <new-external-directory>`.
The fixed schedule is three alternating T100 Python/native pairs, one separate
traced T100 pair and one T1000 pair. Both use `public_topology="direct"`, packed
CFR+, the same 22-world selected game and rank capacity64. Raw outputs/errors,
complete policies, source/build identities, misses and separate Python/native
process peaks are retained. No retry replaces a first failure. Every pair must
preserve complete policy, diagnostics, private-pair probabilities and game census.
Saved sample-zero numeric/exact replay runs at each iteration count; only T1000
has the unchanged 0.001-BB exact acceptance target. T100 misses remain evidence.
The report cannot establish unrestricted solving or commercial convergence.
