"""M7 doors. This first part decides which pairs need a door and how much shared wall that takes, so the
generators can leave room for doors. Door planning, realisation and verification follow in step M7.4.
Plan: docs/2026-09-13_M7_vertical_circulation_plan.md §3.5 (rules D8, sizes D9)."""
from __future__ import annotations

from .brief import Brief
from .circulation import door_kind, door_spec
from .units import to_mm

from .solve.grid import touches  # noqa: E402  (pure integer geometry, no topologicpy)

LEGACY_DOOR_MM = 900  # briefs without a circulation section keep the pre-M7 rule
HSIDES = ("+x", "-x", "+y", "-y")


def door_kind_for(brief: Brief, a: str, b: str) -> str | None:
    """'room' | 'stair' | 'lift' when the pair needs a door, else None (circulation briefs only)."""
    sa, sb = brief.space(a), brief.space(b)
    pair = frozenset((a, b))
    shaft = sa if sa.is_shaft else sb if sb.is_shaft else None
    other = sb if shaft is sa else sa
    if shaft is not None:
        if other.program == "corridor" or pair in brief.marked_door_pairs():
            return door_kind(shaft.program)
        return None
    if {sa.program, sb.program} == {"room", "corridor"}:
        return "room"
    if pair in brief.marked_door_pairs():
        return "room"
    return None


def touch_ok(brief: Brief, a: str, box_a, b: str, box_b, legacy_door_mm: int = LEGACY_DOOR_MM) -> bool:
    """A pair that needs a door must share enough wall for one wherever it touches (M7).
    A pair that needs no door may touch by any amount, including a graze."""
    need = required_overlap_mm(brief, a, b, legacy_door_mm)
    if need <= 1:
        return True
    best = 0
    for side in HSIDES:
        u, _v = touches(box_a, box_b, side)
        best = max(best, u)
    return best == 0 or best >= need


def corridor_opening_mm(brief: Brief, a: str, b: str) -> int:
    """Two corridor segments of one level's spine meet over the full corridor width: an opening, not a door (M15b).
    0 when the pair is not two corridors on the same level."""
    sa, sb = brief.space(a), brief.space(b)
    if sa.program != "corridor" or sb.program != "corridor":
        return 0
    la, lb = sa.wishes.get("level"), sb.wishes.get("level")
    if la is None or lb is None or int(la) != int(lb):
        return 0
    return min(to_mm(sa.w), to_mm(sb.w))


def required_overlap_mm(brief: Brief, a: str, b: str, legacy_door_mm: int = LEGACY_DOOR_MM) -> int:
    """Shared wall a pair must have when it touches: the corridor width for two segments of one spine, door width
    + 2 jambs for door pairs, 1 mm otherwise."""
    opening = corridor_opening_mm(brief, a, b)
    if opening:
        return opening
    if not brief.circulation:
        sa, sb = brief.space(a), brief.space(b)
        legacy = (sa.program == "room" and sb.is_circulation) or (sb.program == "room" and sa.is_circulation)
        return legacy_door_mm if legacy else 1
    kind = door_kind_for(brief, a, b)
    if kind is None:
        return 1
    spec = door_spec(brief)
    return to_mm(spec[kind]["w"] + 2 * spec["jamb"])


# ----------------------------------------------------------------------------- door planning (M7.4, pure)

from dataclasses import asdict, dataclass  # noqa: E402

import networkx as nx  # noqa: E402

from .circulation import Problem, _fmt  # noqa: E402
from .levels import level_height_mm  # noqa: E402
from .solve.grid import Box, OPPOSITE, overlap_len  # noqa: E402


@dataclass(frozen=True)
class Door:
    a: str            # the space on whose wall `side` the door sits
    b: str            # the space it opens into
    kind: str         # room | stair | lift
    level: int
    side: str         # side of `a` facing `b`
    plane_mm: int     # x (for ±x) or y (for ±y) coordinate of the shared wall
    lo_mm: int        # door extent along the wall
    hi_mm: int
    z_mm: int         # bottom of the door = floor of the level
    height_mm: int

    @property
    def width_mm(self) -> int:
        return self.hi_mm - self.lo_mm

    @property
    def pair(self) -> frozenset[str]:
        return frozenset((self.a, self.b))

    @property
    def name(self) -> str:
        return f"door_{self.a}_{self.b}_L{self.level}"

    def to_dict(self) -> dict:
        return {**asdict(self), "name": self.name}

    @classmethod
    def from_dict(cls, d: dict) -> "Door":
        return cls(**{k: d[k] for k in ("a", "b", "kind", "level", "side", "plane_mm", "lo_mm", "hi_mm", "z_mm", "height_mm")})


def _best_wall(A: Box, B: Box, z0: int, z1: int) -> tuple[str, int, int, int] | None:
    """Longest shared wall segment between A and B within the vertical band [z0, z1): (side of A, plane, lo, hi)."""
    best = None
    for side in HSIDES:
        u, v = touches(A, B, side)
        if u == 0:
            continue
        if overlap_len(A.interval("z"), (z0, z1)) == 0 or overlap_len(B.interval("z"), (z0, z1)) == 0:
            continue
        axis, plane = A.face_plane(side)
        along = "y" if axis == "x" else "x"
        lo = max(A.interval(along)[0], B.interval(along)[0])
        hi = min(A.interval(along)[1], B.interval(along)[1])
        if best is None or hi - lo > best[3] - best[2]:
            best = (side, plane, lo, hi)
    return best


def _level_of(box: Box, H: int) -> int:
    return box.z // H


def plan_doors(brief: Brief, placement: dict[str, Box]) -> tuple[list[Door], list[Problem]]:
    """Doors required by rule D8, centred on their shared wall. Briefs without circulation get no doors."""
    if not brief.circulation:
        return [], []
    H = level_height_mm(brief)
    spec = door_spec(brief)
    jamb = to_mm(spec["jamb"])
    doors: list[Door] = []
    problems: list[Problem] = []

    def make(a: str, b: str, kind: str, level: int) -> Door | None:
        A, B = placement[a], placement[b]
        width = to_mm(spec[kind]["w"]); height = to_mm(spec[kind]["h"])
        z0 = level * H
        wall = _best_wall(A, B, z0, z0 + H)
        need = width + 2 * jamb
        have = 0 if wall is None else wall[3] - wall[2]
        if wall is None or have < need:
            problems.append(Problem("door_room",
                                    f"{a} needs {_fmt(need / 1000)} m of shared wall with {b} on level {level} for its door; "
                                    f"it has {_fmt(have / 1000)} m"))
            return None
        side, plane, lo, hi = wall
        centre = (lo + hi) // 2
        return Door(a, b, kind, level, side, plane, centre - width // 2, centre - width // 2 + width, z0, height)

    # corridors by the level their box sits on, whatever they are called (review 2026-09-13, #4)
    corridors_on: dict[int, list[str]] = {}
    for c in brief.spaces:
        if c.program == "corridor" and c.name in placement:
            corridors_on.setdefault(_level_of(placement[c.name], H), []).append(c.name)
    # 1. shafts: a door to a corridor on every served level (the one sharing the longest wall)
    for s in brief.spaces:
        if not s.is_shaft:
            continue
        kind = door_kind(s.program)
        for k in range(s.serves[0], s.serves[1] + 1):
            candidates = corridors_on.get(k, [])
            if not candidates:
                problems.append(Problem("door_corridor", f"{s.name} serves level {k} but there is no corridor on level {k}"))
                continue
            def wall_len(c: str) -> int:
                w = _best_wall(placement[s.name], placement[c], k * H, (k + 1) * H)
                return w[3] - w[2] if w else 0
            corridor = max(candidates, key=wall_len)
            d = make(s.name, corridor, kind, k)
            if d:
                doors.append(d)
    # 2. rooms: exactly one door to a corridor on their level (required contact first, then the longest wall)
    required = brief.required_pairs()
    for s in brief.spaces:
        if s.program != "room":
            continue
        box = placement[s.name]
        k = _level_of(box, H)
        need_room = to_mm(spec["room"]["w"]) + 2 * jamb
        candidates = []
        for c in brief.spaces:
            if c.program != "corridor" or _level_of(placement[c.name], H) != k:
                continue
            wall = _best_wall(box, placement[c.name], k * H, (k + 1) * H)
            if wall is None:
                continue
            have = wall[3] - wall[2]
            # a wall wide enough for the door beats a required contact that is too short
            candidates.append((have >= need_room, frozenset((s.name, c.name)) in required, have, c.name))
        if not candidates:
            problems.append(Problem("door_room", f"{s.name} touches no corridor on level {k}, so it has no door"))
            continue
        *_, corridor = max(candidates)
        d = make(s.name, corridor, "room", k)
        if d:
            doors.append(d)
    # 3. room-to-room doors the brief marks explicitly
    shaft_names = {s.name for s in brief.spaces if s.is_shaft}
    for a, b in brief.door_pairs:
        if a in shaft_names or b in shaft_names:
            continue  # shaft doors are rule 1
        if brief.space(a).program == "room" and brief.space(b).program == "room":
            k = _level_of(placement[a], H)
            d = make(a, b, "room", k)
            if d:
                doors.append(d)
    return doors, problems


def door_graph(brief: Brief, doors: list[Door], placement: dict[str, Box] | None = None) -> nx.Graph:
    """Walkable graph: every space is a node; each door is an edge carrying its kind and level. With `placement`,
    two corridor segments that share the full corridor width are walkable too, through an opening (M15b)."""
    g = nx.Graph()
    g.add_nodes_from(s.name for s in brief.spaces)
    for d in doors:
        g.add_edge(d.a, d.b, kind=d.kind, level=d.level)
    if placement is not None:
        corridors = [s for s in brief.spaces if s.program == "corridor" and s.name in placement]
        for i, ca in enumerate(corridors):
            for cb in corridors[i + 1:]:
                need = corridor_opening_mm(brief, ca.name, cb.name)
                if need and max(touches(placement[ca.name], placement[cb.name], sd)[0] for sd in HSIDES) >= need:
                    g.add_edge(ca.name, cb.name, kind="opening", level=int(ca.wishes.get("level", 0)))
    return g


def access_problems(brief: Brief, placement: dict[str, Box], doors: list[Door]) -> list[Problem]:
    """Every room reaches a stair through doors (or a corridor, when the brief has no stairs);
    with more than one level, every level has a stair door."""
    if not brief.circulation:
        return []
    H = level_height_mm(brief)
    g = door_graph(brief, doors, placement)
    stairs = [s.name for s in brief.spaces if s.program == "stair"]
    targets = set(stairs) if stairs else {s.name for s in brief.spaces if s.program == "corridor"}
    problems = []
    for s in brief.spaces:
        if s.program != "room":
            continue
        reach = nx.node_connected_component(g, s.name)
        if not reach & targets:
            what = "a stair" if stairs else "a corridor"
            problems.append(Problem("access", f"{s.name} cannot reach {what} through doors"))
    if (brief.levels or 1) > 1:
        for k in range(brief.levels):
            if not any(d.kind == "stair" and d.level == k for d in doors):
                problems.append(Problem("access", f"level {k} has no stair door"))
    return problems
