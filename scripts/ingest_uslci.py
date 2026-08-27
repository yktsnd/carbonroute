"""Build an emission-factor table for gas reagents from the U.S. LCI Database.

SOURCE
------
The U.S. LCI Database ("USLCI"), maintained by the National Renewable Energy
Laboratory (NREL) / Alliance for Sustainable Energy for the U.S. Department
of Energy, distributed via the Federal LCA Commons ("LCA Commons") data
platform:

  Landing page      : https://www.lcacommons.gov/
  Repository browser: https://www.lcacommons.gov/lca-collaboration/
  API guide (fetched live 2026-08-26): https://www.lcacommons.gov/lca-commons-api-guide
  API base          : https://api.nal.usda.gov/FederalLCACommonsapi
  Repository        : National_Renewable_Energy_Laboratory / USLCI_Database_Public

The API is hosted on api.data.gov and requires an API key on every request;
a shared, low-quota "DEMO_KEY" (10 req/hour, 50 req/day) works for
exploration and for the tiny number of calls this script makes. Set
env var USLCI_API_KEY to a personal key (free, https://api.data.gov/signup/)
for reliable re-runs; DEMO_KEY is shared across every anonymous caller
and gets rate-limited easily (this script backs off and reports clearly
rather than fabricating a value when that happens -- see CACHING below).

LICENSE
-------
Every USLCI process this script reads carries, in its own
`processDocumentation.restrictionsDescription` field (fetched live, not
retyped from memory), one of two equivalent notices. The substantive one
(fetched verbatim from the live JSON-LD, reproduced here for the record):

    "These U.S. LCI Database Project data ("Data") are provided by the
    National Renewable Energy Laboratory ("NREL"), operated by the Alliance
    for Sustainable Energy, LLC ("Alliance") for the US Department of Energy
    ("DOE") under Contract No. DE-AC36-08GO28308. [...] The user is granted
    the right, without any fee or cost, to use, copy, modify, alter, enhance
    and distribute these Data for any purpose whatsoever, provided that this
    entire notice appears in all copies of the Data. [...] the user agrees
    to credit the DOE/NREL/Alliance in any publication that results from the
    use of these Data. [...]"

The remaining processes instead carry: "All information can be accessed by
everybody." Both are u.s.-government-funded open data with an explicit,
no-fee redistribution right conditioned on attribution and notice
preservation -- exactly the class of licence this project accepts (see
data/factors/uslci.SOURCES.md for the full text and where it was read).
`isCopyrightProtected` is also checked on every row read and any row where
it is `true` is dropped rather than used (see CHEMICAL COVERAGE below: none
of the rows this script keeps are copyright-protected).

CHEMICAL COVERAGE -- WHY ONLY TWO SUBSTANCES, AND WHY NOT THE OBVIOUS ONES
---------------------------------------------------------------------------
USLCI's ~660 unit processes include toluene, methanol, sulfuric acid,
sodium carbonate, sodium hydroxide, ammonia, hydrogen and acetic acid --
exactly bulk reagents this project wants. They were NOT usable here:

1. Every ordinary USLCI process is a *unit* process: its exchanges are its
   own direct emissions plus technosphere links (via `defaultProvider`) to
   *other* unit processes (electricity, fuel combustion, transport, raw
   material extraction, ...). Getting a genuine cradle-to-gate number
   requires solving the whole linked system, not reading one process.

2. This was attempted (see scratch work referenced in
   `data/factors/uslci.SOURCES.md`): the ~660-process technosphere graph
   reachable from those target chemicals was built and solved exactly as a
   linear system ((I - C) x = d, C = technosphere coefficients, d = each
   process's own characterized direct GWP). The system is technically
   solvable (finite condition number, ~8e9) but the numbers it produces are
   not credible: e.g. toluene at plant came out to ~100 kgCO2e/kg and
   hydrogen (steam reforming) at ~1000 kgCO2e/kg, both roughly 50-150x
   published literature ranges. Tracing the worst offender found the cause:
   "Fuel grade uranium, at regional storage" consumes ~4080 kWh of
   electricity per kg of product (a legacy gaseous-diffusion enrichment
   figure), and that electricity is itself partly sourced from the U.S.
   grid mix's nuclear share -- closing a loop that amplifies *every*
   process reachable through "Electricity, at grid" by one to two orders of
   magnitude. This is very likely a real data-vintage mismatch in USLCI
   (old, high-energy diffusion-enrichment data feeding a modern average
   grid mix) rather than a bug in the solver, but resolving that with
   confidence would mean auditing and correcting a ~660-process database by
   hand -- well beyond what a reproducible script can respons8ibly do, and
   exactly the kind of "looks plausible, can't be checked" number this
   project's rules forbid. So: no unit-process chemical from USLCI is
   ingested here, at all, under any name.

3. That leaves USLCI's small set of pre-*aggregated* `LCI_RESULT`-type
   processes, whose exchange list is already a cradle-to-gate elementary
   flow inventory (raw materials like crude oil/natural gas/coal appear as
   direct elementary inputs, not further technosphere links) -- exactly the
   "aggregated inventory of elementary flows" this project's rules allow
   characterizing directly. Of USLCI's 24 such processes, only three are
   chemicals rather than steel/asphalt/roofing/wood products:
     - "Hydrochloric acid, without water, in 30% solution state, at plant"
       -- DROPPED: `data/factors/ademe_base_carbone.csv` already carries a
       row for CAS 7647-01-0 (Hydrochloric acid) with a different value;
       `FactorTable.load()` raises on two tables giving the same identifier
       conflicting values, so adding a second HCl number here would break
       every other command in this repository that loads all factor
       tables, not just this one. See NOT-INGESTED below.
     - "Carbon monoxide, at plant" -- KEPT. Reagent-grade CO is a real
       process-chemistry input (carbonylations, hydroformylation).
     - "Ethylene oxide, at plant" -- KEPT. Common alkylating/PEGylation
       reagent.
   Each has near-zero residual technosphere linkage (see RESIDUAL
   BOUNDARY below), unlike the unit processes above, so no system-solving
   is needed or attempted for them.

None of this reaches the solvents this project actually wants (toluene,
THF, 2-MeTHF, DCM, EtOAc, acetone, ethanol, isopropanol, acetonitrile, DMF,
DMSO, heptane): USLCI simply does not carry them as pre-aggregated system
processes, and its unit-process versions of them are exactly the numbers
this script refuses to fabricate via an unvalidated system solve. See
`docs/sources-investigated.md` for the sources tried instead.

RESIDUAL BOUNDARY (what "aggregated" does not include here)
-------------------------------------------------------------
Both kept processes still carry a handful of small technosphere exchanges
for solid-waste disposal (to landfill/incineration) and a fractional MJ of
"Energy, fossil, unspecified" that are not further resolved by this script.
This is consistent with this project's own default boundary
(`waste_treatment: excluded`, see `examples/route.yaml`) and is reported
explicitly per row in `--report` output and in the CSV `notes` column, with
the excluded exchanges' amounts, so it is checkable rather than silent.

CHARACTERIZATION
-----------------
USLCI's `LCI_RESULT` processes report elementary flows, not a pre-computed
GWP. Every ELEMENTARY_FLOW output exchange whose flow name matches a
well-mixed Kyoto-basket greenhouse gas is characterized with the IPCC AR6
WG1 100-year GWP (GWP-100), fetched live as PDFs from the IPCC on
2026-08-26 and parsed with `pdftotext -layout`:

  - CO2, CH4 (fossil), N2O: Table 7.15 (main chapter text, includes
    chemical/carbon-cycle feedbacks; species this table doesn't cover fall
    back to the next source)
    https://www.ipcc.ch/report/ar6/wg1/downloads/report/IPCC_AR6_WGI_Chapter07.pdf
  - SF6, HFCs, PFC-116 (hexafluoroethane): Table 7.SM.7 (Supplementary
    Material, full gas list, no chemical-feedback adjustment -- the
    adjustment only applies to CH4/N2O per that table's own footnote, and
    the HFC values it gives cross-check exactly against Table 7.15 where
    both list the same gas, e.g. HFC-32 = 771 in both)
    https://www.ipcc.ch/report/ar6/wg1/downloads/report/IPCC_AR6_WGI_Chapter07_SM.pdf

USLCI does not distinguish fossil vs. non-fossil methane (a single
"Methane" flow, plus "Coalbed methane" which is unambiguously fossil), so
CH4-fossil (29.8) is used throughout; both kept processes' methane exchanges
are fossil-fuel-combustion-derived, consistent with that choice. See
GWP100_KGCO2E_PER_KG below for the exact factor set and its provenance.
Any elementary flow whose name is not in that dict does not contribute
(most are non-GHG pollutants: particulates, NOx, SOx, metals, etc., which
correctly have no GWP-100).

CACHING / LIVE-FETCH NOTE
---------------------------
This script fetches each target process live from
`GET /browse/{group}/{repo}/PROCESS/{refId}` and caches the raw response
under --cache-dir, exactly like `ingest_ademe_basecarbone.py` caches
PubChem lookups ("so re-runs are cheap; delete the cache to force a
refresh"). The two responses shipped in the cache directory used by
`--out data/factors/uslci.csv` were fetched live against this exact
endpoint on 2026-08-26, earlier the same UTC day this file was written;
DEMO_KEY's daily quota (50 req/day, shared by every anonymous caller) was
then exhausted for the rest of that day by this same investigation
(confirmed live: the API returned HTTP 429 with a ~6-hour Retry-After).
Delete --cache-dir and re-run with a personal key (`USLCI_API_KEY` env var)
to re-fetch from scratch and confirm the values independently.

HOW TO RE-RUN
--------------
    PYTHONPATH=src python3 scripts/ingest_uslci.py \\
        [--out data/factors/uslci.csv] [--report] \\
        [--cache-dir DIR] [--api-key KEY]

Requires network access to api.nal.usda.gov and pubchem.ncbi.nlm.nih.gov.
"""

from __future__ import annotations

import argparse
import sys as _sys_for_path
_sys_for_path.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from _snapshot import Snapshot, add_offline_flag  # noqa: E402
import csv
import hashlib
import json
import os
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

LCA_COMMONS_BASE = "https://api.nal.usda.gov/FederalLCACommonsapi"
LCA_COMMONS_GROUP = "National_Renewable_Energy_Laboratory"
LCA_COMMONS_REPO = "USLCI_Database_Public"
PUBCHEM_BASE = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"

DEFAULT_OUT = REPO_ROOT / "data" / "factors" / "uslci.csv"
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

LICENSE_SHORT = "US LCI Database Project data license (NREL/Alliance/DOE) -- free use/copy/modify/distribute, attribution required"

# --------------------------------------------------------------------------
# IPCC AR6 WG1 GWP-100 (100-year), fetched live 2026-08-26 as PDFs and parsed
# with pdftotext -layout. See module docstring "CHARACTERIZATION" for which
# table each value came from and why.
# --------------------------------------------------------------------------
GWP100_KGCO2E_PER_KG: dict[str, float] = {
    "carbon dioxide": 1.0,                # Table 7.15 (CO2 = 1 by definition)
    "methane": 29.8,                      # Table 7.15, CH4-fossil
    "coalbed methane": 29.8,              # fossil methane, same factor
    "nitrous oxide": 273.0,               # Table 7.15 (== Table 7.SM.7)
    "sulfur hexafluoride": 24300.0,       # Table 7.SM.7
    "hexafluoroethane": 12400.0,          # Table 7.SM.7 (PFC-116)
    "hfc-23": 14600.0,                    # Table 7.SM.7
    "hfc-32": 771.0,                      # Table 7.15 (== Table 7.SM.7)
    "hfc-125": 3740.0,                    # Table 7.SM.7
    "hfc-134a": 1526.0,                   # Table 7.15
    "hfc-143": 364.0,                     # Table 7.SM.7
    "hfc-143a": 5810.0,                   # Table 7.SM.7
    "hfc-152a": 164.0,                    # Table 7.SM.7
    "hfc-245fa": 962.0,                   # Table 7.SM.7
}

# Target processes: USLCI's LCI_RESULT (pre-aggregated) chemical datasets
# that are (a) not copyright-protected and (b) have near-zero residual
# technosphere linkage. See the module docstring for the full reasoning,
# including why every unit-process chemical (toluene, methanol, etc.) is
# excluded outright.
TARGET_PROCESSES: dict[str, str] = {
    "e0368d96-44a3-3628-8220-e6ae975b0931": "Carbon monoxide",
    "136cbdd8-ef76-3834-904d-6fce42b2b660": "Ethylene oxide",
    "9ee66dd5-dcc9-3e94-9da3-3a7cc6cddeb3": "Hydrochloric acid",
}

# Hydrochloric acid also appears in data/factors/ademe_base_carbone.csv under
# the same CAS with a different value. It is ingested anyway: FactorTable now
# records such a disagreement as a Conflict and reports it, rather than
# refusing to load. Two independent public sources differing about the same
# substance is a measurement of how far public data spreads, and hiding it
# would throw that measurement away.
NOT_INGESTED_LCI_RESULTS: dict[str, str] = {}


#: Set once in main() to a live-or-offline Snapshot for the LCA Commons source.
_USLCI_SNAPSHOT: "Snapshot | None" = None
#: Shared with the other ingestion scripts: one PubChem cache for all of them.
_PUBCHEM_SNAPSHOT: "Snapshot | None" = None


def http_get(url: str, timeout: int = 60, cache_key: str | None = None) -> bytes:
    assert _USLCI_SNAPSHOT is not None, "main() must set up _USLCI_SNAPSHOT before fetching"
    return _USLCI_SNAPSHOT.fetch(
        url,
        headers={"User-Agent": "carbonroute-ingest/1.0 (research script; see scripts/ingest_uslci.py)"},
        timeout=timeout,
        cache_key=cache_key,
    )


def http_get_json(url: str, timeout: int = 60, cache_key: str | None = None) -> dict:
    return json.loads(http_get(url, timeout=timeout, cache_key=cache_key).decode("utf-8"))


# --------------------------------------------------------------------------
# LCA Commons client: fetch one process by UUID, with an on-disk cache
# keyed by (group, repo, refId) -- not by API key, so the cache is portable
# across DEMO_KEY and a personal key alike.
# --------------------------------------------------------------------------
class LcaCommonsClient:
    """LCA Commons access via the shared snapshot, with the API key redacted.

    The live URL carries ``?api_key=...`` and must never be written into
    ``data/raw/uslci/manifest.json`` — even DEMO_KEY being shared publicly is
    no excuse to commit a personal key by the same code path. The cache is
    keyed and labelled by the URL with the key replaced by a placeholder;
    the real key is only ever used for the live request itself.
    """

    def __init__(self, api_key: str):
        self.api_key = api_key

    def get_process(self, ref_id: str) -> tuple[dict, bool, str]:
        """Returns (process_json, from_cache, fetched_at_date)."""
        path = f"browse/{LCA_COMMONS_GROUP}/{LCA_COMMONS_REPO}/PROCESS/{ref_id}"
        cache_key = f"{LCA_COMMONS_BASE}/{path}?api_key=REDACTED"
        real_url = f"{LCA_COMMONS_BASE}/{path}?api_key={urllib.parse.quote(self.api_key)}"
        try:
            data = http_get_json(real_url, cache_key=cache_key)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")
            raise RuntimeError(
                f"LCA Commons request failed ({exc.code}) for process {ref_id}: {body}\n"
                "If this is OVER_RATE_LIMIT: DEMO_KEY allows 10 req/hour, 50 req/day, shared "
                "by every anonymous caller. Wait for the Retry-After window, or set "
                "USLCI_API_KEY to a personal key (free: https://api.data.gov/signup/)."
            ) from exc
        return data, False, date.today().isoformat()


# --------------------------------------------------------------------------
# PubChem, same small cache-and-rate-limit pattern as
# ingest_ademe_basecarbone.py's PubChemClient.
# --------------------------------------------------------------------------
class PubChemClient:
    """PubChem lookups via the shared, cross-script snapshot (see ademe script)."""

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
        data = self._get(f"compound/cid/{cid}/property/InChIKey,MolecularFormula/JSON")
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
class ProcessReport:
    ref_id: str
    name: str
    kept: Kept | None
    direct_ghg: list[tuple[str, float, float]]  # (flow name, amount kg, characterized kgCO2e/kg-ref)
    residual_technosphere: list[tuple[str, float, str]]  # (flow name, amount, unit)
    reason_dropped: str | None


def characterize_process(process: dict) -> tuple[float, list[tuple[str, float, float]], list[tuple[str, float, str]], float, str]:
    """Returns (total_gwp_per_ref_unit, ghg_contributions, residual_technosphere, ref_amount, ref_unit)."""
    ref_exchanges = [e for e in process.get("exchanges", []) if e.get("isQuantitativeReference")]
    if len(ref_exchanges) != 1:
        raise ValueError(f"expected exactly one reference exchange, found {len(ref_exchanges)}")
    ref = ref_exchanges[0]
    ref_amount = ref["amount"]
    ref_unit = ref["unit"]["name"]
    if ref_amount <= 0:
        raise ValueError(f"non-positive reference amount: {ref_amount}")

    contributions: list[tuple[str, float, float]] = []
    residual: list[tuple[str, float, str]] = []
    total = 0.0
    for e in process.get("exchanges", []):
        flow = e["flow"]
        if flow.get("flowType") == "ELEMENTARY_FLOW" and not e.get("isInput", False):
            key = flow["name"].strip().lower()
            factor = GWP100_KGCO2E_PER_KG.get(key)
            if factor is not None:
                per_ref = e["amount"] * factor / ref_amount
                total += per_ref
                contributions.append((flow["name"], e["amount"], per_ref))
        elif flow.get("flowType") == "PRODUCT_FLOW" and e.get("isInput", False):
            # A residual technosphere link inside a nominally "aggregated"
            # LCI_RESULT process: not resolved further (see module
            # docstring "RESIDUAL BOUNDARY"), just reported.
            residual.append((flow["name"], e["amount"], e["unit"]["name"]))

    return total, contributions, residual, ref_amount, ref_unit


def resolve_identity(display_name: str, pubchem: PubChemClient) -> tuple[str | None, str, str | None]:
    """Returns (cas, inchikey, rejection_reason)."""
    cids = pubchem.cids_for_name(display_name)
    if len(cids) != 1:
        return None, "", f"PubChem name lookup for {display_name!r} returned {len(cids)} CIDs (need exactly 1)"
    cid = cids[0]
    props = pubchem.properties(cid)
    inchikey = props.get("InChIKey", "")
    synonyms = pubchem.synonyms(cid)
    cas_candidates = [s for s in synonyms if CAS_RE.fullmatch(s)]
    if not cas_candidates:
        return None, inchikey, f"PubChem CID {cid} has no CAS-shaped synonym"
    first_cas = cas_candidates[0]
    if not cas_checksum_ok(first_cas):
        return None, inchikey, f"CAS candidate {first_cas!r} (PubChem CID {cid}) fails check digit"
    return first_cas, inchikey, None


def process_display_name(usda_process_name: str) -> str:
    # "Carbon monoxide, at plant" -> "Carbon monoxide"
    return usda_process_name.split(",")[0].strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--report", action="store_true", help="print kept vs. dropped rows with reasons")
    parser.add_argument(
        "--api-key",
        default=os.environ.get("USLCI_API_KEY", "DEMO_KEY"),
        help="api.data.gov key (default: $USLCI_API_KEY or the shared, low-quota DEMO_KEY)",
    )
    add_offline_flag(parser)
    args = parser.parse_args()

    global _USLCI_SNAPSHOT, _PUBCHEM_SNAPSHOT
    _USLCI_SNAPSHOT = Snapshot("uslci", offline=args.offline, rate_limit_seconds=1.0)
    _PUBCHEM_SNAPSHOT = Snapshot("pubchem", offline=args.offline, rate_limit_seconds=0.25)

    lca_client = LcaCommonsClient(args.api_key)
    pubchem = PubChemClient()

    reports: list[ProcessReport] = []
    kept: list[Kept] = []

    for ref_id, expected_name in TARGET_PROCESSES.items():
        process, from_cache, fetched_at = lca_client.get_process(ref_id)
        name = process.get("name", expected_name)
        doc = process.get("processDocumentation", {})

        if process.get("processType") != "LCI_RESULT":
            reports.append(ProcessReport(ref_id, name, None, [], [], f"processType is {process.get('processType')!r}, not LCI_RESULT (data changed since this script was written -- refusing to system-solve it here, see module docstring)"))
            continue
        if doc.get("isCopyrightProtected"):
            reports.append(ProcessReport(ref_id, name, None, [], [], "isCopyrightProtected is true"))
            continue

        total_gwp, contributions, residual, ref_amount, ref_unit = characterize_process(process)
        if ref_unit != "kg":
            reports.append(ProcessReport(ref_id, name, None, contributions, residual, f"reference unit is {ref_unit!r}, not kg -- cannot report as kgCO2e/kg without a mass conversion this script does not have"))
            continue

        display_name = process_display_name(name)
        cas, inchikey, reject_reason = resolve_identity(display_name, pubchem)
        if reject_reason:
            reports.append(ProcessReport(ref_id, name, None, contributions, residual, reject_reason))
            continue

        residual_note = ""
        if residual:
            parts = ", ".join(f"{amt:g} {unit} {rn}" for rn, amt, unit in residual)
            residual_note = f"; residual technosphere links not resolved (boundary: waste treatment excluded, cf. examples/route.yaml): {parts}"

        ghg_note = ", ".join(f"{rn}={amt:g}kg" for rn, amt, _ in contributions)
        version = process.get("version", "")
        last_change = process.get("lastChange", "")
        location = (process.get("location") or {}).get("name", "")
        publication = " ".join((doc.get("publication") or {}).get("name", "").split())

        k = Kept(
            identifier=cas,
            name=display_name,
            gwp_kgCO2e_per_kg=total_gwp,
            source=(
                f"US LCI Database (Federal LCA Commons), {LCA_COMMONS_GROUP}/{LCA_COMMONS_REPO}, "
                f"process {name!r} (UUID {ref_id}), LCI_RESULT dataset"
            ),
            database_version=f"process version {version}, last changed {last_change}",
            region=location,
            retrieved_date=fetched_at,
            uncertainty_class="background_db",
            license=LICENSE_SHORT,
            notes=(
                f"characterized from elementary-flow exchanges using IPCC AR6 GWP-100 "
                f"(see script docstring for exact table per gas): {ghg_note}"
                f"{residual_note}"
                + (f"; original publication cited by USLCI: {publication}" if publication else "")
            ),
            inchikey=inchikey,
            gsd="",
        )
        kept.append(k)
        reports.append(ProcessReport(ref_id, name, k, contributions, residual, None))

    kept.sort(key=lambda k: k.identifier)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="\n", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, lineterminator="\n")
        writer.writeheader()
        for k in kept:
            writer.writerow(
                {
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
                }
            )

    if args.report:
        print(f"LCA Commons repository: {LCA_COMMONS_GROUP}/{LCA_COMMONS_REPO}")
        print(f"Target LCI_RESULT processes probed: {len(TARGET_PROCESSES)}")
        for r in reports:
            print(f"\n--- {r.name} ({r.ref_id}) ---")
            if r.direct_ghg:
                for fname, amt, per_ref in r.direct_ghg:
                    print(f"   GHG  {fname:20s} {amt:12.6g} kg -> {per_ref:10.5f} kgCO2e/kg-ref")
            if r.residual_technosphere:
                for fname, amt, unit in r.residual_technosphere:
                    print(f"   [unresolved technosphere, excluded] {amt:g} {unit} {fname}")
            if r.kept:
                print(f"   KEPT: {r.kept.identifier}  {r.kept.name}  {r.kept.gwp_kgCO2e_per_kg:.5g} kgCO2e/kg")
            else:
                print(f"   DROPPED: {r.reason_dropped}")
        print("\nNOT_INGESTED_LCI_RESULTS (probed in earlier investigation, not re-fetched by this script):")
        for ref_id, reason in NOT_INGESTED_LCI_RESULTS.items():
            print(f"  {ref_id}: {reason}")
        print(f"\nWrote {len(kept)} rows to {args.out}")

    print(_USLCI_SNAPSHOT.describe())
    print(_PUBCHEM_SNAPSHOT.describe())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
