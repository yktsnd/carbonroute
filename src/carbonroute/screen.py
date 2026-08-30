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
from collections.abc import Sequence
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


def count_substructure(smiles: str, smarts: str) -> int | None:
    """How many times `smarts` occurs in `smiles`. None if either won't parse.

    Used to check *what bond a reaction forms*, which the mass delta cannot
    see. Two reactions can add the same mass to the same acceptor and be
    different chemistry: transferring an acetyl onto a hydroxyl makes an
    ester, and condensing the same acetyl onto a carbon makes a ketone. Both
    add 42.04. Only one of them is an acetylation.
    """
    try:
        from rdkit import Chem, RDLogger
    except ImportError as exc:  # pragma: no cover - environment-dependent
        raise ScreenError('screening needs RDKit; install with: pip install -e ".[chem]"') from exc
    RDLogger.DisableLog("rdApp.*")
    mol = Chem.MolFromSmiles(smiles)
    patt = Chem.MolFromSmarts(smarts)
    if mol is None or patt is None:
        return None
    return len(mol.GetSubstructMatches(patt))


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


#: How a term on the enzymatic side is charged against a mole of product.
#:
#:   per_turnover  consumed on every catalytic cycle, so charged in full --
#:                 a regeneration co-substrate (sucrose for sucrose synthase,
#:                 formate or glucose for a dehydrogenase), a sacrificial
#:                 reductant, a buffer salt.
#:   amortised     bought once and used for many batches, so divided by
#:                 `reuse_cycles` -- an immobilised enzyme preparation, its
#:                 carrier resin, a packed-bed charge.
#:
#: Two shapes, because a real biocatalytic process has both and they behave
#: oppositely: pushing harder buys down an amortised term and does nothing
#: to a per-turnover one.
_CHARGE_SHAPES = ("per_turnover", "amortised")


@dataclass(frozen=True)
class ProcessMeasure:
    """One thing the enzymatic route consumes, beyond the cofactor itself.

    The enzymatic side of this diff used to be a single line -- the cofactor
    -- which quietly assumed that everything else about running an enzyme is
    free. It is not, and the two things that are not free pull in opposite
    directions:

      * **Regeneration** buys down the cofactor, and costs a co-substrate on
        every single turnover. Recycling a cofactor without charging what
        drives the recycling is the easiest way to make a biocatalytic route
        look better than any real one.
      * **Immobilisation** is the standard way a real process makes an
        enzyme affordable: the enzyme and its carrier are bought once and
        reused over many batches, so their burden is divided by the number
        of cycles rather than paid per turnover.

    Rather than hard-code either, a template declares whatever measures its
    process actually uses and how each is charged. Every figure carries the
    same `sourced` / `generalised` label and the same citation discipline as
    the chemical side's materials, because an unsourced enzyme loading
    flatters exactly the side this tool is most at risk of flattering.
    """

    name: str
    role: Role
    #: One of `_CHARGE_SHAPES`.
    charge: str
    kg_per_mol_product: float
    basis: str
    note: str
    cas: str | None = None
    #: ChEBI id, when the substance is a Rhea participant. Used as the
    #: resolution key so it lines up with how cofactors are keyed.
    chebi: str | None = None
    #: Batches one purchase serves. Required for `amortised`, ignored
    #: otherwise. This is the number immobilisation exists to raise.
    reuse_cycles: float | None = None
    #: True when this measure is what licenses `cofactor_recycling`. A
    #: template with no such measure may not claim any recycling at all.
    enables_recycling: bool = False
    #: Where the figure comes from. Required, like every other amount here.
    source: str = ""

    @property
    def key(self) -> str:
        if self.cas:
            return f"cas:{self.cas}"
        if self.chebi:
            return f"name:{self.chebi.lower()}"
        return f"name:{self.name.lower()}"

    def kg_per_fu(self, mol_per_fu: float, turnovers: float) -> float:
        """Mass per functional unit, by this measure's own charge shape."""
        if self.charge == "amortised":
            return mol_per_fu * self.kg_per_mol_product / (self.reuse_cycles or 1.0)
        return turnovers * self.kg_per_mol_product


@dataclass(frozen=True)
class ProcessReagent:
    """A reagent charged in stoichiometric proportion to the product."""

    name: str
    cas: str | None
    #: Molar mass, kg/mol. A physical constant, checkable against any table.
    kg_per_mol: float
    equivalents: float
    note: str


@dataclass(frozen=True)
class ProcessStage:
    """One operation, charged from the model's parameters rather than a paper."""

    id: str
    reagents: tuple[ProcessReagent, ...]
    solvent_name: str
    solvent_cas: str | None
    solvent_density_kg_per_L: float
    #: Reaction volumes this stage consumes. 1.0 is the reaction itself; an
    #: isolation stage charges its extraction and wash volumes here.
    volumes: float = 1.0
    #: True when the stage is repeated once per group the acceptor must mask.
    per_protected_group: bool = False


@dataclass(frozen=True)
class ProcessModel:
    """A declared model of a competent process, instead of one paper's bench run.

    A template built from a single published procedure inherits that paper's
    idiosyncrasies along with its rigour, and `explain_verdict` showed what
    that costs: in the shipped class every one of 388 verdicts rests at least
    half on one number -- the source paper's 150 mL of boiling ethyl acetate
    per millimole. The verdicts are, to first order, a statement about one
    author's isolation habits.

    Picking a different paper does not fix that; it substitutes a different
    author's habits, with no principled way to choose between them. What does
    fix it is to stop claiming a paper and start declaring a model: reagents
    at stated equivalents, solvent from a stated reaction concentration, and
    workup as stated multiples of the reaction volume.

    That is *less* precise about any single procedure and *more* honest about
    what the tool is doing, because the alternative was arbitrariness wearing
    the costume of rigour. It is also what makes a class cheap: the parameters
    below are chemistry-independent, so a new class supplies its reagents and
    inherits the process.

    Every parameter is `generalised` by construction -- none is read from a
    paper -- and the model is calibrated by running it against the one
    reaction this repository has a hand-built ledger for.
    """

    name: str
    source: str
    reaction_concentration_M: float
    stage_yield: float
    stages: tuple[ProcessStage, ...]
    note: str


def materials_from_process_model(model: ProcessModel) -> tuple[TemplateMaterial, ...]:
    """Turn declared parameters into the same per-mole-of-product amounts a
    paper-sourced template carries, so the rest of the screen cannot tell the
    difference and the two can be compared directly."""
    out: list[TemplateMaterial] = []
    litres_per_mol = 1.0 / model.reaction_concentration_M
    for i, stage in enumerate(model.stages):
        # Downstream losses: material charged at stage i must survive every
        # later stage, exactly as a paper's per-mole-of-product amounts do.
        carry = model.stage_yield ** (len(model.stages) - i)
        for r in stage.reagents:
            out.append(
                TemplateMaterial(
                    name=r.name,
                    cas=r.cas,
                    role="reagent",
                    kg_per_mol_product=r.equivalents * r.kg_per_mol / carry,
                    basis="generalised",
                    note=f"[process model, stage {stage.id}] {r.note}",
                    per_protected_group=stage.per_protected_group,
                )
            )
        out.append(
            TemplateMaterial(
                name=stage.solvent_name,
                cas=stage.solvent_cas,
                role="solvent",
                kg_per_mol_product=(
                    litres_per_mol * stage.volumes * stage.solvent_density_kg_per_L / carry
                ),
                basis="generalised",
                note=(
                    f"[process model, stage {stage.id}] {stage.volumes:g} reaction "
                    f"volume(s) at {model.reaction_concentration_M:g} M, density "
                    f"{stage.solvent_density_kg_per_L:g} kg/L."
                ),
                per_protected_group=stage.per_protected_group,
            )
        )
    return tuple(out)


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
    #: SMARTS for the bond this transformation creates, counted on the
    #: acceptor and on the product: a genuine member gains exactly one per
    #: group transferred. Optional, and only worth setting where the mass
    #: delta is not enough on its own -- but for a chemically mixed cofactor
    #: it is the difference between a class and a coincidence. Acetyl-CoA is
    #: the case that forced it: restricting to EC 2.3.1 *and* to a +42.04
    #: mass delta still admits beta-ketoacyl syntheses, which condense the
    #: same acetyl onto a carbon rather than transferring it onto a
    #: heteroatom. Same donor, same mass, same EC-3 group, different
    #: chemistry and a completely different chemical counterpart.
    transferred_bond_smarts: str | None = None
    #: Restricts the class to reactions whose EC number starts with this,
    #: e.g. "2.3.1". Left unset the class is defined by its cofactor alone,
    #: which is right only where that cofactor does one thing (UDP-hexose).
    #: Where it does several, this is the field that says which one.
    ec_prefix: str | None = None
    assumptions_note: str = ""
    #: The source procedure's own overall yield, if it reported one. Never
    #: applied to anything: the materials are already stated per mole of
    #: *product*, so this yield is folded into each of them and multiplying
    #: it in again would double-count. It is carried so a report can print
    #: it beside the enzymatic conversion the screen was run at, which is
    #: the only place the asymmetry between the two sides is visible.
    source_overall_yield: float | None = None
    #: What the enzymatic route consumes beyond the cofactor: regeneration
    #: co-substrates, immobilised enzyme and carrier, anything else the
    #: process actually needs. Each declares its own charge shape, because a
    #: per-turnover co-substrate and an amortised immobilised preparation
    #: behave oppositely as the process is pushed harder.
    enzymatic_measures: tuple[ProcessMeasure, ...] = ()
    #: An alternative to `materials`: a declared process rather than one
    #: paper's charged amounts. See `ProcessModel` for why that is the more
    #: honest option and not the less rigorous one.
    process_model: ProcessModel | None = None
    #: ChEBI ids for a second reactant this class's reactions genuinely
    #: consume alongside the cofactor above, but whose own cradle-to-gate
    #: cost this template does NOT price -- e.g. the NAD(P)H a monooxygenase
    #: oxidises to NAD(P)+ while O2 supplies the atom the product actually
    #: gains. Excluded from the acceptor search the same way the cofactor
    #: itself is (so `_identify` does not mistake it for the acceptor), but
    #: it never enters `cofactor_coeff`, the mass-delta check, or any
    #: material charge -- pricing a second, independently-varying cofactor is
    #: a real feature this project does not yet have. This is a stated,
    #: deliberate gap, not a shortcut: any reaction whose enzymatic route
    #: needs a co-cofactor like this has its enzymatic side UNDERSTATED by
    #: whatever that co-cofactor's regeneration really costs, in the same
    #: direction every other unpriced gap in this project understates it --
    #: never invented, always flagged. A report renders a standing warning
    #: whenever a class declares one; see render_screen.
    unpriced_co_cofactor_chebi: tuple[str, ...] = ()

    @property
    def recycling_enablers(self) -> tuple[ProcessMeasure, ...]:
        return tuple(m for m in self.enzymatic_measures if m.enables_recycling)

    def matches(self, rxn: RheaReaction) -> bool:
        """True when this template's cofactor is consumed by `rxn`.

        Matching is primarily on the cofactor appearing as a *reactant*, not
        on the EC number: EC numbers are incomplete in Rhea (only 41% of
        reactions carry one) and describe the enzyme, while what decides
        whether a chemical counterpart is even a candidate is what the
        transformation consumes.

        That is necessary but nowhere near sufficient. A cofactor is consumed
        by every reaction in its biochemical neighbourhood, and for a mixed
        one the field has to be narrowed twice more: `ec_prefix` here, then
        `expected_mass_delta` and `transferred_bond_smarts` in
        `screen_reaction`. Acetyl-CoA needs all three -- 347 reactions
        consume it, 138 of those are EC 2.3.1, and 9 of *those* still add
        42.04 g/mol without being acetylations at all.
        """
        if not any(p.chebi in self.cofactor_chebi for p in rxn.left):
            return False
        if self.ec_prefix is None:
            return True
        return any(
            tok.removeprefix("EC:").startswith(self.ec_prefix)
            for tok in rxn.ec.replace(";", " ").split()
        )


def _source_yield(chem: dict, path: str | Path) -> float | None:
    """Read and range-check the source procedure's own overall yield."""
    raw = chem.get("source_overall_yield")
    if raw is None:
        return None
    try:
        y = float(raw)
    except (TypeError, ValueError):
        raise ScreenError(
            f"{path}: chemical_counterpart.source_overall_yield must be a number"
        ) from None
    if not 0.0 < y <= 1.0:
        raise ScreenError(
            f"{path}: chemical_counterpart.source_overall_yield must be in (0, 1], "
            f"got {y}"
        )
    return y


def _measures(raw, path) -> tuple[ProcessMeasure, ...]:
    """Read the optional enzymatic_process block, on the usual terms."""
    if raw is None:
        return ()
    if not isinstance(raw, dict) or not isinstance(raw.get("measures"), list):
        raise ScreenError(
            f"{path}: enzymatic_process must be a mapping with a 'measures' list"
        )
    out: list[ProcessMeasure] = []
    for i, m in enumerate(raw["measures"]):
        where = f"{path}: enzymatic_process.measures[{i}]"
        if not isinstance(m, dict):
            raise ScreenError(f"{where} must be a mapping")
        for k in ("name", "charge", "kg_per_mol_product", "basis", "note", "source"):
            if m.get(k) in (None, ""):
                raise ScreenError(
                    f"{where} is missing {k}. Every figure on the enzymatic "
                    "side carries the same citation discipline as the chemical "
                    "side, because an unsourced enzyme loading flatters exactly "
                    "the route this tool is most at risk of flattering."
                )
        if m["charge"] not in _CHARGE_SHAPES:
            raise ScreenError(
                f"{where}: charge must be one of {_CHARGE_SHAPES}, got "
                f"{m['charge']!r}"
            )
        if m["basis"] not in ("sourced", "generalised"):
            raise ScreenError(
                f"{where}: basis must be 'sourced' or 'generalised', got "
                f"{m['basis']!r}"
            )
        cycles = m.get("reuse_cycles")
        if m["charge"] == "amortised":
            if not cycles or float(cycles) < 1.0:
                raise ScreenError(
                    f"{where}: an amortised measure needs reuse_cycles >= 1 -- "
                    "how many batches one purchase serves. That number is what "
                    "immobilisation exists to raise, so it cannot be implicit."
                )
            cycles = float(cycles)
        out.append(
            ProcessMeasure(
                name=m["name"],
                role=m.get("role", "reagent"),
                charge=m["charge"],
                kg_per_mol_product=float(m["kg_per_mol_product"]),
                basis=m["basis"],
                note=m["note"],
                cas=m.get("cas"),
                chebi=m.get("chebi"),
                reuse_cycles=cycles,
                enables_recycling=bool(m.get("enables_recycling", False)),
                source=m["source"],
            )
        )
    return tuple(out)


def _process_model(raw, path) -> ProcessModel | None:
    """Read the optional process_model block. Everything in it is declared."""
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ScreenError(f"{path}: process_model must be a mapping")
    for k in ("name", "source", "reaction_concentration_M", "stage_yield", "stages", "note"):
        if raw.get(k) in (None, "", []):
            raise ScreenError(f"{path}: process_model is missing {k}")
    conc = float(raw["reaction_concentration_M"])
    if conc <= 0:
        raise ScreenError(f"{path}: process_model.reaction_concentration_M must be > 0")
    y = float(raw["stage_yield"])
    if not 0.0 < y <= 1.0:
        raise ScreenError(f"{path}: process_model.stage_yield must be in (0, 1]")
    stages: list[ProcessStage] = []
    for i, st in enumerate(raw["stages"]):
        where = f"{path}: process_model.stages[{i}]"
        for k in ("id", "solvent", "reagents"):
            if k not in st:
                raise ScreenError(f"{where} is missing {k}")
        sol = st["solvent"]
        for k in ("name", "density_kg_per_L"):
            if sol.get(k) in (None, ""):
                raise ScreenError(f"{where}.solvent is missing {k}")
        reagents = []
        for j, r in enumerate(st["reagents"]):
            for k in ("name", "kg_per_mol", "equivalents", "note"):
                if r.get(k) in (None, ""):
                    raise ScreenError(f"{where}.reagents[{j}] is missing {k}")
            reagents.append(
                ProcessReagent(
                    name=r["name"],
                    cas=r.get("cas"),
                    kg_per_mol=float(r["kg_per_mol"]),
                    equivalents=float(r["equivalents"]),
                    note=r["note"],
                )
            )
        stages.append(
            ProcessStage(
                id=st["id"],
                reagents=tuple(reagents),
                solvent_name=sol["name"],
                solvent_cas=sol.get("cas"),
                solvent_density_kg_per_L=float(sol["density_kg_per_L"]),
                volumes=float(st.get("volumes", 1.0)),
                per_protected_group=bool(st.get("per_protected_group", False)),
            )
        )
    return ProcessModel(
        name=raw["name"],
        source=raw["source"],
        reaction_concentration_M=conc,
        stage_yield=y,
        stages=tuple(stages),
        note=raw["note"],
    )


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
    if not materials and "process_model" not in raw:
        raise ScreenError(
            f"{p}: template has no chemical-counterpart materials and no "
            "process_model -- it must declare a chemical route one way or "
            "the other"
        )

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

    raw_co_cofactor = cls.get("unpriced_co_cofactor_chebi", [])
    if isinstance(raw_co_cofactor, str):
        unpriced_co_cofactor_chebi = (raw_co_cofactor,)
    elif isinstance(raw_co_cofactor, list) and all(isinstance(x, str) for x in raw_co_cofactor):
        unpriced_co_cofactor_chebi = tuple(raw_co_cofactor)
    else:
        raise ScreenError(
            f"{p}: reaction_class.unpriced_co_cofactor_chebi must be a ChEBI "
            "id, or a list of them"
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
        source_overall_yield=_source_yield(chem, path),
        transferred_bond_smarts=cls.get("transferred_bond_smarts"),
        ec_prefix=cls.get("ec_prefix"),
        enzymatic_measures=_measures(raw.get("enzymatic_process"), p),
        process_model=_process_model(raw.get("process_model"), p),
        unpriced_co_cofactor_chebi=unpriced_co_cofactor_chebi,
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
    #: The enzymatic conversion this row was screened at. Declared, never
    #: implicit: the chemical side of a template already carries its source
    #: paper's real yield, so leaving the enzymatic side at pure
    #: stoichiometry silently favours the enzyme. See `screen_reaction`.
    enzymatic_yield: float = 1.0
    #: The lowest enzymatic conversion at which the verdict still holds, with
    #: the chemical plant recovering `reference_recovery` of its solvent.
    #: ``0.0`` means no conversion requirement -- the verdict holds however
    #: badly the enzyme performs. See `minimum_enzymatic_yield`.
    min_enzymatic_yield: float | None = None
    #: The solvent recovery rate `min_enzymatic_yield` was computed at, and
    #: the standard operating point the advantage interval below is taken at.
    reference_recovery: float = 0.90
    #: The enzymatic route's effort dial: the share of cofactor regenerated
    #: rather than discarded. 0.0 is single-use cofactor. The counterpart of
    #: the chemical route's solvent recovery, and the axis whose absence made
    #: every earlier result here a comparison of unequal effort.
    cofactor_recycling: float = 0.0
    #: How much lower the enzymatic route's footprint is, in kg CO2e per kg
    #: of product, evaluated at the standard operating point -- an interval,
    #: because the cofactor's factor is one. Positive means the enzyme saves
    #: that much. This is the only quantity here that means the same thing in
    #: two different classes; the recovery threshold does not, because it is
    #: measured against whatever solvent load that class's template happens
    #: to carry. `advantage_max` is None when something in the delta is
    #: unbounded above. See `rank_by_advantage`.
    advantage_min_kgCO2e: float | None = None
    advantage_max_kgCO2e: float | None = None
    #: The delta set at the standard operating point, kept so a report can
    #: say what the verdict is made of without recomputing it. This project
    #: is scrupulous about where every number came from and, until this
    #: existed, silent about which of them the answer actually rests on --
    #: provenance without leverage. See `explain_verdict`.
    standard_diff: DiffResult | None = None
    skipped_reason: str = ""

    @property
    def advantage_decided(self) -> bool:
        """True when the whole advantage interval is on one side of zero."""
        lo, hi = self.advantage_min_kgCO2e, self.advantage_max_kgCO2e
        if lo is None or hi is None:
            return lo is not None and lo > 0.0
        return lo > 0.0 or hi < 0.0

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

    A proton is excluded from the left side the same way it already was from
    the right: 2,673 of Rhea's 18,558 reactions (14.4%) carry "+ H(+)" as a
    reactant -- mechanistically real (many oxygenases and reductases need
    it), but never the acceptor a class template is looking for. Leaving it
    in `others_left` silently failed every such reaction's identification
    for every class before this fix, understating matched counts across the
    board; verified empirically to be purely additive (it can only reduce
    `others_left`'s count, never increase it, so a reaction that matched
    before still matches the same way after) against all ten shipped
    classes before landing here.

    `template.unpriced_co_cofactor_chebi` is excluded the same way: a
    second reactant some classes genuinely need (e.g. the NAD(P)H a
    monooxygenase oxidises alongside O2) but whose own cost this project
    does not price. Excluding it here only affects which species can be
    "the acceptor" -- it never enters the mass-delta check or any material
    charge, both of which stay driven by `cofactor_chebi` alone.
    """
    exclude = set(template.cofactor_chebi) | set(template.unpriced_co_cofactor_chebi) | {"CHEBI:15378"}
    others_left = [p for p in rxn.left if p.chebi not in exclude]
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
    *,
    enzymatic_yield: float = 1.0,
    reference_recovery: float = 0.90,
    cofactor_recycling: float = 0.0,
    use_process_model: bool = False,
) -> ScreenResult:
    """Build the enzymatic-vs-chemical delta for one reaction and decide it.

    Claiming recycling requires the template to declare a
    ``enzymatic_process`` measure marked ``enables_recycling``; without one
    this raises. A turnover number asserted with nothing driving it is a free
    lunch. What drives it varies by system -- a co-substrate for a
    dehydrogenase or sucrose synthase, an electrode, a whole cell -- so the
    template says which, rather than the code assuming one shape.

    ``cofactor_recycling`` is the enzymatic route's effort dial, and the exact
    counterpart of the chemical route's ``solvent_recovery``. A cofactor that
    is regenerated in situ -- sucrose synthase driving UDP-glucose,
    formate or glucose dehydrogenase driving NAD(P)H -- is charged once and
    used many times, so the bill is the stoichiometric demand times
    ``1 - cofactor_recycling``, the same shape the solvent bill takes. A
    recycling rate of 0.99 is a total turnover number of 100.

    It defaults to 0.0, which is single-use cofactor: the worst enzymatic
    process anyone would actually run. Sweeping solvent recovery against a
    fixed 0.0 here compares an optimised chemical route with an unoptimised
    enzymatic one, and every earlier result in this repository did exactly
    that. `fair_fight_frontier` moves both dials together instead.

    ``enzymatic_yield`` is the enzymatic route's conversion to product. It
    divides the cofactor demand, because a reaction that only converts half
    its acceptor consumes twice the cofactor per kg of product. The default
    of 1.0 reproduces the historical behaviour, and is deliberately *stated*
    rather than assumed: see the comment on ``cofactor_kg_stoich`` for why
    an unstated 1.0 systematically favours the enzymatic route.

    ``reference_recovery`` is the solvent recovery rate at which
    ``min_enzymatic_yield`` is evaluated. It defaults to the 90% a real
    plant achieves by distillation, which is the operating point at which
    the question "how good does the enzyme have to be?" is worth asking.
    """
    if use_process_model and template.process_model is None:
        raise ScreenError(
            f"{template.id}: --process-model was asked for, but this template "
            "declares no process_model block."
        )
    if not use_process_model and not template.materials:
        raise ScreenError(
            f"{template.id}: this template declares no chemical_counterpart "
            "materials, only a process_model. Screen it with "
            "--process-model -- without that flag the chemical side would "
            "silently be empty, which is not 'the enzyme wins', it is 'the "
            "chemical route was never priced'."
        )
    materials = (
        materials_from_process_model(template.process_model)
        if use_process_model
        else template.materials
    )
    if cofactor_recycling > 0.0 and not template.recycling_enablers:
        raise ScreenError(
            f"{template.id}: cofactor_recycling={cofactor_recycling} was asked "
            "for, but no enzymatic_process measure on this template is marked "
            "enables_recycling. Regeneration is driven by something -- a "
            "co-substrate for sucrose synthase or a dehydrogenase, an "
            "electrode, a whole cell -- and whatever it is does not cancel "
            "out of the diff. Crediting the recycling without charging its "
            "driver would make the enzymatic route look better than any real "
            "one is."
        )
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

    # The mass delta says how much was added. It cannot say what it was added
    # *to*, and for a chemically mixed cofactor that is the whole question:
    # transferring an acetyl onto a hydroxyl makes an ester, condensing the
    # same acetyl onto a carbon makes a ketone, and both weigh 42.04. A class
    # whose donor does more than one thing declares the bond it forms, and a
    # genuine member gains exactly one per group transferred.
    if template.transferred_bond_smarts is not None:
        before = count_substructure(acceptor_smiles, template.transferred_bond_smarts)
        after = count_substructure(product_smiles, template.transferred_bond_smarts)
        if before is None or after is None:
            return ScreenResult(
                **{
                    **blank.__dict__,
                    "skipped_reason": "acceptor or product structure would not parse",
                }
            )
        if after - before != cofactor_coeff:
            return ScreenResult(
                **{
                    **blank.__dict__,
                    "skipped_reason": (
                        f"adds the right mass but forms {after - before} of this "
                        f"class's bond, not {cofactor_coeff:g} -- consumes the "
                        "cofactor for a different transformation"
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
    # Stoichiometric cofactor demand: what a *perfect* enzyme would consume.
    # Nothing is screened at this figure unless `enzymatic_yield` is 1.0,
    # which is a declared assumption rather than the silent default it used
    # to be. The asymmetry it papers over is real and it favours the enzyme:
    # a template's chemical amounts are stated per mole of *product*, so they
    # already carry the source paper's own yield (62% glycosylation x 85%
    # deprotection = 52.7% overall, for the shipped UDP-hexosyltransferase
    # class), while an enzymatic route billed at pure stoichiometry pays no
    # such penalty. Real glycosyltransferase conversions are not
    # quantitative, and the cofactor bill scales with 1/yield.
    cofactor_kg_stoich = mol_per_fu * cofactor_coeff * cofactor_mw / 1000.0

    def diff_at(
        solvent_recovery: float, yield_: float, recycling: float = cofactor_recycling
    ) -> DiffResult:
        return _build_diff(
            rxn,
            template,
            table,
            materials,
            mol_per_fu,
            n_masked,
            cofactor_kg_stoich / yield_ * (1.0 - recycling),
            cofactor_coeff,
            solvent_recovery,
            cofactor_chebi,
            template.enzymatic_measures,
            mol_per_fu,
            mol_per_fu * cofactor_coeff / yield_,
            recycling > 0.0,
        )

    verdict = bounded_verdict(diff_at(0.0, enzymatic_yield), assumptions, bounds)
    threshold = solvent_recovery_threshold(
        lambda r: diff_at(r, enzymatic_yield), assumptions, bounds, verdict
    )
    min_yield = minimum_enzymatic_yield(
        lambda y: diff_at(reference_recovery, y), assumptions, bounds
    )
    # The cross-class quantity, and the only one here that survives leaving
    # this class. A recovery threshold is measured against the solvent load
    # of one template, so 86% in a glycosylation class and 86% in a
    # methylation class are not the same statement. Kilograms of CO2e saved
    # per kilogram of product are, provided both are read at the same
    # operating point -- which is what `reference_recovery` fixes.
    standard = bounded_verdict(
        diff_at(reference_recovery, enzymatic_yield), assumptions, bounds
    )

    return ScreenResult(
        rhea_id=rxn.rhea_id,
        equation=rxn.equation,
        ec=rxn.ec,
        product_name=product.name,
        product_chebi=product.chebi,
        product_mw=product_mw,
        acceptor_name=acceptor.name,
        protectable_groups=n_protect,
        # What is actually charged, recycling included -- not the
        # stoichiometric demand. A reported figure that ignored the recycling
        # the run was given would disagree with the diff it came from.
        cofactor_kg_per_fu=cofactor_kg_stoich / enzymatic_yield * (1.0 - cofactor_recycling),
        verdict=verdict,
        recovery_threshold=threshold,
        enzymatic_yield=enzymatic_yield,
        min_enzymatic_yield=min_yield,
        reference_recovery=reference_recovery,
        cofactor_recycling=cofactor_recycling,
        advantage_min_kgCO2e=standard.delta_min_kgCO2e,
        advantage_max_kgCO2e=standard.delta_max_kgCO2e,
        standard_diff=diff_at(reference_recovery, enzymatic_yield),
    )


def _build_diff(
    rxn: RheaReaction,
    template: ClassTemplate,
    table: FactorTable,
    materials: tuple[TemplateMaterial, ...],
    mol_per_fu: float,
    n_masked: int,
    cofactor_kg: float,
    cofactor_coeff: float,
    solvent_recovery: float,
    cofactor_chebi: str,
    measures: tuple[ProcessMeasure, ...] = (),
    mol_per_fu_measures: float = 0.0,
    turnovers_per_fu: float = 0.0,
    recycling_on: bool = False,
) -> DiffResult:
    """The enzymatic-vs-chemical delta set, at a given chemical solvent recovery.

    ``solvent_recovery`` reduces the chemical route's ``role: solvent`` masses
    to their make-up quantity, exactly as `assumptions.solvent_recovery_default`
    does for a real ledger. It is applied to the chemical side only, because
    the enzymatic side of this delta carries no organic solvent to recover.

    That is not the whole story, and reading it as one used to bias every
    number here. Solvent recovery is the chemical route's effort dial, and
    sweeping it while the enzymatic side stays at bare stoichiometry compares
    a chemical process someone optimised against an enzymatic process nobody
    did. The enzymatic route has its own dial and it is not solvent: it is
    how many times the cofactor turns over before it is discarded. Its
    equivalent of recovering solvent is regenerating cofactor, and
    `cofactor_recycling` is where that enters -- see `screen_reaction`.

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
    for m in materials:
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
    # Everything else running the enzyme costs. A measure that only exists
    # to enable recycling is charged only when recycling is switched on; an
    # immobilised preparation is charged whether or not it is, because the
    # process uses it either way. Each measure applies its own charge shape:
    # per-turnover terms scale with the cycles, amortised ones divide by the
    # batches a single purchase serves.
    for m in measures:
        if m.enables_recycling and not recycling_on:
            continue
        kg = m.kg_per_fu(mol_per_fu_measures, turnovers_per_fu)
        if kg <= 0.0:
            continue
        prev = enz.get(m.key)
        enz[m.key] = (m.name, m.role, (prev[2] if prev else 0.0) + kg)

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


def minimum_enzymatic_yield(
    diff_at_yield,
    assumptions: Assumptions,
    bounds: dict[str, Bound],
    *,
    steps: int = 34,
) -> float | None:
    """How good the enzyme has to be for its verdict to survive.

    The mirror image of `solvent_recovery_threshold`, and the half of the
    picture that was missing. A template's chemical amounts are stated per
    mole of product, so they already carry the source paper's real yield;
    the enzymatic side, billed at stoichiometry, carries none. That
    asymmetry is worth what an enzymatic route's own losses are worth, and
    it always points the same way -- towards the enzyme.

    This answers the question that removes it: *at the solvent recovery a
    real plant achieves, what is the lowest conversion at which the
    enzymatic route still wins?* A reaction needing 20% is one whose
    advantage is structural. One needing 95% is one that wins on paper and
    would lose in a reactor.

    Returns that conversion, ``0.0`` if the verdict holds at any conversion
    tested, or ``None`` if the comparison was never decided at full
    conversion in the first place.
    """
    at_full = bounded_verdict(diff_at_yield(1.0), assumptions, bounds)
    if not at_full.decisive:
        return None
    target = at_full.verdict

    def holds(y: float) -> bool:
        return bounded_verdict(diff_at_yield(y), assumptions, bounds).verdict == target

    # Lower conversion only ever costs the enzymatic route more cofactor, so
    # `holds` is monotone in y and a bisection is exact to its step count.
    floor = 0.000001
    if holds(floor):
        return 0.0
    lo, hi = floor, 1.0  # holds(hi) is true, holds(lo) is false
    for _ in range(steps):
        mid = (lo + hi) / 2.0
        if holds(mid):
            hi = mid
        else:
            lo = mid
    return hi


@dataclass(frozen=True)
class RankedReaction:
    """One reaction's place in a ranking that refuses to invent precision.

    `best_rank` and `worst_rank` bracket where this reaction can sit once
    every other reaction is allowed to take any value inside its own
    advantage interval. They are equal only when the interval genuinely
    separates it from everything else; a wide spread between them is the
    honest report that the data does not order these two reactions at all.
    """

    result: ScreenResult
    best_rank: int
    worst_rank: int

    @property
    def determinate(self) -> bool:
        return self.best_rank == self.worst_rank


def _advantage_interval(r: ScreenResult) -> tuple[float, float]:
    lo = r.advantage_min_kgCO2e
    hi = r.advantage_max_kgCO2e
    return (
        float("-inf") if lo is None else lo,
        float("inf") if hi is None else hi,
    )


@dataclass(frozen=True)
class Contribution:
    """One material's share of what a verdict is actually made of."""

    key: str
    name: str
    side: str  # "chemical" | "enzymatic"
    mass_kg: float
    #: The value this material takes in the case LEAST favourable to the
    #: verdict: a chemical-side material at its floor, an enzymatic-side one
    #: at its ceiling. Same convention `bounded_verdict` uses for delta_min.
    value_kgCO2e_per_kg: float | None
    contribution_kgCO2e: float
    #: "measured" (a factor from a table), "bounded" (an asserted interval),
    #: or "unbounded" (no ceiling asserted -- see the note in the bounds file).
    evidence: str
    share: float


@dataclass(frozen=True)
class VerdictExplanation:
    """What a verdict rests on, ranked -- the complement of provenance.

    "This tool invents no numbers" is a claim about where values come from.
    It says nothing about which of them the answer is made of, and those are
    different questions: a heroically-sourced figure carrying 0.1% of the
    delta and a casually-looked-up one carrying 80% get identical ceremony
    from a provenance discipline alone.

    Every result this project has had to withdraw shared one signature: a
    single term dominated the delta and its value came from an assumption
    rather than a measurement. That is mechanically detectable, and this is
    the detector.
    """

    contributions: tuple[Contribution, ...]
    measured_share: float
    bounded_share: float
    unbounded_share: float

    @property
    def top(self) -> Contribution | None:
        return self.contributions[0] if self.contributions else None

    @property
    def concentration(self) -> float:
        """Share of the delta carried by the single largest term.

        High concentration is not an error, but it changes what the verdict
        means: at 0.8 the answer is mostly a statement about one material's
        quantity, and should be read as one.
        """
        t = self.top
        return t.share if t else 0.0


def explain_verdict(
    diff: DiffResult, bounds: dict[str, Bound]
) -> VerdictExplanation:
    """Rank a delta set by how much of the verdict each material carries."""
    raw: list[tuple[str, str, str, float, float | None, float, str]] = []
    for row in diff.rows:
        b = bounds.get(row.key)
        chemical = row.mass_a_kg > row.mass_b_kg
        mass = row.mass_a_kg if chemical else row.mass_b_kg
        if row.factor is not None:
            value, evidence = row.factor.gwp_kgCO2e_per_kg, "measured"
        elif b is None:
            value, evidence = None, "unbounded"
        elif chemical:
            # Hostile to "the enzyme wins": the chemical route costs its floor.
            value, evidence = b.low, "bounded"
        elif b.bounded_above:
            value, evidence = b.high, "bounded"
        else:
            value, evidence = None, "unbounded"
        contribution = mass * (value or 0.0) * (1.0 if chemical else -1.0)
        raw.append(
            (
                row.key,
                row.name,
                "chemical" if chemical else "enzymatic",
                mass,
                value,
                contribution,
                evidence,
            )
        )

    total = sum(abs(r[5]) for r in raw)
    contributions = tuple(
        sorted(
            (
                Contribution(
                    key=k,
                    name=n,
                    side=side,
                    mass_kg=mass,
                    value_kgCO2e_per_kg=value,
                    contribution_kgCO2e=c,
                    evidence=ev,
                    share=(abs(c) / total if total else 0.0),
                )
                for k, n, side, mass, value, c, ev in raw
            ),
            key=lambda c: -c.share,
        )
    )
    by = {"measured": 0.0, "bounded": 0.0, "unbounded": 0.0}
    for c in contributions:
        by[c.evidence] += c.share
    return VerdictExplanation(
        contributions=contributions,
        measured_share=by["measured"],
        bounded_share=by["bounded"],
        unbounded_share=by["unbounded"],
    )


def rank_by_advantage(results: Sequence[ScreenResult]) -> list[RankedReaction]:
    """Rank reactions by kg CO2e saved per kg of product, without faking order.

    This is the metric that crosses class boundaries. A recovery threshold
    cannot: it is stated relative to the solvent load of one template, so the
    same percentage in two classes describes two different things. An
    absolute saving per kilogram of product is the same statement anywhere,
    as long as every class is read at the same operating point.

    What it is not is a total order. Each saving is an interval, and
    intervals overlap, so the honest output is a rank *range*: a reaction is
    beaten only by reactions whose worst case is better than its best case.
    Sorting the intervals by midpoint and printing 1, 2, 3 would manufacture
    exactly the precision this project refuses to manufacture elsewhere.
    """
    scored = [(r, *_advantage_interval(r)) for r in results]
    ranked: list[RankedReaction] = []
    for r, lo, hi in scored:
        # Strict domination only: another reaction outranks this one when its
        # worst case still beats this one's best case.
        beaten_by = sum(1 for _, o_lo, _o_hi in scored if o_lo > hi)
        beats = sum(1 for _, _o_lo, o_hi in scored if o_hi < lo)
        ranked.append(
            RankedReaction(
                result=r,
                best_rank=beaten_by + 1,
                worst_rank=len(scored) - beats,
            )
        )
    ranked.sort(key=lambda x: (x.best_rank, x.worst_rank, -_advantage_interval(x.result)[0]))
    return ranked


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
    #: The enzymatic conversion every row in this run was screened at, the
    #: solvent recovery its `min_enzymatic_yield` figures assume, and the
    #: cofactor regeneration the enzymatic side was credited with.
    enzymatic_yield: float = 1.0
    reference_recovery: float = 0.90
    cofactor_recycling: float = 0.0
    #: Whether the chemical side was charged from the template's declared
    #: process_model rather than from chemical_counterpart.materials. Report
    #: rendering needs this: the "already carries the source paper's yield"
    #: framing is meaningless for a process model, which has no paper.
    use_process_model: bool = False

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
    *,
    enzymatic_yield: float = 1.0,
    reference_recovery: float = 0.90,
    cofactor_recycling: float = 0.0,
    use_process_model: bool = False,
) -> ScreenRun:
    run = ScreenRun(
        template=template,
        enzymatic_yield=enzymatic_yield,
        reference_recovery=reference_recovery,
        cofactor_recycling=cofactor_recycling,
        use_process_model=use_process_model,
    )
    for rxn in reactions:
        if not template.matches(rxn):
            continue
        run.matched += 1
        run.results.append(
            screen_reaction(
                rxn,
                template,
                structures,
                table,
                assumptions,
                bounds,
                enzymatic_yield=enzymatic_yield,
                reference_recovery=reference_recovery,
                cofactor_recycling=cofactor_recycling,
                use_process_model=use_process_model,
            )
        )
    return run


@dataclass(frozen=True)
class FrontierPoint:
    """One point on a class's break-even curve."""

    enzymatic_yield: float
    decided: int
    min_threshold: float | None
    median_threshold: float | None
    max_threshold: float | None


def break_even_frontier(
    reactions: list[RheaReaction],
    template: ClassTemplate,
    structures: dict[str, str],
    table: FactorTable,
    assumptions: Assumptions,
    bounds: dict[str, Bound],
    *,
    yields: Sequence[float] = (1.0, 0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3),
) -> list[FrontierPoint]:
    """A class's verdict boundary on the (conversion, solvent recovery) plane.

    A verdict is not a point, it is a region, and two numbers the screen
    cannot know decide where its edge lies: how much solvent the chemical
    plant recovers, and how well the enzyme converts. Reporting a single
    recovery threshold fixes the second at 100% and hides that it was a
    choice -- one that always flatters the enzyme, because the chemical side
    of a template already carries its source paper's real yield.

    This sweeps the hidden axis and returns the boundary itself. Reading
    down the list shows exactly how much solvent-recovery headroom the
    enzymatic route surrenders for each point of conversion it loses.
    """
    return [
        _summarise_frontier(
            y,
            screen_all(
                reactions,
                template,
                structures,
                table,
                assumptions,
                bounds,
                enzymatic_yield=y,
            ),
        )
        for y in yields
    ]


@dataclass(frozen=True)
class FairFightPoint:
    """Both routes optimised to the same degree, and who wins there."""

    effort: float
    decided: int
    enzyme_wins: int
    chemistry_wins: int
    undecided: int


def fair_fight_frontier(
    reactions: list[RheaReaction],
    template: ClassTemplate,
    structures: dict[str, str],
    table: FactorTable,
    assumptions: Assumptions,
    bounds: dict[str, Bound],
    *,
    efforts: Sequence[float] = (0.0, 0.5, 0.8, 0.9, 0.95, 0.99),
    enzymatic_yield: float = 1.0,
) -> list[FairFightPoint]:
    """Move both routes' effort dials together, and see who wins.

    Every result in this repository before this function swept the chemical
    route's solvent recovery while the enzymatic route stayed at bare
    stoichiometric cofactor. That is not a comparison of two technologies,
    it is a comparison of a process someone optimised against a process
    nobody did, and it flatters whichever side is being swept.

    The two routes do not have the same dial, which is why the asymmetry was
    easy to miss. A chemical plant's lever is solvent: distil it back and
    charge only the make-up. A biocatalytic plant's lever is not solvent --
    it already runs in water -- it is the cofactor, regenerated in situ so
    that one charge of it turns over many times. Recovering 90% of solvent
    and regenerating 90% of cofactor are the same amount of engineering
    ambition pointed at each route's own dominant burden.

    So this sweeps them together: at each `effort`, the chemical side
    recovers that share of its solvent and the enzymatic side regenerates
    that share of its cofactor. The diagonal is the fair fight, and reading
    down it says which technology wins when both are pushed equally hard,
    rather than which one the analyst happened to optimise.
    """
    points: list[FairFightPoint] = []
    for e in efforts:
        run = screen_all(
            reactions,
            template,
            structures,
            table,
            assumptions,
            bounds,
            enzymatic_yield=enzymatic_yield,
            cofactor_recycling=e,
            reference_recovery=e,
        )
        enzyme = chemistry = undecided = 0
        for r in run.results:
            if r.verdict is None:
                continue
            at_effort = r.advantage_min_kgCO2e, r.advantage_max_kgCO2e
            lo = float("-inf") if at_effort[0] is None else at_effort[0]
            hi = float("inf") if at_effort[1] is None else at_effort[1]
            if lo > 0.0:
                enzyme += 1
            elif hi < 0.0:
                chemistry += 1
            else:
                undecided += 1
        points.append(
            FairFightPoint(
                effort=e,
                decided=enzyme + chemistry,
                enzyme_wins=enzyme,
                chemistry_wins=chemistry,
                undecided=undecided,
            )
        )
    return points


def _summarise_frontier(y: float, run: ScreenRun) -> FrontierPoint:
    thresholds = sorted(
        r.recovery_threshold for r in run.decided if r.recovery_threshold is not None
    )
    if not thresholds:
        return FrontierPoint(y, len(run.decided), None, None, None)
    return FrontierPoint(
        enzymatic_yield=y,
        decided=len(run.decided),
        min_threshold=thresholds[0],
        median_threshold=thresholds[len(thresholds) // 2],
        max_threshold=thresholds[-1],
    )
