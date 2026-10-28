# Pinned Boost.Multiprecision standalone headers

This directory contains all 198 files from the official package's `include/`
tree, unchanged, in `headers.zip`, plus its unchanged Boost Software License
1.0 and an exact per-file SHA256 inventory. Original source:
[Boost.Multiprecision 1.92 standalone release](https://github.com/boostorg/multiprecision/releases/tag/Boost_1_92_0),
tag `Boost_1_92_0`, commit `1f7acd34fe929573c131e869867dc1d12b8080b6`.

The original complete archive SHA256 is
`ced65b49128fd95487759d6aa2cf3ae2c57b09bec8d57f6b3c02d67e44d051e4`.
The deterministic, include-only archive SHA256 is
`33c422ab3ebfa9e86c62f41f372ec2b9c2cefa303f1885391aa4d8250ef2f831`.
All original header notices remain; no upstream code is relabeled as project
ownership. See [license](LICENSE_1_0.txt) and [byte inventory](manifest.json).

The native exact build script verifies the pinned archive, license, manifest and
every header before extracting to an external build directory. It defines
`BOOST_MP_STANDALONE`, uses the installed C++20 compiler and performs no network
download or global dependency installation. The entire upstream include tree is
included rather than only the 70 headers observed on MSVC, because other
compilers/platforms select different configuration headers. Cross-platform
conformance still requires actual compilation and tests.

This dependency supplies integer arithmetic. It is not a poker solver/evaluator,
probability model, correct-rounding contract or resource policy. Project-owned
admission, exact arithmetic/rounding, game identity, policy replay and native
build/source provenance remain separate obligations. The baseline Python solver
has no added Python runtime package or automatic native dependency.
