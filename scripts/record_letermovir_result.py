"""Regenerate benchmarks/letermovir/RESULTS.json.

The B2 benchmark's numbers move whenever the factor tables grow, which is the
point of it. Freezing them inside an assertion means every improvement looks
like a broken test. They live in a data file instead, and updating that file is
a deliberate, reviewable act: run this script, read the diff, and say in the
commit message which source moved the number.

    PYTHONPATH=src python3 scripts/record_letermovir_result.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from carbonroute.compute import (  # noqa: E402
    coverage,
    diff_routes,
    run_comparison,
    unresolved_flip_factor,
)
from carbonroute.ledger import adjust_all, load_ledger  # noqa: E402
from carbonroute.resolve import FactorTable, resolve_materials  # noqa: E402
from carbonroute.uncertainty import load_uncertainty  # noqa: E402

LEDGER = ROOT / "benchmarks" / "letermovir" / "ledger.yaml"
OUT = ROOT / "benchmarks" / "letermovir" / "RESULTS.json"


def main() -> None:
    ledger = load_ledger(LEDGER)
    table = FactorTable.load(sorted((ROOT / "data" / "factors").glob("*.csv")))
    comparison = run_comparison(ledger, "merck", "denovo", table, load_uncertainty())

    adjusted = adjust_all(ledger)
    resolutions = {}
    for adj in adjusted.values():
        resolutions.update(resolve_materials(adj.materials, table))
    cov = coverage(diff_routes(adjusted["merck"], adjusted["denovo"], resolutions))
    flip = unresolved_flip_factor(comparison.diff, comparison.assumptions)

    payload = {
        "_comment": (
            "Regenerate with scripts/record_letermovir_result.py. These numbers "
            "are expected to move as data/factors grows; that is the benchmark "
            "working, not failing."
        ),
        "factor_tables": sorted(Path(p).name for p in table.sources),
        "factor_fingerprint": table.fingerprint(),
        "delta_material_count": cov.delta_material_count,
        "resolved_count": cov.resolved_count,
        "coverage_count_fraction": cov.count_fraction,
        "coverage_mass_fraction": cov.mass_fraction,
        "verdict": comparison.stats.verdict,
        "indeterminate_reason": comparison.stats.indeterminate_reason,
        "p_a_lower_resolved_part_only": comparison.stats.p_a_lower,
        "resolved_delta_kgCO2e": flip.resolved_delta_kgCO2e,
        "unresolved_delta_mass_kg": flip.unresolved_delta_mass_kg,
        "breakeven_kgCO2e_per_kg": flip.breakeven_kgCO2e_per_kg,
        "accounted_total_merck_kgCO2e": comparison.a.total_kgCO2e,
        "accounted_total_denovo_kgCO2e": comparison.b.total_kgCO2e,
    }
    OUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {OUT}")
    for k in ("coverage_mass_fraction", "verdict", "breakeven_kgCO2e_per_kg"):
        print(f"  {k}: {payload[k]}")


if __name__ == "__main__":
    main()
