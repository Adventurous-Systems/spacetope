"""M21 orientation pass: turn or mirror a finished plan so more rooms face the side they asked for (PLAN §4.10).

The eight symmetries of the rectangle are applied to a whole placement at once (every level with one transform, z
untouched, moved back to the origin). A placement is a plain name -> `Box` dict and a shaft or a legacy stack is just
more boxes in it, so the transform covers everything a placement carries. Only the compass side each wall faces
changes; door pairs and every score except `affinity` stay equal (checked by the M21 gate).

Mirroring is valid ONLY while doors have no hinge and stairs no run direction. If either ever becomes a stored
property, a mirror image is a different building and `SYMMETRIES` must drop the four mirrored entries.
Pure Python, no kernel.
"""
from __future__ import annotations

from . import affinity
from .brief import Brief
from .placement import Placement
from .solve.grid import Box, bounds
from .units import to_mm

NAMES = ("id", "r90", "r180", "r270", "mx", "mx_r90", "mx_r180", "mx_r270")


def _origin(pl: Placement) -> Placement:
    bb = bounds(pl.values())
    return {n: Box(b.x - bb.x, b.y - bb.y, b.z, b.w, b.l, b.h) for n, b in pl.items()}


def _turn(pl: Placement) -> Placement:
    """A quarter turn counter-clockwise about the plan's bounding box, kept at the origin."""
    top = bounds(pl.values()).y1
    return {n: Box(top - b.y1, b.x, b.z, b.l, b.w, b.h) for n, b in pl.items()}


def _mirror(pl: Placement) -> Placement:
    """x -> -x about the plan's bounding box."""
    right = bounds(pl.values()).x1
    return {n: Box(right - b.x1, b.y, b.z, b.w, b.l, b.h) for n, b in pl.items()}


def symmetries(placement: Placement) -> dict[str, Placement]:
    """All eight, by name; `id` is the placement moved to the origin."""
    base = _origin(placement)
    out: dict[str, Placement] = {}
    for m in (False, True):
        cur = _mirror(base) if m else base
        for k in range(4):
            out[NAMES[4 * m + k]] = cur
            cur = _turn(cur)
    return out


def _fits(brief: Brief, pl: Placement) -> bool:
    if not brief.envelope:
        return True
    bb = bounds(pl.values())
    return bb.x1 <= to_mm(brief.envelope["w"]) and bb.y1 <= to_mm(brief.envelope["l"])


def fitting(brief: Brief, placement: Placement) -> dict[str, Placement]:
    """The symmetries whose bounding box fits the envelope. The original placement is always first, under `id`."""
    out = {"id": placement}
    out.update({n: q for n, q in symmetries(placement).items() if n != "id" and _fits(brief, q)})
    return out


def facade_score(brief: Brief, placement: Placement) -> tuple[int, float]:
    """(hard facade misses, soft facade score) of a placement; the score is 1.0 when no soft facade wish is judged."""
    items = affinity.measure(brief, placement, kinds=("facade",))["items"]
    soft = [i for i in items if i["met"] is not None and i["strength"] not in affinity.HARD]
    weight = sum(i["weight"] for i in soft)
    hits = sum(i["weight"] for i in soft if i["met"])
    return (sum(1 for i in items if i["met"] is False and i["strength"] in affinity.HARD),
            round(hits / weight, 6) if weight else 1.0)


def wants_facade(brief: Brief) -> bool:
    return any(a.kind == "facade" for a in affinity.expand(brief))


def best(brief: Brief, placement: Placement) -> tuple[Placement, dict]:
    """The fitting symmetry with the fewest hard facade misses, then the highest soft facade score; the identity wins
    ties. Returns (placement, {"symmetry", "facade_before", "facade_after"})."""
    cands = fitting(brief, placement)
    marks = {n: facade_score(brief, q) for n, q in cands.items()}
    pick = min(cands, key=lambda n: (marks[n][0], -marks[n][1]))   # min keeps the first of equals, and `id` is first
    return cands[pick], {"symmetry": pick, "facade_before": marks["id"][1], "facade_after": marks[pick][1]}
