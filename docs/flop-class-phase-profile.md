# Fixed-flop phase profile

This is one opt-in 560-sweep compact solve wrapped at existing module boundaries.
It does not modify or instrument the published solver and CFR+ sources. The
ordinary complete-call comparison remains the primary timing evidence.

Each wrapper records a unique event ID, parent event ID, phase name, UTC start
and finish, monotonic wall seconds, process CPU seconds, and error status. A
phase can be nested inside another phase; inclusive durations overlap and must
not be summed as separate costs. Wrappers are restored in `finally`, including
when a phase raises.

The profile includes the existing solve and canonical serialization/hash
boundary through `flop_class_call_measurement.measure_call`. Wrapper dispatch
adds overhead, so these phase timings are diagnostic only, not the preregistered
call medians or a same-work speed comparison. They do not measure RSS.

The run admits the full 560-sweep request before pilot authentication, then
requires clean source snapshots before and after. It retains the raw policy in
bounded gzip and limits the event ledger to 1,000 invocations. A failed profile
remains an error artifact with traceback; it is never retried. The protocol's
LF SHA-256 is pinned by the runner. No actual phase profile has run yet.
