"""Z3 cross-check of the relational model (PLAN M13, design note C). Development tool, not part of the package.

A second encoding of "which wall of a touches which wall of b", written from the model's definition rather than
from spacetope/solve/cpsat.py, used to confirm INFEASIBLE verdicts and to count the distinct required-touch
assignments of tiny briefs. The 2026-09-13 review found an overlap literal in the CP-SAT model that summed two of
four terms; an independent encoding is the cheapest guard against that class of bug.

Single level, no circulation rules: spaces are boxes on one plane with sizes in their tolerance bands (either
orientation), no two overlap, and every required pair shares a wall on exactly one side with at least `need` mm
of overlap. An assignment is the side chosen for every required pair.
"""
from __future__ import annotations

import z3

from spacetope.brief import Brief
from spacetope.doors import required_overlap_mm

SIDES = ("+x", "-x", "+y", "-y")


def model(brief: Brief, door_mm: int = 900):
    s = z3.Solver()
    horizon = sum(max(sp.band("w")[1], sp.band("l")[1]) for sp in brief.spaces)
    V = {}
    for sp in brief.spaces:
        n = sp.name
        x, y, w, l = z3.Int(f"x_{n}"), z3.Int(f"y_{n}"), z3.Int(f"w_{n}"), z3.Int(f"l_{n}")
        (wl, wh), (ll, lh) = sp.band("w"), sp.band("l")
        plain = z3.And(w >= wl, w <= wh, l >= ll, l <= lh)
        turned = z3.And(w >= ll, w <= lh, l >= wl, l <= wh)
        s.add(z3.Or(plain, turned), x >= 0, y >= 0, x + w <= 2 * horizon, y + l <= 2 * horizon)
        V[n] = (x, y, w, l)
    names = list(V)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            ax, ay, aw, al = V[a]; bx, by, bw, bl = V[b]
            s.add(z3.Or(ax + aw <= bx, bx + bw <= ax, ay + al <= by, by + bl <= ay))
    side_vars = {}
    for a, b in brief.contacts:
        need = required_overlap_mm(brief, a, b, door_mm)
        ax, ay, aw, al = V[a]; bx, by, bw, bl = V[b]
        lits = []
        for side in SIDES:
            t = z3.Bool(f"t_{a}_{b}_{side}")
            if side == "+x":
                plane = ax + aw == bx
            elif side == "-x":
                plane = bx + bw == ax
            elif side == "+y":
                plane = ay + al == by
            else:
                plane = by + bl == ay
            if side in ("+x", "-x"):   # overlap along y = min(a1, b1) - max(a0, b0)
                lo = z3.If(ay >= by, ay, by); hi = z3.If(ay + al <= by + bl, ay + al, by + bl)
            else:
                lo = z3.If(ax >= bx, ax, bx); hi = z3.If(ax + aw <= bx + bw, ax + aw, bx + bw)
            s.add(t == z3.And(plane, hi - lo >= need))
            lits.append(t)
        s.add(z3.PbEq([(t, 1) for t in lits], 1))
        side_vars[(a, b)] = lits
    return s, V, side_vars


def feasible(brief: Brief, door_mm: int = 900, timeout_ms: int = 60_000) -> str:
    s, _, _ = model(brief, door_mm)
    s.set("timeout", timeout_ms)
    return str(s.check())          # "sat" | "unsat" | "unknown"


def assignments(brief: Brief, cap: int = 512, door_mm: int = 900, timeout_ms: int = 60_000) -> set[tuple[tuple[str, str, str], ...]]:
    """Every distinct required-touch assignment as a sorted tuple of (a, b, side of a); stops at `cap`."""
    s, _, side_vars = model(brief, door_mm)
    s.set("timeout", timeout_ms)
    out = set()
    while len(out) < cap and s.check() == z3.sat:
        m = s.model()
        chosen, block = [], []
        for (a, b), lits in side_vars.items():
            for side, t in zip(SIDES, lits):
                if z3.is_true(m.eval(t, model_completion=True)):
                    chosen.append((a, b, side)); block.append(t)
        out.add(tuple(sorted(chosen)))
        s.add(z3.Not(z3.And(block)))
    return out


def assignment_of(brief: Brief, placement) -> tuple[tuple[str, str, str], ...]:
    """The required-touch assignment a placement realises (integer boxes), for comparison with `assignments`."""
    from spacetope.solve.grid import touches
    chosen = []
    for a, b in brief.contacts:
        need = required_overlap_mm(brief, a, b)
        for side in SIDES:
            if touches(placement[a], placement[b], side)[0] >= need:
                chosen.append((a, b, side))
    return tuple(sorted(chosen))
