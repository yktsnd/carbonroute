"""Factor tables refuse rows nobody can check (spec sections 6.2, 13)."""

import pytest

from carbonroute.resolve import FactorTable, FactorTableError, resolve_materials
from carbonroute.ledger import adjust_all

HEADER = (
    "identifier,name,gwp_kgCO2e_per_kg,source,database_version,region,"
    "retrieved_date,uncertainty_class,license,notes\n"
)


def _table(tmp_path, rows, name="f.csv"):
    p = tmp_path / name
    p.write_text(HEADER + rows, encoding="utf-8")
    return p


def test_row_without_a_source_is_rejected(tmp_path):
    p = _table(tmp_path, "108-88-3,toluene,3.0,,v1,GLO,2026-01-01,background_db,CC0,\n")
    with pytest.raises(FactorTableError, match="source"):
        FactorTable.load([p])


def test_missing_column_is_rejected(tmp_path):
    p = tmp_path / "f.csv"
    p.write_text("identifier,name,gwp_kgCO2e_per_kg\n108-88-3,toluene,3.0\n", encoding="utf-8")
    with pytest.raises(FactorTableError, match="missing required column"):
        FactorTable.load([p])


def test_non_numeric_and_negative_values_are_rejected(tmp_path):
    bad = _table(tmp_path, "108-88-3,toluene,n/a,src,v1,GLO,2026-01-01,background_db,CC0,\n")
    with pytest.raises(FactorTableError):
        FactorTable.load([bad])
    negative = _table(
        tmp_path, "108-88-3,toluene,-1.0,src,v1,GLO,2026-01-01,background_db,CC0,\n", "g.csv"
    )
    with pytest.raises(FactorTableError, match="negative"):
        FactorTable.load([negative])


def test_disagreeing_sources_are_recorded_not_refused(tmp_path):
    """Two public sources differing about a substance is a measurement.

    Refusing to load would throw that measurement away and block the
    comparison; picking one quietly would hide it. Both values are carried.
    """
    a = _table(tmp_path, "108-88-3,toluene,3.0,src A,v1,GLO,2026-01-01,background_db,CC0,\n", "a.csv")
    b = _table(tmp_path, "108-88-3,toluene,4.0,src B,v1,GLO,2026-01-01,background_db,CC0,\n", "b.csv")
    table = FactorTable.load([a, b])
    assert table.by_key["cas:108-88-3"].gwp_kgCO2e_per_kg == 3.0
    assert len(table.conflicts) == 1
    conflict = table.conflicts[0]
    assert conflict.kept.source == "src A"
    assert conflict.rejected.gwp_kgCO2e_per_kg == 4.0
    assert conflict.ratio == pytest.approx(4.0 / 3.0)


def test_which_source_wins_does_not_depend_on_argument_order(tmp_path):
    a = _table(tmp_path, "108-88-3,toluene,3.0,src A,v1,GLO,2026-01-01,background_db,CC0,\n", "a.csv")
    b = _table(tmp_path, "108-88-3,toluene,4.0,src B,v1,GLO,2026-01-01,background_db,CC0,\n", "b.csv")
    forwards = FactorTable.load([a, b])
    backwards = FactorTable.load([b, a])
    assert (
        forwards.by_key["cas:108-88-3"].gwp_kgCO2e_per_kg
        == backwards.by_key["cas:108-88-3"].gwp_kgCO2e_per_kg
    )


def test_an_identical_duplicate_is_not_a_conflict(tmp_path):
    a = _table(tmp_path, "108-88-3,toluene,3.0,src A,v1,GLO,2026-01-01,background_db,CC0,\n", "a.csv")
    b = _table(tmp_path, "108-88-3,toluene,3.0,src B,v1,GLO,2026-01-01,background_db,CC0,\n", "b.csv")
    assert FactorTable.load([a, b]).conflicts == []


def test_inchikey_and_cas_keys_are_distinguished(tmp_path):
    rows = (
        "108-88-3,toluene,3.0,src,v1,GLO,2026-01-01,background_db,CC0,\n"
        "YXFVVABEGXRONW-UHFFFAOYSA-N,toluene (InChIKey row),3.0,src,v1,GLO,"
        "2026-01-01,background_db,CC0,\n"
    )
    table = FactorTable.load([_table(tmp_path, rows)])
    assert "cas:108-88-3" in table.by_key
    assert "inchikey:YXFVVABEGXRONW-UHFFFAOYSA-N" in table.by_key


def test_name_fallback_is_reported_as_the_weaker_match(analytic_table):
    hit = analytic_table.lookup("name:toluene", "Toluene")
    assert hit.resolved and hit.matched_by == "name"
    exact = analytic_table.lookup("cas:108-88-3", "toluene")
    assert exact.matched_by == "cas"


def test_unknown_material_stays_unresolved(analytic_table):
    miss = analytic_table.lookup("name:novel ligand z", "novel ligand Z")
    assert not miss.resolved
    assert miss.factor is None


def test_fingerprint_changes_with_content(tmp_path):
    a = _table(tmp_path, "108-88-3,toluene,3.0,src,v1,GLO,2026-01-01,background_db,CC0,\n", "a.csv")
    first = FactorTable.load([a]).fingerprint()
    assert first == FactorTable.load([a]).fingerprint()
    a.write_text(HEADER + "108-88-3,toluene,3.5,src,v1,GLO,2026-01-01,background_db,CC0,\n",
                 encoding="utf-8")
    assert FactorTable.load([a]).fingerprint() != first


def test_illustrative_rows_are_flagged(analytic_table):
    assert all(f.is_illustrative for f in analytic_table.by_key.values())


def test_resolve_materials_covers_every_input(analytic_ledger, analytic_table):
    adjusted = adjust_all(analytic_ledger)["a"]
    res = resolve_materials(adjusted.materials, analytic_table)
    assert set(res) == {m.key for m in adjusted.materials}
    assert not res["name:novel ligand z"].resolved


SYN_HEADER = "alias,identifier,inchikey,source,retrieved_date,notes\n"


def test_a_synonym_closes_the_gap_between_a_ledger_name_and_a_table_name(tmp_path):
    """The most expensive kind of gap: the data was there, under another name."""
    factors = _table(
        tmp_path,
        "96-47-9,2-methyltetrahydrofuran,6.0,src,v1,GLO,2026-01-01,background_db,CC0,\n",
    )
    table = FactorTable.load([factors])
    assert not table.lookup("name:2-me-thf", "2-Me-THF").resolved

    syn = tmp_path / "s.csv"
    syn.write_text(
        SYN_HEADER + "2-Me-THF,96-47-9,,PubChem CID 7301,2026-08-27,queried as '2-MeTHF'\n",
        encoding="utf-8",
    )
    table.load_synonyms(syn)
    hit = table.lookup("name:2-me-thf", "2-Me-THF")
    assert hit.resolved
    assert hit.matched_by == "synonym"
    assert hit.factor.gwp_kgCO2e_per_kg == 6.0


def test_a_synonym_without_a_source_is_an_unchecked_identity_claim(tmp_path):
    syn = tmp_path / "s.csv"
    syn.write_text(SYN_HEADER + "2-Me-THF,96-47-9,,,2026-08-27,\n", encoding="utf-8")
    with pytest.raises(FactorTableError, match="source"):
        FactorTable().load_synonyms(syn)


def test_an_exact_key_still_beats_a_synonym(tmp_path):
    rows = (
        "96-47-9,2-methyltetrahydrofuran,6.0,src,v1,GLO,2026-01-01,background_db,CC0,\n"
        "108-88-3,toluene,3.0,src,v1,GLO,2026-01-01,background_db,CC0,\n"
    )
    table = FactorTable.load([_table(tmp_path, rows)])
    syn = tmp_path / "s.csv"
    syn.write_text(SYN_HEADER + "toluene,96-47-9,,PubChem,2026-08-27,deliberately wrong\n",
                   encoding="utf-8")
    table.load_synonyms(syn)
    hit = table.lookup("cas:108-88-3", "toluene")
    assert hit.matched_by == "cas"
    assert hit.factor.gwp_kgCO2e_per_kg == 3.0
