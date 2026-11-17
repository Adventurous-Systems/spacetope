# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Adventurous Systems

"""E9: planted-brief recovery. One factor at a time around a base, 20 seeds per point.

For every (sweep point, seed): plant the brief, run each generator at the bench budgets, and record
whether it solved the brief (at least one option passes all nine checks), the verified share, whether
the planted topology class is among the verified options, and the generation time.

Usage, from the repository root (run alone: generation times are measured):
  .venv/bin/python bench/planted_run.py --out bench/paper/e9_planted.csv --save bench/paper/planted [--resume]
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

SEEDS = range(20)
BENCH_PARAMS = {"cpsat": {"time_limit": 20.0, "per_solve_max": 5.0}, "dual": {"time_limit": 20.0}}
GENS = {"a": ("beam", "cpsat", "dual", "treemap"), "b": ("beam", "cpsat", "dual")}

BASE_A = {"n": 9, "t": 0.10, "rho": 0.5, "slicing": True}
BASE_B = {"rooms": 16, "t": 0.10, "frontage": 0.75, "shape": "straight", "double_loaded": True, "levels": 1}
SWEEPS_A = {"n": [4, 6, 9, 12, 16], "t": [0.02, 0.05, 0.10, 0.20], "rho": [0.25, 0.5, 0.75, 1.0],
            "slicing": [True, False]}
SWEEPS_B = {"rooms": [8, 16, 24, 32, 48, 64], "t": [0.05, 0.10, 0.20], "frontage": [0.6, 0.75, 0.85, 0.95],
            "shape": ["straight", "L"], "levels": [1, 2, 3]}

COLUMNS = ["family", "swept", "point", "params", "seed", "generator", "status", "options", "verified",
           "solved", "planted_class_found", "t_gen", "t_realise", "spaces"]


def points(base: dict, sweeps: dict) -> list[tuple[str, dict]]:
    out, seen = [], set()
    for key, values in sweeps.items():
        for v in values:
            p = {**base, key: v}
            sig = json.dumps(p, sort_keys=True)
            if sig not in seen:
                seen.add(sig)
                out.append((f"{key}={v}" if p != base else "base", p))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="bench/paper/e9_planted.csv")
    ap.add_argument("--save", default=None, help="also write each planted brief + placement here")
    ap.add_argument("--families", nargs="*", default=["a", "b"])
    ap.add_argument("--seeds", type=int, default=20)
    ap.add_argument("--resume", action="store_true")
    args = ap.parse_args()

    from spacetope.circulation import BriefInvalid, prepare
    from spacetope.pipeline import generate, topology_classes
    from spacetope.placement import save_placement
    from spacetope.planted import plant
    from spacetope.solve.registry import GENERATORS

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    done = set()
    if args.resume and out.exists():
        with out.open() as f:
            done = {(r["family"], r["point"], r["seed"], r["generator"]) for r in csv.DictReader(f)}
    new = not out.exists() or out.stat().st_size == 0
    f = out.open("a", newline="")
    w = csv.DictWriter(f, fieldnames=COLUMNS)
    if new:
        w.writeheader()

    grids = {"a": points(BASE_A, SWEEPS_A), "b": points(BASE_B, SWEEPS_B)}
    t_start = time.time()
    for family in args.families:
        for swept, params in grids[family]:
            for seed in range(args.seeds):
                try:
                    brief, planted_pl = plant(family, dict(params), seed)
                    expanded, _ = prepare(brief)
                except BriefInvalid as e:
                    w.writerow({"family": family, "swept": swept.split("=")[0], "point": swept,
                                "params": json.dumps(params), "seed": seed, "generator": "",
                                "status": f"invalid: {str(e)[:60]}"})
                    f.flush()
                    continue
                if args.save:
                    d = Path(args.save)
                    d.mkdir(parents=True, exist_ok=True)
                    (d / f"{brief.name}.yaml").write_text(brief.to_yaml())
                    save_placement(planted_pl, d / f"{brief.name}.planted.json", brief.name)
                for gname in GENS[family]:
                    key = (family, swept, str(seed), gname)
                    if key in done:
                        continue
                    row = {"family": family, "swept": swept.split("=")[0], "point": swept,
                           "params": json.dumps(params), "seed": seed, "generator": gname,
                           "spaces": len(expanded.spaces)}
                    try:
                        options, t_gen, t_real = generate(GENERATORS[gname], expanded, seed,
                                                          dict(BENCH_PARAMS.get(gname, {})) or None, gname)
                        ok = [o for o in options if o.ok]
                        classes = topology_classes(expanded, [planted_pl] + [o.placement for o in ok])
                        row.update(status="ok", options=len(options), verified=len(ok), solved=bool(ok),
                                   planted_class_found=classes[0] in classes[1:],
                                   t_gen=round(t_gen, 3), t_realise=round(t_real, 3))
                    except Exception as e:  # noqa: BLE001 (GeneratorUnsupported and friends are data here)
                        row.update(status=f"{type(e).__name__}: {str(e)[:60]}")
                    w.writerow({k: row.get(k, "") for k in COLUMNS})
                    f.flush()
                    print(f"{family} {swept:14s} seed {seed:2d} {gname:8s} {row.get('status', '')}"
                          f" v {row.get('verified', '-')}/{row.get('options', '-')}"
                          f" planted {row.get('planted_class_found', '-')} ({time.time() - t_start:.0f}s)", flush=True)
    f.close()
    print(f"done in {time.time() - t_start:.0f}s -> {out}")


if __name__ == "__main__":
    main()
