"""M27: field briefs (PLAN §4.11). A schedule of spaces with areas and affinities, a site outline and one or more
paths drawn through it; contacts are not written, they emerge.

    site:   {boundary: [[x, y], ...], setback: 2}        metres; `envelope` (a rectangle) also works
    paths:  [{name, points: [[x, y] | [x, y, level], ...], width: 2.0, stair: 4.5}]

Steps, each kernel-free: `prepare` turns the paths into path cells (a strip per level, a stair where the path
changes level) and fixes how many levels the schedule needs; `relax` lets the rooms find places as discs (affinities
and the path pull and push); `build` tessellates each level's ground among them and returns a `layout.Layout`;
`evaluate` reads it. `solve` is the one call the canvas makes on every drag. `options` is the spacetope tradition:
many candidates, and for each aspect of the volume the one that does it best, built and verified in topologic.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field as _field

import numpy as np
import shapely
import shapely.affinity
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import split, substring

from . import affinity as _aff
from . import layout as _layout
from .brief import Brief, Space
from .circulation import Problem
from .layout import Layout, Prism
from .tessellate import KINDS, Seed, tessellate

PACK = 0.88           # centre distance over the sum of two radii: equal discs tile at 0.952; a little closer lets rooms
#                       stand side by side along a path and take their depth behind
COVER = 0.85          # share of the buildable ground a level may fill before the schedule goes up a level
DEFAULT_WIDTH = 2.0
DEFAULT_STAIR = 4.5


class FieldInvalid(ValueError):
    def __init__(self, problems: list[Problem]):
        self.problems = problems
        super().__init__("; ".join(p.message for p in problems))


def is_field(brief: Brief) -> bool:
    return bool(brief.paths) or (isinstance(brief.site, dict) and bool(brief.site.get("boundary")))


# ----------------------------------------------------------------------------- site and paths

def buildable(brief: Brief) -> Polygon:
    """The ground rooms may stand on, in metres: the site boundary moved in by the setback, or the envelope."""
    site = brief.site if isinstance(brief.site, dict) else {}
    if site.get("boundary"):
        poly = Polygon([(float(p[0]), float(p[1])) for p in site["boundary"]])
        if not poly.is_valid:
            poly = poly.buffer(0)
        back = float(site.get("setback", 0) or 0)
        if back > 0:
            poly = poly.buffer(-back, join_style="mitre")
        parts = [g for g in getattr(poly, "geoms", [poly]) if g.area > 0]
        if not parts:
            raise FieldInvalid([Problem("site_boundary", "site: nothing is left of the boundary inside the setback")])
        return max(parts, key=lambda g: g.area)
    if brief.envelope:
        return box(0, 0, brief.envelope["w"], brief.envelope["l"])
    raise FieldInvalid([Problem("site_boundary", "a field brief needs site.boundary (a list of [x, y] points) or an envelope")])


@dataclass(frozen=True)
class PathCell:
    name: str
    path: str
    program: str       # corridor | stair
    poly: Polygon      # metres
    k0: int            # first level it stands on
    k1: int            # last level (inclusive)
    width: float
    length: float


def _level_height(brief: Brief) -> float:
    return float(brief.level_height or max(s.h for s in brief.spaces))


def level_count(brief: Brief, ground: Polygon) -> int:
    """`levels` when the brief says, else the fewest levels on which the rooms fit: no room left, stack up."""
    if brief.levels:
        return int(brief.levels)
    rooms = sum(s.w * s.l for s in brief.spaces if s.program in ("room", "void"))
    paths = sum(float(p.get("width", DEFAULT_WIDTH)) * LineString([q[:2] for q in p["points"]]).length for p in brief.paths)
    free = max(1e-6, COVER * ground.area - paths)
    top = max((int(q[2]) for p in brief.paths for q in p["points"] if len(q) > 2), default=0)
    return max(1, top + 1, math.ceil(rooms / free))


def path_cells(brief: Brief, ground: Polygon, n: int) -> list[PathCell]:
    """A path with plain [x, y] points runs on every level, with one stair over its first metres when there is more
    than one level. A path whose points carry a level runs where they say; a leg between two levels is a stair that
    stands on both."""
    out: list[PathCell] = []
    taken: dict[int, list[Polygon]] = {}

    def add(name: str, pname: str, program: str, line: LineString, k0: int, k1: int, width: float) -> None:
        if line.length <= 0:
            return
        poly = line.buffer(width / 2, cap_style="flat", join_style="mitre").intersection(ground)
        for k in range(k0, k1 + 1):
            for other in taken.get(k, []):
                poly = poly.difference(other)
        parts = [g for g in getattr(poly, "geoms", [poly]) if g.geom_type == "Polygon" and g.area > 0.05]
        if not parts:
            return
        poly = max(parts, key=lambda g: g.area)
        for k in range(k0, k1 + 1):
            taken.setdefault(k, []).append(poly)
        out.append(PathCell(name, pname, program, poly, k0, k1, width, line.length))

    for p in brief.paths:
        pname = str(p["name"])
        width = float(p.get("width", DEFAULT_WIDTH))
        pts = [tuple(float(c) for c in q) for q in p["points"]]
        if all(len(q) == 2 for q in pts):
            line = LineString(pts)
            cut = min(float(p.get("stair", DEFAULT_STAIR)), 0.4 * line.length) if n > 1 else 0.0
            if cut > 0:
                add(f"{pname}_stair", pname, "stair", substring(line, 0, cut), 0, n - 1, width)
            for k in range(n):
                add(f"{pname}_{k}", pname, "corridor", substring(line, cut, line.length), k, k, width)
            continue
        level = 0
        legs = []
        for q in pts:
            level = int(q[2]) if len(q) > 2 else level
            legs.append((q[0], q[1], min(max(level, 0), n - 1)))
        run = [legs[0]]
        stairs = runs = 0
        used: dict[int, int] = {}

        def close() -> None:
            nonlocal runs
            if len(run) > 1:
                k = run[0][2]
                used[k] = used.get(k, 0) + 1
                add(f"{pname}_{k}" + ("" if used[k] == 1 else "abcdefgh"[used[k] - 2]), pname, "corridor",
                    LineString([(x, y) for x, y, _ in run]), k, k, width)
                runs += 1
        for a, b in zip(legs, legs[1:]):
            if a[2] == b[2]:
                run.append(b)
                continue
            close()
            stairs += 1
            add(f"{pname}_stair" + ("" if stairs == 1 else f"_{stairs}"), pname, "stair", LineString([a[:2], b[:2]]),
                min(a[2], b[2]), max(a[2], b[2]), width)
            run = [b]
        close()
    return out


def validate(brief: Brief) -> list[Problem]:
    out: list[Problem] = []
    names = {s.name for s in brief.spaces}
    seen = set()
    for i, p in enumerate(brief.paths):
        if not isinstance(p, dict) or "name" not in p or len(p.get("points") or []) < 2:
            out.append(Problem("path", f"paths[{i}] needs a name and at least two points"))
            continue
        nm = str(p["name"])
        if nm in names or nm in seen:
            out.append(Problem("path", f"path name {nm!r} is already used"))
        seen.add(nm)
        if any(len(q) not in (2, 3) for q in p["points"]):
            out.append(Problem("path", f"path {nm}: a point is [x, y] or [x, y, level]"))
        if float(p.get("width", DEFAULT_WIDTH)) <= 0:
            out.append(Problem("path", f"path {nm}: width must be positive"))
    site = brief.site if isinstance(brief.site, dict) else {}
    if site.get("boundary") is not None and (not isinstance(site["boundary"], list) or len(site["boundary"]) < 3):
        out.append(Problem("site_boundary", "site: boundary needs at least three [x, y] points"))
    if not any(s.program == "room" for s in brief.spaces):
        out.append(Problem("empty", "the brief has no rooms"))
    return out + _aff.validate_site(brief) + [p for p in _aff.validate(brief) if p.severity == "error"]


@dataclass
class Field:
    """A prepared field brief: the expanded brief (rooms plus path cells), the ground and the levels."""
    brief: Brief
    ground: Polygon
    cells: list[PathCell]
    levels: dict[str, int]
    n: int
    H: float
    source: Brief = None
    fronts: dict = _field(default_factory=dict)   # room -> the path cell its brief says it must open onto

    def rooms(self, k: int | None = None) -> list[Space]:
        return [s for s in self.brief.spaces if s.program in ("room", "void") and (k is None or self.levels.get(s.name) == k)]

    def occupied(self, k: int):
        ps = [c.poly for c in self.cells if c.k0 <= k <= c.k1]
        return shapely.union_all(ps) if ps else Polygon()

    def cuts(self, k: int) -> list[LineString]:
        """The centre lines of the paths that stand on level k, run on at both ends to beyond the outline."""
        x0, y0, x1, y1 = self.ground.bounds
        far = 2 * math.hypot(x1 - x0, y1 - y0)
        out = []
        for p in self.brief.paths:
            if not any(c.path == str(p["name"]) and c.k0 <= k <= c.k1 for c in self.cells):
                continue
            pts = [(float(q[0]), float(q[1])) for q in p["points"]]
            pts = [a for i, a in enumerate(pts) if i == 0 or a != pts[i - 1]]
            if len(pts) < 2:
                continue
            (ax, ay), (bx, by) = pts[0], pts[1]
            d = math.hypot(bx - ax, by - ay)
            head = (ax - far * (bx - ax) / d, ay - far * (by - ay) / d)
            (ax, ay), (bx, by) = pts[-2], pts[-1]
            d = math.hypot(bx - ax, by - ay)
            tail = (bx + far * (bx - ax) / d, by + far * (by - ay) / d)
            out.append(LineString([head, *pts, tail]))
        return out

    def angle(self) -> float:
        """Direction of the longest path leg (else the longest site edge), for the tessellations that have axes."""
        best = (0.0, 0.0)
        lines = [LineString([q[:2] for q in p["points"]]) for p in self.brief.paths] or [self.ground.exterior]
        for line in lines:
            cs = list(line.coords)
            for a, b in zip(cs, cs[1:]):
                d = math.hypot(b[0] - a[0], b[1] - a[1])
                if d > best[0]:
                    best = (d, math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])) % 90)
        return best[1]


def prepare(brief: Brief, seed: int = 0) -> Field:
    """Validate, make the path cells, count the levels and give every room one."""
    problems = validate(brief)
    if problems:
        raise FieldInvalid(problems)
    ground = buildable(brief)
    n = level_count(brief, ground)
    H = _level_height(brief)
    cells = path_cells(brief, ground, n)
    spaces = [s for s in brief.spaces]
    for c in cells:
        if c.program == "stair":
            spaces.append(Space(name=c.name, w=c.width, l=round(c.length, 3), h=round(H * (c.k1 - c.k0 + 1), 3), program="stair",
                                wishes={"path": c.path, "generated": True}, serves=(c.k0, c.k1)))
        else:
            spaces.append(Space(name=c.name, w=c.width, l=round(c.length, 3), h=H, program="corridor",
                                wishes={"path": c.path, "level": c.k0, "generated": True}))
    path_names = {str(p["name"]) for p in brief.paths}
    plain = [(a, b) for a, b in brief.contacts if a not in path_names and b not in path_names]

    def make(contacts: list) -> Brief:
        return Brief(name=brief.name, spaces=spaces, contacts=contacts, envelope=brief.envelope, levels=n, level_height=H,
                     door_pairs=[d for d in brief.door_pairs if tuple(d) in plain], affinities=brief.affinities,
                     site=brief.site, paths=brief.paths, expanded=True)
    from .levels import assign_levels
    lv = {k: int(v) for k, v in assign_levels(make(plain), seed).items()}
    together = [(a, b) for a, b in plain]          # rooms that must share a wall must share a level
    if _aff.written(brief):
        together += [(af.a, o) for af in _aff.expand(make(plain)) if af.kind == "touch" and af.strength == "must" for o in af.others[:1]]
    for _ in range(len(together)):
        moved = False
        for a, b in together:
            if a in lv and b in lv and lv[a] != lv[b]:
                lv[b] = lv[a]
                moved = True
        if not moved:
            break
    fronts: dict[str, str] = {}
    for a, b in brief.contacts:   # a contact with a path becomes a contact with that path's cell on the room's level
        room, path = (a, b) if b in path_names else (b, a) if a in path_names else (None, None)
        if room is None or room in path_names:
            continue
        on = [c.name for c in cells if c.path == path and c.program == "corridor" and c.k0 == lv.get(room, 0)]
        on = on or [c.name for c in cells if c.path == path and c.k0 <= lv.get(room, 0) <= c.k1]
        if on:
            fronts[room] = on[0]
    return Field(make(plain + sorted(fronts.items())), ground, cells, lv, n, H, brief, fronts)


# ----------------------------------------------------------------------------- relaxation

def radius(s: Space) -> float:
    return math.sqrt(s.w * s.l / math.pi)


def relax(f: Field, seed: int = 0, start: dict | None = None, pins: tuple[str, ...] = (), iters: int = 240,
          front: bool = True) -> dict[str, tuple[float, float]]:
    """Rooms as discs. Discs on one level do not overlap; a required contact or a `touch`/`near` wish draws two
    together and `apart` pushes them off; every room is drawn to the edge of the path on its level and kept off it;
    `stack` lines rooms up across levels; `facade` and `exterior` lean on the outline. With `front` (the default) a
    room never leaves the band beside the path, so every room can have its door on it; without, rooms may settle in
    a second row and the `reach` check says which. Same seed, same answer."""
    rooms = f.rooms()
    if not rooms:
        return {}
    rng = np.random.default_rng(seed)
    names = [s.name for s in rooms]
    idx = {n: i for i, n in enumerate(names)}
    R = np.array([radius(s) for s in rooms])
    lev = np.array([f.levels.get(n, 0) for n in names])
    x0, y0, x1, y1 = f.ground.bounds
    fixed = np.array([n in pins for n in names])
    inside = [f.ground.buffer(-0.5 * r) for r in R]
    inside = [g if not g.is_empty else f.ground for g in inside]
    paths = {k: f.occupied(k) for k in range(f.n)}
    same = lev[:, None] == lev[None, :]
    pack = np.full(len(rooms), PACK)
    for k in range(f.n):          # where the path is short for the rooms that want it, they stand closer and go deeper
        sel = lev == k
        front = sum(2 * c.length for c in f.cells if c.program == "corridor" and c.k0 == k)
        if sel.any() and front > 0:
            pack[sel] = min(PACK, max(0.6, 0.8 * front / float(2 * R[sel].sum())))
    want = np.minimum(pack[:, None], pack[None, :]) * (R[:, None] + R[None, :])

    pull = np.zeros((len(rooms), len(rooms)))       # draw together (same level)
    push = np.zeros_like(pull)                      # keep apart
    stack = np.zeros_like(pull)                     # line up across levels
    lean = np.zeros((len(rooms), 2))                # towards a side of the site
    out = np.zeros(len(rooms))                      # towards the outline
    fronts = np.full(len(rooms), 0.3)               # towards the path
    for a, b in f.brief.contacts:
        if a in idx and b in idx:
            pull[idx[a], idx[b]] = pull[idx[b], idx[a]] = 1.0
    for room in f.fronts:
        if room in idx:
            fronts[idx[room]] = 0.45
    north, hemi = _aff.site_of(f.brief)
    for af in _aff.expand(f.brief) if _aff.written(f.brief) else []:
        if af.a not in idx:
            continue
        i = idx[af.a]
        strong = 1.0 if af.strength in _aff.HARD else min(1.0, 0.35 * af.weight)
        neg = af.strength in _aff.NEGATIVE
        if af.kind in ("touch", "near", "apart"):
            for o in af.others:
                if o not in idx:
                    continue
                j = idx[o]
                attract = (af.kind != "apart") != neg
                m = pull if attract else push
                m[i, j] = m[j, i] = max(m[i, j], strong * (0.5 if af.kind == "near" else 1.0))
        elif af.kind == "stack" and not neg:
            for o in af.others:
                if o in idx:
                    stack[i, idx[o]] = stack[idx[o], i] = strong
        elif af.kind in ("facade", "exterior") and not neg:
            if af.kind == "exterior":
                out[i] = max(out[i], strong)
            else:
                side = af.params["side"]
                side = ("N" if hemi == "S" else "S") if side == "sun" else side
                b = math.radians((north + _aff.COMPASS[side]) % 360)
                lean[i] += strong * np.array([math.sin(b), math.cos(b)])
    P = np.zeros((len(rooms), 2))
    runs = {k: [(c, LineString(c.poly.exterior.coords)) for c in f.cells if c.program == "corridor" and c.k0 == k] for k in range(f.n)}
    centre = {str(p["name"]): LineString([q[:2] for q in p["points"]]) for p in f.brief.paths}
    import networkx as nx
    bonds = nx.Graph()
    bonds.add_nodes_from(range(len(rooms)))
    bonds.add_edges_from((i, j) for i in range(len(rooms)) for j in range(i + 1, len(rooms)) if pull[i, j] >= 0.6 and lev[i] == lev[j])
    draw: dict[int, tuple] = {}
    for comp in nx.connected_components(bonds):      # rooms bound to each other share a side and a stretch of path
        draw.update({i: (rng.random() < 0.5, float(rng.random()), int(rng.integers(1 << 30))) for i in comp} if len(comp) == 1
                    else (lambda sd, t, c: {i: (sd, t, c) for i in comp})(rng.random() < 0.5, float(rng.random()), int(rng.integers(1 << 30))))
    for i, n in enumerate(names):
        if start and n in start:
            P[i] = start[n]
            continue
        q = None
        if runs[lev[i]]:              # start beside the path, at a random place and side: nobody begins in a back row
            left, where, choice = draw[i]
            cell, _ = runs[lev[i]][choice % len(runs[lev[i]])]
            line = centre[cell.path]
            for attempt in range(40):
                t = float(np.clip(where + rng.normal(0, 0.04 + 0.02 * attempt), 0, 1)) * line.length
                a, b = line.interpolate(max(0.0, t - 0.5)), line.interpolate(min(line.length, t + 0.5))
                nx_, ny_ = -(b.y - a.y), (b.x - a.x)
                d = math.hypot(nx_, ny_) or 1.0
                side = 1.0 if left else -1.0
                off = cell.width / 2 + 0.8 * R[i]
                cand = (line.interpolate(t).x + side * off * nx_ / d, line.interpolate(t).y + side * off * ny_ / d)
                if f.ground.contains(Point(cand)):
                    q = cand
                    break
        if q is None:
            for _ in range(200):
                q = rng.uniform([x0, y0], [x1, y1])
                if f.ground.contains(Point(q)):
                    break
        P[i] = q
    scale = float(R.mean())
    for it in range(iters):
        cool = 1.0 - 0.8 * it / iters
        d = P[:, None, :] - P[None, :, :]
        dist = np.hypot(d[..., 0], d[..., 1]) + 1e-9
        u = d / dist[..., None]
        move = np.zeros_like(P)
        gap = want - dist
        np.fill_diagonal(gap, 0.0)
        sep = np.where(same & (gap > 0), gap, 0.0)                                    # discs must not overlap
        move += 0.5 * (sep[..., None] * u).sum(axis=1)
        far = np.where(same & (gap < 0), -gap, 0.0) * pull                            # wished neighbours close in
        move -= 0.12 * (far[..., None] * u).sum(axis=1)
        off = np.where(same & (dist < 1.6 * want), 1.6 * want - dist, 0.0) * push      # unwanted ones back off
        np.fill_diagonal(off, 0.0)
        move += 0.3 * (off[..., None] * u).sum(axis=1)
        move -= 0.08 * ((dist * stack)[..., None] * u).sum(axis=1)                    # stacks line up in plan
        for k in range(f.n):
            sel = np.flatnonzero(lev == k)
            if not len(sel):
                continue
            centre = P[sel].mean(axis=0)
            away = P[sel] - centre
            move[sel] -= 0.01 * away                                                   # hold the level together
            norm = np.hypot(away[:, 0], away[:, 1])[:, None] + 1e-9
            move[sel] += 0.25 * scale * out[sel][:, None] * away / norm
            path = paths[k]
            if path.is_empty:
                continue
            pts = shapely.points(P[sel])
            line = shapely.shortest_line(pts, path.boundary)
            near = shapely.get_coordinates(line).reshape(-1, 2, 2)[:, 1, :]
            v = P[sel] - near
            dd = np.hypot(v[:, 0], v[:, 1]) + 1e-9
            inside_path = shapely.contains(path, pts)
            dirn = np.where(inside_path[:, None], -v, v) / dd[:, None]
            signed = np.where(inside_path, -dd, dd)
            target = 0.8 * R[sel]
            move[sel] += np.where((signed < target)[:, None], 0.8 * (target - signed)[:, None] * dirn,
                                  -(fronts[sel] * (signed - target))[:, None] * dirn)
        move += 0.2 * scale * lean
        if it < iters // 3:
            move += rng.normal(0, 0.05 * scale * cool, P.shape)
        step = np.hypot(move[:, 0], move[:, 1])
        cap = 0.6 * scale * cool
        move *= np.minimum(1.0, cap / (step + 1e-9))[:, None]
        move[fixed] = 0.0
        P += move
        if it % 30 == 15 and it < 2 * iters // 3:     # along a path rooms cannot pass each other, so let them trade places
            def unrest(Q: np.ndarray) -> float:
                dq = Q[:, None, :] - Q[None, :, :]
                ds = np.hypot(dq[..., 0], dq[..., 1])
                return float((np.where(same, np.maximum(0.0, ds - want) * pull + np.maximum(0.0, 1.6 * want - ds) * push, 0.0)).sum())
            now = unrest(P)
            for i in rng.permutation(len(P)):
                if fixed[i] or not (pull[i] * same[i] * (dist[i] > 1.3 * want[i])).any():
                    continue
                best = None
                for m in np.flatnonzero(same[i] & ~fixed):
                    if m == i:
                        continue
                    Q = P.copy()
                    Q[[i, m]] = Q[[m, i]]
                    e = unrest(Q)
                    if e < now - 1e-6 and (best is None or e < best[0]):
                        best = (e, m)
                if best:
                    now, m = best
                    P[[i, m]] = P[[m, i]]
        if front:                  # every room keeps to the band beside its level's path and slides along it
            for k in range(f.n):
                sel = np.flatnonzero((lev == k) & ~fixed)
                path = paths[k]
                if not len(sel) or path.is_empty:
                    continue
                pts = shapely.points(P[sel])
                near = shapely.get_coordinates(shapely.shortest_line(pts, path.boundary)).reshape(-1, 2, 2)[:, 1, :]
                v = P[sel] - near
                dd = np.hypot(v[:, 0], v[:, 1]) + 1e-9
                inside_path = shapely.contains(path, pts)
                dirn = np.where(inside_path[:, None], -v, v) / dd[:, None]
                signed = np.where(inside_path, -dd, dd)
                P[sel] = near + dirn * np.clip(signed, 0.6 * R[sel], 0.95 * R[sel])[:, None]
        for i in range(len(P)):
            if not fixed[i] and not inside[i].contains(Point(P[i])):
                q = shapely.shortest_line(Point(P[i]), inside[i])
                P[i] = shapely.get_coordinates(q)[1]
    return {n: (round(float(P[i, 0]), 3), round(float(P[i, 1]), 3)) for i, n in enumerate(names)}


# ----------------------------------------------------------------------------- build

def _mass(f: Field, k: int, rooms: list[Space], positions: dict, fit: str, angle: float = 0.0):
    """[(ground, the rooms that divide it)] for level k: the whole buildable ground (`fit: site`), the mass that emerges round the
    discs and the path (`fit: mass`), or a band of even depth along the path (`fit: band`, what `slice` and `grid`
    get). The path cuts the ground into sides; on each side the mass grows until it holds the areas of
    the rooms standing there, so a room keeps its area whichever side it is on."""
    path = f.occupied(k)
    free = f.ground.difference(path)
    for line in f.cuts(k):            # a path that stops short of the outline still has two sides
        try:
            free = shapely.GeometryCollection([g for part in getattr(free, "geoms", [free]) for g in split(part, line).geoms])
        except (ValueError, shapely.errors.GEOSException):
            pass
    sides = [g for g in getattr(free, "geoms", [free]) if g.geom_type == "Polygon" and g.area > 0.5]
    if not sides:
        return [(free, rooms)]
    groups: list[list[Space]] = [[] for _ in sides]
    for s in rooms:
        pt = Point(positions[s.name])
        i = next((i for i, g in enumerate(sides) if g.covers(pt)), None)
        groups[min(range(len(sides)), key=lambda j: sides[j].distance(pt)) if i is None else i].append(s)
    out = []
    for side, group in zip(sides, groups):
        if not group:
            continue
        need = sum(s.w * s.l for s in group)
        if fit == "site" or need >= 0.97 * side.area:
            out.append((side, group))
            continue
        pts = [Point(positions[s.name]) for s in group]
        radii = [radius(s) for s in group]
        close = 0.5 * float(np.mean(radii))

        if fit == "band" and not path.is_empty:
            def grown(rho: float):
                return path.buffer(rho * 2 * close, join_style="mitre").intersection(side)
        else:
            def grown(rho: float):
                blob = shapely.union_all([p.buffer(rho * r, quad_segs=3) for p, r in zip(pts, radii)])
                blob = blob.buffer(close, join_style="mitre").buffer(-close, join_style="mitre").simplify(0.25)
                return blob.intersection(side).buffer(-0.05, join_style="mitre").buffer(0.05, join_style="mitre").intersection(side)
        lo, hi = 0.05, 8.0
        for _ in range(18):
            mid = (lo + hi) / 2
            if grown(mid).area < need:
                lo = mid
            else:
                hi = mid
        out.append((grown(hi), group))
    return out


def _mm(poly: Polygon) -> Polygon:
    """Metres to whole millimetres. Rounding can pinch a thin neck shut; then the largest sound piece is kept."""
    q = shapely.transform(poly, lambda c: np.round(c * 1000.0))
    if not q.is_valid:
        parts = [g for g in getattr(q.buffer(0), "geoms", [q.buffer(0)]) if g.geom_type == "Polygon" and g.area > 0]
        q = max(parts, key=lambda g: g.area) if parts else q
    return q


def build(f: Field, positions: dict, kind: str = "power", **params) -> Layout:
    """Tessellate every level and return the conformed layout (path cells included). A room that got no ground is
    absent; `cells.precheck` names it."""
    H = int(round(f.H * 1000))
    params.setdefault("angle", f.angle())
    params.setdefault("lloyd", 0.0)      # a power cell whose seed drifts leaves the path, so seeds stay put
    fit = params.pop("fit", None) or ("band" if kind in ("slice", "grid") else "mass")
    lay: Layout = {}
    for c in f.cells:
        lay[c.name] = Prism(_mm(c.poly), c.k0 * H, (c.k1 + 1) * H)
    for k in range(f.n):
        rooms = [s for s in f.rooms(k) if s.name in positions]
        if not rooms:
            continue
        for region, group in _mass(f, k, rooms, positions, fit, float(params["angle"])):
            seeds = [Seed(s.name, positions[s.name][0], positions[s.name][1], s.w * s.l) for s in group]
            for name, poly in tessellate(kind, region, seeds, **params).items():
                lay[name] = Prism(_mm(poly), k * H, (k + 1) * H)
    return _layout.conform(lay)


# ----------------------------------------------------------------------------- reading a layout

def evaluate(f: Field, lay: Layout) -> dict:
    from .cells import precheck
    t = _layout.Table(lay, conformed=True)
    sc = _layout.scores(f.brief, t)
    ground = sum(p.area for p in lay.values() if p.z0 == 0) / 1e6
    sc["coverage"] = round(ground / f.ground.area, 6)
    checks = precheck(f.brief, t)
    out = {"scores": sc, "checks": {k: {"passed": p, "detail": d} for k, (p, d) in checks.items()},
           "ok": all(p for p, _ in checks.values())}
    if _aff.written(f.brief):
        out["affinity"] = _layout.affinity(f.brief, t)
    return out


def layout_payload(f: Field, lay: Layout) -> list[dict]:
    H = int(round(f.H * 1000))
    out = []
    for n, p in lay.items():
        s = f.brief.space(n)
        out.append({"name": n, "program": s.program, "level": p.z0 // H, "levels": [p.z0 // H, (p.z1 - 1) // H],
                    "area": round(p.area / 1e6, 2), "want": round(s.w * s.l, 2) if s.program == "room" else None,
                    "ring": [[x / 1000.0, y / 1000.0] for x, y in p.poly.exterior.coords[:-1]]})
    return out


def solve(brief: Brief, kind: str = "power", seed: int = 0, positions: dict | None = None, pins: tuple[str, ...] = (),
          relaxed: bool = True, iters: int | None = None, **params) -> dict:
    """Everything the canvas shows for one state: positions, cells, scores, affinity report and checks. No kernel."""
    t0 = time.perf_counter()
    f = prepare(brief, seed)
    start = {n: tuple(v) for n, v in (positions or {}).items()}
    pos = relax(f, seed, start=start, pins=tuple(pins), iters=iters or (60 if start else 240)) if relaxed or not start else start
    t1 = time.perf_counter()
    lay = build(f, pos, kind, **params)
    t2 = time.perf_counter()
    ev = evaluate(f, lay)
    return {"kind": kind, "seed": seed, "levels": f.n, "level_height": f.H, "positions": {n: list(v) for n, v in pos.items()},
            "room_levels": {s.name: f.levels.get(s.name, 0) for s in f.rooms()},
            "ground": [list(c) for c in f.ground.exterior.coords[:-1]], "cells": layout_payload(f, lay), **ev,
            "ms": {"relax": round(1000 * (t1 - t0)), "tessellate": round(1000 * (t2 - t1)), "measure": round(1000 * (time.perf_counter() - t2))}}


# ----------------------------------------------------------------------------- options

# aspect -> (score key, +1 when higher is better)
ASPECTS = {"affinity": ("affinity", 1), "compact": ("compactness", 1), "daylight": ("exposure", 1),
           "true areas": ("area_deviation", -1), "regular rooms": ("regularity", 1), "short walks": ("path_depth", -1),
           "lean circulation": ("circulation", -1), "open ground": ("coverage", -1)}
BALANCE = {"affinity": 5, "compactness": 3, "exposure": 2, "area_deviation": -5, "regularity": 2, "path_depth": -1,
           "circulation": -1, "vertical": 10, "adjacency": 10}


@dataclass
class FieldOption:
    kind: str
    seed: int
    positions: dict
    layout: Layout
    scores: dict
    checks: dict
    ok: bool
    champion: list[str] = _field(default_factory=list)
    affinity: dict | None = None
    report: object = None            # cells.LayoutReport once built
    polished: int = 0

    def balance(self) -> float:
        return sum(w * self.scores.get(k, 0.0) for k, w in BALANCE.items())

    def to_dict(self) -> dict:
        d = {"kind": self.kind, "seed": self.seed, "champion": self.champion, "scores": self.scores, "ok": self.ok,
             "checks": self.checks, "positions": {n: list(v) for n, v in self.positions.items()}, "polished": self.polished,
             "layout": {n: p.to_dict() for n, p in self.layout.items()}}
        if self.affinity is not None:
            d["analysis"] = {"affinity": self.affinity}
        if self.report is not None:
            d["verify"] = self.report.to_dict()
            d["ok"] = self.ok and self.report.ok
        return d


def _candidate(f: Field, kind: str, seed: int, pos: dict, params: dict) -> FieldOption:
    lay = build(f, pos, kind, **dict(params))
    ev = evaluate(f, lay)
    return FieldOption(kind, seed, pos, lay, ev["scores"], ev["checks"], ev["ok"], affinity=ev.get("affinity"))


def polish(f: Field, o: FieldOption, key: str, sign: int, steps: int, rng, params: dict) -> FieldOption:
    """Climb one aspect: nudge a few rooms, keep the move when the aspect improves and nothing that passed now fails."""
    best = o
    names = list(o.positions)
    step = 0.35 * float(np.mean([radius(s) for s in f.rooms()]))
    for _ in range(steps):
        pos = dict(best.positions)
        for n in rng.choice(names, size=max(1, len(names) // 4), replace=False):
            x, y = pos[n]
            pos[n] = (x + float(rng.normal(0, step)), y + float(rng.normal(0, step)))
        pos = relax(f, o.seed, start=pos, iters=12)
        c = _candidate(f, o.kind, o.seed, pos, params)
        if (c.ok or not best.ok) and sign * (c.scores[key] - best.scores[key]) > 1e-9:
            c.polished = best.polished + 1
            best = c
    return best


def options(brief: Brief, kinds: tuple[str, ...] = KINDS, seeds: tuple[int, ...] = (0, 1, 2), aspects: tuple[str, ...] | None = None,
            polish_steps: int = 6, verify: bool = True, params: dict | None = None) -> tuple[list[FieldOption], dict]:
    """Candidates over seeds × tessellations; for each aspect the candidate that does it best (climbed a little
    further), plus the best balance; each chosen option built and verified in topologic. Returns (options, info)."""
    t0 = time.perf_counter()
    params = dict(params or {})
    pool: list[FieldOption] = []
    f = None
    for seed in seeds:
        f = prepare(brief, seed)
        pos = relax(f, seed)
        for kind in kinds:
            pool.append(_candidate(f, kind, seed, pos, params))
    fields = {seed: prepare(brief, seed) for seed in seeds}
    good = [o for o in pool if o.ok] or pool
    chosen: list[FieldOption] = []

    def pick(o: FieldOption, label: str) -> None:
        for c in chosen:
            if c is o or (c.kind == o.kind and c.seed == o.seed and c.positions == o.positions):
                c.champion.append(label)
                return
        o.champion.append(label)
        chosen.append(o)

    pick(max(good, key=FieldOption.balance), "balance")
    rng = np.random.default_rng(seeds[0] if seeds else 0)
    for label in aspects or tuple(ASPECTS):
        key, sign = ASPECTS[label]
        o = max(good, key=lambda c: (sign * c.scores.get(key, 0.0), c.balance()))
        if polish_steps:
            o = polish(fields[o.seed], o, key, sign, polish_steps, rng, params)
        pick(o, label)
    if verify:
        from .cells import verify_layout
        for o in chosen:
            o.report = verify_layout(fields[o.seed].brief, o.layout)
    info = {"candidates": len(pool), "passed": sum(1 for o in pool if o.ok), "chosen": len(chosen),
            "seconds": round(time.perf_counter() - t0, 2), "levels": f.n if f else 0}
    return chosen, info
