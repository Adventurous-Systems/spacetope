"""E5: report the Z3 cross-check counts that `gate_m13` asserts but does not print.

The gate proves the two encodings enumerate the same set of required-touch assignments and that a
contradictory brief is INFEASIBLE in both. It says nothing about *how many*, which is the number the paper
reports. This reports it. Nothing here is part of the package or of any generator: it imports the same
`bench.z3check` and `solve_cpsat` the gate does, so the counts are the gate's own.

Run from the repository root, alone (it drives CP-SAT to exhaustion):
  .venv/bin/python bench/e5_z3.py > bench/paper/e5_z3.txt
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bench.z3check import assignment_of, assignments, feasible  # noqa: E402
from spacetope.brief import Brief, load  # noqa: E402
from spacetope.solve.cpsat import CpsatParams, solve_cpsat  # noqa: E402

FOUR = {"name": "four_rooms", "spaces": [
    {"name": "hall", "w": 6, "l": 4, "h": 3, "program": "room"},
    {"name": "study", "w": 3, "l": 3.5, "h": 3, "program": "room"},
    {"name": "bath", "w": 2, "l": 2.5, "h": 3, "program": "room"},
    {"name": "bed", "w": 4, "l": 4.5, "h": 3, "program": "room"}],
    "contacts": [["hall", "study"], ["hall", "bath"], ["hall", "bed"]]}

CONTRADICTORY = {"name": "too_many_neighbours",
                 "spaces": [{"name": "a", "w": 1, "l": 1, "h": 3, "program": "room", "tol": 0.0}] +
                           [{"name": n, "w": 4, "l": 4, "h": 3, "program": "room", "tol": 0.0} for n in "bcdef"],
                 "contacts": [["a", n] for n in "bcdef"]}


def report(name: str, brief: Brief) -> None:
    upper = 4 ** len(brief.contacts)
    t0 = time.time()
    zs = assignments(brief, cap=1024)
    t_z3 = time.time() - t0
    t0 = time.time()
    res = solve_cpsat(brief, CpsatParams(k=600, time_limit=240.0, per_solve_max=5.0, w_stack=0))
    cs = {assignment_of(brief, pl) for pl in res.placements}
    t_cp = time.time() - t0
    print(f"{name}: {len(brief.spaces)} spaces, {len(brief.contacts)} required contacts, "
          f"{upper} side assignments possible ({4}^{len(brief.contacts)})")
    print(f"  Z3     found {len(zs):4d} feasible assignments in {t_z3:6.1f}s")
    print(f"  CP-SAT found {len(cs):4d} feasible assignments in {t_cp:6.1f}s "
          f"(last status {res.statuses[-1]}, so it ran to exhaustion)")
    print(f"  identical sets: {cs == zs}   CP-SAT subset of Z3: {cs <= zs}")
    if cs != zs:
        print(f"  only in Z3:     {sorted(zs - cs)[:5]}")
        print(f"  only in CP-SAT: {sorted(cs - zs)[:5]}")
    print()


def main() -> None:
    print("E5: Z3 cross-check of the relational model (PLAN M13, design note C)")
    print("Counts are the ones gate_m13 asserts; this only prints them.\n")
    report("three_rooms", load(Path("fixtures/three_rooms.yaml")))
    report("four_rooms", Brief.from_dict(FOUR))
    brief = Brief.from_dict(CONTRADICTORY)
    z = feasible(brief)
    c = solve_cpsat(brief, CpsatParams(k=2, time_limit=20.0)).status
    print(f"contradictory brief ({len(brief.spaces)} spaces, {len(brief.contacts)} contacts onto one 1x1 m room)")
    print(f"  Z3     {z}")
    print(f"  CP-SAT {c}")
    print(f"  both reject: {z == 'unsat' and c == 'INFEASIBLE'}")


if __name__ == "__main__":
    main()
