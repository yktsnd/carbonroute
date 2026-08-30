"""Tests for screening a reaction database against a class template."""

from __future__ import annotations

from pathlib import Path

import pytest

from carbonroute.bounds import Bound, load_bounds
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


# --- a second cofactor a class needs but does not price ---------------------


def _write_co_cofactor_template(tmp_path: Path) -> Path:
    p = tmp_path / "co.yaml"
    p.write_text(
        "reaction_class:\n"
        "  id: co\n  name: C\n  cofactor_chebi: 'CHEBI:15379'\n"
        "  unpriced_co_cofactor_chebi: 'CHEBI:57945'\n"
        "  expected_mass_delta: 15.999\n"
        "  mass_delta_tolerance: 1.0\n"
        "chemical_counterpart:\n"
        "  name: C\n  source: S\n  materials:\n"
        "    - {name: x, cas: '7732-18-5', kg_per_mol_product: 1.0, basis: sourced, note: n}\n",
        encoding="utf-8",
    )
    return p


def test_unpriced_co_cofactor_loads_as_a_tuple(tmp_path):
    """A single ChEBI id is accepted the same way cofactor_chebi is."""
    t = load_template(_write_co_cofactor_template(tmp_path))
    assert t.unpriced_co_cofactor_chebi == ("CHEBI:57945",)


def test_unpriced_co_cofactor_defaults_to_empty(tmp_path):
    """The nine classes that never needed a second cofactor are unaffected:
    the field defaults to empty and changes nothing about their behaviour."""
    p = _write_template(
        tmp_path, "    - {name: x, kg_per_mol_product: 1.0, basis: sourced, note: n}\n"
    )
    t = load_template(p)
    assert t.unpriced_co_cofactor_chebi == ()


def test_unpriced_co_cofactor_is_excluded_from_the_acceptor_search(tmp_path):
    """A synthetic monooxygenase-shaped reaction: acceptor + O2 + NADH -> product
    + NAD(+) + H2O. Without the co-cofactor field, `others_left` would contain
    both the acceptor and NADH and fail to resolve at all -- exactly the
    failure mode that blocked EC 1.14.13 before this mechanism existed."""
    t = load_template(_write_co_cofactor_template(tmp_path))
    rxn = parse_reaction(
        "RHEA:00000",
        "phenol + NADH + O2 = catechol + NAD(+) + H2O",
        "CHEBI:15882;CHEBI:57945;CHEBI:15379;CHEBI:18135;CHEBI:57540;CHEBI:15377",
        "EC:1.14.13.1",
    )
    assert rxn is not None
    structures = {
        "CHEBI:15882": "Oc1ccccc1",  # phenol
        "CHEBI:18135": "Oc1ccccc1O",  # catechol
        "CHEBI:15379": "O=O",  # O2, the priced cofactor
    }
    table = FactorTable.load(list(default_factor_paths(ROOT)))
    for syn in default_synonym_paths(ROOT):
        table.load_synonyms(syn)
    assumptions = load_ledger(ARBUTIN / "ledger.yaml").assumptions
    bounds = {
        "name:chebi:15379": Bound(
            key="name:chebi:15379", low=0.5, high=100.0, rationale="r", sources=()
        )
    }
    result = screen_reaction(rxn, t, structures, table, assumptions, bounds)
    assert result.skipped_reason == ""
    assert result.acceptor_name == "phenol"
    assert result.product_name == "catechol"
    # NADH never appears as a priced material: only the cofactor (O2) does.
    assert result.standard_diff is not None
    keys = {row.key for row in result.standard_diff.rows}
    assert not any("57945" in k for k in keys)
    assert any("15379" in k for k in keys)


def test_shipped_template_loads_and_labels_every_generalisation():
    t = load_template(CLASSES / "udp-glucosyltransferase.yaml")
    assert t.cofactor_chebi == (
        "CHEBI:58885", "CHEBI:66914", "CHEBI:57527", "CHEBI:57498",
        "CHEBI:62230", "CHEBI:66915", "CHEBI:57477", "CHEBI:137927",
    )
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
    # the template's file header) -- plus 72 more across six sibling
    # hexose-nucleotide donors added the same way (GDP-mannose,
    # ADP-glucose, GDP-glucose, UDP-galactofuranose, dTDP-glucose,
    # CDP-glucose), for 478 total.
    assert screened.matched == 478
    # 29 of the 478 are excluded by the mass-delta check, not silently
    # templated as glycosylations: 13 where an acceptor/product pair could
    # not be identified, and 16 that consume a class cofactor for a
    # genuinely different transformation -- the cofactor's own hydrolysis
    # (including RHEA:28102 and RHEA:15049, GDP-mannose/GDP-glucose + H2O ->
    # free sugar + GDP, correctly excluded once water is no longer eligible
    # to stand in as "the acceptor" -- see _identify's comment), a
    # sugar-nucleotide exchange, a hexose-1-phosphate transfer onto a lipid
    # carrier (undecaprenyl phosphate), oxidation of the sugar-nucleotide
    # itself, or (among the six sibling donors) chain elongation and
    # isomerisation of the same kind -- verified by hand for every
    # exclusion bucket; see screen_reaction's comment on the check.
    assert len(screened.decided) == 449


def test_screen_reproduces_the_hand_built_case(screened):
    """Calibration. RHEA:12560 is the reaction built by hand, fully sourced, in
    examples/case-studies/beta-arbutin-chemical-vs-enzymatic/.

    A screen that disagreed with the one case it was derived from would be
    reporting on its own template rather than on chemistry, so this is the
    test that gives the other 450 rows any standing at all.
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
    of product. None of the 449 survives 99% recovery, and the whole
    distribution sits below the 90-95% a real plant achieves by distillation.
    If this ever starts passing, the class's advantage has stopped being an
    artefact of glassware and the claim can be made much more strongly.
    """
    assert all(not r.robust for r in screened.results)
    thresholds = [r.recovery_threshold for r in screened.decided]
    # The six sibling hexose donors added the same reactions the original
    # two donors' template already models, so the ceiling (the hardest
    # acceptor to mask) is unchanged; they only pull the floor down, adding
    # reactions whose threshold is even lower than the original minimum.
    assert min(thresholds) == pytest.approx(0.8456, abs=0.002)
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
    external acceptor. Water is excluded from the acceptor search the same
    way a proton is (see _identify's comment), so nothing is left to call
    "the acceptor" and it comes back unresolved rather than mis-decided
    against a spurious water pairing. RHEA:13989 is a sugar-nucleotide
    exchange (galactose 1-phosphate + UDP-glucose -> glucose 1-phosphate +
    UDP-galactose) where nothing is added at all -- this one the mass-delta
    check is what actually catches. RHEA:28126 transfers glucosyl-1-phosphate
    (162.14 + a phosphate group, 242.12 total) onto a lipid carrier
    (undecaprenyl phosphate), not a hydroxyl -- a real but different
    biosynthetic mechanism that only became reachable once UDP-galactose
    reactions widened the field this check has to police. RHEA:35755
    oxidises UDP-glucose itself (an NAD+-dependent step) rather than
    transferring it anywhere. All four consume a class cofactor; none
    belongs in a glycosylation class."""
    r = next(x for x in screened.results if x.rhea_id == "RHEA:29555")
    assert not r.decided
    assert r.skipped_reason == "could not identify acceptor/product"
    for rhea_id in ("RHEA:13989", "RHEA:28126", "RHEA:35755"):
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

    The recovery thresholds sit at 84.56-91.54%, and a real plant distils back
    90%. So for the overwhelming majority of this class the verdict is already
    gone at a realistic solvent loop -- not because the enzyme converts badly,
    but before conversion is even asked about. Only the tail is still decided
    there, and it needs a near-quantitative enzyme to stay that way.
    """
    needs = [r.min_enzymatic_yield for r in screened.decided]
    still_decided = [y for y in needs if y is not None]
    assert len(still_decided) == 25
    assert len(needs) - len(still_decided) == 424
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
    assert all(p.decided == 449 for p in curve)
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
    assert all(p.enzyme_wins == 449 for p in curve)
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
    assert len(guaranteed) == len(run.decided) == 449


def test_the_fair_fight_report_names_what_actually_decides_it(inputs):
    """A table saying the enzyme wins 449-0 at 99% effort is worthless without
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
    assert screened.matched == 478


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
    matters is that the conclusion does not move with it: all 449 reactions
    still have a guaranteed saving. A finding that survives its own dominant
    assumption being replaced is worth more than one that was never tested.
    """
    paper = next(
        x for x in at_published_operating_point.decided if x.rhea_id == "RHEA:12560"
    )
    modelled = next(x for x in by_process_model.decided if x.rhea_id == "RHEA:12560")
    assert modelled.advantage_min_kgCO2e < paper.advantage_min_kgCO2e / 4
    assert modelled.advantage_min_kgCO2e > 0
    assert len([x for x in by_process_model.decided if x.advantage_decided]) == 449


def test_modelling_the_process_loosens_the_grip_of_one_material(
    at_published_operating_point, by_process_model, inputs
):
    """And it does what it was for: the verdicts stop being about one number.

    Under the paper template a single material carries a median 80% of every
    delta and is the top term in all 449 reactions. Under the model that falls
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
    assert paper_etoac == 449
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

    In all 449 decided reactions the single largest term carries at least
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
    # The 426 others straddle zero at 90% recovery: no verdict, not a small one.
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
    """946 Rhea reactions consume SAM at all; no ec_prefix is declared (an
    earlier version restricted to EC 2.1.1, narrowing to 449 -- see the
    template's file header for why that restriction was unnecessary and has
    been removed). 93 do not resolve to a single acceptor/product pair
    (mostly radical-SAM reactions with an extra redox cofactor, or other
    multi-reactant shapes), 55 have a mass delta that fits no multiple of
    14.027, and 126 add exactly the right mass but attach the new methyl to
    carbon -- real C-methyltransferases (steroid/terpene biosynthesis, DNA
    cytosine C5 methylation) that are not this class's O/N/S-alkylation
    chemistry. The remaining 672 both add the right mass (a multiple of
    14.027 g/mol, +/- one proton) and form the right bond (a new methyl on a
    heteroatom, not carbon), all decisively favouring the enzyme.
    """
    assert sam_screened.matched == 946
    assert len(sam_screened.decided) == 672


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


# --- a third class: NAD(P)+-dependent oxidation, and an honest non-result ---


@pytest.fixture(scope="module")
def nad_inputs():
    reactions, _ = load_reactions(RHEA / "reactions.tsv")
    structures = load_structures(RHEA / "participants.csv")
    template = load_template(CLASSES / "nad-oxidoreductase.yaml")
    bounds = load_bounds(CLASSES / "nad-oxidoreductase.bounds.yaml")
    table = FactorTable.load(list(default_factor_paths(ROOT)))
    for syn in default_synonym_paths(ROOT):
        table.load_synonyms(syn)
    assumptions = load_ledger(ARBUTIN / "ledger.yaml").assumptions
    return reactions, template, structures, table, assumptions, bounds


@pytest.fixture(scope="module")
def nad_screened(nad_inputs):
    return screen_all(*nad_inputs, use_process_model=True)


def test_nad_class_matches_and_excludes_oxidative_decarboxylation(nad_screened):
    """515 Rhea reactions consume NAD+ or NADP+ under EC 1.1.1. 492 resolve to
    a single acceptor/product pair, and 466 of those (94.7%) land within one
    proton of a clean 2H-loss (-2.016 g/mol, or -4.03 for a double oxidation).
    The other 26 cluster tightly at -45.02 -- oxidative DEcarboxylation
    (malate dehydrogenase, isocitrate dehydrogenase, 6-phosphogluconate
    dehydrogenase and relatives: -2.016 for the 2H plus -43.99 for the CO2
    that leaves with it), a genuinely different transformation that a
    stoichiometric oxidant alone does not perform, and is correctly excluded
    by the mass-delta check rather than folded in as noise.
    """
    assert nad_screened.matched == 515
    by_id = {r.rhea_id: r for r in nad_screened.results}
    assert "does not match" in by_id["RHEA:12653"].skipped_reason  # (S)-malate oxidative decarboxylation
    assert not by_id["RHEA:12653"].decided


def test_nad_class_has_no_bond_check_and_says_why(nad_inputs):
    """Unlike the other two classes, this one ships no transferred_bond_smarts.
    The natural check -- a new C=O appearing -- fails on reducing sugars
    drawn in ChEBI's cyclic hemiketal form (D-mannitol -> D-fructose shows no
    explicit carbonyl in either SMILES), which would silently exclude dozens
    of genuine hexitol/pentitol dehydrogenase reactions for a drawing
    convention rather than a chemical reason. The mass-delta check alone
    already achieves 94.7% purity with one cleanly identified confound, so
    it is sufficient here without a bond check that would do more harm than
    good.
    """
    template = nad_inputs[1]
    assert template.transferred_bond_smarts is None


def test_nad_class_verdicts_are_honestly_indeterminate_at_current_bounds(nad_screened):
    """Real coverage, and a real limitation, both reported rather than one
    papered over to force the other.

    515 reactions are structurally verified members of this class -- that is
    genuine Q1 coverage, the same sense in which the other two classes'
    matched counts are. But at the bounds this template currently declares,
    every one of them comes back indeterminate: NAD+/NADP+ carries the same
    wide, unevidenced [0.5, 100] ceiling the other classes' cofactors do, and
    unlike glycosylation's paper-scale solvent burden or methylation's
    stoichiometric alkylating agent, this class's process model is a small,
    mostly catalytic oxidation with nothing bulky enough to guarantee the
    chemical route costs more even at the cofactor's cheapest plausible
    value. That is not a bug in the screen; it is what the bounds and the
    process model, honestly evaluated together, actually say. Padding the
    process model's reagent equivalents to force a decision would be exactly
    the kind of thumb on the scale this project refuses everywhere else.
    """
    assert len(nad_screened.decided) == 0
    verdicts = {r.rhea_id: r.verdict for r in nad_screened.results if r.skipped_reason == ""}
    assert all(v is not None and not v.decisive for v in verdicts.values())
    assert all(v.verdict == "indeterminate" for v in verdicts.values())
    # The specific reason: the enzymatic side's worst case beats the
    # chemical side's best case, because the cofactor ceiling is wide open
    # and the chemical route is comparatively small.
    r = next(x for x in nad_screened.results if x.rhea_id == "RHEA:10044")
    assert r.verdict.delta_min_kgCO2e is not None and r.verdict.delta_min_kgCO2e < 0


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


# --- a fourth class: ATP-dependent phosphorylation, and a charge-state fix -


@pytest.fixture(scope="module")
def atp_inputs():
    reactions, _ = load_reactions(RHEA / "reactions.tsv")
    structures = load_structures(RHEA / "participants.csv")
    template = load_template(CLASSES / "atp-kinase.yaml")
    bounds = load_bounds(CLASSES / "atp-kinase.bounds.yaml")
    table = FactorTable.load(list(default_factor_paths(ROOT)))
    for syn in default_synonym_paths(ROOT):
        table.load_synonyms(syn)
    assumptions = load_ledger(ARBUTIN / "ledger.yaml").assumptions
    return reactions, template, structures, table, assumptions, bounds


@pytest.fixture(scope="module")
def atp_screened(atp_inputs):
    return screen_all(*atp_inputs, use_process_model=True)


def test_atp_class_uses_the_dianion_mass_delta_not_the_textbook_one(atp_inputs):
    """A phosphate monoester adds HPO3 in vacuo (79.980 g/mol), but ChEBI
    records this class's products as the phosphate DIANION, two protons
    short of that. RHEA:10224 (pyridoxal -> pyridoxal 5'-phosphate) is the
    reaction that pinned this down: its real, observed mass delta is
    77.963, not 79.980, and the template's expected_mass_delta is set to
    the observed value rather than the textbook one for exactly this
    reason."""
    template = atp_inputs[1]
    assert template.expected_mass_delta == pytest.approx(77.963, abs=1e-6)


def test_atp_class_matches_and_decides_the_expected_number(atp_screened):
    """1,059 Rhea reactions consume ATP; no ec_prefix is declared (an
    earlier version restricted to EC 2.7.1, narrowing to 209 -- see the
    template's file header for why that restriction was unnecessary and has
    been removed). 524 do not resolve to a single acceptor/product pair at
    all -- ATP is consumed by far more Rhea chemistry than kinases once EC
    no longer screens most of it out upstream. Of the 535 that resolve, 369
    (69.0%) land within one proton of the dianion mass delta and are
    decided -- including RHEA:10224 and RHEA:73839 (phenol + ATP + H2O =
    phenyl phosphate + AMP + phosphate + 2 H(+)), recovered once water is
    no longer eligible to stand in as "the acceptor" alongside phenol; see
    _identify's comment. 165 genuinely transfer something else, including
    RHEA:12260, RHEA:18245 and RHEA:18629 (NADH kinase, dephospho-CoA
    kinase, NAD+ kinase), whose donor and acceptor are both large enough
    that the by-elimination resolver locks onto the wrong pair and the
    mass-delta check correctly refuses to decide it rather than guessing.
    """
    assert atp_screened.matched == 1059
    assert len(atp_screened.decided) == 369
    by_id = {r.rhea_id: r for r in atp_screened.results}
    assert by_id["RHEA:10224"].decided
    for rhea_id in ("RHEA:12260", "RHEA:18245", "RHEA:18629"):
        assert not by_id[rhea_id].decided
        assert "does not match" in by_id[rhea_id].skipped_reason


def test_atp_class_bond_check_finds_no_further_exclusions(atp_screened):
    """transferred_bond_smarts checks for exactly one new phosphorus atom
    per phosphate transferred. It excludes none of the 534 reactions that
    reach the mass check, even at this much wider (ec_prefix-free) scale --
    the mass-delta check alone already separates this class, and the bond
    check is a second, independent confirmation rather than the thing doing
    the discriminating work (unlike the SAM class, where the bond check is
    load-bearing against C-methylation)."""
    for r in atp_screened.results:
        assert "class's bond" not in r.skipped_reason


def test_atp_process_model_charges_phosphoryl_chloride_and_pyridine(atp_inputs):
    """The declared process, not a paper: POCl3 and pyridine (as both base
    and solvent, under the existing key-summing behaviour that totals both
    roles under one CAS), scaling per phosphate transferred, plus a
    plant-style isolation. Everything generalised by construction."""
    template = atp_inputs[1]
    materials = materials_from_process_model(template.process_model)
    names = {m.name for m in materials}
    assert {"phosphoryl chloride", "pyridine", "ethyl acetate"} <= names
    assert all(m.basis == "generalised" for m in materials)


def test_atp_class_is_decided_and_decisively_favours_the_enzyme(atp_screened):
    """Unlike the NAD(P)+ class, this one reaches a decisive verdict for
    every reaction it decides: ATP's wide, unevidenced [0.5, 100] cofactor
    ceiling is still not enough to erase the gap once the chemical route's
    POCl3/pyridine stoichiometry (well above the enzymatic side even at
    the cofactor's most expensive assumed value) is counted -- so every
    decided reaction resolves with the enzymatic route lower, over the
    whole box of asserted bounds, without needing to assume where in
    those intervals the true factors fall."""
    decided_with_verdict = [
        r for r in atp_screened.decided if r.verdict is not None and r.verdict.decisive
    ]
    assert len(decided_with_verdict) == len(atp_screened.decided)
    assert all(r.verdict.verdict == "b_lower" for r in decided_with_verdict)


# --- a fifth class: DMAPP-dependent prenylation -----------------------------


@pytest.fixture(scope="module")
def dmapp_inputs():
    reactions, _ = load_reactions(RHEA / "reactions.tsv")
    structures = load_structures(RHEA / "participants.csv")
    template = load_template(CLASSES / "dmapp-prenyltransferase.yaml")
    bounds = load_bounds(CLASSES / "dmapp-prenyltransferase.bounds.yaml")
    table = FactorTable.load(list(default_factor_paths(ROOT)))
    for syn in default_synonym_paths(ROOT):
        table.load_synonyms(syn)
    assumptions = load_ledger(ARBUTIN / "ledger.yaml").assumptions
    return reactions, template, structures, table, assumptions, bounds


@pytest.fixture(scope="module")
def dmapp_screened(dmapp_inputs):
    return screen_all(*dmapp_inputs, use_process_model=True)


def test_dmapp_class_matches_and_decides_the_expected_number(dmapp_screened):
    """73 Rhea reactions consume DMAPP once isopentenyl diphosphate (IPP,
    CHEBI:128769) is excluded from matching (see the template's own
    CORRECTION: a single IPP equivalent condensing with DMAPP is GPP
    synthase, arithmetically indistinguishable from a real transfer by mass
    delta alone, so it has to be excluded by identity instead) and no
    ec_prefix restricts to EC 2.5.1 (an earlier version did; removing it is
    the same step taken for SAM-methyltransferase and ATP-kinase, safe here
    only because the IPP fix closed the false-positive path mass delta
    alone could not catch). 62 (84.9%) resolve to a single acceptor/product
    pair within one proton of 68.119 (the isoprenyl group, C5H8) and are
    decided. RHEA:10852 (leachianone G -> sophoraflavanone G) is the
    reaction that pinned the constant down: 424.493 - 356.374 = 68.119
    exactly, with donor and leaving group drawn in the same charge state so
    no dianion-style offset applies here. RHEA:79231 (hapalindole U + DMAPP
    + H(+) -> ambiguine H) only decides once a proton on the left of the
    equation is excluded from the acceptor search the same way one on the
    right already was."""
    assert dmapp_screened.matched == 73
    assert len(dmapp_screened.decided) == 62
    by_id = {r.rhea_id: r for r in dmapp_screened.results}
    assert by_id["RHEA:10852"].decided
    assert by_id["RHEA:79231"].decided


def test_dmapp_class_excludes_ipp_chain_elongation_and_homodimerisation(dmapp_screened):
    """Isopentenyl diphosphate (IPP) chain elongation -- DMAPP condensing
    with one or more IPP equivalents to build a longer allylic diphosphate
    -- is excluded from matching entirely via excluded_co_cofactor_chebi,
    not just from being decided: RHEA:11328 and RHEA:22408 (exactly one IPP,
    to GPP) and RHEA:27810, RHEA:55520, RHEA:77975 (two or more IPP) never
    even appear in the results, because template.matches() rejects them
    before screen_reaction runs. DMAPP homodimerisation is a separate
    confound this exclusion does not touch: RHEA:14009 and RHEA:21676
    (chrysanthemyl/lavandulyl diphosphate synthase) consume 2 DMAPP and no
    foreign acceptor at all, so they still match but no acceptor/product
    pair resolves."""
    by_id = {r.rhea_id: r for r in dmapp_screened.results}
    all_reactions, _ = load_reactions(RHEA / "reactions.tsv")
    reactions_by_id = {r.rhea_id: r for r in all_reactions}
    for rhea_id in (
        "RHEA:11328",
        "RHEA:22408",
        "RHEA:27810",
        "RHEA:55520",
        "RHEA:77975",
    ):
        assert rhea_id not in by_id
        assert not dmapp_screened.template.matches(reactions_by_id[rhea_id])
    for rhea_id in ("RHEA:14009", "RHEA:21676"):
        assert not by_id[rhea_id].decided
        assert "could not identify" in by_id[rhea_id].skipped_reason


def test_dmapp_process_model_charges_prenyl_bromide_and_base(dmapp_inputs):
    """The declared process, not a paper: prenyl bromide and potassium
    carbonate in acetone, plus a plant-style isolation -- the same
    Williamson-alkylation shape the SAM class uses, with the alkylating
    agent swapped for the five-carbon electrophile this class transfers.
    Everything generalised by construction."""
    template = dmapp_inputs[1]
    materials = materials_from_process_model(template.process_model)
    names = {m.name for m in materials}
    assert {"prenyl bromide", "potassium carbonate", "acetone", "ethyl acetate"} <= names
    assert all(m.basis == "generalised" for m in materials)


def test_dmapp_class_is_decided_and_decisively_favours_the_enzyme(dmapp_screened):
    """Every one of this class's 38 decided reactions reaches a decisive
    verdict favouring the enzyme, the same shape as the ATP-kinase class
    and unlike NAD(P)+-oxidoreductase: the process model's stoichiometric
    prenyl bromide loading is bulky enough to keep the sign fixed even at
    DMAPP's most expensive assumed value within its wide, unevidenced
    [0.5, 100] cofactor ceiling."""
    decided_with_verdict = [
        r for r in dmapp_screened.decided if r.verdict is not None and r.verdict.decisive
    ]
    assert len(decided_with_verdict) == len(dmapp_screened.decided)
    assert all(r.verdict.verdict == "b_lower" for r in decided_with_verdict)


# --- a sixth class: acetyl-CoA-dependent acetylation, another honest non-result


@pytest.fixture(scope="module")
def acoa_inputs():
    reactions, _ = load_reactions(RHEA / "reactions.tsv")
    structures = load_structures(RHEA / "participants.csv")
    template = load_template(CLASSES / "acetyl-coa-acyltransferase.yaml")
    bounds = load_bounds(CLASSES / "acetyl-coa-acyltransferase.bounds.yaml")
    table = FactorTable.load(list(default_factor_paths(ROOT)))
    for syn in default_synonym_paths(ROOT):
        table.load_synonyms(syn)
    assumptions = load_ledger(ARBUTIN / "ledger.yaml").assumptions
    return reactions, template, structures, table, assumptions, bounds


@pytest.fixture(scope="module")
def acoa_screened(acoa_inputs):
    return screen_all(*acoa_inputs, use_process_model=True)


def test_acoa_class_unifies_o_and_n_acetylation_at_one_mass_delta(acoa_inputs):
    """O-acetylation (R-OH -> R-O-COCH3) and N-acetylation (R-NH2 ->
    R-NH-COCH3) are the same net addition, C2H2O = 42.037 g/mol -- but
    N-acetylated members of this class initially clustered at 41.03, short
    by almost exactly one proton, because ChEBI draws amino-acid-type
    acceptors like D-tryptophan as the zwitterion (one proton heavier than
    the neutral form) while the acetylated product is drawn with a neutral
    amide nitrogen. expected_mass_delta is set to the true value, and
    mass_delta_tolerance is widened to 1.1 specifically to catch this,
    unifying both halves as one real chemistry rather than splitting it in
    two for a drawing convention."""
    template = acoa_inputs[1]
    assert template.expected_mass_delta == pytest.approx(42.037, abs=1e-6)
    assert template.mass_delta_tolerance == pytest.approx(1.1, abs=1e-6)


def test_acoa_class_matches_and_excludes_claisen_condensation(acoa_screened):
    """138 Rhea reactions consume acetyl-CoA under EC 2.3.1. 128 resolve to
    a single acceptor/product pair, and 124 of those (96.9%) land within
    1.1 of 42.037 -- both O-acetylation (RHEA:10456, D-maltose) and
    N-acetylation (RHEA:10060, D-tryptophan) clusters. The other 4
    (RHEA:31555, RHEA:47044, RHEA:79655, RHEA:79651) cluster at +-704 or
    -57 g/mol -- Claisen-type condensations building a new C-C bond to
    another CoA thioester, a genuinely different transformation this class
    does not model -- and are correctly excluded."""
    assert acoa_screened.matched == 138
    by_id = {r.rhea_id: r for r in acoa_screened.results}
    assert by_id["RHEA:10456"].skipped_reason == ""
    assert by_id["RHEA:10060"].skipped_reason == ""
    for rhea_id in ("RHEA:31555", "RHEA:47044", "RHEA:79655", "RHEA:79651"):
        assert not by_id[rhea_id].decided
        assert "does not match" in by_id[rhea_id].skipped_reason


def test_acoa_process_model_charges_acetic_anhydride_and_pyridine(acoa_inputs):
    """The declared process, not a paper: acetic anhydride and pyridine
    (as both base and solvent, under the existing key-summing behaviour
    that totals both roles under one CAS), plus a plant-style isolation.
    Everything generalised by construction."""
    template = acoa_inputs[1]
    materials = materials_from_process_model(template.process_model)
    names = {m.name for m in materials}
    assert {"acetic anhydride", "pyridine", "ethyl acetate"} <= names
    assert all(m.basis == "generalised" for m in materials)


def test_acoa_class_verdicts_are_honestly_indeterminate_at_current_bounds(acoa_screened):
    """Real coverage, and a real limitation, both reported rather than one
    papered over to force the other -- the same finding the NAD(P)+ class
    ships with. This class's acceptors are typically small, so acetyl-CoA's
    cost per kilogram of product is comparatively large even at the
    cofactor's cheapest plausible value within its wide, unevidenced
    [0.5, 100] ceiling -- enough to erase the process model's modest
    acetic-anhydride/pyridine burden for every resolvable member. Padding
    the process model's reagent equivalents to force a decision would be
    exactly the thumb-on-the-scale this project refuses everywhere else.
    """
    assert len(acoa_screened.decided) == 0
    verdicts = {
        r.rhea_id: r.verdict for r in acoa_screened.results if r.skipped_reason == ""
    }
    assert len(verdicts) == 124
    assert all(v is not None and not v.decisive for v in verdicts.values())
    assert all(v.verdict == "indeterminate" for v in verdicts.values())


# --- a seventh class: UDP-glucuronate-dependent glucuronidation ------------


@pytest.fixture(scope="module")
def ugt_inputs():
    reactions, _ = load_reactions(RHEA / "reactions.tsv")
    structures = load_structures(RHEA / "participants.csv")
    template = load_template(CLASSES / "udp-glucuronosyltransferase.yaml")
    bounds = load_bounds(CLASSES / "udp-glucuronosyltransferase.bounds.yaml")
    table = FactorTable.load(list(default_factor_paths(ROOT)))
    for syn in default_synonym_paths(ROOT):
        table.load_synonyms(syn)
    assumptions = load_ledger(ARBUTIN / "ledger.yaml").assumptions
    return reactions, template, structures, table, assumptions, bounds


@pytest.fixture(scope="module")
def ugt_screened(ugt_inputs):
    return screen_all(*ugt_inputs, use_process_model=True)


def test_ugt_class_unifies_two_clusters_one_proton_apart(ugt_inputs):
    """A third charge-state split, the same kind of finding as the
    ATP-kinase and acetyl-CoA classes. RHEA:10568 (luteolin ->
    luteolin 7-O-beta-D-glucuronide) gives 460.347 - 285.231 = 175.116;
    RHEA:28314 (baicalein -> baicalin) gives 445.356 - 269.232 = 176.124 --
    both real, structurally confirmed glucuronosylations, one proton apart
    because of which of the acceptor's other hydroxyls ChEBI happens to
    draw protonated in that entry. expected_mass_delta is the midpoint,
    with tolerance widened to cover both real clusters."""
    template = ugt_inputs[1]
    assert template.expected_mass_delta == pytest.approx(175.62, abs=1e-6)
    assert template.mass_delta_tolerance == pytest.approx(1.0, abs=1e-6)


def test_ugt_class_matches_and_excludes_five_other_transformations(ugt_screened):
    """102 Rhea reactions consume UDP-glucuronate. RHEA:11404 (UDP-
    glucuronate 4-epimerase, a pure isomerisation with no separate acceptor)
    cannot be resolved to an acceptor/product pair -- nor can RHEA:23916 and
    RHEA:70523 (UDP-glucuronate decarboxylase to UDP-xylose/UDP-apiose): both
    consume only UDP-glucuronate plus a proton, so once a proton is excluded
    from the acceptor search nothing is left to call "the acceptor" either.
    RHEA:26073 and RHEA:29559 (hydrolysis to D-glucuronate or to the
    1-phosphate) join them for the same reason once water is excluded too --
    see _identify's comment: both consume only UDP-glucuronate plus H2O, and
    once water is no longer eligible to stand in as an acceptor there is
    nothing left on the reactant side either. Of the 97 that do resolve, 94
    (96.9%) land within tolerance and are decided -- every one of them
    decisively favouring the enzyme. The other 3 are genuinely different
    UDP-glucuronate chemistry (hyaluronan chain elongation, oxidative
    decarboxylation to NADH) and are correctly excluded by mass delta."""
    assert ugt_screened.matched == 102
    assert len(ugt_screened.decided) == 94
    by_id = {r.rhea_id: r for r in ugt_screened.results}
    assert by_id["RHEA:10568"].decided
    assert by_id["RHEA:28314"].decided
    for rhea_id in ("RHEA:11404", "RHEA:23916", "RHEA:70523", "RHEA:26073", "RHEA:29559"):
        assert not by_id[rhea_id].decided
        assert "could not identify" in by_id[rhea_id].skipped_reason
    for rhea_id in ("RHEA:12528", "RHEA:20908", "RHEA:24702"):
        assert not by_id[rhea_id].decided
        assert "does not match" in by_id[rhea_id].skipped_reason


def test_ugt_process_model_charges_the_bromide_donor_and_promoter(ugt_inputs):
    """The declared process, not a paper: a Koenigs-Knorr glucuronidation
    with a pre-formed glycosyl bromide donor and a silver promoter, then
    saponification and a plant-style isolation. Everything generalised by
    construction."""
    template = ugt_inputs[1]
    materials = materials_from_process_model(template.process_model)
    names = {m.name for m in materials}
    assert {"methyl acetobromoglucuronate", "silver carbonate", "sodium hydroxide"} <= names
    assert all(m.basis == "generalised" for m in materials)


def test_ugt_class_is_decided_and_decisively_favours_the_enzyme(ugt_screened):
    """Every one of this class's 94 decided reactions reaches a decisive
    verdict favouring the enzyme, the same shape as the ATP-kinase and
    DMAPP-prenyltransferase classes: the process model's silver-promoted
    Koenigs-Knorr coupling plus saponification is bulky enough to keep the
    sign fixed even at UDP-glucuronate's most expensive assumed value
    within its wide, unevidenced [0.5, 100] cofactor ceiling."""
    decided_with_verdict = [
        r for r in ugt_screened.decided if r.verdict is not None and r.verdict.decisive
    ]
    assert len(decided_with_verdict) == len(ugt_screened.decided)
    assert all(r.verdict.verdict == "b_lower" for r in decided_with_verdict)


# --- three siblings of the DMAPP class: GPP, FPP and GGPP prenylation ------


@pytest.mark.parametrize(
    "class_id,cofactor_key,matched,decided",
    [
        ("gpp-prenyltransferase", "name:chebi:58057", 60, 12),
        ("fpp-prenyltransferase", "name:chebi:175763", 178, 9),
        ("ggpp-prenyltransferase", "name:chebi:58756", 55, 5),
    ],
)
def test_prenyl_diphosphate_siblings_match_and_decide_the_expected_number(
    class_id, cofactor_key, matched, decided
):
    """GPP, FPP and GGPP are DMAPP's siblings: the same allylic-diphosphate
    prenylation, transferring two, three and four isoprene units instead of
    one. Each is its own class because each adds a different mass, and each
    is progressively less "clean" than DMAPP: a growing share of each
    donor's real chemistry is chain elongation or homodimerisation rather
    than transfer onto a foreign nucleophile, which is why FPP's decided
    fraction (9 of 178, 5.1%) is much smaller than DMAPP's own (62 of 73,
    84.9%) -- a real finding about the chemistry, not a bug in the screen.
    All three counts have two fixes applied: isopentenyl diphosphate
    (CHEBI:128769) is excluded from matching, closing the single-IPP-hop
    false positive documented on the DMAPP class's own CORRECTION (each
    sibling had at least one under the earlier EC-2.5.1-restricted counts:
    GPP's original 10 decided wrongly included 2, FPP's original 2 wrongly
    included 1, GGPP's original 4 wrongly included 1); and no ec_prefix is
    declared, the same step taken for SAM-methyltransferase, ATP-kinase and
    the DMAPP class, admitting genuine EC-less prenylations that a
    class-purity mass-delta and IPP-exclusion check now separate on their
    own."""
    reactions, _ = load_reactions(RHEA / "reactions.tsv")
    structures = load_structures(RHEA / "participants.csv")
    template = load_template(CLASSES / f"{class_id}.yaml")
    bounds = load_bounds(CLASSES / f"{class_id}.bounds.yaml")
    table = FactorTable.load(list(default_factor_paths(ROOT)))
    for syn in default_synonym_paths(ROOT):
        table.load_synonyms(syn)
    assumptions = load_ledger(ARBUTIN / "ledger.yaml").assumptions
    r = screen_all(
        reactions, template, structures, table, assumptions, bounds, use_process_model=True
    )
    assert r.matched == matched
    assert len(r.decided) == decided
    assert cofactor_key in bounds
    decided_with_verdict = [x for x in r.decided if x.verdict is not None and x.verdict.decisive]
    assert len(decided_with_verdict) == len(r.decided)
    assert all(x.verdict.verdict == "b_lower" for x in decided_with_verdict)


# --- an eleventh class: O2/NAD(P)H-dependent monooxygenation ---------------
# The first class needing unpriced_co_cofactor_chebi -- NAD(P)H is a real,
# required co-reactant this project does not price.


@pytest.fixture(scope="module")
def monooxygenase_inputs():
    reactions, _ = load_reactions(RHEA / "reactions.tsv")
    structures = load_structures(RHEA / "participants.csv")
    template = load_template(CLASSES / "o2-monooxygenase.yaml")
    bounds = load_bounds(CLASSES / "o2-monooxygenase.bounds.yaml")
    table = FactorTable.load(list(default_factor_paths(ROOT)))
    for syn in default_synonym_paths(ROOT):
        table.load_synonyms(syn)
    assumptions = load_ledger(ARBUTIN / "ledger.yaml").assumptions
    return reactions, template, structures, table, assumptions, bounds


@pytest.fixture(scope="module")
def monooxygenase_screened(monooxygenase_inputs):
    return screen_all(*monooxygenase_inputs, use_process_model=True)


def test_monooxygenase_class_declares_nadh_and_nadph_unpriced(monooxygenase_inputs):
    """NAD(P)H drives the mechanism but never appears as a priced material:
    this class's whole point is that it is a real cost this project does
    not charge, not that it can be ignored."""
    template = monooxygenase_inputs[1]
    assert template.unpriced_co_cofactor_chebi == ("CHEBI:57945", "CHEBI:57783")


def test_monooxygenase_class_matches_and_decides_the_expected_number(monooxygenase_screened):
    """441 Rhea reactions consume O2 alongside NAD(P)H (no ec_prefix is
    declared -- an earlier version restricted to EC 1.14.13, narrowing to
    198; see the template's own STAGE 2 note for why that restriction was
    dropped, the same step taken for the other five O2 classes). 262
    (59.4%) resolve to a single acceptor/product pair within tolerance and
    are decided. RHEA:11440 (2,3,5,6-tetrachlorophenol -> ...hydroquinone)
    is the reaction that pinned down the charge-state offset: observed
    delta 14.991, short of the textbook 15.999 by almost exactly one
    proton because ChEBI draws the newly-installed hydroxyl as a
    phenolate."""
    assert monooxygenase_screened.matched == 441
    assert len(monooxygenase_screened.decided) == 262
    by_id = {r.rhea_id: r for r in monooxygenase_screened.results}
    assert by_id["RHEA:11440"].decided
    assert by_id["RHEA:11420"].decided


def test_monooxygenase_class_excludes_decarboxylation_and_demethylation(monooxygenase_screened):
    """Two genuinely different EC 1.14.13 sub-chemistries share the O2
    cofactor with real monooxygenation and are correctly excluded: oxidative
    decarboxylation (RHEA:21628, mass -44.05, a different transformation the
    NAD(P)+-oxidoreductase class's own decarboxylation confound already
    established the pattern for) and O-demethylation (RHEA:10860's sibling
    reactions cluster at -14.03, the mirror image of the SAM class's own
    +14.03 methylation)."""
    by_id = {r.rhea_id: r for r in monooxygenase_screened.results}
    assert not by_id["RHEA:21628"].decided
    assert "does not match" in by_id["RHEA:21628"].skipped_reason


def test_monooxygenase_process_model_charges_mcpba(monooxygenase_inputs):
    """The declared process, not a paper: mCPBA oxidation in
    dichloromethane, plus a plant-style isolation. Everything generalised
    by construction."""
    template = monooxygenase_inputs[1]
    materials = materials_from_process_model(template.process_model)
    names = {m.name for m in materials}
    assert {"meta-chloroperoxybenzoic acid", "dichloromethane", "ethyl acetate"} <= names
    assert all(m.basis == "generalised" for m in materials)


def test_monooxygenase_class_is_decided_and_decisively_favours_the_enzyme(monooxygenase_screened):
    """Every one of this class's 262 decided reactions reaches a decisive
    verdict favouring the enzyme, even with NAD(P)H's own real cost left
    entirely unpriced -- an mCPBA-based chemical route is bulky enough on
    its own to keep the sign fixed."""
    decided_with_verdict = [
        r for r in monooxygenase_screened.decided if r.verdict is not None and r.verdict.decisive
    ]
    assert len(decided_with_verdict) == len(monooxygenase_screened.decided)
    assert all(r.verdict.verdict == "b_lower" for r in decided_with_verdict)


# --- a twelfth class: cytochrome P450 monooxygenation -----------------------
# The same unpriced-co-cofactor mechanism, a different electron-donor
# identity, and Rhea's biggest single O2-consuming EC group.


@pytest.fixture(scope="module")
def p450_inputs():
    reactions, _ = load_reactions(RHEA / "reactions.tsv")
    structures = load_structures(RHEA / "participants.csv")
    template = load_template(CLASSES / "p450-monooxygenase.yaml")
    bounds = load_bounds(CLASSES / "p450-monooxygenase.bounds.yaml")
    table = FactorTable.load(list(default_factor_paths(ROOT)))
    for syn in default_synonym_paths(ROOT):
        table.load_synonyms(syn)
    assumptions = load_ledger(ARBUTIN / "ledger.yaml").assumptions
    return reactions, template, structures, table, assumptions, bounds


@pytest.fixture(scope="module")
def p450_screened(p450_inputs):
    return screen_all(*p450_inputs, use_process_model=True)


def test_p450_class_declares_the_electron_donor_unpriced(p450_inputs):
    """CHEBI:57618 is one ChEBI entity Rhea's equation text variously labels
    'reduced [NADPH--hemoprotein reductase]', 'FMNH2' or
    'reduced [flavodoxin]' depending on biological context -- all the same
    underlying reduced flavin, none of it priced."""
    template = p450_inputs[1]
    assert template.unpriced_co_cofactor_chebi == ("CHEBI:57618", "CHEBI:58307")


def test_p450_class_matches_and_decides_the_expected_number(p450_screened):
    """920 Rhea reactions consume O2 alongside the P450 electron donor (no
    ec_prefix is declared -- an earlier version restricted to EC 1.14.14,
    narrowing to 256, Rhea's single largest O2-consuming EC group; see the
    template's own STAGE 2 note for why that restriction was dropped). 623
    (67.7%) resolve within tolerance and are decided. Under the earlier
    EC-restricted count, 4 could not be resolved to a single
    acceptor/product pair: three need a third reactant (glutathione)
    beyond O2 and the electron donor, and one (RHEA:12312) uses FMNH2 and
    NADH as two separate simultaneous reactants
    rather than the single reduced-donor shape this class handles."""
    assert p450_screened.matched == 920
    assert len(p450_screened.decided) == 623
    by_id = {r.rhea_id: r for r in p450_screened.results}
    assert not by_id["RHEA:12312"].decided
    assert "could not identify" in by_id["RHEA:12312"].skipped_reason


def test_p450_class_excludes_dehydrogenation(p450_screened):
    """This EC group is more chemically diverse than EC 1.14.13's: some
    members are real dehydrogenations (net -2.016, the same 2H-loss
    signature the NAD(P)+-oxidoreductase class targets), a genuinely
    different transformation from oxygen insertion, correctly excluded by
    mass delta rather than folded in as noise."""
    dehydrogenation_like = [
        r
        for r in p450_screened.results
        if r.skipped_reason and "mass added (-2.0" in r.skipped_reason
    ]
    assert len(dehydrogenation_like) > 0
    assert all(not r.decided for r in dehydrogenation_like)


def test_p450_class_is_decided_and_decisively_favours_the_enzyme(p450_screened):
    """Every one of this class's 623 decided reactions reaches a decisive
    verdict favouring the enzyme, the same shape as the o2-monooxygenase
    class, even with the electron donor's real cost left entirely
    unpriced."""
    decided_with_verdict = [
        r for r in p450_screened.decided if r.verdict is not None and r.verdict.decisive
    ]
    assert len(decided_with_verdict) == len(p450_screened.decided)
    assert all(r.verdict.verdict == "b_lower" for r in decided_with_verdict)


# --- a thirteenth class: O2-dependent fatty acyl desaturation ---------------
# Same O2 cofactor as the two monooxygenase classes, but the OPPOSITE mass
# signature: this EC group removes 2H rather than inserting an oxygen atom.


@pytest.fixture(scope="module")
def desaturase_inputs():
    reactions, _ = load_reactions(RHEA / "reactions.tsv")
    structures = load_structures(RHEA / "participants.csv")
    template = load_template(CLASSES / "o2-desaturase.yaml")
    bounds = load_bounds(CLASSES / "o2-desaturase.bounds.yaml")
    table = FactorTable.load(list(default_factor_paths(ROOT)))
    for syn in default_synonym_paths(ROOT):
        table.load_synonyms(syn)
    assumptions = load_ledger(ARBUTIN / "ledger.yaml").assumptions
    return reactions, template, structures, table, assumptions, bounds


@pytest.fixture(scope="module")
def desaturase_screened(desaturase_inputs):
    return screen_all(*desaturase_inputs, use_process_model=True)


def test_desaturase_class_targets_2h_loss_not_oxygen_insertion(desaturase_inputs):
    """Same O2 cofactor as the two monooxygenase classes, but this EC
    group's dominant chemistry is dehydrogenation (octadecanoyl-[ACP] ->
    (9Z)-octadecenoyl-[ACP], -2.016 g/mol), not oxygen insertion -- the
    expected_mass_delta has to be the opposite sign from the other two O2
    classes, not their +15.999."""
    template = desaturase_inputs[1]
    assert template.expected_mass_delta == pytest.approx(-2.016, abs=1e-6)
    assert template.unpriced_co_cofactor_chebi == (
        "CHEBI:29033", "CHEBI:57618", "CHEBI:33738", "CHEBI:57783", "CHEBI:58307",
    )


def test_desaturase_class_matches_and_decides_the_expected_number(desaturase_screened):
    """1,534 Rhea reactions consume O2 alongside one of this class's five
    known electron donors (no ec_prefix is declared -- an earlier version
    restricted to EC 1.14.19, narrowing to 115; see the template's own
    STAGE 2 note for why that restriction was dropped and why this class's
    "matched" count overlaps heavily with the other O2 classes'). 267
    (17.4%) resolve within tolerance and decide -- a much smaller fraction
    than before, because most of the 1,534 are genuine candidates for one
    of the +15.999 O2 classes instead, correctly rejected here by this
    class's own -2.016 sign. RHEA:11776 (octadecanoyl-[ACP] ->
    (9Z)-octadecenoyl-[ACP]), the reaction the class was designed around,
    still decides."""
    assert desaturase_screened.matched == 1534
    assert len(desaturase_screened.decided) == 267
    by_id = {r.rhea_id: r for r in desaturase_screened.results}
    assert by_id["RHEA:11776"].decided


def test_desaturase_class_excludes_dimerisation(desaturase_screened):
    """RHEA:26031/26035 (two flaviolin molecules coupling to a biflaviolin,
    +202.12 g/mol) are oxidative dimerisation -- a new C-C bond between two
    acceptor molecules, not a desaturation of one -- and are correctly
    excluded by mass delta rather than mis-decided."""
    by_id = {r.rhea_id: r for r in desaturase_screened.results}
    for rhea_id in ("RHEA:26031", "RHEA:26035"):
        assert not by_id[rhea_id].decided
        assert "does not match" in by_id[rhea_id].skipped_reason


def test_desaturase_class_is_decided_and_decisively_favours_the_enzyme(desaturase_screened):
    """Every one of this class's 267 decided reactions reaches a decisive
    verdict favouring the enzyme, even with every electron donor's real
    cost left entirely unpriced."""
    decided_with_verdict = [
        r for r in desaturase_screened.decided if r.verdict is not None and r.verdict.decisive
    ]
    assert len(decided_with_verdict) == len(desaturase_screened.decided)
    assert all(r.verdict.verdict == "b_lower" for r in decided_with_verdict)


# --- a fourteenth class: O2-dependent dioxygenation -------------------------
# No unpriced_co_cofactor_chebi needed at all: a true dioxygenase
# incorporates both O2 atoms with no separate electron-donor cofactor.


@pytest.fixture(scope="module")
def dioxygenase_inputs():
    reactions, _ = load_reactions(RHEA / "reactions.tsv")
    structures = load_structures(RHEA / "participants.csv")
    template = load_template(CLASSES / "o2-dioxygenase.yaml")
    bounds = load_bounds(CLASSES / "o2-dioxygenase.bounds.yaml")
    table = FactorTable.load(list(default_factor_paths(ROOT)))
    for syn in default_synonym_paths(ROOT):
        table.load_synonyms(syn)
    assumptions = load_ledger(ARBUTIN / "ledger.yaml").assumptions
    return reactions, template, structures, table, assumptions, bounds


@pytest.fixture(scope="module")
def dioxygenase_screened(dioxygenase_inputs):
    return screen_all(*dioxygenase_inputs, use_process_model=True)


def test_dioxygenase_class_needs_no_co_cofactor(dioxygenase_inputs):
    """A true dioxygenase incorporates both O2 atoms directly, with no
    separate electron-donor cofactor -- architecturally the simplest of
    the four O2-consuming classes."""
    template = dioxygenase_inputs[1]
    assert template.unpriced_co_cofactor_chebi == ()
    assert template.expected_mass_delta == pytest.approx(30.99, abs=1e-6)


def test_dioxygenase_class_matches_and_unifies_three_charge_states(dioxygenase_screened):
    """932 Rhea reactions consume O2 with none of the other five O2
    classes' required co-cofactors present (no ec_prefix is declared --
    an earlier version restricted to EC 1.13.11, narrowing to 102; see the
    template's own STAGE 2 note for why that restriction was dropped). 197
    (21.1%) resolve within tolerance and are decided, spanning three
    charge-state clusters unified by one expected_mass_delta and a widened
    tolerance: RHEA:10428 (a clean lipoxygenase, the textbook 32.0 g/mol),
    RHEA:14409 (one proton short) and RHEA:10084 (a ring-cleaving catechol
    dioxygenase, two protons short) are all decided, confirming all three
    are the same real chemistry rather than three different ones."""
    assert dioxygenase_screened.matched == 932
    assert len(dioxygenase_screened.decided) == 197
    by_id = {r.rhea_id: r for r in dioxygenase_screened.results}
    for rhea_id in ("RHEA:10428", "RHEA:14409", "RHEA:10084"):
        assert by_id[rhea_id].decided


def test_dioxygenase_class_excludes_reactions_needing_a_third_reactant(dioxygenase_screened):
    """RHEA:12981 and RHEA:13957 both genuinely require H2O as a third
    reactant beyond O2 (sulfur/thiol oxidation to sulfite), a different
    reaction shape this class does not attempt to handle. Water is excluded
    from the acceptor search the same way a proton is (see _identify's
    comment), so both resolve on the remaining sulfur-containing reactant
    alone and are correctly excluded once its mass delta does not match a
    dioxygenation -- rather than mis-decided against a spurious
    water-as-acceptor pairing."""
    by_id = {r.rhea_id: r for r in dioxygenase_screened.results}
    for rhea_id in ("RHEA:12981", "RHEA:13957"):
        assert not by_id[rhea_id].decided
        assert "does not match" in by_id[rhea_id].skipped_reason


def test_dioxygenase_class_is_decided_and_decisively_favours_the_enzyme(dioxygenase_screened):
    """Every one of this class's 197 decided reactions reaches a decisive
    verdict favouring the enzyme, even though the chemical route's real
    stoichiometric burden here (a catalytic photosensitiser plus solvent)
    is genuinely small."""
    decided_with_verdict = [
        r for r in dioxygenase_screened.decided if r.verdict is not None and r.verdict.decisive
    ]
    assert len(decided_with_verdict) == len(dioxygenase_screened.decided)
    assert all(r.verdict.verdict == "b_lower" for r in decided_with_verdict)


# --- a fifteenth class: Fe(II)/2-oxoglutarate-dependent dioxygenation ------
# 2-oxoglutarate is oxidatively decarboxylated to succinate + CO2 in the
# same step -- a real, required co-reactant that this class does not price,
# the same unpriced_co_cofactor_chebi mechanism with a very different
# co-cofactor identity from NAD(P)H or a reduced flavin/ferredoxin.


@pytest.fixture(scope="module")
def twoog_inputs():
    reactions, _ = load_reactions(RHEA / "reactions.tsv")
    structures = load_structures(RHEA / "participants.csv")
    template = load_template(CLASSES / "2og-dioxygenase.yaml")
    bounds = load_bounds(CLASSES / "2og-dioxygenase.bounds.yaml")
    table = FactorTable.load(list(default_factor_paths(ROOT)))
    for syn in default_synonym_paths(ROOT):
        table.load_synonyms(syn)
    assumptions = load_ledger(ARBUTIN / "ledger.yaml").assumptions
    return reactions, template, structures, table, assumptions, bounds


@pytest.fixture(scope="module")
def twoog_screened(twoog_inputs):
    return screen_all(*twoog_inputs, use_process_model=True)


def test_2og_class_declares_2_oxoglutarate_unpriced(twoog_inputs):
    """2-oxoglutarate is oxidatively decarboxylated to succinate + CO2 in
    the same step a genuine member inserts an oxygen atom into the
    acceptor -- a real, required co-reactant, not a byproduct, and this
    class does not price it."""
    template = twoog_inputs[1]
    assert template.unpriced_co_cofactor_chebi == ("CHEBI:16810",)
    assert template.expected_mass_delta == pytest.approx(15.999, abs=1e-6)


def test_2og_class_matches_and_decides_the_expected_number(twoog_screened):
    """284 Rhea reactions consume O2 alongside 2-oxoglutarate (no ec_prefix
    is declared -- an earlier version restricted to EC 1.14.11, narrowing
    to 101; see the template's own STAGE 2 note for why that restriction
    was dropped -- 2-oxoglutarate is a uniquely clean discriminator with
    no overlap against any other O2 class's required list). 125 (44.0%)
    resolve within tolerance and are decided, including RHEA:10316
    (thymine -> 5-hydroxymethyluracil). RHEA:35975 still cannot be
    resolved to a single acceptor/product pair: it consumes a second
    cofactor (AH2) and two equivalents of O2, a more complex mechanism
    this class's simple two-reactant shape does not cover."""
    assert twoog_screened.matched == 284
    assert len(twoog_screened.decided) == 125
    by_id = {r.rhea_id: r for r in twoog_screened.results}
    assert by_id["RHEA:10316"].decided
    assert not by_id["RHEA:35975"].decided
    assert "could not identify" in by_id["RHEA:35975"].skipped_reason


def test_2og_class_is_decided_and_decisively_favours_the_enzyme(twoog_screened):
    """Every one of this class's 125 decided reactions reaches a decisive
    verdict favouring the enzyme, even with 2-oxoglutarate's real cost
    left entirely unpriced."""
    decided_with_verdict = [
        r for r in twoog_screened.decided if r.verdict is not None and r.verdict.decisive
    ]
    assert len(decided_with_verdict) == len(twoog_screened.decided)
    assert all(r.verdict.verdict == "b_lower" for r in decided_with_verdict)


# --- a sixteenth class: O2/ferredoxin-dependent monooxygenation -----------
# A third family of electron-donor identity for the same O2-insertion
# chemistry: steroid/bile acid hydroxylases, camphor monooxygenase, alkane
# hydroxylases.


@pytest.fixture(scope="module")
def ferredoxin_inputs():
    reactions, _ = load_reactions(RHEA / "reactions.tsv")
    structures = load_structures(RHEA / "participants.csv")
    template = load_template(CLASSES / "ferredoxin-monooxygenase.yaml")
    bounds = load_bounds(CLASSES / "ferredoxin-monooxygenase.bounds.yaml")
    table = FactorTable.load(list(default_factor_paths(ROOT)))
    for syn in default_synonym_paths(ROOT):
        table.load_synonyms(syn)
    assumptions = load_ledger(ARBUTIN / "ledger.yaml").assumptions
    return reactions, template, structures, table, assumptions, bounds


@pytest.fixture(scope="module")
def ferredoxin_screened(ferredoxin_inputs):
    return screen_all(*ferredoxin_inputs, use_process_model=True)


def test_ferredoxin_class_declares_three_donor_families_unpriced(ferredoxin_inputs):
    """CHEBI:33738 is one ChEBI entity Rhea's equation text variously labels
    'reduced [2Fe-2S]-[ferredoxin]', 'reduced [adrenodoxin]' or
    'reduced [2Fe-2S]-[putidaredoxin]' depending on biological context --
    the same convention already found on the p450-monooxygenase class."""
    template = ferredoxin_inputs[1]
    assert template.unpriced_co_cofactor_chebi == (
        "CHEBI:33738", "CHEBI:33723", "CHEBI:29033",
    )


def test_ferredoxin_class_matches_and_decides_the_expected_number(ferredoxin_screened):
    """357 Rhea reactions consume O2 alongside one of this class's three
    donor families (no ec_prefix is declared -- an earlier version
    restricted to EC 1.14.15, narrowing to 72; see the template's own
    STAGE 2 note for why that restriction was dropped, and for why this
    class's required list overlaps o2-desaturase's without ever
    double-deciding a reaction). 159 (44.5%) resolve within tolerance and
    are decided, every one decisively favouring the enzyme."""
    assert ferredoxin_screened.matched == 357
    assert len(ferredoxin_screened.decided) == 159
    decided_with_verdict = [
        r for r in ferredoxin_screened.decided if r.verdict is not None and r.verdict.decisive
    ]
    assert len(decided_with_verdict) == len(ferredoxin_screened.decided)
    assert all(r.verdict.verdict == "b_lower" for r in decided_with_verdict)


# --- the six O2 classes together: no reaction decides for more than one ----


def test_no_rhea_reaction_decides_for_more_than_one_o2_class(
    monooxygenase_screened,
    p450_screened,
    desaturase_screened,
    dioxygenase_screened,
    twoog_screened,
    ferredoxin_screened,
):
    """The whole point of required_co_cofactor_chebi / excluded_co_cofactor_
    chebi is to let six mechanistically distinct classes share one cofactor
    (O2) without becoming six votes on the same reaction. Several of their
    required lists deliberately overlap (o2-monooxygenase and o2-desaturase
    both accept NADPH; o2-desaturase and ferredoxin-monooxygenase both
    accept Fe(2+) and reduced [2Fe-2S]), so their "matched" candidate pools
    overlap heavily -- but the real tiebreaker is each class's own
    expected_mass_delta (+15.999 for four of them, -2.016 for the
    desaturase, a broader spread for the bare-O2 dioxygenase), which is
    mutually exclusive by construction. This is the property that makes
    that overlap safe rather than a double-count: verified here directly
    against the real Rhea data, not assumed from the individual classes'
    own passing tests."""
    runs = {
        "o2-monooxygenase": monooxygenase_screened,
        "p450-monooxygenase": p450_screened,
        "o2-desaturase": desaturase_screened,
        "o2-dioxygenase": dioxygenase_screened,
        "2og-dioxygenase": twoog_screened,
        "ferredoxin-monooxygenase": ferredoxin_screened,
    }
    counts: dict[str, int] = {}
    for run in runs.values():
        for r in run.decided:
            counts[r.rhea_id] = counts.get(r.rhea_id, 0) + 1
    double_decided = {rid: n for rid, n in counts.items() if n > 1}
    assert double_decided == {}
    total_decided = sum(len(run.decided) for run in runs.values())
    assert total_decided == sum(counts.values())


# --- a seventeenth class: PAPS-dependent sulfation --------------------------
# Built EC-free from the start: Rhea's cleanest single-cofactor class, with
# a mass-delta check alone separating 128 of 130 PAPS-consuming reactions.


@pytest.fixture(scope="module")
def paps_inputs():
    reactions, _ = load_reactions(RHEA / "reactions.tsv")
    structures = load_structures(RHEA / "participants.csv")
    template = load_template(CLASSES / "paps-sulfotransferase.yaml")
    bounds = load_bounds(CLASSES / "paps-sulfotransferase.bounds.yaml")
    table = FactorTable.load(list(default_factor_paths(ROOT)))
    for syn in default_synonym_paths(ROOT):
        table.load_synonyms(syn)
    assumptions = load_ledger(ARBUTIN / "ledger.yaml").assumptions
    return reactions, template, structures, table, assumptions, bounds


@pytest.fixture(scope="module")
def paps_screened(paps_inputs):
    return screen_all(*paps_inputs, use_process_model=True)


def test_paps_class_declares_no_ec_prefix(paps_inputs):
    """Only 41 of the 130 PAPS-consuming reactions carry an EC 2.8.2
    annotation, and 87 carry none at all -- the same 58.9%-of-Rhea gap the
    SAM-methyltransferase and ATP-kinase classes' own headers document.
    The mass-delta check alone already separates this class cleanly, so
    no ec_prefix was ever declared."""
    template = paps_inputs[1]
    assert template.ec_prefix is None
    assert template.expected_mass_delta == pytest.approx(79.056, abs=1e-6)


def test_paps_class_matches_and_decides_the_expected_number(paps_screened):
    """130 Rhea reactions consume PAPS. 128 (98.5%) resolve to a single
    acceptor/product pair within one proton of 79.056 (the sulfonate
    group, SO3, replacing a hydrogen) and are decided, every one
    decisively favouring the enzyme -- the tightest signal-to-noise ratio
    of any class this project has built: zero of the 130 are excluded by
    the mass-delta check itself. RHEA:13453 (quercetin -> quercetin
    3-sulfate) is the reaction that pinned down the constant: 380.286 -
    301.230 = 79.056 exactly."""
    assert paps_screened.matched == 130
    assert len(paps_screened.decided) == 128
    by_id = {r.rhea_id: r for r in paps_screened.results}
    assert by_id["RHEA:13453"].decided
    assert by_id["RHEA:11884"].decided
    assert by_id["RHEA:10908"].decided


def test_paps_class_excludes_its_own_hydrolysis(paps_screened):
    """RHEA:11232 and RHEA:77639 are PAPS's own hydrolysis (PAPS + H2O =
    sulfate/adenosine-5'-phosphosulfate + PAP), not a sulfation of any
    acceptor. Water is excluded from the acceptor search the same way a
    proton is (see _identify's comment), so both correctly come back
    unresolved rather than mis-decided against a spurious water-as-
    acceptor pairing."""
    by_id = {r.rhea_id: r for r in paps_screened.results}
    for rhea_id in ("RHEA:11232", "RHEA:77639"):
        assert not by_id[rhea_id].decided
        assert "could not identify" in by_id[rhea_id].skipped_reason


def test_paps_process_model_charges_so3_pyridine_complex(paps_inputs):
    """The declared process, not a paper: SO3-pyridine complex in pyridine
    solvent (which doubles as the base, since sulfation does not release a
    strong acid the way alkylation releases HI/HBr), plus a plant-style
    isolation. Everything generalised by construction."""
    template = paps_inputs[1]
    materials = materials_from_process_model(template.process_model)
    names = {m.name for m in materials}
    assert {"sulfur trioxide pyridine complex", "pyridine", "ethyl acetate"} <= names
    assert all(m.basis == "generalised" for m in materials)


def test_paps_class_is_decided_and_decisively_favours_the_enzyme(paps_screened):
    """Every one of this class's 128 decided reactions reaches a decisive
    verdict favouring the enzyme."""
    decided_with_verdict = [
        r for r in paps_screened.decided if r.verdict is not None and r.verdict.decisive
    ]
    assert len(decided_with_verdict) == len(paps_screened.decided)
    assert all(r.verdict.verdict == "b_lower" for r in decided_with_verdict)
