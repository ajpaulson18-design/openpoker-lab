# Sparse policy epochs and stable information identity

The next architecture gate separates immutable full-history identity from
policy epochs. The [two-board immutable session](native-frozen-policy-session.md)
measured cold setup amortization, but still constructs/imports a complete dense
policy. Its result does not remove all-row quantization or the
[eleven-card State and parent failures](native-dyadic-storage-census.md).

The new independent reference defines a precise transition before a native
learner is accepted. Start with implicit Q52 uniform policy E0; evaluate a fixed
positive-target board B1 against that frozen epoch for both global seats;
accumulate exact signed regrets and prefix averages; derive E1; then evaluate
B2 against frozen E1 and derive E2. Regrets remain signed and unclipped. Policy
matching uses their positive parts and an independently implemented stable
largest-remainder apportionment. This is a deterministic two-observation
vanilla regret transition, not a sampled CFR+ or convergence claim.

The initial default is implicit uniform Q52. The experimental native Store
keeps nonzero numeric rows only when touched and quantizes changed regret rows. A public
history block may share its immutable legal menu across declared holdings;
information identity still includes the original holding index. Catalog row
identifiers must come from the owned full visible History, actor and holding,
with no second history/card strategy map. Different betting histories and
ordered reveal prefixes remain distinct even when they reach the same numeric
betting continuation. Generic holding capacity is not physical chance support.

The existing imported State remains immutable for its entire lifetime. Its
borrowed policy views cannot be repurposed to change a policy behind a running
walk. The sparse epoch lease freezes all views until both seats finish, then
publishes the next policy atomically. The ordinary CFR+ State has a separate
all-row/clipping lifecycle and is not silently relabeled as sparse vanilla CFR.

## Exact uniform-law arithmetic contract

This first reference admits only uniform proposal on PROOF9. Its board mass is
1/2520 and its prefix denominators at visible lengths 0/3/4/5 are
1/84/504/2520. The raw-regret denominator is fixed at `580*2^625`.
At most two 648-bit signed increments need at most 649 magnitude bits.
Four positive action weights sum within 651 bits. The existing quantizer
scales each normalized action weight by Q52, rather than scaling the sum;
the conservative scaled-action bound is 701 bits, inside the existing 704-bit
carrier. The quantizer still needs its own complete work/storage admission.

Average scaling preserves correlations rather than summing unrelated worst
cases. A raw action numerator is `m*qden*ownNum*u`, with
`m<=29`, `ownNum<=2^E`, `u<=2^52`, `E<=312`. Its denominator is
`29*c*2^(E+52)`, where c at each street is 1/10/20/20. A shared exact average
denominator `580*2^364` therefore scales by `(20/c)*2^(312-E)`.
At every street `qden*(20/c)<=2520`; each aligned numerator is at most
`73080*2^364`. Two increments are below `2^382`, and their sum across legal
actions equals the aligned average mass. The fixed denominator fits 374 bits.
Zero own reach and zero action units remain exact zeros. River-weighted or
mixed proposals require a separate denominator/width proof and are rejected.

## Evidence and open gates

The native Catalog component binds one History owner and declared actor holding
counts before allocation. It stores only encountered public-history blocks,
per-block seen-holding bitmaps and verified shared source menus. Opaque,
owner-qualified row handles remain stable across append-only growth. Both
resolve and borrowed-view reads consume the cumulative lifetime allowance;
foreign/default handles, wrong actor/menu and exhausted budgets poison the
owner. The existing State uses the same ordinal/depth identity helper with
the original query order, error meanings and History charges.

At source `847afaff09aa40c2c0b1f52e374cc424f50d31d9`, local compiled Catalog
controls pass three core C++ control claims normally and optimized. The
introduced catalog-control source is pinned at
`436108a8d9775dd112454298fcc4dffe059bfd52`; four independent Python catalog
checks pass normally and optimized at that source. Declaring
1,326 holding indices but resolving only endpoints 0 and 1325 creates one
public block and two seen information rows. Further action/ordered-flop
controls end with four public blocks, five seen rows, nineteen seen action
slots and three shared menus. Sixteen cumulative accesses charge 96,000
modeled work; the reserved metadata is 4,008 logical words/256,512 bits under
the existing caps. These are not allocator/RSS observations or full-range
physical support. Thirteen real ownership/resource rejection controls pass.

The existing State suite passes eleven checks in each interpreter mode after
the helper extraction. A complete existing ten-card bounded-division training
run preserves all 50,507,464 wire bytes (SHA256
`7fde396c4c2e645087d9fd8abdc373a97a485265bf157e537e3cfd181c538945`)
and all historical owner sidecars. The earlier generic raw-walk policy-provider
extraction also preserves all nineteen complete session outputs and independent
row checks. These are regression/parity gates, with no new speed or capacity
claim. Platform CI and immutable source-inclusive packaging remain separate.

The maintained immutable packet set is recorded in
[`benchmarks/results/sparse-strategy-catalog-v1/manifest.json`](../benchmarks/results/sparse-strategy-catalog-v1/manifest.json).
It pins native Catalog source `847afaff09aa40c2c0b1f52e374cc424f50d31d9`,
introduced packet source `436108a8d9775dd112454298fcc4dffe059bfd52`, and
maintained replay source `03e7fa42eacb561539fda26a41de091c8955710c`. The
catalog archive is 2,463,508 bytes / 305 members
(`8bc5891ea688a7622f24e89d419e4b2d05ef924344e3f720e04e4ce8743b060a`);
legacy regression is 7,494,245 bytes / 687 members
(`32f4e332320d0e1c622d5bfc81b0562d4cdf2eb6140967547756503346acfc7e`);
provider parity is 4,638,454 bytes / 386 members
(`3c1181eadfdec6569e575777956a32e02fa26ed7a0895222d190eed1f4cefac9`); and
the retained weak-transition witness is 332,141 bytes / 6 members
(`07fa828c8c7d106257accef5c2320a4cb39c737f8362609ed34b94f7d1d5f809`).

Local packet replay completed exactly in normal and optimized Python. The
captured logs are `../sparse-catalog-packet1-normal.log` and
`../sparse-catalog-packet1-optimized.log` outside the checkout. Each run
replayed the catalog, legacy regression and provider-parity archives; catalog
normal/optimized archived results matched, the historical 50,507,464-byte
State wire output and SHA256 remained exact, and all nineteen provider session
outputs matched. The replay records zero candidate calls and does not execute
archived source. The new
[`sparse-strategy-catalog-packet.yml`](../.github/workflows/sparse-strategy-catalog-packet.yml)
repeats normal and optimized replay on Windows and Linux with full Git history
and retains both reports as CI artifacts. Local success is not a claim that
these new CI jobs have already run.

At component source `388234c57c1c105cfc9262a3eae20082be1a8ea4`, the bounded
native Store component passes four independent Python controls in both normal
and optimized modes. The local process records are in
`../sparse-epoch-component4-normal` and
`../sparse-epoch-component4-optimized`. They exercise synthetic cumulative
signed regrets, next-policy quantization from positive parts, exact average
scales, average-only updates without intermediate quantization, and lifecycle,
menu and raw-centering rejection guards. This establishes component semantics
only; whole-game execution is recorded separately below. It establishes no
scale, runtime, speed or solution-quality result.

## Executed two-epoch native coupling

Native build source `b4240aa` couples the existing exact raw walk to a leased
sparse Store, with no dense imported State or full-policy input/echo. The
complete independent controller and oracle were frozen at
`41ae6727523abec3044bd32ae93b321d8d2b5bed` before candidate execution. Both
seats use one frozen policy per observation; every supported raw row is staged
before the walk and lease are destroyed and the next epoch is committed.
Only one raw image is live at a time. E1 is serialized privately and no stdout
is published until E2 and the whole-request checks pass.

The independent rank-free forecast examines all 2,520 legal uniform board
selectors and bounds 6,350,400 ordered pairs with replacement. It reserves
136,367,150 modeled work, 1,095,241 entries, 55,627,714 payload bits and
619,152 output bytes, within the unchanged ceilings. Its work partition is
43,000,000 source allowance, 47,649,376 Catalog, 6,036,640 History,
2,579,498 Chance, 22,514,624 Store plus quantizer, 4,680,580 parent numeric
work and 9,906,432 serialization. Borrowed owner charges are counted once.
The source allocation reservation is not a complete allocator census, and
payload bits are not RSS. Scalar whole-domain admission precedes Template,
private chance preparation, History, Catalog and Store construction.

Six complete requests pass normally and with optimized Python: different
positive private-pair boards, reversed order, repeated board, positive then
zero-full-target with a shared turn, zero-target flop first, and maximum raw
stage. Seven invalid CLI requests reject with observed exit 2 and empty
stdout. All thirteen output streams are byte-identical between modes.
Independent replay compares every exported cumulative signed R, exact A and
Q52 unit, both roots against each epoch's input policy, and all 24,420 policy
rows including implicit defaults. Repeated and zero-target observations need
not change the policy. There is no RNG sampler in this request.

For the pinned different-pair sequence, E1 has 440 numeric rows and E2 has
868; policy overlays number 434 and 674. The request performs 1,760 policy
reads, stages 880 rows and quantizes 677 changed-regret rows. It charges
108,096,909 modeled work and emits 505,056 bytes. The largest actual work in
the six-case matrix is 112,604,231. These are bounded operation counters,
not runtime or throughput measurements. Local records are
`../sparse-two-epoch1-normal`, `../sparse-two-epoch1-optimized`, and
`../sparse-two-epoch1-parity.log`. Current saved-result replay also passes
normally and optimized with zero candidate calls and no archived-source
execution; the logs are `../sparse-two-epoch-replay1-normal.log` and
`../sparse-two-epoch-replay1-optimized.log`.

The first compile at `ef1601a` failed because two static Catalog methods were
qualified at namespace scope. Its build failure and source remain preserved;
the correction changes the method qualification. It was not a numerical test
failure. Dedicated Windows, Linux and sanitized epoch CI pass at source
`8652d5d2c5f929f18ee363d40f7ec20a03748a6b`; the catalog packet also replays
normally and optimized on both Windows and Linux. The broader Windows History
control compilation failure is preserved separately.

The source-inclusive immutable whole-game packets are recorded in
[`sparse-two-epoch-v1/manifest.json`](../benchmarks/results/sparse-two-epoch-v1/manifest.json).
Normal and optimized archives each contain 146 members and are 1,017,982 and
1,017,991 bytes (SHA256
`0f8fb2ebc6a707346996ee7bf9ba73799ba5873c2961e4821bc4969c3fd4d269`
and `7250a203c4946f969f70df2e039808044fcdd3171737db988227d9ee211dc1d5`).
The 671,057-byte development archive retains the failed first compilation and
explicitly labels its reconstructed committed inputs as distinct from an
original raw-checkout attestation. Executable bytes are omitted; build/source
manifests and the observed executable hashes are retained.

The maintained `scripts.replay_sparse_two_epoch_packet` reader passes normally
and optimized, authenticates all three archives before mathematical replay,
reconstructs both complete matrices with zero candidate calls, and never
executes archived source. Its initial development-digest transcription refusal
is retained separately; the archive bytes were unchanged. Normal/optimized
component and independent-reference packets also replay exactly through
`scripts.replay_sparse_epoch_component_packet`. Windows/Linux CI now includes
these maintained packet readers; their new job results remain a separate gate.

The independent reference uses literal numeric betting rules, Fraction raw
updates and an independent ranker. It may materialize the complete policy for
oracle evaluation; that is not a native storage claim. Five focused controls
pass normally and under optimized Python: two frozen-policy transitions,
untouched uniform defaults, retained negative regret, exact denominator/width
bounds, stable tie order and weighted-law rejection. A zero-full-target witness
leaves regret/policy unchanged while earlier-prefix averages change.

The stronger transition control initially failed on two boards with the same
five cards and swapped turn/river: the second observation changed raw state
without changing the quantized policy. That failed control is retained at
`c2ad165`. The accepted witness selects the first board of two different
compatible private pairs, checks that E2 differs from E1 and from evaluating
B2 against E0, and preserves untouched uniform rows. This establishes the
selected transition semantics, not a claim that every observation changes
policy.

Cross-platform execution, maintained immutable whole-game packaging, a bounded
sampler and longer learning lifecycle, saved-policy quality, and realistic-range
resource forecasts remain unfinished gates. The old eleven-card State and
quantizer rejections still stand. Two selected PROOF9 observations do not
establish convergence, eleven-card admission, realistic-range capacity or
unrestricted NLHE readiness. All existing solver defaults and limits remain.
