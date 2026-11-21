# Native history control recursive-call mitigation

The test-only mitigation wraps recursive history-control calls in a noinline boundary. This is a compiler-expansion mitigation hypothesis: earlier MSVC 14.52 jobs recorded process exit `0xc00000fd`, but the cause is not established. No production code, compiler flags, or resource caps changed.

The isolated branch contains the original mitigation commit `45e72021bc4895ccca37652fe13fe03bc7900702` and follow-up explicit-vector fix `0baab8a1df93d80205eb7b6f419ed708e52c5edb`. The explicit vectors preserve the same empty path and initial selection while making template argument deduction valid.

Local baseline and corrected builds both passed with MSVC 19.44.35229. The existing history-control test passed in normal and optimized Python modes against each binary. All four captured native stdout streams match exactly (600,954 bytes; SHA-256 `74de3b1b…82b8e5ec`); each child exited 0 with empty stderr. The initial modified compile failure is retained. Local MSVC 19.44 results do not determine the target MSVC 14.52 CI result.

The bounded evidence archive is [evidence.zip](evidence.zip). Its external SHA-256 and member manifest are in [manifest.json](manifest.json). The ZIP includes the three original CI failure archives unchanged.
