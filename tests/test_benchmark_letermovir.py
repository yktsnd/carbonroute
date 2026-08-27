"""Benchmark B2: the letermovir route comparison (spec section 10).

Ground truth is the published study, which is open access:

    Sorgenfrei et al., "Integrated Life Cycle Assessment Guides Sustainability
    in Synthesis: Antiviral Letermovir as a Case Study", J. Am. Chem. Soc. 2025,
    147, 40944. doi:10.1021/jacs.5c14470 (PMC12593353).

The ledger in benchmarks/letermovir was extracted from that paper's
supplementary workbook. Their GWP figures were computed with ecoinvent 3.10,
which this project may not redistribute, so **absolute agreement is neither
achievable nor tested**. What is tested is the behaviour that matters when the
data runs out, which is the situation this benchmark actually represents.
"""

import json
from pathlib import Path

import pytest
import yaml

from carbonroute.compute import coverage, diff_routes, run_comparison, unresolved_flip_factor
from carbonroute.ledger import adjust_all, load_ledger
from carbonroute.resolve import FactorTable, resolve_materials
from carbonroute.uncertainty import load_uncertainty

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "benchmarks" / "letermovir" / "ledger.yaml"
PUBLIC_FACTORS = ROOT / "data" / "factors" / "ademe_base_carbone.csv"

#: From the paper, at the 50% catalyst recovery base case. Cited, never reproduced.
PUBLISHED = {"merck_gwp": 382.0, "denovo_gwp": 369.0, "merck_pmi": 147.0, "denovo_pmi": 127.0}


@pytest.fixture(scope="module")
def ledger():
    return load_ledger(LEDGER)


@pytest.fixture(scope="module")
def public_table():
    return FactorTable.load(sorted((ROOT / "data" / "factors").glob("*.csv")))


@pytest.fixture(scope="module")
def comparison(ledger, public_table):
    return run_comparison(ledger, "merck", "denovo", public_table, load_uncertainty())


def test_the_published_ranking_is_denovo_below_merck():
    """Guards the constant the rest of this file is judged against."""
    assert PUBLISHED["denovo_gwp"] < PUBLISHED["merck_gwp"]
    gap = (PUBLISHED["merck_gwp"] - PUBLISHED["denovo_gwp"]) / PUBLISHED["merck_gwp"]
    assert gap < 0.05, "the published routes are within a few percent; this is a near-tie"


def test_both_routes_have_seven_steps(ledger):
    assert set(ledger.routes) == {"merck", "denovo"}
    for name in ("merck", "denovo"):
        assert len(ledger.routes[name].steps) == 7


def test_the_ledger_carries_masses_and_no_emission_factors():
    """The ledger is portable; the factors it was scored with are not.

    The source workbook's GWP columns are ecoinvent-derived. Nothing resembling
    a factor may appear in this directory, or the benchmark stops being
    redistributable.
    """
    raw = yaml.safe_load(LEDGER.read_text(encoding="utf-8"))
    for route in raw["routes"].values():
        for step in route["steps"]:
            for item in step.get("inputs", []):
                assert set(item) <= {"name", "cas", "mass_kg", "role", "recovery"}
    assert not list((ROOT / "benchmarks" / "letermovir").glob("*.csv"))


def test_the_recorded_run_still_reproduces(comparison, ledger, public_table):
    """Regression against benchmarks/letermovir/RESULTS.json.

    These numbers are expected to move as data/factors grows — that is the
    benchmark working. When they do, regenerate the record with
    scripts/record_letermovir_result.py, read the diff, and say in the commit
    message which source moved it. Freezing them in an assertion instead would
    make every improvement look like a broken test.
    """
    recorded = json.loads((ROOT / "benchmarks" / "letermovir" / "RESULTS.json").read_text())
    adjusted = adjust_all(ledger)
    resolutions = {}
    for adj in adjusted.values():
        resolutions.update(resolve_materials(adj.materials, public_table))
    cov = coverage(diff_routes(adjusted["merck"], adjusted["denovo"], resolutions))
    flip = unresolved_flip_factor(comparison.diff, comparison.assumptions)

    assert cov.delta_material_count == recorded["delta_material_count"]
    assert cov.resolved_count == recorded["resolved_count"]
    assert cov.mass_fraction == pytest.approx(recorded["coverage_mass_fraction"], rel=1e-9)
    assert comparison.stats.verdict == recorded["verdict"]
    assert flip.resolved_delta_kgCO2e == pytest.approx(
        recorded["resolved_delta_kgCO2e"], rel=1e-9
    )
    if recorded["breakeven_kgCO2e_per_kg"] is None:
        assert flip.breakeven_kgCO2e_per_kg is None
    else:
        assert flip.breakeven_kgCO2e_per_kg == pytest.approx(
            recorded["breakeven_kgCO2e_per_kg"], rel=1e-9
        )


def test_no_ranking_is_reported_below_the_coverage_floor(comparison, ledger):
    """The invariant that survives any amount of new data.

    Whatever the Monte Carlo says about the part that resolved, a comparison
    that reaches less of the differing mass than the declared minimum must come
    back undecided, with the coverage named as the reason.
    """
    stats = comparison.stats
    floor = ledger.assumptions.min_delta_coverage
    if stats.coverage_mass_fraction < floor:
        assert stats.verdict == "indeterminate"
        assert "of the differing mass" in stats.indeterminate_reason


def test_a_gap_always_comes_with_a_breakeven(comparison):
    """An unresolved material is never silently worth zero."""
    flip = unresolved_flip_factor(comparison.diff, comparison.assumptions)
    if comparison.diff.delta_unresolved:
        assert flip.unresolved_delta_mass_kg != 0.0 or flip.note
        assert flip.note


def test_the_resolved_part_agrees_with_the_published_ranking(comparison):
    """Once enough of the mass resolves, the tool should lean the published way.

    At 9% coverage it leaned the other way, which is exactly why the coverage
    floor exists. This asserts that the lean corrected itself as data arrived,
    and would catch a factor table that pushed it back the wrong way.

    Route A is merck, B is denovo, so a positive delta means denovo is lower,
    which is what the paper reports.
    """
    flip = unresolved_flip_factor(comparison.diff, comparison.assumptions)
    if comparison.stats.coverage_mass_fraction < 0.3:
        pytest.skip("too little of the delta resolves for the lean to mean anything")
    assert flip.resolved_delta_kgCO2e > 0, (
        "the resolved part now favours the Merck route, against the published "
        "result — check which factor changed before accepting this"
    )


def test_public_data_still_does_not_cover_this_comparison(ledger, public_table):
    """The spec's open question (section 14), measured rather than asserted."""
    adjusted = adjust_all(ledger)
    resolutions = {}
    for adj in adjusted.values():
        resolutions.update(resolve_materials(adj.materials, public_table))
    cov = coverage(diff_routes(adjusted["merck"], adjusted["denovo"], resolutions))

    assert cov.delta_material_count > 30
    assert cov.mass_fraction < ledger.assumptions.min_delta_coverage, (
        "coverage now clears the floor — the benchmark can start testing the "
        "ranking itself; update benchmarks/README.md and this test together"
    )


def test_absolute_agreement_is_not_claimed(comparison):
    """Explicitly: this benchmark does not reproduce the published numbers."""
    for total in (comparison.a.total_kgCO2e, comparison.b.total_kgCO2e):
        assert total < 0.5 * PUBLISHED["denovo_gwp"], (
            "the tool now accounts for a large share of the published footprint; "
            "revisit whether ranking-only acceptance is still the right bar"
        )
