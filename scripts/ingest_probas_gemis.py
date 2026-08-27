"""Build an emission-factor table for bulk chemicals from ProBas / UBA-GEMIS.

SOURCE
------
ProBas ("PROzessorientierte BASisdaten fuer Umweltmanagement-Instrumente"),
published by the German Federal Environment Agency (Umweltbundesamt, UBA).
ProBas is a soda4LCA / ILCD node -- the same REST interface family as
Oekobaudat and the JRC's Life Cycle Data Network -- served at:

  Web UI / node root : https://data.probas.umweltbundesamt.de/
  REST API            : https://data.probas.umweltbundesamt.de/resource/processes

(The older https://probas.umweltbundesamt.de/ site is a client-rendered SPA
with no discoverable API and is not used here -- see docs/sources-investigated.md
under this round's date for that dead end, and the older uslci-round entry
for the earlier attempt at the same URL.)

Most processes on this node are *republished ecoinvent* (their
`dataSources` field names "ecoinvent 3.8 cut-off" explicitly) and are
therefore excluded outright under this project's ecoinvent rule -- see
`is_commercial_sourced()` below, which checks this on every candidate
before it is ever considered. What is left after that filter is UBA's own
original content: roughly 20 000 processes carried over from GEMIS
("Globales Emissions-Modell Integrierter Systeme"), a model built and
maintained by the Oeko-Institut since 1987, entered into ProBas as
independent "LCI result" (i.e. pre-aggregated, cradle-to-gate) datasets
with their own literature citations (Ullmann's Encyclopedia, BUWAL, ECN,
Roempp, ...) -- not ecoinvent, not GaBi/Sphera.

LICENSE
-------
Every process kept by this script carries, in its own
`administrativeInformation.publicationAndOwnership.licenseType` (fetched
live, not retyped from memory), the exact string:

    "Free of charge for all users and uses"

which is also the exact phrase the project brief names as the ILCD
`licenseType` to look for. The node-level usage terms (fetched live from
https://probas.umweltbundesamt.de/daten/static/Nutzungsbedingungen_ProBas.pdf,
saved in this round's scratch directory) additionally require attribution
("es ist auf ProBas als Quelle eines Inhalts hinzuweisen") and prohibit
altering the values -- both of which this script and its output satisfy
(the `source`/`license` columns cite ProBas by name, and no numeric
value is transformed beyond the unit checks below). Full text is quoted
in `data/factors/probas_gemis.SOURCES.md`.

WHAT "GWP" MEANS HERE
----------------------
Each kept process publishes its own pre-computed LCIA result for the
impact category named "Treibhauseffekt" ("greenhouse effect"), methodology
"UBA Probas", whose declared unit (checked live against the LCIA method
dataset's own `quantitativeReference`, not assumed) is "kg CO2-Aeq.". This
is UBA's own characterisation, already aggregated over the process's full
upstream chain ("mit Vorkette" per GEMIS documentation -- the process type
is "LCI result", not "Unit process", precisely because it is the
aggregated/cradle-to-gate figure and not a single unit operation). This
script reads that published number; it does not compute a GWP itself from
elementary-flow exchanges (unlike the rejected USLCI graph-solve -- see
uslci.SOURCES.md -- this number is the source's own stated result, not a
derived one).

CRADLE-TO-GATE / PER-KG FILTER
--------------------------------
A process is only kept if its own `functionalUnitOrOther` string contains
"1 kg" (checked live via regex, see `is_per_kg()`). This mechanically
rejects, without any substance-specific logic:
  - per-tonne aggregate figures (e.g. the plain "Ammoniak" and "Wasserstoff"
    processes, both 1 t)
  - per-energy figures (e.g. "Chem-Anorg\\H2-DE-2015", 1 TJ H2 "energetisch"
    -- converting this to per-kg would require a hydrogen LHV that this
    dataset itself does not state, so per the project's conversion rule it
    is skipped rather than converted)

SUBSTANCE SELECTION -- WHY THESE SEVEN AND NOT MORE
------------------------------------------------------
GEMIS's organic/inorganic bulk-chemical catalogue ("Chem-Org\\*",
"Chem-Anorg\\*") was enumerated live in full (see .SOURCES.md) and checked
by hand against the project's priority list. It only ever modelled a small
set of petrochemical/inorganic *feedstocks*, not laboratory/process
solvents: THF, 2-MeTHF, dichloromethane, ethyl acetate, isopropyl acetate,
acetone, acetonitrile, DMF, DMSO, n-heptane, n-pentane, MTBE, triethylamine,
sodium bicarbonate, potassium phosphate and sodium phosphates do not exist
anywhere in this node under any German synonym tried (full list of terms
tried is in .SOURCES.md) -- a negative result, recorded rather than
papered over. What does exist, cleanly (non-ecoinvent, per-kg, with a
published Treibhauseffekt result): water, toluene, isopropanol, acetic
acid, ethanol, ammonia and hydrogen. Each has more than one GEMIS vintage
or variant on file; `PREFERRED_PROCESS_NAME` records which one this script
selects and why (most recent non-forecast vintage with the fullest
literature citation among the *non-ecoinvent* survivors); every other
vintage/variant this script actually queried is reported as rejected, with
the specific reason, by `--report` and in .SOURCES.md.

HOW TO RE-RUN
--------------
    PYTHONPATH=src python3 scripts/ingest_probas_gemis.py \\
        [--out data/factors/probas_gemis.csv] [--report]

Requires network access to data.probas.umweltbundesamt.de and
pubchem.ncbi.nlm.nih.gov. PubChem responses are cached under a local cache
directory (see --cache-dir) so re-runs are cheap; delete the cache to force
a refresh.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from carbonroute.schema import cas_checksum_ok  # noqa: E402

PROBAS_BASE = "https://data.probas.umweltbundesamt.de"
PUBCHEM_BASE = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"
DEFAULT_OUT = REPO_ROOT / "data" / "factors" / "probas_gemis.csv"
DEFAULT_CACHE_DIR = Path(
    "/tmp/claude-0/-home-user-carbonroute/615824c5-ea95-5811-9178-bd4f433c32ff/scratchpad/cache_probas"
)

LICENSE_TEXT = "Free of charge for all users and uses (ProBas / Umweltbundesamt, attribution required)"
REQUIRED_LICENSE_TYPE = "Free of charge for all users and uses"

CAS_RE = re.compile(r"\d{2,7}-\d{2}-\d")
COMMERCIAL_MARKERS = ("ecoinvent", "gabi", "sphera")

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


@dataclass(frozen=True)
class SubstanceSpec:
    label: str  # short internal label, used only in logs/report
    search_term: str  # German term submitted to the ProBas search endpoint
    preferred_name: str  # exact process `name` this script selects among the survivors
    pubchem_query: str  # English name queried against PubChem for identity resolution
    display_name: str  # name written into the CSV's `name` column
    rationale: str  # why this vintage/variant was preferred over the others


# Curated by hand after enumerating every "LCI result" process returned for
# each search term (see .SOURCES.md "Search terms tried" for the full,
# larger set of terms that returned nothing). The GWP value itself is never
# hard-coded here -- only which process to read it from.
SUBSTANCE_SPECS = (
    SubstanceSpec(
        label="water",
        search_term="destilliertes Wasser",
        preferred_name="Chem-anorg\\destilliertes Wasser",
        pubchem_query="water",
        display_name="Water (distilled)",
        rationale="only non-ecoinvent per-kg candidate; distilled water, not deionised, but chemically "
        "the same substance (CAS 7732-18-5) -- flagged as an approximation in notes",
    ),
    SubstanceSpec(
        label="toluene",
        search_term="Toluol",
        preferred_name="Chem-Org\\Toluol-DE-2000",
        pubchem_query="toluene",
        display_name="Toluene",
        rationale="only non-ecoinvent per-kg candidate for this search term",
    ),
    SubstanceSpec(
        label="isopropanol",
        search_term="2-Propanol",
        preferred_name="Chem-Org\\2-Propanol (hochrein)",
        pubchem_query="2-propanol",
        display_name="Isopropanol (2-propanol, high purity)",
        rationale="only non-ecoinvent per-kg candidate for this search term",
    ),
    SubstanceSpec(
        label="acetic_acid",
        search_term="Essigsäure",
        preferred_name="Chem-Org\\Essigsäure (hochrein)",
        pubchem_query="acetic acid",
        display_name="Acetic acid (high purity)",
        rationale="preferred over 'Essigsäure-DE-2000' (also non-ecoinvent, also per-kg): the 'hochrein' "
        "variant is the more recent vintage (2005 vs 2000) and cites more literature sources "
        "(Ullmann 1985a, ECN 2005) rather than only 'Originaldokumentation'",
    ),
    SubstanceSpec(
        label="ethanol",
        search_term="Ethanol",
        preferred_name="Chem-Org\\Ethanol (hochrein)",
        pubchem_query="ethanol",
        display_name="Ethanol (high purity)",
        rationale="only non-ecoinvent per-kg reagent-grade ethanol candidate for this search term "
        "(the many other 'Ethanol'-matching hits are fuel-ethanol/biofuel pathway processes, a "
        "different product and route, excluded on that basis)",
    ),
    SubstanceSpec(
        label="ammonia",
        search_term="Ammoniak",
        preferred_name="Chem-Anorg\\Ammoniak-DE-2020",
        pubchem_query="ammonia",
        display_name="Ammonia",
        rationale="most recent *non-forecast* per-kg vintage among the non-ecoinvent candidates "
        "(DE-2000/2005/2010/2015 are older vintages of the same process; DE-2030/2050 are "
        "prospective-scenario projections, not current production; the plain 'Ammoniak' process "
        "is per-tonne and cites 'Ecoinvent 2.0' among its many reference sources, so it is excluded "
        "by both the per-kg filter and the commercial-source filter)",
    ),
    SubstanceSpec(
        label="hydrogen",
        search_term="H2-Stoff",
        preferred_name="Chem-Anorg\\H2-Stoff-DE-2015",
        pubchem_query="hydrogen",
        display_name="Hydrogen (chemical-grade, natural-gas steam reforming)",
        rationale="most recent per-kg ('stofflich', i.e. chemical-product-grade, natural-gas steam "
        "reforming) vintage among the non-ecoinvent candidates; 'H2-DE-2015'/'H2-DE-2010' publish the "
        "same route per TJ ('energetisch') with no stated kg<->TJ conversion in the dataset itself, so "
        "per the project's conversion rule they are skipped rather than converted",
    ),
)


def http_get_json(url: str, params: dict | None = None) -> dict:
    if params:
        url = url + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(
        url, headers={"User-Agent": "carbonroute-ingest/1.0 (research script; see scripts/ingest_probas_gemis.py)"}
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def search_processes(term: str, page_size: int = 100) -> list[dict]:
    results: list[dict] = []
    start = 0
    while True:
        data = http_get_json(
            f"{PROBAS_BASE}/resource/processes",
            {"format": "json", "search": "true", "name": term, "pageSize": str(page_size), "startIndex": str(start)},
        )
        page = data.get("data", [])
        results.extend(page)
        start += page_size
        if start >= data.get("totalCount", 0) or not page:
            break
    return results


def process_detail(uuid: str) -> dict:
    return http_get_json(f"{PROBAS_BASE}/resource/processes/{uuid}", {"format": "json", "view": "extended"})


def lciamethod_unit(uuid: str, cache: dict[str, str]) -> str:
    if uuid in cache:
        return cache[uuid]
    data = http_get_json(f"{PROBAS_BASE}/resource/lciamethods/{uuid}", {"format": "json"})
    ref_qty = data.get("LCIAMethodInformation", {}).get("quantitativeReference", {}).get("referenceQuantity", {})
    short = ref_qty.get("shortDescription", [{}])
    unit = short[0].get("value", "") if short else ""
    cache[uuid] = unit
    return unit


def is_commercial_sourced(names: list[str]) -> str | None:
    """Return a reason string if any of the given source-citation names look
    like a commercial LCI database this project excludes; else None."""
    for n in names:
        low = n.lower()
        for marker in COMMERCIAL_MARKERS:
            if marker in low:
                return f"background data sourced from {n!r} (commercial LCI database, excluded per project rule)"
    return None


PER_KG_RE = re.compile(r"\b1\s*kg\b", re.IGNORECASE)


def is_per_kg(functional_unit: list[dict] | None) -> bool:
    if not functional_unit:
        return False
    text = " ".join(fu.get("value", "") for fu in functional_unit)
    return bool(PER_KG_RE.search(text))


# --------------------------------------------------------------------------
# PubChem, with a tiny on-disk cache and a rate limiter.
# --------------------------------------------------------------------------


class PubChemClient:
    def __init__(self, cache_dir: Path, min_interval: float = 0.25):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.min_interval = min_interval
        self._last_request = 0.0

    def _cache_path(self, key: str) -> Path:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return self.cache_dir / f"{digest}.json"

    def _get(self, path: str) -> dict | None:
        cache_path = self._cache_path(path)
        if cache_path.exists():
            return json.loads(cache_path.read_text(encoding="utf-8"))
        wait = self.min_interval - (time.monotonic() - self._last_request)
        if wait > 0:
            time.sleep(wait)
        url = f"{PUBCHEM_BASE}/{path}"
        try:
            data = http_get_json(url)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                data = {"__not_found__": True}
            else:
                raise
        finally:
            self._last_request = time.monotonic()
        cache_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return data

    def cids_for_name(self, name: str) -> list[int]:
        data = self._get(f"compound/name/{urllib.parse.quote(name)}/cids/JSON")
        if not data or data.get("__not_found__"):
            return []
        return data.get("IdentifierList", {}).get("CID", [])

    def inchikey(self, cid: int) -> str:
        data = self._get(f"compound/cid/{cid}/property/InChIKey/JSON")
        return data["PropertyTable"]["Properties"][0].get("InChIKey", "")

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
    spec_label: str
    process_name: str
    uuid: str
    reason: str


def evaluate_candidate(
    spec: SubstanceSpec, listing: dict, lcia_unit_cache: dict[str, str], rejected: list[Rejected]
) -> dict | None:
    """Fetch full detail for one search-result row and apply every hard
    filter. Returns the parsed detail dict (with GWP attached) if it
    survives every check, else None (with a Rejected entry appended)."""
    name = listing.get("name", "")
    uuid = listing.get("uuid", "")

    listing_srcs = [s.get("name", "") for s in listing.get("dataSources", []) if s.get("name")]
    reason = is_commercial_sourced(listing_srcs)
    if reason:
        rejected.append(Rejected(spec.label, name, uuid, reason))
        return None

    detail = process_detail(uuid)
    pi = detail.get("processInformation", {})
    fu = pi.get("quantitativeReference", {}).get("functionalUnitOrOther")
    if not is_per_kg(fu):
        fu_text = "; ".join(f.get("value", "") for f in (fu or []))
        rejected.append(Rejected(spec.label, name, uuid, f"reference flow is not '1 kg' (declared: {fu_text!r})"))
        return None

    detail_srcs = detail.get("modellingAndValidation", {}).get("dataSourcesTreatmentAndRepresentativeness", {}).get(
        "referenceToDataSource", []
    )
    detail_src_names = [
        s.get("shortDescription", [{}])[0].get("value", "") for s in detail_srcs if s.get("shortDescription")
    ]
    reason = is_commercial_sourced(detail_src_names)
    if reason:
        rejected.append(Rejected(spec.label, name, uuid, reason))
        return None

    admin = detail.get("administrativeInformation", {})
    license_type = admin.get("publicationAndOwnership", {}).get("licenseType", "")
    if license_type != REQUIRED_LICENSE_TYPE:
        rejected.append(Rejected(spec.label, name, uuid, f"licenseType {license_type!r} != {REQUIRED_LICENSE_TYPE!r}"))
        return None

    lcia_results = detail.get("LCIAResults", {}).get("LCIAResult", [])
    gwp_entry = None
    for r in lcia_results:
        short = r.get("referenceToLCIAMethodDataSet", {}).get("shortDescription", [{}])
        val = short[0].get("value", "") if short else ""
        if val == "Treibhauseffekt":
            gwp_entry = r
            break
    if gwp_entry is None:
        rejected.append(Rejected(spec.label, name, uuid, "no 'Treibhauseffekt' (GWP) LCIA result published"))
        return None

    method_uuid = gwp_entry.get("referenceToLCIAMethodDataSet", {}).get("refObjectId", "")
    unit = lciamethod_unit(method_uuid, lcia_unit_cache)
    if "CO2" not in unit:
        rejected.append(Rejected(spec.label, name, uuid, f"Treibhauseffekt method unit is {unit!r}, not kg CO2-eq"))
        return None

    detail["_gwp_value"] = gwp_entry.get("meanAmount")
    detail["_gwp_unit"] = unit
    detail["_all_source_names"] = detail_src_names
    return detail


def build_row(
    spec: SubstanceSpec, detail: dict, client: PubChemClient, retrieved_date: str, rejected: list[Rejected]
) -> Kept | None:
    pi = detail["processInformation"]
    name = pi["dataSetInformation"]["name"]["baseName"][0]["value"]
    uuid = pi["dataSetInformation"]["UUID"]
    ref_year = pi.get("time", {}).get("referenceYear")
    geo = pi.get("geography", {}).get("locationOfOperationSupplyOrProduction", {}).get("location", "")

    admin = detail["administrativeInformation"]
    dataset_version = admin.get("publicationAndOwnership", {}).get("dataSetVersion", "")

    cids = client.cids_for_name(spec.pubchem_query)
    if len(cids) != 1:
        rejected.append(
            Rejected(spec.label, name, uuid, f"PubChem name lookup for {spec.pubchem_query!r} returned {len(cids)} CIDs (need exactly 1)")
        )
        return None
    cid = cids[0]
    inchikey = client.inchikey(cid)
    synonyms = client.synonyms(cid)
    cas_candidates = [s for s in synonyms if CAS_RE.fullmatch(s)]
    if not cas_candidates:
        rejected.append(Rejected(spec.label, name, uuid, f"PubChem CID {cid} has no CAS-shaped synonym"))
        return None
    first_cas = cas_candidates[0]
    if not cas_checksum_ok(first_cas):
        rejected.append(Rejected(spec.label, name, uuid, f"CAS candidate {first_cas!r} fails check digit"))
        return None

    notes_parts = [
        f"GEMIS process {name!r} (ProBas UUID {uuid}, dataset version {dataset_version}, reference year {ref_year})",
        f"LCIA result category 'Treibhauseffekt' (methodology UBA Probas), unit {detail['_gwp_unit']!r}, "
        "already aggregated over the full upstream chain (GEMIS 'mit Vorkette')",
        "cited sources: " + ", ".join(detail["_all_source_names"]) if detail["_all_source_names"] else "cited sources: (none beyond original documentation)",
        spec.rationale,
    ]
    if spec.label == "water":
        notes_parts.append(
            "process models distilled water, not deionised water; both are pure H2O (CAS 7732-18-5) so the "
            "identifier match is exact, but the production route (distillation vs. ion exchange) differs"
        )

    return Kept(
        identifier=first_cas,
        name=spec.display_name,
        gwp_kgCO2e_per_kg=float(detail["_gwp_value"]),
        source=f"ProBas / UBA-GEMIS (process {name!r}, UUID {uuid})",
        database_version=f"ProBas dataset version {dataset_version}" + (f", GEMIS reference year {ref_year}" if ref_year else ""),
        region=geo or "DE",
        retrieved_date=retrieved_date,
        uncertainty_class="background_db",
        license=LICENSE_TEXT,
        notes="; ".join(notes_parts),
        inchikey=inchikey,
        gsd="",  # uncertaintyDistributionType is "undefined"/"UNDEFINED" on every process read here
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--report", action="store_true")
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    args = parser.parse_args()

    retrieved_date = date.today().isoformat()
    client = PubChemClient(args.cache_dir)
    lcia_unit_cache: dict[str, str] = {}

    kept: list[Kept] = []
    rejected: list[Rejected] = []
    all_search_hits: dict[str, int] = {}

    for spec in SUBSTANCE_SPECS:
        listings = search_processes(spec.search_term)
        all_search_hits[spec.search_term] = len(listings)
        lci_listings = [l for l in listings if l.get("type") == "LCI result"]

        chosen_detail = None
        for listing in lci_listings:
            detail = evaluate_candidate(spec, listing, lcia_unit_cache, rejected)
            if detail is None:
                continue
            process_name = detail["processInformation"]["dataSetInformation"]["name"]["baseName"][0]["value"]
            if process_name == spec.preferred_name:
                chosen_detail = detail
            else:
                rejected.append(
                    Rejected(
                        spec.label,
                        process_name,
                        detail["processInformation"]["dataSetInformation"]["UUID"],
                        f"passed every hard filter but not the preferred vintage/variant for {spec.label} "
                        f"(preferred: {spec.preferred_name!r}) -- {spec.rationale}",
                    )
                )

        if chosen_detail is None:
            rejected.append(Rejected(spec.label, spec.preferred_name, "", "preferred process not found among survivors"))
            continue

        row = build_row(spec, chosen_detail, client, retrieved_date, rejected)
        if row is not None:
            kept.append(row)

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
        print("Search hits per term (raw, before any filtering):")
        for term, n in all_search_hits.items():
            print(f"  {term!r}: {n} total results")
        print(f"\nKEPT ({len(kept)}):")
        for k in kept:
            print(f"  {k.identifier}  {k.name:20s}  {k.gwp_kgCO2e_per_kg:.4g} kgCO2e/kg  [{k.source}]")
        print(f"\nREJECTED ({len(rejected)}):")
        for r in rejected:
            print(f"  [{r.spec_label}] {r.process_name!r} ({r.uuid}): {r.reason}")
        print(f"\nWrote {len(kept)} rows to {args.out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
