"""M25: what boxes and tessellated cells have in common (PLAN §4.11).

Every space is a `Prism`: a plan polygon in integer millimetres between two heights. A box is a rectangle prism;
a Voronoi, power, sliced or grown cell is any simple polygon. `conform` gives neighbouring rings the same vertices,
after which a wall is one edge that two rings both hold. `Table` indexes those edges once and every reading comes
off it: shared wall, contact area, uncovered wall per direction, the walk graph, the affinity report and the scores.
On boxes the readings equal the integer-box ones (`affinity.measure`, `score.cheap_scores`); the M25 gate holds that.

Pure Python with shapely and numpy: no kernel, so it can be called on every drag.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import networkx as nx
import numpy as np
from shapely.geometry import Polygon, box as _rect
from shapely.geometry.polygon import orient

from . import affinity as _aff
from .brief import Brief, CIRCULATION
from .circulation import door_kind, door_spec
from .levels import level_height_mm
from .units import to_mm

CONFORM_MM = 1.5       # a vertex this close to a neighbour's wall is put on it
DOOR_CLEAR_MM = 2000   # wall height a door needs (the access-graph rule)
LEGACY_DOOR_MM = 900


@dataclass(frozen=True)
class Prism:
    poly: Polygon   # plan outline, coordinates in whole millimetres
    z0: int
    z1: int

    @property
    def h(self) -> int:
        return self.z1 - self.z0

    @property
    def area(self) -> float:
        return self.poly.area

    @property
    def volume(self) -> float:
        return self.poly.area * self.h

    def to_dict(self) -> dict:
        return {"z0": self.z0, "z1": self.z1, "ring": [[int(x), int(y)] for x, y in self.poly.exterior.coords[:-1]],
                "holes": [[[int(x), int(y)] for x, y in r.coords[:-1]] for r in self.poly.interiors]}

    @classmethod
    def from_dict(cls, d: dict) -> "Prism":
        return cls(Polygon(d["ring"], d.get("holes") or None), int(d["z0"]), int(d["z1"]))


Layout = dict[str, Prism]


def from_placement(placement: dict) -> Layout:
    """Integer boxes as prisms; nothing is lost, so every box reading can be repeated on the result."""
    return {n: Prism(_rect(b.x, b.y, b.x1, b.y1), b.z, b.z1) for n, b in placement.items()}


# ----------------------------------------------------------------------------- conforming

def _ring_ints(ring) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    for x, y in list(ring.coords)[:-1]:
        p = (int(round(x)), int(round(y)))
        if not out or out[-1] != p:
            out.append(p)
    if len(out) > 1 and out[0] == out[-1]:
        out.pop()
    k = 0
    while len(out) >= 3 and k < len(out):       # a vertex whose two neighbours coincide is a spike of no width: drop it
        if out[k - 1] == out[(k + 1) % len(out)]:
            del out[k]
            del out[k - 1 if k else len(out) - 1]
            k = max(0, k - 2)
        else:
            k += 1
    return out


def rings_of(poly: Polygon) -> list[list[tuple[int, int]]]:
    """Integer rings, shell counter-clockwise and holes clockwise, so the right of every edge is outside."""
    p = orient(poly, 1.0)
    return [r for r in ([_ring_ints(p.exterior)] + [_ring_ints(i) for i in p.interiors]) if len(r) >= 3]


def conform(layout: Layout, tol: float = CONFORM_MM) -> Layout:
    """Round every vertex to a whole millimetre and put each vertex that lies on a neighbour's wall into that wall,
    so two spaces that meet hold the same edges. A neighbour is a prism whose height range overlaps. A shaft passes
    a vertex from one level to the next, so the pass repeats until nothing moves. Idempotent."""
    for _ in range(6):
        out, changed = _conform_once(layout, tol)
        layout = out
        if not changed:
            break
    return layout


def _conform_once(layout: Layout, tol: float) -> tuple[Layout, bool]:
    names = list(layout)
    rings = {n: rings_of(layout[n].poly) for n in names}
    pts, owner = [], []
    for i, n in enumerate(names):
        for r in rings[n]:
            pts.extend(r)
            owner.extend([i] * len(r))
    if not pts:
        return dict(layout), False
    changed = False
    P = np.array(pts, dtype=float)
    own = np.array(owner)
    z0 = np.array([layout[n].z0 for n in names])
    z1 = np.array([layout[n].z1 for n in names])
    out: Layout = {}
    for i, n in enumerate(names):
        near = (own != i) & (np.minimum(z1[own], z1[i]) > np.maximum(z0[own], z0[i]))
        if rings[n]:
            xs = [p[0] for r in rings[n] for p in r]
            ys = [p[1] for r in rings[n] for p in r]
            near &= (P[:, 0] >= min(xs) - tol) & (P[:, 0] <= max(xs) + tol) & (P[:, 1] >= min(ys) - tol) & (P[:, 1] <= max(ys) + tol)
        Q = P[near]
        new_rings = []
        for r in rings[n]:
            if not len(Q):
                new_rings.append(r)
                continue
            nr: list[tuple[int, int]] = []
            for k, a in enumerate(r):
                b = r[(k + 1) % len(r)]
                nr.append(a)
                d = np.array([b[0] - a[0], b[1] - a[1]], dtype=float)
                L2 = float(d @ d)
                rel = Q - np.array(a, dtype=float)
                t = (rel @ d) / L2
                dist = np.abs(rel[:, 0] * d[1] - rel[:, 1] * d[0]) / math.sqrt(L2)
                hit = (t > 0) & (t < 1) & (dist <= tol)
                if hit.any():
                    seen = {a, b}
                    for j in np.argsort(t[hit]):
                        q = (int(Q[hit][j][0]), int(Q[hit][j][1]))
                        if q not in seen:
                            seen.add(q)
                            nr.append(q)
                            changed = True
            new_rings.append(nr)
        poly = Polygon(new_rings[0], new_rings[1:] or None) if new_rings else layout[n].poly
        out[n] = Prism(poly, int(layout[n].z0), int(layout[n].z1))
    return out, changed


# ----------------------------------------------------------------------------- the edge table

def _line(a: tuple[int, int], b: tuple[int, int]) -> tuple:
    """Exact key of the directed wall line through a→b: primitive direction and offset. Collinear edges that face
    the same way share it; a box side is one line."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    g = math.gcd(abs(dx), abs(dy)) or 1
    dx, dy = dx // g, dy // g
    return dx, dy, a[0] * dy - a[1] * dx


def _bearing(a: tuple[int, int], b: tuple[int, int]) -> float:
    """Outward normal of edge a→b (outside is on the right), in degrees clockwise from plan +y."""
    return math.degrees(math.atan2(b[1] - a[1], -(b[0] - a[0]))) % 360


class Table:
    """All walls of a layout, indexed once. Lengths in mm, areas in mm²."""

    def __init__(self, layout: Layout, conformed: bool = False):
        self.layout = layout if conformed else conform(layout)
        self.names = list(self.layout)
        self.walls: dict[str, list[tuple[tuple, float, tuple, float]]] = {}   # name -> (edge key, length, line, bearing)
        holders: dict[tuple, list[str]] = {}
        for n, p in self.layout.items():
            ws = []
            for r in rings_of(p.poly):
                for k, a in enumerate(r):
                    b = r[(k + 1) % len(r)]
                    key = (a, b) if a <= b else (b, a)
                    ws.append((key, math.hypot(b[0] - a[0], b[1] - a[1]), _line(a, b), _bearing(a, b)))
                    holders.setdefault(key, []).append(n)
            self.walls[n] = ws
        self.holders = holders
        self._lat: dict[frozenset, dict[tuple, float]] = {}
        for n, ws in self.walls.items():
            for key, length, line, _b in ws:
                for m in holders[key]:
                    if m != n and self.zlap(n, m) > 0:
                        per = self._lat.setdefault(frozenset((n, m)), {})
                        lk = (n, line)   # summed once per holder; `touch` reads one holder's lines
                        per[lk] = per.get(lk, 0.0) + length
        self._vert: dict[frozenset, float] | None = None
        self._walks: dict[int, nx.Graph] = {}

    # --- pairs
    def zlap(self, a: str, b: str) -> int:
        A, B = self.layout[a], self.layout[b]
        return max(0, min(A.z1, B.z1) - max(A.z0, B.z0))

    def touch(self, a: str, b: str) -> tuple[float, int]:
        """(longest shared straight wall, shared height); (0, 0) when the two share no vertical wall."""
        per = self._lat.get(frozenset((a, b)))
        if not per:
            return 0.0, 0
        return max(v for (n, _l), v in per.items() if n == a), self.zlap(a, b)

    def lateral(self, a: str, b: str) -> float:
        per = self._lat.get(frozenset((a, b)))
        return sum(v for (n, _l), v in per.items() if n == a) * self.zlap(a, b) if per else 0.0

    @property
    def vert(self) -> dict[frozenset, float]:
        """Plan overlap of every pair where one's ceiling is the other's floor."""
        if self._vert is None:
            self._vert = {}
            by_floor: dict[int, list[str]] = {}
            for n, p in self.layout.items():
                by_floor.setdefault(p.z0, []).append(n)
            for a, A in self.layout.items():
                ab = A.poly.bounds
                for b in by_floor.get(A.z1, []):
                    bb = self.layout[b].poly.bounds
                    if ab[0] >= bb[2] or bb[0] >= ab[2] or ab[1] >= bb[3] or bb[1] >= ab[3]:
                        continue
                    area = A.poly.intersection(self.layout[b].poly).area
                    if area >= 1.0:
                        self._vert[frozenset((a, b))] = area
        return self._vert

    def vertical(self, a: str, b: str) -> float:
        return self.vert.get(frozenset((a, b)), 0.0)

    def contact(self, a: str, b: str) -> float:
        return self.lateral(a, b) + self.vertical(a, b)

    def pairs(self) -> set[frozenset]:
        return set(self._lat) | set(self.vert)

    # --- one space against the outside
    def uncovered(self, a: str) -> dict[tuple, tuple[float, float]]:
        """Per wall line: (length not covered by a neighbour as tall as the space, bearing of the outward normal)."""
        A = self.layout[a]
        out: dict[tuple, tuple[float, float]] = {}
        for key, length, line, bearing in self.walls[a]:
            covered = any(m != a and self.layout[m].z0 <= A.z0 and self.layout[m].z1 >= A.z1 for m in self.holders[key])
            have = out.get(line, (0.0, bearing))[0]
            out[line] = (have + (0.0 if covered else length), bearing)
        return out

    def outside(self, a: str, bearing: float | None = None) -> float:
        """Longest uncovered straight wall; with `bearing`, among walls whose normal is within 45° of it."""
        best = 0.0
        for u, b in self.uncovered(a).values():
            if bearing is None or round(min((b - bearing) % 360, (bearing - b) % 360), 9) <= 45:
                best = max(best, u)
        return best

    # --- walking
    def walk(self, brief: Brief) -> nx.Graph:
        g = self._walks.get(id(brief))
        if g is None:
            g = self._walks[id(brief)] = (self._door_graph(brief) if brief.circulation
                                          else self._path_graph(brief) if getattr(brief, "paths", None)
                                          else self._access_graph(brief))
        return g

    def _access_graph(self, brief: Brief) -> nx.Graph:
        """`doors.access_graph`: door-wide walls, plus two cores of one program stacked on each other."""
        g = nx.Graph()
        g.add_nodes_from(self.names)
        for pair in self._lat:
            a, b = tuple(pair)
            u, v = self.touch(a, b)
            if u >= LEGACY_DOOR_MM and v >= DOOR_CLEAR_MM:
                g.add_edge(a, b)
        for pair in self.vert:
            a, b = tuple(pair)
            sa, sb = brief.space(a), brief.space(b)
            if sa.is_vertical and sa.program == sb.program:
                g.add_edge(a, b)
        return g

    def _path_graph(self, brief: Brief) -> nx.Graph:
        """Field briefs: a room opens onto a path cell through a door-wide wall, path cells open onto each other,
        and two rooms are joined only where the brief asks for that contact."""
        spec = door_spec(brief)
        need = to_mm(spec["room"]["w"] + 2 * spec["jamb"])
        required = brief.required_pairs()
        g = nx.Graph()
        g.add_nodes_from(self.names)
        for pair in self._lat:
            a, b = tuple(pair)
            ca, cb = brief.space(a).program in CIRCULATION, brief.space(b).program in CIRCULATION
            u, v = self.touch(a, b)
            if v < DOOR_CLEAR_MM:
                continue
            if (ca and cb and u >= LEGACY_DOOR_MM) or ((ca or cb or pair in required) and not (ca and cb) and u >= need):
                g.add_edge(a, b)
        return g

    def _door_graph(self, brief: Brief) -> nx.Graph:
        """The pairs `doors.plan_doors` joins and the openings `doors.door_graph` adds, read from walls alone."""
        from .doors import corridor_opening_mm
        H = level_height_mm(brief)
        spec = door_spec(brief)
        jamb = to_mm(spec["jamb"])
        L = self.layout

        def wall(a: str, b: str, k: int) -> float:
            z0, z1 = k * H, (k + 1) * H
            if min(L[a].z1, z1) <= max(L[a].z0, z0) or min(L[b].z1, z1) <= max(L[b].z0, z0):
                return 0.0
            return self.touch(a, b)[0]

        g = nx.Graph()
        g.add_nodes_from(s.name for s in brief.spaces)

        def door(a: str, b: str, kind: str, k: int) -> None:
            if wall(a, b, k) >= to_mm(spec[kind]["w"]) + 2 * jamb and wall(a, b, k) > 0:
                g.add_edge(a, b, kind=kind, level=k)

        corridors_on: dict[int, list[str]] = {}
        for c in brief.spaces:
            if c.program == "corridor" and c.name in L:
                corridors_on.setdefault(L[c.name].z0 // H, []).append(c.name)
        for s in brief.spaces:
            if not s.is_shaft or s.name not in L:
                continue
            for k in range(s.serves[0], s.serves[1] + 1):
                cands = corridors_on.get(k, [])
                if cands:
                    door(s.name, max(cands, key=lambda c: wall(s.name, c, k)), door_kind(s.program), k)
        required = brief.required_pairs()
        need_room = to_mm(spec["room"]["w"]) + 2 * jamb
        for s in brief.spaces:
            if s.program != "room" or s.name not in L:
                continue
            k = L[s.name].z0 // H
            cands = []
            for c in brief.spaces:
                if c.program != "corridor" or c.name not in L or L[c.name].z0 // H != k:
                    continue
                have = wall(s.name, c.name, k)
                if have > 0:
                    cands.append((have >= need_room, frozenset((s.name, c.name)) in required, have, c.name))
            if cands:
                door(s.name, max(cands)[3], "room", k)
        shafts = {s.name for s in brief.spaces if s.is_shaft}
        for a, b in brief.door_pairs:
            if a in shafts or b in shafts or a not in L or b not in L:
                continue
            if brief.space(a).program == "room" and brief.space(b).program == "room":
                door(a, b, "room", L[a].z0 // H)
        cs = [s for s in brief.spaces if s.program == "corridor" and s.name in L]
        for i, ca in enumerate(cs):
            for cb in cs[i + 1:]:
                need = corridor_opening_mm(brief, ca.name, cb.name)
                if need and self.touch(ca.name, cb.name)[0] >= need:
                    g.add_edge(ca.name, cb.name, kind="opening", level=int(ca.wishes.get("level", 0)))
        return g


def table(x) -> Table:
    return x if isinstance(x, Table) else Table(x)


# ----------------------------------------------------------------------------- affinity, on any layout

def affinity(brief: Brief, layout, *, strengths: tuple[str, ...] | None = None, kinds: tuple[str, ...] | None = None) -> dict:
    """`affinity.measure` for any layout: the same report, each kind read from walls instead of box sides."""
    t = table(layout)
    L = t.layout
    H = level_height_mm(brief)
    north, _hemi = _aff.site_of(brief)
    hemi = _hemi

    def levels(p: Prism) -> tuple[int, int]:
        return p.z0 // H, (p.z1 - 1) // H

    top = max((levels(p)[1] for p in L.values()), default=0)
    metres = lambda mm: round(mm / 1000, 6)  # noqa: E731

    def pair(af, a: str, o: str):
        A, B = L[a], L[o]
        p = af.params
        if af.kind == "touch":
            u = t.touch(a, o)[0]
            return u >= to_mm(p["min"]) and u > 0, metres(u), p["min"], "m"
        if af.kind == "apart":
            area = t.contact(a, o)
            return area == 0, round(area / 1e6, 6), 0, "m2"
        if af.kind == "near":
            g = t.walk(brief)
            if a not in g or o not in g or not nx.has_path(g, a, o):
                return (False, None, p["depth"], "doors") if a in g and o in g else None
            d = nx.shortest_path_length(g, a, o)
            return d <= p["depth"], d, p["depth"], "doors"
        if af.kind == "stack":
            adjacent = A.z1 == B.z0 or B.z1 == A.z0
            share = t.vertical(a, o) / min(A.area, B.area) if adjacent else 0.0
            return adjacent and share >= p["overlap"] - 1e-9, round(share, 6), p["overlap"], "share"
        (a0, a1), (b0, b1) = levels(A), levels(B)
        gap = max(a0 - b1, b0 - a1, 0)
        return gap == 0, gap, 0, "levels"

    def site(af, a: str):
        p = af.params
        if af.kind in ("facade", "exterior"):
            if af.kind == "facade":
                side = p["side"]
                if side == "sun":
                    side = "N" if hemi == "S" else "S"
                u = t.outside(a, (north + _aff.COMPASS[side]) % 360)
            else:
                u = t.outside(a)
            return u >= to_mm(p["min"]) and u > 0, metres(u), p["min"], "m"
        lv = levels(L[a])
        if af.kind == "ground":
            return L[a].z0 == 0, lv[0], 0, "level"
        return lv[1] == top, lv[1], top, "level"

    return _aff.report(brief, L, pair, site, strengths=strengths, kinds=kinds)


# ----------------------------------------------------------------------------- scores, on any layout

def adjacency(brief: Brief, t: Table) -> float:
    """Required contacts realised."""
    req = brief.required_pairs()
    return len(req & t.pairs()) / len(req) if req else 1.0


def compactness(t: Table) -> float:
    """Cube-equivalent form factor: surface of a cube of the same volume over the external surface."""
    L = t.layout
    vol = sum(p.volume for p in L.values()) / 1e9
    surf = sum(2 * p.area + p.poly.length * p.h for p in L.values())
    shared = sum(t.contact(*tuple(pair)) for pair in t.pairs())
    ext = (surf - 2 * shared) / 1e6
    if ext <= 0 or vol <= 0:
        return 0.0
    return min(1.0, 6 * (vol ** (2 / 3)) / ext)


def circulation(brief: Brief, t: Table) -> float:
    circ = sum(p.area for n, p in t.layout.items() if brief.space(n).program in CIRCULATION)
    net = sum(p.area for n, p in t.layout.items() if brief.space(n).program == "room")
    return circ / net if net else 0.0


def reach(brief: Brief, t: Table) -> float:
    """`score.vertical`: the share of spaces in the largest walkable component."""
    g = t.walk(brief)
    if g.number_of_nodes() == 0:
        return 0.0
    return max(len(c) for c in nx.connected_components(g)) / g.number_of_nodes()


def daylight(brief: Brief, t: Table) -> float:
    rooms = [n for n in t.layout if brief.space(n).program == "room"]
    if not rooms:
        return 0.0
    return sum(1 for n in rooms if any(u > 0 for u, _b in t.uncovered(n).values())) / len(rooms)


def envelope_volume_mm3(brief: Brief) -> float:
    if brief.envelope:
        return to_mm(brief.envelope["w"]) * to_mm(brief.envelope["l"]) * to_mm(brief.envelope["h"])
    return 0.0


def area_deviation(brief: Brief, t: Table) -> float:
    """Mean fractional difference between a room's plan area and the area the brief asks (w × l)."""
    rooms = [(n, p) for n, p in t.layout.items() if brief.space(n).program == "room"]
    if not rooms:
        return 0.0
    tot = 0.0
    for n, p in rooms:
        s = brief.space(n)
        want = s.nominal_mm("w") * s.nominal_mm("l")
        tot += abs(p.area - want) / want
    return tot / len(rooms)


def exposure(brief: Brief, t: Table) -> float:
    """Share of the rooms' wall length that faces outside."""
    out = wall = 0.0
    for n, p in t.layout.items():
        if brief.space(n).program == "room":
            out += sum(u for u, _b in t.uncovered(n).values())
            wall += p.poly.length
    return out / wall if wall else 0.0


def regularity(brief: Brief, t: Table) -> float:
    """How room-like the plans are: mean of plan area over the area of the tightest rectangle around it."""
    vals = [p.area / p.poly.minimum_rotated_rectangle.area for n, p in t.layout.items()
            if brief.space(n).program == "room" and p.area > 0]
    return sum(vals) / len(vals) if vals else 0.0


def path_depth(brief: Brief, t: Table) -> float:
    """Mean number of doors from a room to the nearest circulation cell; a room that reaches none counts `far`."""
    g = t.walk(brief)
    circ = {n for n in t.layout if brief.space(n).program in CIRCULATION}
    rooms = [n for n in t.layout if brief.space(n).program == "room"]
    if not rooms or not circ:
        return 0.0
    far = len(t.layout)
    dist = nx.multi_source_dijkstra_path_length(g, circ & set(g)) if circ & set(g) else {}
    return sum(dist.get(n, far) for n in rooms) / len(rooms)


def scores(brief: Brief, layout) -> dict[str, float]:
    """Every reading that is defined for any layout. The first seven equal `score.cheap_scores` on boxes."""
    t = table(layout)
    env = envelope_volume_mm3(brief)
    out = {
        "adjacency": adjacency(brief, t),
        "compactness": compactness(t),
        "circulation": circulation(brief, t),
        "vertical": reach(brief, t),
        "envelope_fit": min(1.0, sum(p.volume for p in t.layout.values()) / env) if env else 0.0,
        "daylight": daylight(brief, t),
        "affinity": affinity(brief, t)["score"],
        "area_deviation": area_deviation(brief, t),
        "exposure": exposure(brief, t),
        "regularity": regularity(brief, t),
        "path_depth": path_depth(brief, t),
    }
    return {k: round(v, 6) for k, v in out.items()}


BOX_EQUAL = ("adjacency", "compactness", "circulation", "vertical", "envelope_fit", "daylight", "affinity")
