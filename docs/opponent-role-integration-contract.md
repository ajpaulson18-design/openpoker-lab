# Native policy-role integration contract

Status: implementation contract after the independently replayed
[conditional moments](opponent-action-moment-gate.md) and
[native compact-row arithmetic](opponent-role-row-native.md). The native
[role lease facade](opponent-role-epoch.md) is implemented as a source-frozen
component with original execution acceptance pending. The complete sampled
walk below is not implemented or admitted.

## Architectural choice and evidence

Keep the current History, Catalog, Prepared chance and sparse Store as the
shared owners. Add a narrow role facade around the existing Store; do not
introduce a second policy database, private row identity scheme or production
solver. Initially retain canonical Store denominators `2^625` and `2^364`.
Compute raw sampled values on `2^365`/Q52 and expand exactly at the staging
boundary. The executed row gate proves this scale coupling preserves every
signed cumulative coordinate and Q52 policy image. A later compact Store
contract can change storage separately, with its own complete resource proof.

This sequence follows the bottleneck evidence: admitted read-family cycles
are only about 20% of the native walk, and both finer arithmetic observers
miss their fixed overhead gates. The structural study predicts a large
branch-count reduction, while the moment study validates the conditional
estimator. Native row measurements show that reduced input width does not
itself reduce Quantizer division width. Therefore pursue complete walk/role
integration before selecting a division rewrite or claiming a speedup.

## Roles, ownership and publication

The facade owns its underlying Store privately. It exposes no conversion to
the legacy raw walk's concrete epoch lease. The underlying one-read canonical
numeric contract is reused only for ownership, fixed denominator arithmetic,
implicit policies and atomic publication; it is not relabeled as a sampled
walk proof. The new front door must explicitly name the role contract.

An epoch binds one active Prepared joint-ticket certificate, declared range
counts and the same History deck. Each read checks the selected actor's
original holding index and certified visible public prefix. Cache identity
includes actor, original own holding and the **full** History ordinal; a
shared numeric source node is never an information key. The first visit
obtains the existing Catalog-owned RowId and frozen policy. Subsequent
opposite-target visits reuse only that same immutable policy within the
active epoch. No cached policy survives publication.

The target order is SB then BB. A row may be visited once in each target
traversal; its role mask records both separately. The actor's own traversal
authorizes regret increments; the other traversal authorizes average units.
Missing regret role requires zero regrets. Missing averaging role requires
zero averages; present averaging role requires the exact frozen Q52 units.
Every staged regret row must center exactly on those frozen units. Separate
owner/generation-qualified row tokens prevent foreign, stale, duplicate or
unobserved stages. Both target walks must finish and all observed rows must
stage before publication. Any failed or abandoned facade epoch blocks its
commit, including an error after otherwise complete staging.

Role bookkeeping alone cannot prove recursive branch completeness. That
belongs to the source-frozen native front door and independently reconstructed
transcript: every own action, including zero-probability actions, is expanded;
each opponent node follows exactly one supported action. Root-role marks and
declared counts alone must not be advertised as that proof.

## Native walk and ticket contract

At a target node, recursively compute every child, mix by the frozen Q52
policy, and emit child minus mixed value. At an opponent node, choose by exact
integer CDF with a ticket in `[0,2^52)`, emit that opponent row's policy units
as its averages, and return the chosen child's value. Opponent reach and
proposal reach cancel; the native recurrence needs neither prefix product.
The two target roots are independent estimates in global SB/BB roles. Never
set the BB root to the negative of the realized SB root.

Initially use supplied deterministic ticket tapes with an explicit bounded
schema. Preserve every actual ticket, target, full row descriptor, selected
action and Q52 proposal factor. Native first/last ticket witnesses are not
random draws and make no convergence claim. A stochastic-law interpretation
requires uniform, independent tickets under its separately specified source.
Do not form a product over the entire branched partial transcript, and do not
reuse a draw merely because two paths share a numeric source continuation.

Fold/showdown payoff, whole-hand money, ordered reveals and physical private
collision conditioning stay with their existing authorities. Conditional
raw parity composes with the already verified full-range true-joint producer;
it does not replace that producer with a selected-hand prior.

## Admission and independent acceptance

Before native allocation or range/rank/template preparation, forecast the
whole request: existing owners, variable row/slot union, both role directories,
cache, token validation, extra History checks, exact scaling, complete stage
and publication, proposal tapes, raw policy output and validation scratch.
Retain eager Catalog storage first; its lazy candidate has two preserved
elapsed misses and should not be conflated with branch sampling.

The componentwise structural maxima (367 visits, 204 policy encounters and
327 traversed actions per two-target world) remain conservative for any legal
policy-CDF path: its support is a subset of the uniform proposal's legal
paths. Expected uniform encounters and million-world occupancy do **not**
transfer to evolving policy proposals. Use at most 204 cached rows/816 action
slots per observation as a conservative envelope; these are proposed maxima,
not an executed whole-request admission. Derive cumulative T2 bounds and all
remaining component charges independently before implementing them. Keep
the old work, storage, integer, I/O and learning-lifetime ceilings unchanged.

Required tests include both target roots and every raw regret/average/policy
coordinate against a current independent literal-history transcript oracle;
two evolving epochs; zero-policy branches; distinct histories sharing a
numeric source; hidden opponent/tail changes under identical visible input;
both existing full52 range profiles; malformed tickets; foreign certificates,
History owners and row tokens; duplicate/missing roles; wrong frozen averages;
stale/abandoned epochs; and original-source/raw-byte drift. Preserve all input
tapes, policies, misses and original process/build receipts, and independently
replay saved evidence before accepting the native path.

Per-step branch reduction is not cost to equal solver quality. After exact
native parity and complete admission, measure full calls under a frozen,
predeclared comparison; then separately extend the supported lifetime and
evaluate saved policies with independent visible-information diagnostics.
Any retained sparse-row or quality failure must drive architecture revision,
not limit increases. The old eleven-card exhaustive State/Quantizer refusal
remains unchanged, and small conditioned successes are intermediate evidence
toward a practical realistic heads-up NLHE solver, not the terminal objective.
