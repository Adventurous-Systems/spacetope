"""spacetope CLI. M1: realise a placement, verify, score, render."""
from __future__ import annotations

import argparse
import json
import sys

from .brief import load
from .placement import load_placement


def cmd_realise(args) -> int:
    from .score import score
    from .verify import verify
    from .circulation import BriefInvalid, prepare
    try:
        brief, _ = prepare(load(args.brief))  # the placement names the expanded spaces (review 2026-09-13, #10)
    except BriefInvalid as e:
        print(json.dumps({"invalid_brief": [p.to_dict() for p in e.problems]}, indent=1))
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
    print(json.dumps(out, indent=1))
    return 0 if rep.ok else 1


def cmd_generate(args) -> int:
    """Generate, verify, score and rank options; write a JSON index plus optional HTML/BREP per option."""
    from pathlib import Path
    from .pipeline import generate, rank
    from .solve.registry import GENERATORS
    from .circulation import BriefInvalid
    from .solve.registry import GeneratorUnsupported
    brief = load(args.brief)
    params = json.loads(args.params) if args.params else None
    try:
        options, t_gen, t_real = generate(GENERATORS[args.generator], brief, args.seed, params, args.generator)
    except (GeneratorUnsupported, BriefInvalid) as e:
        print(json.dumps({"error": str(e)}, indent=1))
        return 2
    ranked = rank(options)
    out_dir = Path(args.out) if args.out else None
    index = {"brief": brief.name, "generator": args.generator, "seed": args.seed, "t_gen": round(t_gen, 3),
             "t_realise": round(t_real, 3), "options": []}
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
    print(json.dumps({"brief": brief.name, "generator": args.generator, "seed": args.seed, "t_gen": index["t_gen"],
                      "t_realise": index["t_realise"], "options": summary, "out": str(out_dir) if out_dir else None}, indent=1))
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
    print(json.dumps(out, indent=1))
    return 0 if b.feasible and any(c["verified"] for c in out["candidates"]) else 1


def cmd_export(args) -> int:
    """OBJ and/or JSON of a realised complex, from a saved option stem or from a brief + placement."""
    from .io.mesh import write_json, write_obj
    if args.stem:
        from .io.brep import load as load_realised
        r = load_realised(args.stem)
    else:
        if not (args.brief and args.placement):
            print(json.dumps({"error": "give --stem, or --brief and --placement"})); return 2
        from .circulation import BriefInvalid, prepare
        try:
            brief, _ = prepare(load(args.brief))
        except BriefInvalid as e:
            print(json.dumps({"invalid_brief": [p.to_dict() for p in e.problems]}, indent=1)); return 2
        from .realise import realise
        r = realise(brief, load_placement(args.placement))
    out = {}
    if args.obj:
        out["obj"] = str(write_obj(r, args.obj))
    if args.json:
        out["json"] = str(write_json(r, args.json))
    if not out:
        print(json.dumps({"error": "give --obj and/or --json"})); return 2
    print(json.dumps({"brief": r.brief.name, "cells": r.n_cells, "doors": len(r.doors), **out}, indent=1))
    return 0


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
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
