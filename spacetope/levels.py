# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Adventurous Systems

"""Levels are emergent z-bands, but generators need a working assignment of spaces to levels.
Rules: explicit `wishes.level` wins; cores/corridors are dealt round-robin; rooms follow their required
contacts; the rest balance floor area. Level height = brief.level_height or the tallest space."""
from __future__ import annotations

import random

from .brief import Brief
from .units import to_mm


def level_height_mm(brief: Brief) -> int:
    if brief.level_height:
        return to_mm(brief.level_height)
    return max(s.nominal_mm("h") for s in brief.spaces)


def envelope_mm(brief: Brief) -> dict[str, int] | None:
    if not brief.envelope:
        return None
    return {k: to_mm(float(v)) for k, v in brief.envelope.items()}


def assign_levels(brief: Brief, seed: int = 0) -> dict[str, int]:
    """Level per floor-bound space. Shafts (stairs and lifts with `serves`) have a span instead and are
    not in the result; see `shafts` and `shafts_on`."""
    n = brief.levels or 1
    rng = random.Random(seed)
    lv: dict[str, int] = {}
    for s in brief.spaces:
        if "level" in s.wishes:
            lv[s.name] = int(s.wishes["level"]) % n
    for program in ("stair", "elevator", "corridor"):
        group = sorted(s.name for s in brief.spaces if s.program == program and s.name not in lv and not s.is_shaft)
        for i, name in enumerate(group):
            lv[name] = i % n
    changed = True
    while changed:
        changed = False
        for a, b in brief.contacts:
            for x, y in ((a, b), (b, a)):
                if x in lv and y not in lv and brief.space(y).program == "room" and not brief.space(x).is_vertical:
                    lv[y] = lv[x]
                    changed = True
    area = {k: 0 for k in range(n)}
    for name, k in lv.items():
        s = brief.space(name)
        area[k] += s.nominal_mm("w") * s.nominal_mm("l")
    rest = [s for s in brief.spaces if s.name not in lv and not s.is_shaft]
    rng.shuffle(rest)
    rest.sort(key=lambda s: -(s.w * s.l))
    for s in rest:
        k = min(area, key=lambda kk: area[kk])
        lv[s.name] = k
        area[k] += s.nominal_mm("w") * s.nominal_mm("l")
    return lv


def shafts(brief: Brief) -> list:
    """Stairs and lifts declared once with a level span (M7)."""
    return [s for s in brief.spaces if s.is_shaft]


def shafts_on(brief: Brief, k: int) -> list:
    return [s for s in shafts(brief) if s.serves[0] <= k <= s.serves[1]]


def core_stacks(brief: Brief, levels: dict[str, int]) -> list[list[str]]:
    """Legacy briefs only: group per-floor stair and lift members into stacks (one member per level).
    Shafts are single spaces and never form stacks."""
    stacks: list[list[str]] = []
    for program in ("stair", "elevator"):
        per_level: dict[int, list[str]] = {}
        for s in brief.spaces:
            if s.program == program and not s.is_shaft:
                per_level.setdefault(levels[s.name], []).append(s.name)
        for k in per_level:
            per_level[k].sort()
        depth = max((len(v) for v in per_level.values()), default=0)
        for i in range(depth):
            stack = [per_level[k][i] for k in sorted(per_level) if i < len(per_level[k])]
            if stack:
                stacks.append(stack)
    return stacks
