# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Adventurous Systems

"""Scoreboard: run every registered generator on every fixture over fixed seeds.

Usage: python bench.py [--out bench/scoreboard.csv] [--fixtures three_rooms ... | all]
                       [--generators beam ...] [--seeds 0-4] [--params-json '{"beam": {"redim": false}}']
                       [--per-option PATH] [--save-placements DIR] [--resume] [--deterministic]
Generators register themselves in spacetope.solve.registry (M2+). M0 writes the header only.
Rows stream to the CSVs as each (generator, fixture, seed) finishes, so a stopped run loses at most one
cell and `--resume` skips what is already written.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import subprocess
import time
from pathlib import Path

COLUMNS = ["generator", "fixture", "seed", "options", "verified", "distinct", "distinct_topologies", "adjacency", "deviation",
           "compactness", "circulation", "stacking", "vertical", "envelope_fit", "daylight", "t_gen", "t_realise",
           "git_commit", "machine"]
OPTION_COLUMNS = ["generator", "fixture", "seed", "option", "placement_hash", "preverified", "verified", "failed_checks",
                  "adjacency", "deviation", "compactness", "circulation", "stacking", "vertical", "envelope_fit", "daylight",
                  "topology_class", "touching_pairs", "required_pairs", "unwished_room_room", "git_commit", "machine"]
METRICS = ["adjacency", "deviation", "compactness", "circulation", "stacking", "vertical", "envelope_fit", "daylight"]
SIDES = ("+x", "-x", "+y", "-y", "ceiling", "floor")
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


def git_commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    except OSError:
        return ""


def placement_hash(pl) -> str:
    text = ";".join(f"{n}:{b.x},{b.y},{b.z},{b.w},{b.l},{b.h}" for n, b in sorted(pl.items()))
    return hashlib.sha1(text.encode()).hexdigest()[:12]


def contact_counts(brief, pl) -> tuple[int, int, int]:
    """(touching pairs, required pairs, room-to-room pairs nobody asked for) on the boxes (E10c)."""
    from spacetope.solve.grid import contact_area
    names = list(pl)
    req = brief.required_pairs()
    touching = {frozenset((a, b)) for i, a in enumerate(names) for b in names[i + 1:]
                if any(contact_area(pl[a], pl[b], s) > 0 for s in SIDES)}
    rooms = {n for n in names if brief.space(n).program == "room"}
    unwished_rr = [p for p in touching if p <= rooms and p not in req]
    return len(touching), len(req), len(unwished_rr)


def option_rows(brief, options, gname: str, fx: str, seed: int) -> list[dict]:
    from spacetope.pipeline import topology_classes
    from spacetope.score import cheap_scores
    from spacetope.verify import preverify
    classes = topology_classes(brief, [o.placement for o in options]) if options else []
    rows = []
    for i, (o, cls) in enumerate(zip(options, classes)):
        sc = cheap_scores(brief, o.placement)
        touch, req, unwished = contact_counts(brief, o.placement)
        rows.append({"generator": gname, "fixture": fx, "seed": seed, "option": i,
                     "placement_hash": placement_hash(o.placement),
                     "preverified": preverify(brief, o.placement)[0], "verified": o.ok,
                     "failed_checks": " ".join(k for k, (p, _) in o.report.checks.items() if not p),
                     **{m: round(sc.get(m, 0.0), 4) for m in METRICS},
                     "topology_class": cls, "touching_pairs": touch, "required_pairs": req,
                     "unwished_room_room": unwished})
    return rows


class StreamCsv:
    """Append rows as they come; write the header only when the file starts empty."""

    def __init__(self, path: Path, columns: list[str]):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.columns = columns
        new = not path.exists() or path.stat().st_size == 0
        self.f = path.open("a", newline="")
        self.w = csv.DictWriter(self.f, fieldnames=columns)
        if new:
            self.w.writeheader()
            self.f.flush()

    def write(self, row: dict) -> None:
        self.w.writerow({k: row.get(k, "") for k in self.columns})
        self.f.flush()


def done_cells(path: Path) -> set[tuple[str, str, str]]:
    if not path.exists():
        return set()
    with path.open() as f:
        return {(r["generator"], r["fixture"], r["seed"]) for r in csv.DictReader(f)}


def run(out: Path, fixtures: tuple[str, ...], generators: dict, seeds=SEEDS, params_json: dict | None = None,
        per_option: Path | None = None, save_placements: Path | None = None, resume: bool = False,
        deterministic: bool = False) -> int:
    from spacetope.brief import load
    from spacetope.circulation import prepare
    from spacetope.pipeline import generate, summarise
    from spacetope.placement import save_placement

    commit, machine = git_commit(), platform.node()
    board = StreamCsv(out, COLUMNS)
    options_csv = StreamCsv(per_option, OPTION_COLUMNS) if per_option else None
    skip = done_cells(out) if resume else set()
    n = 0
    for gname, gen in generators.items():
        params = dict(BENCH_PARAMS.get(gname, {}))
        params.update((params_json or {}).get(gname, {}))
        if deterministic and gname == "cpsat":
            params["deterministic"] = True
        for fx in fixtures:
            brief, _ = prepare(load(Path("fixtures") / f"{fx}.yaml"))
            for seed in seeds:
                if (gname, fx, str(seed)) in skip:
                    continue
                try:
                    t0 = time.perf_counter()
                    options, t_gen, t_real = generate(gen, brief, seed, dict(params) or None, gname)
                    row = summarise(brief, options, t_gen, t_real)
                except Exception as e:  # noqa: BLE001  (e.g. GeneratorUnsupported: single-level generator, multi-level brief)
                    print(f"  {gname:8s} {fx:22s} seed {seed}: skipped ({type(e).__name__}: {str(e)[:60]})", flush=True)
                    continue
                board.write({"generator": gname, "fixture": fx, "seed": seed, **row,
                             "git_commit": commit, "machine": machine})
                n += 1
                if options_csv:
                    for r in option_rows(brief, options, gname, fx, seed):
                        options_csv.write({**r, "git_commit": commit, "machine": machine})
                if save_placements:
                    d = save_placements / gname / fx
                    d.mkdir(parents=True, exist_ok=True)
                    for i, o in enumerate(options):
                        p = d / f"seed{seed}_opt{i}.json"
                        save_placement(o.placement, p, brief_name=brief.name)
                        meta = json.loads(p.read_text())
                        meta.update(fixture=fx, generator=gname, seed=seed, option=i, commit=commit,
                                    verified=o.ok, expanded=True)
                        p.write_text(json.dumps(meta, indent=2))
                print(f"  {gname:8s} {fx:22s} seed {seed}: verified {row['verified']}/{row['options']} distinct {row['distinct']} adj {row['adjacency']} dev {row['deviation']} t {row['t_gen']}+{row['t_realise']}s", flush=True)
    return n


def parse_seeds(text: str) -> tuple[int, ...]:
    out: list[int] = []
    for part in text.replace(",", " ").split():
        if "-" in part[1:]:
            lo, hi = part.split("-", 1)
            out.extend(range(int(lo), int(hi) + 1))
        else:
            out.append(int(part))
    return tuple(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="bench/scoreboard.csv")
    ap.add_argument("--fixtures", nargs="*", default=list(FIXTURES))
    ap.add_argument("--generators", nargs="*", default=None)
    ap.add_argument("--seeds", default="0-4", help="e.g. '0-4' or '0 1 7'")
    ap.add_argument("--params-json", default=None, help='generator parameters, keyed by generator: \'{"beam": {"redim": false}}\'')
    ap.add_argument("--per-option", default=None, help="write one CSV row per option to this path")
    ap.add_argument("--save-placements", default=None, help="write every placement as JSON under this directory")
    ap.add_argument("--resume", action="store_true", help="skip generator/fixture/seed cells already in --out")
    ap.add_argument("--deterministic", action="store_true", help="CP-SAT: one worker, deterministic time budget (E14)")
    args = ap.parse_args()
    gens = registry()
    if args.generators:
        gens = {k: v for k, v in gens.items() if k in args.generators}
    if args.fixtures == ["all"]:
        fixtures = tuple(sorted(p.stem for p in Path("fixtures").glob("*.yaml")))
    else:
        fixtures = tuple(args.fixtures)
    t0 = time.time()
    n = run(Path(args.out), fixtures, gens, parse_seeds(args.seeds),
            json.loads(args.params_json) if args.params_json else None,
            Path(args.per_option) if args.per_option else None,
            Path(args.save_placements) if args.save_placements else None,
            args.resume, args.deterministic) if gens else 0
    print(f"wrote {n} rows to {args.out} in {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
