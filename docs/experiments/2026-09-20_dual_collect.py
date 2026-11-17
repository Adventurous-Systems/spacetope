# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Adventurous Systems

"""Collect distinct rectangular-dual options per brief across triangulation seeds, verified by spacetope.verify."""
import json, sys, time
# run from the repo root with the project venv: .venv/bin/python docs/experiments/2026-09-20_dual_collect.py fixtures/eight_rooms_corridor.yaml
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))  # dual_proto.py sits next to this file
import networkx as nx
import importlib.util as _u; _s = _u.spec_from_file_location("dual_proto", __import__("pathlib").Path(__file__).with_name("2026-09-20_dual_proto.py")); dp = _u.module_from_spec(_s); _s.loader.exec_module(dp)
from spacetope.brief import load
from spacetope.circulation import prepare
from spacetope.doors import required_overlap_mm
from spacetope.solve.grid import Box, touches
from spacetope.verify import verify

def signature(boxes):
    names = sorted(boxes); sig = set()
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            for side in ("+x", "-x", "+y", "-y"):
                if touches(boxes[a], boxes[b], side)[0] > 0: sig.add((a, side, b))
    return frozenset(sig)

def collect(path, seeds=120, keep=8, cap=12):
    brief, _ = prepare(load(path))
    H = int(round(brief.level_height * 1000)) if brief.level_height else max(s.nominal_mm("h") for s in brief.spaces)
    G = nx.Graph(); G.add_nodes_from(s.name for s in brief.spaces); G.add_edges_from(brief.contacts)
    through = {s.name for s in brief.spaces if s.program == "corridor"}
    bands = {s.name: (s.band("w"), s.band("l")) for s in brief.spaces}
    stats = {"seeds": 0, "clean": 0, "rels": 0, "dimensioned": 0, "verified": 0, "distinct": 0, "t": 0.0}
    seen, options = set(), []
    t0 = time.perf_counter()
    for s_ in range(seeds):
        stats["seeds"] += 1
        try:
            Gp, emb, outer, added, arcs, sep, voids = dp.make_ptp(G, s_, through=through)
        except Exception:
            continue
        if sep: continue
        stats["clean"] += 1
        rels, ccw = dp.enumerate_rels(Gp, emb, cap, s_)
        stats["rels"] += len(rels)
        b2 = dict(bands)
        for v in voids: b2[v] = ((1, 100_000), (1, 100_000))
        need = {}
        for a, b in Gp.edges():
            if a in dp.OUTER or b in dp.OUTER: continue
            need[frozenset((a, b))] = 1 if (a in voids or b in voids) else required_overlap_mm(brief, a, b)
        for rel in rels:
            dim = dp.dimension(Gp, emb, rel, ccw, b2, need)
            if not dim: continue
            stats["dimensioned"] += 1
            boxes = {v: Box(x, y, 0, w, l, H) for v, (x, y, w, l) in dim.items() if v not in voids}
            sig = signature(boxes)
            if sig in seen: continue
            rep = verify(brief, boxes)
            if not rep.ok: continue
            stats["verified"] += 1
            seen.add(sig); stats["distinct"] += 1
            r = rep.realised
            from spacetope.score import score
            options.append({"seed": s_, "boxes": {v: b.to_m() for v, b in boxes.items()},
                            "voids": {v: [x / 1000, y / 1000, w / 1000, l / 1000] for v, (x, y, w, l) in dim.items() if v in voids},
                            "labelling": {f"{u}>{v}": c for (u, v), c in rel.items()},
                            "added_edges": [list(e) for e in added], "arcs": arcs,
                            "contacts": [c.to_list() for c in r.realised_contacts()], "doors": [d.to_dict() for d in r.doors],
                            "scores": score(r)})
            if len(options) >= keep: break
        if len(options) >= keep: break
    stats["t"] = round(time.perf_counter() - t0, 2)
    return {"brief": brief.to_dict(), "stats": stats, "options": options,
            "wish_edges": [list(e) for e in brief.contacts]}

out = {}
for path in sys.argv[1:]:
    r = collect(path)
    out[r["brief"]["name"]] = r
    print(json.dumps({"brief": r["brief"]["name"], **r["stats"]}), flush=True)
json.dump(out, open("dual_options.json", "w"))
