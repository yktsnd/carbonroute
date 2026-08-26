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


def test_public_data_covers_almost_none_of_this_comparison(ledger, public_table):
    """The measured answer to the spec's last open question (section 14).

    Openly licensed factors reach a small fraction of a real pharmaceutical
    route. This number is pinned so that adding a factor source visibly moves
    it; if it goes up, update the bound and say which source did it.
    """
    adjusted = adjust_all(ledger)
    resolutions = {}
    for adj in adjusted.values():
        resolutions.update(resolve_materials(adj.materials, public_table))
    cov = coverage(diff_routes(adjusted["merck"], adjusted["denovo"], resolutions))

    assert cov.delta_material_count > 30
    assert cov.mass_fraction < 0.20, "coverage improved — update this bound and the docs"
    assert cov.count_fraction < 0.20
    # Catalysts are where mass coverage misleads most, and they resolve worst.
    assert cov.by_role["catalyst"][0] == 0.0


def test_the_tool_refuses_to_rank_on_this_coverage(comparison):
    """The point of the whole benchmark.

    On the resolved 9% the Monte Carlo is extremely confident, and it is
    confident in the direction opposite the published result. A tool that
    reported that as its conclusion would be worse than useless. It must
    withhold the ranking and say why.
    """
    stats = comparison.stats
    assert stats.verdict == "indeterminate"
    assert "of the differing mass" in stats.indeterminate_reason
    assert stats.coverage_mass_fraction < 0.20


def test_the_breakeven_analysis_points_at_the_published_answer(comparison, public_table):
    """No factor is invented, and the honest question still has a useful answer.

    The resolved fraction alone leans towards Merck. The break-even calculation
    says how clean the missing 30 kg/FU would have to be for that lean to
    survive: below about 0.2 kgCO2e/kg on average. Every organic solvent in the
    project's own factor table sits above that, so the tool's own data argues
    for the published ranking without ever asserting it.
    """
    flip = unresolved_flip_factor(comparison.diff, comparison.assumptions)
    assert flip.resolved_delta_kgCO2e < 0, "resolved part leans towards Merck"
    assert flip.breakeven_kgCO2e_per_kg is not None
    assert 0.0 < flip.breakeven_kgCO2e_per_kg < 1.0

    organics = [
        f.gwp_kgCO2e_per_kg
        for f in public_table.by_key.values()
        if f.gwp_kgCO2e_per_kg > 0.25  # the light organics, not the bulk mineral acids
    ]
    assert organics, "expected at least one organic factor in the public table"
    assert flip.breakeven_kgCO2e_per_kg < min(organics)


def test_absolute_agreement_is_not_claimed(comparison):
    """Explicitly: this benchmark does not reproduce the published numbers."""
    for total in (comparison.a.total_kgCO2e, comparison.b.total_kgCO2e):
        assert total < 0.1 * PUBLISHED["denovo_gwp"], (
            "the tool now accounts for a large share of the published footprint; "
            "revisit whether ranking-only acceptance is still the right bar"
        )
