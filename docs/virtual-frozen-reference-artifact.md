# Streaming exact reference artifacts

Status: development codec for the [complete frozen-update study](virtual-frozen-update-study.md).
No complete native/reference update batch has run. The codec saves semantic
rows from either a sampled-board reference or the q-free expected reference.
Producer/admission receipts and row-visit diagnostics belong to separately
preserved metadata; this format does not serialize a Python context or graph.

Files contain an ASCII JSON header, one JSON array per row and a final checksum
footer. Every rational is a pair of canonical signed-lowercase hexadecimal
numerator and positive denominator strings. The maximum integer width is 4,096
bits. Ordered actions, policy exponents, physical own-hand/global-seat identity,
full visible history, raw regret values, average mass and average-action values
are retained exactly. Row classes may differ after loading; semantic fields
are the comparison boundary. Loaded expected rows expose the q-free average
mass name as an alias.

The writer opens exclusively and never overwrites existing evidence. It reserves
the complete declared output allowance before opening, emits one bounded row
at a time and retains any incomplete file on failure. No whole-file JSON object
or text buffer is created. The reader bounds each line before parsing, validates
nesting before JSON allocates containers, bounds decimal and hexadecimal widths
before integer conversion, and rejects duplicate fields/keys, invalid identities,
truncation, count mismatch, checksum drift and trailing bytes. It retains the
loaded row dictionary; this is not constant-memory loading of an entire policy.

The checksum covers the exact header and row bytes. It detects drift, not source
provenance or mathematical truth. A deliberately changed value with a recomputed
checksum loads structurally and still fails the separate exact comparator. The
codec does not sum or multiply independent large rational denominators merely
to frame them. Fraction reconstruction stays within the bounded numerator and
denominator input widths; the original mathematical values are saved for review.

## Allowances

For declared rows R, action slots S and scalar fields V=R+2*S, the byte allowance
is `8192 + R*(256+15*130) + S*130 + 2*V*(1024+4)`.
The header/footer are at most 4,096 bytes each and each row line at most 32,768.
Escaped printable token bytes are included. Sampled artifacts permit at most
868 rows/2,078 slots; expected artifacts permit at most 24,420/58,164.
Counts and token/vector lengths reject before result-to-frame copies.

The codec reports named byte/field work, retained logical entries, retained
integer payload and separate bounded row scratch. These are framing/model
allowances, not CPU, Python allocator or RSS measurements. Writer payload is
borrowed from the already-admitted result. The reader additionally owns all
loaded semantic rows and their bounded Fraction values. The enclosing experiment
must account for live reference results and native/comparator/accumulator state
at the same time.

The complete reference export family bounds two laws of 2,520 sampled artifacts
plus one q-free artifact. It uses the independently counted 107,080 row records
per law and a four-action-per-row upper bound. Native raw stdout/stderr, request
files, metadata, source/build closure and outer logs remain separate; the returned
family receipt explicitly does not claim whole-study admission.

## Executed controls

Seven controls pass normally and optimized: exact sampled round-trip into the
separate comparator, expected-row alias and 4,096-bit boundary, checksum/truncation/
trailing-byte rejection, decimal/hex/nesting bounds, exclusive creation and
whole-output admission, complete export-family accounting, and a changed value
with a recomputed checksum still failing mathematical comparison.

The initial round-trip assertion compared two different dataclass types and
failed despite matching semantic fields. Its original source and raw failure
are preserved. The corrected assertion compares all saved semantic fields and
then invokes the independent comparator. No producer was rerun for this codec
or its fixture correction. Whole-study source freeze, actual full exported
updates, complete expectation acceptance and later training/quality remain open.
