# Native training walk observations

The study extends the [phase measurements](native-training-phase-profile.md) with
periodic observations of the standard trainer's primary thread on Windows x64.
The trainer runs the bounded ten-card, two-sweep fixture. The observer launches
the trainer in an owned Windows job, takes a bounded snapshot of its primary
thread, resumes it, and unwinds the saved stack using admitted local image data.
The report retains instruction addresses, advancing stack frames, unresolved
frames, API results, and the observed child exit.

The image correspondence check binds the public symbol map to the training
executable. The two PE images differ only in the COFF and debug-directory
timestamps. After masking those structurally located fields in memory, every
other byte matches. Labels require a public symbol at the start of a verified
unwind extent. Folded aliases remain visible in the report.

The first two studies stopped when the primary thread began exiting during a
capture. The trainer produced the complete reference stream and cleanup
observed exit zero in both cases. The final observer classifies a capture
failure as a separate terminal event only after both owned handles signal and
both exit codes are read as zero. A bounded wait of up to 250 ms covers kernel
teardown. The final study retained four such failed capture attempts and used
1,641 valid observations in its context counts.

All 32 calls in the completed study reproduced the reference compact stream,
checkpoints, and owner receipts. The independent reviewer replayed the saved
policy with zero native trainer calls. The 16 focused controls pass in both
normal and optimized Python. They include failure-path controls for child
ownership, the pause watchdog, and the report and image bounds.

| Alternating comparison | Median paired ratio | Limit |
| --- | ---: | ---: |
| Sampling enabled over disabled, same observer | 0.89179 | 1.01 |
| Disabled observer over direct trainer | 1.04891 | 1.01 |

The wrapper comparison missed the preset limit. Host load was uncontrolled and
individual pairs varied substantially. The samples are provisional wall-time
observations, including time waiting for I/O. An identified caller can include
inlined work and calls into system libraries.

| Nearest identified project frame | Observations |
| --- | ---: |
| Image staging | 306 |
| Committed checkpoint streaming | 235 |
| Training walk visit | 142 |
| Policy spill append | 99 |
| Prepared public chance contraction | 98 |

All 1,641 samples are in the denominator, including four without a resolved
project context. Context counts identify expensive execution paths on the
fixture. They do not allocate exclusive CPU time to a method.

The [eleven-card forecast](native-dyadic-storage-census.md#compiled-eleven-card-forecast)
projects 5.95 billion modeled work units against 2.15 billion. Parent work
alone projects 2.31 billion units. Removing all modeled State and Quantizer
work would leave 4.28 billion. The forecast and the observed staging and
transport contexts support investigating a traversal and state schedule that
avoids work on unvisited public branches. The bounded starting point is exact
expected-update parity for visible-prefix fold contributions under uniform
public sampling, followed by staged, generation-safe row updates and an
independent saved-policy quality check.

The [study manifest](../benchmarks/results/native-owned-child-walk-v1/manifest.json)
links the immutable archive containing all three studies, the two image files
and public map, output and source identities, the controls, and saved replay.

