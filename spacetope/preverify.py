"""Checks that need no geometry kernel, on integer boxes (PLAN M10). Pure Python: the search layer may import this."""
from __future__ import annotations

from .brief import Brief
from .levels import level_height_mm
from .placement import Placement, overlaps


def check_constraints(brief: Brief, placement: Placement) -> tuple[bool, str]:
    """Envelope (AABB from origin) and level count, when the brief states them (M3)."""
    problems = []
    if brief.envelope:
        env = {k: int(round(v * 1000)) for k, v in brief.envelope.items()}
        for name, b in placement.items():
            if b.x < 0 or b.y < 0 or b.z < 0 or b.x1 > env["w"] or b.y1 > env["l"] or b.z1 > env["h"]:
                problems.append(f"{name} leaves envelope")
    if brief.levels is not None:
        zs = sorted({b.z for b in placement.values()})
        if len(zs) != brief.levels:
            problems.append(f"{len(zs)} z-bands, brief asks {brief.levels}")
    H = level_height_mm(brief)
    for s in brief.spaces:
        if s.is_shaft and s.name in placement:
            b = placement[s.name]
            lo, hi = s.serves
            if b.z != lo * H or b.h != (hi - lo + 1) * H:
                problems.append(f"{s.name} should span levels {lo}–{hi} (z {lo * H} mm, height {(hi - lo + 1) * H} mm), "
                                f"got z {b.z} mm, height {b.h} mm")
    return (not problems, "; ".join(problems) or "ok")

def preverify(brief: Brief, placement: Placement) -> tuple[bool, dict[str, tuple[bool, str]]]:
    """The checks that need no geometry kernel, on integer boxes (PLAN M10): no overlaps, constraints, door
    planning and access through doors. `verify` can still reject what this accepts (build, slivers, tags), but in
    every run so far the kernel-only checks never failed on a placement that passed these."""
    from .doors import access_problems, plan_doors
    checks: dict[str, tuple[bool, str]] = {}
    missing = {s.name for s in brief.spaces} - set(placement)
    checks["complete"] = (not missing, "all spaces placed" if not missing else f"missing {sorted(missing)[:4]}")
    ov = overlaps(placement) if not missing else []
    checks["no_overlaps"] = (not ov, "none" if not ov else f"overlapping pairs {ov[:4]}")
    checks["constraints"] = check_constraints(brief, placement) if not missing else (False, "incomplete")
    if brief.circulation and not missing and not ov:
        doors, problems = plan_doors(brief, placement)
        issues = [q.message for q in problems] + [q.message for q in access_problems(brief, placement, doors)]
        checks["doors"] = (not issues, "; ".join(issues) if issues else f"{len(doors)} doors")
    else:
        checks["doors"] = (not brief.circulation or False, "no doors required" if not brief.circulation else "not planned")
    return all(ok for ok, _ in checks.values()), checks
