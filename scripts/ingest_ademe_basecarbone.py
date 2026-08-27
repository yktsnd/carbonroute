"""Build an emission-factor table for bulk chemicals from ADEME Base Carbone(R).

SOURCE
------
ADEME Base Carbone(R), the French public LCA/emission-factor database
published by l'Agence de la transition ecologique (ADEME).

  Dataset landing page : https://data.ademe.fr/datasets/base-carboner
  Dataset API root     : https://data.ademe.fr/data-fair/api/v1/datasets/base-carboner

LICENSE
-------
"Licence Ouverte / Open Licence" (Etalab v2.0), as declared by the dataset's
own metadata (`license.title` / `license.href` on the dataset API root, see
`fetch_dataset_metadata()` below). This licence permits reuse, including
commercial reuse, with attribution. See:
https://www.etalab.gouv.fr/licence-ouverte-open-licence

RETRIEVAL PROCEDURE (all done live by this script, nothing hard-coded)
-----------------------------------------------------------------------
1. Fetch the dataset metadata (title, license, version) from the API root.
2. Fetch the row set for a fixed, hand-picked list of `Code_de_la_catégorie`
   values inside the "Achats de biens > Plastiques et produits chimiques >
   Produits chimiques" branch (see CATEGORIES below), using
   `.../lines?Code_de_la_catégorie_eq=<category>&size=<n>`.
3. Keep only rows where `Type_Ligne == "Elément"`,
   `Type_de_l'élément == "Facteur d'émission"`, and the unit is a per-mass
   unit (kgCO2e/kg or kgCO2e/ton). Convert kgCO2e/ton to kgCO2e/kg by
   dividing by 1000 (recorded in `notes`).
4. For every surviving row, resolve the substance name to PubChem (CID ->
   InChIKey/synonyms), take the first CAS-shaped synonym, and verify its
   check digit with `carbonroute.schema.cas_checksum_ok`. Rows that don't
   resolve to exactly one CID, or whose CAS candidate fails the check
   digit, are dropped and reported.
5. Rows naming a mixture, a graded/diluted commercial solution (e.g. "Acide
   nitrique 50%"), or a vague generic term (e.g. "Alcool") are dropped
   without ever querying PubChem for them, because assigning such a value
   to a pure substance's CAS would misrepresent it -- see REJECTED list
   below and the .SOURCES.md file for the full reasoning.
6. `gsd` is derived from ADEME's `Incertitude` (a %, treated as a relative
   coefficient of variation `cv`) via
   `gsd = exp(sqrt(log(1 + cv**2)))`. Left empty when `Incertitude` is
   absent on the row.

CATEGORY SELECTION -- WHY THESE AND NOT OTHERS
------------------------------------------------
The full category tree of the dataset was enumerated live (via
`values_agg?field=Code_de_la_catégorie`) and every branch that could
plausibly contain reactor-feedstock chemicals was inspected by hand before
writing this script (see .SOURCES.md "Categories explored" section for the
full list and what was found/rejected in each). Categories NOT walked here
that were deliberately excluded, with reasons:

  * "...Produits chimiques > Engrais, phytosanitaires..." (whole subtree):
    fertilisers, pesticides and viticulture-specific inputs -- out of scope
    per the brief, and several entries share one clearly-proxied value
    (3300 kgCO2e/t appears identically on three unrelated acids).
  * "...Produits chimiques > Autres produits chimiques": a single row that
    is a formulated product ("Produits de traitement de la vapeur d'eau"),
    not a substance.
  * "...Produits chimiques > Peintures et résines": formulated
    adhesives/lacquers/varnishes (e.g. "Adhesif Epoxy"), not single
    PubChem-resolvable substances.
  * "...Plastiques et caoutchouc > *" (all 6 sub-categories, polymer
    resins): bulk plastics are not reactor feedstocks and several entries
    carry ambiguous duplicate values (e.g. LDPE listed at both 2090 and
    202 kgCO2e/t with no field distinguishing which is which).
  * "Combustibles > Fossiles > Gazeux > Gaz industriels": these are
    industrial *fuel* off-gases (blast-furnace gas, coke-oven gas), priced
    per GJ, not per kg -- wrong substance class and wrong unit basis.
  * "Process et émissions fugitives > PRG a 100 ans ...": these rows give
    the GWP of a gas *if released* (e.g. "Dioxyde de Carbone" = 1
    kgCO2e/kg, tautologically), not the cradle-to-gate emissions of
    *manufacturing* it. Including them would silently redefine what this
    column means, so they are excluded even though the numbers are real
    and fetched.
  * "Achats de biens > Hydrogene > Production d'hydrogene": hydrogen (CAS
    1333-74-0, verified live) resolves cleanly, but ADEME gives seven
    mutually exclusive production-route-specific values (electrolysis on
    five different grid/source mixes, biomethane reforming, natural-gas
    reforming) spanning 0.45-19.8 kgCO2e/kg H2, with no generic/market
    average row. The factor-table schema allows only one value per
    identifier, so picking one route would be an editorial judgement this
    script is not willing to make silently. Left out; see .SOURCES.md.

HOW TO RE-RUN
--------------
    PYTHONPATH=src python3 scripts/ingest_ademe_basecarbone.py \\
        [--out data/factors/ademe_base_carbone.csv] [--report]

Requires network access to data.ademe.fr and pubchem.ncbi.nlm.nih.gov.
PubChem responses are cached under a local cache directory (see
--cache-dir) so re-runs are cheap; delete the cache to force a refresh.
"""

from __future__ import annotations

import argparse
import sys as _sys_for_path
_sys_for_path.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from _snapshot import Snapshot, add_offline_flag  # noqa: E402
import csv
import hashlib
import json
import math
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from carbonroute.schema import cas_checksum_ok  # noqa: E402

ADEME_BASE = "https://data.ademe.fr/data-fair/api/v1/datasets/base-carboner"
PUBCHEM_BASE = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"
DEFAULT_OUT = REPO_ROOT / "data" / "factors" / "ademe_base_carbone.csv"
LICENSE_TEXT = "Licence Ouverte / Open Licence (Etalab)"

CAS_RE = re.compile(r"\d{2,7}-\d{2}-\d")

CSV_COLUMNS = (
    "identifier",
    "name",
    "gwp_kgCO2e_per_kg",
    "source",
    "database_version",
    "region",
    "retrieved_date",
    "uncertainty_class",
    "license",
    "notes",
    "inchikey",
    "gsd",
)

# --------------------------------------------------------------------------
# Category selection.
#
# Categories that were fetched and used as *candidate* rows (some of whose
# rows are still rejected downstream -- graded solutions, vague names, ...).
# --------------------------------------------------------------------------
CANDIDATE_CATEGORIES = (
    "Achats de biens > Plastiques et produits chimiques > Produits chimiques > Produits chimiques de base",
)

# Categories that were fetched, inspected, and whose rows are excluded
# *wholesale* with a fixed reason -- see the module docstring for the
# rationale on each. Recorded here (rather than only in prose) so the
# --report output and the generated .SOURCES.md are grounded in something
# the script actually executed, not just asserted.
EXCLUDED_CATEGORIES = {
    "Achats de biens > Plastiques et produits chimiques > Produits chimiques > Autres produits chimiques": (
        "category inspected: sole row is a formulated product "
        "(\"Produits de traitement de la vapeur d'eau\"), not a substance"
    ),
    "Achats de biens > Plastiques et produits chimiques > Produits chimiques > Peintures et résines": (
        "category inspected: rows are formulated adhesives/lacquers/varnishes, not single substances"
    ),
    "Achats de biens > Plastiques et produits chimiques > Plastiques et caoutchouc > Polymères de l'éthylène": (
        "category inspected: bulk polymer resins, not reactor feedstocks; ambiguous duplicate values present"
    ),
    "Achats de biens > Plastiques et produits chimiques > Plastiques et caoutchouc > Plastique moyen": (
        "category inspected: generic averaged plastic, not a substance"
    ),
    "Achats de biens > Plastiques et produits chimiques > Plastiques et caoutchouc > Polymères du chlorure de vinyle": (
        "category inspected: bulk polymer resin (PVC), not a reactor feedstock"
    ),
    "Achats de biens > Plastiques et produits chimiques > Plastiques et caoutchouc > Polymères du styrène": (
        "category inspected: bulk polymer resin (polystyrene), not a reactor feedstock"
    ),
    "Achats de biens > Plastiques et produits chimiques > Plastiques et caoutchouc > Polyamides": (
        "category inspected: bulk polymer resin (nylon), not a reactor feedstock"
    ),
    "Achats de biens > Plastiques et produits chimiques > Plastiques et caoutchouc > Polymères de propylène": (
        "category inspected: bulk polymer resin (PP), not a reactor feedstock"
    ),
    "Combustibles > Fossiles > Gazeux > Gaz industriels": (
        "category inspected: industrial off-gas fuels (blast-furnace/coke-oven gas), priced per GJ not per kg"
    ),
    "Achats de biens > Hydrogène > Production d'hydrogène": (
        "category inspected: hydrogen resolves to CAS 1333-74-0 but only as 7 mutually exclusive "
        "production-route-specific values (0.45-19.8 kgCO2e/kg), no generic/market-average row; "
        "picking one would be an editorial judgement, not mechanical extraction"
    ),
}

# Rows dropped by name/content *before* ever calling PubChem, because the
# ADEME name itself signals a mixture, a graded/diluted commercial product,
# or too vague a term to safely attach to one pure substance's CAS number.
PRE_PUBCHEM_REJECT_NAMES = {
    "Acide nitrique 50%": "graded/diluted commercial solution (50%), not the pure substance",
    "Soude 50%": "graded/diluted commercial solution (50%), not the pure substance",
    "Hypochlorite de sodium 15% (alcalin chloré)": "graded/diluted commercial solution (15%), not the pure substance",
    "Alcool": "generic/ambiguous name -- does not specify which alcohol",
}

# Name to feed to PubChem for rows whose ADEME English name is not a usable
# chemical-name query string (a direct machine translation rather than a
# nomenclature term). Mapping is French common name -> standard English
# chemical name; PubChem itself still supplies CID/CAS/InChIKey.
PUBCHEM_NAME_OVERRIDE = {
    "Soude solide (poudre, granulés)": "Sodium hydroxide",
}

MASS_UNITS = {
    "kgCO2e/kg": 1.0,
    "kgCO2e/ton": 1.0 / 1000.0,
}


#: Set once in main() to a live-or-offline Snapshot for the ADEME source.
_ADEME_SNAPSHOT: "Snapshot | None" = None
#: Shared across every ingestion script: a PubChem lookup made once, by any
#: script, is frozen once and replayed by all of them.
_PUBCHEM_SNAPSHOT: "Snapshot | None" = None


def http_get_json(url: str, params: dict | None = None, headers: dict | None = None) -> dict:
    if params:
        url = url + "?" + urllib.parse.urlencode(params)
    req_headers = {"User-Agent": "carbonroute-ingest/1.0 (research script; see repo scripts/ingest_ademe_basecarbone.py)"}
    if headers:
        req_headers.update(headers)
    assert _ADEME_SNAPSHOT is not None, "main() must set up _ADEME_SNAPSHOT before fetching"
    return _ADEME_SNAPSHOT.fetch_json(url, headers=req_headers, timeout=30)


# --------------------------------------------------------------------------
# ADEME
# --------------------------------------------------------------------------

def fetch_dataset_metadata() -> dict:
    return http_get_json(ADEME_BASE)


def fetch_category_lines(category: str, size: int = 200) -> list[dict]:
    results: list[dict] = []
    after = None
    while True:
        params = {"Code_de_la_catégorie_eq": category, "size": str(size)}
        if after:
            params["after"] = after
        data = http_get_json(ADEME_BASE + "/lines", params)
        page = data.get("results", [])
        results.extend(page)
        nxt = data.get("next")
        after = None
        if isinstance(nxt, str) and "after=" in nxt:
            after = urllib.parse.parse_qs(urllib.parse.urlparse(nxt).query).get("after", [None])[0]
        if not after or len(page) < size:
            break
    return results


# --------------------------------------------------------------------------
# PubChem, with a tiny on-disk cache and a rate limiter.
# --------------------------------------------------------------------------

class PubChemClient:
    """PubChem lookups, backed by the shared, durable, cross-script snapshot.

    Rate limiting and the "404 means not found, not an error" translation live
    on the Snapshot itself now, so every script that queries PubChem behaves
    identically and shares one on-disk cache.
    """

    def _get(self, path: str) -> dict | None:
        assert _PUBCHEM_SNAPSHOT is not None, "main() must set up _PUBCHEM_SNAPSHOT first"
        url = f"{PUBCHEM_BASE}/{path}"
        try:
            return _PUBCHEM_SNAPSHOT.fetch_json(url)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return {"__not_found__": True}
            raise

    def cids_for_name(self, name: str) -> list[int]:
        data = self._get(f"compound/name/{urllib.parse.quote(name)}/cids/JSON")
        if not data or data.get("__not_found__"):
            return []
        return data.get("IdentifierList", {}).get("CID", [])

    def properties(self, cid: int) -> dict:
        data = self._get(f"compound/cid/{cid}/property/InChIKey,MolecularFormula,CanonicalSMILES/JSON")
        return data["PropertyTable"]["Properties"][0]

    def synonyms(self, cid: int) -> list[str]:
        data = self._get(f"compound/cid/{cid}/synonyms/JSON")
        info = data.get("InformationList", {}).get("Information", [])
        if not info:
            return []
        return info[0].get("Synonym", [])


@dataclass
class Kept:
    identifier: str
    name: str
    gwp_kgCO2e_per_kg: float
    source: str
    database_version: str
    region: str
    retrieved_date: str
    uncertainty_class: str
    license: str
    notes: str
    inchikey: str
    gsd: str


@dataclass
class Rejected:
    name: str
    element_id: str
    reason: str


def compute_gsd(pct: float | int | str | None) -> str:
    if pct is None or pct == "":
        return ""
    cv = float(pct) / 100.0
    gsd = math.exp(math.sqrt(math.log(1 + cv**2)))
    return f"{gsd:.4f}"


def resolve_row(row: dict, client: PubChemClient, retrieved_date: str,
                 dataset_version: str, rejected: list[Rejected]) -> Kept | None:
    fr_name = (row.get("Nom_base_français") or "").strip()
    en_name = (row.get("Nom_base_anglais") or "").strip()
    element_id = str(row.get("Identifiant_de_l'élément") or "")

    if row.get("Type_Ligne") != "Elément":
        rejected.append(Rejected(fr_name, element_id, f"Type_Ligne != 'Elément' ({row.get('Type_Ligne')!r})"))
        return None
    if row.get("Type_de_l'élément") != "Facteur d'émission":
        rejected.append(Rejected(fr_name, element_id, "Type_de_l'élément != 'Facteur d'émission'"))
        return None

    unit = (row.get("Unité_anglais") or "").strip()
    if unit not in MASS_UNITS:
        rejected.append(Rejected(fr_name, element_id, f"unit {unit!r} is not a per-mass unit; skipped"))
        return None

    if fr_name in PRE_PUBCHEM_REJECT_NAMES:
        rejected.append(Rejected(fr_name, element_id, PRE_PUBCHEM_REJECT_NAMES[fr_name]))
        return None

    raw_value = row.get("Total_poste_non_décomposé")
    if raw_value is None:
        rejected.append(Rejected(fr_name, element_id, "no value in Total_poste_non_décomposé"))
        return None
    raw_value = float(raw_value)
    converted = raw_value * MASS_UNITS[unit]

    query_name = PUBCHEM_NAME_OVERRIDE.get(fr_name, en_name or fr_name)
    cids = client.cids_for_name(query_name)
    if len(cids) != 1:
        rejected.append(
            Rejected(fr_name, element_id,
                      f"PubChem name lookup for {query_name!r} returned {len(cids)} CIDs (need exactly 1)")
        )
        return None
    cid = cids[0]

    props = client.properties(cid)
    inchikey = props.get("InChIKey", "")

    synonyms = client.synonyms(cid)
    cas_candidates = [s for s in synonyms if CAS_RE.fullmatch(s)]
    if not cas_candidates:
        rejected.append(Rejected(fr_name, element_id, f"PubChem CID {cid} has no CAS-shaped synonym"))
        return None
    first_cas = cas_candidates[0]
    if not cas_checksum_ok(first_cas):
        rejected.append(
            Rejected(fr_name, element_id, f"CAS candidate {first_cas!r} (from PubChem CID {cid}) fails check digit")
        )
        return None

    other_cas = [c for c in cas_candidates[1:6] if c != first_cas]
    original_unit_label = row.get("Unité_français") or unit
    notes_parts = [
        f"original value {raw_value:g} {original_unit_label}",
        (f"converted to kgCO2e/kg by dividing by {int(round(1 / MASS_UNITS[unit]))}"
         if MASS_UNITS[unit] != 1.0 else "unit already kgCO2e/kg"),
        f"PubChem CID {cid}",
    ]
    if other_cas:
        notes_parts.append("other CAS candidates seen: " + ", ".join(other_cas))
    pct = row.get("Incertitude")
    if pct not in (None, ""):
        notes_parts.append(f"ADEME Incertitude {pct}%")
    overridden = fr_name in PUBCHEM_NAME_OVERRIDE
    if overridden:
        notes_parts.append(
            f"ADEME name {fr_name!r} / {en_name!r} queried on PubChem as {query_name!r} "
            "(standard chemical name substituted for ADEME's literal English translation)"
        )

    region = (row.get("Localisation_géographique") or "").strip()
    mod_date = (row.get("Date_de_modification") or "").strip()
    display_name = query_name if overridden else (en_name or fr_name)

    return Kept(
        identifier=first_cas,
        name=display_name,
        gwp_kgCO2e_per_kg=converted,
        source=f"ADEME Base Carbone (element id {element_id})",
        database_version=f"{dataset_version} (row last modified {mod_date})" if mod_date else dataset_version,
        region=region,
        retrieved_date=retrieved_date,
        uncertainty_class="literature",
        license=LICENSE_TEXT,
        notes="; ".join(notes_parts),
        inchikey=inchikey,
        gsd=compute_gsd(pct),
    )


def dedupe_rows(rows: list[dict]) -> list[dict]:
    """The `lines` endpoint returns each row via more than one internal
    join path in this dataset, so identical `_id` values can repeat. Keep
    first occurrence per `_id`."""
    seen: set[str] = set()
    out = []
    for r in rows:
        rid = r.get("_id")
        if rid in seen:
            continue
        seen.add(rid)
        out.append(r)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--report", action="store_true", help="print kept vs rejected rows with reasons")
    add_offline_flag(parser)
    args = parser.parse_args()

    global _ADEME_SNAPSHOT, _PUBCHEM_SNAPSHOT
    _ADEME_SNAPSHOT = Snapshot("ademe_base_carbone", offline=args.offline, rate_limit_seconds=0.1)
    _PUBCHEM_SNAPSHOT = Snapshot("pubchem", offline=args.offline, rate_limit_seconds=0.25)

    retrieved_date = date.today().isoformat()

    meta = fetch_dataset_metadata()
    license_info = meta.get("license") or {}
    license_title = license_info.get("title", "")
    if "ouverte" not in license_title.lower() and "open licence" not in license_title.lower():
        print(f"WARNING: dataset license changed since this script was written: {license_info!r}", file=sys.stderr)
    dataset_version = str(meta.get("dataVersion") or meta.get("updatedAt") or meta.get("finalizedAt") or "unknown")

    client = PubChemClient()

    all_candidate_rows: list[dict] = []
    for cat in CANDIDATE_CATEGORIES:
        rows = dedupe_rows(fetch_category_lines(cat))
        all_candidate_rows.extend(rows)

    # Categories that were fetched purely to confirm the exclusion reason
    # (counts recorded for --report / SOURCES.md; rows are not resolved).
    excluded_counts: dict[str, int] = {}
    for cat in EXCLUDED_CATEGORIES:
        rows = dedupe_rows(fetch_category_lines(cat))
        excluded_counts[cat] = len(rows)

    kept: list[Kept] = []
    rejected: list[Rejected] = []
    for row in all_candidate_rows:
        result = resolve_row(row, client, retrieved_date, dataset_version, rejected)
        if result is not None:
            kept.append(result)

    # Deterministic order: sort by identifier (CAS).
    kept.sort(key=lambda k: k.identifier)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="\n", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, lineterminator="\n")
        writer.writeheader()
        for k in kept:
            writer.writerow({
                "identifier": k.identifier,
                "name": k.name,
                "gwp_kgCO2e_per_kg": f"{k.gwp_kgCO2e_per_kg:.6g}",
                "source": k.source,
                "database_version": k.database_version,
                "region": k.region,
                "retrieved_date": k.retrieved_date,
                "uncertainty_class": k.uncertainty_class,
                "license": k.license,
                "notes": k.notes,
                "inchikey": k.inchikey,
                "gsd": k.gsd,
            })

    if args.report:
        print(f"Dataset: {meta.get('title')!r}  license={license_title!r}  version={dataset_version}")
        print(f"Candidate rows fetched: {len(all_candidate_rows)}")
        print(f"\nKEPT ({len(kept)}):")
        for k in kept:
            print(f"  {k.identifier}  {k.name:35s}  {k.gwp_kgCO2e_per_kg:.4g} kgCO2e/kg  [{k.source}]")
        print(f"\nREJECTED ({len(rejected)}):")
        for r in rejected:
            print(f"  {r.name!r} (element id {r.element_id}): {r.reason}")
        print("\nEXCLUDED CATEGORIES (whole category skipped, see script docstring for reasons):")
        for cat, n in excluded_counts.items():
            print(f"  [{n:3d} rows] {cat}\n           reason: {EXCLUDED_CATEGORIES[cat]}")
        print(f"\nWrote {len(kept)} rows to {args.out}")

    print(_ADEME_SNAPSHOT.describe())
    print(_PUBCHEM_SNAPSHOT.describe())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
