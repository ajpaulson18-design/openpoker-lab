# Retained Windows validation qualification

The duplicate Windows suite for source
`f5918ff1968d328b868d7794065c0bcb7b4cc835` finished with **1,631 tests, three
failures, eight errors and 14 skips**. It is retained as a failed run. Complete
GitHub suites on Python 3.11, 3.12 and 3.13 passed for
[merged PR #201](https://github.com/ajpaulson18-design/openpoker-lab/pull/201).

The [qualification receipt](../benchmarks/results/flop-class-windows-validation-v1.json)
pins the three compressed raw logs and their uncompressed hashes:

- [Initial failed full run](../benchmarks/results/flop-class-windows-full-suite-initial-v1.log.gz).
- [Frozen historical replay rerun](../benchmarks/results/flop-class-windows-frozen-replay-v1.log.gz).
- [Short-path staging rerun](../benchmarks/results/flop-class-windows-short-path-rerun-v1.log.gz).

One error explicitly reports source drift during historical verification. The
lead committed source while the first local suite was running. Its one-test
frozen-source rerun passed. Later work uses isolated checkouts so source-stable
checks do not share a mutable checkout with ongoing implementation.

All remaining failures/errors occurred while opening existing turn/river
publication staging files with paths of 262, 264, 266 or 268 characters. All
nine affected test methods passed with identical source from the shorter
`C:\Users\pauls\Documents\Codex\ot` checkout. No solver, shared turn/river
module, test, filesystem policy or registry setting was changed for that rerun.
These observations establish a path-dependent Windows validation limitation;
they do not establish that the original local suite passed.
