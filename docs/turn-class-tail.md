# Explicit fixed-game turn training on exact river classes

The research-only entry point solve_turn_class_tail in
[pokerlab/turn_class_tail_adapter.py](../pokerlab/turn_class_tail_adapter.py)
trains the fixed [three-hand full-deck turn game](turn-three-hand-physical-audit.md)
through its independently checked [seven river classes](turn-three-hand-classes.md).
It restores all physical policy rows before fresh full-physical diagnostics.
Ordinary solver APIs, kernels, resource limits and defaults are unchanged.

The API accepts only keyword arguments iterations, discard and resource_model.
All three are required. The only model name is turn-seven-class-vector-v1.
It has no configurable board, range, stack, action sizing or selected-river input.
For a bounded example:

    from pokerlab.turn_class_tail_adapter import solve_turn_class_tail
    result = solve_turn_class_tail(
        iterations=10, discard=3, resource_model="turn-seven-class-vector-v1")

This adds a computational representation for that exact finite game. It is not
a general range compressor, sampler, unrestricted Hold'em solver or convergence
guarantee. The [saved T750 target miss](turn-three-hand-direct-tail-experiment.md)
and all preceding reports remain immutable.

## Same physical game, different training representation

The turn board is Js8d4c2h. OOP holds AsAh:0.5,KsKh:1,QsQh:0.75;
IP holds AcAd:1,KcKd:0.75,QcQd:0.5. Both streets use pot100, stack220,
a half-pot opening, half-pot raise, one raise and no additional all-in size.
Every compatible private pair retains all44 legal rivers:9 pairs,396 worlds
and48 globally reachable public river cards. Future cards are hidden until
revealed; responses aggregate hidden opponent hands before choosing an action.

A neutral class contains36 cards. Six two-card classes are Ac/Ad, Ah/As,
Kc/Kd, Kh/Ks, Qc/Qd and Qh/Qs. Each private pair supports five complete classes.
The45 training worlds use exact original pair mass times class multiplicity/44,
converted once to binary64. This is full-deck marginalization, not conditioning
on seven selected cards. The adapter checks all396 physical signs and masses,
then stream-compares every original public branch, action and terminal refund
against its class image. Representative labels remain internal.

| Dimension | Original physical tree | Training classes |
| --- | ---: | ---: |
| Worlds |396|45|
| Public states |3039|456|
| Decisions |1254|188|
| Terminals |1780|263|
| Chance nodes |5|5|
| Policy rows |3606|486|
| Action slots |8046|1086|
| Prefix/private-pair edges |405|54|
| Depth |9|9|

The unchanged direct-tail helper performs both alternating regret updates on
every requested sweep. Only averaging discards the first D sweeps; retained
averages use original sweep weights D+1 through T. Own reach is unchanged by
the class map. At a river class with multiplicity m, raw counterfactual regrets
and own-hand joint-marginal average numerators scale by m; normalized behavioral
policies have scale1. Turn updates integrate all future classes with scale1.

An independent Fraction first-sweep test reconstructs both player half-steps
without production trainers, trees or regret evaluators. It checks all1803
physical versus243 class regret rows per player, exact regret scaling, rematched
policies and all3606 post-sweep own-reach average rows. Real T10/D0 and T10/D3
controls separately compare every physical action and original joint-weighted
own-action realization against the existing full-physical tail API, with a fixed
1e-9 tolerance. Binary64 summation order can differ; bitwise equality is not
required. Small controls are implementation evidence, not equilibrium quality.

## Full-request admission

The [pure planner](../pokerlab/turn_class_vector_budget.py) imports no poker or
ranking code. It rejects before enumeration or allocation when any requirement
exceeds its independently stored literal ceiling. Every logical storage
requirement is reserved upfront; bounded mappings enforce both tree shapes
before individual node construction. The metadata distinguishes modeled
reservations from the adapter's observed billed source cells.

The ordinary physical candidate-pair and world-iteration limits remain3million,
and original tree, prefix and information/action caps remain enforced. Class
training has additional unchanged30million world/dense proxies and a separate,
explicit500million complete modeled vector-work ceiling. The old physical30million
training proxy is reported as an informational comparison and is not the new
representation's admission rule. The ordinary API still rejects T790.

Full training reserves6288+75159*T logical source units, independent of discard.
An additional2000000 reserve covers preparation, lifting, full physical diagnostics
and accounting. Its fixed source components total1970224:

| Fixed component | Modeled source units |
| --- | ---: |
| Input checks |9066|
| Physical enumeration and rank preparation |104312|
| Tree counter mapping |18925|
| Other tree construction |109830|
| Tree scans |20966|
| Complete physical/class tree comparison |45459|
| Exact class validation and construction |28435|
| Information/metadata layout |50297|
| Header/configuration/ledger fields |4096|
| Accounting helper and bounded-counter overhead |754090|
| Legal prefix layouts |3969|
| Validation and aggregation |24150|
| Full physical policy lift |295257|
| Full physical numeric diagnostics |501372|

The class partition term bounds the fixed support loops and temporary collections;
the label tuple contributes63 cumulative fields. The information-layout bound
counts histories, sorted legal-hand lists, row keys and both maps. The lift bound
is30*3606+5*18105+12*8046, conservatively treating every row as five-card and
every action as a wager helper. Separate named requirements cover construction
and coexistence of raw/normalized worlds, class support maps and temporary sets,
all metadata/key/history fields, training maps and recursion vectors, and the
full output plus diagnostic normalization copy. These are per-structure logical
slot ceilings, not a sum claimed to bound allocated bytes or RSS. JSON encoding
and disk publication belong to the separate experiment, outside this API model.

For T6000/D2000 the planner forecasts54000 candidate-pair iterations,
2376000 physical-world iterations,25920000 class world-proxy units,
24628104 dense-proxy units and452960288 complete vector units. These are
admission arithmetic, not evidence that a T6000 call or accuracy experiment ran.
A future frozen experiment must preserve every miss and independently replay the
complete lifted policy before any accuracy or performance claim.

## Verification and output boundaries

The result has version research-turn-seven-class-tail-adapter-v1, the established
physical row schema, both physical/training dimensions, full-deck runouts,
original-weight schedule, requested work and local accounting ledgers. Fresh
physical diagnostics provide value and both legal response gains; NashConv is
their sum and exploitability is half that sum. Numeric values are not an exact
equilibrium certificate.

Focused checks cover source-derived bills, every one-slot storage rejection,
nonvacuous fixed ceilings, corrupted world mass/sign/support, terminal mismatches,
missing or nonfinite policy rows, actual276 rank calls, all8046 actions and
independent physical plus both exact class traversal modes. Run:

    python -B -m unittest discover -s tests -p "test_turn_class*.py" -v
    python -B -O -m unittest discover -s tests -p "test_turn_class*.py" -v
    python -m scripts.validate_docs

The [fixed T6000/D2000 experiment](turn-class-tail-T6000-experiment.md)
completed its [preregistered protocol](turn-class-tail-T6000-experiment-spec.md).
Its untouched lifted policy met the unchanged 1/1000-chip exact NashConv target
at approximately 0.00003025771156. All eight full-physical exact metrics agree
with both class traversal modes and numeric replay. The saved T750 miss remains
unchanged. This result applies to the fixed three-hand game and saved policy;
it does not establish a separately known exact game value or broader convergence.

Executed local checks passed:30 focused tests in47.797 seconds (normal) and
37.497 seconds (optimized), plus27 existing tail/three-hand regressions in
118.302 seconds. The final literal-model guard and provenance clarification
passed24 focused admission/corruption tests in each mode. Documentation
validation passed for157 Markdown files and814 local links. These checks
introduce no longer-budget quality or performance result.
