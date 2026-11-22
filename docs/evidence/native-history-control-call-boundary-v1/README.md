# Native history controls MSVC failure investigation

This record tracks the test-only MSVC 14.52 compiler failure. Its cause is unproven. No production code, compiler flags, or resource caps changed.

The isolated branch retains the noinline experiment in commit `45e72021bc4895ccca37652fe13fe03bc7900702` and its explicit-vector compile fix in `0baab8a1df93d80205eb7b6f419ed708e52c5edb`. That hypothesis did not resolve the compiler failure: all three subsequent MSVC 14.52 phases, including syntax-only `/Zs` and unoptimized `/Od`, exited `0xc00000fd`. The failure alone does not identify the cause.

Local baseline and corrected builds both passed with MSVC 19.44.35229. The existing history-control test passed in normal and optimized Python modes against each binary. All four captured native stdout streams match exactly (600,954 bytes; SHA-256 `74de3b1b…82b8e5ec`); each child exited 0 with empty stderr. The initial modified compile failure is retained. Local MSVC 19.44 results do not determine the target MSVC 14.52 CI result.

The bounded original evidence archive is [evidence.zip](evidence.zip). Its external SHA-256 and member manifest are in [manifest.json](manifest.json). The ZIP includes the three first CI failure archives unchanged. Later phase artifacts are stored beside it as separate hash-recorded files.

## Later MSVC 14.52 CI result

The first published mitigation attempt at `0baab8a1df93d80205eb7b6f419ed708e52c5edb` failed again in workflow run `44960913155`, job `137019288511`. The archived MSVC 19.52.37029 compiler (toolset path 14.52.37025) exited `3221225725` (`0xc00000fd`) while compiling the history controls with `/O2`. Its captured build log contains only the translation unit filename and no C++ diagnostic. This confirms the prior mitigation did not resolve the failure on that CI compiler; it does not prove whether the failure comes from frontend or optimizer expansion. The original archive is preserved at [raw-history-failure-14729568289.zip](raw-history-failure-14729568289.zip), with its SHA-256 and run metadata in [ci-failure-14729568289.json](ci-failure-14729568289.json). The earlier `evidence.zip` remains byte-for-byte unchanged.

## Compiler phase diagnostic

A bounded CI diagnostic ran `/Zs`, compile-only `/O2`, and compile-only `/Od` against the authenticated test translation unit. All three exited `3221225725` (`0xc00000fd`) under MSVC 19.52.37029 (toolset 14.52.37025), with source and compiler hashes unchanged. This falsifies the optimizer-only/noinline explanation: the same exit occurs in syntax-only and unoptimized compile phases. It still does not identify the cause. The exact archive is [history-msvc1452-phase-diagnostic-14731366057.zip](history-msvc1452-phase-diagnostic-14731366057.zip); hashes, phase outputs and metadata are in [its JSON record](history-msvc1452-phase-diagnostic-14731366057.json).

## Fixed-signature comparison candidate

The current test-only candidate restores the pre-experiment control source and replaces only its generic self-recursive `compare` callback with the fixed-signature `compare_visits` helper. It preserves the comparison checks, traversal order, output, receipts, rejection controls, and all other baseline recursive walkers. Local normal and optimized validation passed under MSVC 19.44.35229; both 600,954-byte native outputs match the retained baseline byte-for-byte (SHA-256 `74de3b1b…82b8e5ec`). This does not establish MSVC 14.52 behavior or the failure cause. The source, build receipt, and both outputs are preserved in [named-compare-local-17f0ecf.zip](named-compare-local-17f0ecf.zip), with an external hash record in [named-compare-local-17f0ecf.json](named-compare-local-17f0ecf.json).
