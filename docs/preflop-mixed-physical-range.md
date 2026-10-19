# Mixed full physical preflop ranges

This [frozen benchmark](../benchmarks/preflop-mixed-physical-range-v1.json)
uses `AA:1,QQ:0.5` against `KK`: 12 SB hands, six BB hands and 72 compatible
pairs representing 123,285,888 final boards. The existing covered-table API
pools two ordinary three-pair sources. Independent exhaustive
[AA/KK](preflop-five-card-reference.md) and
[QQ/KK](preflop-generic-five-reference.md) reports authenticate all six source
classes before use. One suit bijection must map both ordered hands together.
There is no new ranking or enumeration during strategy training.

All physical hands stay distinct. Each AA/KK pair has exact prior `1/54` and
each QQ/KK pair `1/108`, yielding SB rank masses `2/3` and `1/3` after global
normalization. The game preserves blinds 0.5/1, stacks 3/3, configured raise
sizes 0.5/1, two raises, limps, the BB option and all-ins. Every nonfolded
closed line forces hidden full-board checkdown. Later-street betting and
unrestricted starting ranges remain outside this finite experiment.

## Independent guarantees and quality gates

The [reference](../scripts/preflop_mixed_range_reference.py) authenticates both
published count reports and reconstructs every mapped physical count. It
checks all 72 rows, both rank classes and the `6/24/6` suit-overlap census for
each rank. The original independent numeric rules establish legal strategies:

- SB jams each own AA hand, guaranteeing at least +1 against any BB response,
  and folds each own QQ hand, losing 0.5. Its weighted guarantee is +0.5.
- BB checks every limp and folds to every opening raise. SB then earns -0.5
  by folding, at most +1 by checking down, or +1 by raising.

Thus the equilibrium SB value lies in `[1/2,1]`. These bounds do not identify
the exact value. The independent replay sums hidden-opponent payoffs before
maximizing or minimizing at each own-hand information set. Its rational
policy BR interval must intersect the constructive interval; it need not
contain that entire interval. A profile value need not itself lie in the
constructive equilibrium interval.

The [runner](../scripts/benchmark_preflop_mixed_range.py) freezes CFR+
checkpoints 10, 100 and 400, final three alternating paired repeats, independent
metric tolerance `1e-10`, backend metric/probability gates `1e-8`/`1e-6`, and
mandatory final NashConv at most 0.005 chips for both Python/native. Every raw
policy, assessment, early miss and failed observation is retained. Every
requested profile is admitted before native build lookup. Maximum Python/native
modeled complete work is 484,175,040 / 185,208,304, below the unchanged
500-million cap. The final iteration count was selected using admission only,
before training measurements; no gate or cap is relaxed.

Complete-call timings include JSON serialization and hashing. Input validation
and independent replay are outside timing. Three final samples must serialize
deterministically within each backend; earlier single samples have no median.
No memory, general performance or exact equilibrium claim follows.

## Validation status

Nine focused [boundary/reference checks](../tests/test_preflop_mixed_range_reference.py)
pass locally, including actual native/Python ten-iteration replay/parity,
physical priors, source tampering, constructive bounds and dirty-source guards.
Formal frozen measurements and GitHub publication have not yet run at this
source revision; this section will be updated from retained evidence.
