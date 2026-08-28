"""Tests for screening a reaction database against a class template."""

from __future__ import annotations

from pathlib import Path

import pytest

from carbonroute.bounds import load_bounds
from carbonroute.ledger import load_ledger
from carbonroute.resolve import (
    FactorTable,
    default_factor_paths,
    default_synonym_paths,
)
from carbonroute.screen import (
    ScreenError,
    count_protectable_groups,
    load_reactions,
    load_structures,
    load_template,
    molecular_weight,
    parse_reaction,
    screen_all,
)

ROOT = Path(__file__).resolve().parents[1]
RHEA = ROOT / "data" / "rhea"
CLASSES = ROOT / "data" / "reaction-classes"
ARBUTIN = ROOT / "examples" / "case-studies" / "beta-arbutin-chemical-vs-enzymatic"

pytest.importorskip("rdkit", reason="screening needs RDKit (pip install -e '.[chem]')")


# --- equation parsing -------------------------------------------------------


def test_parses_a_plain_equation():
    rxn = parse_reaction(
        "RHEA:12560",
        "hydroquinone + UDP-alpha-D-glucose = hydroquinone O-beta-D-glucopyranoside + UDP + H(+)",
        "CHEBI:17594;CHEBI:58885;CHEBI:18305;CHEBI:58223;CHEBI:15378",
        "EC:2.4.1.218",
    )
    assert rxn is not None
    assert [p.chebi for p in rxn.left] == ["CHEBI:17594", "CHEBI:58885"]
    assert [p.chebi for p in rxn.right] == ["CHEBI:18305", "CHEBI:58223", "CHEBI:15378"]
    assert all(p.coefficient == 1.0 for p in rxn.left)


def test_parses_stoichiometric_coefficients():
    rxn = parse_reaction(
        "RHEA:10136",
        "2 glyoxylate + H(+) = 2-hydroxy-3-oxopropanoate + CO2",
        "CHEBI:36655;CHEBI:15378;CHEBI:57978;CHEBI:16526",
        "EC:4.1.1.47",
    )
    assert rxn is not None
    assert rxn.left[0].coefficient == 2.0
    assert rxn.left[1].coefficient == 1.0


def test_refuses_to_guess_when_terms_and_ids_disagree():
    """Rather than mis-assign a ChEBI id to the wrong species."""
    assert (
        parse_reaction("RHEA:1", "a + b = c", "CHEBI:1;CHEBI:2", "")
        is None
    )


def test_rejects_a_non_equation():
    assert parse_reaction("RHEA:1", "not an equation", "CHEBI:1", "") is None


# --- structure-derived quantities -------------------------------------------


def test_molecular_weight_matches_hand_calculation():
    # The same value the beta-arbutin ledger's arithmetic was built on.
    assert molecular_weight("Oc1ccc(O)cc1") == pytest.approx(110.112, abs=0.01)


def test_protectable_group_count_is_a_structural_fact():
    assert count_protectable_groups("Oc1ccc(O)cc1") == 2  # hydroquinone: two phenols
    assert count_protectable_groups("CO") == 1  # methanol: one hydroxyl
    assert count_protectable_groups("c1ccccc1") == 0  # benzene: nothing to mask
    # An amide N is not a protection target the way a free amine is.
    assert count_protectable_groups("CC(=O)N") == 0


def test_unparseable_structure_returns_none_rather_than_raising():
    assert molecular_weight("not-a-smiles") is None
    assert count_protectable_groups("not-a-smiles") is None


# --- template loading -------------------------------------------------------


def _write_template(tmp_path: Path, materials: str) -> Path:
    p = tmp_path / "t.yaml"
    p.write_text(
        "reaction_class:\n"
        "  id: t\n  name: T\n  cofactor_chebi: 'CHEBI:58885'\n"
        "  expected_mass_delta: 162.14\n"
        "chemical_counterpart:\n"
        "  name: C\n  source: S\n  materials:\n" + materials,
        encoding="utf-8",
    )
    return p


def test_template_rejects_an_unlabelled_basis(tmp_path):
    p = _write_template(
        tmp_path,
        "    - {name: x, kg_per_mol_product: 1.0, basis: guessed, note: n}\n",
    )
    with pytest.raises(ScreenError, match="basis"):
        load_template(p)


def test_template_rejects_a_material_with_no_note(tmp_path):
    p = _write_template(
        tmp_path, "    - {name: x, kg_per_mol_product: 1.0, basis: sourced}\n"
    )
    with pytest.raises(ScreenError, match="note"):
        load_template(p)


def test_shipped_template_loads_and_labels_every_generalisation():
    t = load_template(CLASSES / "udp-glucosyltransferase.yaml")
    assert t.cofactor_chebi == "CHEBI:58885"
    assert all(m.basis in ("sourced", "generalised") for m in t.materials)
    assert all(m.note.strip() for m in t.materials)
    # The acetic anhydride substitution is the template's largest extrapolation
    # and must stay labelled as one.
    anhydride = next(m for m in t.materials if m.cas == "108-24-7")
    assert anhydride.basis == "generalised"
    assert anhydride.per_protected_group is True


# --- the screen -------------------------------------------------------------


@pytest.fixture(scope="module")
def screened():
    reactions, _ = load_reactions(RHEA / "reactions.tsv")
    structures = load_structures(RHEA / "participants.csv")
    template = load_template(CLASSES / "udp-glucosyltransferase.yaml")
    bounds = load_bounds(CLASSES / "udp-glucosyltransferase.bounds.yaml")
    table = FactorTable.load(list(default_factor_paths(ROOT)))
    for syn in default_synonym_paths(ROOT):
        table.load_synonyms(syn)
    assumptions = load_ledger(ARBUTIN / "ledger.yaml").assumptions
    return screen_all(reactions, template, structures, table, assumptions, bounds)


def test_the_class_matches_the_expected_number_of_reactions(screened):
    assert screened.matched == 263
    # 13 of the 263 are excluded by the mass-delta check, not silently
    # templated as glycosylations: 7 where an acceptor/product pair could
    # not be identified, and 6 that consume UDP-glucose for a genuinely
    # different transformation (its own hydrolysis, a sugar-nucleotide
    # exchange) -- verified by hand for every exclusion bucket; see
    # screen_reaction's comment on the check.
    assert len(screened.decided) == 250


def test_screen_reproduces_the_hand_built_case(screened):
    """Calibration. RHEA:12560 is the reaction built by hand, fully sourced, in
    examples/case-studies/beta-arbutin-chemical-vs-enzymatic/.

    A screen that disagreed with the one case it was derived from would be
    reporting on its own template rather than on chemistry, so this is the
    test that gives the other 249 rows any standing at all.
    """
    r = next(x for x in screened.results if x.rhea_id == "RHEA:12560")
    assert r.acceptor_name == "hydroquinone"
    assert r.protectable_groups == 2
    # beta-arbutin, the same MW the hand-built ledger's arithmetic used.
    assert r.product_mw == pytest.approx(272.253, abs=0.01)
    # Same direction as the hand-built comparison: the enzymatic route is lower.
    assert r.decided
    assert r.verdict is not None and r.verdict.verdict == "b_lower"
    # And the cofactor mass agrees with the ledger's 2.080 kg/FU to within the
    # difference between ChEBI's dianion and the ledger's free acid (~0.4%).
    assert r.cofactor_kg_per_fu == pytest.approx(2.08, rel=0.01)


def test_no_reaction_in_this_class_survives_industrial_solvent_recovery(screened):
    """The finding that keeps the screen honest.

    Every verdict here is decided at zero solvent recovery, but the template
    comes from a bench procedure that discards over 800 kg of solvent per kg
    of product. None of the 250 survives 99% recovery, and the whole
    distribution sits below the 90-95% a real plant achieves by distillation.
    If this ever starts passing, the class's advantage has stopped being an
    artefact of glassware and the claim can be made much more strongly.
    """
    assert all(not r.robust for r in screened.results)
    thresholds = [r.recovery_threshold for r in screened.decided]
    assert min(thresholds) == pytest.approx(0.8558, abs=0.002)
    assert max(thresholds) == pytest.approx(0.9143, abs=0.002)


def test_more_groups_to_mask_means_a_bigger_enzymatic_advantage(screened):
    """The mechanism the screen exists to measure, checked as a trend.

    An enzyme's regioselectivity is worth more the more sites a chemical
    route would have to mask, so the recovery threshold should rise with the
    acceptor's protectable-group count.
    """
    by_groups: dict[int, list[float]] = {}
    for r in screened.decided:
        by_groups.setdefault(r.protectable_groups, []).append(r.recovery_threshold)
    simple = min(k for k in by_groups if k <= 1)
    complex_ = max(by_groups)
    assert complex_ >= 10  # the class really does contain polyol acceptors
    assert max(by_groups[complex_]) > max(by_groups[simple])


def test_bis_glycosylation_scales_the_chemical_side_too(screened):
    """A reaction transferring two glucosyls must charge the chemical route for
    two glycosylations, not one -- otherwise it shows up as a false outlier."""
    r = next((x for x in screened.results if x.rhea_id == "RHEA:31543"), None)
    if r is None or not r.decided:
        pytest.skip("RHEA:31543 not in this snapshot")
    # It should sit inside the class's normal band, not far below it.
    assert r.recovery_threshold > 0.80


def test_mass_delta_check_excludes_reactions_that_are_not_this_transformation(screened):
    """RHEA:29555 consumes UDP-glucose but is the cofactor's OWN hydrolysis
    (UDP-glucose + H2O -> glucose 1-phosphate + UMP), not a transfer onto an
    external acceptor -- `_identify` mistakes water for the acceptor, and the
    mass-delta check is what actually catches it. RHEA:13989 is a sugar-
    nucleotide exchange (galactose 1-phosphate + UDP-glucose -> glucose
    1-phosphate + UDP-galactose) where nothing is added at all. Both consume
    the cofactor; neither belongs in a glycosylation class."""
    for rhea_id in ("RHEA:29555", "RHEA:13989"):
        r = next(x for x in screened.results if x.rhea_id == rhea_id)
        assert not r.decided
        assert "does not match this class's expected" in r.skipped_reason


def test_mass_delta_check_tolerates_chebis_own_charge_state_bookkeeping(screened):
    """RHEA:13437 (cinnamate -> 1-O-cinnamoyl-beta-D-glucose) is a genuine
    glycosylation, but ChEBI records the acceptor as the carboxylate anion
    and the product as the neutral ester, so the raw mass delta is short by
    one proton (161.13, not 162.14). It must still be screened, not silently
    dropped for a database bookkeeping artefact that isn't chemistry."""
    r = next(x for x in screened.results if x.rhea_id == "RHEA:13437")
    assert r.decided
