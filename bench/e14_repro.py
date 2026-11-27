# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Adventurous Systems

"""E14 from the recorded runs: do two runs of the same brief and seed give the same options?

Reads the per-option files of repeated `bench.py` runs (`<dir>/<run>_options.csv`) and compares,
per (generator, fixture, seed), the ordered list of placement hashes. A cell is `identical` when
every run in the group gives the same hashes in the same order, `same_set` when only the order
differs. `jaccard_min` is the smallest overlap between any two runs' hash sets.

Usage, from the repository root:
  .venv/bin/python bench/e14_repro.py bench/paper/e14 bench/paper/e14_repro.csv
"""
from __future__ import annotations

import csv
import sys
from collections import defaultdict
from itertools import combinations
from pathlib import Path

GROUPS = {"deterministic": ("det_a", "det_b"), "default": ("def_a", "def_b", "def_c")}


def hashes(path: Path) -> dict[tuple[str, str, str], list[str]]:
    out: dict[tuple[str, str, str], list[tuple[int, str]]] = defaultdict(list)
    with path.open() as f:
        for r in csv.DictReader(f):
            out[(r["generator"], r["fixture"], r["seed"])].append((int(r["option"]), r["placement_hash"]))
    return {k: [h for _, h in sorted(v)] for k, v in out.items()}


def main() -> None:
    src, out = Path(sys.argv[1]), Path(sys.argv[2])
    rows = []
    for mode, runs in GROUPS.items():
        data = [hashes(src / f"{r}_options.csv") for r in runs]
        for key in sorted(set().union(*data)):
            lists = [d.get(key, []) for d in data]
            sets = [set(x) for x in lists]
            jac = min(len(a & b) / len(a | b) if a | b else 1.0 for a, b in combinations(sets, 2))
            rows.append({"mode": mode, "generator": key[0], "fixture": key[1], "seed": key[2],
                         "runs": len(runs), "options": " ".join(str(len(x)) for x in lists),
                         "identical": all(x == lists[0] for x in lists),
                         "same_set": all(s == sets[0] for s in sets), "jaccard_min": round(jac, 4)})
    with out.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    per: dict[tuple[str, str], list[int]] = defaultdict(lambda: [0, 0, 0])
    for r in rows:
        c = per[(r["mode"], r["generator"])]
        c[0] += 1
        c[1] += r["identical"]
        c[2] += r["same_set"]
    print(f"wrote {len(rows)} rows to {out}\n\ncells (generator, fixture, seed) identical across runs")
    for (mode, gen), (n, ident, same) in sorted(per.items()):
        print(f"  {mode:14s} {gen:8s} identical {ident:3d}/{n:<3d}  same set {same:3d}/{n}")
    for r in rows:
        if r["mode"] == "deterministic" and not r["identical"]:
            print(f"  not identical: {r['generator']} {r['fixture']} seed {r['seed']}"
                  f" options {r['options']} jaccard {r['jaccard_min']}")


if __name__ == "__main__":
    main()
