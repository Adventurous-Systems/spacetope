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

import time
from dataclasses import dataclass, field

from ortools.sat.python import cp_model

from ..brief import Brief, Space
from ..doors import required_overlap_mm
from ..levels import assign_levels, core_stacks, envelope_mm, level_height_mm
from ..placement import assembly_from_placement
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
    m.Minimize(p.w_dev * sum(dev_terms) + p.w_perim * (W + L) - p.w_stack * sum(stack_hits))

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
