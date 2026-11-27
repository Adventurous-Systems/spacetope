# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Adventurous Systems

"""E1d from the recorded runs, no regeneration: does the pre-verifier (integer boxes, no kernel)
give the verdict the kernel verifier gives?

Reads `options_e2.csv` (columns `preverified`, `verified`) and the E1 files `e1_faults_v2.csv` and
`e1b_metamorphic_v2.csv` (columns `preverify`, `verify`), and writes one confusion row per source and
kind. "Positive" is "accepted": a false accept is a placement the pre-verifier passed and the
kernel rejected, which costs a wasted build; a false reject is one it would have hidden from the
architect, which costs an option.

Usage, from the repository root:
  .venv/bin/python bench/e1d_from_csv.py bench/paper bench/paper/e1d_confusion.csv
"""
from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path

SOURCES = [("options_e2.csv", "preverified", "verified", "generator"),
           ("e1_faults_v2.csv", "preverify", "verify", "transform"),
           ("e1b_metamorphic_v2.csv", "preverify", "verify", "transform")]
CELLS = ("both_accept", "both_reject", "false_accept", "false_reject")


def cell(pre: bool, ker: bool) -> str:
    if pre == ker:
        return "both_accept" if pre else "both_reject"
    return "false_accept" if pre else "false_reject"


def main() -> None:
    src, out = Path(sys.argv[1]), Path(sys.argv[2])
    rows = []
    for name, pcol, vcol, by in SOURCES:
        counts: dict[str, dict[str, int]] = defaultdict(lambda: dict.fromkeys(CELLS, 0))
        with (src / name).open() as f:
            for r in csv.DictReader(f):
                if r[pcol] not in ("True", "False") or r[vcol] not in ("True", "False"):
                    continue  # a crashed row has no verdict to compare
                counts[r[by]][cell(r[pcol] == "True", r[vcol] == "True")] += 1
        for key, c in sorted(counts.items()):
            n = sum(c.values())
            rows.append({"source": name, "group": key, "placements": n, **c,
                         "agreement": round((c["both_accept"] + c["both_reject"]) / n, 4)})
    total = {k: sum(r[k] for r in rows) for k in ("placements", *CELLS)}
    rows.append({"source": "all", "group": "all", **total,
                 "agreement": round((total["both_accept"] + total["both_reject"]) / total["placements"], 4)})
    with out.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    for r in rows:
        print(f"  {r['source']:22s} {r['group']:18s} n {r['placements']:5d}  accept {r['both_accept']:5d}"
              f"  reject {r['both_reject']:5d}  false accept {r['false_accept']:3d}"
              f"  false reject {r['false_reject']:3d}")
    print(f"wrote {len(rows)} rows to {out}")


if __name__ == "__main__":
    main()
