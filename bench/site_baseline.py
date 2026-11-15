"""Orientation pass baseline (PLAN M21 gate line 6): what does turning each finished plan cost and change?

One row per site brief (`fixtures/site/`) x beam seed 0-2. The beam runs once; the same placements are verified with the
real verifier as generated and after `orient.best`. Facade scores are means over the pre-verified placements (the
figures of gate line 4); `worst` is the lowest score among the symmetries that fit the envelope. Run from the repo root:

    .venv/bin/python -m bench.site_baseline [out.csv]
"""
from __future__ import annotations

import csv
import sys
import time
from collections import Counter
from pathlib import Path

from spacetope import orient
from spacetope.brief import load
from spacetope.circulation import prepare
from spacetope.pipeline import evaluate_placements
from spacetope.preverify import preverify
from spacetope.solve.registry import GENERATORS

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "bench" / "history" / "2026-11-15_m21_site.csv"
SEEDS = (0, 1, 2)
NAMES = ("school_three_levels", "small_hospital", "house_ground", "clinic")
COLUMNS = ["fixture", "seed", "options", "preverified", "verified_without", "verified_with", "facade_generated",
           "facade_after", "facade_worst", "signatures_before", "signatures_after", "symmetries", "t_gen", "t_pass"]


def site_brief(name: str):
    return prepare(load(ROOT / "fixtures" / "site" / f"{name}.yaml"))[0]


def row(name: str, brief, seed: int) -> dict:
    t = time.process_time()
    pls = GENERATORS["beam"](brief, None, seed)
    t_gen = time.process_time() - t
    t = time.process_time()
    turned = [orient.best(brief, pl) for pl in pls]
    t_pass = time.process_time() - t
    pre = [i for i, pl in enumerate(pls) if preverify(brief, pl)[0]]
    mean = lambda xs: round(sum(xs) / len(xs), 4) if xs else ""
    worst = [min(orient.facade_score(brief, q)[1] for q in orient.fitting(brief, pls[i]).values()) for i in pre]
    before = [o for o in evaluate_placements(brief, pls, "beam", seed) if o.ok]
    after = [o for o in evaluate_placements(brief, [q for q, _ in turned], "beam", seed) if o.ok]
    return {"fixture": name, "seed": seed, "options": len(pls), "preverified": len(pre), "verified_without": len(before),
            "verified_with": len(after), "facade_generated": mean([turned[i][1]["facade_before"] for i in pre]),
            "facade_after": mean([turned[i][1]["facade_after"] for i in pre]), "facade_worst": mean(worst),
            "signatures_before": len({o.signature for o in before}), "signatures_after": len({o.signature for o in after}),
            "symmetries": ";".join(f"{k}:{v}" for k, v in sorted(Counter(r["symmetry"] for _, r in turned).items())),
            "t_gen": round(t_gen, 3), "t_pass": round(t_pass, 3)}


def main(out: Path = OUT) -> None:
    rows = []
    for name in NAMES:
        brief = site_brief(name)
        for seed in SEEDS:
            rows.append(row(name, brief, seed))
            print(rows[-1], flush=True)
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, COLUMNS)
        w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else OUT)
