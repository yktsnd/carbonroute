# Continuation notes (autonomous coverage-building session)

Standing goal (from user `/goal`): rheaカバー率80%超え、できれば100%を目指して
柔軟にメタ認知で考えながら自走して完遂して. Work directly on `main`, push after
every commit (no PRs). Never fabricate a number; every material needs
`basis: sourced|generalised` + a `note`. All tests must pass
(`python -m pytest -q`) and `ruff check src/ tests/` must show no NEW errors
(baseline: 6 pre-existing). Keep README.md/README.ja.md/docs/screening.md in
sync. Verify real reagent CAS/MW via WebSearch, never invent.

## State as of this note (commit 4ea6fa8, pushed to origin/main)

**22 classes shipped. 7,024/18,558 Rhea reactions matched (37.8%),
3,859 decided (20.8%).** Structural ceiling (true reachable max): 88.6% —
requires ~800 more class templates, a genuine multi-session undertaking.
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
   and `README.ja.md` (mirror spots — search for `37.8%` / `20.8%` /
   `22個` to find them). **Gotcha**: when editing README.ja.md via
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

## In-flight when this note was written

A background WebSearch agent was verifying real reagent data for the next
candidate class, **`cdp-choline` / phosphocholine transferase**
(CHEBI:58779, EC 2.7.8.2 family — CDP-choline-dependent phosphocholine
transfer onto diacylglycerol/ceramide/protein-serine acceptors, forming
phosphatidylcholine/sphingomyelin/protein phosphocholination). Already
verified against the real pipeline logic (by hand, matching `_identify`
exactly — NOT yet run through the actual `screen_all()`, do that first
per step 2 above): **18 reactions consume CDP-choline; 17 resolve to a
single acceptor/product pair, ALL 17 landing on an exact, clean
165.129 g/mol delta (the phosphocholine group)** — RHEA:16273, RHEA:21224,
RHEA:32939, RHEA:36179, RHEA:36183, RHEA:36227, RHEA:44288, RHEA:54232,
RHEA:54236, RHEA:54240, RHEA:54244, RHEA:54332, RHEA:54336, RHEA:54344,
RHEA:54348, RHEA:54352, RHEA:56080 (the last is protein Rab1 serine
phosphocholination — a genuine class member, same clean delta, not an
outlier). The only exclusion: RHEA:32487 (CDP-choline + H2O = phosphocholine
+ CMP + 2H+ — plain hydrolysis, no organic acceptor, correctly excluded by
the `_identify` logic since `others_left` is empty).

The chemical-route research (in progress when interrupted): the real,
published "Aneja's method" for synthetic phosphatidylcholine — react a
1,2-diacylglycerol with 2-chloro-2-oxo-1,3,2-dioxaphospholane (a cyclic
chlorophosphate) + a tertiary amine base (likely triethylamine, CAS
121-44-8) to form a cyclic phosphotriester, then ring-open with
trimethylamine to install the choline headgroup. **UNVERIFIED numbers
from a prior session that MUST be re-confirmed via WebSearch before use**:
2-chloro-2-oxo-1,3,2-dioxaphospholane CAS 6609-64-9 (MW/formula not yet
confirmed); trimethylamine CAS 75-50-3, MW ~59.11 (not yet confirmed this
session). **Do not write the YAML file until these are confirmed** — check
if the background agent (if this session is still alive) already returned
a result; if not, or if starting fresh, redo the WebSearch.

## Next steps in priority order

1. Finish `cdp-choline` class (small, ~18 reactions, but clean and already
   scoped — quick win). Steps: confirm reagent CAS/MW via WebSearch →
   write YAML + bounds.yaml → verify against real `screen_all()` → write
   tests → update docs/README → test+lint → commit → push.
2. **Bigger opportunity found but NOT yet built**: NADPH-dependent
   reduction (CHEBI:57783). Hand-survey found **687 total reactions
   consume NADPH; 348 resolve to a single acceptor/product pair; the
   dominant cluster (268 reactions, 77% purity) lands at delta ≈ +2.00**
   (a straightforward hydride reduction, mirroring the already-shipped
   `nad-oxidoreductase` class's oxidative -2.00 in reverse). This is the
   single largest remaining candidate by raw count found in this session's
   survey — potentially worth ~268 more matched reactions (would push
   matched% from 37.8% toward ~39.2% alone). Caveats before building:
   - NADPH itself is heavy (~745 g/mol, same weight class as
     `nad-oxidoreductase`'s NAD+/NADP+, which decided 0/515 — see the
     heavy-cofactor caveat in step 5 above). This class will very likely
     also be an "honest non-result" (0 or few decided) — expected and
     fine per project convention, but set that expectation before
     building, and say so plainly in the YAML header.
   - The chemical counterpart is a stoichiometric hydride reducing agent
     (NaBH4, CAS 16940-66-2, or similar — well-known, easy to verify) —
     should be a quick, low-risk process_model to write.
   - **Purity is only 77%**, not 90%+ like the cleanest classes — inspect
     what the other ~23% of the top-cluster-eligible reactions actually
     are before finalizing (some early example equations already pulled:
     many are electron-transfer/quinone/cytochrome reductions, e.g.
     `RHEA:11692 NAD(+) + NADPH = NADH + NADP(+)` — a transhydrogenase,
     probably NOT a real "reduce an organic acceptor" class member and
     needs excluding or handling; inspect the full delta distribution and
     what's NOT in the +2.00 cluster before writing the header's
     "structural verification" numbers).
   - Also present in the same survey but not yet investigated: several
     large families of chain-length-specific acyl-CoA thioesters
     (palmitoyl-CoA CHEBI:57379, oleoyl-CoA CHEBI:57387, stearoyl-CoA
     CHEBI:57394, linoleoyl-CoA CHEBI:57383, myristoyl-CoA CHEBI:57385,
     malonyl-CoA CHEBI:57384, succinyl-CoA CHEBI:57292, generic "an
     acyl-CoA" CHEBI:58342) — each transfers a DIFFERENT mass (chain-length
     dependent), so each would need its own class (can't merge, unlike the
     UDP-sugar donors which share identical masses). All are heavy
     (700–1000+ g/mol) so likely also honest-non-results. Lower priority
     than NADPH; only worth it if NADPH pans out and the goal is still
     raw matched-count coverage.
   - A 2-oxoglutarate-based transaminase-family candidate (CHEBI:16810,
     387 total, 94 resolved to single-acceptor, dominant cluster only 81
     count/86% purity) was also seen but NOT investigated — transamination
     chemistry doesn't map cleanly onto this project's Koenigs-Knorr/
     acylation-style process-model pattern (no simple stoichiometric
     chemical counterpart), so this is a harder build; deprioritize unless
     revisiting method design.
3. After NADPH (or instead of, if it turns out low-value), re-run the
   broader discovery survey (see step 1 of the workflow above) since only
   the top ~40 of 156 not-yet-covered candidates (≥15 reactions each) were
   inspected this session — there is more here.
4. The standing goal (task tracker item #6, "Continue building reaction
   classes toward 80% Rhea coverage") remains open-ended. Keep making real,
   verified, incremental progress; report honestly; never fabricate a
   number to satisfy a coverage threshold.
