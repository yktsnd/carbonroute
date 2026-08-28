"""Pins the published numbers of examples/case-studies/beta-arbutin-chemical-vs-enzymatic/.

If any of these move, that case study's SOURCES.md write-up is stale.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from carbonroute.compute import resolved_delta_gwp, run_comparison, unresolved_flip_factor
from carbonroute.ledger import load_ledger
from carbonroute.resolve import (
    FactorTable,
    default_factor_paths,
    default_synonym_paths,
)
from carbonroute.uncertainty import load_uncertainty

ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / "examples" / "case-studies" / "beta-arbutin-chemical-vs-enzymatic"


@pytest.fixture()
def table() -> FactorTable:
    t = FactorTable.load(list(default_factor_paths(ROOT)))
    for syn in default_synonym_paths(ROOT):
        t.load_synonyms(syn)
    return t


def test_coverage_is_97_9_percent(table: FactorTable):
    from carbonroute.compute import adjust_route, coverage, diff_routes
    from carbonroute.resolve import resolve_materials

    ledger = load_ledger(CASE / "ledger.yaml")
    a = adjust_route("chemical", ledger.routes["chemical"], ledger.assumptions)
    b = adjust_route("enzymatic", ledger.routes["enzymatic"], ledger.assumptions)
    diff = diff_routes(a, b, resolve_materials(list(a.materials) + list(b.materials), table))
    cov = coverage(diff)
    assert cov.resolved_mass_kg / cov.delta_mass_kg == pytest.approx(0.979, abs=0.001)


def test_enzymatic_wins_decisively_at_placeholder_yield(table: FactorTable):
    ledger = load_ledger(CASE / "ledger.yaml")
    model = load_uncertainty(None)
    comparison = run_comparison(ledger, "chemical", "enzymatic", table, model, seed=1)
    assert comparison.stats.p_a_lower == pytest.approx(0.0, abs=1e-4)
    assert comparison.stats.verdict == "B<A"  # enzymatic (B) lower than chemical (A)
    resolved = resolved_delta_gwp(comparison.diff, comparison.assumptions)
    assert resolved == pytest.approx(1431, abs=1)
    flip = unresolved_flip_factor(comparison.diff, comparison.assumptions)
    assert flip.breakeven_kgCO2e_per_kg is None  # no positive value reverses it


def test_no_yield_in_range_flips_the_verdict(table: FactorTable):
    """Sweeps the enzymatic step's own yield exactly as SOURCES.md reports:
    no crossing in [0.05, 1.0]."""
    from carbonroute.compute import adjust_route, diff_routes, resolved_delta_gwp
    from carbonroute.resolve import resolve_materials

    ledger = load_ledger(CASE / "ledger.yaml")

    def resolved_at(enzymatic_yield: float) -> float:
        a = adjust_route("chemical", ledger.routes["chemical"], ledger.assumptions)
        enz_route = ledger.routes["enzymatic"].model_copy(deep=True)
        enz_route.steps[0].yield_ = enzymatic_yield
        b = adjust_route("enzymatic", enz_route, ledger.assumptions)
        diff = diff_routes(a, b, resolve_materials(list(a.materials) + list(b.materials), table))
        return resolved_delta_gwp(diff, ledger.assumptions)

    for y in (0.05, 0.2, 0.5, 1.0):
        # resolved_delta only depends on the chemical route's held solvents
        # here (hydroquinone and UDP-glucose are both unresolved), so it is
        # constant across yield -- pinning that invariant, not just the sign.
        assert resolved_at(y) == pytest.approx(1430.71, abs=1)


def test_verdict_survives_near_total_solvent_recovery(table: FactorTable):
    """Pins the solvent-recovery sweep in SOURCES.md: still not reversed at 99.99%."""
    from carbonroute.compute import adjust_route, diff_routes, resolved_delta_gwp
    from carbonroute.resolve import resolve_materials

    ledger = load_ledger(CASE / "ledger.yaml")
    asm = ledger.assumptions.model_copy(update={"solvent_recovery_default": 0.9999})
    a = adjust_route("chemical", ledger.routes["chemical"], asm)
    b = adjust_route("enzymatic", ledger.routes["enzymatic"], asm)
    diff = diff_routes(a, b, resolve_materials(list(a.materials) + list(b.materials), table))
    resolved = resolved_delta_gwp(diff, asm)
    assert resolved > 0  # chemical still higher even at 99.99% recovery
    assert resolved == pytest.approx(0.62, abs=0.05)
    flip = unresolved_flip_factor(diff, asm)
    assert flip.breakeven_kgCO2e_per_kg is None
