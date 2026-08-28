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
    ScreenResult,
    break_even_frontier,
    count_protectable_groups,
    load_reactions,
    load_structures,
    load_template,
    molecular_weight,
    parse_reaction,
    rank_by_advantage,
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
    assert t.cofactor_chebi == ("CHEBI:58885", "CHEBI:66914")
    assert all(m.basis in ("sourced", "generalised") for m in t.materials)
    assert all(m.note.strip() for m in t.materials)
    # The acetic anhydride substitution is the template's largest extrapolation
    # and must stay labelled as one.
    anhydride = next(m for m in t.materials if m.cas == "108-24-7")
    assert anhydride.basis == "generalised"
    assert anhydride.per_protected_group is True


# --- the screen -------------------------------------------------------------


@pytest.fixture(scope="module")
def inputs():
    reactions, _ = load_reactions(RHEA / "reactions.tsv")
    structures = load_structures(RHEA / "participants.csv")
    template = load_template(CLASSES / "udp-glucosyltransferase.yaml")
    bounds = load_bounds(CLASSES / "udp-glucosyltransferase.bounds.yaml")
    table = FactorTable.load(list(default_factor_paths(ROOT)))
    for syn in default_synonym_paths(ROOT):
        table.load_synonyms(syn)
    assumptions = load_ledger(ARBUTIN / "ledger.yaml").assumptions
    return reactions, template, structures, table, assumptions, bounds


@pytest.fixture(scope="module")
def screened(inputs):
    return screen_all(*inputs)


def test_the_class_matches_the_expected_number_of_reactions(screened):
    # 263 consume UDP-glucose, 143 consume UDP-galactose (its diastereomer,
    # added because it shares the same 162.14 mass-delta signature -- see
    # the template's file header).
    assert screened.matched == 406
    # 18 of the 406 are excluded by the mass-delta check, not silently
    # templated as glycosylations: 9 where an acceptor/product pair could
    # not be identified, and 9 that consume a class cofactor for a
    # genuinely different transformation -- the cofactor's own hydrolysis, a
    # sugar-nucleotide exchange, a hexose-1-phosphate transfer onto a lipid
    # carrier (undecaprenyl phosphate), or oxidation of the sugar-nucleotide
    # itself -- verified by hand for every exclusion bucket; see
    # screen_reaction's comment on the check.
    assert len(screened.decided) == 388


def test_screen_reproduces_the_hand_built_case(screened):
    """Calibration. RHEA:12560 is the reaction built by hand, fully sourced, in
    examples/case-studies/beta-arbutin-chemical-vs-enzymatic/.

    A screen that disagreed with the one case it was derived from would be
    reporting on its own template rather than on chemistry, so this is the
    test that gives the other 387 rows any standing at all.
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
    of product. None of the 388 survives 99% recovery, and the whole
    distribution sits below the 90-95% a real plant achieves by distillation.
    If this ever starts passing, the class's advantage has stopped being an
    artefact of glassware and the claim can be made much more strongly.
    """
    assert all(not r.robust for r in screened.results)
    thresholds = [r.recovery_threshold for r in screened.decided]
    assert min(thresholds) == pytest.approx(0.8558, abs=0.002)
    assert max(thresholds) == pytest.approx(0.9154, abs=0.002)


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
    1-phosphate + UDP-galactose) where nothing is added at all. RHEA:28126
    transfers glucosyl-1-phosphate (162.14 + a phosphate group, 242.12 total)
    onto a lipid carrier (undecaprenyl phosphate), not a hydroxyl -- a real
    but different biosynthetic mechanism that only became reachable once
    UDP-galactose reactions widened the field this check has to police.
    RHEA:35755 oxidises UDP-glucose itself (an NAD+-dependent step) rather
    than transferring it anywhere. All four consume a class cofactor; none
    belongs in a glycosylation class."""
    for rhea_id in ("RHEA:29555", "RHEA:13989", "RHEA:28126", "RHEA:35755"):
        r = next(x for x in screened.results if x.rhea_id == rhea_id)
        assert not r.decided
        assert "does not match this class's expected" in r.skipped_reason


def test_screens_a_udp_galactose_reaction_using_the_same_class(screened):
    """UDP-galactose (CHEBI:66914) is the second cofactor this class matches
    on -- its diastereomer relationship to UDP-glucose is the reason one
    template covers both (see the template's file header). RHEA:10088
    (sucrose + UDP-galactose -> 6-alpha-D-galactosylsucrose + UDP + H+) is a
    genuine member: the transferred mass is the same 162.14 anhydrohexosyl
    unit, and it must be screened and decided like any glucose-donor row."""
    r = next(x for x in screened.results if x.rhea_id == "RHEA:10088")
    assert "UDP-alpha-D-galactose" in r.equation
    assert r.decided
    assert r.acceptor_name == "sucrose"


# --- enzymatic conversion: the axis that was missing ------------------------


@pytest.fixture(scope="module")
def screened_at_half(inputs):
    return screen_all(*inputs, enzymatic_yield=0.5)


def test_the_template_declares_the_yield_its_chemical_side_already_carries():
    """The asymmetry is only auditable if both sides state their conversion.

    The amounts are per mole of product, so this yield is already folded into
    them and must never be applied again -- it is declared so a reader can see
    52.7% sitting next to whatever the enzymatic side was billed at.
    """
    t = load_template(CLASSES / "udp-glucosyltransferase.yaml")
    assert t.source_overall_yield == pytest.approx(0.527)


def test_template_rejects_an_out_of_range_source_yield(tmp_path):
    p = tmp_path / "t.yaml"
    p.write_text(
        "reaction_class:\n"
        "  id: t\n  name: T\n  cofactor_chebi: 'CHEBI:58885'\n"
        "  expected_mass_delta: 162.14\n"
        "chemical_counterpart:\n"
        "  name: C\n  source: S\n  source_overall_yield: 1.4\n  materials:\n"
        "    - {name: x, kg_per_mol_product: 1.0, basis: sourced, note: n}\n",
        encoding="utf-8",
    )
    with pytest.raises(ScreenError, match="source_overall_yield"):
        load_template(p)


def test_a_half_converting_enzyme_pays_twice_the_cofactor(screened, screened_at_half):
    """The asymmetry this axis exists to remove.

    A template's chemical amounts are stated per mole of *product*, so they
    already carry the source paper's real yield (62% x 85% = 52.7% for the
    shipped class). Billing the enzymatic side at bare stoichiometry gave the
    enzyme a free pass the chemistry never got. Halving conversion must
    double the cofactor bill, because half the acceptor never becomes product.
    """
    full = next(r for r in screened.decided if r.rhea_id == "RHEA:12560")
    half = next(r for r in screened_at_half.results if r.rhea_id == "RHEA:12560")
    assert half.cofactor_kg_per_fu == pytest.approx(2 * full.cofactor_kg_per_fu)
    assert half.enzymatic_yield == 0.5


def test_a_worse_enzyme_buys_the_chemical_route_headroom(screened, screened_at_half):
    """Every threshold must fall, and none may rise: a less efficient enzyme
    cannot make the enzymatic route harder to beat."""
    full = {r.rhea_id: r.recovery_threshold for r in screened.decided}
    for r in screened_at_half.decided:
        if full.get(r.rhea_id) is not None and r.recovery_threshold is not None:
            assert r.recovery_threshold < full[r.rhea_id]


def test_the_class_does_not_survive_an_industrial_solvent_loop_at_any_conversion(screened):
    """The finding that the conversion axis exposed, and the sharpest one here.

    The recovery thresholds sit at 85.58-91.54%, and a real plant distils back
    90%. So for the overwhelming majority of this class the verdict is already
    gone at a realistic solvent loop -- not because the enzyme converts badly,
    but before conversion is even asked about. Only the tail is still decided
    there, and it needs a near-quantitative enzyme to stay that way.
    """
    needs = [r.min_enzymatic_yield for r in screened.decided]
    still_decided = [y for y in needs if y is not None]
    assert len(still_decided) == 25
    assert len(needs) - len(still_decided) == 363
    # And those 25 are not comfortable: the median one needs 93% conversion.
    still_decided.sort()
    assert min(still_decided) == pytest.approx(0.853, abs=0.005)
    assert still_decided[len(still_decided) // 2] == pytest.approx(0.933, abs=0.005)


def test_the_calibration_case_loses_its_verdict_before_conversion_matters(screened):
    """RHEA:12560's threshold is 85.87%, below the 90% reference recovery, so
    there is no conversion at which its verdict survives that plant -- and the
    screen must report `None` rather than invent a requirement."""
    r = next(x for x in screened.results if x.rhea_id == "RHEA:12560")
    assert r.recovery_threshold == pytest.approx(0.8587, abs=0.002)
    assert r.reference_recovery == 0.90
    assert r.min_enzymatic_yield is None


def test_the_break_even_frontier_slopes_the_only_way_it_can(inputs):
    """The 2-D boundary, sampled. Losing conversion can only cost the
    enzymatic route solvent-recovery headroom, so every summary statistic
    must decrease monotonically down the curve."""
    curve = break_even_frontier(*inputs, yields=(1.0, 0.7, 0.5))
    assert [p.enzymatic_yield for p in curve] == [1.0, 0.7, 0.5]
    assert all(p.decided == 388 for p in curve)
    for a, b in zip(curve, curve[1:]):
        assert b.min_threshold < a.min_threshold
        assert b.median_threshold < a.median_threshold
        assert b.max_threshold < a.max_threshold
    # The size of the effect is the point, not just its sign: a coin-flip
    # enzyme costs the class ~14 points of the median threshold.
    assert curve[0].median_threshold == pytest.approx(0.8642, abs=0.002)
    assert curve[-1].median_threshold == pytest.approx(0.7247, abs=0.002)


# --- ranking on a quantity that survives leaving the class ------------------


def _fake_result(rhea_id: str, lo: float | None, hi: float | None) -> ScreenResult:
    """A ScreenResult carrying nothing but an advantage interval."""
    return ScreenResult(
        rhea_id=rhea_id,
        equation="",
        ec="",
        product_name=rhea_id,
        product_chebi="",
        product_mw=1.0,
        acceptor_name="",
        protectable_groups=0,
        cofactor_kg_per_fu=0.0,
        verdict=None,
        advantage_min_kgCO2e=lo,
        advantage_max_kgCO2e=hi,
    )


def test_ranking_orders_strictly_only_when_the_intervals_separate():
    """The machinery, on intervals that do and do not overlap.

    A reaction outranks another only when its worst case still beats the
    other's best case. [10,12] beats [1,2]; [3,8] overlaps both and can be
    placed nowhere exact, so it must report a range rather than a number.
    """
    ranked = rank_by_advantage(
        [_fake_result("hi", 10.0, 12.0), _fake_result("lo", 1.0, 2.0), _fake_result("mid", 3.0, 8.0)]
    )
    by_id = {x.result.rhea_id: x for x in ranked}
    assert (by_id["hi"].best_rank, by_id["hi"].worst_rank) == (1, 1)
    assert (by_id["lo"].best_rank, by_id["lo"].worst_rank) == (3, 3)
    # "mid" overlaps neither strictly, so it is pinned second by both sides.
    assert (by_id["mid"].best_rank, by_id["mid"].worst_rank) == (2, 2)
    assert all(x.determinate for x in ranked)
    assert [x.result.rhea_id for x in ranked] == ["hi", "mid", "lo"]


def test_ranking_reports_a_range_rather_than_inventing_an_order():
    """Two overlapping intervals are not ordered by the data, and the rank
    must say so instead of breaking the tie on a midpoint."""
    ranked = rank_by_advantage([_fake_result("a", 1.0, 9.0), _fake_result("b", 2.0, 8.0)])
    assert all((x.best_rank, x.worst_rank) == (1, 2) for x in ranked)
    assert not any(x.determinate for x in ranked)


def test_an_open_upper_end_blocks_every_comparison(screened):
    """The shipped bounds file asserts no ceiling on four chemical-side
    materials, so every reaction's advantage runs to infinity and nothing can
    outrank anything. This is a fact about the bounds, not the chemistry, and
    the screen must expose it rather than quietly ordering on midpoints."""
    ranked = rank_by_advantage(screened.decided)
    assert all(x.result.advantage_max_kgCO2e is None for x in ranked)
    assert all((x.best_rank, x.worst_rank) == (1, len(ranked)) for x in ranked)


def test_the_advantage_is_read_at_the_industrial_operating_point(screened):
    """Not at zero solvent recovery, which is where the recovery threshold
    starts. A cross-class number is only comparable if every class is read at
    the same operating point, and the bench point is not one a plant has."""
    decided = screened.decided
    assert all(r.reference_recovery == 0.90 for r in decided)
    guaranteed = [r for r in decided if r.advantage_decided]
    assert len(guaranteed) == 25
    # The 363 others straddle zero at 90% recovery: no verdict, not a small one.
    assert all(r.advantage_min_kgCO2e <= 0.0 for r in decided if not r.advantage_decided)


def test_the_guaranteed_saving_reproduces_the_regioselectivity_mechanism(screened):
    """The cross-class metric has to recover the same physical story the
    recovery threshold does, or it is measuring something else. It does: the
    largest guaranteed savings belong to the most heavily protected
    acceptors, because that is what an enzyme spares a chemical route."""
    ranked = rank_by_advantage(screened.decided)
    top = [x.result for x in ranked[:10]]
    assert all(r.protectable_groups >= 20 for r in top)
    assert ranked[0].result.advantage_min_kgCO2e == pytest.approx(4.15, abs=0.05)


def test_mass_delta_check_tolerates_chebis_own_charge_state_bookkeeping(screened):
    """RHEA:13437 (cinnamate -> 1-O-cinnamoyl-beta-D-glucose) is a genuine
    glycosylation, but ChEBI records the acceptor as the carboxylate anion
    and the product as the neutral ester, so the raw mass delta is short by
    one proton (161.13, not 162.14). It must still be screened, not silently
    dropped for a database bookkeeping artefact that isn't chemistry."""
    r = next(x for x in screened.results if x.rhea_id == "RHEA:13437")
    assert r.decided
