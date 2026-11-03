"""Planted briefs (E9): build a placement first, then write it back as a brief, so at least one exact
solution exists by construction. Two families:

- **A, no circulation**: a rectangle cut into n rooms, by guillotine cuts (slicing) or with a pinwheel
  insert (non-slicing). Required contacts are a fraction rho of the realised room-to-room contacts,
  keeping the contact graph connected; about half of them are marked as doors.
- **B, corridor-served**: a corridor of fixed width, straight or L-shaped (two segments), rooms on one
  or both sides, every room touching the corridor. Room widths against the corridor length set the
  frontage ratio. Extra levels stack the same corridor, with a stair and a lift through every level.

Every space's nominal size is its planted size x (1 + u), u drawn uniformly from (-t/2, t/2), with band
+-t, so the planted solution sits inside the band but not at its centre. Corridors and shafts keep their
planted sizes exactly (their bands are fixed by the brief format). All construction is on the integer
millimetre grid; metres appear only in the written brief.
"""
from __future__ import annotations

import random
from dataclasses import dataclass

from .brief import Brief, Space
from .solve.grid import Box, contact_area

HS = ("+x", "-x", "+y", "-y")
MIN_SIDE = 1_500            # a leaf room is never narrower than this (mm)
DOOR_RUN = 1_100            # only contacts with at least this shared run are marked as doors (900 + jambs)
H_MM = 3_000


@dataclass
class PlantedAParams:
    n: int = 9
    t: float = 0.10
    rho: float = 0.5
    slicing: bool = True
    room_area: float = 16.0  # m2 target per room


@dataclass
class PlantedBParams:
    rooms: int = 16
    t: float = 0.10
    frontage: float = 0.75
    shape: str = "straight"   # or "L"
    double_loaded: bool = True
    levels: int = 1
    corridor_w: float = 1.8


# --------------------------------------------------------------------------- family A

def _pinwheel(rect: tuple[int, int, int, int], rng: random.Random) -> list[tuple[int, int, int, int]]:
    """Five rooms in a pinwheel: four wrapping a centre. Non-slicing: no cut crosses the whole rectangle."""
    x0, y0, w, l = rect
    x1 = x0 + int(w * rng.uniform(0.30, 0.42))
    x2 = x0 + int(w * rng.uniform(0.58, 0.70))
    y1 = y0 + int(l * rng.uniform(0.30, 0.42))
    y2 = y0 + int(l * rng.uniform(0.58, 0.70))
    X1, Y1 = x0 + w, y0 + l
    return [(x0, y0, x2 - x0, y1 - y0),        # bottom
            (x2, y0, X1 - x2, y2 - y0),        # right
            (x1, y2, X1 - x1, Y1 - y2),        # top
            (x0, y1, x1 - x0, Y1 - y1),        # left
            (x1, y1, x2 - x1, y2 - y1)]        # centre


def _split(rect: tuple[int, int, int, int], k: int, rng: random.Random, slicing: bool) -> list[tuple[int, int, int, int]]:
    x0, y0, w, l = rect
    if k == 1:
        return [rect]
    if not slicing and k == 5 and w >= 3 * MIN_SIDE and l >= 3 * MIN_SIDE:
        return _pinwheel(rect, rng)
    if not slicing and k > 5 and rng.random() < 0.5:
        k1 = 5
    else:
        k1 = max(1, min(k - 1, round(k * rng.uniform(0.35, 0.65))))
    axis_w = w >= l
    side = w if axis_w else l
    cut = int(side * (k1 / k) * rng.uniform(0.9, 1.1))
    cut = max(MIN_SIDE * (1 if k1 == 1 else 2), min(side - MIN_SIDE * (1 if k - k1 == 1 else 2), cut))
    if axis_w:
        a, b = (x0, y0, cut, l), (x0 + cut, y0, w - cut, l)
    else:
        a, b = (x0, y0, w, cut), (x0, y0 + cut, w, l - cut)
    return _split(a, k1, rng, slicing) + _split(b, k - k1, rng, slicing)


def _nominal(planted_mm: int, t: float, rng: random.Random) -> float:
    """Nominal size in metres: planted x (1 + u), u ~ U(-t/2, t/2), snapped to mm; planted stays in band."""
    if t <= 0:
        return planted_mm / 1000
    for _ in range(8):
        u = rng.uniform(-t / 2, t / 2)
        nominal = round(planted_mm * (1 + u)) / 1000
        lo = max(1, int(round(nominal * 1000 * (1 - t))))
        hi = int(round(nominal * 1000 * (1 + t)))
        if lo <= planted_mm <= hi:
            return nominal
    return planted_mm / 1000  # rounding pushed every draw out (tiny rooms); plant at the centre instead


def _touching_rooms(placement: dict[str, Box]) -> list[tuple[str, str, int]]:
    names = sorted(placement)
    out = []
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            area = max(contact_area(placement[a], placement[b], s) for s in HS)
            if area > 0:
                run = area // min(placement[a].h, placement[b].h)  # plan run of the shared wall
                out.append((a, b, run))
    return out


def plant_a(params: PlantedAParams | None = None, seed: int = 0) -> tuple[Brief, dict[str, Box]]:
    p = params or PlantedAParams()
    rng = random.Random(seed)
    area_mm2 = p.n * int(p.room_area * 1e6)
    aspect = rng.uniform(1.1, 1.5)
    W = int((area_mm2 * aspect) ** 0.5)
    L = area_mm2 // W
    rects = _split((0, 0, W, L), p.n, rng, p.slicing)
    rects.sort(key=lambda r: (r[1], r[0]))
    placement = {f"room_{i + 1}": Box(x, y, 0, w, l, H_MM) for i, (x, y, w, l) in enumerate(rects)}

    touching = _touching_rooms(placement)
    rng.shuffle(touching)
    # a random spanning tree first, so the contact graph stays connected
    required: list[tuple[str, str]] = []
    joined = {next(iter(placement))}
    frontier = list(touching)
    while len(joined) < len(placement):
        for t_ in frontier:
            a, b, _ = t_
            if (a in joined) != (b in joined):
                required.append((a, b))
                joined |= {a, b}
                frontier.remove(t_)
                break
        else:  # disconnected partition cannot happen in a rectangle tiling; guard anyway
            raise AssertionError("contact graph of a planted tiling must be connected")
    want = max(len(required), round(p.rho * len(touching)))
    for a, b, _ in touching:
        if len(required) >= want:
            break
        if (a, b) not in required and (b, a) not in required:
            required.append((a, b))

    runs = {frozenset((a, b)): run for a, b, run in touching}
    doorable = [c for c in required if runs[frozenset(c)] >= DOOR_RUN]
    rng.shuffle(doorable)
    doors = set(map(frozenset, doorable[: len(doorable) // 2]))

    spaces = [Space(name=n, w=_nominal(b.w, p.t, rng), l=_nominal(b.l, p.t, rng), h=H_MM / 1000, tol=p.t)
              for n, b in sorted(placement.items())]
    name = f"planted_a_n{p.n}_t{int(p.t * 100)}_rho{int(p.rho * 100)}_{'slice' if p.slicing else 'pin'}_s{seed}"
    brief = Brief(name=name, spaces=spaces, contacts=[list(c) for c in required],
                  door_pairs=[c for c in required if frozenset(c) in doors])
    return brief, placement


# --------------------------------------------------------------------------- family B

def _pack_side(rooms: list[tuple[str, int, int]], x0: int, y: int, z: int, below: bool,
               along: str = "x") -> dict[str, Box]:
    """Pack rooms shoulder to shoulder along a corridor side, starting at x0 (or y0 when along y)."""
    out: dict[str, Box] = {}
    cursor = x0
    for name, w_mm, d_mm in rooms:
        if along == "x":
            out[name] = Box(cursor, y - d_mm if below else y, z, w_mm, d_mm, H_MM)
        else:
            out[name] = Box(y - d_mm if below else y, cursor, z, d_mm, w_mm, H_MM)
        cursor += w_mm
    return out


def plant_b(params: PlantedBParams | None = None, seed: int = 0) -> tuple[Brief, dict[str, Box]]:
    """Straight: rooms on one or both corridor sides. L (two segments): segment 1 is loaded on its south
    side only and segment 2 on both, so no room can reach the inner corner from two directions; the
    frontage ratio is honoured over the two geometric sides of each segment either way."""
    p = params or PlantedBParams()
    rng = random.Random(seed)
    cw = int(p.corridor_w * 1000)
    segments = 2 if p.shape.upper() == "L" else 1

    # planted room sizes; w faces the corridor
    dims = [(f"room_{i + 1}", int(rng.uniform(3200, 4800)), int(rng.uniform(4200, 5800))) for i in range(p.rooms)]
    per_level = [dims[k::p.levels] for k in range(p.levels)]

    # assign rooms to segment sides once per level, then size the segments so every level fits
    plans = []
    C1 = C2 = 0
    for rooms_k in per_level:
        if segments == 1:
            south, north = _balance(rooms_k, rng) if p.double_loaded else (list(rooms_k), [])
            plans.append((south, north, [], []))
            C1 = max(C1, _needed(south, north, p.frontage))
        else:
            cut = max(1, len(rooms_k) // 3)
            g1 = rooms_k[:cut]                       # south of segment 1 only (see docstring)
            east, west = _balance(rooms_k[cut:], rng)
            plans.append((g1, [], east, west))
            C1 = max(C1, _needed(g1, [], p.frontage))
            C2 = max(C2, _needed(east, west, p.frontage, head_b=cw))

    placement: dict[str, Box] = {}
    for k, (south, north, east, west) in enumerate(plans):
        z = k * H_MM
        placement[f"corridor_{k}" if segments == 1 else f"corridor_{k}_1"] = Box(0, 0, z, C1, cw, H_MM)
        placement.update(_pack_side(south, 0, 0, z, below=True))
        placement.update(_pack_side(north, 0, cw, z, below=False))
        if segments == 2:
            placement[f"corridor_{k}_2"] = Box(C1, 0, z, cw, C2, H_MM)
            placement.update(_pack_side(east, 0, C1 + cw, z, below=False, along="y"))
            placement.update(_pack_side(west, cw, C1, z, below=True, along="y"))

    circulation: dict = {"corridor": {"w": p.corridor_w, "l": round(C1 / 1000, 3)}}
    if segments == 2:
        circulation["corridor"]["segments"] = 2
    if p.levels > 1:
        circulation["stairs"] = [{"name": "stair", "w": 3.0, "l": 5.0}]
        circulation["lifts"] = [{"name": "lift", "w": 2.5, "l": 2.5}]
        if segments == 1:
            placement["stair"] = Box(C1, 0, 0, 5000, 3000, p.levels * H_MM)      # end-on at +x
        else:
            placement["stair"] = Box(C1, C2, 0, 3000, 5000, p.levels * H_MM)     # end-on at segment 2's far end
        placement["lift"] = Box(-2500, 0, 0, 2500, 2500, p.levels * H_MM)        # end-on at -x

    by_level = {n: k for k, rooms_k in enumerate(per_level) for n, _, _ in rooms_k}
    spaces = [Space(name=n, w=_nominal(w_mm, p.t, rng), l=_nominal(d_mm, p.t, rng), h=H_MM / 1000,
                    tol=p.t, wishes={"level": by_level[n]} if p.levels > 1 else {})
              for n, w_mm, d_mm in dims]
    name = (f"planted_b_r{p.rooms}_t{int(p.t * 100)}_f{int(p.frontage * 100)}_{p.shape.lower()}"
            f"_{'dbl' if p.double_loaded else 'sgl'}_l{p.levels}_s{seed}")
    brief = Brief(name=name, spaces=spaces, levels=p.levels, level_height=H_MM / 1000, circulation=circulation)
    return brief, placement


def _needed(side_a: list, side_b: list, frontage: float, head_b: int = 0) -> int:
    """Corridor length (mm): the rooms' widths fill `frontage` of the segment's two sides, and each side
    still fits its own rooms (side b packs from `head_b` in, clearing the L's inner corner)."""
    ta, tb = sum(w for _, w, _ in side_a), sum(w for _, w, _ in side_b)
    by_frontage = int((ta + tb) / (2 * frontage)) if ta + tb else 0
    return max(by_frontage, ta, tb + head_b, 3_000)


def _balance(group: list[tuple[str, int, int]], rng: random.Random):
    group = list(group)
    rng.shuffle(group)
    a: list = []
    b: list = []
    for item in group:  # greedy: each room to the emptier side
        (a if sum(w for _, w, _ in a) <= sum(w for _, w, _ in b) else b).append(item)
    return a, b


# --------------------------------------------------------------------------- entry

def plant(family: str, params: dict | None = None, seed: int = 0) -> tuple[Brief, dict[str, Box]]:
    params = dict(params or {})
    if family.lower() == "a":
        return plant_a(PlantedAParams(**params), seed)
    if family.lower() == "b":
        return plant_b(PlantedBParams(**params), seed)
    raise ValueError(f"unknown planted family {family!r}; choose A or B")
