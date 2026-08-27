"""Build an emission-factor table from publisher-issued PCFs and association
eco-profiles (Product Carbon Footprints, EPDs, industry eco-profiles) for
process solvents and bulk chemicals.

Unlike the other `ingest_*` scripts in this repo, this lane's numbers are not
behind a queryable database API -- they live inside PDF reports published by
trade associations (PlasticsEurope/CEFIC) and individual producers (Nobian,
via the EPD International registry). So this script carries a declarative
table of citations (see ROWS below) rather than computing anything from a
live query. What makes that acceptable, per this project's rules, is that
every row was reached by actually downloading and reading the cited PDF
(with `pdftotext -layout`, transcript kept in the scratch dir this session
used) -- never guessed from a search snippet or a summary -- and this script
re-fetches every cited URL on every run and reports whether it is still
reachable, so the table stays checkable by a third party. See
`data/factors/published_pcf.SOURCES.md` for the full per-row citation
(publisher, document title, page/table, licence) and for every candidate
that was investigated and rejected, with the reason.

WHERE THESE FIVE SUBSTANCES CAME FROM
--------------------------------------
1. Toluene and Benzene: PlasticsEurope & CEFIC/APPE "Eco-profile and EPD:
   Benzene, Toluene, and Xylenes (Aromatics, BTX)", February 2013. Table 19
   (p.32) gives cradle-to-gate GWP-100 per kg of product, built from
   confidential primary process/emission data from ~50 European steam
   cracker sites (2007-2010) plus representative literature for the BTX
   extraction step -- not an ecoinvent/GaBi lookup (the report says so of
   itself; see SOURCES.md). Boundary: crude oil extraction to liquid BTX at
   plant; use phase and end-of-life explicitly excluded.
   Retrieved via: legacy.plasticseurope.org's eco-profiles flowchart page,
   which (unlike plasticseurope.org itself) is not bot-blocked; the
   flowchart's "toluene"/"benzene" boxes link to /download_file/<id>/0
   zip bundles containing the PDF report plus EcoSpold/Excel/ILCD exports.

2. Ammonia and Hydrogen (steam-reforming route): PlasticsEurope Eco-profiles
   "Ammonia" and "H2 reformer" (I. Boustead, for PlasticsEurope; data
   calculated March 2005, process data ~2001). Each report's Table 7 sums
   the CO2-equivalents of gross air emissions per kg of product at a
   100-year horizon; that "100 year equiv" total row is the cradle-to-gate
   GWP used here. These are older reports (pre-dating the BTX report's
   explicit methodology chapter) but PlasticsEurope's own methodology
   document (fetched live, see SOURCES.md) states the programme's standing
   practice is primary data collection from member-company questionnaires
   for the foreground process -- consistent with what these Boustead-era
   reports say of themselves. A second PlasticsEurope hydrogen value exists
   (naphtha-cracker by-product H2, 1.7 kgCO2e/kg, a different
   co-product-allocated route) and was deliberately NOT used here; see
   SOURCES.md for why the steam-reforming number was preferred.

3. Dichloromethane (methylene chloride): Nobian Industrial Chemicals B.V.,
   EPD "Methylene Chloride ISCC PLUS certified" (EPD-IES-0022304:001),
   published via EPD International (environdec.com), 2025-12-05. This is a
   genuine single-producer PCF (Frankfurt, Germany plant), third-party
   reviewed under ISO 14025 / PCR 2021:03 Basic Chemicals, declared unit
   1 kg, module A1-A3 ("Cradle to gate") reported separately from module A4
   (downstream transport) -- the A1-A3 figure is what is used here.

WHAT WAS REJECTED, AND WHY (full detail in SOURCES.md)
---------------------------------------------------------
- Phenol and Acetone: PlasticsEurope/CEFIC "Phenol and Acetone" EPD
  (Sept 2016) explicitly states its own LCI is "not based on primary
  industry data but solely on literature data" sourced from the GaBi 2015
  database -- exactly what this project's rules say to reject. Both
  candidate numbers (1.79 and 1.64 kgCO2e/kg) were read from the PDF and
  then discarded for this reason.
- HSPA/PlasticsEurope "Category 1/2/3/6/8 Hydrocarbon Solvents" eco-profiles
  (ESIG/HSPA, 2021-2024): these cover blended, UVCB market-mix solvent
  products (e.g. "white spirit", "C6 aliphatics"), not single named
  substances with their own CAS on this project's target list -- not used.
- IMPCA "Methanol carbon footprint and certification Guidance" (May 2022):
  a parametrised calculation tool with generic/default modelling
  assumptions ("non-verified, user-specified inputs" per the tool's own
  disclaimer), not a single verified published figure, and its headline
  "~2.2 kgCO2e/kg" number is itself a footnoted reference to yet another
  source, not IMPCA's own primary result -- not used.
- Fertilizers Europe "Carbon footprint of fertiliser production" regional
  reference report: gives ammonia *energy consumption* (GJ/tonne) by
  region, not a direct published GWP per kg of ammonia; turning that into a
  number would mean this script choosing its own emission factors, which
  the project's rules treat as fabrication -- not used.
- BASF press release on rPCF variants of BDO/THF/PolyTHF/NMP (2026-03):
  states only a *relative* reduction ("at least 10 percent lower") versus
  BASF's own standard product; no absolute kgCO2e/kg figure is disclosed
  publicly (individual PCF values sit behind BASF's customer PCF portal,
  not a public document) -- not used.

CAS/InChIKey RESOLUTION
------------------------
Every identifier below was resolved live via PubChem PUG REST
(name -> CID -> InChIKey, and CID -> synonyms to confirm the CAS appears as
a synonym) during this investigation, and every CAS passed
`carbonroute.schema.cas_checksum_ok`. By default this script re-does the
PubChem InChIKey lookup on every run (best-effort: a network hiccup or rate
limit is reported, not fatal, since the expected InChIKey is pinned in this
file from that earlier successful resolution); pass --skip-pubchem to skip
it entirely (e.g. offline re-runs).

HOW TO RE-RUN
--------------
    PYTHONPATH=src python3 scripts/ingest_published_pcf.py \\
        [--out data/factors/published_pcf.csv] [--report] [--skip-pubchem]

Requires network access to legacy.plasticseurope.org, api.prod.environdec.com,
and (unless --skip-pubchem) pubchem.ncbi.nlm.nih.gov.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from carbonroute.schema import cas_checksum_ok  # noqa: E402

DEFAULT_OUT = REPO_ROOT / "data" / "factors" / "published_pcf.csv"
PUBCHEM_BASE = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"
USER_AGENT = "Mozilla/5.0 (carbonroute published-pcf ingest)"

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

RETRIEVED_DATE = "2026-08-27"

_ECOPROFILES_LICENSE = (
    "PlasticsEurope Eco-profiles: \"This page enables free download and use "
    "of PlasticsEurope's Eco-profiles\" (legacy.plasticseurope.org/en/"
    "resources/eco-profiles, retrieved live 2026-08-27); no further reuse "
    "restriction stated on the download page or in the PDF itself."
)
_NOBIAN_EPD_LICENSE = (
    "EPD International AB / International EPD System, ISO 14025:2006 "
    "registered and third-party-verified Environmental Product Declaration, "
    "EPD Owner Nobian Industrial Chemicals B.V.; published for free public "
    "download and reference/attribution use at environdec.com/library/"
    "epd22304 (see EPD General Programme Instructions for reuse terms)."
)


@dataclass(frozen=True)
class SourceRow:
    identifier: str  # CAS
    name: str
    gwp: float
    source: str
    database_version: str
    region: str
    uncertainty_class: str
    license: str
    notes: str
    inchikey: str  # expected, from a live PubChem resolution (see docstring)
    verify_url: str  # exact document URL this script re-fetches each run
    verify_what: str  # human-readable description of what verify_url is


ROWS: tuple[SourceRow, ...] = (
    SourceRow(
        identifier="71-43-2",
        name="Benzene",
        gwp=1.86,
        source=(
            "PlasticsEurope & CEFIC/APPE, 'Eco-profile and EPD: Benzene, "
            "Toluene, and Xylenes (Aromatics, BTX)', February 2013, Table 19 "
            "(PDF p.32) and Environmental Performance table (PDF p.4)"
        ),
        database_version="PlasticsEurope BTX Eco-profile 2013-02",
        region="EU27 + Norway",
        uncertainty_class="literature",
        license=_ECOPROFILES_LICENSE,
        notes=(
            "Cradle-to-gate (crude oil/natural gas extraction to liquid "
            "benzene at plant); use phase and end-of-life outside system "
            "boundary. Reference year 2010; data collection 2007-2010; "
            "calculated Feb 2013. GWP-100, IPCC 2007 (AR4) characterisation "
            "factors, as stated in the report. Built from confidential "
            "primary process/emission data from ~50 European steam cracker "
            "sites plus representative literature for BTX extraction from "
            "pygas/reformate; not an ecoinvent/GaBi lookup (report states "
            "its own data sourcing)."
        ),
        inchikey="UHOVQNZJYSORNB-UHFFFAOYSA-N",
        verify_url="https://legacy.plasticseurope.org/download_file/781/0",
        verify_what="zip bundle containing the BTX Eco-profile PDF (benzene box)",
    ),
    SourceRow(
        identifier="75-09-2",
        name="Dichloromethane",
        gwp=0.48,
        source=(
            "Nobian Industrial Chemicals B.V., EPD 'Methylene Chloride ISCC "
            "PLUS certified' (registration EPD-IES-0022304:001), EPD "
            "International, published 2025-12-05, Table 1, 'Cradle to gate' "
            "column, row 'GWP - total (excl. biogenic)' (PDF p.8); also "
            "stated as the report's own headline figure: '4.80E-01 CO2-eq / "
            "kg ISCC PLUS certified methylene chloride'"
        ),
        database_version="EPD-IES-0022304:001",
        region="Germany (Frankfurt plant); declared geographical scope Global",
        uncertainty_class="supplier",
        license=_NOBIAN_EPD_LICENSE,
        notes=(
            "Cradle-to-gate (EN15804+A2 modules A1 upstream + A2-A3 core), "
            "declared unit 1 kg methylene chloride (CH2Cl2), excluding "
            "biogenic CO2-eq per the report's own stated convention; module "
            "A4 (downstream transport to customers, 0.0506 kgCO2e/kg) is "
            "reported separately in the source and deliberately excluded "
            "here to keep the value at the plant gate. ISCC PLUS mass-"
            "balance certified feedstock and renewable electricity input. "
            "PCR Basic Chemicals 2021:03 v1.1.5. EPD publication date "
            "2025-12-05, valid until 2030-10-20."
        ),
        inchikey="YMWUJEATGCHHMB-UHFFFAOYSA-N",
        verify_url=(
            "https://api.prod.environdec.com/api/v1/EPDLibrary/Files/EPDs/"
            "4a04bf22-a0fc-4ca2-6169-08dd7d87b4f5/Documents"
        ),
        verify_what="the EPD PDF itself, served directly by EPD International's API",
    ),
    SourceRow(
        identifier="108-88-3",
        name="Toluene",
        gwp=1.22,
        source=(
            "PlasticsEurope & CEFIC/APPE, 'Eco-profile and EPD: Benzene, "
            "Toluene, and Xylenes (Aromatics, BTX)', February 2013, Table 19 "
            "(PDF p.32) and Environmental Performance table (PDF p.4)"
        ),
        database_version="PlasticsEurope BTX Eco-profile 2013-02",
        region="EU27 + Norway",
        uncertainty_class="literature",
        license=_ECOPROFILES_LICENSE,
        notes=(
            "Cradle-to-gate (crude oil/natural gas extraction to liquid "
            "toluene at plant); use phase and end-of-life outside system "
            "boundary. Reference year 2010; data collection 2007-2010; "
            "calculated Feb 2013. GWP-100, IPCC 2007 (AR4) characterisation "
            "factors, as stated in the report. Built from confidential "
            "primary process/emission data from ~50 European steam cracker "
            "sites plus representative literature for BTX extraction from "
            "pygas/reformate; not an ecoinvent/GaBi lookup (report states "
            "its own data sourcing)."
        ),
        inchikey="YXFVVABEGXRONW-UHFFFAOYSA-N",
        verify_url="https://legacy.plasticseurope.org/download_file/786/0",
        verify_what="zip bundle containing the BTX Eco-profile PDF (toluene box)",
    ),
    SourceRow(
        identifier="1333-74-0",
        name="Hydrogen",
        gwp=7.5,
        source=(
            "PlasticsEurope Eco-profile 'H2 reformer' (I. Boustead, for "
            "PlasticsEurope), data last calculated March 2005, Table 7, row "
            "'100 year equiv', 'Totals' column (PDF p.8)"
        ),
        database_version="PlasticsEurope H2 reformer Eco-profile, calculated 2005-03",
        region="Europe (process data ~2001)",
        uncertainty_class="literature",
        license=_ECOPROFILES_LICENSE,
        notes=(
            "Cradle-to-gate production of 1 kg hydrogen via steam methane "
            "reforming, the route linked (in PlasticsEurope's own eco-"
            "profile flowchart) to the Ammonia eco-profile's feedstock "
            "hydrogen. Table 7 sums CO2-equivalents of gross air emissions "
            "per kg product at a 100-year horizon; the pre-AR6/AR5 "
            "characterisation set used is not restated in this document. "
            "Process data ~2001; calculated 2005. A second PlasticsEurope "
            "hydrogen figure exists for naphtha-cracker by-product hydrogen "
            "(1.7 kgCO2e/kg, different co-product allocation) and was NOT "
            "used here -- see published_pcf.SOURCES.md."
        ),
        inchikey="UFHFLCQGNIYNRP-UHFFFAOYSA-N",
        verify_url="https://legacy.plasticseurope.org/download_file/780/0",
        verify_what="zip bundle containing the H2 reformer Eco-profile PDF",
    ),
    SourceRow(
        identifier="7664-41-7",
        name="Ammonia",
        gwp=2.4,
        source=(
            "PlasticsEurope Eco-profile 'Ammonia' (I. Boustead, for "
            "PlasticsEurope), data last calculated March 2005, Table 7, row "
            "'100 year equiv', 'Totals' column (PDF p.7-8)"
        ),
        database_version="PlasticsEurope Ammonia Eco-profile, calculated 2005-03",
        region="Europe (process data ~2001)",
        uncertainty_class="literature",
        license=_ECOPROFILES_LICENSE,
        notes=(
            "Cradle-to-gate production of 1 kg ammonia (steam reforming of "
            "natural gas for hydrogen + air separation for nitrogen). "
            "Table 7 sums CO2-equivalents of gross air emissions per kg "
            "product at a 100-year horizon; the pre-AR6/AR5 "
            "characterisation set used is not restated in this document. "
            "Process data ~2001; calculated 2005. PlasticsEurope's own "
            "methodology document states the programme's standing practice "
            "is primary data collection from member-company questionnaires "
            "for the foreground process."
        ),
        inchikey="QGZKDVFQNNGYKY-UHFFFAOYSA-N",
        verify_url="https://legacy.plasticseurope.org/download_file/779/0",
        verify_what="zip bundle containing the Ammonia Eco-profile PDF",
    ),
)


def _http_reachable(url: str, timeout: float = 20.0) -> tuple[bool, str]:
    """Best-effort liveness check for a citation URL.

    Tries HEAD first (cheap); falls back to a GET that reads only a small
    prefix of the body, since some of these endpoints (legacy PHP app,
    environdec's file API) reject HEAD with 405 but serve GET fine. Returns
    (reachable, human-readable status string) -- never raises.
    """
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT}, method="HEAD")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return True, f"HTTP {resp.status} (HEAD)"
    except urllib.error.HTTPError as exc:
        if exc.code not in (403, 405, 501):
            return False, f"HTTP {exc.code} (HEAD)"
    except Exception as exc:  # noqa: BLE001 - report, don't crash the run
        pass

    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            resp.read(256)  # just confirm the body starts streaming
            return True, f"HTTP {resp.status} (GET)"
    except urllib.error.HTTPError as exc:
        return False, f"HTTP {exc.code} (GET)"
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"


def _pubchem_inchikey(name: str, timeout: float = 20.0) -> str | None:
    url = f"{PUBCHEM_BASE}/compound/name/{urllib.parse.quote(name)}/property/InChIKey/JSON"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
        return data["PropertyTable"]["Properties"][0]["InChIKey"]
    except Exception:  # noqa: BLE001 - best-effort, see docstring
        return None


def build_rows(check_pubchem: bool, check_reachability: bool, report: bool) -> list[SourceRow]:
    kept: list[SourceRow] = []
    for row in sorted(ROWS, key=lambda r: r.identifier):
        if not cas_checksum_ok(row.identifier):
            print(f"REJECT {row.name} ({row.identifier}): fails CAS checksum", file=sys.stderr)
            continue

        if check_reachability:
            reachable, status = _http_reachable(row.verify_url)
        else:
            reachable, status = True, "not checked (--offline)"
        pubchem_note = "skipped"
        if check_pubchem:
            key = _pubchem_inchikey(row.name)
            if key is None:
                pubchem_note = "lookup failed (network/rate-limit) -- not fatal, InChIKey pinned from earlier resolution"
            elif key != row.inchikey:
                pubchem_note = f"MISMATCH: PubChem now says {key}, pinned value is {row.inchikey}"
                print(
                    f"WARNING {row.name} ({row.identifier}): {pubchem_note}",
                    file=sys.stderr,
                )
            else:
                pubchem_note = f"confirmed ({key})"

        if report:
            print(
                f"{row.identifier:12s} {row.name:20s} gwp={row.gwp:>6.2f}  "
                f"url-reachable={reachable} [{status}]  pubchem={pubchem_note}  "
                f"({row.verify_what})"
            )
        if not reachable:
            print(
                f"WARNING {row.name} ({row.identifier}): citation URL is not currently "
                f"reachable ({status}) -- keeping the row (it was read and transcribed "
                f"live during this investigation) but this needs re-checking: "
                f"{row.verify_url}",
                file=sys.stderr,
            )
        kept.append(row)
    return kept


def write_csv(rows: list[SourceRow], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="\n", encoding="utf-8") as fh:
        writer = csv.writer(fh, lineterminator="\n")
        writer.writerow(CSV_COLUMNS)
        for row in rows:
            writer.writerow(
                [
                    row.identifier,
                    row.name,
                    f"{row.gwp:g}",
                    row.source,
                    row.database_version,
                    row.region,
                    RETRIEVED_DATE,
                    row.uncertainty_class,
                    row.license,
                    row.notes,
                    row.inchikey,
                    "",  # gsd: none of these sources publish an uncertainty
                ]
            )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="output CSV path")
    parser.add_argument(
        "--report", action="store_true", help="print per-row reachability/PubChem status"
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Touch no network at all: skip both the PubChem re-confirmation and the "
        "citation-URL reachability check. The GWP values themselves are a declarative "
        "table baked into this script, cited to a document, not fetched -- this flag "
        "only affects the two live re-verification steps, matching the meaning of "
        "--offline in this project's other ingestion scripts.",
    )
    parser.add_argument(
        "--skip-pubchem",
        action="store_true",
        help="skip the live PubChem InChIKey re-check (offline re-runs)",
    )
    args = parser.parse_args()

    rows = build_rows(
        check_pubchem=not args.skip_pubchem and not args.offline,
        check_reachability=not args.offline,
        report=args.report,
    )
    if not rows:
        print("No rows survived validation -- refusing to write an empty table", file=sys.stderr)
        return 1

    write_csv(rows, args.out)
    print(f"Wrote {len(rows)} rows to {args.out} (retrieved_date={RETRIEVED_DATE})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
