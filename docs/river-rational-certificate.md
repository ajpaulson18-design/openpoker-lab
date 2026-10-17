# Exact normalized certificates for saved river policies

A later [exact equilibrium witness](river-sequence-equilibrium.md) establishes
the weighted raised game value. The saved-policy certificates below retain
their original profiles, nonzero gaps and historical audit context.

## Purpose and fixed games

This audit applies the existing bounded exact arithmetic helper to the saved
[river accuracy extension](river-accuracy-extension.md) and
[long-budget polarised game](river-long-budget.md). It adds exact normalized
policy EV and legal response bounds for the weighted raised fixture, whose
earlier general replay used floating-point arithmetic. It also checks the
polarised policies against the separate explicit-history rational oracle.

The input set contains fifteen archival records: two river fixtures, both
materialized and matrix-free CFR+ backends at 1k/3k/10k, plus matrix-free
polarised policies at 10k/30k/100k. Both archived polarised matrix-free 10k
records remain distinct. Their raw JSON bytes and SHA256 values differ, while
their decoded complete solver results match exactly. Both facts are checked
from the hash-verified files.

The polarised game is board `2c7d9hJsKd`, OOP `AsAh,3c4c`, IP `QsQh`, pot and
stack 100, one pot-sized wager and no extra all-in option. The weighted raised
game is board `Js8d4c2h2s`, OOP `AsAh:0.5,KsKh:1`, IP `AcAd:1,KcKd:0.75`,
pot 100, stacks 220/120, opening fractions 0.33/0.75, raise fractions 0.5/1,
at most two raises, with all-in actions. These remain finite fixed-board
heads-up games with small supplied ranges and configured action sizes.

## Meaning of the exact bounds

The unchanged independent validator must first reconstruct the physical
private-hand deal law and legal tree, validate complete visible-information
strategy rows and metadata, replay all eight metrics and compare them with
the serialized solver values. The exact helper then converts each binary64
probability to its exact Fraction and divides by the exact row sum. The
certificate concerns this explicitly normalized policy. Every row correction
and the canonical normalized-policy hash remain part of the evidence.

World masses use exact input-weight products with a global compatible-pair
normalizer. Terminal constants are exact rational images of the independent
numeric oracle's configured binary64 constants. The audit shares that oracle's
rules, physical worlds and ranks; it checks their arithmetic exactly rather
than supplying a second independent general rules implementation or proving
equivalence to arbitrary decimal sizing intent.

A best response chooses one action per own hand and visible history, after
integrating unknown opponent hands and their policy. It can deviate at
previously unreachable rows. It cannot choose actions using the opponent's
hidden hand. If `V` is the exact OOP profile value, `U` its legal response
against fixed IP, and `L` OOP's value against IP's legal response, the exact
identities are:

```text
L = -BR_ip <= V <= U = BR_oop
gain_oop = U - V; gain_ip = V - L
NashConv = U - L = gain_oop + gain_ip
exploitability = NashConv / 2
```

There is no floating-point negative-gain clipping in these identities. The
finite zero-sum game value lies in the legal response interval. For the
polarised fixture, the independently known value 25 must also be inside it,
and all eight Fraction metrics must exactly equal the separate five-history,
16/4 pure-response rational oracle. No known equilibrium value is asserted
for the weighted raised game. See the [general derivation](turn-rational-certificate.md).

## Provenance, caps and independent review

Canonical parent-report hashes and all fifteen raw policy hashes are pinned
before model reconstruction. The fixture and profile identities come from
reviewed constants, rather than inferred payload fields. Historical source
matching is limited to relevant independent model dependencies, permitting
only checkout path/line-ending representation differences. Strict current-run
source and input hashes must match before and after the audit.

The oldest extension report predates later validator hardening. Its existing
[hardened replay record](../benchmarks/results/river-cfrplus-accuracy-hardened-replay-v1.json)
provides the explicit bridge: a pinned canonical record links the original
extension report and all twelve policy identities to the current whole
validator file. Other independent model dependencies retain their historical
whole-file checks. The old report and its original fingerprints are preserved.

Generation commit and source fingerprints describe the original run. Later
verification preserves that provenance and reconstructs the certificate with
fresh current-run before/after hashes; it does not require the current checkout
to have the generation commit or unrelated production files' historical bytes.
The relevant fixed-model historical gates and all pinned policy identities
remain mandatory. This permits normal checkout line endings and later
unrelated development without relaxing mathematical reconstruction.

The unchanged exact helper enforces 100,000 modeled work units, depth 64 and
65,536 bits per accepted Fraction numerator or denominator. River trees have
no future chance nodes and use the helper's original scan mode. These bounds
do not measure CPU instructions, allocator work, temporary Fraction-library
storage, elapsed time or RSS. Exhaustion rejects the audit.

Saved report rows must be reconstructed from the pinned policies after reload;
internally consistent but altered fraction identities are insufficient. The
report retains every exact `1/1000` NashConv threshold meet and miss, floating
cross-check difference, ledger, hash, model dimension and work counter. These
are normalized saved-policy certificates, not raw-binary64 interval proofs,
new equilibrium solves, convergence guarantees or changes to production APIs.

Sol's separate raised-game witness uses equal nuts/air against a bluff-catcher,
pot 100, stacks 200, opening wager 100 and a legal raise to 200. Nine explicit
terminal histories and exhaustive 144 OOP/12 IP pure legal responses establish
profile value 0, OOP best response 50 and IP best response 0. An illegal IP
response that sees OOP's hidden hand reaches 100. The independent numeric
replay and exact helper must reproduce the legal values. This checks raising,
matched-wager refunds and information boundaries without asserting equilibrium.

## Executed evidence

The [saved certificate](../benchmarks/results/river-rational-certificate-v1.json)
was generated at `a0db4ce1ba6823acd96164288209ae64bac58245` and reloaded for
fresh reconstruction of all fifteen rows. Its 486,372 bytes have SHA256
`5acb6b4a0f1fa9a05af36feb2c010ac0b005be0bf29629571d99738b7ba34a34`.
It retains 83 source/input fingerprints and 270 normalization ledger rows.
The largest probability adjustment is approximately 1.12e-16; the largest
exact-normalized versus independent floating replay metric difference is
1.995e-14 chips.

Rounded exact NashConv values are below. Both backends' full Fraction values
and differences remain in the report; the rounded columns do not imply bit
identity between backends.

| Fixture / archive | 1k | 3k | 10k | 30k | 100k |
| --- | ---: | ---: | ---: | ---: | ---: |
| Polarised, extension (both backends) | 0.0705657041 | 0.0182906265 | 0.00790056594 | — | — |
| Weighted raises, extension (both backends) | 0.00404474440 | 0.000848854325 | 0.000279553443 | — | — |
| Polarised, long budget (matrix-free) | — | — | 0.00790056594 | 0.00265815977 | 0.000907974712 |

Exactly five records meet `NashConv <= 1/1000`: weighted raises at 3k and
10k on both backends, plus polarised matrix-free at 100k. All ten misses
remain explicit. The intersection of the independently verified exact
response intervals has floating views `[24.999640477379614, 25.00054845209176]`
for the polarised game and `[-20.03656240193997, -20.03628284849715]` for
weighted raises. These decimals are rounded views of the saved rational
bounds, not outward-rounded binary64 certificates. The weighted game's
equilibrium value remains unknown within those exact response bounds.

The polarised model has two worlds, six information sets, four public
decisions and nine total nodes at depth four. Weighted raises has four
worlds, 36 information sets, 18 public decisions and 51 total nodes at depth
six. Exact work is respectively 322 and 3,050 units. The largest Fraction
numerator/denominator sizes across rows range from 243 to 1,627 bits. All
unchanged work/depth/bit caps hold.

Sol separately computed all eight exact metrics for all fifteen policies
before seeing the final report, using a different Fraction recursion without
importing the new auditor or bounded exact helper. A subsequent separate
artifact review reconstructed all normalization rows/hashes, checked the
hand-derived world masses and showdown signs, recomputed legal responses,
compared those earlier vectors and checked all 83 current fingerprints.
The raised nine-history/144/12 witness also passed. This review shares the
independent validator's configured tree/rank model, as described above.

All 13 focused audit/review tests passed normally and with `python -O`;
53 broader exact-helper, chance-partition and independent-replay tests also
passed. Negative cases include internally consistent false saved metrics,
raw hash/model/action/row corruption, missing/duplicate profiles, bridge
tampering, resource exhaustion and source/HEAD changes during an actual audit.
An initial Windows temporary-directory ACL failure was resolved with a unique
project-local directory before the passing focused runs; it did not require
production changes.

```text
python -m scripts.audit_river_rational_certificate
python -m scripts.audit_river_rational_certificate --verify
python -m unittest tests.test_audit_river_rational_certificate tests.test_river_rational_review -v
python -O -m unittest tests.test_audit_river_rational_certificate tests.test_river_rational_review -v
python -m scripts.validate_docs
```

The first command regenerates the report; `--verify` instead replays the saved
artifact while preserving its original generation context. It remains usable
after a commit or in a shallow checkout with ordinary LF/CRLF differences.
