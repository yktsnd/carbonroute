"""Coverage of the delta set — the last open question in spec section 14."""

import pytest

from carbonroute.compute import coverage, diff_routes
from carbonroute.ledger import adjust_all
from carbonroute.resolve import FactorTable, resolve_materials
from carbonroute.uncertainty import effective_gsd, load_uncertainty

HEADER = (
    "identifier,name,gwp_kgCO2e_per_kg,source,database_version,region,"
    "retrieved_date,uncertainty_class,license,notes,inchikey,gsd\n"
)


@pytest.fixture()
def cov(analytic_ledger, analytic_table):
    adjusted = adjust_all(analytic_ledger)
    resolutions = {}
    for adj in adjusted.values():
        resolutions.update(resolve_materials(adj.materials, analytic_table))
    return coverage(diff_routes(adjusted["a"], adjusted["b"], resolutions))


def test_coverage_counts_the_delta_set_only(cov):
    # benzene and acetone cancel; toluene, 2-MeTHF and the novel ligand do not.
    assert cov.delta_material_count == 3
    assert cov.resolved_count == 2
    assert cov.unresolved_count == 1


def test_mass_and_count_coverage_disagree(cov):
    """The disagreement is the finding, not a rounding artefact.

    96% of the differing mass resolves while a third of the materials do not,
    which is exactly how a mass-based metric hides a small, high-impact input.
    """
    assert cov.count_fraction == pytest.approx(2 / 3)
    assert cov.mass_fraction == pytest.approx(12.5 / 13.0)
    assert cov.count_fraction < cov.mass_fraction


def test_per_role_breakdown_exposes_the_gap(cov):
    assert cov.by_role["solvent"] == pytest.approx((12.5, 12.5))
    assert cov.by_role["reagent"] == pytest.approx((0.0, 0.5))


def test_unresolved_are_listed_largest_first(cov):
    masses = [m for _, _, _, m in cov.unresolved]
    assert masses == sorted(masses, reverse=True)
    assert cov.unresolved[0][1] == "novel ligand Z"


def test_full_coverage_reports_one(analytic_ledger, analytic_table, tmp_path):
    extra = tmp_path / "extra.csv"
    extra.write_text(
        HEADER
        + "7440-06-4,novel ligand Z,1.0,fixture,n/a,GLO,2026-01-01,analogue_substitute,CC0,,,\n",
        encoding="utf-8",
    )
    table = FactorTable.load([analytic_table.sources and next(iter(analytic_table.sources)), extra])
    adjusted = adjust_all(analytic_ledger)
    resolutions = {}
    for adj in adjusted.values():
        resolutions.update(resolve_materials(adj.materials, table))
    c = coverage(diff_routes(adjusted["a"], adjusted["b"], resolutions))
    assert c.unresolved == []
    assert c.mass_fraction == 1.0 and c.count_fraction == 1.0


def test_sourced_gsd_overrides_the_placeholder_class(tmp_path):
    """A GSD the source published beats the uncalibrated class default."""
    p = tmp_path / "f.csv"
    p.write_text(
        HEADER
        + "108-88-3,toluene,3.0,ADEME,v1,FR,2026-01-01,literature,LO,,YXFVVABEGXRONW-UHFFFAOYSA-N,1.83\n"
        + "67-56-1,methanol,1.0,ADEME,v1,FR,2026-01-01,literature,LO,,OKKJLVBELUTLKV-UHFFFAOYSA-N,\n",
        encoding="utf-8",
    )
    table = FactorTable.load([p])
    model = load_uncertainty()
    toluene = table.by_key["cas:108-88-3"]
    methanol = table.by_key["cas:67-56-1"]
    assert toluene.gsd == 1.83
    assert effective_gsd(toluene, model) == 1.83
    # An empty cell means "the source was silent", not "no uncertainty".
    assert methanol.gsd is None
    assert effective_gsd(methanol, model) == model.gsd("literature")


def test_inchikey_is_a_usable_join_key(tmp_path):
    p = tmp_path / "f.csv"
    p.write_text(
        HEADER
        + "108-88-3,toluene,3.0,ADEME,v1,FR,2026-01-01,literature,LO,,YXFVVABEGXRONW-UHFFFAOYSA-N,\n",
        encoding="utf-8",
    )
    table = FactorTable.load([p])
    assert table.lookup("inchikey:YXFVVABEGXRONW-UHFFFAOYSA-N", "?").resolved
    assert table.by_inchikey["YXFVVABEGXRONW-UHFFFAOYSA-N"].name == "toluene"


def test_a_gsd_below_one_is_rejected(tmp_path):
    from carbonroute.resolve import FactorTableError

    p = tmp_path / "f.csv"
    p.write_text(
        HEADER + "108-88-3,toluene,3.0,ADEME,v1,FR,2026-01-01,literature,LO,,,0.5\n",
        encoding="utf-8",
    )
    with pytest.raises(FactorTableError, match="gsd"):
        FactorTable.load([p])
