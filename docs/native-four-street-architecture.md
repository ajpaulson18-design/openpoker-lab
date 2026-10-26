# Native four-street computation architecture

## Decision and scope

The owner's October 25, 2026 instruction authorizes language migration for
performance, memory, numerical accuracy and reliability without requiring
Python to survive. Sol selects a C++ computational backend with a separate
Python control and validation layer for the current coupled finite game.
This is a measured migration boundary, not a claim that one language is fastest
for every component or that unrestricted Hold'em has been solved.

The first migrated component is complete public-tree, alternating CFR+ training
across preflop, flop, turn and river. One native invocation owns all sweeps.
Python prepares the bounded physical game, enforces existing admission, computes
numeric best responses, serializes the established result and runs independent
numeric and rational policy audits. Existing C equity/fixed-tree engines and
the JavaScript presentation remain separate working capabilities.

Native selection is explicit; the original Python backend remains the regression
reference. Unsupported algorithms, delayed averaging, convergence callbacks and
alternative indexing reject before preparation. Native errors propagate without
a Python retry. Supported solves use zero-delay CFR+, public-batched training
and diagnostics, and public-vector admission.

## Technical comparison

| Candidate | Assessment for this workload | Decision |
| --- | --- | --- |
| Python training | Dictionaries, recursive closures and list allocation dominate the profiled game. Arbitrary precision remains useful in the independent exact oracle. | Migrate repeated training; retain bounded setup, API and independent checks while their costs are small. |
| C | Existing fixed-tree evidence supports native training, but its protocol lacks public chance nodes. Manual ownership and indexing require care. | Retain existing engines without changing their frozen protocol. |
| C++ | Contiguous numeric storage, owned buffers and strict binary64 arithmetic support a chance-aware backend without a managed runtime. The language does not guarantee memory safety. | Implement with bounds/overflow checks, strict FP and compiled CI; measure full calls. |
| Rust | Ownership and checked indexing offer strong reliability benefits without garbage collection; it can represent the same numeric model. No equal-work Rust implementation has been measured here. | Credible alternative; no C++-over-Rust speed claim. Reconsider against measured execution and safety evidence. |
| Julia, Java, Go, C# | Introduce another runtime/compiler ecosystem without demonstrated advantage for this bounded numeric model. | Require evidence of a benefit before adding another production language. |

The numeric representation and execution boundary control the choice. Being
compiled does not establish a speedup. A full native rewrite of preparation or
transport is not justified by training-dominated evidence alone. Standalone
native game construction, parallelism and larger supports require separate
profiles and independent validation. Exact arithmetic is not replaced merely
to reduce the language inventory.

## Evidence and acceptance

A diagnostic cProfile of the existing 22-world fixture at T100 on bundled
CPython 3.12 observed 14.923 seconds: 14.444 seconds in `train_public_batched`,
0.144 in tree merge and 0.124 in public diagnostics. Instrumentation perturbs
timing; these are phase observations rather than benchmark medians. T100 had
numeric NashConv about 0.011806 BB, a diagnostic miss rather than the historical
T1000 quality result.

The separate [same-work benchmark](../scripts/benchmark_native_four_street.py)
retains full-call timings, complete payloads, native source/build identities,
repetitions and failures. Both backends use the same game, iteration budget,
CFR+ schedule and diagnostics. Independent visible-information replay checks
profile and legal response values; policy parity is an additional control.
Historical [frozen evidence](four-street-integration-result.md) is preserved.
Runtime, Python allocations, modeled native heap and process RSS remain distinct.

The [saved-sample verifier](../scripts/verify_native_four_street_sample.py)
authenticates an externally pinned benchmark report, its clean/stable source
closure and first native raw envelope before importing the independent rational
certificate. It performs no production solve, native call or training. Its exact
normalization ledger and whole-game gap are retained separately from timing.

## Invariants

Public reveals are explicit chance edges. Prefix-conditioned joint private-hand
mass and mass-times-showdown-sign travel separately. No strategy sees opponent
hands or future reveals. Regrets use opponent reach; averaging uses own reach,
prefix marginal and original iteration weight. Player 0 updates and rematches,
then player 1 updates and rematches, then the completed profile is averaged.
All physical/off-path rows and uniform zero-average fallbacks are retained.

Transport validates topology, indices, finite values and resource envelopes.
Native admission supplements existing Python admission and charges the full
requested iteration count. Work/allocation arithmetic rejects overflow. Strict
build flags prohibit unsafe reassociation and contraction. Binary64 differences
are assessed by numeric replay and policy tolerances, not assumed absent.

The versioned native work model counts logical loop entries, including repeated
terminal/prefix-edge visits, rematching, completed-sweep averaging, setup/scratch
initialization and output. Native parsing checks declared shape counters against
the parsed tree before training. The 500-million-entry and 256 MiB modeled
storage ceilings are independent of the existing Python guards. Modeled storage
includes bounded input/parser reserve, owned arrays, depth scratch and output;
it is not an allocator, operating-system or RSS bound.

Float reductions select left-to-right addition for Python 3.11 and compensated
addition for Python 3.12 or later. This mode and caller version are recorded.
Initial development found a 0.304 maximum policy discrepancy on tied off-path
rows before matching the reference reductions; that failed comparison is not a
successful control. Strict compilation alone did not resolve it. Review also
corrected an initial unique-edge work undercount and hidden-future rejection
at early all-in terminals before the retained benchmark was run.

Source-built executables require matching source/binary manifests. Builds are
explicit and outside the source tree. No external evaluator, generated table,
solver implementation or third-party runtime is imported.

## Build and call

Use an x64 MSVC developer terminal on Windows, or a POSIX C++ environment:

```sh
python -m scripts.build_native_public --output-dir /absolute/outside-source/build
```

```python
from pokerlab.four_street_solver import solve_four_street

# request: algorithm="cfrplus", traversal=diagnostics="public-batched",
# resource_model="public-vector".
result = solve_four_street(request, native_executable="/absolute/build/native-public-train")
```

Windows produces `native-public-train.exe`. The immutable request describes the
mathematical game; deployment paths are call options. Native build provenance
is retained in the result payload.

## Design references

References, not imported implementations:
[C++ resource and bounds guidance](https://isocpp.github.io/CppCoreGuidelines/CppCoreGuidelines),
[Rust ownership](https://doc.rust-lang.org/stable/book/ch04-00-understanding-ownership.html),
and [Clang floating-point modes](https://clang.llvm.org/docs/UsersManual.html).
Repository tests and retained runs establish this implementation's behavior.
