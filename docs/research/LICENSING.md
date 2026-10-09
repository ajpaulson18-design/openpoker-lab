# Dependency, tooling and licensing record

Baseline: [pyproject.toml](../../pyproject.toml) declares no runtime dependencies,
Python >=3.11 and setuptools >=68 as the build requirement. Python standard
library, plain JavaScript/HTML/CSS and SQLite through the standard library form
the application. Build/dev/CI services are not runtime dependencies.
[LICENSE](../../LICENSE) is MIT with contributor copyright; it permits commercial
use subject to its included notice conditions. This audit does not change license,
repository visibility, ownership or distribution terms.

## Existing external research

Canonical source/provenance notes: [solver research](../solver-research.md),
[turn research](../turn-research-notes.md), [postflop research](../postflop-research.md),
and [public-batched implementation](../public-batched-cfr.md). These record
conceptual references and dated observations, not newly verified current third-party
license facts. Do not repeat historical patent/licensing observations as current
clearance. No third-party implementation is imported by this documentation change.

## Audit before specialized implementation or reuse

Record capability needed; tools/libraries evaluated; technical fit; pinned source
and version; exact license/notice obligations; commercial distribution implications;
provenance of any copied code, asset, data or trained output; and why reuse or an
independent implementation was selected. Recheck actual component files rather
than relying on a README or a prior date's public license observation.

General ideas and independently implemented published methods differ from
reusable code and assets. Studying proprietary products does not authorize copying
their implementations or interfaces. Owner preference for unobtrusive attribution
cannot remove mandatory notices. Do not claim patent clearance, solver ownership
of third-party work, or commercial permission without supporting evidence.

Do not commit secrets, personal opponent records, private hand notes, proprietary
solver output or copied commercial interfaces. Optional external coaching is
opt-in and allowlisted; [setup](../ai-coach-setup.md) explains its data boundary.
GitHub workflows have separate provider/compiler/cost configuration; preserve
existing guardrails and do not assume that a configured service is usable.
