"""Exact engine: CP-SAT relational model (Wu et al. 2018 style) on the integer-mm grid.

Variables per space: x, y, w, l (bands, optional 90-degree rotation); z fixed by level assignment.
Constraints: AddNoOverlap2D per level; for every required pair on one level, a Boolean per side
'touch[a,b,side]' implying plane equality and door-width overlap, with at least one side true;
every room reaches a circulation space by a door; core stacks share their footprint across levels;
envelope bounds; symmetry breaking for identical spaces.
Objective: fractional dimensional deviation + bounding-box half-perimeter.
K distinct options by re-solving with a blocking clause on the required-touch assignment.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field

from ortools.sat.python import cp_model

from .. import affinity as _aff
from ..brief import Brief, Space
from ..doors import required_overlap_mm
from ..levels import assign_levels, core_stacks, envelope_mm, level_height_mm
from ..placement import assembly_from_placement
from ..units import to_mm
from .grid import Box

HSIDES = ("+x", "-x", "+y", "-y")


@dataclass
class CpsatParams:
    k: int = 8
    door_mm: int = 900
    time_limit: float = 60.0        # total budget across the K solves
    per_solve_min: float = 3.0
    per_solve_max: float = 60.0     # CP-SAT rarely proves optimality on 30+ rooms; stop improving after this
    workers: int = 8
    w_dev: int = 1                  # per (fractional deviation * 1e6)
    w_perim: int = 20               # per mm of W + L
    rotate: bool = True
    symmetry_breaking: bool = True
    frontage_cut: bool = True       # redundant cut: rooms on one corridor side must fit along it (PLAN M10)
    w_stack: int = 3000             # reward per wall plane of level k that lands on a plane of level k-1 (PLAN M11)
    stack_pairs_max: int = 200      # skip the stacking term when a level pair would need more pair literals than this
    w_affinity: int = 80_000        # objective units per unit of soft-affinity weight (PLAN M20); 0 drops the soft terms
    # Literal budget for the affinity block. Hard (must/never) entries are always built; a soft entry is built only while
    # the running count of Boolean literals plus its estimated cost stays under this. school_three_levels (9 hard apart
    # pairs, 12 wet rooms with cluster/stack rules) builds 187 affinity literals, so 1 500 leaves about 8x headroom.
    affinity_literals_max: int = 1500


@dataclass
class CpsatResult:
    status: str
    placements: list[dict[str, Box]] = field(default_factory=list)
    seconds: float = 0.0
    statuses: list[str] = field(default_factory=list)


class _Vars:
    def __init__(self, m: cp_model.CpModel, s: Space, z: int, H: int, horizon: int, rotate: bool):
        n = s.name
        self.z, self.h = z, H
        bw, bl = s.band("w"), s.band("l")
        lo = min(bw[0], bl[0]); hi = max(bw[1], bl[1])
        self.x = m.NewIntVar(0, horizon, f"x_{n}"); self.y = m.NewIntVar(0, horizon, f"y_{n}")
        self.w = m.NewIntVar(lo, hi, f"w_{n}"); self.l = m.NewIntVar(lo, hi, f"l_{n}")
        self.x1 = m.NewIntVar(0, 2 * horizon, f"x1_{n}"); self.y1 = m.NewIntVar(0, 2 * horizon, f"y1_{n}")
        m.Add(self.x1 == self.x + self.w); m.Add(self.y1 == self.y + self.l)
        self.rot = m.NewBoolVar(f"rot_{n}")
        if not rotate or s.w == s.l:
            m.Add(self.rot == 0)
        for var, band_plain, band_rot in ((self.w, bw, bl), (self.l, bl, bw)):
            m.Add(var >= band_plain[0]).OnlyEnforceIf(self.rot.Not()); m.Add(var <= band_plain[1]).OnlyEnforceIf(self.rot.Not())
            m.Add(var >= band_rot[0]).OnlyEnforceIf(self.rot); m.Add(var <= band_rot[1]).OnlyEnforceIf(self.rot)
        self.ix = m.NewIntervalVar(self.x, self.w, self.x1, f"ix_{n}")
        self.iy = m.NewIntervalVar(self.y, self.l, self.y1, f"iy_{n}")
        # fractional deviation terms (scaled by 1e6 / nominal)
        self.dev_terms = []
        # one deviation variable per orientation, so a rotated room is weighted by the nominal it is
        # actually compared against (review 2026-09-13)
        for var, nom_plain, nom_rot in ((self.w, s.nominal_mm("w"), s.nominal_mm("l")), (self.l, s.nominal_mm("l"), s.nominal_mm("w"))):
            dp = m.NewIntVar(0, horizon, f"devp_{n}_{var.Name()}")
            m.Add(dp >= var - nom_plain).OnlyEnforceIf(self.rot.Not()); m.Add(dp >= nom_plain - var).OnlyEnforceIf(self.rot.Not())
            m.Add(dp == 0).OnlyEnforceIf(self.rot)
            dr = m.NewIntVar(0, horizon, f"devr_{n}_{var.Name()}")
            m.Add(dr >= var - nom_rot).OnlyEnforceIf(self.rot); m.Add(dr >= nom_rot - var).OnlyEnforceIf(self.rot)
            m.Add(dr == 0).OnlyEnforceIf(self.rot.Not())
            self.dev_terms.append(dp * (1_000_000 // nom_plain) + dr * (1_000_000 // nom_rot))


class _StopAtFirst(cp_model.CpSolverSolutionCallback):
    def on_solution_callback(self) -> None:
        self.StopSearch()


def _touch_literal(m: cp_model.CpModel, a: _Vars, b: _Vars, side: str, need: int, name: str):
    lit = m.NewBoolVar(name)
    if side == "+x": m.Add(a.x1 == b.x).OnlyEnforceIf(lit)
    if side == "-x": m.Add(b.x1 == a.x).OnlyEnforceIf(lit)
    if side == "+y": m.Add(a.y1 == b.y).OnlyEnforceIf(lit)
    if side == "-y": m.Add(b.y1 == a.y).OnlyEnforceIf(lit)
    # overlap = min(a1, b1) - max(a0, b0) >= need needs all four pairings, including each box's own
    # length along the wall (review 2026-09-13, #6: a rotated 1 m room passed with two terms)
    if side in ("+x", "-x"):
        for lhs in (a.y1 - b.y, b.y1 - a.y, a.l, b.l):
            m.Add(lhs >= need).OnlyEnforceIf(lit)
    else:
        for lhs in (a.x1 - b.x, b.x1 - a.x, a.w, b.w):
            m.Add(lhs >= need).OnlyEnforceIf(lit)
    return lit


_OPP = {"+x": "-x", "-x": "+x", "+y": "-y", "-y": "+y"}


class _AffinityBlock:
    """PLAN M20: the affinity entries of `affinity.expand(brief)` as constraints and rewarded Booleans.

    Every predicate is built so that its literal implies the predicate that `affinity.measure` judges (sufficient,
    never weaker): positive predicates return a list of literals of which one must hold; negative ones return one
    literal that implies the predicate's negation. Literals are cached by space pair, so tag rules that expand to both
    (a, b) and (b, a) do not double the model."""

    def __init__(self, m, V, span, p: CpsatParams, big: int):
        self.m, self.V, self.span, self.p, self.big = m, V, span, p, big
        self.count = 0
        self.cache: dict = {}
        self.terms: list = []          # (hit literal, integer reward)
        self.skipped: list = []

    # ---- helpers
    def new(self, name: str):
        self.count += 1
        return self.m.NewBoolVar(name)

    def mode(self, a: str, b: str):
        (a0, a1), (b0, b1) = self.span(a), self.span(b)
        if a0 <= b1 and b0 <= a1:
            return "same"
        if a1 + 1 == b0 or b1 + 1 == a0:
            return "adj"
        return None

    def memo(self, key, build):
        if key not in self.cache:
            self.cache[key] = build()
        return self.cache[key]

    # ---- touch: a shared vertical wall of at least `need` mm
    def touch_lits(self, a: str, b: str, need: int) -> list:
        out = []
        for side in HSIDES:
            key = ("t", a, b, side, need); mirror = ("t", b, a, _OPP[side], need)
            if key not in self.cache and mirror in self.cache:
                self.cache[key] = self.cache[mirror]
            if key not in self.cache:
                self.count += 1
                self.cache[key] = _touch_literal(self.m, self.V[a], self.V[b], side, need, f"af_t_{a}_{b}_{side}_{need}")
                nw = self.cache.get(("nw", frozenset((a, b)), need))
                if nw is not None:                      # the two polarities on one pair exclude each other outright
                    self.m.AddBoolOr([nw.Not(), self.cache[key].Not()])
            out.append(self.cache[key])
        return out

    def no_wall(self, a: str, b: str, need: int):
        """q implies: a and b share no vertical wall of length >= need. Exact (not just sufficient) for a pair whose
        spans overlap: on each side either the planes differ (strictly less / strictly greater) or the overlap along
        the wall, min of the four pairings as in _touch_literal, is at most need-1."""
        key = ("nw", frozenset((a, b)), need)
        if key in self.cache:
            return self.cache[key]
        m, A, B = self.m, self.V[a], self.V[b]
        q = self.new(f"af_nw_{a}_{b}_{need}")
        ovy = m.NewIntVar(-self.big, self.big, f"af_ovy_{a}_{b}_{need}")
        ovx = m.NewIntVar(-self.big, self.big, f"af_ovx_{a}_{b}_{need}")
        m.AddMinEquality(ovy, [A.y1 - B.y, B.y1 - A.y, A.l, B.l])
        m.AddMinEquality(ovx, [A.x1 - B.x, B.x1 - A.x, A.w, B.w])
        for side in HSIDES:
            pa, pb = {"+x": (A.x1, B.x), "-x": (B.x1, A.x), "+y": (A.y1, B.y), "-y": (B.y1, A.y)}[side]
            ov = ovy if side in ("+x", "-x") else ovx
            lt, gt, short = (self.new(f"af_nw_{a}_{b}_{side}_{k}") for k in ("lt", "gt", "sh"))
            m.Add(pa + 1 <= pb).OnlyEnforceIf(lt); m.Add(pa >= pb + 1).OnlyEnforceIf(gt)
            m.Add(ov <= need - 1).OnlyEnforceIf(short)
            m.AddBoolOr([lt, gt, short]).OnlyEnforceIf(q)
        self.cache[key] = q
        for side in HSIDES:                              # literal => touching, so q and a touch literal exclude each other;
            for k2 in (("t", a, b, side, need), ("t", b, a, _OPP[side], need)):   # stated so that propagation sees it
                if k2 in self.cache:
                    m.AddBoolOr([q.Not(), self.cache[k2].Not()])
        return q

    # ---- apart: no shared wall, floor or ceiling area
    def apart_lits(self, a: str, b: str):
        """Literals of which one implies `apart`, or True when the spans are more than a level apart (always apart)."""
        key = ("ap", frozenset((a, b)))
        if key in self.cache:
            return self.cache[key]
        mode = self.mode(a, b)
        if mode is None:
            out = True
        else:
            m, A, B = self.m, self.V[a], self.V[b]
            # non-strict separation in one of four directions
            ns = {}
            for d, (lo, hi) in {"xp": (A.x1, B.x), "xm": (B.x1, A.x), "yp": (A.y1, B.y), "ym": (B.y1, A.y)}.items():
                ns[d] = self.new(f"af_ns_{a}_{b}_{d}")
                m.Add(lo <= hi).OnlyEnforceIf(ns[d])
            if mode == "adj":
                # floor/ceiling contact needs positive overlap on both axes, so one non-strict separation is exact
                out = list(ns.values())
            else:
                # same level: strict separation on one axis, or non-strict on both (corner contact has zero area).
                # Exact: interiors are disjoint, so x-overlap <= 0 or y-overlap <= 0; if x touches (gap 0) the y
                # intervals must also be non-strictly separated, else the shared wall has positive length.
                out = []
                for d, (lo, hi) in {"xp": (A.x1, B.x), "xm": (B.x1, A.x), "yp": (A.y1, B.y), "ym": (B.y1, A.y)}.items():
                    st = self.new(f"af_st_{a}_{b}_{d}")
                    m.Add(lo + 1 <= hi).OnlyEnforceIf(st)
                    out.append(st)
                cr = self.new(f"af_cr_{a}_{b}")
                m.AddBoolOr([ns["xp"], ns["xm"]]).OnlyEnforceIf(cr)
                m.AddBoolOr([ns["yp"], ns["ym"]]).OnlyEnforceIf(cr)
                out.append(cr)
        self.cache[key] = out
        return out

    def contact(self, a: str, b: str):
        """c implies some face contact of positive area (negation of apart); None when impossible (> 1 level apart).
        Sufficient only: same-level contact is a vertical wall (floor/ceiling contact cannot occur between overlapping
        spans), adjacent-level contact is a positive plan overlap."""
        key = ("ct", frozenset((a, b)))
        if key in self.cache:
            return self.cache[key]
        mode = self.mode(a, b)
        if mode is None:
            c = None
        else:
            m, A, B = self.m, self.V[a], self.V[b]
            c = self.new(f"af_ct_{a}_{b}")
            if mode == "same":
                m.AddBoolOr(self.touch_lits(a, b, 1)).OnlyEnforceIf(c)
            else:
                for lhs in (A.x1 - B.x, B.x1 - A.x, A.y1 - B.y, B.y1 - A.y):
                    m.Add(lhs >= 1).OnlyEnforceIf(c)
        self.cache[key] = c
        return c

    # ---- stack: adjacent levels, plan overlap >= overlap x the smaller footprint
    def stack_lits(self, a: str, b: str, overlap: float) -> list:
        """Two anchor literals; anchor X implies overlap_x >= c*X.w and overlap_y >= c*X.l with c = ceil(1000*sqrt(overlap))/1000.
        Then overlap area >= c^2 * area(X) >= overlap * area(X) >= overlap * min(area(a), area(b)), which is measure's
        predicate, whichever room is the smaller. The overlap is min(a1,b1)-max(a0,b0), so all four pairings are
        bounded (the X.w one is trivially true as c <= 1). Sufficient, not necessary: the true smaller room need not be
        the anchor, hence two anchors (ov = 1 needs the smaller room contained in the larger)."""
        cm = math.ceil(math.sqrt(overlap) * 1000)
        key = ("sk", frozenset((a, b)), cm)
        if key in self.cache:
            return self.cache[key]
        m, A, B = self.m, self.V[a], self.V[b]
        out = []
        for (xn, X), (yn, Y) in (((a, A), (b, B)), ((b, B), (a, A))):
            lit = self.new(f"af_sk_{a}_{b}_{xn}")
            for lhs, ext in ((A.x1 - B.x, X.w), (B.x1 - A.x, X.w), (Y.w, X.w), (A.y1 - B.y, X.l), (B.y1 - A.y, X.l), (Y.l, X.l)):
                m.Add(1000 * lhs >= cm * ext).OnlyEnforceIf(lit)
            out.append(lit)
        self.cache[key] = out
        return out

    def no_overlap_adj(self, a: str, b: str):
        """q implies the adjacent-level pair has no plan overlap (stronger than 'share < overlap', so sound)."""
        key = ("na", frozenset((a, b)))
        if key not in self.cache:
            lits = self.apart_lits(a, b)
            q = self.new(f"af_na_{a}_{b}")
            self.m.AddBoolOr(lits).OnlyEnforceIf(q)
            self.cache[key] = q
        return self.cache[key]

    # ---- one entry
    def add(self, af, hard: bool):
        a, V = af.a, self.V
        partners = [o for o in af.others if o in V and o != a]
        if a not in V or (af.kind in _aff.PAIR_KINDS and not partners):
            return
        m = self.m
        neg = af.strength in _aff.NEGATIVE
        kind, par = af.kind, af.params
        # per-partner: the sufficient condition for the predicate (positive) or its negation (negative);
        # "pos": list of literals of which one must hold (OR over partners), "neg": literals that must all hold
        pos: list = []; negs: list = []; always = False; impossible = False
        if kind == "touch":
            need = max(1, to_mm(par["min"]))
            ps = [o for o in partners if self.mode(a, o) == "same"]
            if neg:
                negs = [self.no_wall(a, o, need) for o in ps]
            else:
                pos = [l for o in ps for l in self.touch_lits(a, o, need)]
        elif kind == "stack":
            ps = [o for o in partners if self.mode(a, o) == "adj"]
            if neg:
                negs = [self.no_overlap_adj(a, o) for o in ps]
            else:
                pos = [l for o in ps for l in self.stack_lits(a, o, par["overlap"])]
        elif kind == "apart":
            if neg:                                   # wants face contact with every partner
                cs = [self.contact(a, o) for o in partners]
                if any(c is None for c in cs):
                    impossible = True
                negs = [c for c in cs if c is not None]
            else:
                for o in partners:
                    lits = self.apart_lits(a, o)
                    if lits is True:
                        always = True
                    else:
                        pos.extend(lits)
        else:
            return
        if not neg and not always and not pos and not impossible:
            impossible = True                         # nothing can meet it (e.g. a touch across levels)
        if hard:
            if impossible or (not neg and not always and not pos):
                m.Add(False)
            elif neg:
                for q in negs:
                    m.AddBoolOr([q])
            elif not always:
                m.AddBoolOr(pos)
            return
        if impossible or (not neg and always):
            return                                    # unreachable, or met for free: nothing to reward
        if not negs and neg:
            return                                    # met for free
        hit = self.new(f"af_hit_{af.source}_{af.a}")
        if neg:
            for q in negs:
                m.AddImplication(hit, q)
        else:
            m.AddBoolOr(pos + [hit.Not()])
        self.terms.append((hit, int(round(self.p.w_affinity * af.weight))))

    def cost(self, af) -> int:
        n = max(1, len(af.others))
        per = {"touch": 14 if af.strength in _aff.NEGATIVE else 5, "apart": 10, "stack": 5}.get(af.kind, 0)
        return per * n + 1

    def build(self, affs):
        for af in affs:
            if af.strength in _aff.HARD:
                self.add(af, True)
        if self.p.w_affinity > 0:
            for af in affs:
                if af.strength in _aff.HARD or af.kind not in ("touch", "apart", "stack"):
                    continue
                if self.count + self.cost(af) > self.p.affinity_literals_max:
                    self.skipped.append(af)
                    continue
                self.add(af, False)


def solve_cpsat(brief: Brief, params: CpsatParams | None = None, seed: int = 0,
                hint: dict[str, Box] | None = None) -> CpsatResult:
    """`hint`: a feasible placement (e.g. from the beam) used as a CP-SAT solution hint (warm start)."""
    p = params or CpsatParams()
    t_start = time.perf_counter()
    levels = assign_levels(brief, seed)
    H = level_height_mm(brief)
    env = envelope_mm(brief)
    n_levels = brief.levels or 1
    total_w = sum(max(s.band("w")[1], s.band("l")[1]) for s in brief.spaces)
    horizon = min(env["w"], total_w) if env else total_w
    horizon_l = min(env["l"], total_w) if env else total_w

    def span(name: str) -> tuple[int, int]:
        """Levels a space occupies: one level for floor-bound spaces, the served range for shafts (M7)."""
        sp = brief.space(name)
        return sp.serves if sp.is_shaft else (levels[name], levels[name])

    def can_touch(a: str, b: str) -> bool:
        (a0, a1), (b0, b1) = span(a), span(b)
        return a0 <= b1 and b0 <= a1

    def on_level(name: str, k: int) -> bool:
        lo, hi = span(name)
        return lo <= k <= hi

    m = cp_model.CpModel()
    V: dict[str, _Vars] = {}
    for s in brief.spaces:
        lo, hi = span(s.name)
        V[s.name] = _Vars(m, s, lo * H, (hi - lo + 1) * H, max(horizon, horizon_l), p.rotate)
        if env:
            m.Add(V[s.name].x1 <= env["w"]); m.Add(V[s.name].y1 <= env["l"])
    # non-overlap per level
    for k in range(n_levels):
        names = [s.name for s in brief.spaces if on_level(s.name, k)]  # a shaft's intervals join every level it serves
        if len(names) > 1:
            m.AddNoOverlap2D([V[n].ix for n in names], [V[n].iy for n in names])
    # core stacks: same footprint across levels
    for stack in core_stacks(brief, levels):
        for a, b in zip(stack, stack[1:]):
            m.Add(V[a].x == V[b].x); m.Add(V[a].y == V[b].y); m.Add(V[a].w == V[b].w); m.Add(V[a].l == V[b].l)
    # required contacts on one level: at least one side literal
    required_lits: list = []
    lits_by_pair: dict[frozenset, list] = {}
    for a, b in brief.contacts:
        if not can_touch(a, b):
            continue  # legacy vertical pairs are handled by stacks
        need = required_overlap_mm(brief, a, b, p.door_mm)
        lits = [_touch_literal(m, V[a], V[b], side, need, f"t_{a}_{b}_{side}") for side in HSIDES]
        m.AddBoolOr(lits)
        m.Add(sum(lits) <= 1)
        required_lits.extend(lits)
        lits_by_pair[frozenset((a, b))] = lits
    # access: every room reaches some circulation space on its level through a door
    # circulation briefs: a room's door opens onto a corridor (rule D8); legacy briefs: any circulation space
    circ = [s for s in brief.spaces if (s.program == "corridor" if brief.circulation else s.is_circulation)]
    if circ:
        for r in brief.spaces:
            if r.program != "room":
                continue
            opts = []
            for c in circ:
                if not can_touch(c.name, r.name):
                    continue
                key = frozenset((r.name, c.name))
                if key in lits_by_pair:
                    opts.extend(lits_by_pair[key])
                else:
                    need = required_overlap_mm(brief, r.name, c.name, p.door_mm)
                    opts.extend(_touch_literal(m, V[r.name], V[c.name], side, need, f"acc_{r.name}_{c.name}_{side}") for side in HSIDES)
            if opts:
                m.AddBoolOr(opts)
    # a shaft reaches a corridor on every level it serves. With one corridor per level expansion makes this a
    # required contact; on a chained spine it is a choice of segment, so it is stated here (PLAN M15b).
    for s in brief.spaces:
        if not s.is_shaft:
            continue
        for k in range(s.serves[0], s.serves[1] + 1):
            opts = []
            for c in brief.spaces:
                if c.program != "corridor" or not on_level(c.name, k) or not can_touch(c.name, s.name):
                    continue
                key = frozenset((s.name, c.name))
                if key in lits_by_pair:
                    opts.extend(lits_by_pair[key])
                else:
                    need = required_overlap_mm(brief, s.name, c.name, p.door_mm)
                    opts.extend(_touch_literal(m, V[s.name], V[c.name], side, need, f"sh_{s.name}_{c.name}_{k}_{side}") for side in HSIDES)
            if opts:
                m.AddBoolOr(opts)
    # PLAN M10, redundant frontage cut. Spaces touching one side of a corridor do not overlap each other and each
    # overlaps the corridor's extent, so all but the two outermost lie inside it: the sum of their smallest widths
    # is at most the corridor's length on that side plus the two largest possible overhangs.
    if p.frontage_cut:
        OPP = {"+x": "-x", "-x": "+x", "+y": "-y", "-y": "+y"}
        per_side: dict[tuple[str, str], list] = {}
        for a, b in brief.contacts:
            key = frozenset((a, b))
            if key not in lits_by_pair or len(lits_by_pair[key]) != 4:
                continue
            for c, other, flip in ((a, b, False), (b, a, True)):
                if brief.space(c).program != "corridor":
                    continue
                so = brief.space(other)
                lo_w = min(so.band("w")[0], so.band("l")[0]); hi_w = max(so.band("w")[1], so.band("l")[1])
                need = required_overlap_mm(brief, a, b, p.door_mm)
                for side, lit in zip(HSIDES, lits_by_pair[key]):      # literals are from a's point of view
                    c_side = OPP[side] if flip else side
                    per_side.setdefault((c, c_side), []).append((lit, lo_w, max(0, hi_w - need)))
        for (c, c_side), terms in per_side.items():
            if len(terms) < 3:
                continue
            over = sorted((o for _, _, o in terms), reverse=True)[:2]
            length = V[c].l if c_side in ("+x", "-x") else V[c].w
            m.Add(sum(lit * lo_w for lit, lo_w, _ in terms) <= length + sum(over))
    # symmetry breaking among identical spaces
    if p.symmetry_breaking:
        groups: dict[tuple, list[str]] = {}
        partners = {s.name: tuple(sorted(b if a == s.name else a for a, b in brief.contacts if s.name in (a, b))) for s in brief.spaces}
        for s in brief.spaces:
            if s.wishes.get("level") is not None:
                continue
            key = (s.program, s.w, s.l, s.h, span(s.name), partners[s.name], tuple(sorted(s.wishes.items())))
            groups.setdefault(key, []).append(s.name)
        for names in groups.values():
            for a, b in zip(names, names[1:]):
                m.Add(V[a].x <= V[b].x)
    # PLAN M20: affinities, driven only by affinity.expand (never by tags). Absent, nothing below runs.
    aff_terms: list = []
    affs = [af for af in _aff.expand(brief) if af.kind in ("touch", "apart", "stack")]
    if affs:
        block = _AffinityBlock(m, V, span, p, 4 * max(horizon, horizon_l) + 4 * H)
        block.build(affs)
        aff_terms = block.terms
    # objective
    W = m.NewIntVar(0, 2 * max(horizon, horizon_l), "W"); L = m.NewIntVar(0, 2 * max(horizon, horizon_l), "L")
    for v in V.values():
        m.Add(W >= v.x1); m.Add(L >= v.y1)
    dev_terms = [t for v in V.values() for t in v.dev_terms]
    # PLAN M11: cross-level alignment as a soft term. A wall plane of a space on level k "hits" when it equals a wall
    # plane of some space present on level k-1 (shafts count on every level they cover), which is how
    # score.stacking reads a placement. One literal per (plane, plane below) implies the equality; one hit literal
    # per plane is rewarded. Shafts already share their planes across levels and need no literals of their own.
    stack_hits: list = []
    stack_eq: list = []            # (literal, var_upper, var_lower) for hinting
    if p.w_stack > 0 and n_levels > 1:
        for k in range(1, n_levels):
            upper = [s.name for s in brief.spaces if not s.is_shaft and levels.get(s.name) == k]
            lower = [s.name for s in brief.spaces if on_level(s.name, k - 1)]
            if not upper or not lower or len(upper) * len(lower) > p.stack_pairs_max:
                continue
            for r in upper:
                for axis, ends in (("x", (V[r].x, V[r].x1)), ("y", (V[r].y, V[r].y1))):
                    for e_i, end in enumerate(ends):
                        eqs = []
                        for q in lower:
                            for q_end in ((V[q].x, V[q].x1) if axis == "x" else (V[q].y, V[q].y1)):
                                lit = m.NewBoolVar(f"st_{r}_{axis}{e_i}_{q}_{q_end.Name()}")
                                m.Add(end == q_end).OnlyEnforceIf(lit)
                                eqs.append(lit); stack_eq.append((lit, end, q_end))
                        hit = m.NewBoolVar(f"hit_{r}_{axis}{e_i}")
                        m.AddBoolOr(eqs + [hit.Not()])      # hit -> some equality holds
                        stack_hits.append(hit)
    obj = p.w_dev * sum(dev_terms) + p.w_perim * (W + L) - p.w_stack * sum(stack_hits)
    if aff_terms:
        obj = obj - sum(c * h for h, c in aff_terms)
    m.Minimize(obj)

    if hint:
        for n, b in hint.items():
            if n not in V:
                continue
            sp = brief.space(n)
            rot = int((b.w, b.l) == (sp.nominal_mm("l"), sp.nominal_mm("w")) and sp.w != sp.l)
            m.AddHint(V[n].x, b.x); m.AddHint(V[n].y, b.y); m.AddHint(V[n].w, b.w); m.AddHint(V[n].l, b.l)
            m.AddHint(V[n].rot, rot)
        if stack_eq:                                   # the beam's aligned planes become hinted equalities
            val = {}
            for n, b in hint.items():
                if n in V:
                    val[V[n].x.Name()] = b.x; val[V[n].x1.Name()] = b.x1; val[V[n].y.Name()] = b.y; val[V[n].y1.Name()] = b.y1
            for lit, up, lo in stack_eq:
                if up.Name() in val and lo.Name() in val:
                    m.AddHint(lit, int(val[up.Name()] == val[lo.Name()]))
    placements: list[dict[str, Box]] = []
    statuses: list[str] = []
    seen: set = set()
    status_name = "UNKNOWN"
    for i in range(p.k):
        remaining = p.time_limit - (time.perf_counter() - t_start)
        if remaining <= 0:
            break
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = min(p.per_solve_max, max(p.per_solve_min, remaining / max(1, p.k - i)))
        solver.parameters.num_workers = p.workers
        solver.parameters.random_seed = seed + i
        st = solver.Solve(m)
        status_name = solver.StatusName(st)
        if st == cp_model.UNKNOWN and not placements:
            # PLAN M10: no option yet and this share ran out. Splitting the budget k ways must not cost the first
            # option: spend what is left on finding one, and stop at the first solution so later solves keep time.
            remaining = p.time_limit - (time.perf_counter() - t_start)
            if remaining > p.per_solve_min:
                solver = cp_model.CpSolver()
                solver.parameters.max_time_in_seconds = remaining
                solver.parameters.num_workers = p.workers
                solver.parameters.random_seed = seed + i
                st = solver.Solve(m, _StopAtFirst())
                status_name = solver.StatusName(st)
        statuses.append(status_name)
        if st not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            break
        pl = {n: Box(solver.Value(v.x), solver.Value(v.y), v.z, solver.Value(v.w), solver.Value(v.l), v.h) for n, v in V.items()}
        sig = assembly_from_placement(brief, pl).signature()
        if sig not in seen:
            seen.add(sig)
            placements.append(pl)
        if not required_lits:
            break
        m.AddBoolOr([lit.Not() if solver.Value(lit) else lit for lit in required_lits])
    final = "INFEASIBLE" if statuses and statuses[0] == "INFEASIBLE" else ("OK" if placements else status_name)
    return CpsatResult(final, placements, time.perf_counter() - t_start, statuses)


def cpsat_generator(brief: Brief, params: dict | None = None, seed: int = 0) -> list[dict[str, Box]]:
    """CP-SAT warm-started with the best beam placement (survey: CDCL/heuristic -> CP-SAT warm start)."""
    params = dict(params or {})
    warm = params.pop("warm_start", True)
    hint = None
    cp = CpsatParams(**params)
    if warm:
        t0 = time.perf_counter()
        from .beam import BeamParams, beam_search
        from .multilevel import beam_multilevel
        bp = BeamParams(k=1, beam_width=8)
        seeds = beam_multilevel(brief, bp, seed) if ((brief.levels or 1) > 1 or brief.envelope) else beam_search(brief, bp, seed)
        hint = seeds[0] if seeds else None
        cp.time_limit = max(p_min := cp.per_solve_min, cp.time_limit - (time.perf_counter() - t0) - 1.0)  # warm start counts
    return solve_cpsat(brief, cp, seed, hint=hint).placements
