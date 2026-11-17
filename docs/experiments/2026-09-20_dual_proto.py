# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Adventurous Systems

"""Prototype of docs/2026-09-14_STRETCH_GOALS_DESIGN.md §B.3–B.5: wish graph -> PTP graph -> RELs by CP-SAT -> wall
segments -> integer dimensioning. Pure networkx + ortools; verification by spacetope.verify at the end."""
from __future__ import annotations
import itertools, json, random, sys, time
import networkx as nx
from ortools.sat.python import cp_model

OUTER = ("N", "E", "S", "W")
LABELS = ("OB", "OR", "IB", "IR")           # ccw order around an inner vertex
REV = {"OB": "IB", "IB": "OB", "OR": "IR", "IR": "OR"}


def faces_of(emb: nx.PlanarEmbedding):
    seen, out = set(), []
    for u, v in emb.edges():
        if (u, v) in seen: continue
        f = emb.traverse_face(u, v, mark_half_edges=seen)
        out.append(f)
    return out


def _add_half_edge(emb, start, end, ref, side):
    if hasattr(emb, "add_half_edge"):
        emb.add_half_edge(start, end, **({side: ref} if ref is not None else {}))
    else:
        getattr(emb, f"add_half_edge_{side}")(start, end, ref) if ref is not None else emb.add_half_edge_first(start, end)


def _try(emb, ops):
    """Apply half-edge insertions on a copy; return the copy if networkx accepts the structure, else None."""
    e2 = emb.copy()
    try:
        for start, end, ref, side in ops:
            _add_half_edge(e2, start, end, ref, side)
        e2.check_structure()
        return e2
    except Exception as ex:
        _try.last = f"{type(ex).__name__}: {ex}"
        return None


def _incident(e, u, v):
    return [e.traverse_face(u, v), e.traverse_face(v, u)]


# networkx convention (read from source): walking a face, at w arrived from v the next node is the ccw-successor of v
# at w; add_half_edge(s, e, cw=r) puts the new edge immediately ccw of r, add_half_edge(s, e, ccw=r) immediately cw of r.

def insert_chord(emb, a, v, b):
    """Add chord a-b inside the face that walks (a, v, b). Deterministic from the traversal convention."""
    e2 = emb.copy()
    e2.add_half_edge(a, b, ccw=v)     # at a the face angle runs ccw from a's predecessor to v: the chord sits just cw of v
    e2.add_half_edge(b, a, cw=v)      # at b the angle runs ccw from v to b's successor: the chord sits just ccw of v
    e2.check_structure()
    assert any(len(f) == 3 and set(f) == {a, v, b} for f in _incident(e2, a, b)), f"chord {a}-{b} around {v} did not cut a triangle"
    return e2


def find_run(walk, names):
    n = len(walk)
    for i in range(n):
        if all(walk[(i + k) % n] == names[k] for k in range(len(names))): return i
    raise RuntimeError(f"run {names} not on walk {walk}")


def insert_vertex(emb, new, walk, start, count):
    """Add a new vertex inside the face `walk`, adjacent to the `count` consecutive walk vertices from index `start`."""
    e = emb.copy(); e.add_node(new)
    n = len(walk); prev_t = None
    for k in range(count):
        i = (start + k) % n; v = walk[i]; prv = walk[i - 1]
        e.add_half_edge(v, new, cw=prv)                       # inside v's face angle, which runs ccw from prv to its successor
        if prev_t is None: e.add_half_edge(new, v)
        else: e.add_half_edge(new, v, ccw=prev_t)             # around `new` the targets run cw in walk order
        prev_t = v
    e.check_structure()
    return e


OUT = "__out__"


def outer_walk(emb):
    """The face holding the marker pendant OUT, with the marker removed from the walk (longest face before the marker exists)."""
    fs = faces_of(emb)
    if OUT in emb:
        f = next(f for f in fs if OUT in f)
        i = f.index(OUT)
        return f[:i - 1] + f[i + 1:] if i > 0 else f[2:]   # walk reads .., x, OUT, x, ..: drop OUT and one x
    fs.sort(key=len, reverse=True); return fs[0]


def make_ptp(G: nx.Graph, seed: int = 0, corner_voids: bool = True, through: set | None = None):
    """Return (G', embedding, outer_walk, added_edges, arcs, separating_triangles, voids).

    1. Chord the wish graph inside one maintained embedding until every inner face is a triangle and the outer walk
       repeats only `through` vertices (corridors), each exactly twice (it reaches two opposite walls).
    2. Ring of voids: one void per room on the outer walk, between the room and the outer wall, so rows of rooms
       of different depth can line a straight wall (the voids are dropped before realisation: a jagged outline).
    3. N, E, S, W attached to the voids (and to the corridor ends); the final triangulation is 3-connected, so its
       embedding is unique and one check_planarity call is safe."""
    through = set(through or ())
    rng = random.Random(seed)
    nodes = list(G.nodes); rng.shuffle(nodes); edges = list(G.edges); rng.shuffle(edges)
    G2 = nx.Graph(); G2.add_nodes_from(nodes); G2.add_edges_from(edges); G = G2; added = []
    ok, emb = nx.check_planarity(G); assert ok, "wish graph is not planar"
    kept: dict = {}
    for _round in range(500):
        fs = faces_of(emb); fs.sort(key=len, reverse=True)
        outer, inner = fs[0], fs[1:]
        action = None
        occ = {}
        for i, v in enumerate(outer): occ.setdefault(v, []).append(i)
        for v, idx in occ.items():
            if len(idx) < 2: continue
            if v in through and v not in kept:
                a0 = rng.randrange(len(idx)); ks = [idx[a0], idx[(a0 + len(idx) // 2) % len(idx)]]
                kept[v] = {(outer[i - 1], outer[(i + 1) % len(outer)]) for i in ks}
            for i in idx:
                pair = (outer[i - 1], outer[(i + 1) % len(outer)])
                if v in kept and (pair in kept[v] or pair[::-1] in kept[v]): continue
                if pair[0] != pair[1] and not G.has_edge(*pair):
                    action = (pair[0], v, pair[1]); break
            if action: break
        if not action:
            for f in inner:
                occ = {}
                for i, v in enumerate(f): occ.setdefault(v, []).append(i)
                rep = [i for v, idx in occ.items() if len(idx) > 1 for i in idx]
                cand = rep if rep else (list(range(len(f))) if len(f) > 3 else [])
                for i in cand:
                    a, b = f[i - 1], f[(i + 1) % len(f)]
                    if a != b and not G.has_edge(a, b):
                        action = (a, f[i], b); break
                if action: break
        if not action: break
        a, v, b = action
        emb = insert_chord(emb, a, v, b); G.add_edge(a, b); added.append((a, b))
    outer = outer_walk(emb); n = len(outer)
    thr_pos = {p_ for p_, v in enumerate(outer) if v in through and outer.count(v) == 2}
    is_c = lambda p_: (p_ % n) in thr_pos
    # 2. ring around the outer walk: a void between each room and the wall, except that a room flanking a corridor
    #    end sits on the wall itself with its void at the corner; a 3-walk gets a second void so the ring is a 4-cycle
    entries = []                                   # (kind, position, name) in walk order
    for p_ in range(n):
        v = outer[p_]
        if is_c(p_): entries.append(("room", p_, v)); continue
        void = f"void_{p_}_{v}"
        if is_c(p_ - 1) and is_c(p_ + 1): entries.append(("room", p_, v))
        elif is_c(p_ - 1): entries += [("room", p_, v), ("void", p_, void)]
        elif is_c(p_ + 1): entries += [("void", p_, void), ("room", p_, v)]
        else: entries.append(("void", p_, void))
    if not thr_pos and n == 3: entries.insert(1, ("void", 0, f"void_0b_{outer[0]}"))
    Ga = nx.Graph(G); voids = []
    for k, p_, name in entries:
        if k == "void": voids.append(name); Ga.add_edge(name, outer[p_])
    m = len(entries)
    for q in range(m):
        (k1, p1, n1), (k2, p2, n2) = entries[q], entries[(q + 1) % m]
        Ga.add_edge(n1, n2)
        if k1 == "void" and k2 == "void" and p1 != p2:
            # the two voids touch; which room the other void also touches decides the staircase direction here
            Ga.add_edge(n1, outer[p2]) if rng.random() < 0.5 else Ga.add_edge(n2, outer[p1])
        elif k1 == "void" and p1 != p2: Ga.add_edge(n1, outer[p2])
    # 3. outer vertices on arcs of ring entries; corners are the voids nearest the corridor ends, else evenly spaced
    def rng_idx(a, b):                             # cyclic inclusive range of ring indices
        out = [a % m]
        while out[-1] != b % m: out.append((out[-1] + 1) % m)
        return out
    thr = sorted(thr_pos)
    if thr:
        ia = next(q for q, e in enumerate(entries) if e[0] == "room" and e[1] == thr[0])
        ib = next(q for q, e in enumerate(entries) if e[0] == "room" and e[1] == thr[1])
        def corner(from_q, step, stop_q):
            q = from_q
            while q % m != stop_q % m and entries[q % m][0] != "void": q += step
            return (q if entries[q % m][0] == "void" else from_q) % m
        cNW, cNE = corner(ia + 1, +1, ib), corner(ib - 1, -1, ia)
        cSE, cSW = corner(ib + 1, +1, ia), corner(ia - 1, -1, ib)
        pos = {"N": rng_idx(cNW, cNE), "E": rng_idx(cNE, cSE), "S": rng_idx(cSE, cSW), "W": rng_idx(cSW, cNW)}
    else:
        rot = rng.randrange(m); corners = [(rot + int(k * m / 4)) % m for k in range(4)]
        pos = {name: rng_idx(corners[k], corners[(k + 1) % 4]) for k, name in enumerate(OUTER)}
    arcs = {}
    for name, qs in pos.items():
        arcs[name] = [entries[q][2] for q in qs]
        for x in arcs[name]: Ga.add_edge(name, x)
    Ga.add_edges_from([("N", "E"), ("E", "S"), ("S", "W"), ("W", "N")])
    ok, emb2 = nx.check_planarity(Ga)
    if not ok: return Ga, None, outer, added, arcs, [("nonplanar", "ring", "construction")], voids
    fset = {frozenset(f) for f in faces_of(emb2)}
    big = [f for f in faces_of(emb2) if len(f) > 3 and set(f) != set(OUTER)]
    tri = [c for c in nx.enumerate_all_cliques(Ga) if len(c) == 3]
    sep = [c for c in tri if frozenset(c) not in fset] + [("face", len(f), f[:4]) for f in big]
    return Ga, emb2, outer, added, arcs, sep, voids


def rel_model(G, emb, ccw: bool):
    inner = [v for v in G.nodes if v not in OUTER]
    lab_edges = [(u, v) for u, v in G.edges() if not (u in OUTER and v in OUTER)]
    m = cp_model.CpModel(); L = {}
    for u, v in lab_edges:
        for end in (u, v):
            L[(end, u, v)] = {c: m.NewBoolVar(f"{end}|{u}-{v}|{c}") for c in LABELS}
            m.AddExactlyOne(L[(end, u, v)].values())
        for c in LABELS:                                   # consistency across the edge
            m.Add(L[(u, u, v)][c] == L[(v, u, v)][REV[c]])
    def lab(v, w):
        e = (v, w) if (v, w, ) and ((v, w) in G.edges) else (w, v)
        key = (v, v, w) if (v, v, w) in L else (v, w, v)
        return L[key]
    for v in inner:
        order = list(emb.neighbors_cw_order(v))
        if ccw: order = order[::-1]
        n = len(order)
        labs = [lab(v, w) for w in order]
        for c in LABELS: m.AddBoolOr([lb[c] for lb in labs])          # each class non-empty
        changes = []
        for i in range(n):
            a, b = labs[i], labs[(i + 1) % n]
            ch = m.NewBoolVar(f"ch|{v}|{i}"); changes.append(ch)
            for ci, c in enumerate(LABELS):
                nxt = LABELS[(ci + 1) % 4]
                m.AddBoolOr([a[c].Not(), b[c], b[nxt]])              # forward-only transitions
                m.AddBoolOr([a[c].Not(), b[c].Not(), ch.Not()])        # same label -> no change
                m.AddBoolOr([a[c].Not(), b[nxt].Not(), ch])            # next label -> change
        m.Add(sum(changes) == 4)
    fixed = {"N": "IR", "E": "IB", "S": "OR", "W": "OB"}
    for o, c in fixed.items():
        for w in G.neighbors(o):
            if w in OUTER: continue
            m.Add(lab(o, w)[c] == 1)
    return m, L, lab_edges, lab


def enumerate_rels(G, emb, cap=64, seed=0):
    for ccw in (True, False):
        m, L, lab_edges, lab = rel_model(G, emb, ccw)
        solver = cp_model.CpSolver(); solver.parameters.num_workers = 1; solver.parameters.random_seed = seed
        out = []
        while len(out) < cap:
            st = solver.Solve(m)
            if st not in (cp_model.OPTIMAL, cp_model.FEASIBLE): break
            rel = {}
            for u, v in lab_edges:
                c = next(c for c in LABELS if solver.Value(L[(u, u, v)][c]))
                # store as directed coloured edge from the perspective of u
                if c == "OB": rel[(u, v)] = "B"
                elif c == "IB": rel[(v, u)] = "B"
                elif c == "OR": rel[(u, v)] = "R"
                else: rel[(v, u)] = "R"
            out.append(rel)
            m.AddBoolOr([L[(u, u, v)][c].Not() for u, v in lab_edges for c in LABELS if solver.Value(L[(u, u, v)][c])])
        if out: return out, ccw
    return [], None


def st_faces(G, emb, rel, colour, ccw):
    """Faces (as sets of angles (v, a, b)) of the st-graph of one colour, closed by the outer 4-cycle."""
    edges = {e for e, c in rel.items() if c == colour}
    if colour == "R": edges |= {("S", "W"), ("W", "N"), ("S", "E"), ("E", "N")}
    else: edges |= {("W", "S"), ("S", "E"), ("W", "N"), ("N", "E")}
    und = {frozenset(e) for e in edges}
    rot = {}
    for v in G.nodes:
        order = list(emb.neighbors_cw_order(v))
        if ccw: order = order[::-1]                         # ccw list
        rot[v] = [w for w in order if frozenset((v, w)) in und]
    def next_ccw(w, v):
        r = rot[w]; return r[(r.index(v) + 1) % len(r)]
    angles = {(v, r[i], r[(i + 1) % len(r)]) for v, r in rot.items() for i in range(len(r))}
    faces, seen = [], set()
    for ang in angles:
        if ang in seen: continue
        f, cur = [], ang
        while cur not in seen:
            seen.add(cur); f.append(cur)
            v, a, b = cur
            cur = (b, v, next_ccw(b, v))
        faces.append(f)
    face_of = {ang: i for i, f in enumerate(faces) for ang in f}
    return faces, face_of, rot, edges


def dimension(G, emb, rel, ccw, bands, need, horizon=200_000):
    """bands[v] = ((w_lo, w_hi), (l_lo, l_hi)); need[(u,v)] = mm of shared wall. Returns boxes in mm or None."""
    inner = [v for v in G.nodes if v not in OUTER]
    Rf, Rof, Rrot, Redges = st_faces(G, emb, rel, "R", ccw)   # faces of T2 = vertical segments
    Bf, Bof, Brot, Bedges = st_faces(G, emb, rel, "B", ccw)   # faces of T1 = horizontal segments
    m = cp_model.CpModel()
    X = [m.NewIntVar(0, horizon, f"X{i}") for i in range(len(Rf))]
    Y = [m.NewIntVar(0, horizon, f"Y{i}") for i in range(len(Bf))]
    def runs(v, rot_all):
        """label of each neighbour of inner v in ccw order (full embedding)."""
        order = list(emb.neighbors_cw_order(v));
        if ccw: order = order[::-1]
        labs = []
        for w in order:
            if (v, w) in rel: labs.append(("O" + rel[(v, w)], w))
            elif (w, v) in rel: labs.append(("I" + rel[(w, v)], w))
            else: labs.append((None, w))
        return labs
    left, right, bottom, top = {}, {}, {}, {}
    for v in inner:
        labs = runs(v, None)
        def last_first(a, b):
            idx_a = [i for i, (c, _) in enumerate(labs) if c == a]; idx_b = [i for i, (c, _) in enumerate(labs) if c == b]
            # last of run a (ccw) then first of run b
            n = len(labs)
            # choose the pair (i in a, j in b) with j == i+1 modulo skipping non-red/blue labels between
            for i in idx_a:
                j = (i + 1) % n
                while labs[j][0] not in (a, b) and labs[j][0] is not None and j != i: j = (j + 1) % n
                if labs[j][0] == b: return labs[i][1], labs[j][1]
            raise RuntimeError(f"no run boundary {a}->{b} at {v}")
        u1, w1 = last_first("IR", "OR"); right[v] = Rof[(v, u1, w1)]
        u2, w2 = last_first("OR", "IR"); left[v] = Rof[(v, u2, w2)]
        u3, w3 = last_first("OB", "IB"); top[v] = Bof[(v, u3, w3)]
        u4, w4 = last_first("IB", "OB"); bottom[v] = Bof[(v, u4, w4)]
    rots = {}
    for v in inner:
        (wl, wh), (ll, lh) = bands[v]
        r = m.NewBoolVar(f"rot{v}"); rots[v] = r
        W = X[right[v]] - X[left[v]]; Lv = Y[top[v]] - Y[bottom[v]]
        m.Add(W >= wl).OnlyEnforceIf(r.Not()); m.Add(W <= wh).OnlyEnforceIf(r.Not())
        m.Add(Lv >= ll).OnlyEnforceIf(r.Not()); m.Add(Lv <= lh).OnlyEnforceIf(r.Not())
        m.Add(W >= ll).OnlyEnforceIf(r); m.Add(W <= lh).OnlyEnforceIf(r)
        m.Add(Lv >= wl).OnlyEnforceIf(r); m.Add(Lv <= wh).OnlyEnforceIf(r)
    def prev_ccw(rot, w, v): r = rot[w]; return r[(r.index(v) - 1) % len(r)]
    def next_ccw(rot, w, v): r = rot[w]; return r[(r.index(v) + 1) % len(r)]
    for (u, v), c in rel.items():
        n = need.get(frozenset((u, v)), 1)
        if c == "R":   # shared horizontal wall between u (below) and v spans from left face to right face of the edge
            fr = Rof[(u, prev_ccw(Rrot, u, v), v)]; fl = Rof[(u, v, next_ccw(Rrot, u, v))]
            m.Add(X[fr] - X[fl] >= n)
        else:
            fb = Bof[(u, prev_ccw(Brot, u, v), v)]; ft = Bof[(u, v, next_ccw(Brot, u, v))]
            m.Add(Y[ft] - Y[fb] >= n)
    # outer walls: the T2 face that is the unbounded one has angles only at N,E,S,W; the west wall face touches W and inner
    def wall(faces, of, o, other_end):
        cands = [of[a] for a in of if a[0] == o]
        outer_face = next((i for i, f in enumerate(faces) if all(a[0] in OUTER for a in f)), None)
        cands = [c for c in cands if c != outer_face]
        return cands[0]
    m.Add(X[wall(Rf, Rof, "W", None)] == 0); m.Add(Y[wall(Bf, Bof, "S", None)] == 0)
    dev = []
    for v in inner:
        (wl, wh), (ll, lh) = bands[v]; nw, nl = (wl + wh) // 2, (ll + lh) // 2
        if wh >= 100_000: continue   # void: free size, no deviation term
        W = X[right[v]] - X[left[v]]; Lv = Y[top[v]] - Y[bottom[v]]
        for expr, nom_a, nom_b in ((W, nw, nl), (Lv, nl, nw)):
            d = m.NewIntVar(0, horizon, ""); m.Add(d >= expr - nom_a).OnlyEnforceIf(rots[v].Not()); m.Add(d >= nom_a - expr).OnlyEnforceIf(rots[v].Not())
            m.Add(d >= expr - nom_b).OnlyEnforceIf(rots[v]); m.Add(d >= nom_b - expr).OnlyEnforceIf(rots[v]); dev.append(d)
    m.Minimize(10 * sum(dev) + X[wall(Rf, Rof, "E", None)] + Y[wall(Bf, Bof, "N", None)])
    s = cp_model.CpSolver(); s.parameters.num_workers = 4; s.parameters.max_time_in_seconds = 5
    st = s.Solve(m)
    dimension.last_status = s.StatusName(st)
    if st not in (cp_model.OPTIMAL, cp_model.FEASIBLE): return None
    return {v: (s.Value(X[left[v]]), s.Value(Y[bottom[v]]), s.Value(X[right[v]]) - s.Value(X[left[v]]), s.Value(Y[top[v]]) - s.Value(Y[bottom[v]])) for v in inner}


def run_brief(path, cap=64, seed=0, height_mm=3000, verify_n=8):
    from spacetope.brief import load
    from spacetope.circulation import prepare
    from spacetope.doors import required_overlap_mm
    from spacetope.solve.grid import Box
    brief, _ = prepare(load(path))
    G = nx.Graph(); G.add_nodes_from(s.name for s in brief.spaces); G.add_edges_from(brief.contacts)
    t0 = time.perf_counter()
    tried = 0
    for s_ in range(seed, seed + 200):        # embeddings depend on insertion order: reshuffle until wish triangles are faces
        tried += 1
        try:
            Gp, emb, outer, added, arcs, sep, voids = make_ptp(G, s_, through={s.name for s in brief.spaces if s.program == 'corridor'})
        except (RuntimeError, AssertionError, StopIteration) as ex:
            sep = [("insertion_failed", str(ex)[:60])]; continue
        if not sep: break
    else:
        return {"brief": brief.name, "error": f"no clean triangulation in {tried} embeddings; last: {sep}", "rels": 0, "dimensioned": 0,
                "t_enumerate": 0, "t_dimension": 0, "separating_triangles": sep, "ccw": None, "added_edges": [], "verified": [], "results": [],
                "voids": [], "embeddings_tried": tried, "wish_edges": [list(e) for e in brief.contacts], "outer_cycle": [], "arcs": {},
                "spaces": [{"name": s.name, "w": s.w, "l": s.l, "program": s.program} for s in brief.spaces]}
    rels, ccw = enumerate_rels(Gp, emb, cap, seed)
    t1 = time.perf_counter()
    bands = {s.name: (s.band("w"), s.band("l")) for s in brief.spaces}
    for v in voids: bands[v] = ((1, 100_000), (1, 100_000))
    need = {}
    for a, b in Gp.edges():
        if a in OUTER or b in OUTER: continue
        need[frozenset((a, b))] = 1 if (a in voids or b in voids) else required_overlap_mm(brief, a, b)
    results = []
    for rel in rels:
        boxes = dimension(Gp, emb, rel, ccw, bands, need)
        results.append({"labelling": {f"{u}>{v}": c for (u, v), c in rel.items()},
                        "boxes": boxes and {v: [x / 1000, y / 1000, w / 1000, l / 1000] for v, (x, y, w, l) in boxes.items() if v not in voids},
                        "voids": boxes and {v: [x / 1000, y / 1000, w / 1000, l / 1000] for v, (x, y, w, l) in boxes.items() if v in voids}})
    t2 = time.perf_counter()
    verified = None
    if verify_n:
        from spacetope.verify import verify
        verified = []
        for r in [r for r in results if r["boxes"]][:verify_n]:
            pl = {v: Box(int(x * 1000), int(y * 1000), 0, int(w * 1000), int(l * 1000), height_mm) for v, (x, y, w, l) in r["boxes"].items()}
            rep = verify(brief, pl)
            verified.append({"ok": rep.ok, "checks": {k: v["passed"] for k, v in rep.to_dict()["checks"].items()}})
            r["verified"] = rep.ok
    return {"brief": brief.name, "wish_edges": [list(e) for e in brief.contacts], "added_edges": [list(e) for e in added],
            "outer_cycle": outer, "arcs": arcs, "separating_triangles": sep, "ccw": ccw, "voids": voids, "embeddings_tried": tried,
            "rels": len(rels), "dimensioned": sum(1 for r in results if r["boxes"]), "t_enumerate": round(t1 - t0, 3),
            "t_dimension": round(t2 - t1, 3), "verified": verified, "results": results,
            "spaces": [{"name": s.name, "w": s.w, "l": s.l, "program": s.program} for s in brief.spaces]}


if __name__ == "__main__":
    out = {}
    for path in sys.argv[1:]:
        r = run_brief(path)
        out[r["brief"]] = r
        print(json.dumps({k: r[k] for k in ("brief", "rels", "dimensioned", "t_enumerate", "t_dimension", "separating_triangles", "ccw")}
                         | {"added": len(r["added_edges"]), "verified": [v["ok"] for v in (r["verified"] or [])]}), flush=True)
    json.dump(out, open("dual_results.json", "w"))
