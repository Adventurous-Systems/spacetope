# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Adventurous Systems

"""E10a/E10c from the recorded run, no regeneration: do the eight scores tell a generator's K
options apart (E10a), and how many room-to-room contacts nobody asked for does each generator
leave (E10c)?

Reads `options_e2.csv` (one row per option: the eight scores, touching/required/unwished counts,
verified flag) and aggregates per (generator, fixture, seed) over the *verified* options, using the
pilot's definition of a distinct score vector: the eight metrics rounded to 4 decimals
(`bench/discrimination.py`). The pilot regenerated options; this reads the frozen E2 run, so the
numbers are the run's own.

Usage, from the repository root:
  .venv/bin/python bench/e10_from_csv.py bench/paper/options_e2.csv bench/paper/e10_discrimination.csv
"""
from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path

METRICS = ["adjacency", "deviation", "compactness", "circulation", "stacking", "vertical",
           "envelope_fit", "daylight"]


def main() -> None:
    src, out = Path(sys.argv[1]), Path(sys.argv[2])
    groups: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    with src.open() as f:
        for r in csv.DictReader(f):
            if r["verified"] == "True":
                groups[(r["generator"], r["fixture"], r["seed"])].append(r)

    rows = []
    for (gen, fx, seed), opts in sorted(groups.items()):
        vecs = {tuple(round(float(o[m]), 4) for m in METRICS) for o in opts}
        row = {"generator": gen, "fixture": fx, "seed": seed, "verified_options": len(opts),
               "distinct_score_vectors": len(vecs),
               "distinct_topology_classes": len({o["topology_class"] for o in opts})}
        for m in METRICS:
            vals = [float(o[m]) for o in opts]
            row[f"{m}_spread"] = round(max(vals) - min(vals), 4)
        for c in ("touching_pairs", "required_pairs", "unwished_room_room"):
            row[f"{c}_mean"] = round(sum(int(o[c]) for o in opts) / len(opts), 1)
        rows.append(row)

    with out.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    print(f"wrote {len(rows)} (generator, fixture, seed) rows to {out}\n")
    print("E10a: distinct score vectors / verified options, summed per generator")
    per_gen: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        per_gen[r["generator"]].append(r)
    for gen, rs in sorted(per_gen.items()):
        opts = sum(r["verified_options"] for r in rs)
        vecs = sum(r["distinct_score_vectors"] for r in rs)
        collapsed = sum(1 for r in rs if r["verified_options"] > 1 and r["distinct_score_vectors"] == 1)
        print(f"  {gen:8s} {vecs}/{opts} distinct; {collapsed} of {len(rs)} calls where K>1 options"
              f" share one vector")
    print("\nE10c: unwished room-to-room pairs, mean per option per generator")
    for gen, rs in sorted(per_gen.items()):
        tot = sum(r["unwished_room_room_mean"] * r["verified_options"] for r in rs)
        opts = sum(r["verified_options"] for r in rs)
        print(f"  {gen:8s} {tot / opts:.1f} unwished pairs per option over {opts} verified options")


if __name__ == "__main__":
    main()
