"""Scoreboard: run every registered generator on every fixture over fixed seeds.

Usage: python bench.py [--out bench/scoreboard.csv] [--fixtures three_rooms ...] [--generators beam ...]
Generators register themselves in spacetope.solve.registry (M2+). M0 writes the header only.
"""
from __future__ import annotations

import argparse
import csv
import time
from pathlib import Path

COLUMNS = ["generator", "fixture", "seed", "options", "verified", "distinct", "distinct_topologies", "adjacency", "deviation",
           "compactness", "circulation", "stacking", "vertical", "envelope_fit", "daylight", "t_gen", "t_realise"]
SEEDS = (0, 1, 2, 3, 4)
FIXTURES = ("three_rooms", "eight_rooms_corridor", "two_levels_stair")


def registry() -> dict:
    try:
        from spacetope.solve.registry import GENERATORS
        return GENERATORS
    except ImportError:
        return {}


# Fixed budgets so the scoreboard compares quality at equal cost; gates use their own budgets.
BENCH_PARAMS = {"cpsat": {"time_limit": 20.0, "per_solve_max": 5.0}, "dual": {"time_limit": 20.0}}


def run(out: Path, fixtures: tuple[str, ...], generators: dict, seeds=SEEDS) -> list[dict]:
    from spacetope.brief import load
    from spacetope.pipeline import run_generator  # M2

    rows = []
    for gname, gen in generators.items():
        for fx in fixtures:
            brief = load(Path("fixtures") / f"{fx}.yaml")
            for seed in seeds:
                try:
                    row = run_generator(gen, brief, seed, BENCH_PARAMS.get(gname), gname)
                except Exception as e:  # noqa: BLE001  (e.g. GeneratorUnsupported: single-level generator, multi-level brief)
                    print(f"  {gname:8s} {fx:22s} seed {seed}: skipped ({type(e).__name__}: {str(e)[:60]})", flush=True)
                    continue
                rows.append({"generator": gname, "fixture": fx, "seed": seed, **row})
                print(f"  {gname:8s} {fx:22s} seed {seed}: verified {row['verified']}/{row['options']} distinct {row['distinct']} adj {row['adjacency']} dev {row['deviation']} t {row['t_gen']}+{row['t_realise']}s", flush=True)
    return rows


def write(out: Path, rows: list[dict]) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in COLUMNS})


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="bench/scoreboard.csv")
    ap.add_argument("--fixtures", nargs="*", default=list(FIXTURES))
    ap.add_argument("--generators", nargs="*", default=None)
    args = ap.parse_args()
    gens = registry()
    if args.generators:
        gens = {k: v for k, v in gens.items() if k in args.generators}
    t0 = time.time()
    rows = run(Path(args.out), tuple(args.fixtures), gens) if gens else []
    write(Path(args.out), rows)
    print(f"wrote {len(rows)} rows to {args.out} in {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
