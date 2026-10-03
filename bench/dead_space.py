"""Where does a layout's empty ground go? (PLAN M15c). Development tool, not part of the package.

M15c planned a gap-closing pass, on the premise that "rooms attached at alignment offsets leave slivers of dead
space between neighbours on the same corridor side". Measured 2026-09-20, that premise is false: no generator
leaves a sliver. This module is what measured it, and `tests/gates/test_m15c.py` keeps it true. It separates

  * enclosed holes      - empty ground surrounded by spaces, which sliding a room could close
  * corridor-side gaps  - space between consecutive neighbours along one side of a corridor
  * outline             - the rest: the ragged edge of the plan, which is the building's shape, not a hole

Run from the repo root:  .venv/bin/python -m bench.dead_space
"""
from __future__ import annotations

from collections import deque

from spacetope.brief import load
from spacetope.circulation import prepare
from spacetope.preverify import preverify
from spacetope.solve.grid import Box, touches
from spacetope.solve.registry import GENERATORS

FIXTURES = ("eight_rooms_corridor", "hotel_floor", "clinic", "house_ground", "gallery_rich",
            "small_hospital", "school_three_levels")


def levels(pl):
    for z in sorted({b.z for b in pl.values()}):
        yield z, [b for b in pl.values() if b.z <= z < b.z1]


def bbox_dead(pl) -> float:
    total = 0.0
    for _z, on in levels(pl):
        w = max(b.x1 for b in on) - min(b.x for b in on)
        l = max(b.y1 for b in on) - min(b.y for b in on)
        total += (w * l - sum(b.w * b.l for b in on)) / 1e6
    return round(total, 1)


def enclosed_holes(pl, cell: int = 100) -> float:
    """Empty ground not reachable from outside the bounding box. A cell counts as covered only when a space covers
    it completely, so a sliver is over-reported rather than missed."""
    total = 0.0
    for _z, on in levels(pl):
        x0, y0 = min(b.x for b in on), min(b.y for b in on)
        nx = (max(b.x1 for b in on) - x0) // cell + 2
        ny = (max(b.y1 for b in on) - y0) // cell + 2
        grid = [bytearray(ny) for _ in range(nx)]
        for b in on:
            for i in range(-(-(b.x - x0) // cell), (b.x1 - x0) // cell):        # fully inside only
                for j in range(-(-(b.y - y0) // cell), (b.y1 - y0) // cell):
                    if 0 <= i < nx and 0 <= j < ny:
                        grid[i][j] = 1
        seen = [bytearray(ny) for _ in range(nx)]
        q = deque()
        for i in range(nx):
            for j in (0, ny - 1):
                if not grid[i][j] and not seen[i][j]:
                    seen[i][j] = 1; q.append((i, j))
        for j in range(ny):
            for i in (0, nx - 1):
                if not grid[i][j] and not seen[i][j]:
                    seen[i][j] = 1; q.append((i, j))
        while q:
            i, j = q.popleft()
            for a, b_ in ((i + 1, j), (i - 1, j), (i, j + 1), (i, j - 1)):
                if 0 <= a < nx and 0 <= b_ < ny and not grid[a][b_] and not seen[a][b_]:
                    seen[a][b_] = 1; q.append((a, b_))
        total += sum(1 for i in range(nx) for j in range(ny) if not grid[i][j] and not seen[i][j]) * cell * cell / 1e6
    return round(total, 1)


def corridor_side_gaps(brief, pl) -> tuple[float, int]:
    """Metres of gap between consecutive spaces along the long sides of every corridor, and how many."""
    total = count = 0
    for cn, cb in pl.items():
        if brief.space(cn).program != "corridor":
            continue
        along = "y" if cb.l >= cb.w else "x"
        for side in (("+x", "-x") if along == "y" else ("+y", "-y")):
            row = sorted((pl[n].interval(along)[0], pl[n].interval(along)[1]) for n in pl
                         if n != cn and touches(cb, pl[n], side)[0] > 0)
            for (_lo1, hi1), (lo2, _hi2) in zip(row, row[1:]):
                if lo2 > hi1:
                    total += lo2 - hi1; count += 1
    return round(total / 1000, 1), count


def report(name, brief, pl):
    dead = bbox_dead(pl)
    holes = enclosed_holes(pl)
    gaps, n = corridor_side_gaps(brief, pl)
    print(f"{name:24s} bbox dead {dead:7.1f} m2 | enclosed holes {holes:6.1f} m2 | corridor gaps {n:2d} = {gaps:5.1f} m"
          f" | outline {dead - holes:7.1f} m2")


if __name__ == "__main__":
    for fx in FIXTURES:
        brief, _ = prepare(load(f"fixtures/{fx}.yaml"))
        ok = [pl for pl in GENERATORS["beam"](brief, None, 0) if preverify(brief, pl)[0]]
        if not ok:
            print(f"{fx:24s} no pre-verified placement"); continue
        report(fx, brief, ok[0])
    # instrument check: a hole and a gap pushed into a layout on purpose must show up
    brief, _ = prepare(load("fixtures/eight_rooms_corridor.yaml"))
    pl = [p for p in GENERATORS["beam"](brief, None, 0) if preverify(brief, p)[0]][0]
    print("\ncontrol, with a 2 m gap opened along the corridor:")
    victim = max((n for n in pl if brief.space(n).program == "room"), key=lambda n: pl[n].x)
    moved = dict(pl); b = pl[victim]; moved[victim] = Box(b.x + 2000, b.y, b.z, b.w, b.l, b.h)
    report("eight_rooms (room moved)", brief, moved)
