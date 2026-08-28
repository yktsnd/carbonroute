# Reproducibility: the non-API route

## Two different claims, easy to conflate

**Claim 1: `carbonroute` itself never touches a network.** `validate`,
`resolve`, `coverage`, `compare`, `lock` and `bootstrap` read only local YAML
and CSV files. This is not a policy statement to be trusted — it is enforced
by `tests/test_cli.py::test_no_networking_code_is_reachable`, which parses the
import graph of `src/carbonroute/` with `ast` and fails if any module so much
as imports `socket`, `urllib`, `http`, `requests`, or similar. If the external
services this page describes vanished entirely tomorrow, the tool would run
exactly as it does today, on whatever is already committed to `data/factors/`,
`data/synonyms/` and `benchmarks/`.

**Claim 2: the factor tables were built by scripts that used to require a
live network.** ADEME's API, PubChem's API, the ProBas/GEMIS node, and the
Federal LCA Commons API are all outside this project's control. Any of them
can be restructured, rate-limited, paywalled or retired. Before this document,
that would have meant the committed CSVs stood on their own but could never be
re-derived, checked, or extended without depending on services that might not
answer tomorrow. This page is about closing that gap.

## The mechanism

Every network call an ingestion script makes now goes through
`scripts/_snapshot.py`, a small shared cache with two modes:

- **live** (default): fetch each URL, and write the raw response into
  `data/raw/<source>/` before returning it. Every live run refreshes the
  snapshot to match what it just saw.
- **`--offline`**: touch no network at all. Read exclusively from
  `data/raw/<source>/`, populated by a previous live run. A URL that was
  never cached raises a clear error naming it — the script stops there rather
  than reaching for the network or fabricating an answer.

`data/raw/<source>/manifest.json` records, for every cached URL, the first
and most recent UTC timestamp it was fetched — the frozen snapshot's "as of"
point, readable without running anything:

```
PYTHONPATH=src python3 scripts/_snapshot.py
```

A 404 from a service like PubChem ("this name is not a compound") is a
meaningful answer, not a failure, so it is frozen and replayed too — an
`--offline` run reports exactly the same unresolved names as the live run
that produced the snapshot did.

An endpoint that embeds a credential (the Federal LCA Commons API takes an
`api_key` query parameter) is cached and reported under a redacted key —
`?api_key=REDACTED` — never the real one, so a personal API key is never at
risk of ending up in a commit.

## Which point in time each snapshot represents

| Source | Script | Snapshot directory | Status |
| --- | --- | --- | --- |
| ADEME Base Carbone | `scripts/ingest_ademe_basecarbone.py` | `data/raw/ademe_base_carbone/` | populated |
| ProBas / UBA-GEMIS | `scripts/ingest_probas_gemis.py` | `data/raw/probas_gemis/` | populated |
| PlasticsEurope / EPD International (published_pcf) | `scripts/ingest_published_pcf.py` | none — see below | N/A by design |
| PubChem (shared across scripts) | several | `data/raw/pubchem/` | populated |
| Letermovir SI CAS resolution | `scripts/extract_letermovir_ledger.py` | `data/raw/letermovir_cas_cache.json` | populated |
| US LCI Database | `scripts/ingest_uslci.py` | `data/raw/uslci/` | **not yet populated** — see below |

Run `python3 scripts/_snapshot.py` for the exact UTC window of each populated
snapshot; it changes every time a script is re-run live, so this table
deliberately does not hard-code timestamps that would go stale.

`published_pcf.csv` is different in kind: its GWP values are a declarative
table of citations baked directly into the script (publisher, document, page,
retrieval date), not fetched from an API — see its module docstring. `--offline`
on that script only gates two *re-verification* steps (a PubChem InChIKey
double-check, and an HTTP reachability probe of each citation URL), neither of
which can change the values themselves. There is nothing to freeze because the
values were never live-fetched in the first place.

## The letermovir benchmark's primary source is also committed

Unlike the API-fetched factor tables, `benchmarks/letermovir/ledger.yaml`'s
entire empirical basis is one small (224 KB) Excel workbook, confirmed
**CC BY** licensed via Europe PMC's own record metadata — an explicit
redistribution grant, not an assumption. It is committed at
`benchmarks/letermovir/source-material/`, and
`scripts/extract_letermovir_ledger.py` defaults to reading it from there, so:

```bash
PYTHONPATH=src python3 scripts/extract_letermovir_ledger.py --offline
```

with **no arguments and no network access at all** reproduces
`benchmarks/letermovir/ledger.yaml` byte-for-byte, using only files already in
this repository.

This is deliberately not the general policy for every citation in this
project. `data/processes/*.yaml` and `data/factors/published_pcf.csv` cite
BREFs, IPCC reports and PlasticsEurope/Nobian documents by stable URL rather
than embedding them, because most of those carry weaker or more ambiguous
redistribution terms ("free to download and use", "for reference/citation
use") than the letermovir paper's confirmed CC BY. Embedding a document here
is the exception, made only when the redistribution grant is as unambiguous
as this one.

## Known gap: USLCI

`scripts/ingest_uslci.py` was retrofitted identically to the others, but
populating `data/raw/uslci/` requires one successful live run against the
Federal LCA Commons API, and that hit api.data.gov's shared `DEMO_KEY` hourly
rate limit (10 requests/hour, shared by every anonymous caller worldwide)
mid-session. The already-committed `data/factors/uslci.csv` is unaffected —
this only means offline replay of the *ingestion script* isn't available yet
for this one source. Tracked in
[carbonroute#1](https://github.com/yktsnd/carbonroute/issues/1); see that
issue for how to resume (wait for the window to clear, or set a free personal
key via `USLCI_API_KEY`).

## Selecting a route

```bash
# Live: fetch current data, refresh the snapshot.
PYTHONPATH=src python3 scripts/ingest_ademe_basecarbone.py

# Offline: replay the exact frozen snapshot, no network at all.
PYTHONPATH=src python3 scripts/ingest_ademe_basecarbone.py --offline
```

Both write the same output file by default. In this project's own testing,
live and `--offline` runs of every populated source produced byte-identical
CSVs (aside from `retrieved_date`, which is stamped to the day the script
actually runs — the manifest's UTC timestamps are the authoritative "as of"
record when that distinction matters).

## Why this is a maintenance step, not a build step

Rebuilding a snapshot is a deliberate, occasional action — something a
maintainer does when adding a new substance or refreshing stale data — not
something that happens automatically on every commit or every `carbonroute`
invocation. The committed `data/factors/*.csv` files are what the tool
actually reads; the snapshot exists so that, months or years from now, the
path from "what did ADEME actually say" to "what is in this CSV" stays walkable
even if ADEME's API has moved on.
