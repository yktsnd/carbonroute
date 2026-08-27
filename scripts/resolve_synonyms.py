"""Map the names a chemist writes onto the identifiers a factor table uses.

A ledger says `2-Me-THF`. A factor table says `2-methyltetrahydrofuran`. Nothing
in either file connects them, so the material goes unresolved and its mass drops
out of the comparison — the most expensive kind of gap, because the data was
there the whole time.

This script takes the unresolved names out of a ledger, asks PubChem what they
are, and writes the mapping down with the record that supports it. Every row
carries the PubChem CID it came from and the InChIKey that fixes the structure,
so the claim "these two names are the same substance" can be checked rather than
trusted. A name that does not resolve to exactly one compound, or whose CAS
fails its check digit, is reported and left out.

    PYTHONPATH=src python3 scripts/resolve_synonyms.py benchmarks/letermovir/ledger.yaml

Review the output before committing it. An alias is an identity claim about
chemistry, and a wrong one silently attributes one substance's footprint to
another.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from carbonroute.ledger import adjust_all, load_ledger  # noqa: E402
from carbonroute.resolve import FactorTable, resolve_materials  # noqa: E402
from carbonroute.schema import cas_checksum_ok, normalize_name  # noqa: E402

PUG = "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound"
CAS_RE = re.compile(r"^\d{2,7}-\d{2}-\d$")
COLUMNS = ("alias", "identifier", "inchikey", "source", "retrieved_date", "notes")
_CACHE: dict[str, object] = {}


def _get(url: str):
    if url in _CACHE:
        return _CACHE[url]
    time.sleep(0.25)  # PubChem asks for no more than 5 requests a second
    req = urllib.request.Request(url, headers={"User-Agent": "carbonroute-synonyms/0.1"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        payload = json.load(resp)
    _CACHE[url] = payload
    return payload


def spelling_variants(name: str) -> list[str]:
    """Purely orthographic rewrites of a name, in the order they are tried.

    A ledger writes "2-Me-THF" and "2- picoline"; PubChem indexes "2-MeTHF" and
    "2-picoline". Closing that distance is punctuation, not chemistry: nothing
    here changes a substituent, a locant or a parent. The variant that matched
    is recorded on the row, so a reviewer can see exactly what was asked.
    """
    variants = [name]
    collapsed = re.sub(r"\s*-\s*", "-", name.strip())
    variants += [
        collapsed,
        re.sub(r"\s+", "-", collapsed),
        re.sub(r"\s+", "", collapsed),
    ]
    # "2-Me-THF" -> "2-MeTHF": drop the last internal hyphen only.
    if collapsed.count("-") > 1:
        head, _, tail = collapsed.rpartition("-")
        variants.append(head + tail)
    seen, ordered = set(), []
    for v in variants:
        if v and v not in seen:
            seen.add(v)
            ordered.append(v)
    return ordered


def resolve(name: str) -> tuple[dict | None, str]:
    cids, used, failures = None, name, []
    for variant in spelling_variants(name):
        quoted = urllib.parse.quote(variant, safe="")
        try:
            found = _get(f"{PUG}/name/{quoted}/cids/JSON")["IdentifierList"]["CID"]
        except Exception as exc:  # noqa: BLE001 - any failure means "not this spelling"
            failures.append(f"{variant!r}: {type(exc).__name__}")
            continue
        if len(found) != 1:
            failures.append(f"{variant!r}: {len(found)} compounds, ambiguous")
            continue
        cids, used = found, variant
        break
    if cids is None:
        return None, "PubChem matched no spelling — " + "; ".join(failures)
    cid = cids[0]
    props = _get(f"{PUG}/cid/{cid}/property/InChIKey/JSON")["PropertyTable"]["Properties"][0]
    synonyms = _get(f"{PUG}/cid/{cid}/synonyms/JSON")["InformationList"]["Information"][0][
        "Synonym"
    ]
    cas_candidates = [s for s in synonyms if CAS_RE.fullmatch(s)]
    if not cas_candidates:
        return None, f"PubChem CID {cid} lists no CAS-shaped synonym"
    cas = cas_candidates[0]
    if not cas_checksum_ok(cas):
        return None, f"first CAS candidate {cas} fails its check digit"
    return {
        "alias": name,
        "identifier": cas,
        "inchikey": props["InChIKey"],
        "source": f"PubChem CID {cid} ({PUG}/cid/{cid}/synonyms/JSON)",
        "retrieved_date": date.today().isoformat(),
        "notes": (
            f"queried PubChem as {used!r}"
            + ("" if used == name else " (orthographic variant of the ledger name)")
            + f"; other CAS candidates: {', '.join(cas_candidates[1:5]) or 'none'}"
        ),
    }, ""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("ledger", help="ledger whose unresolved names should be looked up")
    ap.add_argument("--factors", action="append", default=None)
    ap.add_argument("--out", default="data/synonyms/pubchem.csv")
    args = ap.parse_args()

    factor_paths = [Path(p) for p in (args.factors or [])] or sorted(
        (ROOT / "data" / "factors").glob("*.csv")
    )
    table = FactorTable.load(factor_paths)

    ledger = load_ledger(args.ledger)
    unresolved: dict[str, str] = {}
    for adjusted in adjust_all(ledger).values():
        for key, res in resolve_materials(adjusted.materials, table).items():
            if not res.resolved:
                unresolved.setdefault(res.name, key)

    out = Path(args.out)
    existing: dict[str, dict] = {}
    if out.exists():
        with out.open(encoding="utf-8") as fh:
            existing = {normalize_name(r["alias"]): r for r in csv.DictReader(fh)}

    added, skipped = [], []
    for name in sorted(unresolved):
        if normalize_name(name) in existing:
            continue
        row, reason = resolve(name)
        if row is None:
            skipped.append((name, reason))
            continue
        # Only useful if the identifier it points at is actually in a table;
        # record the rest so a later run picks them up when data arrives.
        row["notes"] += "; target present in factor tables" if (
            f"cas:{row['identifier']}" in table.by_key
        ) else "; no factor for this identifier yet"
        added.append(row)
        existing[normalize_name(name)] = row

    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="\n") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(COLUMNS), lineterminator="\n")
        writer.writeheader()
        for key in sorted(existing):
            writer.writerow({c: existing[key].get(c, "") for c in COLUMNS})

    print(f"unresolved names in {args.ledger}: {len(unresolved)}")
    print(f"newly mapped: {len(added)}; already known: {len(existing) - len(added)}")
    for row in added:
        print(f"  + {row['alias']} -> {row['identifier']} ({row['notes'].split(';')[-1].strip()})")
    for name, reason in skipped:
        print(f"  - {name}: {reason}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
