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
    fair_fight_frontier,
    count_substructure,
    explain_verdict,
    materials_from_process_model,
    load_reactions,
    load_structures,
    load_template,
    molecular_weight,
    parse_reaction,
    rank_by_advantage,
    screen_all,
    screen_reaction,
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


@pytest.fixture(scope="module")
def at_published_operating_point(inputs):
    """Both sides at figures someone published: Liu et al.'s 240 cofactor
    turnovers, and the ~90% an industrial distillation recovers."""
    return screen_all(*inputs, cofactor_recycling=1 - 1 / 240, reference_recovery=0.90)


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


# --- the enzymatic route's own effort dial -----------------------------------


def test_recycling_is_refused_when_nothing_declared_drives_it(inputs, tmp_path):
    """A turnover number with nothing driving it is a free lunch.

    What drives regeneration varies by system -- a co-substrate for sucrose
    synthase or a dehydrogenase, an electrode, a whole cell -- so the code
    does not assume a shape. It only insists that some declared measure
    claims the job, because dividing the cofactor by a turnover number while
    charging nothing for its driver makes the enzymatic route look better
    than any real one is.
    """
    reactions, template, structures, table, assumptions, bounds = inputs
    bare = load_template(_acetyl_template(tmp_path, bond=False, ec=False))
    assert bare.enzymatic_measures == ()
    assert bare.recycling_enablers == ()
    rxn = next(r for r in reactions if r.rhea_id == "RHEA:12560")
    with pytest.raises(ScreenError, match="enables_recycling"):
        screen_reaction(
            rxn, bare, structures, table, assumptions, bounds, cofactor_recycling=0.9
        )


def test_the_shipped_class_charges_what_a_real_cascade_charges(inputs):
    """Not the 1:1 SuSy stoichiometry -- what a published system puts in.

    A regeneration cascade runs sucrose in large excess to drive the
    equilibrium, so the theoretical one-per-turnover figure this template
    used to carry understated the co-substrate by 4.2x, in the direction
    that flatters the enzymatic route. The figure now comes from Liu et al.
    2021 (CC BY 4.0), whose stated 500 mM sucrose against a ~52 g/L
    nothofagin titre works out at 4.196 mol per mole of product.
    """
    t = inputs[1]
    (sucrose,) = t.recycling_enablers
    assert sucrose.name == "sucrose"
    assert sucrose.chebi == "CHEBI:17992"
    assert sucrose.charge == "per_turnover"
    assert sucrose.kg_per_mol_product == pytest.approx(4.196 * 0.342297, rel=1e-3)
    # Still generalised: Liu et al. run a C-glycosyltransferase cascade and
    # this class is O-glycosylation. The regeneration half is what is
    # borrowed; the acceptor chemistry is not.
    assert sucrose.basis == "generalised"
    assert "10.1002/adsc.202001549" in sucrose.source


def test_an_amortised_measure_divides_by_its_reuse_cycles(tmp_path):
    """The shape immobilisation needs, and the reason two shapes exist.

    A regeneration co-substrate is consumed every cycle, so pushing the
    process harder never buys it down. An immobilised enzyme preparation is
    bought once and reused, so its burden divides by the batches one purchase
    serves -- the number immobilisation exists to raise. The two behave
    oppositely and a template must be able to say which it means.
    """
    p = tmp_path / "t.yaml"
    p.write_text(
        "reaction_class:\n"
        "  id: t\n  name: T\n  cofactor_chebi: 'CHEBI:58885'\n"
        "  expected_mass_delta: 162.14\n"
        "chemical_counterpart:\n"
        "  name: C\n  source: S\n  materials:\n"
        "    - {name: x, kg_per_mol_product: 1.0, basis: sourced, note: n}\n"
        "enzymatic_process:\n  measures:\n"
        "    - {name: co-substrate, charge: per_turnover, kg_per_mol_product: 2.0,"
        " basis: sourced, note: n, source: s, enables_recycling: true}\n"
        "    - {name: immobilised enzyme, charge: amortised, kg_per_mol_product: 50.0,"
        " reuse_cycles: 25, basis: sourced, note: n, source: s}\n",
        encoding="utf-8",
    )
    t = load_template(p)
    per_turnover, amortised = t.enzymatic_measures
    # 10 mol of product, 10 turnovers.
    assert per_turnover.kg_per_fu(10.0, 10.0) == pytest.approx(20.0)
    assert amortised.kg_per_fu(10.0, 10.0) == pytest.approx(10.0 * 50.0 / 25)
    assert t.recycling_enablers == (per_turnover,)


def test_an_amortised_measure_must_say_how_many_cycles(tmp_path):
    p = tmp_path / "t.yaml"
    p.write_text(
        "reaction_class:\n"
        "  id: t\n  name: T\n  cofactor_chebi: 'CHEBI:58885'\n"
        "  expected_mass_delta: 162.14\n"
        "chemical_counterpart:\n"
        "  name: C\n  source: S\n  materials:\n"
        "    - {name: x, kg_per_mol_product: 1.0, basis: sourced, note: n}\n"
        "enzymatic_process:\n  measures:\n"
        "    - {name: carrier, charge: amortised, kg_per_mol_product: 1.0,"
        " basis: sourced, note: n, source: s}\n",
        encoding="utf-8",
    )
    with pytest.raises(ScreenError, match="reuse_cycles"):
        load_template(p)


def test_an_enzymatic_measure_needs_a_source_like_everything_else(tmp_path):
    p = tmp_path / "t.yaml"
    p.write_text(
        "reaction_class:\n"
        "  id: t\n  name: T\n  cofactor_chebi: 'CHEBI:58885'\n"
        "  expected_mass_delta: 162.14\n"
        "chemical_counterpart:\n"
        "  name: C\n  source: S\n  materials:\n"
        "    - {name: x, kg_per_mol_product: 1.0, basis: sourced, note: n}\n"
        "enzymatic_process:\n  measures:\n"
        "    - {name: enzyme, charge: per_turnover, kg_per_mol_product: 1.0,"
        " basis: sourced, note: n}\n",
        encoding="utf-8",
    )
    with pytest.raises(ScreenError, match="source"):
        load_template(p)


def test_recycling_buys_down_the_cofactor_but_pays_a_co_substrate(inputs):
    """The whole point of the block. Recycling must reduce the cofactor and
    add its driver, not reduce the cofactor for free."""
    reactions, template, structures, table, assumptions, bounds = inputs
    rxn = next(r for r in reactions if r.rhea_id == "RHEA:12560")
    plain = screen_reaction(rxn, template, structures, table, assumptions, bounds)
    recycled = screen_reaction(
        rxn, template, structures, table, assumptions, bounds, cofactor_recycling=0.9
    )
    # The cofactor charge falls by exactly the recycling factor...
    assert recycled.cofactor_kg_per_fu == pytest.approx(0.1 * plain.cofactor_kg_per_fu)
    # ...and the enzymatic side is no longer a single line: sucrose is on it,
    # at one turnover per product molecule.
    assert recycled.advantage_min_kgCO2e is not None


def test_the_fair_fight_holds_once_both_sides_are_evidenced(inputs):
    """Where two corrections in opposite directions left the answer.

    Charging the real sucrose amount (4.2x the theoretical one) made the 99%
    column collapse to no verdict. Replacing sucrose's ceiling -- an
    unjustified 10 kgCO2e/kg -- with ADEME/Agribalyse evidence at 0.754
    brought it back. The intermediate result was an artefact of the bound,
    not of the chemistry, and both corrections were right.

    What holds it up at 99% is not solvent. At that recovery the chemical
    side is dominated by reagents that do not recover at all -- 8.9 kg of
    potassium carbonate per kg of product, the peracetylated donor, sulfuric
    acid -- while the enzymatic side's whole burden regenerates. That
    asymmetry, not the isolation solvent, is what the class actually turns on
    once both routes are pushed hard.
    """
    curve = fair_fight_frontier(*inputs, efforts=(0.0, 0.9, 0.99))
    assert all(p.enzyme_wins == 388 for p in curve)
    assert all(p.chemistry_wins == 0 for p in curve)


def test_sucrose_is_bounded_by_evidence_not_by_a_round_number(inputs):
    """The dominant enzymatic term, and where its ceiling comes from.

    Sucrose is charged 4.196 times per mole of product, which makes it larger
    than the cofactor it regenerates. Its ceiling is ADEME Base Carbone's
    Agribalyse figure for white sugar -- retail packaged, so an over-estimate
    of bulk technical sucrose, which is exactly why it is a defensible
    ceiling and not a factor.
    """
    bounds = inputs[5]
    sucrose = bounds["name:chebi:17992"]
    assert sucrose.high == pytest.approx(0.754)
    assert any("Agribalyse" in s for s in sucrose.sources)
    # It must stay a bound: the Agribalyse boundary is cradle-to-shelf with
    # paper packaging, not the cradle-to-gate a bioreactor feed would carry.
    assert "packag" in sucrose.rationale.lower()


def test_the_published_operating_point_is_decided_for_the_whole_class(inputs):
    """The question the tool exists to answer, at real numbers on both sides.

    Liu et al. report the UDP-glucose recycled 240 times, and industrial
    distillation recovers about 90%. Screened at those two published figures
    rather than at round numbers, every reaction in the class has a
    guaranteed saving -- one that holds everywhere inside the asserted
    bounds, sucrose's included.
    """
    run = screen_all(*inputs, cofactor_recycling=1 - 1 / 240, reference_recovery=0.90)
    guaranteed = [r for r in run.decided if r.advantage_decided]
    assert len(guaranteed) == len(run.decided) == 388


def test_the_fair_fight_report_names_what_actually_decides_it(inputs):
    """A table saying the enzyme wins 388-0 at 99% effort is worthless without
    the reason. The dominant solvent term is a bench isolation, and recovery
    can only divide it -- it cannot un-choose it."""
    from carbonroute.report import render_fair_fight

    text = render_fair_fight(fair_fight_frontier(*inputs, efforts=(0.0, 0.9)), inputs[1])
    assert "ethyl acetate" in text
    assert "159.2 kg per mole" in text
    assert "upper bound on the enzymatic advantage" in text


# --- what bond was formed, which the mass delta cannot see -------------------

ACETYL_ON_HETEROATOM = "[O,N,n,S;!$([O,N,S]=*)][CX3](=[OX1])[CH3]"


def test_count_substructure_counts_a_bond_not_a_mass():
    # Ethyl acetate has one acetyl on an oxygen; acetone has none on any
    # heteroatom, though both are small carbonyls.
    assert count_substructure("CC(=O)OCC", ACETYL_ON_HETEROATOM) == 1
    assert count_substructure("CC(=O)C", ACETYL_ON_HETEROATOM) == 0
    assert count_substructure("not-a-smiles", ACETYL_ON_HETEROATOM) is None
    assert count_substructure("CCO", "not-a-smarts(") is None


def _acetyl_template(tmp_path: Path, *, bond: bool, ec: bool) -> Path:
    p = tmp_path / "acetyl.yaml"
    lines = [
        "reaction_class:",
        "  id: acetyl",
        "  name: Acetylation",
        "  cofactor_chebi: 'CHEBI:57288'",
        "  expected_mass_delta: 42.037",
    ]
    if bond:
        lines.append(f"  transferred_bond_smarts: '{ACETYL_ON_HETEROATOM}'")
    if ec:
        lines.append("  ec_prefix: '2.3.1'")
    lines += [
        "chemical_counterpart:",
        "  name: C",
        "  source: S",
        "  materials:",
        "    - {name: acetic anhydride, cas: '108-24-7', kg_per_mol_product: 0.102,"
        " basis: sourced, note: n}",
    ]
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


def test_ec_prefix_narrows_a_cofactor_that_does_more_than_one_thing(inputs, tmp_path):
    """Acetyl-CoA is consumed by 347 reactions in Rhea. Only a fraction are
    acyl transfers; the rest are Claisen condensations, redox steps and the
    cofactor's own hydrolysis. Without `ec_prefix` the class is the whole
    neighbourhood."""
    reactions = inputs[0]
    wide = load_template(_acetyl_template(tmp_path, bond=False, ec=False))
    narrow_dir = tmp_path / "n"
    narrow_dir.mkdir()
    narrow = load_template(_acetyl_template(narrow_dir, bond=False, ec=True))
    assert wide.ec_prefix is None and narrow.ec_prefix == "2.3.1"
    assert sum(1 for r in reactions if wide.matches(r)) == 347
    assert sum(1 for r in reactions if narrow.matches(r)) == 138


def test_the_bond_check_rejects_chemistry_the_mass_check_lets_through(inputs, tmp_path):
    """The finding that made this check necessary.

    RHEA:21564 (an acyl-CoA + acetyl-CoA = a 3-oxoacyl-CoA + CoA) is a
    beta-ketoacyl synthase: a Claisen condensation forming a carbon-carbon
    bond. It consumes acetyl-CoA, it is annotated EC 2.3.1, and it adds
    exactly the 42.04 g/mol an acetylation adds -- so cofactor, EC group and
    mass delta all wave it through. It is not an acetylation, and no
    acetic-anhydride procedure is a counterpart for it. Only asking what bond
    was formed catches it.
    """
    reactions, _tpl, structures, table, assumptions, bounds = inputs
    template = load_template(_acetyl_template(tmp_path, bond=True, ec=True))
    by_id = {r.rhea_id: r for r in reactions}

    claisen = screen_reaction(
        by_id["RHEA:21564"], template, structures, table, assumptions, bounds
    )
    assert not claisen.decided
    assert "not 1" in claisen.skipped_reason and "different transformation" in claisen.skipped_reason

    # A genuine N-acetylation in the same EC group, same donor, same mass.
    real = screen_reaction(
        by_id["RHEA:24292"], template, structures, table, assumptions, bounds
    )
    assert real.skipped_reason == ""
    assert real.acceptor_name == "L-glutamate"


def test_the_shipped_glycosylation_class_declares_no_bond_check(screened):
    """It does not need one, and saying so is part of the claim.

    UDP-hexose is the rare cofactor that does one thing: every resolvable
    acceptor/product pair in the class lands on the anhydrohexosyl mass, and
    the exclusions were verified by hand. The bond check exists for donors
    like acetyl-CoA that do not behave that way, and switching it on here
    would imply a doubt the data does not support.
    """
    assert screened.template.transferred_bond_smarts is None
    assert screened.template.ec_prefix is None
    assert screened.matched == 406


# --- a declared process instead of one paper's bench run ---------------------


@pytest.fixture(scope="module")
def by_process_model(inputs):
    return screen_all(
        *inputs,
        use_process_model=True,
        cofactor_recycling=1 - 1 / 240,
        reference_recovery=0.90,
    )


def test_the_process_model_charges_from_parameters_not_from_a_paper(inputs):
    """Solvent from a stated concentration, reagents at stated equivalents.

    Everything it produces is `generalised` by construction: nothing in it was
    read from a procedure, and saying so is the point rather than a weakness.
    """
    model = inputs[1].process_model
    assert model is not None
    materials = materials_from_process_model(model)
    assert all(m.basis == "generalised" for m in materials)
    assert all("process model" in m.note for m in materials)
    # The isolation stage: 5 reaction volumes at 0.2 M, ethyl acetate at
    # 0.902 kg/L, carried through one stage yield.
    etoac = next(m for m in materials if m.name == "ethyl acetate")
    expected = (1 / 0.2) * 5.0 * 0.902 / (0.85 ** 1)
    assert etoac.kg_per_mol_product == pytest.approx(expected, rel=1e-6)
    # The protection stage still scales with the acceptor's own structure.
    anhydride = next(m for m in materials if m.name == "acetic anhydride")
    assert anhydride.per_protected_group is True


def test_the_paper_charges_six_times_the_isolation_solvent_a_process_would(inputs):
    """The number that was deciding every verdict, put next to a modelled one.

    Cepanec & Litvic charge 159 kg of ethyl acetate per mole of product -- 150
    mL of boiling solvent per millimole, an effective isolation concentration
    near 0.03 M. The model charges 5 reaction volumes at 0.2 M. The gap is not
    a disagreement about chemistry; it is the difference between a bench run
    and a process.
    """
    template = inputs[1]
    paper = {m.name: m.kg_per_mol_product for m in template.materials}
    model = {m.name: m.kg_per_mol_product for m in materials_from_process_model(template.process_model)}
    assert paper["ethyl acetate"] / model["ethyl acetate"] == pytest.approx(6.0, abs=0.3)
    # The donor, which is real chemistry rather than habit, agrees closely.
    assert paper["1,2,3,4,6-penta-O-acetyl-beta-D-glucopyranose"] / model[
        "1,2,3,4,6-penta-O-acetyl-beta-D-glucopyranose"
    ] == pytest.approx(1.0, abs=0.15)


def test_the_verdict_survives_being_modelled_instead_of_quoted(
    at_published_operating_point, by_process_model, inputs
):
    """The robustness check the process model was built to make possible.

    Screened against a competent process rather than one paper's bench run,
    the enzymatic advantage shrinks by roughly six-fold -- that is the size of
    the "which paper did you pick" effect, measured rather than argued. What
    matters is that the conclusion does not move with it: all 388 reactions
    still have a guaranteed saving. A finding that survives its own dominant
    assumption being replaced is worth more than one that was never tested.
    """
    paper = next(
        x for x in at_published_operating_point.decided if x.rhea_id == "RHEA:12560"
    )
    modelled = next(x for x in by_process_model.decided if x.rhea_id == "RHEA:12560")
    assert modelled.advantage_min_kgCO2e < paper.advantage_min_kgCO2e / 4
    assert modelled.advantage_min_kgCO2e > 0
    assert len([x for x in by_process_model.decided if x.advantage_decided]) == 388


def test_modelling_the_process_loosens_the_grip_of_one_material(
    at_published_operating_point, by_process_model, inputs
):
    """And it does what it was for: the verdicts stop being about one number.

    Under the paper template a single material carries a median 80% of every
    delta and is the top term in all 388 reactions. Under the model that falls
    to 60%, and it is no longer the top term in a substantial minority.
    """
    bounds = inputs[5]

    def profile(run):
        ex = [explain_verdict(r.standard_diff, bounds) for r in run.decided]
        conc = sorted(e.concentration for e in ex)
        etoac = sum(1 for e in ex if e.top.name == "ethyl acetate")
        return conc[len(conc) // 2], etoac

    paper_conc, paper_etoac = profile(at_published_operating_point)
    model_conc, model_etoac = profile(by_process_model)
    assert paper_etoac == 388
    assert model_etoac < 300
    assert model_conc < paper_conc - 0.1


# --- what a verdict is actually made of --------------------------------------


def test_explain_ranks_by_share_and_classes_the_evidence(at_published_operating_point, inputs):
    """Provenance says where a number came from; this says how much of the
    answer it carries. Shares are of the absolute delta and must total one."""
    bounds = inputs[5]
    r = next(
        x for x in at_published_operating_point.decided if x.rhea_id == "RHEA:12560"
    )
    e = explain_verdict(r.standard_diff, bounds)
    assert e.contributions == tuple(sorted(e.contributions, key=lambda c: -c.share))
    assert sum(c.share for c in e.contributions) == pytest.approx(1.0)
    assert e.measured_share + e.bounded_share + e.unbounded_share == pytest.approx(1.0)
    assert {c.evidence for c in e.contributions} <= {"measured", "bounded", "unbounded"}
    # Chemical-side materials are valued at their floor and enzymatic ones at
    # their ceiling: the case least favourable to "the enzyme wins".
    sucrose = next(c for c in e.contributions if c.key == "name:chebi:17992")
    assert sucrose.side == "enzymatic"
    assert sucrose.value_kgCO2e_per_kg == pytest.approx(bounds["name:chebi:17992"].high)


def test_every_verdict_in_this_class_rests_on_one_material(at_published_operating_point, inputs):
    """The finding this detector was built to surface, and it is not a
    comfortable one.

    In all 388 decided reactions the single largest term carries at least
    half the delta, and it is the same material every time: ethyl acetate,
    the template's 159 kg/mol bench isolation. The verdicts are therefore
    mostly a statement about one paper's choice of extraction volume. That
    does not make them wrong, but it makes them narrower than they look, and
    nothing in a provenance discipline alone would have said so.
    """
    bounds = inputs[5]
    explained = [
        explain_verdict(r.standard_diff, bounds)
        for r in at_published_operating_point.decided
    ]
    assert all(e.concentration >= 0.5 for e in explained)
    assert all(e.top.name == "ethyl acetate" for e in explained)
    median = sorted(e.concentration for e in explained)[len(explained) // 2]
    assert median == pytest.approx(0.80, abs=0.03)


def test_the_cofactor_carries_almost_none_of_the_verdict(at_published_operating_point, inputs):
    """A claim this repository made about itself, checked and found false.

    The bounds file described UDP-glucose as "the whole cost of the enzymatic
    route" and "where the screen's verdict actually lives". Measured, it
    carries under 1% of the delta -- and it is the second most heavily
    documented entry in that file. Effort here has been close to inversely
    correlated with leverage, which is precisely what a provenance-only
    discipline cannot detect.
    """
    bounds = inputs[5]
    r = next(
        x for x in at_published_operating_point.decided if x.rhea_id == "RHEA:12560"
    )
    e = explain_verdict(r.standard_diff, bounds)
    cofactor = next(c for c in e.contributions if c.key == "name:chebi:58885")
    assert cofactor.share < 0.05
    top = e.top
    assert top.share > 15 * cofactor.share


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


# --- a second class: SAM-dependent methylation --------------------------


@pytest.fixture(scope="module")
def sam_inputs():
    reactions, _ = load_reactions(RHEA / "reactions.tsv")
    structures = load_structures(RHEA / "participants.csv")
    template = load_template(CLASSES / "sam-methyltransferase.yaml")
    bounds = load_bounds(CLASSES / "sam-methyltransferase.bounds.yaml")
    table = FactorTable.load(list(default_factor_paths(ROOT)))
    for syn in default_synonym_paths(ROOT):
        table.load_synonyms(syn)
    assumptions = load_ledger(ARBUTIN / "ledger.yaml").assumptions
    return reactions, template, structures, table, assumptions, bounds


@pytest.fixture(scope="module")
def sam_screened(sam_inputs):
    return screen_all(*sam_inputs, use_process_model=True)


def test_sam_template_has_no_materials_but_does_have_a_process_model(sam_inputs):
    """This class ships with no chemical_counterpart.materials at all -- it
    is screened only via --process-model. load_template must accept that
    (materials may be empty when a process_model is present) and screening
    without --process-model must fail loudly rather than silently produce an
    empty chemical side."""
    template = sam_inputs[1]
    assert template.materials == ()
    assert template.process_model is not None
    reactions, _, structures, table, assumptions, bounds = sam_inputs
    rxn = next(r for r in reactions if r.rhea_id == "RHEA:10072")
    with pytest.raises(ScreenError, match="process_model"):
        screen_reaction(rxn, template, structures, table, assumptions, bounds)


def test_sam_class_matches_and_decides_the_expected_number(sam_screened):
    """946 Rhea reactions consume SAM at all; EC 2.1.1 narrows that to 449
    with a single resolvable acceptor. Of those, 351 both add the right mass
    (a multiple of 14.027 g/mol, +/- one proton) and form the right bond (a
    new methyl on a heteroatom, not carbon). The other 98 are excluded for
    reasons verified by hand: 18 unidentifiable acceptor/product pairs
    (mostly radical-SAM reactions with an extra redox cofactor), 6 with a
    mass delta that fits no multiple of 14.027, and 74 that add exactly the
    right mass but attach the new methyl to carbon -- real C-methyltransferases
    (steroid/terpene biosynthesis, DNA cytosine C5 methylation) that are not
    this class's O/N/S-alkylation chemistry. See the template's file header.
    """
    assert sam_screened.matched == 449
    assert len(sam_screened.decided) == 351


def test_sam_class_bond_check_keeps_heteroatom_methylation_only(sam_screened):
    """RHEA:32103 (trans-resveratrol -> pterostilbene, di-O-methylation) and
    RHEA:32463 (glycine -> N,N-dimethylglycine, di-N-methylation) are genuine
    members and must be screened. RHEA:13137 (cycloartenol -> cyclolaudenol)
    and RHEA:13681 (cytosine -> 5-methylcytosine in DNA) add exactly the same
    14.03 g/mol per methyl but onto a ring or alkene carbon, not a
    heteroatom -- the bond check must exclude them even though the mass
    check alone would not.
    """
    by_id = {r.rhea_id: r for r in sam_screened.results}
    assert by_id["RHEA:32103"].decided
    assert by_id["RHEA:32463"].decided
    assert not by_id["RHEA:13137"].decided
    assert "does not match" in by_id["RHEA:13137"].skipped_reason or (
        "different transformation" in by_id["RHEA:13137"].skipped_reason
    )
    assert not by_id["RHEA:13681"].decided


def test_sam_class_scales_with_di_and_tri_methylation(sam_screened):
    """RHEA:32351 (tricetin -> 3',4',5'-O-trimethyltricetin) consumes 3 SAM
    per product, read from Rhea's own stoichiometric coefficient -- the same
    cofactor_coeff mechanism the glycosylation class uses for bis-glucosides.
    It is decided only because both the mass-delta check (3 x 14.027) and the
    bond check (3 new methyls on oxygen) scaled with that coefficient rather
    than staying fixed at 1; RHEA:32347, the same tricetin donor's
    di-methylated relative (2 SAM, +28.1), is a real member too, confirming
    the scaling is not a fluke of one reaction."""
    by_id = {r.rhea_id: r for r in sam_screened.results}
    assert by_id["RHEA:32351"].decided
    assert by_id["RHEA:32347"].decided
    tri = next(x for x in sam_screened.decided if x.rhea_id == "RHEA:32351")
    assert tri.cofactor_kg_per_fu > 0


def test_sam_process_model_charges_methyl_iodide_and_base(sam_inputs):
    """The declared process, not a paper: methyl iodide and potassium
    carbonate in acetone, scaling per methyl transferred, plus a plant-style
    isolation. Everything generalised by construction."""
    template = sam_inputs[1]
    materials = materials_from_process_model(template.process_model)
    names = {m.name for m in materials}
    assert {"methyl iodide", "potassium carbonate", "acetone", "ethyl acetate"} <= names
    assert all(m.basis == "generalised" for m in materials)


def test_sam_class_is_decided_and_bounded(sam_screened):
    """At default settings (stoichiometric cofactor, zero solvent recovery)
    every decided reaction should produce a verdict -- not necessarily
    "enzyme wins" by construction, but a computable one, which confirms the
    template's bounds file actually resolves enough of the delta to decide.
    """
    decided_with_verdict = [
        r for r in sam_screened.decided if r.verdict is not None and r.verdict.decisive
    ]
    assert len(decided_with_verdict) == len(sam_screened.decided)
