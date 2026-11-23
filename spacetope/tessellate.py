"""M26: tessellations (PLAN §4.11). One call divides a plan region among seeds, five ways:

    voronoi   nearest seed owns the ground; areas fall where they fall
    power     weighted Voronoi; the weights are moved until every cell has its share of the area
    slice     straight cuts across the region, splitting the seeds by area each time (orthogonal rooms)
    grid      rooms grown cell by cell on a square module from their seeds
    hex       the same growth on a hexagonal module

Every kind takes the same input (a region and seeds with a wanted area, in metres) and returns one simple polygon per
seed; together they fill the region, with shared vertices where cells meet. Wanted areas are shares: they are scaled
to the region. `slice`, `grid` and `hex` take `angle` (degrees) to turn their axes. Pure numpy and shapely.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import shapely
from scipy.spatial import cKDTree
from shapely import affinity as _shp
from shapely.geometry import Point, Polygon, box
from shapely.prepared import prep

KINDS = ("voronoi", "power", "slice", "grid", "hex")
WELD_M = 2e-4      # vertices closer than this are one vertex
MIN_PART_M2 = 1e-4


@dataclass(frozen=True)
class Seed:
    name: str
    x: float
    y: float
    area: float


def tessellate(kind: str, region, seeds: list[Seed], **params) -> dict[str, Polygon]:
    """Cells per seed name. A region in several parts is divided part by part, each among the seeds inside it; a part
    with no seed is left out. A seed that gets no ground is missing from the result (the caller reports it)."""
    if kind not in KINDS:
        raise ValueError(f"unknown tessellation {kind!r}; choose from {', '.join(KINDS)}")
    angle = float(params.get("angle", 0.0) or 0.0) if kind in ("slice", "grid", "hex") else 0.0
    if angle:
        region = _shp.rotate(region, -angle, origin=(0, 0))
        c, s = math.cos(math.radians(-angle)), math.sin(math.radians(-angle))
        seeds = [Seed(q.name, q.x * c - q.y * s, q.x * s + q.y * c, q.area) for q in seeds]
    cells: dict[str, object] = {}
    spare: list[Polygon] = []
    for part, group in _distribute(region, seeds):
        if kind in ("voronoi", "power"):
            got = _power_cells(part, group, iters=0 if kind == "voronoi" else int(params.get("iters", 30)),
                               tol=float(params.get("tol", 0.03)), lloyd=float(params.get("lloyd", 0.5)))
        elif kind == "slice":
            got = _slice(part, group)
        else:
            got = _grow(part, group, module=params.get("module"), hexagonal=kind == "hex")
        cells.update(got)
        if got:   # ground of this part that no seed was given goes to the neighbour it touches most
            spare += [p for p in _parts(part.difference(shapely.union_all(list(got.values())).buffer(1e-6))) if p.area > 0.01]
    out = _tidy(cells, {q.name: q for q in seeds}, spare)
    if angle:
        out = {n: _shp.rotate(p, angle, origin=(0, 0)) for n, p in out.items()}
    return out


# ----------------------------------------------------------------------------- shared helpers

def _parts(geom) -> list[Polygon]:
    if geom is None or geom.is_empty:
        return []
    if isinstance(geom, Polygon):
        return [geom] if geom.area > MIN_PART_M2 else []
    return [g for g in getattr(geom, "geoms", []) for g in _parts(g)]


def _distribute(region, seeds: list[Seed]) -> list[tuple[Polygon, list[Seed]]]:
    parts = _parts(region)
    if not parts:
        return []
    groups: list[list[Seed]] = [[] for _ in parts]
    for q in seeds:
        pt = Point(q.x, q.y)
        k = next((i for i, p in enumerate(parts) if p.covers(pt)), None)
        if k is None:
            k = min(range(len(parts)), key=lambda i: parts[i].distance(pt))
        groups[k].append(q)
    return [(p, g) for p, g in zip(parts, groups) if g]


def _tidy(cells: dict[str, object], seeds: dict[str, Seed], spare: list[Polygon] = ()) -> dict[str, Polygon]:
    """One simple polygon per seed: a cell cut in pieces keeps the piece its seed is in (else the largest) and gives
    the others to the neighbour they share most boundary with; then near-coincident vertices are welded."""
    main: dict[str, Polygon] = {}
    orphans: list[Polygon] = list(spare)
    for n, g in cells.items():
        ps = sorted(_parts(g), key=lambda p: p.area, reverse=True)
        if not ps:
            continue
        pt = Point(seeds[n].x, seeds[n].y)
        keep = next((p for p in ps if p.covers(pt)), ps[0])
        main[n] = keep
        orphans += [p for p in ps if p is not keep]
    for o in sorted(orphans, key=lambda p: p.area, reverse=True):
        halo = o.buffer(0.01)
        best = max(main, key=lambda n: halo.intersection(main[n]).area, default=None)
        if best is None or halo.intersection(main[best]).area <= 0:
            continue
        u = shapely.union_all([main[best], o], grid_size=1e-4)
        ps = _parts(u)
        if ps:
            main[best] = max(ps, key=lambda p: p.area)
    return _weld(main)


def _weld(cells: dict[str, Polygon]) -> dict[str, Polygon]:
    coords, where = [], []
    for n, p in cells.items():
        for ri, ring in enumerate([p.exterior, *p.interiors]):
            for x, y in list(ring.coords)[:-1]:
                coords.append((x, y))
                where.append((n, ri))
    if not coords:
        return cells
    P = np.array(coords)
    parent = list(range(len(P)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for i, j in cKDTree(P).query_pairs(WELD_M):
        parent[find(j)] = find(i)
    rings: dict[tuple, list] = {}
    for k, key in enumerate(where):
        q = tuple(np.round(P[find(k)], 3))   # whole millimetres, the same for every holder of the vertex
        r = rings.setdefault(key, [])
        if not r or r[-1] != q:
            r.append(q)
    out = {}
    for n, p in cells.items():
        shell = rings.get((n, 0), [])
        holes = [rings[(n, i)] for i in range(1, len(p.interiors) + 1) if len(rings.get((n, i), [])) >= 3]
        if len(shell) >= 3:
            q = Polygon(shell, holes)
            if not q.is_valid:
                q = max(_parts(q.buffer(0)), key=lambda g: g.area, default=None)
            if q is not None and q.area > MIN_PART_M2:
                out[n] = q
    return out


def _shares(region: Polygon, seeds: list[Seed]) -> np.ndarray:
    a = np.array([max(q.area, 1e-6) for q in seeds], dtype=float)
    return a * (region.area / a.sum())


# ----------------------------------------------------------------------------- voronoi and power

def _clip(V: np.ndarray, n: np.ndarray, c: float) -> np.ndarray:
    """Keep the part of convex polygon V where n·x <= c."""
    d = V @ n - c
    inside = d <= 0
    if inside.all():
        return V
    if not inside.any():
        return V[:0]
    out = []
    k = len(V)
    for i in range(k):
        j = (i + 1) % k
        if inside[i]:
            out.append(V[i])
        if inside[i] != inside[j]:
            t = d[i] / (d[i] - d[j])
            out.append(V[i] + t * (V[j] - V[i]))
    return np.array(out)


def power_diagram(P: np.ndarray, w: np.ndarray, bounds: tuple[float, float, float, float]) -> list[np.ndarray]:
    """Convex power cells of points P with weights w inside a bounding rectangle: x belongs to the site with the
    smallest |x − p|² − w. Each cell is cut only by the neighbours that reach it, most violated first."""
    x0, y0, x1, y1 = bounds
    sq = (P ** 2).sum(axis=1) - w
    cells = []
    for i in range(len(P)):
        V = np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1]], dtype=float)
        N = 2.0 * (P - P[i])
        c = sq - sq[i]
        done = np.zeros(len(P), dtype=bool)
        done[i] = True
        while len(V):
            D = V @ N.T - c
            D[:, done] = -1.0
            worst = D.max(axis=0)
            j = int(worst.argmax())
            if worst[j] <= 1e-10:
                break
            V = _clip(V, N[j], c[j])
            done[j] = True
        cells.append(V)
    return cells


def _power_cells(region: Polygon, seeds: list[Seed], iters: int, tol: float, lloyd: float) -> dict[str, object]:
    if len(seeds) == 1:
        return {seeds[0].name: region}
    P = np.array([[q.x, q.y] for q in seeds], dtype=float)
    T = _shares(region, seeds)
    w = np.zeros(len(P))
    x0, y0, x1, y1 = region.bounds
    pad = max(x1 - x0, y1 - y0)
    bounds = (x0 - pad, y0 - pad, x1 + pad, y1 + pad)

    def cut(P, w):
        geoms = []
        for V in power_diagram(P, w, bounds):
            g = Polygon(V).intersection(region) if len(V) >= 3 else Polygon()
            geoms.append(g)
        return geoms

    best = None
    for it in range(iters + 1):
        geoms = cut(P, w)
        A = np.array([g.area for g in geoms])
        err = float((np.abs(A - T) / T).mean()) if A.all() else float("inf")
        if best is None or err < best[0]:
            best = (err, geoms)
        if it == iters or err < tol:
            break
        w = w + 0.35 * (T - A)                    # a cell short of ground pushes its walls out
        if lloyd:                                 # and its seed drifts to the middle of what it holds
            for k, g in enumerate(geoms):
                if g.area > 0:
                    cx, cy = g.centroid.coords[0]
                    P[k] += lloyd * (np.array([cx, cy]) - P[k])
        d2 = ((P[:, None, :] - P[None, :, :]) ** 2).sum(axis=2)
        np.fill_diagonal(d2, np.inf)
        w = np.clip(w - w.min(), 0.0, 0.95 * d2.min(axis=1))   # keeps every seed inside its own cell
    return {q.name: g for q, g in zip(seeds, best[1])}


# ----------------------------------------------------------------------------- slice

def _slice(region, seeds: list[Seed]) -> dict[str, object]:
    """Cut the region in two across its longer side so each half holds its seeds' share of the area, and again.
    Where a cut leaves a half in pieces (a concave outline), the largest piece carries on and the caller gives the
    others to a neighbour."""
    parts = _parts(region)
    if not parts or not seeds:
        return {}
    part = max(parts, key=lambda p: p.area)
    if len(seeds) == 1:
        return {seeds[0].name: part}
    x0, y0, x1, y1 = part.bounds
    best = None
    for along_x in (True, False):          # cut where the seeds part most cleanly, counting the longer side for more
        order = sorted(seeds, key=lambda q: (q.x if along_x else q.y, q.name))
        areas = np.array([max(q.area, 1e-6) for q in order])
        cum = np.cumsum(areas)[:-1]
        k = int(np.abs(cum - areas.sum() / 2).argmin()) + 1
        co = [q.x if along_x else q.y for q in order]
        extent = (x1 - x0) if along_x else (y1 - y0)
        clean = (co[k] - co[k - 1]) * extent / max(x1 - x0, y1 - y0)
        if best is None or clean > best[0] + 1e-9:
            best = (clean, along_x, order, areas, cum, k)
    _, along_x, order, areas, cum, k = best
    want = part.area * cum[k - 1] / areas.sum()
    lo, hi = (x0, x1) if along_x else (y0, y1)
    for _ in range(40):
        mid = (lo + hi) / 2
        half = box(x0, y0, mid, y1) if along_x else box(x0, y0, x1, mid)
        if part.intersection(half).area < want:
            lo = mid
        else:
            hi = mid
    mid = round((lo + hi) / 2, 3)
    first = box(x0 - 1, y0 - 1, mid, y1 + 1) if along_x else box(x0 - 1, y0 - 1, x1 + 1, mid)
    return {**_slice(part.intersection(first), order[:k]), **_slice(part.difference(first), order[k:])}


# ----------------------------------------------------------------------------- grid and hex growth

def default_module(seeds: list[Seed], region: Polygon) -> float:
    """A module that gives the smallest room about nine cells, in steps of 0.3 m, between 0.6 and 3 m."""
    share = _shares(region, seeds).min()
    return float(min(3.0, max(0.6, math.floor(math.sqrt(share / 9) / 0.3) * 0.3)))


def _lattice(region: Polygon, m: float, hexagonal: bool):
    x0, y0, x1, y1 = region.bounds
    pieces, centres, index = [], [], {}
    if not hexagonal:
        ox, oy = math.floor(x0 / m) * m, math.floor(y0 / m) * m
        for j in range(int(math.ceil((y1 - oy) / m)) + 1):
            for i in range(int(math.ceil((x1 - ox) / m)) + 1):
                cell = box(ox + i * m, oy + j * m, ox + (i + 1) * m, oy + (j + 1) * m)
                index[(i, j)] = (cell, (ox + (i + 0.5) * m, oy + (j + 0.5) * m))
        nb = lambda i, j: [(i + 1, j), (i - 1, j), (i, j + 1), (i, j - 1)]  # noqa: E731
    else:
        s = m / math.sqrt(1.5 * math.sqrt(3))          # side of a hexagon with the area of an m × m square
        dx, dy = math.sqrt(3) * s, 1.5 * s
        ox, oy = x0 - dx, y0 - dy
        corners = [(s * math.cos(math.radians(30 + 60 * k)), s * math.sin(math.radians(30 + 60 * k))) for k in range(6)]
        for j in range(int(math.ceil((y1 - oy) / dy)) + 2):
            for i in range(int(math.ceil((x1 - ox) / dx)) + 2):
                cx, cy = ox + (i + 0.5 * (j % 2)) * dx, oy + j * dy
                index[(i, j)] = (Polygon([(cx + a, cy + b) for a, b in corners]), (cx, cy))
        nb = lambda i, j: [(i + 1, j), (i - 1, j), (i, j + 1), (i, j - 1),  # noqa: E731
                           (i + (1 if j % 2 else -1), j + 1), (i + (1 if j % 2 else -1), j - 1)]
    keep: dict[tuple, int] = {}
    prepared = prep(region)
    for key, (cell, centre) in index.items():
        if not prepared.intersects(cell):
            continue
        piece = cell if prepared.contains(cell) else cell.intersection(region)
        ps = _parts(piece)
        if not ps:
            continue
        keep[key] = len(pieces)
        pieces.append(max(ps, key=lambda p: p.area))
        centres.append(centre)
    neighbours = [[keep[k] for k in nb(*key) if k in keep] for key in keep]
    return pieces, np.array(centres, dtype=float).reshape(-1, 2), neighbours, keep


def _grow(region: Polygon, seeds: list[Seed], module, hexagonal: bool) -> dict[str, object]:
    """Rooms grow from their seeds one module cell at a time; the room furthest behind its share grows next and
    takes the free neighbouring cell nearest its seed (square distance on the grid, so rooms come out boxy)."""
    if len(seeds) == 1:
        return {seeds[0].name: region}
    m = float(module) if module else default_module(seeds, region)
    pieces, C, nbrs, keep = _lattice(region, m, hexagonal)
    if not pieces:
        return {}
    area = np.array([p.area for p in pieces])
    T = _shares(region, seeds)
    S = np.array([[q.x, q.y] for q in seeds])
    owner = np.full(len(pieces), -1)
    have = np.zeros(len(seeds))
    frontier: list[set[int]] = [set() for _ in seeds]

    def dist(r: int, cells) -> np.ndarray:
        d = np.abs(C[cells] - S[r])
        return np.hypot(d[:, 0], d[:, 1]) if hexagonal else d.max(axis=1) + 1e-3 * d.sum(axis=1)

    def take(r: int, c: int) -> None:
        owner[c] = r
        have[r] += area[c]
        frontier[r].update(k for k in nbrs[c] if owner[k] < 0)

    for r in np.argsort(-T):
        free = np.flatnonzero(owner < 0)
        if len(free):
            take(int(r), int(free[np.hypot(*(C[free] - S[r]).T).argmin()]))
    home = set(np.flatnonzero(owner >= 0).tolist())     # the cell a room started on stays its own
    if not hexagonal:
        _grow_rectangles(owner, have, area, T, keep, take)
    while True:
        for f in frontier:
            f.difference_update([c for c in f if owner[c] >= 0])
        live = [r for r in range(len(seeds)) if frontier[r]]
        if not live:
            break
        r = min(live, key=lambda r: have[r] / T[r])
        cand = np.fromiter(frontier[r], dtype=int)
        own = np.array([sum(1 for k in nbrs[c] if owner[k] == r) for c in cand])
        take(r, int(cand[(dist(r, cand) - 10.0 * own).argmin()]))       # fill notches before reaching out
    if not hexagonal:
        out = {}
        for r, q in enumerate(seeds):
            mine = [pieces[c] for c in np.flatnonzero(owner == r)]
            if mine:
                out[q.name] = shapely.union_all(mine, grid_size=1e-4).simplify(1e-4)
        return out
    _even_out(owner, have, area, T, C, S, nbrs, home=home)
    out = {}
    for r, q in enumerate(seeds):
        mine = [pieces[c] for c in np.flatnonzero(owner == r)]
        if mine:
            out[q.name] = shapely.union_all(mine, grid_size=1e-4).simplify(1e-4)
    return out


def _grow_rectangles(owner, have, area, T, keep: dict, take) -> None:
    """Square grid: every room first grows as a rectangle, a whole row or column of free cells at a time (after
    Lopes et al. 2010), the room furthest behind its share first and on the side that keeps it most nearly square.
    What the rectangles cannot reach is filled cell by cell afterwards, so rooms end as rectangles with a few steps."""
    where = {v: k for k, v in keep.items()}
    rect = {}
    for r in range(len(T)):
        mine = np.flatnonzero(owner == r)
        if len(mine):
            i, j = where[int(mine[0])]
            rect[r] = [i, i, j, j]
    stuck: set[int] = set()
    while True:
        live = [r for r in rect if r not in stuck and have[r] < T[r]]
        if not live:
            return
        r = min(live, key=lambda r: have[r] / T[r])
        i0, i1, j0, j1 = rect[r]
        lines = []
        for side, cells in (("w", [(i0 - 1, j) for j in range(j0, j1 + 1)]), ("e", [(i1 + 1, j) for j in range(j0, j1 + 1)]),
                            ("s", [(i, j0 - 1) for i in range(i0, i1 + 1)]), ("n", [(i, j1 + 1) for i in range(i0, i1 + 1)])):
            if all(c in keep and owner[keep[c]] < 0 for c in cells):
                w, h = (i1 - i0 + 2, j1 - j0 + 1) if side in "we" else (i1 - i0 + 1, j1 - j0 + 2)
                lines.append((max(w, h) / min(w, h), side, cells))
        if not lines:
            stuck.add(r)
            continue
        _, side, cells = min(lines)
        for c in cells:
            take(r, keep[c])
        rect[r] = [i0 - (side == "w"), i1 + (side == "e"), j0 - (side == "s"), j1 + (side == "n")]


def _even_out(owner, have, area, T, C, S, nbrs, sweeps: int = 24, home: set = frozenset()) -> None:
    """After growth a hemmed-in room is short and its neighbours long. In each sweep every border cell whose owner
    is fuller than the room next to it is offered to that room, largest difference first; it moves when the giver
    is still at least as full as the taker afterwards and stays in one piece. The surplus drains through the plan."""
    def connected_without(r: int, c: int) -> bool:
        left = set(np.flatnonzero(owner == r).tolist()) - {c}
        if not left:
            return False
        first = next(iter(left))
        seen, stack = {first}, [first]
        while stack:
            for k in nbrs[stack.pop()]:
                if k in left and k not in seen:
                    seen.add(k)
                    stack.append(k)
        return len(seen) == len(left)

    for _ in range(sweeps):
        fill = have / T
        offers = []
        for c in np.flatnonzero(owner >= 0).tolist():
            if c in home:
                continue
            a = owner[c]
            for b in {int(owner[k]) for k in nbrs[c]} - {int(a), -1}:
                if fill[a] > fill[b]:
                    offers.append((fill[b] - fill[a], float(np.hypot(*(C[c] - S[b]))), c, b))
        moved = 0
        for _gain, _d, c, b in sorted(offers):
            a = int(owner[c])
            if a == b or (have[a] - area[c]) / T[a] < (have[b] + area[c]) / T[b]:
                continue
            if not any(owner[k] == b for k in nbrs[c]) or not connected_without(a, c):
                continue
            owner[c] = b
            have[a] -= area[c]
            have[b] += area[c]
            moved += 1
        if not moved:
            break
