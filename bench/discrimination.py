# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Adventurous Systems

"""E10a pilot: do the eight scores tell a generator's K options apart? Also counts unwished contacts (E10c).
Run with cwd = repo root:  .venv/bin/python ../discrimination.py out.csv"""
import csv
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))
from spacetope.brief import load  # noqa: E402
from spacetope.circulation import prepare  # noqa: E402
from spacetope.doors import plan_doors  # noqa: E402
from spacetope.preverify import preverify  # noqa: E402
from spacetope.score import cheap_scores  # noqa: E402
from spacetope.solve.grid import contact_area  # noqa: E402
from spacetope.solve.registry import GENERATORS  # noqa: E402

METRICS = ["adjacency", "deviation", "compactness", "circulation", "stacking", "vertical", "envelope_fit", "daylight"]
SIDES = ("+x", "-x", "+y", "-y", "ceiling", "floor")


def contacts(brief, pl):
    names = list(pl)
    req = brief.required_pairs()
    touching = {frozenset((a, b)) for i, a in enumerate(names) for b in names[i + 1:]
                if any(contact_area(pl[a], pl[b], s) > 0 for s in SIDES)}
    rooms = {n for n in names if brief.space(n).program == "room"}
    unwished_rr = [p for p in touching if p <= rooms and p not in req]
    return len(touching), len(req), len(unwished_rr)


def main():
    out = Path(sys.argv[1])
    gens = sys.argv[2].split(",") if len(sys.argv) > 2 else ["beam"]
    rows = []
    for fx in sorted(Path("fixtures").glob("*.yaml")):
        brief, _ = prepare(load(fx))
        for gen in gens:
            t0 = time.perf_counter()
            try:
                opts = GENERATORS[gen](brief, None, 0)
            except Exception as e:  # dual refuses some briefs with a reason
                print(fx.stem, gen, "refused:", str(e)[:80], flush=True)
                continue
            tg = time.perf_counter() - t0
            ok = [pl for pl in opts if preverify(brief, pl)[0]]
            if not ok:
                print(fx.stem, gen, "no pre-verified options", flush=True)
                continue
            sc = [cheap_scores(brief, pl) for pl in ok]
            vecs = {tuple(round(s[m], 4) for m in METRICS) for s in sc}
            row = {"fixture": fx.stem, "generator": gen, "spaces": len(brief.spaces), "options": len(ok),
                   "distinct_score_vectors": len(vecs), "t_gen": round(tg, 1)}
            for m in METRICS:
                vals = [s[m] for s in sc]
                row[f"{m}_min"] = round(min(vals), 3)
                row[f"{m}_spread"] = round(max(vals) - min(vals), 3)
            c = [contacts(brief, pl) for pl in ok]
            row["touching_pairs_mean"] = round(sum(x[0] for x in c) / len(c), 1)
            row["required_pairs"] = c[0][1]
            row["unwished_room_room_mean"] = round(sum(x[2] for x in c) / len(c), 1)
            if brief.circulation:
                row["doors_mean"] = round(sum(len(plan_doors(brief, pl)[0]) for pl in ok) / len(ok), 1)
            rows.append(row)
            print(row, flush=True)
    keys = list(dict.fromkeys(k for r in rows for k in r))
    with out.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    main()
