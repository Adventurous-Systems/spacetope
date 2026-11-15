"""Affinity baseline (PLAN M19 gate line 6): how well does the unchanged beam meet the written affinities?

One row per fixture that carries any affinity (tags rules, per-space entries or `wishes.exterior`) x beam x seeds 0-2.
`affinity` is the mean score over verified options; the met/total columns are sums over verified options.
M20 sets its improvement margin from these numbers. Run from the repo root, never beside pytest:

    .venv/bin/python -m bench.affinity_baseline [out.csv]
"""
from __future__ import annotations

import csv
import sys
import time
from pathlib import Path

from spacetope import affinity
from spacetope.brief import load
from spacetope.circulation import prepare
from spacetope.pipeline import generate
from spacetope.solve.registry import GENERATORS

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "bench" / "history" / "2026-11-15_m19_affinity.csv"
SEEDS = (0, 1, 2)
SLOW = {}       # fixture -> {"build": "top", "keep": 3}, filled in only if the full run is too long
COLUMNS = ["fixture", "generator", "seed", "build", "options", "verified", "affinity", "soft_met", "soft_total",
           "hard_met", "hard_total", "unmeasured"]


def fixtures():
    for p in sorted((ROOT / "fixtures").glob("*.yaml")):
        brief = load(p)
        if affinity.expand(prepare(brief)[0]):
            yield p.stem, brief


def row(name: str, brief, seed: int) -> dict:
    kw = SLOW.get(name, {"build": "all"})
    options, _, _ = generate(GENERATORS["beam"], brief, seed, None, "beam", **kw)
    ver = [o for o in options if o.ok]
    an = [o.analysis["affinity"] for o in ver if "affinity" in o.analysis]
    n = lambda k, f: sum(a[k][f] for a in an)
    return {"fixture": name, "generator": "beam", "seed": seed, "build": kw["build"], "options": len(options),
            "verified": len(ver), "affinity": round(sum(a["score"] for a in an) / len(an), 4) if an else "",
            "soft_met": n("soft", "met"), "soft_total": n("soft", "total"), "hard_met": n("hard", "met"),
            "hard_total": n("hard", "total"), "unmeasured": sum(a["unmeasured"] for a in an)}


def main(out: Path = OUT) -> None:
    rows = []
    for name, brief in fixtures():
        t = time.perf_counter()
        for seed in SEEDS:
            rows.append(row(name, brief, seed))
            print(rows[-1], flush=True)
        print(f"  {name}: {time.perf_counter() - t:.0f} s", flush=True)
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, COLUMNS)
        w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else OUT)
