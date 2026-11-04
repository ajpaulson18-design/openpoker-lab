# Frozen-update source and run controls

Status: development prerequisites for the [complete study](virtual-frozen-update-study.md).
No all-outcome update batch has run. These controls neither certify numerical
values nor establish native admission.

## Committed source and raw bytes

`tests/virtual_frozen_source_guard.py` binds every regular file in the committed
Git tree to an exact working-file SHA-256. It validates path/count/file/total-byte
limits, rejects linked/reparse paths and Git links, and streams Git blobs and
working files in bounded chunks. Committed blob object IDs are independently
recomputed while reading. An optional external exclusive snapshot retains raw
checkout bytes, never executable archived code.

The first capture explicitly checks Git text/eol attributes and newline settings.
It accepts identical raw bytes or a declared LF normalization that matches the
committed content. Custom clean filters, working-tree encodings and ident
transforms reject before dirty-status checks; fsmonitor hooks are disabled for
metadata queries. Source changes, untracked files and changed HEAD reject.
The later recheck requires identical raw bytes, even if Git caches classify the
file as unchanged. It also rechecks attributes, newline configuration, HEAD and
complete path/object identities. Newline bridging is not repeated as a drift
exception.

Metadata stdout/stderr readers enforce their limits; the committed blob stream
has a watchdog. The source inventory/hash receipt alone does not authenticate
all semantic inputs of an arbitrary program. The eventual study controller must
require its specific complete reference/protocol/build closure, actual compiler,
headers and executable, then compose all guards before execution.

Seven controls pass normally and optimized using disposable Git repositories:
complete capture/copy/recheck, explicit LF bridge plus cached-metadata raw drift,
binary/untracked drift, changed commit, unsupported transform ordering, linked
Git object rejection, and CRLF conversion across a streaming chunk boundary.
The initial LF-bridge fixture was dirty before capture; that rejection is retained.
The corrected fixture refreshes its normalized Git index before capture and then
uses assume-unchanged metadata to ensure raw hashing catches a later edit.
These are fixture results, not a full production-tree authentication receipt.

## Exclusive attempt and observed process exit

`tests/virtual_frozen_run_control.py` creates an exclusive attempt directory and
claim receipt. Any existing directory blocks acquisition, including failed or
incomplete attempts. Terminal metadata is exclusive and single-use. No automatic
retry, directory cleanup or partial-batch resume is implemented.

The child helper saves the request before launch, runs an explicit argument list
without a shell, streams capped stdout/stderr directly to new files, and kills
the child on overflow or deadline. It waits for the actual process exit before
writing its process receipt, preserving exit code, saved-stream hashes, byte
counts and first stream failure. A nonzero exit, timeout or overflow is evidence
of failure, not a numerical result. The helper is scoped to the authenticated
single-process native probe, which does not spawn descendant programs; it is
not a general process-tree containment system.

Four controls pass normally and optimized using small Python child processes:
exclusive failed-attempt retention, saved request/stdout/stderr plus observed
nonzero exit, capped overflow termination, and deadline termination with a saved
receipt. No native solver, ranker or reference update executes in these controls.

The [development manifest](../benchmarks/results/virtual-frozen-source-control-development-v1/manifest.json)
preserves the original dirty-fixture failure, raw control streams and before/after
source identities. All final normal/optimized control processes exited 0.

A separate [actual project-tree observation](../benchmarks/results/virtual-frozen-real-source-auth-v1/manifest.json)
at committed source `2628a0eff7c38d148906518817fa16db456a7b83` authenticates
2,373 files/358,262,859 bytes, then passes the full raw-byte recheck. The observed
outer process exits 0, entering zero native or reference computations. Total
capture plus recheck takes 117.575 seconds in this environment. This is guard
cost, not solver speed. The archive retains the hash inventory and raw process
receipt, not a copy of every source file. Complete study freeze must still save
its own cohort and authenticate actual build/dependency/executable identities.

## Remaining integration

A full enforcing controller still must compose source/build authentication,
both native worst-law admissions, all experiment meters, exclusive claim,
per-call output/metadata preservation, reference exports, exact comparisons,
complete per-law expectation finalization and real saved corruption witnesses.
Only then can a clean committed executable/protocol cohort be frozen for one
complete experiment. The larger solver/training/quality objective remains open.
