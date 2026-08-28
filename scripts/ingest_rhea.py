"""Ingest the Rhea reaction database, and measure the cofactor vocabulary.

Source
------
  Landing page : https://www.rhea-db.org/
  REST API     : https://www.rhea-db.org/rhea?query=...&columns=...&format=tsv
  Bulk TSVs    : https://ftp.expasy.org/databases/rhea/tsv/

Rhea is an expert-curated, manually annotated database of biochemical
reactions, produced by the SIB Swiss Institute of Bioinformatics with the
EBI and released under **CC BY 4.0** (stated on the Rhea site's licence
page and in its FTP README). Reaction participants are ChEBI identifiers,
so every reaction is a fully specified, balanced chemical equation, not
free text.

Why this project ingests it
---------------------------
`carbonroute` compares two synthetic routes to the same product. A common
and commercially real version of that question is "enzyme or chemistry?",
and answering it one molecule at a time does not scale: Rhea alone holds
~18,500 reactions.

What makes it scale is a structural property of the *comparison*, not of
the chemistry. In a diff of two routes to the same product, everything
common to both routes cancels (spec section 7.4) — the substrate and the
product largely do. What survives into the delta set is:

  - on the enzymatic side: the **cofactor** (NADPH, SAM, UDP-glucose, ...)
  - on the chemical side: the **protecting groups, activator and solvents**

Both are small, closed vocabularies that recur across thousands of
reactions. This script measures the first one directly, rather than
asserting it: it counts how many distinct Rhea reactions each ChEBI
participant appears in, and writes the ranked result. The measured
distribution is extremely concentrated — see `data/rhea/README.md` for the
numbers this produced — which is what makes a database-wide screen a
bounded amount of factor work instead of an unbounded one.

Outputs (all under `data/rhea/`)
--------------------------------
  reactions.tsv          one row per Rhea reaction: id, equation, ChEBI
                         participants, EC number
  participants.csv       every ChEBI participant, with the number of
                         distinct reactions it appears in, ranked
  README.md is written by hand, not by this script.

Licence note
------------
Rhea's own content is CC BY 4.0 and is redistributed here with attribution.
ChEBI (EMBL-EBI) is CC BY 4.0 as well. Both are credited in
`data/rhea/README.md`.

Requires network access to www.rhea-db.org and ftp.expasy.org, unless
`--offline` is given (see `scripts/_snapshot.py` and
`docs/reproducibility.md`).
"""

from __future__ import annotations

import argparse
import collections
import csv
import io
import sys
from pathlib import Path

from _snapshot import REPO_ROOT, Snapshot, SnapshotError, add_offline_flag

RHEA_API = "https://www.rhea-db.org/rhea"
RHEA_FTP = "https://ftp.expasy.org/databases/rhea/tsv"
OUT_DIR = REPO_ROOT / "data" / "rhea"

#: Rhea's REST API caps a single response; this is comfortably above the
#: ~18.5k reactions it currently holds, and is checked against the returned
#: row count so a silent truncation cannot pass unnoticed.
FETCH_LIMIT = 100000

USER_AGENT = (
    "carbonroute-ingest/1.0 (research script; see repo scripts/ingest_rhea.py)"
)


def fetch_reactions(snap: Snapshot) -> list[dict]:
    """Every Rhea reaction with its equation, ChEBI participants and EC number."""
    url = (
        f"{RHEA_API}?query=*&columns=rhea-id,equation,chebi-id,ec"
        f"&format=tsv&limit={FETCH_LIMIT}"
    )
    raw = snap.fetch(url, headers={"User-Agent": USER_AGENT}, timeout=300)
    text = raw.decode("utf-8")
    rows = list(csv.DictReader(io.StringIO(text), delimiter="\t"))
    if not rows:
        raise SnapshotError("Rhea returned no reactions; refusing to write an empty table")
    if len(rows) >= FETCH_LIMIT:
        raise SnapshotError(
            f"Rhea returned exactly the requested limit ({FETCH_LIMIT} rows), which "
            "means the response was probably truncated. Raise FETCH_LIMIT and re-run."
        )
    return rows


def fetch_chebi_names(snap: Snapshot) -> dict[str, str]:
    """ChEBI id -> display name, from Rhea's own bundled mapping."""
    raw = snap.fetch(
        f"{RHEA_FTP}/chebiId_name.tsv", headers={"User-Agent": USER_AGENT}, timeout=120
    )
    names: dict[str, str] = {}
    for row in csv.reader(io.StringIO(raw.decode("utf-8")), delimiter="\t"):
        if len(row) >= 2:
            names[row[0]] = row[1]
    return names


def fetch_chebi_smiles(snap: Snapshot) -> dict[str, str]:
    """ChEBI id -> SMILES, from Rhea's own bundled structures.

    Structures matter for the chemical side of a comparison: the number of
    protectable groups on a substrate is what sets how many protect/deprotect
    steps a chemical route needs, and that is read off the structure.
    """
    raw = snap.fetch(
        f"{RHEA_FTP}/rhea-chebi-smiles.tsv", headers={"User-Agent": USER_AGENT}, timeout=180
    )
    smiles: dict[str, str] = {}
    for row in csv.reader(io.StringIO(raw.decode("utf-8")), delimiter="\t"):
        if len(row) >= 2:
            smiles[row[0]] = row[1]
    return smiles


def write_reactions(rows: list[dict], path: Path) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, delimiter="\t")
        w.writerow(["rhea_id", "equation", "chebi_ids", "ec"])
        for row in rows:
            w.writerow(
                [
                    row.get("Reaction identifier", ""),
                    row.get("Equation", ""),
                    row.get("ChEBI identifier", ""),
                    row.get("EC number", ""),
                ]
            )
    return len(rows)


def participant_frequency(rows: list[dict]) -> collections.Counter:
    """How many distinct reactions each ChEBI participant appears in.

    Counted per reaction, not per occurrence: a species on both sides of an
    equation counts once, so the ranking measures *how many transformations
    a factor would serve*, which is the quantity that decides how much
    factor work a database-wide screen actually costs.
    """
    freq: collections.Counter = collections.Counter()
    for row in rows:
        ids = {c for c in (row.get("ChEBI identifier") or "").split(";") if c}
        for chebi in ids:
            freq[chebi] += 1
    return freq


def write_participants(
    freq: collections.Counter,
    names: dict[str, str],
    smiles: dict[str, str],
    n_reactions: int,
    path: Path,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["chebi_id", "name", "n_reactions", "share_of_reactions", "smiles"])
        for chebi, count in freq.most_common():
            w.writerow(
                [
                    chebi,
                    names.get(chebi, ""),
                    count,
                    f"{count / n_reactions:.6f}",
                    smiles.get(chebi, ""),
                ]
            )


def report_concentration(freq: collections.Counter, rows: list[dict]) -> None:
    """Print the measurement that justifies screening the whole database.

    Not a claim, a count: how much of the participant vocabulary a given
    number of factors would cover.
    """
    total_slots = sum(
        len({c for c in (r.get("ChEBI identifier") or "").split(";") if c}) for r in rows
    )
    print(f"\nreactions: {len(rows)}")
    print(f"distinct ChEBI participants: {len(freq)}")
    print(f"participant slots (reaction x distinct species): {total_slots}")
    print("\nhow many species recur:")
    for k in (5, 10, 25, 50, 100, 500, 1000):
        print(f"  in >= {k:5d} reactions: {sum(1 for v in freq.values() if v >= k):6d} species")
    print("\ncumulative coverage of all participant slots:")
    for k in (10, 30, 60, 120, 300):
        top = {c for c, _ in freq.most_common(k)}
        covered = sum(
            1
            for r in rows
            for c in {c for c in (r.get("ChEBI identifier") or "").split(";") if c}
            if c in top
        )
        print(f"  top {k:4d} species: {covered / total_slots * 100:5.1f}%")
    print(
        "\nThe uncovered remainder is dominated by each reaction's own substrate "
        "and product,\nwhich cancel out of a same-product route comparison and so "
        "need no factor at all."
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    add_offline_flag(parser)
    parser.add_argument(
        "-o",
        "--out-dir",
        type=Path,
        default=OUT_DIR,
        help="Directory to write reactions.tsv and participants.csv into.",
    )
    args = parser.parse_args()

    snap = Snapshot(source="rhea", offline=args.offline)

    try:
        rows = fetch_reactions(snap)
        names = fetch_chebi_names(snap)
        smiles = fetch_chebi_smiles(snap)
    except SnapshotError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    n = write_reactions(rows, args.out_dir / "reactions.tsv")
    freq = participant_frequency(rows)
    write_participants(freq, names, smiles, n, args.out_dir / "participants.csv")

    print(f"wrote {n} reaction(s) to {args.out_dir / 'reactions.tsv'}")
    print(f"wrote {len(freq)} participant(s) to {args.out_dir / 'participants.csv'}")
    report_concentration(freq, rows)
    print(f"\n{snap.describe()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
