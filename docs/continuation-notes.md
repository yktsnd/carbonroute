# Continuation notes (autonomous coverage-building session)

Standing goal (from user `/goal`): rheaカバー率80%超え、できれば100%を目指して
柔軟にメタ認知で考えながら自走して完遂して. Work directly on `main`, push after
every commit (no PRs). Never fabricate a number; every material needs
`basis: sourced|generalised` + a `note`. All tests must pass
(`python -m pytest -q`) and `ruff check src/ tests/` must show no NEW errors
(baseline: 6 pre-existing). Keep README.md/README.ja.md/docs/screening.md in
sync. Verify real reagent CAS/MW via WebSearch, never invent.

## State as of this note (24 classes committed; check `git log --oneline -1`
## to confirm what's actually pushed when you pick this up)

**24 classes shipped. 7,729/18,558 Rhea reactions matched (41.6%),
3,876 decided (20.9%).** Structural ceiling (true reachable max): 88.6% —
requires ~800 more class templates, a genuine multi-session undertaking.
`cdp-cholinetransferase` (CDP-choline-dependent phosphocholine transfer,
18 matched/17 decided) and `nadph-ketoreductase` (NADPH-dependent carbonyl
reduction, 687 matched/0 decided — an honest non-result, same pattern as
`nad-oxidoreductase`) both shipped this round. See "Done this round" below
for details, and skip straight to "Next steps" for what comes after.
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
   `23個`, to find them). **Gotcha**: when editing README.ja.md via
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
