"""Deciding a comparison from bounds instead of values.

The problem this solves
-----------------------

`carbonroute compare` refuses to rank two routes when too little of the
differing mass resolves to a factor. That refusal is correct as a default:
a ranking computed from half the mass is a ranking about half the mass.

But it throws away a real asymmetry. Ranking two routes is a strictly
easier question than measuring either one, and it stays easier when the
data is bad. You do not need to know what an unresolved material's factor
*is*; you only need to know enough about where it *cannot* be for the
answer to stop depending on it.

That is what this module computes. Given, for each unresolved material, an
interval its true factor is asserted to lie in, it asks whether the verdict
is the same everywhere in that box. If it is, the verdict is established
for every assignment the bounds permit -- including the true one, whatever
it turns out to be.

Why the arithmetic is exact
---------------------------

The signed difference between two routes is linear in every factor::

    delta = resolved_delta + sum_i (delta_mass_i * f_i)

so over a box of intervals its extremes sit at corners, and because each
term's sign is fixed by the sign of `delta_mass_i`, the extreme corner is
known without search:

- to make `delta` as large as possible: take `high` where `delta_mass_i > 0`
  and `low` where `delta_mass_i < 0`
- to make it as small as possible: the other way round

Two evaluations settle it. There is no optimisation, no sampling, and no
approximation: the reported worst cases *are* the worst cases.

What a bound is, and what it is not
-----------------------------------

A bound is not a factor. It never enters the Monte Carlo, never contributes
to an indicative total, never lands in a factor table, and never turns an
unresolved material into a resolved one. Coverage is reported exactly as
before. A bound is only ever used to answer one question -- "does the
verdict survive everywhere in here?" -- and the answer is reported together
with the box it was proved over, because a proof over the wrong box is
worth nothing.

This is what lets genuinely poor data be used honestly. Two published
estimates for the same substance that disagree by a factor of eight cannot
be averaged into a factor anyone should trust. They can, however, bracket
one: the interval spanned by both is a defensible bound precisely *because*
it is wide enough to contain the disagreement. If the verdict holds across
it, the disagreement was never load-bearing, and the comparison can be
settled without settling the argument.

The threshold, when it does not hold
------------------------------------

When a box is too wide to decide, the useful output is not "indeterminate"
again but the inequality that would decide it. For each unresolved material
this module computes the value at which the ranking ties, holding the other
materials at their least favourable admissible values. That converts "we
need data" into "we need to know whether this one number is above 1.36",
which a reader with domain knowledge can often answer immediately, and
which tells anyone gathering data exactly which measurement is worth the
effort.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .compute import DiffResult, resolved_delta_gwp
from .schema import Assumptions


class BoundsError(ValueError):
    """A bounds file could not be read, or asserts something impossible."""


@dataclass(frozen=True)
class Bound:
    """An interval a material's true factor is asserted to lie in.

    `low` is required and must be >= 0 (no cradle-to-gate factor is
    negative in this model). `high` may be None, meaning "not bounded
    above" -- an honest position that leaves one side of the test open
    rather than inventing a ceiling.
    """

    key: str
    low: float
    high: float | None
    rationale: str
    sources: tuple[str, ...]

    @property
    def bounded_above(self) -> bool:
        return self.high is not None


@dataclass(frozen=True)
class CriticalThreshold:
    """The value of one material at which the ranking ties.

    Every other unresolved material is held at the admissible value least
    favourable to the verdict under test, so this is the *hardest* the
    threshold can be -- clearing it settles the comparison regardless of
    where the others fall in their own bounds.
    """

    key: str
    name: str
    delta_mass_kg: float
    threshold_kgCO2e_per_kg: float | None
    direction: str  # "above" | "below" -- which side of the threshold keeps the verdict
    bound: Bound | None
    cleared_by_bound: bool | None  # None when there is no bound to check it against
    status: str = "threshold"
    # "threshold": a positive tie point exists; `threshold_kgCO2e_per_kg` holds it.
    # "always":    no non-negative value of this material can flip the verdict, so
    #              the conclusion does not rest on it at all -- a stronger result
    #              than clearing a threshold, not a failure to find one.
    # "unbounded": another material carries no ceiling, so this material's tie
    #              point is not computable. Bound that one to get this one.


@dataclass(frozen=True)
class BoundedVerdict:
    """The result of asking whether a verdict survives a box of intervals."""

    delta_min_kgCO2e: float | None  # None when unbounded below (only if a bound is missing)
    delta_max_kgCO2e: float | None  # None when some material is unbounded above
    decisive: bool
    verdict: str  # "a_lower" | "b_lower" | "indeterminate"
    a_name: str
    b_name: str
    resolved_delta_kgCO2e: float
    bounded_keys: tuple[str, ...]
    unbounded_above_keys: tuple[str, ...]
    missing_bound_keys: tuple[str, ...]
    critical: tuple[CriticalThreshold, ...]
    note: str


def load_bounds(path: str | Path) -> dict[str, Bound]:
    """Read a bounds file.

    Format::

        bounds:
          "cas:174501-64-5":
            low: 3.5
            high: 27.3
            rationale: "why this interval is defensible"
            sources:
              - "a citation"
              - "another citation"

    `high` may be omitted for "not bounded above". `rationale` is required:
    an interval without a stated reason is exactly the kind of unexplained
    number this project exists to keep out, and it is cheap to demand one
    because a bound that cannot be justified in a sentence should not be
    asserted at all.
    """
    p = Path(path)
    try:
        raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise BoundsError(f"could not read bounds file {p}: {exc}") from exc

    if not isinstance(raw, dict):
        raise BoundsError(f"{p}: top level must be a mapping with a 'bounds:' key")
    entries = raw.get("bounds")
    if not isinstance(entries, dict):
        raise BoundsError(f"{p}: missing or malformed 'bounds:' mapping")

    out: dict[str, Bound] = {}
    for key, spec in entries.items():
        if not isinstance(spec, dict):
            raise BoundsError(f"{p}: bounds entry {key!r} must be a mapping")
        if "low" not in spec:
            raise BoundsError(f"{p}: bounds entry {key!r} has no 'low'")
        low = _as_float(p, key, "low", spec["low"])
        high: float | None = None
        if spec.get("high") is not None:
            high = _as_float(p, key, "high", spec["high"])

        if low < 0.0:
            raise BoundsError(
                f"{p}: bounds entry {key!r} has low={low}; a cradle-to-gate factor "
                "cannot be negative"
            )
        if high is not None and high < low:
            raise BoundsError(f"{p}: bounds entry {key!r} has high={high} below low={low}")

        rationale = spec.get("rationale")
        if not isinstance(rationale, str) or not rationale.strip():
            raise BoundsError(
                f"{p}: bounds entry {key!r} has no 'rationale'. State why this interval "
                "is defensible; an unexplained bound is not usable evidence."
            )

        sources_raw = spec.get("sources") or []
        if isinstance(sources_raw, str):
            sources_raw = [sources_raw]
        if not isinstance(sources_raw, list) or not all(isinstance(s, str) for s in sources_raw):
            raise BoundsError(f"{p}: bounds entry {key!r} has a malformed 'sources' list")

        out[str(key)] = Bound(
            key=str(key),
            low=low,
            high=high,
            rationale=rationale.strip(),
            sources=tuple(sources_raw),
        )
    return out


def _as_float(path: Path, key: str, field: str, value: Any) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError) as exc:
        raise BoundsError(f"{path}: bounds entry {key!r} has non-numeric {field}={value!r}") from exc
    if not math.isfinite(out):
        raise BoundsError(f"{path}: bounds entry {key!r} has non-finite {field}={value!r}")
    return out


def bounded_verdict(
    diff: DiffResult,
    assumptions: Assumptions,
    bounds: dict[str, Bound],
) -> BoundedVerdict:
    """Ask whether the ranking is the same everywhere in the supplied box.

    Returns the extreme values of `GWP_A - GWP_B` over the box, whether they
    share a sign (and so settle the comparison), and -- decisive or not --
    the per-material threshold that would settle it.
    """
    resolved = resolved_delta_gwp(diff, assumptions)
    unresolved_rows = [r for r in diff.rows if not r.resolved]

    bounded: list[str] = []
    unbounded_above: list[str] = []
    missing: list[str] = []

    delta_max: float | None = resolved
    delta_min: float | None = resolved

    for row in unresolved_rows:
        bound = bounds.get(row.key)
        if bound is None:
            missing.append(row.key)
            # A missing bound is still bounded below by zero -- no factor is
            # negative -- so only one side of the test is actually lost.
            lo, hi = 0.0, None
        else:
            bounded.append(row.key)
            lo, hi = bound.low, bound.high
            if hi is None:
                unbounded_above.append(row.key)

        dm = row.delta_mass_kg
        if dm > 0.0:
            # Larger factor pushes delta up.
            if delta_max is not None:
                delta_max = None if hi is None else delta_max + dm * hi
            if delta_min is not None:
                delta_min = delta_min + dm * lo
        else:
            # Larger factor pushes delta down.
            if delta_max is not None:
                delta_max = delta_max + dm * lo
            if delta_min is not None:
                delta_min = None if hi is None else delta_min + dm * hi

    # One side is enough. If the delta cannot get above zero it is negative
    # everywhere in the box, however far below zero the other extreme runs --
    # so a material left unbounded in the direction that only reinforces the
    # conclusion does not block it. This matters in practice: the honest bound
    # on a badly-documented substance is often "at least X, ceiling unknown",
    # and that is frequently all the question needs.
    if delta_max is not None and delta_max < 0.0:
        decisive, verdict = True, "a_lower"
    elif delta_min is not None and delta_min > 0.0:
        decisive, verdict = True, "b_lower"
    else:
        decisive, verdict = False, "indeterminate"

    critical = _critical_thresholds(diff, resolved, unresolved_rows, bounds)
    note = _note(
        decisive, verdict, diff, delta_min, delta_max, unbounded_above, missing
    )

    return BoundedVerdict(
        delta_min_kgCO2e=delta_min,
        delta_max_kgCO2e=delta_max,
        decisive=decisive,
        verdict=verdict,
        a_name=diff.a_name,
        b_name=diff.b_name,
        resolved_delta_kgCO2e=resolved,
        bounded_keys=tuple(bounded),
        unbounded_above_keys=tuple(unbounded_above),
        missing_bound_keys=tuple(missing),
        critical=critical,
        note=note,
    )


def _critical_thresholds(
    diff: DiffResult,
    resolved: float,
    unresolved_rows: list[Any],
    bounds: dict[str, Bound],
) -> tuple[CriticalThreshold, ...]:
    """For each unresolved material: the value at which the ranking ties.

    Every *other* unresolved material is held at the admissible value that
    makes this material's job hardest -- its `low` if it pushes the delta the
    same way, its `high` if the other way -- so a material that clears its
    own threshold settles the comparison on its own.
    """
    out: list[CriticalThreshold] = []

    for row in unresolved_rows:
        dm = row.delta_mass_kg
        if dm == 0.0:
            continue

        # Sum the others at their least favourable admissible values, in the
        # direction that resists whatever sign `resolved` already leans.
        others = 0.0
        unbounded = False
        for other in unresolved_rows:
            if other.key == row.key:
                continue
            b = bounds.get(other.key)
            lo = b.low if b is not None else 0.0
            hi = b.high if b is not None else None
            # Least favourable = pushes delta toward zero-crossing hardest,
            # i.e. maximises the magnitude this material must supply.
            if (other.delta_mass_kg > 0.0) == (dm > 0.0):
                # Same direction as this material: least favourable is its low.
                others += other.delta_mass_kg * lo
            else:
                # Opposite direction: least favourable is its high.
                if hi is None:
                    unbounded = True
                    break
                others += other.delta_mass_kg * hi

        bound = bounds.get(row.key)
        if unbounded:
            out.append(
                CriticalThreshold(
                    key=row.key,
                    name=row.name,
                    delta_mass_kg=dm,
                    threshold_kgCO2e_per_kg=None,
                    direction="above" if dm < 0.0 else "below",
                    bound=bound,
                    cleared_by_bound=None,
                    status="unbounded",
                )
            )
            continue

        # resolved + others + dm * f == 0  ->  f = -(resolved + others) / dm
        threshold = -(resolved + others) / dm
        # If dm < 0, larger f drives delta down (toward "a_lower"): the verdict
        # "a_lower" is kept by f ABOVE the threshold. If dm > 0, the reverse.
        direction = "above" if dm < 0.0 else "below"

        # A tie point at or below zero means no admissible (non-negative) value
        # of this material reaches it: the verdict holds for anything it could
        # be. That is a stronger statement than clearing a threshold, and is
        # reported as such rather than as an absent number.
        if threshold <= 0.0:
            out.append(
                CriticalThreshold(
                    key=row.key,
                    name=row.name,
                    delta_mass_kg=dm,
                    threshold_kgCO2e_per_kg=None,
                    direction=direction,
                    bound=bound,
                    cleared_by_bound=True,
                    status="always",
                )
            )
            continue

        cleared: bool | None = None
        if bound is not None:
            if direction == "above":
                cleared = bound.low >= threshold
            else:
                cleared = bound.high is not None and bound.high <= threshold

        out.append(
            CriticalThreshold(
                key=row.key,
                name=row.name,
                delta_mass_kg=dm,
                threshold_kgCO2e_per_kg=threshold,
                direction=direction,
                bound=bound,
                cleared_by_bound=cleared,
                status="threshold",
            )
        )

    out.sort(key=lambda c: -abs(c.delta_mass_kg))
    return tuple(out)


def _note(
    decisive: bool,
    verdict: str,
    diff: DiffResult,
    delta_min: float | None,
    delta_max: float | None,
    unbounded_above: list[str],
    missing: list[str],
) -> str:
    if decisive:
        lower = diff.b_name if verdict == "b_lower" else diff.a_name
        higher = diff.a_name if verdict == "b_lower" else diff.b_name
        lo = "unbounded" if delta_min is None else f"{delta_min:.4g}"
        hi = "unbounded" if delta_max is None else f"{delta_max:.4g}"
        return (
            f"Over the whole box of asserted bounds, GWP_A - GWP_B stays in "
            f"[{lo}, {hi}] kgCO2e/FU and never changes sign. "
            f"{lower!r} is lower than {higher!r} for every assignment the bounds "
            "permit, so the ranking does not depend on where in those intervals "
            "the true factors fall. It does depend on the bounds themselves being "
            "right: this is a conditional result, and the condition is stated."
        )

    parts = ["The bounds are too wide to settle the ranking: the difference changes sign inside them."]
    if unbounded_above:
        parts.append(
            f"{len(unbounded_above)} material(s) are not bounded above "
            f"({', '.join(sorted(unbounded_above))}), so one extreme is open."
        )
    if missing:
        parts.append(
            f"{len(missing)} unresolved material(s) have no bound at all "
            f"({', '.join(sorted(missing))}); they were treated as [0, unbounded)."
        )
    parts.append("See the per-material thresholds for the inequality that would decide it.")
    return " ".join(parts)
