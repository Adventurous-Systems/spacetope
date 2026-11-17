# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Adventurous Systems

"""M8: how many floors does a brief need?

Three stages, cheapest first (docs/2026-09-13_M7_vertical_circulation_plan.md §7):

1. `bounds` — arithmetic only. The fewest floors whose per-floor demand fits the envelope footprint, and
   the most the envelope height allows. An impossible brief is reported here, in milliseconds.
2. `sweep` — for each candidate count, expand the brief and generate layouts without building geometry,
   ranked by a cheap proxy (adjacency, fill, dimensional deviation).
3. `search` — build and verify only the best few per candidate, so the architect compares real options
   across floor counts.

A floor plate is never fully usable, so the demand is compared against `utilisation` × footprint.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field

from .brief import Brief
from .circulation import level_height_m, prepare
from .pipeline import Option, evaluate_placements
from .placement import assembly_from_placement
from .score import adjacency, deviation
from .solve.grid import bounds as box_bounds

# Share of a floor plate that rooms, corridors and shafts actually occupy. Calibrated 2026-09-13 against
# the smallest floor count that verifies, on the three-level fixture at four envelopes: implied utilisation
# ran 0.43-0.64, so 0.65 keeps the bound from ruling out counts that demonstrably build. The bound stays a
# cheap filter; the search reports what each candidate really produced.
UTILISATION = 0.65
MAX_LEVELS_CAP = 8     # when no envelope height is given, do not search beyond this


@dataclass
class Areas:
    rooms: float             # m², summed over every room in the brief
    corridor: float          # m², one corridor per floor
    shafts: float            # m², each shaft occupies its footprint on every floor it serves
    room_frontage: float     # m, corridor wall the rooms need (each room's shorter side)
    shaft_frontage: float    # m, corridor wall the shafts take on every floor

    def per_level(self, levels: int) -> float:
        return self.rooms / levels + self.corridor + self.shafts

    def frontage_per_level(self, levels: int) -> float:
        return self.room_frontage / levels + self.shaft_frontage


@dataclass
class Bounds:
    min_levels: int
    max_levels: int
    feasible: bool
    reason: str
    areas: Areas
    footprint: float | None
    level_height: float

    frontage_supply: float = 0.0   # m of corridor wall a floor can offer inside the envelope
    tight: list[int] = field(default_factory=list)  # counts whose rooms barely fit along the corridor

    def candidates(self, most: int = 3) -> list[int]:
        if not self.feasible:
            return []
        return list(range(self.min_levels, min(self.max_levels, self.min_levels + most - 1) + 1))


def areas(brief: Brief) -> Areas:
    """Floor areas from the compact brief: rooms, one corridor per floor, and the shafts."""
    circ = brief.circulation or {}
    rooms = sum(s.w * s.l for s in brief.spaces if s.program == "room")
    corridor = 0.0
    if circ.get("corridor"):
        corridor = float(circ["corridor"]["w"]) * float(circ["corridor"]["l"])
    else:
        per_level: dict[object, float] = {}
        for s in brief.spaces:
            if s.program == "corridor":
                per_level.setdefault(s.wishes.get("level"), 0.0)
                per_level[s.wishes.get("level")] += s.w * s.l
        corridor = max(per_level.values()) if per_level else 0.0
    shafts = sum(float(item["w"]) * float(item["l"]) for key in ("stairs", "lifts") for item in circ.get(key) or [])
    shafts += sum(s.w * s.l for s in brief.spaces if s.is_shaft)
    # frontage: a room sits along the corridor on its shorter side, and so does a shaft
    room_frontage = sum(min(s.w, s.l) for s in brief.spaces if s.program == "room")
    shaft_frontage = sum(min(float(item["w"]), float(item["l"])) for key in ("stairs", "lifts") for item in circ.get(key) or [])
    shaft_frontage += sum(min(s.w, s.l) for s in brief.spaces if s.is_shaft)
    return Areas(rooms=rooms, corridor=corridor, shafts=shafts,
                 room_frontage=room_frontage, shaft_frontage=shaft_frontage)


def frontage_supply(brief: Brief, a: Areas) -> float:
    """Corridor wall one floor can offer: both sides of the longest corridor that fits the envelope."""
    circ = brief.circulation or {}
    corridor = circ.get("corridor")
    longest = float(corridor["l"]) if corridor else max((s.l for s in brief.spaces if s.program == "corridor"), default=0.0)
    if corridor:
        from .brief import Space
        longest = Space(name="c", w=float(corridor["w"]), l=float(corridor["l"]), h=3.0, program="corridor").band("l")[1] / 1000
    env = brief.envelope or {}
    if "w" in env and "l" in env:
        longest = min(longest, max(float(env["w"]), float(env["l"])))
    return 2 * longest


def bounds(brief: Brief, utilisation: float = UTILISATION, cap: int = MAX_LEVELS_CAP) -> Bounds:
    H = level_height_m(brief)
    a = areas(brief)
    env = brief.envelope or {}
    footprint = float(env["w"]) * float(env["l"]) if "w" in env and "l" in env else None
    supply = frontage_supply(brief, a)
    from .units import to_mm  # integer mm: 8.1 // 2.7 is 2.0 in floats but 3 in millimetres (review 2026-09-13, #9)
    max_levels = to_mm(float(env["h"])) // to_mm(H) if "h" in env else cap
    max_levels = max(0, min(max_levels, cap))
    if footprint is None:
        lo = 1
        reason = f"no envelope footprint: one floor fits by default; height allows up to {max_levels}"
    else:
        usable = footprint * utilisation
        lo = None
        for k in range(1, cap + 1):
            if a.per_level(k) <= usable + 1e-9:
                lo = k
                break
        if lo is None:
            need = a.per_level(cap)
            return Bounds(cap, max_levels, False,
                          f"even {cap} floors need about {need:.0f} m² each; {usable:.0f} m² is usable of a "
                          f"{footprint:.0f} m² footprint", a, footprint, H, supply, [])
        reason = (f"{lo} floor{'s' if lo > 1 else ''} need about {a.per_level(lo):.0f} m² each, within the "
                  f"{footprint * utilisation:.0f} m² usable of a {footprint:.0f} m² footprint")
    if max_levels < lo:
        h = float(env["h"]) if "h" in env else max_levels * H
        return Bounds(lo, max_levels, False,
                      f"{lo} floors × {H:g} m need {lo * H:g} m; the envelope is {h:g} m tall", a, footprint, H, supply, [])
    # Frontage (corridor wall per floor) is reported, not used to move the bound: a first attempt at flagging
    # "tight" counts failed to predict the measured failures (docs/PLAN.md, 2026-09-13), so the honest signal
    # is the per-candidate reason the search reports after actually generating.
    return Bounds(lo, max_levels, True, reason, a, footprint, H, supply, [])


def brief_for_levels(brief: Brief, levels: int) -> Brief:
    """The same brief asked to use `levels` floors.

    Three things have to give way, because they name a floor that may not exist at this count:
    room level wishes, contacts naming a generated corridor, and shaft level spans. Rooms then reach a
    corridor through the generators' access rules and door planning instead of a named contact; room-to-room
    contacts are kept, and level assignment keeps such pairs on one floor.
    """
    import copy
    d = copy.deepcopy(brief.to_dict())  # to_dict shares the circulation dict; never edit the caller's brief
    d["levels"] = levels
    # Rooms keep a corridor to open onto: a contact naming corridor_k is remapped onto a corridor that exists
    # at this count. Rooms that must touch each other are remapped to the same corridor, so they stay on one
    # floor (level assignment follows required contacts, and a cross-floor room pair can never touch).
    contacts = [list(c) for c in d.get("contacts", [])]
    room_names = {s["name"] for s in d["spaces"] if s.get("program", "room") == "room"}
    explicit_level: dict[str, int | None] = {}
    for sp in d["spaces"]:
        if sp.get("program") == "corridor":
            explicit_level[sp["name"]] = (sp.get("wishes") or {}).get("level")

    def corridor_level(name: str):
        """Level a corridor name stands for: an explicit corridor's wish, or the k in a generated corridor_k."""
        if name in explicit_level:
            return explicit_level[name]
        if name.startswith("corridor_") and name[9:].isdigit():
            return int(name[9:])
        return None

    is_corridor = lambda name: corridor_level(name) is not None
    group: dict[str, str] = {}

    def root(name: str) -> str:
        while group.get(name, name) != name:
            name = group[name]
        return name

    for c in contacts:  # union rooms that are required to touch
        a, b = c[0], c[1]
        if a in room_names and b in room_names:
            ra, rb = root(a), root(b)
            if ra != rb:
                group[rb] = ra
    corridor_for: dict[str, int] = {}
    for c in contacts:
        for i, other in ((0, 1), (1, 0)):
            if is_corridor(c[i]) and c[other] in room_names:
                corridor_for.setdefault(root(c[other]), corridor_level(c[i]) % levels)
    for c in contacts:
        for i, other in ((0, 1), (1, 0)):
            if is_corridor(c[i]):
                k = corridor_for.get(root(c[other])) if c[other] in room_names else corridor_level(c[i]) % levels
                c[i] = f"corridor_{k if k is not None else corridor_level(c[i]) % levels}"
    d["contacts"] = contacts
    for space in d["spaces"]:
        wishes = space.get("wishes") or {}
        wishes.pop("level", None)
        if wishes:
            space["wishes"] = wishes
        else:
            space.pop("wishes", None)
    circ = d.get("circulation") or {}
    for key in ("stairs", "lifts"):
        for item in circ.get(key) or []:
            item.pop("serves", None)
    if levels > 1 and circ and not circ.get("stairs"):
        circ["stairs"] = [{"name": "stair", "w": 3.0, "l": 5.0}]
    return Brief.from_dict(d)


def proxy_score(brief: Brief, placement) -> float:
    """Cheap ranking without topologicpy: required adjacency, how densely the plate is filled, deviation."""
    pairs = assembly_from_placement(brief, placement).contact_pairs()
    bb = box_bounds(placement.values())
    fill = sum(b.w * b.l for b in placement.values()) / max(1, bb.w * bb.l)
    return 10 * adjacency(brief, pairs) + 3 * fill - 5 * deviation(brief, placement)


@dataclass
class FloorOption:
    levels: int
    options: list[Option] = field(default_factory=list)
    t_gen: float = 0.0
    t_build: float = 0.0
    reason: str = ""       # why this count produced no verified option

    @property
    def verified(self) -> list[Option]:
        return [o for o in self.options if o.ok]


def sweep(brief: Brief, generator, levels: int, seed: int = 0, keep: int = 3) -> tuple[Brief, list, float]:
    """Generation only for one candidate count: returns the expanded brief and the best `keep` placements."""
    expanded, _ = prepare(brief_for_levels(brief, levels))
    t0 = time.perf_counter()
    placements = generator(expanded, None, seed)
    t_gen = time.perf_counter() - t0
    placements.sort(key=lambda pl: -proxy_score(expanded, pl))
    return expanded, placements[:keep], t_gen


def search(brief: Brief, generator, seed: int = 0, keep: int = 3, most: int = 3,
           utilisation: float = UTILISATION) -> tuple[Bounds, list[FloorOption]]:
    """Bounds, then a generation-only sweep per candidate count, then build and verify the best few."""
    b = bounds(brief, utilisation)
    results: list[FloorOption] = []
    for levels in b.candidates(most):
        expanded, placements, t_gen = sweep(brief, generator, levels, seed, keep)
        t0 = time.perf_counter()
        options = evaluate_placements(expanded, placements, "floors", seed)
        entry = FloorOption(levels=levels, options=options, t_gen=t_gen, t_build=time.perf_counter() - t0)
        if not entry.verified:
            entry.reason = _why_nothing(b, levels, placements, options)
        results.append(entry)
    return b, results


def _why_nothing(b: Bounds, levels: int, placements: list, options: list[Option]) -> str:
    if not placements:
        note = f"{levels} floors: the generator found no layout inside the envelope"
    else:
        details = [d for o in options if not o.ok for k, (passed, d) in o.report.checks.items() if not passed]
        note = f"{levels} floors: {len(options)} layouts, none verified" + (f" — {details[0][:160]}" if details else "")
    demand = b.areas.frontage_per_level(levels)
    if demand > 0.8 * b.frontage_supply > 0:
        note += (f" (corridor wall is tight at this count: rooms and shafts need about {demand:.0f} m "
                 f"of roughly {b.frontage_supply:.0f} m available)")
    return note
