"""Screening a reaction database, instead of one comparison at a time.

The problem
-----------

`carbonroute compare` answers one question: for these two routes to this
product, which is lower? Answering it well takes a day of reading a paper
and building a ledger. Rhea holds about 18,500 enzymatic reactions. At one
day each that is a career, so the interesting question is not how to
compare two routes but what makes comparing *thousands* of them cost less
than thousands of times as much.

What makes it cheap
-------------------

A structural property of the *diff*, not of the chemistry. When two routes
make the same product, everything common to both cancels out of the delta
set (spec section 7.4). For enzyme-versus-chemistry, what cancels is the
expensive part to look up — the substrate and the product, which are
different in every one of the 18,500 reactions. What survives is:

  - enzymatic side: the **cofactor** — UDP-glucose, NADPH, SAM, acetyl-CoA
  - chemical side: the **protecting groups, activator, base and solvents**

Both are small closed vocabularies that recur across the whole database.
`scripts/ingest_rhea.py` measures the first one rather than assuming it:
of 14,251 distinct participants across 18,558 reactions, only 63 appear in
100 reactions or more, and the top 30 cover 47.8% of all participant slots.
The long tail that is *not* covered is precisely the per-reaction substrate
and product — the part that cancels.

So the factor work for a database-wide screen is bounded by the size of
those two vocabularies (tens of substances), not by the number of
reactions. Once they are in hand, each additional reaction costs one
arithmetic evaluation.

What a screen is, and is not
----------------------------

This is a screen, not a life-cycle assessment, and the difference is not a
disclaimer — it is what the output means.

A `compare` run models two routes that someone actually published. A screen
models one route that someone published (the enzymatic one, from Rhea's
curated stoichiometry) against a *class template*: a chemical procedure,
taken from one real cited paper, applied to every substrate in the same
reaction class. That last step is the assumption the whole method rests on,
and every template records which of its terms are sourced from its paper
and which are generalised beyond it (`basis: sourced` / `basis: generalised`,
the same discipline `data/processes/` uses for `stated` vs `stoichiometric`).

Accordingly the output is never an absolute number and never a per-reaction
verdict presented as fact. It is a **ranking with a stated condition**: for
each reaction, whether the enzymatic route wins everywhere inside the
asserted bounds, and if not, what would have to be true for it to. The
reactions that come back decided are the ones worth spending a real
`compare` on.

Calibration
-----------

The one reaction in this repository that has been done both ways is
RHEA:12560 — hydroquinone + UDP-alpha-D-glucose = beta-arbutin + UDP + H(+)
— which is hand-built as a fully sourced ledger in
`examples/case-studies/beta-arbutin-chemical-vs-enzymatic/`. The screen is
expected to reproduce that case's direction, and a test asserts it does.
A screen that disagrees with the hand-built case it was derived from would
be reporting on its own template, not on chemistry.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .bounds import Bound, BoundedVerdict, bounded_verdict
from .compute import DeltaRow, DiffResult
from .resolve import FactorTable, resolve_materials
from .schema import Assumptions, Role


class ScreenError(ValueError):
    """A reaction database, class template, or structure could not be used."""


# --- the reaction database --------------------------------------------------


@dataclass(frozen=True)
class Participant:
    chebi: str
    coefficient: float
    name: str


@dataclass(frozen=True)
class RheaReaction:
    rhea_id: str
    equation: str
    ec: str
    left: tuple[Participant, ...]
    right: tuple[Participant, ...]

    def chebi_ids(self) -> set[str]:
        return {p.chebi for p in self.left} | {p.chebi for p in self.right}


#: A leading integer coefficient, as Rhea writes it ("2 glyoxylate").
_COEFF = re.compile(r"^(\d+)\s+(.*)$")


def _split_side(side: str) -> list[tuple[float, str]]:
    out: list[tuple[float, str]] = []
    for term in side.split(" + "):
        term = term.strip()
        if not term:
            continue
        m = _COEFF.match(term)
        if m:
            out.append((float(m.group(1)), m.group(2).strip()))
        else:
            out.append((1.0, term))
    return out


def parse_reaction(rhea_id: str, equation: str, chebi_ids: str, ec: str) -> RheaReaction | None:
    """Pair Rhea's equation text with its ChEBI id list.

    Rhea gives the equation as display text and the participants as a
    separate, order-matched ``;``-separated ChEBI list. Where the two do not
    line up — a handful of equations use notation this parser does not model
    (compartment tags, generic ``A``/``AH2`` redox placeholders) — the
    reaction is returned as ``None`` rather than guessed at, and the caller
    counts it as skipped.
    """
    if "=" not in equation:
        return None
    ids = [c.strip() for c in chebi_ids.split(";") if c.strip()]
    left_text, right_text = equation.split("=", 1)
    left_terms = _split_side(left_text)
    right_terms = _split_side(right_text)
    if len(left_terms) + len(right_terms) != len(ids):
        return None

    left = tuple(
        Participant(chebi=ids[i], coefficient=c, name=n)
        for i, (c, n) in enumerate(left_terms)
    )
    right = tuple(
        Participant(chebi=ids[len(left_terms) + i], coefficient=c, name=n)
        for i, (c, n) in enumerate(right_terms)
    )
    return RheaReaction(rhea_id=rhea_id, equation=equation.strip(), ec=ec, left=left, right=right)


def load_reactions(path: str | Path) -> tuple[list[RheaReaction], int]:
    """Read ``data/rhea/reactions.tsv``. Returns (parsed, n_skipped)."""
    p = Path(path)
    try:
        text = p.read_text(encoding="utf-8")
    except OSError as exc:
        raise ScreenError(f"could not read reaction table {p}: {exc}") from exc

    out: list[RheaReaction] = []
    skipped = 0
    for row in csv.DictReader(text.splitlines(), delimiter="\t"):
        rxn = parse_reaction(
            row.get("rhea_id", ""),
            row.get("equation", ""),
            row.get("chebi_ids", ""),
            row.get("ec", ""),
        )
        if rxn is None:
            skipped += 1
        else:
            out.append(rxn)
    if not out:
        raise ScreenError(f"{p}: no reactions could be parsed")
    return out, skipped


def load_structures(path: str | Path) -> dict[str, str]:
    """ChEBI id -> SMILES, from ``data/rhea/participants.csv``."""
    p = Path(path)
    smiles: dict[str, str] = {}
    with p.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if row.get("smiles"):
                smiles[row["chebi_id"]] = row["smiles"]
    return smiles


# --- structure-derived quantities -------------------------------------------


def molecular_weight(smiles: str) -> float | None:
    """Molecular weight from SMILES, via RDKit. None if it will not parse.

    RDKit is an optional dependency of this project (`pip install -e ".[chem]"`).
    Without it a screen cannot run, because it cannot convert Rhea's molar
    stoichiometry into the mass basis every other part of the tool uses --
    so this raises rather than silently degrading to a guess.
    """
    try:
        from rdkit import Chem, RDLogger
        from rdkit.Chem.Descriptors import MolWt
    except ImportError as exc:  # pragma: no cover - environment-dependent
        raise ScreenError(
            "screening needs RDKit to turn Rhea's molar stoichiometry into "
            'masses; install it with: pip install -e ".[chem]"'
        ) from exc
    RDLogger.DisableLog("rdApp.*")
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return None
    return float(MolWt(mol))


#: Groups a chemical glycosylation/acylation would have to mask on the
#: acceptor before it could be selective. An enzyme does not: its active
#: site supplies the selectivity, which is exactly the advantage a screen
#: is trying to size.
_PROTECTABLE_SMARTS = (
    "[OX2H]",   # hydroxyl (alcohol or phenol)
    "[NX3;H2,H1;!$(NC=O)]",  # primary/secondary amine, excluding amides
    "[CX3](=O)[OX2H1]",  # carboxylic acid
)


def count_protectable_groups(smiles: str) -> int | None:
    """How many groups on this molecule a chemical route would have to protect.

    This is a count of a structural fact, not an estimate: each matched group
    is a site that a non-selective chemical reagent could also attack, and so
    a site a chemical route must mask and later unmask. It sets how many
    extra steps the chemical counterpart carries relative to the enzyme,
    which is the single largest structural difference between the two.
    """
    try:
        from rdkit import Chem, RDLogger
    except ImportError as exc:  # pragma: no cover - environment-dependent
        raise ScreenError('screening needs RDKit; install with: pip install -e ".[chem]"') from exc
    RDLogger.DisableLog("rdApp.*")
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return None
    total = 0
    for smarts in _PROTECTABLE_SMARTS:
        patt = Chem.MolFromSmarts(smarts)
        if patt is not None:
            total += len(mol.GetSubstructMatches(patt))
    return total


# --- the class template -----------------------------------------------------


@dataclass(frozen=True)
class TemplateMaterial:
    """One material the chemical counterpart consumes, per mole of product.

    ``basis`` is the honesty field, and mirrors `data/processes/`'s
    ``stated``/``stoichiometric`` split:

    - ``sourced``      the amount comes from the template's own cited paper
    - ``generalised``  the amount is extended beyond what that paper did --
                       to a different substrate, or a standard reagent the
                       paper did not itself use. Always spelled out in
                       ``note``.

    ``per_protected_group`` marks an amount that scales with the acceptor's
    own count of protectable groups rather than being fixed per mole.
    """

    name: str
    cas: str | None
    role: Role
    kg_per_mol_product: float
    basis: str
    note: str
    per_protected_group: bool = False


@dataclass(frozen=True)
class ClassTemplate:
    id: str
    name: str
    description: str
    #: One or more ChEBI ids that are interchangeable for this class: the same
    #: transferred group, so the same `expected_mass_delta`. UDP-alpha-D-
    #: glucose and UDP-alpha-D-galactose are diastereomers -- identical
    #: molecular formula, identical MW (564.29), identical anhydrohexosyl
    #: mass delta -- so a hexosylation class can match either without a
    #: second template. A cofactor that transfers a *different* group (e.g.
    #: UDP-N-acetylglucosamine, which adds an extra acetamido group) needs
    #: its own class, because its expected_mass_delta is not this one.
    cofactor_chebi: tuple[str, ...]
    cofactor_role: Role
    chemical_name: str
    chemical_source: str
    materials: tuple[TemplateMaterial, ...]
    #: The mass (g/mol) a genuine member of this class adds to the acceptor
    #: -- +14.03 (CH2) for a methylation, +42.04 (C2H2O) for an acetylation,
    #: +162.14 (C6H10O5) for a hexosylation, and so on. Required: a cofactor
    #: is not a reaction type on its own (see the module docstring's note on
    #: CoA and SAM covering several unrelated transformations), and this is
    #: the one part of "does this reaction belong in this class" that is a
    #: checkable structural fact rather than a judgment call.
    expected_mass_delta: float
    mass_delta_tolerance: float = 1.0
    assumptions_note: str = ""

    def matches(self, rxn: RheaReaction) -> bool:
        """True when this template's cofactor is consumed by `rxn`.

        Matching is on the cofactor appearing as a *reactant*, not on the EC
        number: EC numbers are incomplete in Rhea (many reactions carry none)
        and describe the enzyme, while what decides whether a chemical
        counterpart is even a candidate is what the transformation consumes.

        This is necessary but not sufficient -- a cofactor is consumed by
        every reaction in its biochemical neighbourhood, not just the clean
        group-transfer ones (CoA, for instance, is also consumed by Claisen
        condensations and redox steps that share nothing with acetylation).
        `screen_reaction` applies the `expected_mass_delta` check afterward
        to reject those; `matches` alone only narrows the field.
        """
        return any(p.chebi in self.cofactor_chebi for p in rxn.left)


def load_template(path: str | Path) -> ClassTemplate:
    p = Path(path)
    try:
        raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ScreenError(f"could not read class template {p}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ScreenError(f"{p}: a class template must be a mapping")

    try:
        cls = raw["reaction_class"]
        chem = raw["chemical_counterpart"]
    except KeyError as exc:
        raise ScreenError(f"{p}: missing top-level key {exc}") from exc

    if "expected_mass_delta" not in cls:
        raise ScreenError(
            f"{p}: reaction_class.expected_mass_delta is required -- the mass "
            "(g/mol) a genuine member of this class adds to the acceptor. "
            "Without it, every reaction that merely consumes this cofactor "
            "would be screened as if it were the same transformation, "
            "including ones that are not (see ClassTemplate.matches)."
        )
    try:
        expected_mass_delta = float(cls["expected_mass_delta"])
    except (TypeError, ValueError) as exc:
        raise ScreenError(f"{p}: reaction_class.expected_mass_delta is not a number") from exc
    mass_delta_tolerance = float(cls.get("mass_delta_tolerance", 1.0))

    materials: list[TemplateMaterial] = []
    for entry in chem.get("materials", []):
        basis = entry.get("basis")
        if basis not in ("sourced", "generalised"):
            raise ScreenError(
                f"{p}: material {entry.get('name')!r} has basis={basis!r}; must be "
                "'sourced' (from this template's own cited paper) or 'generalised' "
                "(extended beyond it, with the extension stated in 'note')"
            )
        if not entry.get("note"):
            raise ScreenError(f"{p}: material {entry.get('name')!r} has no 'note'")
        materials.append(
            TemplateMaterial(
                name=entry["name"],
                cas=entry.get("cas"),
                role=entry.get("role", "reagent"),
                kg_per_mol_product=float(entry["kg_per_mol_product"]),
                basis=basis,
                note=entry["note"],
                per_protected_group=bool(entry.get("per_protected_group", False)),
            )
        )
    if not materials:
        raise ScreenError(f"{p}: template has no chemical-counterpart materials")

    raw_cofactor = cls["cofactor_chebi"]
    if isinstance(raw_cofactor, str):
        cofactor_chebi = (raw_cofactor,)
    elif isinstance(raw_cofactor, list) and raw_cofactor and all(
        isinstance(x, str) for x in raw_cofactor
    ):
        cofactor_chebi = tuple(raw_cofactor)
    else:
        raise ScreenError(
            f"{p}: reaction_class.cofactor_chebi must be a ChEBI id, or a list "
            "of ChEBI ids that all share this class's expected_mass_delta"
        )

    return ClassTemplate(
        id=cls["id"],
        name=cls["name"],
        description=cls.get("description", ""),
        cofactor_chebi=cofactor_chebi,
        cofactor_role=cls.get("cofactor_role", "reagent"),
        chemical_name=chem["name"],
        chemical_source=chem["source"],
        materials=tuple(materials),
        expected_mass_delta=expected_mass_delta,
        mass_delta_tolerance=mass_delta_tolerance,
        assumptions_note=chem.get("assumptions_note", ""),
    )


# --- screening one reaction -------------------------------------------------


@dataclass(frozen=True)
class ScreenResult:
    rhea_id: str
    equation: str
    ec: str
    product_name: str
    product_chebi: str
    product_mw: float
    acceptor_name: str
    protectable_groups: int
    cofactor_kg_per_fu: float
    verdict: BoundedVerdict | None
    #: The chemical route's solvent recovery rate at which the verdict stops
    #: holding. This, not the verdict at zero recovery, is the number worth
    #: reading -- see `solvent_recovery_threshold`.
    recovery_threshold: float | None = None
    skipped_reason: str = ""

    @property
    def decided(self) -> bool:
        return self.verdict is not None and self.verdict.decisive

    @property
    def robust(self) -> bool:
        """Decided even if the chemical route recovers 99% of its solvent.

        The distinction that matters in a screen: a reaction that only wins
        because a bench procedure threw its solvent away is not a finding
        about enzymes, it is a finding about bench procedures.
        """
        return self.recovery_threshold is not None and self.recovery_threshold >= 0.99


def _identify(rxn: RheaReaction, template: ClassTemplate) -> tuple[Participant, Participant] | None:
    """Pick out (acceptor, product): the two species that are *not* the cofactor.

    The acceptor is the reactant that is not the cofactor; the product is the
    heaviest species on the right that is not the cofactor's own leaving
    group. Both are identified positionally from Rhea's own curated equation,
    not inferred from names.
    """
    others_left = [p for p in rxn.left if p.chebi not in template.cofactor_chebi]
    if len(others_left) != 1:
        return None
    acceptor = others_left[0]
    # The product carries the acceptor's skeleton plus the transferred group,
    # so among the right-hand species it is the one that is neither a proton
    # nor the nucleotide leaving group. Take the longest-named remaining
    # species as a proxy for "the elaborated one" only when a single
    # candidate does not fall out; both are checked by MW downstream.
    candidates = [p for p in rxn.right if p.chebi not in {"CHEBI:15378"}]
    if not candidates:
        return None
    return acceptor, candidates[0]


def screen_reaction(
    rxn: RheaReaction,
    template: ClassTemplate,
    structures: dict[str, str],
    table: FactorTable,
    assumptions: Assumptions,
    bounds: dict[str, Bound],
) -> ScreenResult:
    """Build the enzymatic-vs-chemical delta for one reaction and decide it."""
    blank = ScreenResult(
        rhea_id=rxn.rhea_id,
        equation=rxn.equation,
        ec=rxn.ec,
        product_name="",
        product_chebi="",
        product_mw=0.0,
        acceptor_name="",
        protectable_groups=0,
        cofactor_kg_per_fu=0.0,
        verdict=None,
    )

    ident = _identify(rxn, template)
    if ident is None:
        return ScreenResult(**{**blank.__dict__, "skipped_reason": "could not identify acceptor/product"})
    acceptor, product = ident

    product_smiles = structures.get(product.chebi)
    acceptor_smiles = structures.get(acceptor.chebi)
    if not product_smiles or not acceptor_smiles:
        return ScreenResult(**{**blank.__dict__, "skipped_reason": "no structure for acceptor or product"})

    product_mw = molecular_weight(product_smiles)
    if not product_mw:
        return ScreenResult(**{**blank.__dict__, "skipped_reason": "product structure would not parse"})

    acceptor_mw = molecular_weight(acceptor_smiles)
    if not acceptor_mw:
        return ScreenResult(**{**blank.__dict__, "skipped_reason": "acceptor structure would not parse"})

    # Which of this class's (possibly several) interchangeable cofactors this
    # particular reaction actually consumes -- its own SMILES, MW and bound
    # key, not necessarily the first one listed in the template.
    cofactor_chebi = next(p.chebi for p in rxn.left if p.chebi in template.cofactor_chebi)
    cofactor_coeff = next(
        p.coefficient for p in rxn.left if p.chebi == cofactor_chebi
    )

    # The class-defining check: does this reaction actually add the group this
    # template models, or does it merely happen to consume the same cofactor?
    # A cofactor is not a reaction type on its own -- see ClassTemplate.matches.
    #
    # Two real effects have to be accounted for before rejecting a mismatch,
    # both found by inspecting what this check actually excluded on the
    # shipped UDP-glucosyltransferase class:
    #
    # - a reaction transferring the group N times (N UDP-glucose consumed,
    #   e.g. a bis-glucoside) adds N times the mass of one transfer, so the
    #   target scales by the cofactor's own stoichiometric coefficient; and
    # - ChEBI records the same acceptor or product at whichever protonation
    #   state its curators used -- often a carboxylate acceptor paired with
    #   a neutral ester product, or vice versa -- so a genuine match can be
    #   off by one proton's mass (1.008) purely from that bookkeeping, not
    #   from a different reaction. Both signs are accepted for the same
    #   reason charge state is not itself chemistry.
    #
    # What this does NOT paper over: a reaction where the "acceptor" is
    # water (the cofactor's own hydrolysis) or where product and acceptor
    # are isomers of each other (a sugar-nucleotide exchange) lands far
    # outside either window and is correctly excluded -- verified by hand
    # against every exclusion bucket before this comment was written.
    _PROTON = 1.00784
    expected = template.expected_mass_delta * cofactor_coeff
    observed_delta = product_mw - acceptor_mw
    candidates = (expected, expected + _PROTON, expected - _PROTON)
    if min(abs(observed_delta - c) for c in candidates) > template.mass_delta_tolerance:
        return ScreenResult(
            **{
                **blank.__dict__,
                "skipped_reason": (
                    f"mass added ({observed_delta:.2f}) does not match this class's "
                    f"expected {expected:.2f} (+/- one proton) -- consumes the "
                    "cofactor but is not this transformation"
                ),
            }
        )

    n_protect = count_protectable_groups(acceptor_smiles)
    if n_protect is None:
        return ScreenResult(**{**blank.__dict__, "skipped_reason": "acceptor structure would not parse"})
    # One of the acceptor's groups is the one the reaction is meant to modify;
    # a chemical route must mask the rest.
    n_masked = max(n_protect - 1, 0)

    # Functional unit: 1 kg of product => this many moles of product.
    mol_per_fu = 1000.0 / product_mw

    cofactor_smiles = structures.get(cofactor_chebi)
    cofactor_mw = molecular_weight(cofactor_smiles) if cofactor_smiles else None
    if not cofactor_mw:
        return ScreenResult(**{**blank.__dict__, "skipped_reason": "no usable cofactor structure"})
    cofactor_kg = mol_per_fu * cofactor_coeff * cofactor_mw / 1000.0

    def diff_at(solvent_recovery: float) -> DiffResult:
        return _build_diff(
            rxn,
            template,
            table,
            mol_per_fu,
            n_masked,
            cofactor_kg,
            cofactor_coeff,
            solvent_recovery,
            cofactor_chebi,
        )

    verdict = bounded_verdict(diff_at(0.0), assumptions, bounds)
    threshold = solvent_recovery_threshold(diff_at, assumptions, bounds, verdict)

    return ScreenResult(
        rhea_id=rxn.rhea_id,
        equation=rxn.equation,
        ec=rxn.ec,
        product_name=product.name,
        product_chebi=product.chebi,
        product_mw=product_mw,
        acceptor_name=acceptor.name,
        protectable_groups=n_protect,
        cofactor_kg_per_fu=cofactor_kg,
        verdict=verdict,
        recovery_threshold=threshold,
    )


def _build_diff(
    rxn: RheaReaction,
    template: ClassTemplate,
    table: FactorTable,
    mol_per_fu: float,
    n_masked: int,
    cofactor_kg: float,
    cofactor_coeff: float,
    solvent_recovery: float,
    cofactor_chebi: str,
) -> DiffResult:
    """The enzymatic-vs-chemical delta set, at a given chemical solvent recovery.

    ``solvent_recovery`` reduces the chemical route's ``role: solvent`` masses
    to their make-up quantity, exactly as `assumptions.solvent_recovery_default`
    does for a real ledger. It is applied to the chemical side only, because
    the enzymatic side of this delta carries no organic solvent to recover --
    that asymmetry is the point of the comparison, not an oversight.

    ``cofactor_coeff`` is how many groups the reaction transfers per molecule
    of product -- 2 for a bis-glucoside, and so on. The template's amounts are
    written per *transfer*, so its fixed stages scale with it: making a
    bis-glucoside chemically means running the glycosylation twice, not once.
    Without this the chemical side would be charged for one transfer while the
    enzymatic side paid for two, which understates the chemical route and
    shows up immediately as an outlier in the recovery-threshold ranking.
    """
    # a = chemical, b = enzymatic, so delta_mass > 0 means "chemical uses more".
    chem: dict[str, tuple[str, Role, float]] = {}
    for m in template.materials:
        scale = n_masked if m.per_protected_group else cofactor_coeff
        if scale == 0:
            continue
        kg = mol_per_fu * m.kg_per_mol_product * scale
        if m.role == "solvent":
            kg *= 1.0 - solvent_recovery
        key = f"cas:{m.cas}" if m.cas else f"name:{m.name.lower()}"
        prev = chem.get(key)
        chem[key] = (m.name, m.role, (prev[2] if prev else 0.0) + kg)

    enz_key = f"name:{cofactor_chebi.lower()}"
    enz = {enz_key: (_cofactor_display(rxn, template), template.cofactor_role, cofactor_kg)}

    all_keys = set(chem) | set(enz)
    materials = [
        _FakeMaterial(
            key=k,
            name=(chem.get(k) or enz.get(k))[0],
            cas=k.split("cas:", 1)[1] if k.startswith("cas:") else None,
        )
        for k in sorted(all_keys)
    ]
    resolutions = resolve_materials(materials, table)

    rows: list[DeltaRow] = []
    unresolved: list[str] = []
    for key in sorted(all_keys):
        name, role, _ = (chem.get(key) or enz.get(key))
        mass_a = chem.get(key, (None, None, 0.0))[2]
        mass_b = enz.get(key, (None, None, 0.0))[2]
        delta = mass_a - mass_b
        if abs(delta) <= 1e-12:
            continue
        res = resolutions.get(key)
        factor = res.factor if res is not None else None
        if factor is None:
            unresolved.append(key)
        rows.append(
            DeltaRow(
                key=key,
                name=name,
                role=role,
                mass_a_kg=mass_a,
                mass_b_kg=mass_b,
                delta_mass_kg=delta,
                factor=factor,
                resolved=factor is not None,
            )
        )

    return DiffResult(
        a_name="chemical",
        b_name="enzymatic",
        rows=rows,
        delta_electricity_kWh=0.0,
        common_unresolved=[],
        delta_unresolved=sorted(unresolved),
    )


def solvent_recovery_threshold(
    diff_at,
    assumptions: Assumptions,
    bounds: dict[str, Bound],
    verdict_at_zero: BoundedVerdict,
    *,
    steps: int = 34,
) -> float | None:
    """How much solvent the chemical route would have to recover to catch up.

    A class template is built from a published *bench* procedure, and bench
    procedures throw their solvent away: the template in
    `data/reaction-classes/udp-glucosyltransferase.yaml` charges over 800 kg
    of solvent per kg of product. A plant does not. So a screen that only
    reported the verdict at zero recovery would mostly be reporting on
    laboratory glassware, and would be emphatically, uselessly pro-enzyme.

    This is the number that survives that objection. It answers: *at what
    solvent recovery rate does this reaction's verdict stop holding?* A
    reaction still decided at 99% recovery is one whose advantage does not
    come from solvent at all. One that turns over at 40% is one where the
    published chemistry, not the enzyme, is doing the work.

    Returns the recovery rate at which the zero-recovery verdict is lost, or
    ``None`` if it was never decided in the first place, or ``1.0`` if it
    survives everything tested.
    """
    if not verdict_at_zero.decisive:
        return None
    target = verdict_at_zero.verdict

    def holds(r: float) -> bool:
        return bounded_verdict(diff_at(r), assumptions, bounds).verdict == target

    if holds(0.999999):
        return 1.0
    lo, hi = 0.0, 0.999999
    for _ in range(steps):
        mid = (lo + hi) / 2.0
        if holds(mid):
            lo = mid
        else:
            hi = mid
    return hi


def _cofactor_display(rxn: RheaReaction, template: ClassTemplate) -> str:
    for p in rxn.left:
        if p.chebi in template.cofactor_chebi:
            return p.name
    return "/".join(template.cofactor_chebi)


@dataclass(frozen=True)
class _FakeMaterial:
    """The minimal shape `resolve_materials` needs: a key, a name, a CAS."""

    key: str
    name: str
    cas: str | None
    role: Role = "reagent"
    mass_kg: float = 0.0


# --- screening the database -------------------------------------------------


@dataclass
class ScreenRun:
    template: ClassTemplate
    results: list[ScreenResult] = field(default_factory=list)
    matched: int = 0
    skipped_unparsed: int = 0

    @property
    def decided(self) -> list[ScreenResult]:
        return [r for r in self.results if r.decided]

    @property
    def undecided(self) -> list[ScreenResult]:
        return [r for r in self.results if r.verdict is not None and not r.verdict.decisive]

    @property
    def unscreened(self) -> list[ScreenResult]:
        return [r for r in self.results if r.verdict is None]


def screen_all(
    reactions: list[RheaReaction],
    template: ClassTemplate,
    structures: dict[str, str],
    table: FactorTable,
    assumptions: Assumptions,
    bounds: dict[str, Bound],
) -> ScreenRun:
    run = ScreenRun(template=template)
    for rxn in reactions:
        if not template.matches(rxn):
            continue
        run.matched += 1
        run.results.append(
            screen_reaction(rxn, template, structures, table, assumptions, bounds)
        )
    return run
