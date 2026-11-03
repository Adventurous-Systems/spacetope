"""spacetope CLI. M1: realise a placement, verify, score, render."""
from __future__ import annotations

import argparse
import contextlib
import json
import sys

from .brief import load
from .placement import load_placement

_stdout = sys.stdout  # the real stdout; while a command runs, library messages go to stderr instead


def emit(obj) -> None:
    """Write a command's JSON result: the only thing a command puts on stdout (STATUS §2.6, fix 2)."""
    _stdout.write(json.dumps(obj, indent=1) + "\n")
    _stdout.flush()


def cmd_realise(args) -> int:
    from .score import score
    from .verify import verify
    from .circulation import BriefInvalid, prepare
    try:
        brief, _ = prepare(load(args.brief))  # the placement names the expanded spaces (review 2026-09-13, #10)
    except BriefInvalid as e:
        emit({"invalid_brief": [p.to_dict() for p in e.problems]})
        return 2
    placement = load_placement(args.placement)
    rep = verify(brief, placement)
    out = {"verify": rep.to_dict()}
    if rep.ok and rep.realised is not None:
        out["scores"] = score(rep.realised)
        if args.html:
            from .viz.plotly import write_html
            out["html"] = str(write_html(rep.realised, args.html))
        if args.save:
            from .io.brep import save
            from .io.graph import graph_payload, save_graph
            paths = save(rep.realised, args.save)
            save_graph(graph_payload(rep.realised), str(args.save) + ".graph.json")
            out["saved"] = {k: str(v) for k, v in paths.items()}
    emit(out)
    return 0 if rep.ok else 1


def cmd_generate(args) -> int:
    """Generate, verify, score and rank options; write a JSON index plus optional HTML/BREP per option."""
    from pathlib import Path
    from .pipeline import generate, rank
    from .solve.registry import GENERATORS
    from .circulation import BriefInvalid
    from .solve.registry import GeneratorUnsupported
    from . import kernel
    brief = load(args.brief)
    params = json.loads(args.params) if args.params else None
    try:
        options, t_gen, t_real = generate(GENERATORS[args.generator], brief, args.seed, params, args.generator)
    except (GeneratorUnsupported, BriefInvalid) as e:
        emit({"error": str(e)})
        return 2
    ranked = rank(options)
    out_dir = Path(args.out) if args.out else None
    index = {"brief": brief.name, "generator": args.generator, "seed": args.seed, "t_gen": round(t_gen, 3),
             "t_realise": round(t_real, 3), "kernel": kernel.active(), "options": []}
    for i, o in enumerate(ranked):
        entry = o.to_dict()
        entry["rank"] = i
        if out_dir and o.ok and o.realised is not None:
            out_dir.mkdir(parents=True, exist_ok=True)
            stem = out_dir / f"option_{i:02d}"
            if args.html:
                from .viz.plotly import write_html
                entry["html"] = str(write_html(o.realised, stem.with_suffix(".html")))
            if args.save:
                from .io.brep import save
                from .io.graph import graph_payload, save_graph
                entry["saved"] = {k: str(v) for k, v in save(o.realised, stem).items()}
                save_graph(graph_payload(o.realised), str(stem) + ".graph.json")
        index["options"].append(entry)
    text = json.dumps(index, indent=1)
    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "options.json").write_text(text)
    summary = [{k: e[k] for k in ("rank", "ok", "scores")} for e in index["options"]]
    emit({"brief": brief.name, "generator": args.generator, "seed": args.seed, "t_gen": index["t_gen"],
          "t_realise": index["t_realise"], "options": summary, "out": str(out_dir) if out_dir else None})
    return 0 if any(o.ok for o in options) else 1


def cmd_floors(args) -> int:
    """How many floors does this brief need? Bounds, then verified options per candidate count (M8)."""
    from .floors import search
    from .pipeline import rank
    from .solve.registry import GENERATORS
    brief = load(args.brief)
    b, results = search(brief, GENERATORS[args.generator], seed=args.seed, keep=args.keep, most=args.most)
    out = {"brief": brief.name, "level_height": b.level_height, "footprint": b.footprint,
           "areas": {"rooms": round(b.areas.rooms, 1), "corridor": round(b.areas.corridor, 1), "shafts": round(b.areas.shafts, 1)},
           "bounds": {"min": b.min_levels, "max": b.max_levels, "feasible": b.feasible, "reason": b.reason},
           "candidates": []}
    for r in results:
        best = rank(r.verified)[:1]
        out["candidates"].append({
            "levels": r.levels, "options": len(r.options), "verified": len(r.verified),
            "t_gen": round(r.t_gen, 2), "t_build": round(r.t_build, 2),
            "best_scores": best[0].scores if best else None,
        })
    emit(out)
    return 0 if b.feasible and any(c["verified"] for c in out["candidates"]) else 1


def cmd_export(args) -> int:
    """OBJ and/or JSON of a realised complex, from a saved option stem or from a brief + placement."""
    from .io.mesh import write_json, write_obj
    if args.stem:
        from .io.brep import load as load_realised
        r = load_realised(args.stem)
    else:
        if not (args.brief and args.placement):
            emit({"error": "give --stem, or --brief and --placement"}); return 2
        from .circulation import BriefInvalid, prepare
        try:
            brief, _ = prepare(load(args.brief))
        except BriefInvalid as e:
            emit({"invalid_brief": [p.to_dict() for p in e.problems]}); return 2
        from .realise import realise
        r = realise(brief, load_placement(args.placement))
    out = {}
    if args.obj:
        out["obj"] = str(write_obj(r, args.obj))
    if args.json:
        out["json"] = str(write_json(r, args.json))
    if not out:
        emit({"error": "give --obj and/or --json"}); return 2
    emit({"brief": r.brief.name, "cells": r.n_cells, "doors": len(r.doors), **out})
    return 0


def _seed_range(spec: str) -> list[int]:
    """`7`, `0-99`, or `1,4,9`."""
    out: list[int] = []
    for part in str(spec).split(","):
        if "-" in part:
            lo, hi = part.split("-", 1)
            out.extend(range(int(lo), int(hi) + 1))
        else:
            out.append(int(part))
    return out


def cmd_programme(args) -> int:
    """Draw briefs from a programme: write them out, perturb them, or turn them into dataset rows (M17)."""
    from pathlib import Path
    from .circulation import BriefInvalid, prepare
    from .programme import ProgrammeError, names, sample, variations
    if args.list or not args.name:
        emit({"programmes": names()})
        return 0
    seeds = _seed_range(args.seeds)
    out_dir = Path(args.out) if args.out else None
    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)
    written, tight, invalid, rows = [], 0, [], 0
    if args.dataset:
        from .learn.dataset import rows_from_programme, write_rows
        from .solve.registry import GENERATORS
        rows = write_rows(rows_from_programme(args.name, seeds, GENERATORS[args.generator], args.generator,
                                              json.loads(args.params) if args.params else None, args.per_brief),
                          args.dataset)
    else:
        for seed in seeds:
            try:
                brief, front = sample(args.name, seed)
                expanded, _ = prepare(brief)
            except (ProgrammeError, BriefInvalid) as e:
                invalid.append({"seed": seed, "why": str(e)[:160]})
                continue
            tight += front.tight
            entry = {"seed": seed, "name": brief.name, "spaces": len(expanded.spaces), "levels": brief.levels,
                     "frontage": round(front.ratio, 3), "tight": front.tight}
            if out_dir:
                (out_dir / f"{brief.name}.yaml").write_text(brief.to_yaml())
                entry["path"] = str(out_dir / f"{brief.name}.yaml")
                if args.variations:
                    for kind, v in variations(brief, seed).items():
                        (out_dir / f"{brief.name}__{kind}.yaml").write_text(v.to_yaml())
                    entry["variations"] = len(variations(brief, seed))
            written.append(entry)
    emit({"programme": args.name, "seeds": len(seeds), "briefs": len(written),
          "tight_frontage": tight, "invalid": invalid[:5], "rows": rows,
          "out": str(out_dir) if out_dir else None, "dataset": args.dataset})
    return 0 if (rows or written) else 1


def cmd_planted(args) -> int:
    """Write briefs with a known exact solution, and that solution next to them (E9)."""
    from pathlib import Path
    from .circulation import BriefInvalid, prepare
    from .placement import save_placement
    from .planted import plant
    from .preverify import preverify
    params = json.loads(args.params) if args.params else {}
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    written, failed = [], []
    for seed in _seed_range(args.seeds):
        brief, pl = plant(args.family, dict(params), seed)
        try:
            expanded, _ = prepare(brief)
        except BriefInvalid as e:
            failed.append({"seed": seed, "why": str(e)[:160]})
            continue
        ok, checks = preverify(expanded, pl)
        if not ok:  # the sanity rule: a planted placement that fails is a bug, never something to write out
            failed.append({"seed": seed, "why": "; ".join(d for k, (p, d) in checks.items() if not p)[:160]})
            continue
        (out_dir / f"{brief.name}.yaml").write_text(brief.to_yaml())
        save_placement(pl, out_dir / f"{brief.name}.planted.json", brief.name)
        written.append(brief.name)
    emit({"family": args.family.lower(), "params": params, "written": len(written),
          "failed": failed, "out": str(out_dir)})
    return 0 if written and not failed else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="spacetope")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("realise", help="build, verify, score a placement")
    r.add_argument("brief"); r.add_argument("placement")
    r.add_argument("--html"); r.add_argument("--save")
    r.set_defaults(fn=cmd_realise)
    g = sub.add_parser("generate", help="generate, verify, score and rank options for a brief")
    g.add_argument("brief")
    g.add_argument("--generator", default="beam", choices=["beam", "cpsat", "treemap", "dual"])
    g.add_argument("--seed", type=int, default=0)
    g.add_argument("--params", help="JSON dict of generator params, e.g. '{\"k\": 4}'")
    g.add_argument("--out", help="directory for options.json and per-option files")
    g.add_argument("--html", action="store_true", help="write a Plotly HTML per option (needs --out)")
    g.add_argument("--save", action="store_true", help="write BREP + selectors + graph JSON per option (needs --out)")
    g.set_defaults(fn=cmd_generate)
    f = sub.add_parser("floors", help="search how many floors a brief needs (M8)")
    f.add_argument("brief")
    f.add_argument("--generator", default="beam", choices=["beam", "cpsat"])
    f.add_argument("--seed", type=int, default=0)
    f.add_argument("--keep", type=int, default=3, help="placements built and verified per candidate count")
    f.add_argument("--most", type=int, default=3, help="how many candidate counts to try")
    f.set_defaults(fn=cmd_floors)
    x = sub.add_parser("export", help="OBJ and/or JSON of a realised cell complex, from topologic")
    x.add_argument("--stem", help="option stem written by --save (reads .brief.json + .placement.json)")
    x.add_argument("--brief"); x.add_argument("--placement")
    x.add_argument("--obj", help="output .obj path (a .mtl is written next to it)")
    x.add_argument("--json", help="output .json path")
    x.set_defaults(fn=cmd_export)
    pr = sub.add_parser("programme", help="draw briefs from a programme, or dataset rows from one (M17)")
    pr.add_argument("name", nargs="?", help="programme name, e.g. office; omit with --list")
    pr.add_argument("--list", action="store_true", help="list the programmes that exist")
    pr.add_argument("--seeds", default="0-9", help="7, 0-99 or 1,4,9")
    pr.add_argument("--out", help="directory to write one brief YAML per seed")
    pr.add_argument("--variations", action="store_true", help="also write each brief's variations (needs --out)")
    pr.add_argument("--dataset", help="write JSONL dataset rows here instead of briefs")
    pr.add_argument("--generator", default="beam", choices=["beam", "cpsat", "treemap", "dual"])
    pr.add_argument("--params", help="JSON dict of generator params")
    pr.add_argument("--per-brief", type=int, default=None, help="cap the rows kept per brief")
    pr.set_defaults(fn=cmd_programme)
    pt = sub.add_parser("planted", help="briefs with a known exact solution, written from a planted placement (E9)")
    pt.add_argument("--family", required=True, choices=["A", "a", "B", "b"], help="A: cut rectangle; B: corridor-served")
    pt.add_argument("--out", required=True, help="directory for <name>.yaml and <name>.planted.json")
    pt.add_argument("--seeds", default="0", help="7, 0-19 or 1,4,9")
    pt.add_argument("--params", help='JSON for the family, e.g. \'{"n": 12, "slicing": false}\' or \'{"rooms": 16, "levels": 2}\'')
    pt.set_defaults(fn=cmd_planted)
    args = ap.parse_args(argv)
    global _stdout
    _stdout = sys.stdout
    with contextlib.redirect_stdout(sys.stderr):
        return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
