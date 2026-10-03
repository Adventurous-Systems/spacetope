"""Rectangular-dual generator (PLAN M12, design note B, prototype docs/experiments/2026-09-20_dual_proto.py).

Starts from the wish graph instead of from geometry:

1. `ptp_graph`   one planar embedding is kept and chords are inserted into it until every inner face is a triangle.
                 A corridor may appear twice on the outer walk (it reaches two opposite walls); rooms may not.
                 A ring of void cells goes between the outer rooms and the four outer vertices N, E, S, W, so rows
                 of unequal depth can line a straight wall; rooms flanking a corridor end sit on the wall themselves.
2. `labellings`  every regular edge labelling (blue = left of, red = below; four runs around each inner vertex)
                 found by CP-SAT with blocking clauses. One labelling = one plan topology.
3. `dimension`   walls are the faces of the red and blue st-graphs; integer-mm positions per wall under each
                 space's tolerance band and door-width overlaps. Any solution is a valid dissection.
4. voids are dropped, the placement is pre-verified on integer boxes and kept if its topology class is new.

Pure Python + networkx + ortools. Single level. Seeds vary the embedding, the corridor side of each room and the
direction of each void staircase, which is where the variety comes from on corridor briefs (the labelling lattice
of one triangulation is small there)."""
from __future__ import annotations

import random
import time
from dataclasses import dataclass, replace

import networkx as nx
from ortools.sat.python import cp_model

from ..brief import Brief
from ..doors import required_overlap_mm
from ..levels import envelope_mm, level_height_mm
from ..placement import topology_classes
from ..preverify import preverify
from .grid import Box

OUTER = ("N", "E", "S", "W")
LABELS = ("OB", "OR", "IB", "IR")            # counter-clockwise order of the four runs around an inner vertex
REV = {"OB": "IB", "IB": "OB", "OR": "IR", "IR": "OR"}
VOID_MAX = 200_000


class NotPlanar(ValueError):
    """The wish graph cannot be drawn without crossings, so no rectangular dual exists."""


class WillNotTile(ValueError):
    """The wishes can be drawn, but the rooms cannot tile a rectangle inside their tolerance bands."""


TOLERANCE_PROBE = (0.15, 0.2, 0.25, 0.3, 0.4, 0.5, 0.75)


@dataclass
class DualParams:
    k: int = 8
    max_seeds: int = 200
    rel_cap: int = 12              # labellings tried per triangulation
    time_limit: float = 60.0
    size_seconds: float = 2.0      # CP-SAT limit per labelling when sizing
    door_mm: int = 900
    workers: int = 4


# ----------------------------------------------------------------------------- planar structure

def faces_of(emb: nx.PlanarEmbedding) -> list[list]:
    seen, out = set(), []
    for u, v in emb.edges():
        if (u, v) not in seen:
            out.append(emb.traverse_face(u, v, mark_half_edges=seen))
    return out


def insert_chord(emb: nx.PlanarEmbedding, a, v, b) -> nx.PlanarEmbedding:
    """Chord a-b inside the face that walks (a, v, b). networkx convention, read from its source: at a node reached
    from x the face continues to the counter-clockwise successor of x; add_half_edge(s, e, cw=r) puts the new edge
    immediately counter-clockwise of r, ccw=r immediately clockwise of r."""
    e2 = emb.copy()
    e2.add_half_edge(a, b, ccw=v)
    e2.add_half_edge(b, a, cw=v)
    e2.check_structure()
    if not any(len(f) == 3 and set(f) == {a, v, b} for f in (e2.traverse_face(a, b), e2.traverse_face(b, a))):
        raise RuntimeError(f"chord {a}-{b} around {v} did not cut a triangle")
    return e2


def ptp_graph(G: nx.Graph, seed: int, through: set[str]):
    """(graph with voids and N/E/S/W, embedding, voids, added chords) or None when this seed's embedding leaves a
    separating triangle (a wish triangle with a room embedded inside it)."""
    rng = random.Random(seed)
    nodes = list(G.nodes); rng.shuffle(nodes); edges = list(G.edges); rng.shuffle(edges)
    G2 = nx.Graph(); G2.add_nodes_from(nodes); G2.add_edges_from(edges); G = G2
    ok, emb = nx.check_planarity(G)
    if not ok:
        raise NotPlanar("the required contacts cannot be drawn without crossings")
    added: list[tuple] = []
    kept: dict = {}
    for _ in range(1000):
        fs = faces_of(emb); fs.sort(key=len, reverse=True)
        outer, inner = fs[0], fs[1:]
        action = None
        occ: dict = {}
        for i, v in enumerate(outer):
            occ.setdefault(v, []).append(i)
        for v, idx in occ.items():
            if len(idx) < 2:
                continue
            if v in through and v not in kept:          # two opposite occurrences stay open: balanced sides
                a0 = rng.randrange(len(idx))
                kept[v] = {(outer[i - 1], outer[(i + 1) % len(outer)]) for i in (idx[a0], idx[(a0 + len(idx) // 2) % len(idx)])}
            for i in idx:
                pair = (outer[i - 1], outer[(i + 1) % len(outer)])
                if v in kept and (pair in kept[v] or pair[::-1] in kept[v]):
                    continue
                if pair[0] != pair[1] and not G.has_edge(*pair):
                    action = ("chord", pair[0], v, pair[1]); break
            if action:
                break
        if not action:
            for f in inner:
                occ = {}
                for i, v in enumerate(f):
                    occ.setdefault(v, []).append(i)
                rep = [i for idx in occ.values() if len(idx) > 1 for i in idx]
                # Filling a face with a void instead of chording it was tried on 2026-10-03 and reverted: by the
                # time this runs the outer-walk chording has already left every inner face a triangle, so the
                # branch never fired on any fixture, nor on a deliberately sparse chain or star (PLAN §5).
                for i in (rep if rep else (range(len(f)) if len(f) > 3 else ())):
                    a, b = f[i - 1], f[(i + 1) % len(f)]
                    if a != b and not G.has_edge(a, b):
                        action = ("chord", a, f[i], b); break
                if action:
                    break
        if not action:
            break
        _, a, v, b = action
        emb = insert_chord(emb, a, v, b); G.add_edge(a, b); added.append((a, b))
    fs = faces_of(emb); fs.sort(key=len, reverse=True)
    outer = fs[0]; n = len(outer)
    thr_pos = {i for i, v in enumerate(outer) if v in through and outer.count(v) == 2}
    is_c = lambda i: (i % n) in thr_pos  # noqa: E731
    entries: list[tuple[str, int, str]] = []          # ring around the outer walk: (kind, walk position, name)
    for i, v in enumerate(outer):
        void = f"void_{i}_{v}"
        if is_c(i) or (is_c(i - 1) and is_c(i + 1)):
            entries.append(("room", i, v))
        elif is_c(i - 1):
            entries += [("room", i, v), ("void", i, void)]   # a room at a corridor end sits on the wall; void at the corner
        elif is_c(i + 1):
            entries += [("void", i, void), ("room", i, v)]
        else:
            entries.append(("void", i, void))
    if not thr_pos and n == 3:
        entries.insert(1, ("void", 0, f"void_0b_{outer[0]}"))    # a ring of three voids would be a separating triangle
    Ga = nx.Graph(G); voids: list[str] = []
    for kind, i, name in entries:
        if kind == "void":
            voids.append(name); Ga.add_edge(name, outer[i])
    m = len(entries)
    for q in range(m):
        (k1, p1, n1), (k2, p2, n2) = entries[q], entries[(q + 1) % m]
        Ga.add_edge(n1, n2)
        if k1 == "void" and k2 == "void" and p1 != p2:       # which room the neighbouring void also touches = step direction
            Ga.add_edge(n1, outer[p2]) if rng.random() < 0.5 else Ga.add_edge(n2, outer[p1])
        elif k1 == "void" and p1 != p2:
            Ga.add_edge(n1, outer[p2])

    def ring(a: int, b: int) -> list[int]:
        out = [a % m]
        while out[-1] != b % m:
            out.append((out[-1] + 1) % m)
        return out

    thr = sorted(thr_pos)
    if thr:
        ia = next(q for q, e in enumerate(entries) if e[0] == "room" and e[1] == thr[0])
        ib = next(q for q, e in enumerate(entries) if e[0] == "room" and e[1] == thr[1])

        def corner(start: int, step: int, stop: int) -> int:
            q = start
            while q % m != stop % m and entries[q % m][0] != "void":
                q += step
            return (q if entries[q % m][0] == "void" else start) % m
        c_nw, c_ne, c_se, c_sw = corner(ia + 1, 1, ib), corner(ib - 1, -1, ia), corner(ib + 1, 1, ia), corner(ia - 1, -1, ib)
        pos = {"N": ring(c_nw, c_ne), "E": ring(c_ne, c_se), "S": ring(c_se, c_sw), "W": ring(c_sw, c_nw)}
    else:
        rot = rng.randrange(m); cs = [(rot + int(k * m / 4)) % m for k in range(4)]
        pos = {name: ring(cs[k], cs[(k + 1) % 4]) for k, name in enumerate(OUTER)}
    for name, qs in pos.items():
        for q in qs:
            Ga.add_edge(name, entries[q][2])
    Ga.add_edges_from([("N", "E"), ("E", "S"), ("S", "W"), ("W", "N")])
    ok, emb2 = nx.check_planarity(Ga)      # safe here: the finished triangulation is 3-connected, its embedding unique
    if not ok:
        return None
    fs2 = faces_of(emb2)
    fset = {frozenset(f) for f in fs2}
    if any(len(f) > 3 and set(f) != set(OUTER) for f in fs2):
        return None
    if any(len(c) == 3 and frozenset(c) not in fset for c in nx.enumerate_all_cliques(Ga) if len(c) <= 3):
        return None
    return Ga, emb2, voids, added


# ----------------------------------------------------------------------------- regular edge labellings

def labellings(G: nx.Graph, emb: nx.PlanarEmbedding, cap: int, seed: int) -> tuple[list[dict], bool | None]:
    """Up to `cap` labellings as {(u, v): 'B' | 'R'} (u left of v, or u below v) and the orientation that worked."""
    for ccw in (True, False):
        inner = [v for v in G.nodes if v not in OUTER]
        lab_edges = [(u, v) for u, v in G.edges() if not (u in OUTER and v in OUTER)]
        m = cp_model.CpModel(); L: dict = {}
        for u, v in lab_edges:
            for end in (u, v):
                L[(end, u, v)] = {c: m.NewBoolVar(f"{end}|{u}|{v}|{c}") for c in LABELS}
                m.AddExactlyOne(L[(end, u, v)].values())
            for c in LABELS:
                m.Add(L[(u, u, v)][c] == L[(v, u, v)][REV[c]])

        def lab(v, w):
            return L[(v, v, w)] if (v, v, w) in L else L[(v, w, v)]
        for v in inner:
            order = list(emb.neighbors_cw_order(v))
            if ccw:
                order = order[::-1]
            labs = [lab(v, w) for w in order]
            for c in LABELS:
                m.AddBoolOr([lb[c] for lb in labs])
            changes = []
            for i in range(len(labs)):
                a, b = labs[i], labs[(i + 1) % len(labs)]
                ch = m.NewBoolVar(f"ch|{v}|{i}"); changes.append(ch)
                for ci, c in enumerate(LABELS):
                    nxt = LABELS[(ci + 1) % 4]
                    m.AddBoolOr([a[c].Not(), b[c], b[nxt]])
                    m.AddBoolOr([a[c].Not(), b[c].Not(), ch.Not()])
                    m.AddBoolOr([a[c].Not(), b[nxt].Not(), ch])
            m.Add(sum(changes) == 4)
        for o, c in {"N": "IR", "E": "IB", "S": "OR", "W": "OB"}.items():
            for w in G.neighbors(o):
                if w not in OUTER:
                    m.Add(lab(o, w)[c] == 1)
        solver = cp_model.CpSolver(); solver.parameters.num_workers = 1; solver.parameters.random_seed = seed
        out = []
        while len(out) < cap:
            if solver.Solve(m) not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
                break
            rel = {}
            for u, v in lab_edges:
                c = next(c for c in LABELS if solver.Value(L[(u, u, v)][c]))
                rel[(u, v) if c in ("OB", "OR") else (v, u)] = "B" if c in ("OB", "IB") else "R"
            out.append(rel)
            m.AddBoolOr([L[(u, u, v)][c].Not() for u, v in lab_edges for c in LABELS if solver.Value(L[(u, u, v)][c])])
        if out:
            return out, ccw
    return [], None


def _st_faces(G, emb, rel, colour: str, ccw: bool):
    """Faces of one colour's st-graph (closed by the outer 4-cycle) as sets of angles (v, a, b), b ccw-next of a."""
    edges = {e for e, c in rel.items() if c == colour}
    edges |= {("S", "W"), ("W", "N"), ("S", "E"), ("E", "N")} if colour == "R" else {("W", "S"), ("S", "E"), ("W", "N"), ("N", "E")}
    und = {frozenset(e) for e in edges}
    rot = {}
    for v in G.nodes:
        order = list(emb.neighbors_cw_order(v))
        if ccw:
            order = order[::-1]
        rot[v] = [w for w in order if frozenset((v, w)) in und]
    face_of: dict = {}
    faces = []
    for v, r in rot.items():
        for i in range(len(r)):
            cur = (v, r[i], r[(i + 1) % len(r)])
            if cur in face_of:
                continue
            f = []
            while cur not in face_of:
                face_of[cur] = len(faces); f.append(cur)
                x, _a, b = cur
                rb = rot[b]
                cur = (b, x, rb[(rb.index(x) + 1) % len(rb)])
            faces.append(f)
    return faces, face_of, rot


def dimension(G, emb, rel, ccw, bands, nominal, need, p: DualParams, envelope: dict | None = None) -> dict | None:
    """Integer-mm (x, y, w, l) per inner vertex, or None. bands[v] = ((w_lo, w_hi), (l_lo, l_hi)); voids are free."""
    inner = [v for v in G.nodes if v not in OUTER]
    rf, rof, rrot = _st_faces(G, emb, rel, "R", ccw)     # faces of the red graph = vertical walls
    bf, bof, brot = _st_faces(G, emb, rel, "B", ccw)     # faces of the blue graph = horizontal walls
    m = cp_model.CpModel()
    X = [m.NewIntVar(0, VOID_MAX, f"X{i}") for i in range(len(rf))]
    Y = [m.NewIntVar(0, VOID_MAX, f"Y{i}") for i in range(len(bf))]
    left, right, bottom, top = {}, {}, {}, {}
    for v in inner:
        order = list(emb.neighbors_cw_order(v))
        if ccw:
            order = order[::-1]
        labs = [("O" + rel[(v, w)], w) if (v, w) in rel else ("I" + rel[(w, v)], w) for w in order]

        def boundary(a: str, b: str):
            n = len(labs)
            for i, (c, _) in enumerate(labs):
                if c != a:
                    continue
                j = (i + 1) % n
                while labs[j][0] not in (a, b) and j != i:
                    j = (j + 1) % n
                if labs[j][0] == b:
                    return labs[i][1], labs[j][1]
            raise RuntimeError(f"no run boundary {a}->{b} at {v}")
        right[v] = rof[(v, *boundary("IR", "OR"))]; left[v] = rof[(v, *boundary("OR", "IR"))]
        top[v] = bof[(v, *boundary("OB", "IB"))]; bottom[v] = bof[(v, *boundary("IB", "OB"))]
    rots = {}
    for v in inner:
        (wl, wh), (ll, lh) = bands[v]
        r = m.NewBoolVar(f"rot|{v}"); rots[v] = r
        W = X[right[v]] - X[left[v]]; Lv = Y[top[v]] - Y[bottom[v]]
        for expr, plain, turned in ((W, (wl, wh), (ll, lh)), (Lv, (ll, lh), (wl, wh))):
            m.Add(expr >= plain[0]).OnlyEnforceIf(r.Not()); m.Add(expr <= plain[1]).OnlyEnforceIf(r.Not())
            m.Add(expr >= turned[0]).OnlyEnforceIf(r); m.Add(expr <= turned[1]).OnlyEnforceIf(r)
    for (u, v), c in rel.items():
        rot, of = (rrot, rof) if c == "R" else (brot, bof)
        ru = rot[u]; i = ru.index(v)
        hi, lo = of[(u, ru[i - 1], v)], of[(u, v, ru[(i + 1) % len(ru)])]   # the shared wall runs between these two walls
        if c == "R":
            m.Add(X[hi] - X[lo] >= need.get(frozenset((u, v)), 1))
        else:
            m.Add(Y[lo] - Y[hi] >= need.get(frozenset((u, v)), 1))

    def wall(faces, of, o):
        unbounded = next((i for i, f in enumerate(faces) if all(a[0] in OUTER for a in f)), None)
        return next(of[a] for a in of if a[0] == o and of[a] != unbounded)
    xw, xe, ys, yn = wall(rf, rof, "W"), wall(rf, rof, "E"), wall(bf, bof, "S"), wall(bf, bof, "N")
    m.Add(X[xw] == 0); m.Add(Y[ys] == 0)
    if envelope:
        m.Add(X[xe] <= envelope["w"] + 2000); m.Add(Y[yn] <= envelope["l"] + 2000)   # voids may add a little outside the rooms
    dev = []
    for v in inner:
        if v not in nominal:
            continue
        nw, nl = nominal[v]
        W = X[right[v]] - X[left[v]]; Lv = Y[top[v]] - Y[bottom[v]]
        for expr, plain, turned in ((W, nw, nl), (Lv, nl, nw)):
            d = m.NewIntVar(0, VOID_MAX, "")
            m.Add(d >= expr - plain).OnlyEnforceIf(rots[v].Not()); m.Add(d >= plain - expr).OnlyEnforceIf(rots[v].Not())
            m.Add(d >= expr - turned).OnlyEnforceIf(rots[v]); m.Add(d >= turned - expr).OnlyEnforceIf(rots[v])
            dev.append(d)
    m.Minimize(10 * sum(dev) + X[xe] + Y[yn])
    s = cp_model.CpSolver(); s.parameters.num_workers = p.workers; s.parameters.max_time_in_seconds = p.size_seconds
    if s.Solve(m) not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return None
    return {v: (s.Value(X[left[v]]), s.Value(Y[bottom[v]]), s.Value(X[right[v]]) - s.Value(X[left[v]]),
                s.Value(Y[top[v]]) - s.Value(Y[bottom[v]])) for v in inner}


# ----------------------------------------------------------------------------- generator

def _widen(nominal: dict[str, tuple[int, int]], names, tol: float) -> dict:
    """Bands at a uniform ±tol around each nominal, for asking how much give the brief would need."""
    return {n: ((max(1, int(nominal[n][0] * (1 - tol))), int(nominal[n][0] * (1 + tol))),
                (max(1, int(nominal[n][1] * (1 - tol))), int(nominal[n][1] * (1 + tol)))) for n in names}


def tolerance_needed(probes, nominal, p: DualParams, env, deadline: float) -> float | None:
    """The smallest uniform tolerance from `TOLERANCE_PROBE` at which any kept drawing sizes, or None if none does
    by the deadline. Used only to explain a failure, never to loosen what the architect asked for."""
    quick = replace(p, size_seconds=min(p.size_seconds, 1.0))
    for tol in TOLERANCE_PROBE:
        for Ga, emb, rels, ccw, bands, need, voids in probes:
            wide = dict(bands)
            wide.update(_widen(nominal, [n for n in bands if n not in voids and n in nominal], tol))
            for rel in rels[:2]:
                if time.perf_counter() > deadline:
                    return None
                try:
                    if dimension(Ga, emb, rel, ccw, wide, nominal, need, quick, env):
                        return tol
                except (RuntimeError, KeyError, StopIteration):
                    continue
    return None


def dual_generator(brief: Brief, params: dict | None = None, seed: int = 0) -> list[dict[str, Box]]:
    p = DualParams(**(params or {}))
    G = nx.Graph(); G.add_nodes_from(s.name for s in brief.spaces); G.add_edges_from(brief.contacts)
    if not nx.check_planarity(G)[0]:
        raise NotPlanar("the required contacts cannot be drawn without crossings, so they cannot all be shared walls on one level")
    through = {s.name for s in brief.spaces if s.program == "corridor"}
    H = level_height_mm(brief); env = envelope_mm(brief)
    bands = {s.name: (s.band("w"), s.band("l")) for s in brief.spaces}
    nominal = {s.name: (s.nominal_mm("w"), s.nominal_mm("l")) for s in brief.spaces}
    t0 = time.perf_counter()
    out: list[dict[str, Box]] = []
    graphs = labellings_found = 0
    probes: list[tuple] = []            # drawings kept aside, to explain a failure with
    for i in range(p.max_seeds):
        if len(out) >= p.k or time.perf_counter() - t0 > p.time_limit:
            break
        try:
            built = ptp_graph(G, seed * 7919 + i, through)
        except (nx.NetworkXException, RuntimeError, AssertionError, StopIteration, KeyError, IndexError):
            continue        # an embedding this construction cannot triangulate; a NameError or the like must not
                            # be caught here — a blanket except once hid a missing helper as "this seed failed"
        if built is None:
            continue
        Ga, emb, voids, _added = built
        b2 = dict(bands)
        for v in voids:
            b2[v] = ((1, VOID_MAX), (1, VOID_MAX))
        need = {frozenset((a, b)): (1 if (a in voids or b in voids) else required_overlap_mm(brief, a, b, p.door_mm))
                for a, b in Ga.edges() if a not in OUTER and b not in OUTER}
        graphs += 1
        rels, ccw = labellings(Ga, emb, p.rel_cap, seed + i)
        labellings_found += len(rels)
        if rels and len(probes) < 3:
            probes.append((Ga, emb, rels, ccw, b2, need, voids))
        for rel in rels:
            if len(out) >= p.k or time.perf_counter() - t0 > p.time_limit:
                break
            try:
                dim = dimension(Ga, emb, rel, ccw, b2, nominal, need, p, env)
            except (RuntimeError, KeyError, StopIteration):
                continue
            if not dim:
                continue
            rooms = {v: xywl for v, xywl in dim.items() if v not in voids}
            x0 = min(x for x, _, _, _ in rooms.values()); y0 = min(y for _, y, _, _ in rooms.values())
            pl = {v: Box(x - x0, y - y0, 0, w, l, H) for v, (x, y, w, l) in rooms.items()}
            if not preverify(brief, pl)[0]:
                continue
            if out and len(set(topology_classes(brief, out + [pl]))) == len(out):
                continue                                   # same topology class as one already kept (out holds one per class)
            out.append(pl)
    if out:
        return out
    # Nothing came back. Say which wall it hit, rather than hand the architect an empty gallery (PLAN M12, §6.0).
    if graphs == 0:
        raise WillNotTile("the wished contacts leave a room enclosed by three others that all touch each other, "
                          "which no arrangement of rectangles can satisfy; relax one of those contacts")
    if labellings_found == 0:
        raise WillNotTile(f"the wishes were drawn {graphs} ways and none admits a rectangular plan")
    if probes:
        tol = tolerance_needed(probes, nominal, p, env, time.perf_counter() + max(5.0, p.time_limit / 3))
        if tol is not None:
            raise WillNotTile(
                f"these rooms cannot tile a rectangle within their tolerance: {labellings_found} arrangements were "
                f"found over {graphs} drawings and none could be sized. A rectangular plan leaves no slack, so every "
                f"room's size is fixed by the walls it shares. About ±{int(tol * 100)} % would be needed, against the "
                f"±10 % the brief allows. Widen the tolerance of the rooms that must touch each other, or use `beam` "
                f"or `cpsat`, which may leave space between rooms.")
    raise WillNotTile(f"{labellings_found} arrangements over {graphs} drawings, none of which could be sized within "
                      f"the tolerance bands, at any tolerance tried")
