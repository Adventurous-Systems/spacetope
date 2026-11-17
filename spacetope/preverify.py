# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Adventurous Systems

"""Checks that need no geometry kernel, on integer boxes (PLAN M10). Pure Python: the search layer may import this."""
from __future__ import annotations

from .brief import MIN_HEIGHT_MM, Brief
from .levels import level_height_mm
from .placement import Placement, overlaps
from .solve.grid import contact_area

SIDES = ("+x", "-x", "+y", "-y", "ceiling", "floor")


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


def check_required_contacts(brief: Brief, placement: Placement) -> tuple[bool, str]:
    """Every pair the brief requires shares a face on the boxes, any side. The existing `contacts` check in
    `verify` tests that the kernel realised what was placed (H1a); this one tests the brief (H1b): a fault
    that removes a required contact from the placement no longer takes the intent with it."""
    required = brief.required_pairs()
    missing = []
    for pair in sorted(required, key=sorted):
        a, b = sorted(pair)
        if a not in placement or b not in placement or \
                not any(contact_area(placement[a], placement[b], s) > 0 for s in SIDES):
            missing.append(f"{a}-{b}")
    detail = f"{len(required)} required pairs touch" if not missing else "missing: " + ", ".join(missing[:6])
    return (not missing, detail)


def check_bands(brief: Brief, placement: Placement) -> tuple[bool, str]:
    """Every space lies inside its tolerance band, in either plan orientation, for width and length, and
    clears the height rules.

    Plan: exempt, exactly as the brief format declares free, the length of a corridor that states no
    explicit `l` tolerance (the README's rule: a corridor's width is fixed and its length is free).
    Rooms are never exempt in plan.

    Height (M18). A declared height is usually an *intention*, not a dimension the solver is free to
    choose: a room on a level is as tall as the level. So three rules, in this order:

    1. No space is ever shorter than `MIN_HEIGHT_MM`, whatever its mode or the level height.
    2. `height_mode: minimum` (an auditorium): the realised height must clear the declared height. There
       is no upper bound — a taller space still satisfies a minimum.
    3. Otherwise the height is a request: the realised height passes if it is the level height (which
       overrides the request by design) or lies inside the declared band. A shaft's height is pinned
       exactly by `check_constraints`, which is stricter, so it is not re-tested here.
    """
    H = level_height_mm(brief)
    bad, why = [], {}
    for name, box in placement.items():
        s = brief.by_name.get(name)
        if s is None:
            continue
        bw, bl, bh = s.band("w"), s.band("l"), s.band("h")
        l_free = s.program == "corridor" and (s.tol is None or (isinstance(s.tol, dict) and "l" not in s.tol))
        plain = bw[0] <= box.w <= bw[1] and (l_free or bl[0] <= box.l <= bl[1])
        rotated = bw[0] <= box.l <= bw[1] and (l_free or bl[0] <= box.w <= bl[1])

        if box.h < MIN_HEIGHT_MM:
            h_ok, reason = False, f"height {box.h} mm is below the minimum {MIN_HEIGHT_MM} mm"
        elif s.height_is_minimum:
            need = s.nominal_mm("h")
            h_ok = box.h >= need
            reason = "" if h_ok else f"height {box.h} mm does not clear the required minimum {need} mm"
        elif s.is_shaft:
            h_ok, reason = True, ""
        else:
            h_ok = box.h == H or bh[0] <= box.h <= bh[1]
            reason = "" if h_ok else f"height {box.h} mm is neither the level height {H} mm nor in {bh}"

        if not (plain or rotated):
            bad.append(name)
            why[name] = f"{box.w}x{box.l} mm outside {bw} x {bl}"
        elif not h_ok:
            bad.append(name)
            why[name] = reason
    detail = ("all inside their bands (height: the level height satisfies a request; a minimum must be "
              "cleared; nothing below %d mm)" % MIN_HEIGHT_MM if not bad
              else f"{len(bad)} out of band: " + "; ".join(f"{n} ({why[n]})" for n in sorted(bad)[:4]))
    return (not bad, detail)


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
    checks["required_contacts"] = check_required_contacts(brief, placement) if not missing else (False, "incomplete")
    checks["bands"] = check_bands(brief, placement)
    if brief.circulation and not missing and not ov:
        doors, problems = plan_doors(brief, placement)
        issues = [q.message for q in problems] + [q.message for q in access_problems(brief, placement, doors)]
        checks["doors"] = (not issues, "; ".join(issues) if issues else f"{len(doors)} doors")
    else:
        checks["doors"] = (not brief.circulation or False, "no doors required" if not brief.circulation else "not planned")
    return all(ok for ok, _ in checks.values()), checks
