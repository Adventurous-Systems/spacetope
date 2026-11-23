"""M29: bodies on springs in a three-dimensional void (PLAN §4.11).

The original spacetope graph, afloat: every space node is the centre of a body, its six wall nodes sit on the body's
surface, and a contact is a spring. A spring between two wall nodes has a direction (`a.ceiling — b.floor` draws b
above a); a contact whose sides are not stated is a spring between the centres. Affinities are weaker springs.

A body is a lens, not a sphere: its plan radius comes from the room's area and its height from the storey, because
a sphere with a room's volume would stand two storeys tall. Bodies cannot fill a void (packed spheres leave a third
of it empty); the cells cut from them do. So the void is filled storey by storey with the tessellations of M26, or,
as a sketch, with free polyhedral cells.

    void: {blocks: [{boundary: [[x, y], ...], levels: [from, to]}, ...]}     # stacked outlines, in metres

`relax` floats the bodies and lets the storeys emerge; `build` cuts storey cells (a `layout.Layout`, so every
measure, check and option of M25–M27 applies); `solve` is the call the canvas makes; `free` is the sketch mode.
"""
from __future__ import annotations

import math
import time

import numpy as np
import shapely
from shapely.geometry import Point

from . import affinity as _aff
from . import field as _field
from . import layout as _layout
from .brief import Brief, Space
from .field import Field
from .layout import Layout, Prism
from .spacegraph import NORMAL
from .tessellate import Seed, tessellate

FULL = 1.08          # a storey may be asked this much of its ground before a body is sent elsewhere


def storeys_of(f: Field, s: Space) -> int:
    """How many storeys a room stands through: a hall twice the storey height is a double-height room."""
    return max(1, min(f.n, int(round(s.h / f.H))))


def capacity(f: Field) -> np.ndarray:
    return np.array([f.ground_at(k).difference(f.occupied(k)).area for k in range(f.n)])


def bodies(f: Field, scales: dict | None = None) -> tuple[list[Space], np.ndarray, np.ndarray, np.ndarray, float]:
    """(rooms, asked plan area with inflation, plan radius, storeys stood through, fill factor). Every body is
    grown by the same factor so that together the storey areas they ask equal the ground the void has."""
    rooms = f.rooms()
    st = np.array([storeys_of(f, s) for s in rooms])
    asked = np.array([s.w * s.l * float((scales or {}).get(s.name, 1.0)) for s in rooms])
    fill = float(capacity(f).sum() / max(1e-9, (asked * st).sum()))
    return rooms, asked, np.sqrt(asked * fill / math.pi), st, fill


def from_brief(brief: Brief, cover: float = 0.8) -> Brief:
    """A box brief as a volume brief. Rooms keep their sizes, tags, affinities and level wishes. The corridor, written
    as a space or in the circulation section, becomes one path on every storey (a spine down the long middle, or a U
    where the rooms want more frontage than a spine has), and a contact
    with it a contact with that path; stairs and lifts go, because a path on several levels brings its own stair.
    The void has the envelope's proportions where the brief has one, and in either case is sized so the rooms fill
    `cover` of each storey beside the path."""
    if brief.void:
        return brief
    rooms = [s for s in brief.spaces if s.program in ("room", "void")]
    n = int(brief.levels or 1)
    circ = (brief.circulation or {}).get("corridor") or {}
    corridors = [s for s in brief.spaces if s.program == "corridor"]
    width = float(circ.get("w") or max((min(s.w, s.l) for s in corridors), default=0.0))
    area = sum(s.w * s.l for s in rooms) / n / cover          # ground a storey needs for its rooms
    if brief.envelope:      # the envelope's proportions, no larger than the rooms need: a loose envelope would bloat them
        W, L = float(brief.envelope["w"]), float(brief.envelope["l"])
        long, short = max(W, L), min(W, L)
        k = min(1.0, (width * long + math.sqrt((width * long) ** 2 + 4 * long * short * area)) / (2 * long * short))
        W, L = round(W * k, 1), round(L * k, 1)
    else:
        length = max((max(s.w, s.l) for s in corridors), default=0.0)
        W = max(length, math.sqrt(1.6 * area))
        L = area / W + width
        W, L = round(W, 1), round(L, 1)
    d = brief.to_dict()
    d.pop("circulation", None)
    d.pop("envelope", None)
    d.pop("expanded", None)
    d["spaces"] = [s.to_dict() for s in rooms]
    d["level_height"] = float(brief.level_height or max(s.h for s in rooms))
    d["void"] = {"blocks": [{"boundary": [[0, 0], [W, 0], [W, L], [0, L]], "levels": [0, n - 1]}]}
    names = {s.name for s in rooms}
    gone = {s.name for s in brief.spaces} - names
    spine = "spine"
    while spine in names:
        spine += "_"
    contacts = []
    for a, b in brief.contacts:
        a2, b2 = (a if a in names else spine if a.startswith("corridor") or a in {c.name for c in corridors} else None,
                  b if b in names else spine if b.startswith("corridor") or b in {c.name for c in corridors} else None)
        if a2 and b2 and a2 != b2 and width > 0 or (a2 in names and b2 in names):
            if [a2, b2] not in contacts and [b2, a2] not in contacts:
                contacts.append([a2, b2])
    d["contacts"] = contacts
    if width > 0:
        end = 0.5
        need = sum(1.6 * math.sqrt(s.w * s.l / math.pi) for s in rooms) / n     # frontage a storey's rooms want, side by side
        for _ in range(2):          # the second pass is on a void grown to hold the path as well as the rooms
            a, b = (W, L) if W >= L else (L, W)                   # a: along the path, b: across
            if need <= 2 * (a - 2 * end):
                pts = [[end, b / 2], [a - end, b / 2]]            # one spine, rooms on both sides
            else:                                                # too many rooms for one spine: out, across and back
                pts = [[end, b / 4], [a - b / 4, b / 4], [a - b / 4, 3 * b / 4], [end, 3 * b / 4]]
            run = sum(math.dist(p, q) for p, q in zip(pts, pts[1:]))
            grow = math.sqrt((area + run * width) / (W * L))
            if grow <= 1.001:
                break
            W, L = round(W * grow, 1), round(L * grow, 1)
        d["void"] = {"blocks": [{"boundary": [[0, 0], [W, 0], [W, L], [0, L]], "levels": [0, n - 1]}]}
        d["paths"] = [{"name": spine, "width": width, "points": [[round(u, 2), round(v, 2)] if W >= L else [round(v, 2), round(u, 2)] for u, v in pts]}]
    for sp in d["spaces"]:      # an affinity or wish that names a space that is gone cannot be kept
        sp["affinities"] = [a for a in sp.get("affinities", []) if not (set(map(str, a.values())) & gone)] if sp.get("affinities") else []
        if not sp["affinities"]:
            sp.pop("affinities")
    d["affinities"] = [a for a in d.get("affinities", []) if not (set(a.get("between", [])) & gone)]
    return Brief.from_dict(d)


def springs_from_assembly(ag) -> list[tuple[str, str, str]]:
    """(a, side of a, b) for every contact edge of an AssemblyGraph: the wall-node springs of a box option."""
    return [(c.a, c.side_a, c.b) for c in ag.contacts()]


def relax(f: Field, seed: int = 0, start: dict | None = None, pins: tuple[str, ...] = (), scales: dict | None = None,
          sided: tuple = (), iters: int = 300) -> dict[str, tuple[float, float, float]]:
    """Float the bodies. In plan they behave as the discs of M27 do; in height they are drawn to the middle of a
    storey, harder as the run cools. Bodies cannot pass through each other, so every few steps a storey that is
    asked for more ground than it has sends the body that loses least by going to a storey with room, and a body
    whose wished neighbours are on another storey may follow them. `must` ground / top wishes fix a storey."""
    rooms, asked, a, st, _fill = bodies(f, scales)
    n = len(rooms)
    if not n:
        return {}
    rng = np.random.default_rng(seed)
    names = [s.name for s in rooms]
    idx = {nm: i for i, nm in enumerate(names)}
    H = f.H
    c = st * H / 2
    cap = capacity(f)
    top = f.n - st                                     # highest storey each body may start on
    pull = np.zeros((n, n))
    push = np.zeros((n, n))
    stack = np.zeros((n, n))
    level_pin = np.full(n, -1)
    for x, y in f.brief.contacts:
        if x in idx and y in idx:
            pull[idx[x], idx[y]] = pull[idx[y], idx[x]] = 1.0
    for af in _aff.expand(f.brief) if _aff.written(f.brief) else []:
        if af.a not in idx:
            continue
        i = idx[af.a]
        strong = 1.0 if af.strength in _aff.HARD else min(1.0, 0.35 * af.weight)
        neg = af.strength in _aff.NEGATIVE
        if af.kind in ("touch", "near", "apart", "same_level"):
            for o in af.others:
                if o in idx:
                    m = pull if ((af.kind != "apart") != neg) else push
                    m[i, idx[o]] = m[idx[o], i] = max(m[i, idx[o]], strong * (0.5 if af.kind in ("near", "same_level") else 1.0))
        elif af.kind == "stack" and not neg:
            for o in af.others:
                if o in idx:
                    stack[i, idx[o]] = stack[idx[o], i] = strong
        elif af.kind in ("ground", "top") and af.strength == "must":
            level_pin[i] = 0 if af.kind == "ground" else top[i]
    for i, sp in enumerate(rooms):          # a level written in the brief is kept
        if "level" in sp.wishes:
            level_pin[i] = int(np.clip(int(sp.wishes["level"]), 0, top[i]))
    side_springs = [(idx[x], np.array(NORMAL[sd], dtype=float), idx[y]) for x, sd, y in sided if x in idx and y in idx]

    def into(i: int, q: np.ndarray, k: int) -> np.ndarray:
        whole = f.ground_at(k)
        for up in range(k + 1, min(f.n, k + int(st[i]))):       # a tall body stands only where every storey has ground
            whole = whole.intersection(f.ground_at(up))
        g = whole.buffer(-0.5 * a[i])
        g = g if not g.is_empty else whole
        pt = Point(q)
        return q if g.contains(pt) else shapely.get_coordinates(shapely.shortest_line(pt, g))[1]

    lev = np.zeros(n, dtype=int)
    P = np.zeros((n, 3))
    fixed = np.array([nm in pins for nm in names])
    for i, nm in enumerate(names):
        if start and nm in start:
            P[i] = start[nm]
            lev[i] = int(np.clip(round(P[i, 2] / H - st[i] / 2), 0, top[i])) if level_pin[i] < 0 or fixed[i] else level_pin[i]
            continue
        lev[i] = level_pin[i] if level_pin[i] >= 0 else int(rng.choice(top[i] + 1, p=cap[:top[i] + 1] / cap[:top[i] + 1].sum()))
        x0, y0, x1, y1 = f.ground_at(lev[i]).bounds
        P[i, :2] = into(i, rng.uniform([x0, y0], [x1, y1]), lev[i])
        P[i, 2] = (lev[i] + st[i] / 2) * H + rng.normal(0, 0.3 * H)

    def stands(L: np.ndarray) -> np.ndarray:
        """n × storeys: which storeys each body stands on."""
        ks = np.arange(f.n)[None, :]
        return (ks >= L[:, None]) & (ks < (L + st)[:, None])

    def unrest(L: np.ndarray) -> np.ndarray:
        """Per body: how much of what it wishes is on a storey it does not share."""
        on = stands(L)
        share = (on[:, None, :] & on[None, :, :]).any(axis=2)
        beside = np.abs(L[:, None] - L[None, :]) <= np.maximum(st[:, None], st[None, :])
        out = (pull * ~share).sum(axis=1) + (push * share).sum(axis=1) + (stack * (share | ~beside)).sum(axis=1)
        for i, nrm, j in side_springs:       # a wall-node spring says which storey: the same, the one above, the one below
            ok = (L[j] == L[i] + st[i]) if nrm[2] > 0 else (L[j] + st[j] == L[i]) if nrm[2] < 0 else share[i, j]
            if not ok:
                out[i] += 2.0
                out[j] += 2.0
        return out

    # bodies that must share a storey move between storeys as one unit: must-contacts and level wall-node springs
    import networkx as nx
    ties = nx.Graph()
    ties.add_nodes_from(range(n))
    ties.add_edges_from((i, j) for i in range(n) for j in range(i + 1, n) if pull[i, j] >= 1.0 and st[i] == st[j])
    ties.add_edges_from((i, j) for i, nrm, j in side_springs if nrm[2] == 0 and st[i] == st[j])
    units = [sorted(u) for u in nx.connected_components(ties)]
    free_units = [u for u in units if not any(fixed[m] or level_pin[m] >= 0 for m in u)]

    def over_of(L: np.ndarray) -> np.ndarray:
        return np.maximum((asked[:, None] * _fill * stands(L)).sum(axis=0) - FULL * cap, 0.0)

    def put(L: np.ndarray, unit: list[int], q: int) -> np.ndarray:
        L = L.copy()
        L[unit] = np.minimum(q, top[unit])
        return L

    def rebalance() -> None:
        for u in units:                                   # a unit stands on one storey
            L0 = next((int(level_pin[m]) for m in u if level_pin[m] >= 0), next((int(lev[m]) for m in u if fixed[m]), int(lev[u[0]])))
            for m in u:
                if not fixed[m] and level_pin[m] < 0:
                    lev[m] = min(L0, top[m])
        for _ in range(4 * n):
            over = over_of(lev)
            now = unrest(lev).sum()
            if over.sum() <= 0 and now <= 0:
                return
            best = None                                   # (overfill after, unrest after) must go down; least first
            here = (float(over.sum()), float(now))
            for u in free_units:
                p = int(lev[u[0]])
                for q in range(int(top[u].min()) + 1):    # the unit goes to another storey alone
                    if q != p:
                        L = put(lev, u, q)
                        key = (round(float(over_of(L).sum()), 6), round(float(unrest(L).sum()), 6))
                        if key < (round(here[0], 6), round(here[1], 6)) and (best is None or key < best[0]):
                            best = (key, L)
                for w in free_units:                      # or trades storeys with another unit
                    q = int(lev[w[0]])
                    if w is u or q == p or q > top[u].min() or p > top[w].min():
                        continue
                    L = put(put(lev, u, q), w, p)
                    key = (round(float(over_of(L).sum()), 6), round(float(unrest(L).sum()), 6))
                    if key < (round(here[0], 6), round(here[1], 6)) and (best is None or key < best[0]):
                        best = (key, L)
            if best is None:
                return
            for m in np.flatnonzero(best[1] != lev):
                lev[m] = best[1][m]
                P[m, :2] = into(int(m), P[m, :2], int(lev[m]))
                P[m, 2] = (lev[m] + st[m] / 2) * H

    scale = float(a.mean())
    rebalance()
    for it in range(iters):
        cool = 1.0 - 0.8 * it / iters
        d = P[:, None, :] - P[None, :, :]
        zs = (a[:, None] + a[None, :]) / (c[:, None] + c[None, :])       # a lens is a sphere once z is stretched
        dm = np.sqrt(d[..., 0] ** 2 + d[..., 1] ** 2 + (d[..., 2] * zs) ** 2) + 1e-9
        want = _field.PACK * (a[:, None] + a[None, :])
        u = d / dm[..., None]
        gap = want - dm
        np.fill_diagonal(gap, 0.0)
        move = 0.5 * (np.where(gap > 0, gap, 0.0)[..., None] * u).sum(axis=1)
        move -= 0.12 * ((np.where(gap < 0, -gap, 0.0) * pull)[..., None] * u).sum(axis=1)
        off = np.where(dm < 1.6 * want, 1.6 * want - dm, 0.0) * push
        np.fill_diagonal(off, 0.0)
        move += 0.3 * (off[..., None] * u).sum(axis=1)
        plan = np.hypot(d[..., 0], d[..., 1])[..., None] + 1e-9
        move[:, :2] -= 0.08 * (stack[..., None] * d[..., :2]).sum(axis=1)               # stacks line up in plan
        for i, nrm, j in side_springs:                                                  # wall node to wall node
            ext = np.array([a[i] + a[j], a[i] + a[j], c[i] + c[j]]) * np.abs(nrm) * _field.PACK
            err = (P[j] - P[i]) - nrm * ext.sum()
            move[i] += 0.15 * err
            move[j] -= 0.15 * err
        move[:, 2] += (0.1 + 0.6 * (1 - cool)) * ((lev + st / 2) * H - P[:, 2])           # the floors take hold
        if it < iters // 3:
            move += rng.normal(0, 0.05 * scale * cool, P.shape)
        step = np.linalg.norm(move, axis=1)
        move *= np.minimum(1.0, 0.6 * scale * cool / (step + 1e-9))[:, None]
        move[fixed] = 0.0
        P += move
        free = ~fixed & (level_pin < 0)
        lev[free] = np.clip(np.round(P[free, 2] / H - st[free] / 2), 0, top[free]).astype(int)   # a body is on the storey it floats in
        if it % 25 == 12 and it < 3 * iters // 4:
            rebalance()
        P[:, 2] = np.clip(P[:, 2], c, f.n * H - c)
        for i in range(n):
            if not fixed[i]:
                P[i, :2] = into(i, P[i, :2], int(lev[i]))
    rebalance()
    P[~fixed, 2] = ((lev + st / 2) * H)[~fixed]
    return {nm: (round(float(P[i, 0]), 3), round(float(P[i, 1]), 3), round(float(P[i, 2]), 3)) for i, nm in enumerate(names)}


def settle(f: Field, pos: dict, scales: dict | None = None) -> Field:
    """The field with every room on the storey its body came to rest on."""
    lv = dict(f.levels)
    for s in f.rooms():
        if s.name in pos:
            st = storeys_of(f, s)
            lv[s.name] = int(np.clip(round(pos[s.name][2] / f.H - st / 2), 0, f.n - st))
    return Field(f.brief, f.ground, f.cells, lv, f.n, f.H, f.source, f.fronts, f.grounds, {})


def build(f: Field, pos: dict, kind: str = "power", scales: dict | None = None, **params) -> Layout:
    """Storey cells. Storeys are cut from the bottom up; a room that stands through two storeys is cut on its
    lowest one and keeps that outline above, where the other rooms divide what is left. `fit` defaults to the
    whole storey (`site`): the contraption fills the void."""
    g = settle(f, pos, scales)
    H = int(round(g.H * 1000))
    fit = params.pop("fit", None) or "site"
    params.setdefault("angle", g.angle())
    params.setdefault("lloyd", 0.0)
    lay: Layout = {}
    for cell in g.cells:
        lay[cell.name] = Prism(_field._mm(cell.poly), cell.k0 * H, (cell.k1 + 1) * H)
    def cut(k: int, rooms: list[Space]) -> dict:
        xy = {s.name: pos[s.name][:2] for s in rooms}
        out = {}
        for region, group in _field._mass(g, k, rooms, xy, fit, float(params["angle"])):
            core = region.buffer(-0.5)
            core = core if not core.is_empty else region
            seeds = []
            for s in group:      # a body floating over ground that is taken (a tall room from below) seeds the nearest free ground
                pt = Point(xy[s.name])
                x, y = xy[s.name] if region.contains(pt) else shapely.get_coordinates(shapely.shortest_line(pt, core))[1]
                seeds.append(Seed(s.name, float(x), float(y), s.w * s.l * float((scales or {}).get(s.name, 1.0)) * storeys_of(g, s)))
            out.update(tessellate(kind, region, seeds, **params))
        return out

    for k in range(g.n):
        rooms = [s for s in g.rooms(k) if s.name in pos]
        if not rooms:
            continue
        tall = [s for s in rooms if storeys_of(g, s) > 1]
        if tall:      # a room standing through several storeys takes only ground that all of them have; the rest re-divide
            first = cut(k, rooms)
            for s in tall:
                st = storeys_of(g, s)
                poly = first.get(s.name)
                if poly is None:
                    continue
                for up in range(k + 1, k + st):
                    poly = poly.intersection(g.ground_at(up).difference(g.occupied(up)))
                parts = [q for q in getattr(poly, "geoms", [poly]) if q.geom_type == "Polygon" and q.area > 0.5]
                if not parts:
                    continue
                poly = max(parts, key=lambda q: q.area)
                lay[s.name] = Prism(_field._mm(poly), k * H, (k + st) * H)
                for up in range(k, k + st):
                    g.extra.setdefault(up, []).append(poly)
            rooms = [s for s in rooms if s not in tall]
        for name, poly in cut(k, rooms).items():
            lay[name] = Prism(_field._mm(poly), k * H, (k + 1) * H)
    return _layout.conform(lay)


def springs(f: Field) -> list[list[str]]:
    """The pairs joined by a spring, for drawing: required contacts and the `touch`/`near`/`stack` wishes."""
    rooms = {s.name for s in f.rooms()}
    out = {tuple(sorted(c)) for c in f.brief.contacts if c[0] in rooms and c[1] in rooms}
    for af in _aff.expand(f.brief) if _aff.written(f.brief) else []:
        if af.kind in ("touch", "near", "stack") and af.strength not in _aff.NEGATIVE and af.a in rooms:
            out |= {tuple(sorted((af.a, o))) for o in af.others if o in rooms}
    return [list(p) for p in sorted(out)]


def solve(brief: Brief, kind: str = "power", seed: int = 0, positions: dict | None = None, pins: tuple[str, ...] = (),
          scales: dict | None = None, relaxed: bool = True, iters: int | None = None, **params) -> dict:
    """One state of the contraption: where the bodies are, the storey cells cut from them, and every reading of
    M25–M27. No kernel. `scales` inflates rooms (name -> factor of the asked area)."""
    t0 = time.perf_counter()
    f = _field.prepare(brief, seed)
    start = {n: tuple(v) for n, v in (positions or {}).items()}
    pos = relax(f, seed, start=start, pins=tuple(pins), scales=scales, iters=iters or (80 if start else 300)) if relaxed or not start else start
    t1 = time.perf_counter()
    g = settle(f, pos, scales)
    if g.cells and relaxed:        # with a path, the rooms of each storey then line it as in M27
        xy = _field.relax(g, seed, start={n: p[:2] for n, p in pos.items()}, pins=tuple(pins), iters=120)
        pos = {n: (xy[n][0], xy[n][1], pos[n][2]) for n in pos}
    lay = build(g, pos, kind, scales, **params)
    t2 = time.perf_counter()
    ev = _field.evaluate(g, lay)
    rooms, asked, a, st, fill = bodies(g, scales)
    cap = capacity(f)
    load = [float(sum(asked[i] * fill for i, s in enumerate(rooms) if g.levels[s.name] <= k < g.levels[s.name] + st[i])) for k in range(g.n)]
    ev["scores"]["storey_balance"] = round(max(abs(l - c_) / c_ for l, c_ in zip(load, cap)), 6)
    share = {s.name: asked[i] * fill for i, s in enumerate(rooms)}     # what a room asks once the void is filled
    off = [abs(p.area / 1e6 - share[n]) / share[n] for n, p in lay.items() if n in share]
    ev["scores"]["share_deviation"] = round(sum(off) / len(off), 6) if off else 0.0
    return {"kind": kind, "seed": seed, "levels": g.n, "level_height": g.H, "fill": round(fill, 4),
            "positions": {n: list(v) for n, v in pos.items()},
            "bodies": [{"name": s.name, "x": pos[s.name][0], "y": pos[s.name][1], "z": pos[s.name][2], "radius": round(float(a[i]), 3),
                        "half_height": round(float(st[i] * g.H / 2), 3), "level": g.levels[s.name], "storeys": int(st[i]),
                        "scale": float((scales or {}).get(s.name, 1.0))} for i, s in enumerate(rooms) if s.name in pos],
            "springs": springs(g), "room_levels": {s.name: g.levels[s.name] for s in rooms},
            "storeys": [{"level": k, "ground": [list(p) for p in g.ground_at(k).exterior.coords[:-1]], "has": round(float(cap[k]), 1),
                         "asked": round(load[k], 1)} for k in range(g.n)],
            "ground": [list(p) for p in g.ground.exterior.coords[:-1]], "cells": _field.layout_payload(g, lay), **ev,
            "ms": {"relax": round(1000 * (t1 - t0)), "tessellate": round(1000 * (t2 - t1)), "measure": round(1000 * (time.perf_counter() - t2))}}


# ----------------------------------------------------------------------------- sketch mode: free cells

def free(f: Field, pos: dict, scales: dict | None = None, rounds: int = 30) -> dict:
    """Free polyhedral cells: a three-dimensional power diagram of the bodies, cut to each block of the void (to the
    block's convex hull: a concave block is a limit of the sketch). Weights move until a room's pieces hold its share
    of the volume. Returns pieces as vertex and face lists in full precision; rounding them would bend the sloping
    faces. A sketch: walls slope, so the storey measures do not apply; `volume_off` and the face slopes are reported."""
    from scipy.spatial import ConvexHull, HalfspaceIntersection
    rooms, asked, a, st, _fill = bodies(f, scales)
    rooms = [s for s in rooms if s.name in pos]
    n = len(rooms)
    P = np.array([pos[s.name] for s in rooms], dtype=float)
    H = f.H
    stretch = float(np.mean(a) / (H / 2))                 # lenses: measure height in the stretched space
    Q = P * np.array([1.0, 1.0, stretch])
    blocks = []
    for poly, lo, hi in (_field.void_blocks(f.brief) or [(f.ground, 0, f.n - 1)]):
        hull = shapely.geometry.polygon.orient(poly.convex_hull, 1.0)
        cs = list(hull.exterior.coords)
        hs = [[(q[1] - p[1]), -(q[0] - p[0]), 0.0, -((q[1] - p[1]) * p[0] - (q[0] - p[0]) * p[1])] for p, q in zip(cs, cs[1:])]
        hs += [[0, 0, 1.0, -(hi + 1) * H * stretch], [0, 0, -1.0, lo * H * stretch]]
        blocks.append((np.array(hs, dtype=float), hull, lo * H * stretch, (hi + 1) * H * stretch))
    void = sum(b[1].area * (b[3] - b[2]) for b in blocks)
    vol = asked * st
    T = vol / vol.sum() * void
    w = np.zeros(n)
    best = None
    for it in range(rounds + 1):
        sq = (Q ** 2).sum(axis=1) - w
        pieces = []
        got = np.zeros(n)
        for i in range(n):
            mine = np.array([[*(2 * (Q[j] - Q[i])), -(sq[j] - sq[i])] for j in range(n) if j != i]).reshape(-1, 4)
            for hs, hull, z0, z1 in blocks:
                A_ = np.vstack([mine, hs])
                seedpt = _inside(A_)
                if seedpt is None:
                    continue
                try:
                    h = ConvexHull(HalfspaceIntersection(A_, seedpt).intersections)
                except Exception:
                    continue
                if h.volume > 1e-6:
                    pieces.append((i, h))
                    got[i] += h.volume
        err = float((np.abs(got - T) / T).mean())
        if best is None or err < best[0]:
            best = (err, pieces, got)
        if it == rounds or err < 0.03:
            break
        w = w + 0.5 * (T - got) / np.cbrt(T)
        d2 = ((Q[:, None] - Q[None]) ** 2).sum(axis=2)
        np.fill_diagonal(d2, np.inf)
        w = np.clip(w - w.min(), 0.0, 0.95 * d2.min(axis=1))
    err, pieces, got = best
    out, level, upright, sloping = [], 0, 0, 0
    for i, h in pieces:
        pts = h.points / np.array([1.0, 1.0, stretch])
        faces: dict[tuple, set] = {}
        for simplex, eq in zip(h.simplices, h.equations):
            faces.setdefault(tuple(np.round(eq, 6)), set()).update(simplex.tolist())
        polys = []
        for eq, vs in faces.items():
            nrm = np.array(eq[:3]) * np.array([1.0, 1.0, stretch])
            nrm /= np.linalg.norm(nrm)
            q = pts[list(vs)]
            c0 = q.mean(axis=0)
            e1 = np.cross(nrm, [1, 0, 0] if abs(nrm[0]) < 0.9 else [0, 1, 0])
            e1 /= np.linalg.norm(e1)
            e2 = np.cross(nrm, e1)
            polys.append([list(map(float, p)) for p in q[np.argsort(np.arctan2((q - c0) @ e2, (q - c0) @ e1))]])
            level, upright, sloping = level + (abs(nrm[2]) > 0.999), upright + (abs(nrm[2]) < 0.02), sloping + (0.02 <= abs(nrm[2]) <= 0.999)
        out.append({"name": rooms[i].name, "program": rooms[i].program, "volume": round(float(h.volume / stretch), 3), "faces": polys})
    return {"pieces": out, "rooms": n, "volume_off": round(err, 4), "void_m3": round(void / stretch, 1),
            "split_rooms": sorted({rooms[i].name for i, _ in pieces if sum(1 for j, _ in pieces if j == i) > 1}),
            "missing": sorted(s.name for k, s in enumerate(rooms) if got[k] <= 0),
            "faces": {"level": int(level), "upright": int(upright), "sloping": int(sloping)}}


def _inside(A_: np.ndarray):
    """A point strictly inside the halfspaces A x + b <= 0 (the centre of the largest ball), or None."""
    from scipy.optimize import linprog
    norm = np.linalg.norm(A_[:, :3], axis=1)
    res = linprog([0, 0, 0, -1], A_ub=np.hstack([A_[:, :3], norm[:, None]]), b_ub=-A_[:, 3], bounds=[(None, None)] * 3 + [(0, None)], method="highs")
    return res.x[:3] if res.success and res.x[3] > 1e-6 else None


def realise_free(sketch: dict):
    """The sketch as a topologic CellComplex: one Cell per piece, named; faces keep their full precision."""
    from topologicpy.Cell import Cell
    from topologicpy.CellComplex import CellComplex
    from topologicpy.Dictionary import Dictionary
    from topologicpy.Face import Face
    from topologicpy.Topology import Topology
    from topologicpy.Vertex import Vertex
    cells = []
    for p in sketch["pieces"]:
        fs = [Face.ByVertices([Vertex.ByCoordinates(*v) for v in poly], silent=True) for poly in p["faces"]]
        c = Cell.ByFaces([x for x in fs if x is not None], silent=True) if all(x is not None for x in fs) else None
        if c is not None and Topology.IsInstance(c, "Cell"):
            Topology.SetDictionary(c, Dictionary.ByPythonDictionary({"name": p["name"], "program": p["program"], "volume": p["volume"]}))
            cells.append(c)
    cc = CellComplex.ByCells(cells, silent=True) if len(cells) > 1 else (cells[0] if cells else None)
    return cc, cells
