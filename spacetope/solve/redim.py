# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Adventurous Systems

"""Relation-preserving re-dimensioning with CP-SAT: keep every realised contact and every
separation, move sizes inside their bands to reduce dead space and deviation. Integer mm throughout,
so contacts stay exact. Returns None when infeasible or the solver times out."""
from __future__ import annotations

from ortools.sat.python import cp_model

from ..brief import Brief
from ..doors import required_overlap_mm, touch_ok
from .grid import Box, contact_area, overlap_len

SIDES_H = ("+x", "-x", "+y", "-y")


def redimension(brief: Brief, placement: dict[str, Box], door_mm: int = 900, time_limit: float = 5.0,
                w_perim: int = 20, w_dev: int = 1) -> dict[str, Box] | None:
    """Objective = w_dev * sum(fractional deviation * 1e6) + w_perim * (W + L) in mm."""
    names = list(placement)
    m = cp_model.CpModel()
    v: dict[str, dict[str, cp_model.IntVar]] = {}
    horizon = 4 * max(b.x1 for b in placement.values()) + 4 * max(b.y1 for b in placement.values()) + 1
    for n in names:
        s = brief.space(n)
        b = placement[n]
        rotated = (b.w, b.l) == (s.nominal_mm("l"), s.nominal_mm("w")) and b.w != b.l
        bw = s.band("l") if rotated else s.band("w")
        bl = s.band("w") if rotated else s.band("l")
        v[n] = {
            "x": m.NewIntVar(0, horizon, f"x_{n}"), "y": m.NewIntVar(0, horizon, f"y_{n}"),
            "w": m.NewIntVar(bw[0], bw[1], f"w_{n}"), "l": m.NewIntVar(bl[0], bl[1], f"l_{n}"),
        }
        v[n]["x1"] = m.NewIntVar(0, 2 * horizon, f"x1_{n}"); m.Add(v[n]["x1"] == v[n]["x"] + v[n]["w"])
        v[n]["y1"] = m.NewIntVar(0, 2 * horizon, f"y1_{n}"); m.Add(v[n]["y1"] == v[n]["y"] + v[n]["l"])
    # relations
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            A, B = placement[a], placement[b]
            va, vb = v[a], v[b]
            touched = False
            for side in SIDES_H:
                if contact_area(A, B, side) <= 0:
                    continue
                touched = True
                axis = "x" if side in ("+x", "-x") else "y"
                inplane = "y" if axis == "x" else "x"
                if side == "+x": m.Add(va["x1"] == vb["x"])
                if side == "-x": m.Add(vb["x1"] == va["x"])
                if side == "+y": m.Add(va["y1"] == vb["y"])
                if side == "-y": m.Add(vb["y1"] == va["y"])
                cur = overlap_len(A.interval(inplane), B.interval(inplane))
                pair_need = required_overlap_mm(brief, a, b, door_mm)  # a door pair keeps its door (review #5)
                need = min(cur, pair_need) if pair_need <= cur else max(1, cur)
                lo = inplane; hi = inplane + "1"
                # overlap >= need: min(a1,b1) - max(a0,b0) >= need
                m.Add(va[hi] - vb[lo] >= need); m.Add(vb[hi] - va[lo] >= need)
            if touched:
                continue
            # separated: keep the axis ordering that currently separates them (largest gap)
            gaps = []
            if A.x1 <= B.x: gaps.append((B.x - A.x1, ("x", a, b)))
            if B.x1 <= A.x: gaps.append((A.x - B.x1, ("x", b, a)))
            if A.y1 <= B.y: gaps.append((B.y - A.y1, ("y", a, b)))
            if B.y1 <= A.y: gaps.append((A.y - B.y1, ("y", b, a)))
            if not gaps:
                return None  # overlapping input; not our job
            _, (axis, p, q) = max(gaps)
            m.Add(v[p][axis + "1"] <= v[q][axis])
    # objective: bbox half-perimeter (dead space proxy) + deviation
    W = m.NewIntVar(0, 2 * horizon, "W"); L = m.NewIntVar(0, 2 * horizon, "L")
    for n in names:
        m.Add(W >= v[n]["x1"]); m.Add(L >= v[n]["y1"])
    dev_terms = []
    for n in names:
        s = brief.space(n)
        b = placement[n]
        rotated = (b.w, b.l) == (s.nominal_mm("l"), s.nominal_mm("w")) and b.w != b.l
        nom_w = s.nominal_mm("l") if rotated else s.nominal_mm("w")
        nom_l = s.nominal_mm("w") if rotated else s.nominal_mm("l")
        for var, nom in ((v[n]["w"], nom_w), (v[n]["l"], nom_l)):
            d = m.NewIntVar(0, horizon, f"dev_{n}_{var.Name()}")
            m.Add(d >= var - nom); m.Add(d >= nom - var)
            dev_terms.append(d * (1_000_000 // nom))  # fractional deviation, same metric as score.deviation
    m.Minimize(w_perim * (W + L) + w_dev * sum(dev_terms))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit
    solver.parameters.num_workers = 4
    status = solver.Solve(m)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return None
    out = {}
    for n in names:
        b = placement[n]
        out[n] = Box(solver.Value(v[n]["x"]), solver.Value(v[n]["y"]), b.z, solver.Value(v[n]["w"]), solver.Value(v[n]["l"]), b.h)
    # belt and braces: never hand back a layout where a door pair lost its door wall
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            if not touch_ok(brief, a, out[a], b, out[b], door_mm):
                return None
    return out
