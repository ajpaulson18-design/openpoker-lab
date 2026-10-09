# Espresso interface boundary

The [approved image](design/openpoker-blueprint.png) is the visual blueprint, not inspiration for a redesign: a brown lounge shell, green oval felt and amber rail, with play on the left, strategy on the right, and an educational coach below. The existing standard-library server, APIs and calculation modules remain unchanged. This branch was isolated from `main`; concurrent postflop work in PR #55 is outside its scope.

## Components and contracts

- `index.html`: semantic shell, table setup/actions, native collapsible analysis, coach and existing research tabs. Existing IDs and form names are preserved.
- `style.css` and `names.css`: palette, layout, felt, seats, cards, matrix, responsive styling. No calculation lives in CSS.
- `app.js`: existing request, revision and evidence checks remain authoritative. Pure presentation adapters are enclosed in a marked block for direct testing. Renderers consume those adapters without changing responses.
- Table consumes the existing visible game response: `id`, `revision`, `street`, `board`, `hands` (hidden opponents remain null), `names`, `stacks`, `committed`, `street_bets`, `folded`, `button`, `actor`, `legal`, settlement and history. Chips remain chips; no invented big-blind conversion or positional assignment.
- Matrix consumes the existing fixed-bet `/api/solve` response and captured request board. Four separate decision nodes: OOP opening bet/check, OOP call/fold after checking, IP bet/check after check, IP call/fold facing a bet. Different nodes are never combined into a fabricated three-action policy. Unsupported response shapes fail closed.
- Each class cell averages the **returned physical combinations equally for visual inspection only**. This is not a range-weighted action total. Unreturned hands stay neutral. Selecting a cell exposes each returned combination's unmodified numeric probability. Smooth color blending changes no frequencies. The original solver report preserves aggregate values, gap, scope, locks and unreachable-node caveats. Per-hand EV is unavailable in this endpoint and is labeled as such.
- The matrix is independent river research and explicitly identifies its board/node. It is never advertised as a solution of the practice hand. Practice coaching retains its own immutable preview/decision bindings and simplified-model limitations.

No demonstration strategy, EV or coaching data is shipped. The initial table and matrix are empty until the user requests real computation. AI stays downstream of validated evidence; external-AI opt-in remains unchanged.

The raise slider and exact numeric input share the existing legal min/max and street-total amount. Only the available check or call action is shown. Dealer markers come from the real button index; descriptive positions are not inferred. Table setup and coach voice remain accessible through native disclosure controls. The analysis disclosure retains a visible reopening affordance when collapsed.

## Validation

Run `node scripts/test_frontend.cjs`, `node --check pokerlab/web/app.js`, and `python -m unittest discover -s tests -v`. Browser review must cover dealing, actions, current-study and local educational coaching, solving, exact-combination inspection, analysis collapse, mobile overflow, hidden opponents, keyboard access and CSP/errors. The screenshot reference has a dense full-range three-action matrix; the current API exposes compact fixed-bet binary nodes, so its real matrix can be sparse. Filling missing cells with plausible colors would misrepresent the solver.

Verified on this branch: 312 existing Python tests and 8 frontend contract checks passed; browser inspection covered real six-seat dealing, check/call controls, preview invalidation after an action, local educational answers, a genuine 2,000-iteration river solve, exact-combination frequencies, collapse/reopen, desktop reference width and narrow-screen layout. The first sandbox run encountered Windows temporary-directory ACL errors; the same suite passed outside that sandbox. No card-evaluation logic changed, so exhaustive evaluator enumeration was not rerun.

Remaining visual/data differences: the reference's 100bb scenario and SB/UTG labels are not hard-coded into practice; the API uses chips and explicit seats. Sparse returned ranges cannot produce the reference's fully populated matrix. Per-hand solver EVs are absent and stay unavailable. The compact coach expands when the user requests detailed evidence. CSS approximates the felt texture and lighting; this is not a claim of pixel-identical rendering. Retain the approved image for future fidelity reviews as real data capabilities evolve.
