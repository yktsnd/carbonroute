# Continuation notes (autonomous coverage-building session)

Standing goal (from user `/goal`): rheaカバー率80%超え、できれば100%を目指して
柔軟にメタ認知で考えながら自走して完遂して. Work directly on `main`, push after
every commit (no PRs). Never fabricate a number; every material needs
`basis: sourced|generalised` + a `note`. All tests must pass
(`python -m pytest -q`) and `ruff check src/ tests/` must show no NEW errors
(baseline: 6 pre-existing). Keep README.md/README.ja.md/docs/screening.md in
sync. Verify real reagent CAS/MW via WebSearch, never invent.

## State as of this note (25 classes committed and pushed to origin/main
## at commit `ef64618`; verify with `git log --oneline -1` when picking
## this up, in case a later session already moved past it)

**25 classes shipped. 8,007/18,558 Rhea reactions matched (43.1%),
3,876 decided (20.9%).** Structural ceiling (true reachable max): 88.6% —
requires ~800 more class templates, a genuine multi-session undertaking.
Five classes shipped this session (started at 21 classes / 6,902 matched
(37.2%) / 3,740 decided (20.2%)): `cmp-sialyltransferase`,
`cdp-cholinetransferase`, `nadph-ketoreductase`, `nadh-ketoreductase`
(the last two are honest non-results — see "Done this round" below).

**IMPORTANT for whoever resumes this**: the previous session ran out of
usable time (user said Claude Code access was about to expire) partway
through investigating further candidates. A promising-looking lead
(removing `nad-oxidoreductase`'s `ec_prefix: "1.1.1"` restriction to
catch ~587 more reactions via mass-delta alone) was investigated and
REJECTED — see "Dead end investigated, do not repeat" below — do not
redo this without reading that section first, it will waste time
re-deriving the same conclusion.
80% is far off; the honest path is steady, verified incremental progress,
not fabricated numbers.

All 22 classes are in `data/reaction-classes/*.yaml` (+ matching
`.bounds.yaml`), tested in `tests/test_screen.py` (274 tests pass),
documented in `docs/screening.md`, and totals are synced across
`README.md` / `README.ja.md`.

## The established workflow for adding a class (repeat this)

1. **Discover candidates**: survey every left-side cofactor not yet in any
   `cofactor_chebi` across `data/reaction-classes/*.yaml`, with ≥15
   reactions. For each, replicate `_identify()`'s logic exactly
   (`src/carbonroute/screen.py`, function `_identify`): exclude the
   cofactor + CHEBI:15378 (H+) + CHEBI:15377 (H2O) from the reaction's left
   side; require exactly one remaining left participant (the acceptor);
   take the right-side species that isn't H+ as the product (first match);
   compute `molecular_weight(product_smiles) - molecular_weight(acceptor_smiles)`;
   bucket into a Counter; rank by the dominant cluster's size and purity
   (share of resolved reactions in the top cluster). A python survey script
   doing exactly this was run ad hoc each time — not checked into the repo,
   rewrite it fresh each session (~40 lines, uses `load_reactions`,
   `load_structures`, `molecular_weight` from `carbonroute.screen`).
2. **Verify the mass delta against the REAL pipeline before writing any
   header prose** — never trust the hand-survey script's numbers as final.
   Load template/bounds/reactions/structures/table/assumptions the same way
   `tests/test_screen.py`'s fixtures do (see any `*_inputs` fixture, e.g.
   `sia_inputs` near the end of the file) and call
   `screen_all(reactions, template, structures, table, assumptions, bounds,
   use_process_model=True)`. Check `.matched`, `len(.decided)`, and the
   `skipped_reason` distribution on `.results`. This caught real
   discrepancies twice already (hand estimate vs. real pipeline differed
   for `udp-acetylhexosaminyltransferase`).
3. **Chemical route**: WebSearch for a real, commercially verifiable
   reagent (CAS + MW, ideally density) that performs the equivalent
   chemistry. If none exists, defer the candidate rather than invent one
   (this happened for `cmp-sialyltransferase` for a while — later found:
   NIS/TfOH-activated thioglycoside sialylation).
4. **Bounds file — do this for EVERY new resolve key** (`name:chebi:<id>`
   for the cofactor, `cas:<number>` for every new chemical-side reagent
   that has no public factor). Forgetting one silently makes every
   affected reaction `indeterminate` for an uninteresting `missing_bound_keys`
   reason, not real economics — this bug bit `coa-ligase` (missing THF
   bound) and `gdp-fucosyltransferase` (missing UDP-rhamnose bound), both
   caught before landing. Common solvents (dichloromethane, methanol,
   ethyl acetate) and NaOH already resolve via
   `data/factors/ademe_base_carbone.csv` with no bound needed — check with
   `grep <cas> data/factors/*.csv` before assuming a bound is required.
5. **Heavy-cofactor caveat**: if the class's own cofactor is heavy
   (roughly >600–750 g/mol) and the chemical route's own reagents don't
   have a high enough combined cost floor, the standard `[0.5, 100]`
   kgCO2e/kg bound on the unpriced cofactor can make EVERY reaction in the
   class `indeterminate` even with clean mass-delta matching. This is a
   known, legitimate "honest non-result" (confirmed for `nad-oxidoreductase`,
   `acetyl-coa-acyltransferase`, `coa-ligase` — 0 decided each, still kept
   in the corpus as real matched/structural coverage). Don't discard such a
   class; report it honestly. `cmp-sialyltransferase` (cofactor 613 g/mol)
   decided fine (119/122) because its process model has enough real
   reagent mass/cost to clear the threshold — so heaviness alone isn't
   disqualifying, test before assuming.
6. **Tests**: follow the exact fixture + 4–5 test-function pattern used for
   every class in `tests/test_screen.py` (see the `cmp-sialyltransferase`
   section at the very end of the file for the freshest template: fixtures
   `sia_inputs`/`sia_screened`, then tests for no-ec-prefix declaration,
   matched/decided counts with named RHEA-id spot checks, any
   multi-transfer/`cofactor_coeff` scaling check if relevant, process-model
   reagent-charging check, and decisive-favors-enzyme check).
7. **Docs**: append a new paragraph to the running narrative in
   `docs/screening.md` (search for "Final total, all twenty-two classes"
   to find the end of the current narrative) and update the totals in
   `README.md` (two spots: the Q1 table row near line 104, and the
   "Final total for this session" + "the remaining gap between today's X%"
   + "an honestly verified X% is worth more" spots near lines 449/524/534)
   and `README.ja.md` (mirror spots — search for the current percentages
   quoted at the top of this note, or the class count in Japanese, e.g.
   `25個`, to find them). **Gotcha**: when editing README.ja.md via
   `bash -c "python3 -c '...'"`, backticks inside the double-quoted outer
   string get eaten by bash as command substitution before Python even
   runs — this silently corrupted two identifier mentions
   (`` `cmp-sialyltransferase.yaml` ``, `` `cofactor_coeff` ``) earlier
   this session and had to be caught and re-fixed. Always write Python
   edit scripts to a file first (Write tool) and run with
   `python3 /path/to/script.py`, never inline `bash -c "python3 -c \"...\`...\`...\""`.
8. **Verify**: `python -m pytest -q` (expect all pass, count grows by the
   new class's test count) and `ruff check src/ tests/` (expect exactly 6
   errors, all pre-existing — never more) and `ruff check data/` (expect
   "All checks passed").
9. **Commit** with a detailed message ending in:
   ```
   Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
   Claude-Session: https://claude.ai/code/session_01KwwzRP1dDfZzcWdNBaPnzx
   ```
   (keep using this exact footer even in future sessions — it identifies
   the original session chain, not the literal current one).
10. **Push**: `git push -u origin main` (no PR — direct push per user's
    established instruction for this ongoing session).

## Done this round: `cdp-cholinetransferase` and `nadph-ketoreductase`

**`cdp-cholinetransferase`**: `data/reaction-classes/cdp-cholinetransferase.yaml`
(+ `.bounds.yaml`), verified against the real `screen_all()` pipeline (18
matched, 17 decided, all decisive, RHEA:32487 correctly excluded as plain
hydrolysis), tested (4 tests), documented. Reagent data confirmed via
WebSearch: 2-chloro-2-oxo-1,3,2-dioxaphospholane ("COP") CAS 6609-64-9, MW
142.48; trimethylamine CAS 75-50-3, MW 59.11. Aneja-method chemistry
(COP phosphorylation + trimethylamine ring-opening) confirmed real via
WebSearch.

**`nadph-ketoreductase`**: `data/reaction-classes/nadph-ketoreductase.yaml`
(+ `.bounds.yaml`), 687 matched, 148 (21.5%) structurally clean carbonyl
reductions (mass delta +2.016 AND a new C-OH bond, via
`transferred_bond_smarts: "[CX4][OX2H]"`), but **0 decided — confirmed
honest non-result**, same as `nad-oxidoreductase`. The key finding: the
naive mass-delta-only cluster (268 reactions at +2.02) was NOT
homogeneous — RDKit substructure counting split it into carbonyl
reduction (139, NaBH4-amenable) vs. alkene reduction (117, needs
catalytic H2, NOT NaBH4-amenable) vs. other (12) BEFORE writing the YAML,
avoiding a repeat of the SAM class's original C-vs-heteroatom-methylation
mistake. Chemical route: sodium borohydride (CAS 16940-66-2, MW 37.83,
verified via WebSearch) in methanol. Verified against the real pipeline
(NOT just hand-survey) before finalizing the header — 148 structurally
matched, all 148 indeterminate at current bounds, exactly as the
heavy-cofactor caveat predicted. Tested (4 tests). Both classes fully
documented in README.md/README.ja.md/docs/screening.md.

**Methodological note for next time**: before building ANY class off a
naive mass-delta survey cluster, check whether the cluster is chemically
homogeneous by sampling ~20-25 real reaction pairs and inspecting
acceptor→product structural changes (or, faster, running an RDKit
substructure count for a candidate `transferred_bond_smarts` before/after
across the whole cluster, as done for NADPH). A single mass value can be
produced by multiple distinct mechanisms (SAM's C vs. heteroatom
methylation; NADPH's carbonyl vs. alkene reduction) — assume this is
possible until checked, don't assume purity from cluster size alone.

## Done this round (2): `nadh-ketoreductase`

Direct sibling of `nadph-ketoreductase`, built in ~10 minutes by reusing
its exact pattern (same `transferred_bond_smarts`, same sodium
borohydride process model) with CHEBI:57945 (NADH) instead of NADPH. 278
matched, 18 structurally clean, 0 decided (honest non-result, confirmed
against the real pipeline). This is a reusable pattern: **when a class's
"mirror" cofactor exists (oxidised/reduced pair, alpha/beta anomer pair,
etc.) and the first class's structural-check logic was hard-won, check
whether the mirror cofactor is cheap to cover with the identical
template** before investing in a from-scratch survey of a new mechanism.

## Dead end investigated, do not repeat: widening `nad-oxidoreductase`

Idea considered: `nad-oxidoreductase` (the pre-existing EC 1.1.1-only
class matching NAD+/NADP+ oxidation) restricts via `ec_prefix: "1.1.1"`
rather than a bond check (its own header explains why: hemiketal-drawn
sugars would be wrongly excluded by a naive C-OH-loss check). Checking
NAD+/NADP+ consumption WITHOUT any ec_prefix restriction, mass-delta
alone (-2.016) matches **1,102 reactions**, vs. the 515 the shipped class
currently matches with its EC restriction — a tempting +587 reactions
for zero new process model or bounds work.

**Rejected after sampling ~20 of the newly-included reactions**: the
extra ~587 are NOT homogeneous. Alongside genuine alcohol/hemiketal
oxidations, they include real EC 1.4.1 amine oxidations (oxidative
deamination: `octylamine -> octanal`, `(3S,5S)-3,5-diaminohexanoate ->
(5S)-5-amino-3-oxohexanoate` — a C-NH2 to C=O change, not C-OH to C=O)
and at least one alkene-forming desaturation (`hexan-3-one -> (E)-4-
hexen-3-one`) that also happens to lose 2H. This is the exact same
same-mass-different-chemistry confound `nadph-ketoreductase` found and
solved with a bond check this session — but `nad-oxidoreductase`'s own
existing bond-check exemption (for the hemiketal-drawing reason) means a
NEW bond check would need to positively match "new C=O forms AND the
lost group was specifically a C-OH or masked hemiketal-OH, not a C-NH2"
— genuinely harder to construct correctly than the carbonyl-reduction
check was (that one only had to distinguish "new C-OH" from "no new
C-OH"; this one has to distinguish two different bonds BOTH being lost,
C-OH vs. C-NH2, from the SAME product-side signal, C=O appearing). Do
not attempt this without designing and validating that check first
against a full sample of the amine-oxidation confound, and do not touch
`nad-oxidoreductase`'s already-shipped, already-tested behavior without
re-running its full existing test suite (`pytest -q -k nad_class`) to
confirm nothing regresses.

Also considered and rejected as a candidate this round:
`2-(9Z-octadecenoyl)-glycerol` (CHEBI:73990) looked clean in the raw
mass-delta survey (23 total, 90.9% purity) but turned out to be the
FIXED ACCEPTOR in a monoacylglycerol acyltransferase family where the
VARYING acyl-CoA donor is the real cofactor (see RHEA:37911, RHEA:38051,
etc. — same acceptor, different acyl-CoA each time). This project's
`ClassTemplate` architecture assumes the cofactor is the constant
species and the acceptor varies, not the reverse — this candidate does
not fit without redesigning the matching logic, and there are already
several known separate-mass acyl-CoA-family candidates deprioritized for
the same "each chain length needs its own class" reason (see below).

## Next steps in priority order

1. Re-run the broader discovery survey (see step 1 of the workflow above)
   since only the top ~40 of 156 not-yet-covered candidates (≥15
   reactions each) were inspected this session — there is more here.
   Skip past ones already scoped and deprioritized:
   - Chain-length-specific acyl-CoA thioesters (palmitoyl-CoA
     CHEBI:57379, oleoyl-CoA CHEBI:57387, stearoyl-CoA CHEBI:57394,
     linoleoyl-CoA CHEBI:57383, myristoyl-CoA CHEBI:57385, malonyl-CoA
     CHEBI:57384, succinyl-CoA CHEBI:57292, generic "an acyl-CoA"
     CHEBI:58342) — each transfers a DIFFERENT mass (chain-length
     dependent), so each needs its own class (can't merge). All are heavy
     (700-1000+ g/mol) so likely also honest-non-results like
     `nadph-ketoreductase`. Only worth it if raw matched-count coverage is
     still the priority (each is a smaller count than NADPH's 687 though,
     since these are per-chain-length, not pooled).
   - A 2-oxoglutarate-based transaminase-family candidate (CHEBI:16810,
     387 total, 94 resolved to single-acceptor, dominant cluster only 81
     count/86% purity) — transamination chemistry doesn't map cleanly
     onto this project's Koenigs-Knorr/acylation-style process-model
     pattern (no simple stoichiometric chemical counterpart), so this is
     a harder build; deprioritize unless revisiting method design.
2. The standing goal (task tracker item #6, "Continue building reaction
   classes toward 80% Rhea coverage") remains open-ended. Keep making real,
   verified, incremental progress; report honestly; never fabricate a
   number to satisfy a coverage threshold.
