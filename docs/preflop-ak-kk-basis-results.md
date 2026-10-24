# Independently counted AK/KK source classes

The single [seven-stage observation](../benchmarks/results/preflop-ak-kk-basis-v1/report.json)
passed with exact agreement between the project-owned native seven-card counter
and the separately implemented best-five reference. Each of these three new
ordered private pairs covers all 1,712,304 possible unordered five-card boards:

| SB hand | BB hand | SB wins | Ties | SB losses |
| --- | --- | ---: | ---: | ---: |
| AcKc | KdKh | 576,944 | 14,122 | 1,121,238 |
| AdKc | KdKh | 509,318 | 15,019 | 1,187,967 |
| AdKc | KhKs | 506,801 | 13,510 | 1,191,993 |

The two offsuit rows remain distinct because the opponent's relative suits
change the physical available deck. These are physical source counts for
three named suit orbits. Count agreement does not establish a transported
84-pair table, a strategy, convergence or unrestricted Hold'em solving.

## Frozen observation and work

The [original protocol](../benchmarks/preflop-ak-kk-basis-v1.json) and its
[planning document](preflop-ak-kk-basis.md) remain unchanged historical inputs.
The full protocol's canonical SHA-256 is
`73f99d04785a203b6ea3c5498889d96e7cc105f65608556ca98d4ef91eefbec8`.
The observation ran once at clean committed source
`4aac2c22fa7066fa2d0a896cbd8b0c77800ccd1b`. All 783 original source identities,
both compiler/build identities and executables were identical before and after.
No retry or reduced-work fallback occurred, every numerical call returned zero,
and all seven stderr streams are empty.

The complete stage order was reference all-five, reference AA calibration,
native AA calibration, reference AK suited, native AK suited, reference AK
offsuit, native AK offsuit. The current reference build's 2,598,960 five-card
tuples matched the independent Python evaluator, with zero mismatches. Both
counters' AA calibration agreed with the independently authenticated published
AA basis before either new AK query. Including calibration, each method visited
10,273,824 boards and 20,547,648 seven-card hands; the reference visited
431,500,608 five-card subsets. Existing per-request caps are unchanged.

The external process receipt records CPython 3.12.14 on Windows, from
2026-10-23T20:21:48.981150Z to 20:23:21.073059Z, taking 92.0913182 seconds.
This is one uncontrolled complete observation, including conformance and saved
reports; it establishes no speedup, memory allocation or process RSS bound.
Both unchanged project-owned C sources were built once in fresh external
directories with the installed MSVC 19.44.35229 compiler. Compiler flags,
manifest hashes, executable hashes and source identities are retained in the
reports. No third-party source, dependency or compiler installation was added.

## Original archive and independent saved authentication

The [index](../benchmarks/results/preflop-ak-kk-basis-v1/index.json) maps the two
original reports and thirteen small raw streams. With the index there are
sixteen byte-preserved files totaling 1,194,581 bytes. Reports and streams were
copied from the original observation without reformatting or new counting.

| File | Bytes | Raw SHA-256 | Canonical artifact SHA-256 |
| --- | ---: | --- | --- |
| report.json | 807,681 | 89f2720092e659ccd982665cf4fdaa1d33448e30bb25a9321f9111410942e7a7 | 4f64aea64d85a77153187dfb0b8c537b173674cc542d38200133c5e01aaed982 |
| aa-conformance-report.json | 379,343 | 4287737d17713847ee9d58b3dbeb83c1da40adaf06456859d04e3b88c7e9497c | 3f490292c996068004f5918da4afa2bd7d7b1dd8f0dc1fdc1ef612e486185e8a |
| index.json | 6,080 | fb08e891b9879d1fb17671a6c71c6019cd0bbb1fdc21fc120737773a9c47ffad | 2424f97058a3be821e5e53a9aaaabcf6e832fc1fee23af5e4c97173bac043ea0 |

The complete binary all-five stdout remains outside Git: 15,593,760 bytes,
SHA-256 `7dfd1ff4ed2761fef77db70b170fdae750cf7c162932087e30163037e4e78e52`.
Its original comparison result, shape/category census and captured digest are
retained. Saved publication authentication does not repeat that binary
comparison or any physical board count and cannot establish its presence on a
different machine from the committed JSON alone.

The four original noncalculation context files are archived under
`benchmarks/sources/preflop-ak-kk-context-freeze-v1/`; their historical LF hashes
must match the report, while current context is separately recorded. All other
calculation sources remain strict. Any later publication-only source transition
must have explicit original/current pins and original archived bytes.

The [saved-publication verifier](../scripts/verify_preflop_ak_kk_basis_publication.py)
checks raw index and all mapped files before parsing them, authenticates the
original complete protocol, published AA prerequisite and separately saved
current-build conformance report, and links every seven-stage receipt to the
captured streams, source/build identities and exact typed count rows. It
attests a clean current checkout before and after all validation. Historical
source changes are limited to the four archived context files and the three
exact [publication-only transitions](preflop-publication-source-history.md);
new current-main/publication files are separately recorded as unmeasured.

The combined planner, runner, saved-publication, source-history, transport and
exact-witness suite passed 52 tests under bundled CPython 3.12.14. The fourteen
AK publication tests include actual saved corpus authentication with numerical
entry points forbidden, altered raw files, malformed metadata, conformance
failure and source drift. Actual clean CLI authentication and final-head CI are
verified separately before merge. The original observation's metadata and
failure semantics are preserved.

```text
python -B -m scripts.verify_preflop_ak_kk_basis_publication
```

## Next bounded use and model limits

A rank-free AA/AK-versus-KK table would have 22 SB hands, six BB hands and 84
compatible pairs after removing 48 blocked candidates. Under unit hand weights,
the three hand-type masses would be AA 3/7, AK suited 1/7 and AK offsuit 3/7.
That forecast is already admitted by the unchanged 128-pair prepared-table cap;
an independent joint-suit transport proof remains necessary before using it.
Combining AA/QQ/JJ and AK against KK requires 156 pairs and remains rejected.

Any subsequent policy claim requires a separately admitted finite betting game
and independent legal own-hand responses that sum hidden opponent hands before
maximizing. These count results add no flop, turn or river betting solution.
Shared solver kernels, production defaults, AI Coach and explanations remain
separate. The implementation and validation methods are original project code;
published method references are retained in the prior
[source-count evidence](preflop-jj-kk-basis-results.md).
