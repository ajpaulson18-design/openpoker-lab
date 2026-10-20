# Correct value alone does not certify equilibrium

A deterministic negative control derived from either saved [exact witness](full-deck-raised-turn-clean-witness.md) has the same exact OOP value, -400/21, but exact NashConv 325/33. This fixed 176-world raised turn/river game therefore provides a concrete regression against accepting a strategy solely because its profile payoff matches the known game value.

The control chooses the action with highest saved probability in each of all 2,404 rows, breaking ties by original legal-action order. It preserves every row, history, public board and action amount. Both source files remain unchanged. This deliberately large policy transformation is separate from the preceding tiny cleanup that produced the exact witnesses. The control is research evidence and does not change production strategy selection.

## Exact metrics

| Metric | Deterministic control |
| --- | ---: |
| OOP value | -400/21 |
| IP value | 400/21 |
| OOP best-response value | -200/21 |
| IP best-response value | 4475/231 |
| OOP response gain | 200/21 |
| IP response gain | 25/77 |
| NashConv | 325/33 |
| Exploitability | 325/66 |

The independent full-physical exact oracle recomputes all eight metrics after derivation. It keeps all 48 public river cards and original joint masses. Inherited equilibrium metrics and training/averaging claims are not attached to the derived strategy.

## A constructive legal deviation

Change only OOP's KhKs root row, with empty public history, from check to bet@50. Every other strategy row stays fixed. This uses only the player's own hand and starting public information.

An independent deterministic walk through all 176 worlds yields the following OOP terminal utility for each private pair. Every one of the 44 legal river cards for each pair gives the listed utility.

| OOP / IP | Original joint pair mass | Pure control payoff | Payoff after KhKs root bet |
| --- | ---: | ---: | ---: |
| AhAs / AcAd | 4/21 | 0 | 0 |
| AhAs / KcKd | 1/7 | 100 | 100 |
| KhKs / AcAd | 8/21 | -50 | -100 |
| KhKs / KcKd | 2/7 | -50 | 50 |

The control's weighted payoff is 100/7 - 400/21 - 100/7 = -400/21. The one-row deviation gives 100/7 - 800/21 + 100/7 = -200/21. Its gain is (8/21)*(-50) + (2/7)*100 = 200/21, exactly attaining the oracle's OOP response value. Complete independent numeric-rule replay also agrees on the deviated value within 1e-9.

This direct terminal sum uses neither an exact best-response evaluator nor any production trainer. It supplies a concrete improvement even before computing the full NashConv. Matching a known value, and checking legal unilateral responses, remain distinct quality tests.

## Reproduction and validation

Run python -m unittest tests.test_raised_turn_argmax_control -v and repeat
with python -O. The helper pins the two original policy hashes, caps input bytes
at 2,000,000, checks input identity before deriving, builds fresh research
metadata and recomputes every metric. It never writes to either source policy
and does not call training.

Sol reviewed Luna's bounded draft and strengthened the integrated tests with
all-eight-metric independent numeric comparisons, exactly one changed root row,
and literal 44-river utility counts for every pair. The four integrated controls
plus the existing immutable physical-report regression passed together in
normal Python (five tests, 24.163 seconds). The four controls passed optimized
Python (7.100 seconds). Luna's revised scratch tests also passed normal and
optimized Python (four tests, 10.516/6.864 seconds). Documentation validation
passed for 135 Markdown files, 637 local links and 12 required entry points.
