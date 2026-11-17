# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Adventurous Systems

"""Cores-first multi-level assembly (MANSION / Rodrigues discipline).

Shaft briefs (M7): each stair or lift is one tall box, placed once while assembling its first served level
and passed unchanged as a fixed box to every other level it serves; corridors and rooms on each level are
assembled around the shafts present there.
Legacy briefs: per-floor stair and lift members are copied to every level at the same footprint.
Each upper level gets a stacking bonus for wall planes aligned with the level below, inside the shared envelope."""
from __future__ import annotations

from ..brief import Brief
from ..levels import assign_levels, core_stacks, envelope_mm, level_height_mm, shafts
from ..placement import assembly_from_placement
from .beam import BeamParams, beam_search, planes
from .grid import Box, bounds


def _normalise_all(placement: dict[str, Box]) -> dict[str, Box]:
    bb = bounds(placement.values())
    return {n: Box(b.x - bb.x, b.y - bb.y, b.z, b.w, b.l, b.h) for n, b in placement.items()}


def beam_multilevel(brief: Brief, params: BeamParams | None = None, seed: int = 0,
                    base_options: int = 4, per_level: int = 2, scorer=None, batch_scorer=None,
                    trace: list | None = None) -> list[dict[str, Box]]:
    p = params or BeamParams()
    n_levels = brief.levels or 1
    H = level_height_mm(brief)
    env = envelope_mm(brief)
    levels = assign_levels(brief, seed)
    stacks = core_stacks(brief, levels)
    shaft_list = shafts(brief)
    by_level = {k: [s for s in brief.spaces if not s.is_shaft and levels[s.name] == k] for k in range(n_levels)}
    for sh in shaft_list:
        by_level[sh.serves[0]].append(sh)  # a shaft is placed with its first served level
    if n_levels == 1:
        return beam_search(brief, p, seed, envelope=env, height=H, scorer=scorer, batch_scorer=batch_scorer, trace=trace)

    base = beam_search(brief, p, seed, spaces=by_level[0], envelope=env, height=H, z0=0,
                       normalise_output=False, redim=False, scorer=scorer, batch_scorer=batch_scorer, trace=trace)
    combos: list[dict[str, Box]] = []
    for b0 in base[:base_options]:
        partials = [dict(b0)]
        for k in range(1, n_levels):
            nxt: list[dict[str, Box]] = []
            for partial in partials:
                lower = [b for b in partial.values() if b.z <= (k - 1) * H < b.z1]
                fixed: dict[str, Box] = {sh.name: partial[sh.name] for sh in shaft_list
                                         if sh.serves[0] < k <= sh.serves[1] and sh.name in partial}
                for stack in stacks:
                    # member on level k inherits the footprint of the member on level k-1
                    prev = [m for m in stack if levels[m] == k - 1 and m in partial]
                    cur = [m for m in stack if levels[m] == k]
                    if prev and cur:
                        pb = partial[prev[0]]
                        fixed[cur[0]] = Box(pb.x, pb.y, k * H, pb.w, pb.l, H)
                todo = [s for s in by_level[k] if s.name not in fixed]
                outs = beam_search(brief, p, seed + 100 * k, spaces=todo, fixed=fixed,
                                   context=list(partial.values()), ref_planes=planes(lower),
                                   envelope=env, height=H, z0=k * H, normalise_output=False, redim=False,
                                   scorer=scorer, batch_scorer=batch_scorer, trace=trace)
                for o in outs[:per_level]:
                    merged = dict(partial); merged.update(o)
                    nxt.append(merged)
            partials = nxt
        combos.extend(partials)
    seen, results = set(), []
    for pl in combos:
        pl = _normalise_all(pl)
        if env:
            bb = bounds(pl.values())
            if bb.w > env["w"] or bb.l > env["l"] or bb.z1 > env["h"]:
                continue
        sig = assembly_from_placement(brief, pl).signature()
        if sig in seen:
            continue
        seen.add(sig)
        results.append(pl)
        if len(results) >= p.k:
            break
    return results
