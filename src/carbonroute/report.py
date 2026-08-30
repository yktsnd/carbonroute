"""Markdown report and lock-file rendering (spec sections 9, 13).

This module never computes an emission value itself; it only formats
:class:`~carbonroute.compute.Comparison`/`RouteResult` objects (and the
:class:`~carbonroute.sensitivity.Threshold` list) that ``compute.py`` and
``sensitivity.py`` build. Deliberately duck-typed: the ``from __future__
import annotations`` postpones evaluation of the type hints below, so this
module carries no hard import on ``compute``/``sensitivity`` — it only needs
objects that look like their dataclasses.
"""

from __future__ import annotations

from collections import Counter

import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

if TYPE_CHECKING:  # pragma: no cover - type checking only, no runtime import
    from .bounds import BoundedVerdict
    from .compute import Comparison, RouteResult
    from .ledger import AdjustedRoute
    from .resolve import FactorTable, Resolution
    from .schema import Ledger
    from .screen import ScreenRun
    from .sensitivity import Threshold

_NOT_ISO_NOTICE = (
    "**This is not an ISO 14067-conformant calculation.** carbonroute is a "
    "screening-level, comparative tool: it estimates which of two synthetic "
    "routes has the lower cradle-to-gate GHG footprint under the assumptions "
    "stated below, and how confident that ranking is. It does not certify a "
    "Product Carbon Footprint, has not been through critical review, and must "
    "not be cited as an ISO 14067/14040 result."
)


def _fmt(x: float | None, digits: int = 4) -> str:
    if x is None:
        return "n/a"
    return f"{x:.{digits}g}"


def _pct(x: float) -> str:
    return f"{100.0 * x:.1f}%"


def _confidence_word(p_a_lower: float) -> str:
    p = max(p_a_lower, 1.0 - p_a_lower)
    if p >= 0.95:
        return "very likely"
    if p >= 0.8:
        return "likely"
    return "marginally likely"


def _yaml_block(assumptions: Any) -> str:
    dumped = assumptions.model_dump(mode="json")
    return yaml.safe_dump(dumped, sort_keys=False, allow_unicode=True, default_flow_style=False)


def _factor_table_section(comparison: "Comparison") -> list[str]:
    # Group the database_version(s) actually seen per table path, from the
    # resolved factors — FactorTable itself is not carried on Comparison.
    versions_by_path: dict[str, set[str]] = defaultdict(set)
    for res in comparison.resolutions.values():
        if res.factor is not None and res.factor.table:
            versions_by_path[res.factor.table].add(res.factor.database_version or "n/a")

    lines = ["## Factor tables", ""]
    lines.append("| path | sha256 | database version(s) seen |")
    lines.append("|---|---|---|")
    for path, digest in sorted(comparison.factor_sources.items()):
        versions = ", ".join(sorted(versions_by_path.get(path, {"(none used)"})))
        lines.append(f"| `{path}` | `{digest}` | {versions} |")
    lines.append("")
    lines.append(f"Combined fingerprint (order-independent): `{comparison.factor_fingerprint}`")
    lines.append("")
    return lines


def _provenance_breakdown(comparison: "Comparison") -> list[str]:
    """Share of the *delta*'s emissions attributable to each uncertainty class."""
    totals: dict[str, float] = defaultdict(float)
    for row in comparison.diff.rows:
        if row.resolved and row.factor is not None:
            totals[row.factor.uncertainty_class] += abs(row.delta_mass_kg * row.factor.gwp_kgCO2e_per_kg)

    grid = comparison.assumptions.grid_factor
    elec_contribution = abs(comparison.diff.delta_electricity_kWh * grid.value_kgCO2e_per_kWh)
    if elec_contribution > 0:
        totals[grid.uncertainty_class] += elec_contribution

    grand_total = sum(totals.values())
    lines = ["## Provenance breakdown of the resolution", ""]
    lines.append(
        "Share of the resolved delta's absolute GWP contribution "
        "(`|delta_mass * factor|`, electricity included under the grid "
        "factor's own uncertainty class) that comes from each provenance class:"
    )
    lines.append("")
    if grand_total <= 0:
        lines.append("_No resolved, non-cancelling delta contributions to break down._")
        lines.append("")
        return lines
    lines.append("| uncertainty class | share of absolute delta GWP | kgCO2e (abs) |")
    lines.append("|---|---|---|")
    for cls, value in sorted(totals.items(), key=lambda kv: -kv[1]):
        lines.append(f"| {cls} | {_pct(value / grand_total)} | {_fmt(value)} |")
    lines.append("")
    n_unresolved = len(comparison.diff.delta_unresolved)
    if n_unresolved:
        lines.append(
            f"_{n_unresolved} delta material(s) are unresolved and excluded from this "
            "breakdown; see the warning below._"
        )
        lines.append("")
    return lines


def _warning_block(comparison: "Comparison") -> list[str]:
    illustrative = comparison.illustrative_keys
    unresolved = comparison.diff.delta_unresolved
    derived = comparison.derived_keys
    if not illustrative and not unresolved and not derived:
        return []
    lines = ["> **WARNING — read before trusting the conclusion below.**", ">"]
    if illustrative:
        lines.append(
            f"> {len(illustrative)} of the factors consumed in this comparison are "
            "**ILLUSTRATIVE placeholders**, not real LCA data:"
        )
        for key in sorted(illustrative):
            res = comparison.resolutions.get(key)
            label = res.name if res is not None else key
            lines.append(f"> - `{key}` ({label})")
        lines.append(">")
    if derived:
        lines.append(
            f"> {len(derived)} of the factors consumed here were **derived by "
            "`carbonroute bootstrap`** from a production recipe rather than measured. "
            "Each is a lower bound widened into an interval by a declared completeness "
            "assumption, so it is a model of a plant, not an observation of one:"
        )
        for key in sorted(derived):
            res = comparison.resolutions.get(key)
            label = res.name if res is not None else key
            factor = res.factor if res is not None else None
            interval = ""
            if factor is not None and factor.gsd:
                low = factor.gwp_kgCO2e_per_kg / factor.gsd ** 1.6448536269514722
                high = factor.gwp_kgCO2e_per_kg * factor.gsd ** 1.6448536269514722
                interval = f" — modelled range {_fmt(low)} to {_fmt(high)} kgCO2e/kg"
            lines.append(f"> - `{key}` ({label}){interval}")
        lines.append(">")
    if unresolved:
        lines.append(
            f"> {len(unresolved)} material(s) that materially differ between the routes "
            "have **no resolved factor** and are excluded from the statistics below, "
            "biasing the comparison by an unknown amount:"
        )
        for key in sorted(unresolved):
            lines.append(f"> - `{key}`")
        lines.append(">")
    lines.append("> Treat any ranking below as provisional until these are addressed.")
    lines.append("")
    return lines


def _conclusion(comparison: "Comparison", thresholds: "list[Threshold] | None") -> list[str]:
    stats = comparison.stats
    a, b = comparison.a, comparison.b
    lines = ["## Conclusion", ""]

    from .compute import unresolved_flip_factor

    flip = unresolved_flip_factor(comparison.diff, comparison.assumptions)

    if stats.verdict == "indeterminate":
        band = comparison.assumptions.indeterminate_band
        if stats.indeterminate_reason:
            lines.append(
                f"**The comparison is undecided**, because {stats.indeterminate_reason}. "
                f"No ranking is reported."
            )
            lines.append("")
            lines.append(
                f"The Monte Carlo over the resolved part alone gives "
                f"P(GWP({a.label}) < GWP({b.label})) {_fmt_probability(stats.p_a_lower, stats.iterations)}. That number "
                f"describes {stats.coverage_mass_fraction * 100:.1f}% of the differing mass and "
                f"says nothing about the rest, which is why it is not the conclusion."
            )
        else:
            lines.append(
                f"**The comparison is undecided.** P(GWP({a.label}) < GWP({b.label})) "
                f"{_fmt_probability(stats.p_a_lower, stats.iterations)}, inside the configured indeterminate band "
                f"[{band.low}, {band.high}]. No ranking is reported."
            )
        lines.append("")
        lines.extend(_flip_lines(flip))
        lines.append("What would settle it:")
        lines.append("")
        unresolved_rows = sorted(
            (r for r in comparison.diff.rows if not r.resolved),
            key=lambda r: -abs(r.delta_mass_kg),
        )
        if unresolved_rows:
            lines.append("- Largest unresolved delta materials (need a factor):")
            for row in unresolved_rows[:8]:
                lines.append(
                    f"  - `{row.key}` ({row.name}, role={row.role}): "
                    f"delta mass {row.delta_mass_kg:+.4g} kg/FU"
                )
        else:
            lines.append("- No unresolved materials are driving the delta; the tie is genuine "
                          "under the current uncertainty model.")
        if thresholds:
            crossing = sorted(
                (t for t in thresholds if t.crossing is not None),
                key=lambda t: abs(t.baseline - t.crossing),
            )
            if crossing:
                lines.append("- Reversal thresholds nearest to their crossing point:")
                for t in crossing[:5]:
                    lines.append(
                        f"  - {t.label}: baseline {_fmt(t.baseline)}, crosses P=0.5 at "
                        f"{_fmt(t.crossing)}"
                    )
        lines.append("")
        return lines

    winner = a if stats.verdict == "A<B" else b
    loser = b if stats.verdict == "A<B" else a
    p_win = stats.p_a_lower if stats.verdict == "A<B" else 1.0 - stats.p_a_lower
    lines.append(
        f"**{winner.label} is {_confidence_word(p_win)} lower** than {loser.label} "
        f"(P {_fmt_probability(p_win, stats.iterations)})."
    )
    lines.append("")
    lines.append(
        f"Delta ({a.label} - {b.label}): median {_fmt(stats.delta_median)} kgCO2e/FU, "
        f"90% interval [{_fmt(stats.delta_p05)}, {_fmt(stats.delta_p95)}], "
        f"{stats.iterations} draws, seed {stats.seed}."
    )
    if stats.excluded_keys:
        lines.append(
            f"({len(stats.excluded_keys)} unresolved delta material(s) excluded from the "
            "Monte Carlo — see the warning above.)"
        )
    lines.append("")
    lines.extend(_flip_lines(flip))
    return lines


def _flip_lines(flip) -> list[str]:
    """How much the unresolved part of the delta would have to carry to reverse things."""
    if flip.unresolved_delta_mass_kg == 0.0 and flip.breakeven_kgCO2e_per_kg is None:
        return []
    lines = ["### What the missing data would have to be", ""]
    lines.append(
        f"Resolved part of the difference: {_fmt(flip.resolved_delta_kgCO2e)} kgCO2e/FU. "
        f"Unresolved differing mass: {_fmt(flip.unresolved_delta_mass_kg)} kg/FU (signed)."
    )
    lines.append("")
    lines.append(flip.note)
    lines.append("")
    lines.append(
        "_No factor was assumed for the unresolved materials. This states the "
        "break-even value they would need to average, which is a question the data "
        "can answer, rather than filling the gap with a number it cannot._"
    )
    lines.append("")
    return lines


def _route_body(rr: "RouteResult") -> list[str]:
    lines = [f"### {rr.label} (`{rr.name}`)", ""]
    lines.append(
        f"Indicative total: **{_fmt(rr.total_kgCO2e)} kgCO2e/FU** "
        f"(materials {_fmt(rr.material_gwp_kgCO2e)} + electricity "
        f"{_fmt(rr.electricity_gwp_kgCO2e)}, resolved rows only — see warnings above "
        "for what this omits). This absolute figure is indicative context, not the "
        "tool's conclusion."
    )
    lines.append("")
    lines.append("| material | role | mass_kg/FU | factor kgCO2e/kg | gwp kgCO2e/FU |")
    lines.append("|---|---|---|---|---|")
    for row in rr.materials:
        factor_val = _fmt(row.factor.gwp_kgCO2e_per_kg) if row.factor else "UNRESOLVED"
        gwp_val = _fmt(row.gwp_kgCO2e) if row.gwp_kgCO2e is not None else "-"
        lines.append(f"| {row.name} | {row.role} | {_fmt(row.mass_kg)} | {factor_val} | {gwp_val} |")
    lines.append("")
    lines.append("By role (resolved only):")
    lines.append("")
    lines.append("| role | kgCO2e/FU |")
    lines.append("|---|---|")
    for role, value in sorted(rr.by_role.items(), key=lambda kv: -kv[1]):
        lines.append(f"| {role} | {_fmt(value)} |")
    lines.append("")
    if rr.missing:
        lines.append(f"Missing factors: {', '.join(f'`{k}`' for k in rr.missing)}")
        lines.append("")
    return lines


def _delta_table(comparison: "Comparison") -> list[str]:
    diff = comparison.diff
    lines = ["## Contribution to the delta, by material", ""]
    lines.append(f"{comparison.a.label} - {comparison.b.label}, materials with a non-zero "
                 "adjusted-mass difference only:")
    lines.append("")
    lines.append("| material | role | mass_a_kg | mass_b_kg | delta_mass_kg | delta gwp kgCO2e |")
    lines.append("|---|---|---|---|---|---|")
    for row in diff.rows:
        if row.resolved and row.factor is not None:
            delta_gwp = _fmt(row.delta_mass_kg * row.factor.gwp_kgCO2e_per_kg)
        else:
            delta_gwp = "UNRESOLVED"
        lines.append(
            f"| {row.name} | {row.role} | {_fmt(row.mass_a_kg)} | {_fmt(row.mass_b_kg)} | "
            f"{row.delta_mass_kg:+.4g} | {delta_gwp} |"
        )
    if diff.delta_electricity_kWh:
        lines.append(
            f"| _electricity_ | - | - | - | {diff.delta_electricity_kWh:+.4g} kWh | "
            f"{_fmt(diff.delta_electricity_kWh * comparison.assumptions.grid_factor.value_kgCO2e_per_kWh)} |"
        )
    lines.append("")

    by_role: dict[str, float] = defaultdict(float)
    for row in diff.rows:
        if row.resolved and row.factor is not None:
            by_role[row.role] += row.delta_mass_kg * row.factor.gwp_kgCO2e_per_kg
    lines.append("### Contribution to the delta, by role")
    lines.append("")
    lines.append("| role | delta gwp kgCO2e |")
    lines.append("|---|---|")
    for role, value in sorted(by_role.items(), key=lambda kv: -abs(kv[1])):
        lines.append(f"| {role} | {_fmt(value)} |")
    lines.append("")

    if diff.common_unresolved:
        lines.append(
            "Unresolved materials whose masses cancel between routes (informational, "
            "not a warning — they do not affect the delta): "
            + ", ".join(f"`{k}`" for k in diff.common_unresolved)
        )
        lines.append("")
    return lines


def _thresholds_section(thresholds: "list[Threshold] | None") -> list[str]:
    if thresholds is None:
        return []
    lines = ["## Reversal thresholds", ""]
    if not thresholds:
        lines.append("_No threshold scan was requested or none applied to this ledger._")
        lines.append("")
        return lines
    lines.append("| variable | baseline | range | crossing (P=0.5) | P at low | P at high | note |")
    lines.append("|---|---|---|---|---|---|---|")
    for t in thresholds:
        crossing = _fmt(t.crossing) if t.crossing is not None else "none in range"
        lines.append(
            f"| {t.label} | {_fmt(t.baseline)} | [{_fmt(t.low)}, {_fmt(t.high)}] | {crossing} | "
            f"{_fmt(t.p_at_low, 3)} | {_fmt(t.p_at_high, 3)} | {t.message} |"
        )
    lines.append("")
    return lines


def render_report(
    comparison: "Comparison",
    thresholds: "list[Threshold] | None",
    ledger_path: str,
    bounded: "BoundedVerdict | None" = None,
) -> str:
    """Render the full Markdown comparison report (spec section 9).

    Section order is binding: (1) the not-ISO-14067 notice, (2) the full
    applied assumptions, (3) factor table versions/hashes, (4) the
    provenance breakdown — *then* a warning block if warranted, *then* the
    conclusion as a ranking-plus-probability. Everything after that
    (absolute totals, material/role tables, thresholds) is supporting body.
    """
    a, b = comparison.a, comparison.b
    lines: list[str] = []
    lines.append(f"# carbonroute comparison: {a.label} vs {b.label}")
    lines.append("")
    lines.append(f"> {_NOT_ISO_NOTICE}")
    lines.append("")
    lines.append(f"Ledger: `{ledger_path}`")
    lines.append("")

    lines.append("## Applied assumptions")
    lines.append("")
    lines.append("```yaml")
    lines.append(_yaml_block(comparison.assumptions).rstrip("\n"))
    lines.append("```")
    lines.append("")

    lines.extend(_factor_table_section(comparison))
    lines.extend(render_conflicts(comparison.factor_conflicts))
    lines.extend(_provenance_breakdown(comparison))
    lines.extend(_warning_block(comparison))
    lines.extend(_conclusion(comparison, thresholds))

    lines.append("---")
    lines.append("")
    lines.append("## Route totals and contributions (indicative detail)")
    lines.append("")
    lines.extend(_route_body(a))
    lines.extend(_route_body(b))
    lines.extend(_delta_table(comparison))
    lines.extend(_thresholds_section(thresholds))
    lines.extend(render_bounded_verdict(bounded))

    return "\n".join(lines).rstrip("\n") + "\n"


def render_bounded_verdict(verdict: "BoundedVerdict | None") -> list[str]:
    """Render the bounds section: can the ranking be settled without values?

    Kept visually and textually separate from the Monte Carlo conclusion
    above it, because it answers a different question on different evidence.
    Nothing here is a factor; see `carbonroute.bounds` and `docs/bounds.md`.
    """
    if verdict is None:
        return []

    lines = ["## Verdict from bounds", ""]
    lines.append(
        "This section asks a different question from the conclusion above: not "
        "*what* the missing factors are, but whether the ranking is the same "
        "everywhere they could be. Bounds are assertions about where a value "
        "cannot be. **They are not factors** — none of them entered the Monte "
        "Carlo, contributed to any total, or changed the coverage figure."
    )
    lines.append("")

    if verdict.decisive:
        lower = verdict.b_name if verdict.verdict == "b_lower" else verdict.a_name
        higher = verdict.a_name if verdict.verdict == "b_lower" else verdict.b_name
        lines.append(
            f"**Decided: `{lower}` is lower than `{higher}` everywhere in the "
            "asserted bounds.**"
        )
    else:
        lines.append("**Not decided:** the difference changes sign inside the asserted bounds.")
    lines.append("")
    lines.append(verdict.note)
    lines.append("")
    lines.append(
        f"Resolved part of the difference: {_fmt(verdict.resolved_delta_kgCO2e)} kgCO2e/FU. "
        f"Bounded materials: {len(verdict.bounded_keys)}; "
        f"unbounded above: {len(verdict.unbounded_above_keys)}; "
        f"no bound supplied: {len(verdict.missing_bound_keys)}."
    )
    lines.append("")

    lines.append("### What each unresolved material would have to be")
    lines.append("")
    lines.append(
        "Each row holds every *other* unresolved material at its least "
        "favourable admissible value, so a material that clears its own "
        "threshold settles the comparison on its own."
    )
    lines.append("")
    lines.append("| material | delta_mass kg/FU | needs to be | asserted bound | clears it |")
    lines.append("|---|---|---|---|---|")
    for c in verdict.critical:
        if c.status == "always":
            needs = "any value — cannot flip it"
        elif c.status == "unbounded":
            needs = "not computable (another material has no ceiling)"
        else:
            assert c.threshold_kgCO2e_per_kg is not None
            needs = f"{c.direction} {_fmt(c.threshold_kgCO2e_per_kg)} kgCO2e/kg"
        if c.bound is None:
            bound_txt = "—"
        else:
            hi = "unbounded" if c.bound.high is None else _fmt(c.bound.high)
            bound_txt = f"[{_fmt(c.bound.low)}, {hi}]"
        clears = {True: "yes", False: "**no**", None: "—"}[c.cleared_by_bound]
        lines.append(
            f"| {c.name} | {_fmt(c.delta_mass_kg)} | {needs} | {bound_txt} | {clears} |"
        )
    lines.append("")

    bounded_with_sources = [c for c in verdict.critical if c.bound is not None]
    if bounded_with_sources:
        lines.append("### Where each bound comes from")
        lines.append("")
        for c in bounded_with_sources:
            assert c.bound is not None
            lines.append(f"**{c.name}** (`{c.key}`)")
            lines.append("")
            lines.append(f"- {c.bound.rationale}")
            for src in c.bound.sources:
                lines.append(f"- Source: {src}")
            lines.append("")

    lines.append(
        "> A result from bounds is conditional on the bounds. If you disagree "
        "with one, the threshold column above is the whole argument: change the "
        "bound, and the verdict follows from the same arithmetic."
    )
    lines.append("")
    return lines


def render_resolution_table(routes: "dict[str, RouteResult]", table: "FactorTable", show_missing: bool) -> str:
    """Render the ``resolve`` command's report: what resolved, what did not."""
    lines: list[str] = ["# Factor resolution", ""]
    lines.append(f"Factor tables loaded: {len(table.sources)}; fingerprint `{table.fingerprint()}`")
    lines.append("")
    for path, digest in sorted(table.sources.items()):
        lines.append(f"- `{path}` sha256:`{digest}`")
    lines.append("")

    for name, rr in routes.items():
        resolved = [m for m in rr.materials if m.factor is not None]
        missing = [m for m in rr.materials if m.factor is None]
        lines.append(f"## {name} ({rr.label})")
        lines.append("")
        lines.append(f"Resolved {len(resolved)}/{len(rr.materials)} material(s).")
        lines.append("")
        if resolved:
            lines.append("| key | name | role | mass_kg/FU | gwp kgCO2e/kg | source | uncertainty_class |")
            lines.append("|---|---|---|---|---|---|---|")
            for m in resolved:
                assert m.factor is not None
                lines.append(
                    f"| `{m.key}` | {m.name} | {m.role} | {_fmt(m.mass_kg)} | "
                    f"{_fmt(m.factor.gwp_kgCO2e_per_kg)} | {m.factor.source} | "
                    f"{m.factor.uncertainty_class} |"
                )
            lines.append("")
        if missing:
            lines.append(
                f"**Missing ({len(missing)}):** "
                + ", ".join(f"`{m.key}` ({m.name})" for m in sorted(missing, key=lambda x: x.key))
            )
            lines.append("")
            if show_missing:
                lines.append("| key | name | role | mass_kg/FU |")
                lines.append("|---|---|---|---|")
                for m in sorted(missing, key=lambda x: x.key):
                    lines.append(f"| `{m.key}` | {m.name} | {m.role} | {_fmt(m.mass_kg)} |")
                lines.append("")
        else:
            lines.append("No missing factors.")
            lines.append("")

    return "\n".join(lines).rstrip("\n") + "\n"


def _sha256_file(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build_lock(
    ledger: "Ledger",
    ledger_path: str,
    table: "FactorTable",
    resolutions: "dict[str, Resolution]",
    comparison: "Comparison | None" = None,
) -> dict:
    """Build the JSON-serialisable lock payload (spec sections 8, 9, 13).

    Pins everything needed to reproduce a resolution/comparison byte-for-byte:
    ledger contents, factor table contents, the uncertainty config, the
    resolved value+provenance for every material key, and the RNG
    seed/iteration count. Does not itself run any computation; it only
    hashes and restates what was already computed.
    """
    # The uncertainty config path/hash is required by spec but not carried on
    # Comparison; load the default config here so it is always represented,
    # even for a `lock` that did not run a comparison. A caller who resolved
    # against a --uncertainty override would need that override reflected by
    # passing a Comparison through (its RNG seed/iterations are taken from
    # `comparison.stats` below); the config file itself is still the default
    # unless the CLI is extended to thread an override through.
    from .uncertainty import load_uncertainty  # local import: keeps report.py decoupled

    uncertainty_model = load_uncertainty()

    resolved_payload = {}
    for key in sorted(resolutions):
        res = resolutions[key]
        if res.factor is None:
            resolved_payload[key] = {"resolved": False, "matched_by": None}
        else:
            f = res.factor
            resolved_payload[key] = {
                "resolved": True,
                "matched_by": res.matched_by,
                "gwp_kgCO2e_per_kg": f.gwp_kgCO2e_per_kg,
                "uncertainty_class": f.uncertainty_class,
                "source": f.source,
                "database_version": f.database_version,
                "table": _portable_path(f.table),
                "is_illustrative": f.is_illustrative,
            }

    if comparison is not None:
        rng = {"seed": comparison.stats.seed, "iterations": comparison.stats.iterations}
        comparison_payload: dict[str, Any] | None = {
            "a": comparison.a.name,
            "b": comparison.b.name,
            "verdict": comparison.stats.verdict,
            "p_a_lower": comparison.stats.p_a_lower,
            "delta_median_kgCO2e": comparison.stats.delta_median,
        }
    else:
        mc = ledger.assumptions.monte_carlo
        rng = {"seed": mc.seed, "iterations": mc.iterations}
        comparison_payload = None

    return {
        "schema_version": ledger.schema_version,
        "tool_version": _tool_version(),
        "ledger": {"path": _portable_path(ledger_path), "sha256": _sha256_file(ledger_path)},
        "factor_tables": {
            "sources": {_portable_path(p): d for p, d in sorted(table.sources.items())},
            "fingerprint": table.fingerprint(),
            # Which source won a disagreement changes the numbers, so it is
            # pinned alongside the tables themselves.
            "conflicts": [
                {
                    "key": c.key,
                    "used": {
                        "gwp_kgCO2e_per_kg": c.kept.gwp_kgCO2e_per_kg,
                        "source": c.kept.source,
                        "table": _portable_path(c.kept.table),
                    },
                    "not_used": {
                        "gwp_kgCO2e_per_kg": c.rejected.gwp_kgCO2e_per_kg,
                        "source": c.rejected.source,
                        "table": _portable_path(c.rejected.table),
                    },
                }
                for c in sorted(table.conflicts, key=lambda c: c.key)
            ],
        },
        "uncertainty_config": {
            "path": _portable_path(uncertainty_model.path),
            "sha256": _sha256_file(uncertainty_model.path),
        },
        "resolutions": resolved_payload,
        "rng": rng,
        "comparison": comparison_payload,
    }


def _portable_path(path: str) -> str:
    """Path as it should appear in a lock file.

    A lock file is meant to travel with a paper or a report, so an absolute
    path from whoever happened to run the tool is noise at best and a privacy
    leak at worst. Paths under the working directory become relative; anything
    else (a packaged default, a table elsewhere on disk) is reduced to its file
    name. The accompanying sha256 is what actually pins the content.
    """
    p = Path(path)
    try:
        return str(p.resolve().relative_to(Path.cwd().resolve()))
    except ValueError:
        return p.name


def _fmt_probability(p: float, iterations: int) -> str:
    """Render a sampled probability without claiming more than sampling gives.

    A Monte Carlo estimate that lands on 0 or 1 means "no draw fell the other
    way in this many draws", not certainty, so those cases are reported as a
    bound at the resolution the draw count actually supports.
    """
    resolution = 1.0 / max(iterations, 1)
    if p >= 1.0 - resolution:
        return f"> {1.0 - resolution:.4g}"
    if p <= resolution:
        return f"< {resolution:.4g}"
    return f"= {p:.3f}"


def _tool_version() -> str:
    from . import __version__

    return __version__


def dump_lock_json(lock: dict) -> str:
    """Deterministic JSON rendering for the ``lock`` command (spec section 8)."""
    return json.dumps(lock, sort_keys=True, indent=2) + "\n"


def render_coverage(cov, a_name: str, b_name: str, table: "FactorTable") -> str:
    """Render the coverage of a delta set (spec section 14's last open item)."""
    lines = [
        f"# Factor coverage of the delta set: `{a_name}` vs `{b_name}`",
        "",
        f"Factor tables loaded: {len(table.sources)}; "
        f"fingerprint `{table.fingerprint()}`",
        "",
        f"- Materials whose adjusted mass differs between the routes: **{cov.delta_material_count}**",
        f"- Resolved to a factor: **{cov.resolved_count}** "
        f"({cov.count_fraction * 100:.1f}% by count)",
        f"- Share of the absolute delta mass that is resolved: "
        f"**{cov.mass_fraction * 100:.1f}%** "
        f"({_fmt(cov.resolved_mass_kg)} of {_fmt(cov.delta_mass_kg)} kg/FU)",
        "",
        "> Mass coverage is not impact coverage. A catalyst charged at a fraction of a",
        "> percent by mass can dominate a route's footprint, and no mass-based measure",
        "> will show it. Read the per-role table below before treating a high",
        "> percentage as reassurance.",
        "",
        "| role | resolved kg/FU | delta kg/FU | resolved share |",
        "|---|---|---|---|",
    ]
    for role, (resolved, total) in cov.by_role.items():
        share = f"{resolved / total * 100:.1f}%" if total else "n/a"
        lines.append(f"| {role} | {_fmt(resolved)} | {_fmt(total)} | {share} |")
    lines.append("")

    if cov.unresolved:
        lines.append("## Unresolved materials in the delta set")
        lines.append("")
        lines.append("Largest first. Each of these is a gap in the comparison, not a zero.")
        lines.append("")
        lines.append("| material | role | delta mass kg/FU | key |")
        lines.append("|---|---|---|---|")
        for key, name, role, mass in cov.unresolved:
            lines.append(f"| {name} | {role} | {_fmt(mass)} | `{key}` |")
        lines.append("")
    else:
        lines.append("Every material in the delta set resolved to a factor.")
        lines.append("")
    return "\n".join(lines)


def render_conflicts(conflicts) -> list[str]:
    """Substances the loaded tables disagree about.

    Not an error and not a footnote. Two independent public sources differing
    about the same material measures how far apart openly available data sits,
    which is one of the things this project set out to find out. The first table
    in sorted path order supplies the value used; both are shown.
    """
    if not conflicts:
        return []
    lines = [
        "## Sources disagree",
        "",
        f"{len(conflicts)} substance(s) appear in more than one loaded table with "
        "different values. The value used is the one from the first table in sorted "
        "path order; the alternative is shown so the spread is visible.",
        "",
        "| substance | used | from | alternative | from | ratio |",
        "|---|---|---|---|---|---|",
    ]
    for c in sorted(conflicts, key=lambda c: c.key):
        lines.append(
            f"| {c.kept.name} (`{c.key}`) | {_fmt(c.kept.gwp_kgCO2e_per_kg)} | "
            f"{c.kept.source} | {_fmt(c.rejected.gwp_kgCO2e_per_kg)} | "
            f"{c.rejected.source} | {c.ratio:.2f}x |"
        )
    lines.append("")
    return lines


def render_fair_fight(curve: list, template) -> str:
    """Both routes' effort dials moved together, and the caveat that decides it.

    Sweeping the chemical route's solvent recovery against an enzymatic route
    stuck at single-use cofactor compares an optimised process with an
    unoptimised one. This moves both: at each effort the chemical side
    recovers that share of its solvent and the enzymatic side regenerates
    that share of its cofactor, paying its regeneration co-substrate in full.
    """
    lines = [
        "## Fair fight: both routes optimised to the same degree",
        "",
        "At each effort the chemical route recovers that share of its solvent "
        "and the enzymatic route regenerates that share of its cofactor — the "
        "same engineering ambition pointed at each route's own dominant "
        "burden. The regeneration co-substrate is charged in full at every "
        "turnover, so recycling is not a free lunch.",
        "",
        "| effort | cofactor turnovers | enzyme lower | chemistry lower | undecided |",
        "|---|---|---|---|---|",
    ]
    for p in curve:
        ttn = "1" if p.effort >= 1.0 or p.effort == 0.0 else f"{1 / (1 - p.effort):.0f}"
        lines.append(
            f"| {p.effort * 100:.0f}% | {ttn} | {p.enzyme_wins} | "
            f"{p.chemistry_wins} | {p.undecided} |"
        )
    lines.append("")

    solvents = [m for m in template.materials if m.role == "solvent"]
    if solvents:
        worst = max(solvents, key=lambda m: m.kg_per_mol_product)
        lines.append(
            f"**Read this against the template's largest solvent term.** "
            f"{worst.name} is charged at {worst.kg_per_mol_product:.1f} kg per "
            "mole of product, and it dominates the chemical side at every "
            "effort above. Recovery only ever divides that number; it cannot "
            "un-choose it. A chemical process that were *itself* serious about "
            "solvent would not recover 99% of a bench isolation, it would "
            "replace the isolation — crystallise, use an antisolvent, run the "
            "extraction continuously. Solvent recovery and solvent avoidance "
            "are different levers and this template can only model the first, "
            "so a sweep like the one above puts a genuinely solvent-lean "
            "enzymatic route against a chemical route that is merely tidying "
            "up after a wasteful one. Until the class carries a template built "
            "from a solvent-lean published procedure, read the table as an "
            "upper bound on the enzymatic advantage, not as a fair fight."
        )
        lines.append("")
    return "\n".join(lines)


def _render_what_it_rests_on(run: "ScreenRun", bounds) -> list[str]:
    """Say which numbers the verdicts are actually made of.

    This project is scrupulous about where every value came from and was,
    until this section existed, silent about which of them the answer rests
    on. Those are different questions, and the second is the one that has
    repeatedly gone wrong here: every result this repository has had to
    withdraw shared one signature -- a single term dominated the delta while
    its value came from an assumption rather than a measurement.
    """
    from .screen import explain_verdict

    lines = ["## What these verdicts are made of", ""]
    explained = [
        (r, explain_verdict(r.standard_diff, bounds))
        for r in run.decided
        if r.standard_diff is not None
    ]
    if not explained:
        lines.append("No decided reaction carries a delta set to explain.")
        lines.append("")
        return lines

    lines.append(
        "Provenance says where a number came from. It cannot say how much of "
        "the answer that number carries, and a heroically-sourced figure "
        "worth 0.1% of the delta looks identical to a casually-looked-up one "
        "worth 80%. This section separates them. Each material is valued at "
        "whichever end of its interval is *least* favourable to the verdict, "
        "the same convention the guaranteed saving uses."
    )
    lines.append("")

    concentrations = sorted(e.concentration for _, e in explained)
    med = concentrations[len(concentrations) // 2]
    dominated = sum(1 for c in concentrations if c >= 0.5)
    counter: Counter[str] = Counter()
    for _, e in explained:
        if e.top is not None:
            counter[e.top.name] += 1
    lines.append(
        f"**In {dominated} of {len(explained)} decided reactions, one single "
        f"material carries at least half the delta** (median concentration "
        f"{med * 100:.0f}%). "
        + (
            "The same material is the largest term in "
            f"{counter.most_common(1)[0][1]} of them: "
            f"**{counter.most_common(1)[0][0]}**. "
            if counter
            else ""
        )
        + "A concentrated verdict is not wrong, but it means something "
        "narrower than it looks: it is mostly a statement about one "
        "material's quantity, and the template that sets that quantity."
    )
    lines.append("")

    measured = sum(e.measured_share for _, e in explained) / len(explained)
    bounded = sum(e.bounded_share for _, e in explained) / len(explained)
    unbounded = sum(e.unbounded_share for _, e in explained) / len(explained)
    lines.append(
        f"Averaged over those reactions, {measured * 100:.0f}% of the delta "
        f"rests on measured factors, {bounded * 100:.0f}% on asserted bounds "
        f"and {unbounded * 100:.0f}% on materials with no ceiling asserted."
    )
    lines.append("")

    ex, exp = max(explained, key=lambda pair: pair[1].concentration)
    lines.append(
        f"The most concentrated example is `{ex.rhea_id}` "
        f"({exp.concentration * 100:.0f}% on one term):"
    )
    lines.append("")
    lines.append("| material | side | kg/kg product | value used | share | evidence |")
    lines.append("|---|---|---|---|---|---|")
    for c in exp.contributions[:8]:
        v = "—" if c.value_kgCO2e_per_kg is None else f"{c.value_kgCO2e_per_kg:.3f}"
        lines.append(
            f"| {c.name[:46]} | {c.side} | {c.mass_kg:.3f} | {v} | "
            f"{c.share * 100:.1f}% | {c.evidence} |"
        )
    lines.append("")
    return lines


def _render_ranking(run: "ScreenRun") -> list[str]:
    """Rank reactions on the one quantity that means the same in every class.

    A recovery threshold is stated against the solvent load of one template,
    so 86% in a glycosylation class and 86% in a methylation class are not
    the same claim and cannot be put in one list. Kilograms of CO2e saved per
    kilogram of product can, provided every class is read at the same
    operating point.
    """
    from .screen import rank_by_advantage

    lines: list[str] = []
    rec = run.reference_recovery * 100
    lines.append("## Ranked by saving, the way classes can be compared")
    lines.append("")
    if not run.decided:
        lines.append("No reaction in this class was decided, so there is nothing to rank.")
        lines.append("")
        return lines

    ranked = rank_by_advantage(run.decided)
    guaranteed = [r for r in run.decided if r.advantage_decided]
    lines.append(
        "The recovery threshold above cannot be compared between classes: it "
        "is measured against whatever solvent load that class's template "
        "happens to carry. This column can be. It is the enzymatic route's "
        "advantage in **kg CO₂e per kg of product**, read at the standard "
        f"operating point of {rec:.0f}% solvent recovery and "
        f"{run.enzymatic_yield * 100:.0f}% enzymatic conversion — the same "
        "statement whatever the reaction makes."
    )
    lines.append("")
    lines.append(
        f"**{len(guaranteed)} of {len(run.decided)} reactions have a "
        f"guaranteed saving at {rec:.0f}% recovery** — an advantage interval "
        "lying entirely on one side of zero. For the rest the interval "
        "straddles zero, which is not a small advantage but an absent verdict."
    )
    lines.append("")

    determinate = sum(1 for x in ranked if x.determinate)
    unbounded: tuple[str, ...] = ()
    for r in run.decided:
        if r.verdict is not None and r.verdict.unbounded_above_keys:
            unbounded = r.verdict.unbounded_above_keys
            break
    if determinate == 0 and unbounded:
        lines.append(
            "**No two reactions here can be strictly ordered, and the reason "
            "is nameable.** A reaction outranks another only when its worst "
            "case still beats the other's best case. "
            f"{len(unbounded)} materials on the chemical side carry no "
            "asserted ceiling (`high: null`) — "
            + ", ".join(f"`{k}`" for k in unbounded)
            + " — so every reaction's advantage is unbounded above and every "
            "rank range spans the whole class. That is a statement about the "
            "bounds file, not about the chemistry: putting a defensible "
            "ceiling on those four is what would make this ranking bite."
        )
        lines.append("")
        lines.append(
            "What survives is the **guaranteed floor**: the saving that holds "
            "everywhere in the asserted bounds. Ordering on it is exact — it "
            "is a computed bound, not an estimate — but it ranks the floor, "
            "not the true saving."
        )
    else:
        lines.append(
            f"{determinate} of {len(ranked)} reactions have a rank that does "
            "not move as the others range over their own intervals. A wide "
            "rank range is the honest report that these reactions are not "
            "ordered by the data."
        )
    lines.append("")
    lines.append("| rank | guaranteed saving | rank range | groups | product |")
    lines.append("|---|---|---|---|---|")
    for i, x in enumerate(ranked[:20], 1):
        r = x.result
        floor = r.advantage_min_kgCO2e
        floor_s = "unbounded below" if floor is None else f"{floor:+.2f}"
        ceiling = "∞" if r.advantage_max_kgCO2e is None else f"{r.advantage_max_kgCO2e:.2f}"
        lines.append(
            f"| {i} | {floor_s} … {ceiling} | {x.best_rank}–{x.worst_rank} | "
            f"{r.protectable_groups} | {r.product_name[:60]} |"
        )
    lines.append("")
    return lines


def render_screen(run: "ScreenRun", reaction_source: str, bounds=None) -> str:
    """Render a database screen: a ranked shortlist, not a set of verdicts.

    The headline is deliberately not "how many reactions the enzyme wins".
    A class template is instantiated from a published bench procedure, and
    bench procedures discard their solvent, so a zero-recovery verdict is
    mostly a statement about laboratory glassware. The number that survives
    that objection -- and therefore the number this report leads with -- is
    the solvent recovery rate at which each verdict stops holding.
    """
    t = run.template
    lines: list[str] = [f"# carbonroute screen: {t.name}", ""]
    lines.append(f"> {_NOT_ISO_NOTICE}")
    lines.append("")
    lines.append(
        "> **This is a screen, not a comparison.** Each row pairs one curated "
        "enzymatic reaction against a *class template*: a single real published "
        "chemical procedure applied to every substrate in the class. That "
        "extrapolation is the method's central assumption. Read the output as a "
        "ranked shortlist of reactions worth spending a real `carbonroute "
        "compare` on — never as a verdict about any individual reaction."
    )
    lines.append("")
    lines.append(f"Reactions: `{reaction_source}`")
    lines.append(f"Class template: `{t.id}`")
    lines.append(f"Enzymatic conversion assumed: **{run.enzymatic_yield * 100:.0f}%**")
    if t.source_overall_yield is not None:
        lines.append(
            f"Chemical conversion, from the source procedure: "
            f"**{t.source_overall_yield * 100:.1f}%** (already folded into the "
            "template's per-mole-of-product amounts)"
        )
    lines.append("")
    if run.enzymatic_yield >= 1.0:
        chem_basis = (
            "declared at process-model stage yields, which are stated "
            "assumptions rather than a paper's real losses"
            if run.use_process_model
            else (
                "stated per mole of *product*, so they already carry the "
                "source paper's own yield"
            )
        )
        lines.append(
            "> **The enzymatic side is billed at 100% conversion, and that "
            f"favours it.** This template's chemical amounts are {chem_basis}; "
            "an enzymatic route charged pure stoichiometry pays no equivalent "
            "penalty. Every threshold below is therefore an upper bound. Re-run "
            "with `--enzymatic-yield` to price a real conversion."
        )
        lines.append("")
    if run.use_process_model:
        lines.append(
            "> **Screened against the declared `process_model`, not a cited "
            "paper.** Every chemical-side amount below is `generalised` by "
            "construction: reagents at stated equivalents, solvent from a "
            "stated reaction concentration. See docs/screening.md, \"A "
            "declared process, instead of one paper's bench run\"."
        )
        lines.append("")
    if t.unpriced_co_cofactor_chebi:
        lines.append(
            "> **This class's reactions consume a second cofactor that is "
            "NOT priced.** "
            f"({', '.join(t.unpriced_co_cofactor_chebi)}, excluded from the "
            "acceptor search but never charged as a material.) Its real "
            "regeneration cost is a stated, deliberate gap, not an invented "
            "zero — every enzymatic-side figure below is UNDERSTATED by "
            "whatever that cofactor actually costs, the same direction "
            "every other unpriced gap in this project understates it."
        )
        lines.append("")
    lines.append(f"**Chemical counterpart modelled:** {t.chemical_name}")
    lines.append("")
    lines.append(f"> {t.chemical_source.strip()}")
    lines.append("")
    if t.assumptions_note:
        lines.append("**Stated simplifications**")
        lines.append("")
        lines.append(f"> {t.assumptions_note.strip()}")
        lines.append("")

    sourced = sum(1 for m in t.materials if m.basis == "sourced")
    generalised = sum(1 for m in t.materials if m.basis == "generalised")
    lines.append(
        f"Template materials: {len(t.materials)} "
        f"({sourced} sourced from the cited paper, {generalised} generalised beyond it)."
    )
    lines.append("")

    lines.append("## What was screened")
    lines.append("")
    lines.append(f"- Reactions matching this class: **{run.matched}**")
    lines.append(f"- Screened to a verdict: **{len(run.decided) + len(run.undecided)}**")
    lines.append(f"- Could not be screened: **{len(run.unscreened)}**")
    if run.unscreened:
        reasons: dict[str, int] = defaultdict(int)
        for r in run.unscreened:
            reasons[r.skipped_reason] += 1
        for reason, n in sorted(reasons.items(), key=lambda kv: -kv[1]):
            lines.append(f"  - {n} — {reason}")
    lines.append("")

    thresholds = sorted(
        r.recovery_threshold for r in run.decided if r.recovery_threshold is not None
    )
    lines.append("## The number that matters: solvent recovery threshold")
    lines.append("")
    if not thresholds:
        lines.append("No reaction in this class was decided, so there is no threshold to report.")
        lines.append("")
        return "\n".join(lines).rstrip("\n") + "\n"

    lines.append(
        "At what chemical-route solvent recovery rate does each verdict stop "
        "holding? Below its threshold the enzymatic route is lower everywhere "
        "in the asserted bounds; above it, the comparison is no longer decided."
    )
    lines.append("")
    lines.append("| statistic | recovery threshold |")
    lines.append("|---|---|")
    for label, q in (("minimum", 0.0), ("25th pct", 0.25), ("median", 0.5), ("75th pct", 0.75), ("maximum", 1.0)):
        idx = min(int(q * (len(thresholds) - 1)), len(thresholds) - 1)
        lines.append(f"| {label} | {thresholds[idx] * 100:.2f}% |")
    lines.append("")
    robust = [r for r in run.results if r.robust]
    lines.append(
        f"**{len(robust)} of {len(run.decided)} decided reactions survive 99% solvent "
        "recovery.** Industrial distillation routinely recovers 90–95%, so a class "
        "whose thresholds sit below that is one where the modelled advantage comes "
        "substantially from the bench procedure's solvent handling rather than from "
        "the enzyme."
    )
    lines.append("")

    lines.append(
        f"## How good the enzyme has to be, at {run.reference_recovery * 100:.0f}% "
        "solvent recovery"
    )
    lines.append("")
    lines.append(
        "The threshold above sweeps the chemical plant's solvent recovery at one "
        "fixed enzymatic conversion. This sweeps the other axis instead, and it "
        "sweeps the whole of it — from a perfect enzyme downwards, independent "
        "of the conversion the rest of this report was run at. With the plant "
        f"recovering the {run.reference_recovery * 100:.0f}% a real distillation "
        "achieves, what is the lowest conversion at which the enzymatic verdict "
        "still holds?"
    )
    lines.append("")
    needs = sorted(
        r.min_enzymatic_yield for r in run.decided if r.min_enzymatic_yield is not None
    )
    stranded = len(run.decided) - len(needs)
    if not needs:
        lines.append(
            f"**No reaction in this class holds its verdict at "
            f"{run.reference_recovery * 100:.0f}% solvent recovery, at any "
            "conversion.** The advantage this class shows at zero recovery does "
            "not survive an industrial solvent loop, so there is no conversion "
            "requirement to report — the question stops being about the enzyme."
        )
    else:
        lines.append("| statistic | minimum conversion required |")
        lines.append("|---|---|")
        for label, q in (("minimum", 0.0), ("median", 0.5), ("maximum", 1.0)):
            idx = min(int(q * (len(needs) - 1)), len(needs) - 1)
            lines.append(f"| {label} | {needs[idx] * 100:.1f}% |")
        lines.append("")
        lines.append(
            f"**{len(needs)} of {len(run.decided)} decided reactions are still "
            f"decided at {run.reference_recovery * 100:.0f}% recovery**, and they "
            f"need the conversions above to stay that way. The other {stranded} "
            "lose their verdict at this recovery rate however well the enzyme "
            "performs."
        )
    lines.append("")

    lines.extend(_render_what_it_rests_on(run, bounds))
    lines.extend(_render_ranking(run))

    lines.append("## Most robust in this class")
    lines.append("")
    lines.append(
        "Ranked by recovery threshold. A higher threshold means the enzymatic "
        "advantage survives more solvent recycling on the chemical side. "
        "`groups` is the count of protectable groups on the acceptor — the sites "
        "a chemical route must mask and an enzyme does not."
    )
    lines.append("")
    lines.append("| rhea | threshold | groups | product |")
    lines.append("|---|---|---|---|")
    ranked = sorted(run.decided, key=lambda r: -(r.recovery_threshold or 0.0))
    for r in ranked[:20]:
        lines.append(
            f"| `{r.rhea_id}` | {(r.recovery_threshold or 0) * 100:.2f}% | "
            f"{r.protectable_groups} | {r.product_name[:70]} |"
        )
    lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"
