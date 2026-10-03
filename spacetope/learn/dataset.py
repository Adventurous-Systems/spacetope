"""M6 dataset: one JSON line per verified option. Enough to re-realise and re-verify every row
from stored coordinates (integrity), and to train proposal models on brief graph -> relations."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from ..brief import Brief
from ..pipeline import Option
from ..placement import assembly_from_placement
from ..solve.grid import Box
from ..verify import verify


def option_row(brief: Brief, option: Option) -> dict:
    return {
        "brief": brief.to_dict(),
        "brief_graph": {"nodes": [{"name": s.name, "program": s.program, "w": s.w, "l": s.l, "h": s.h} for s in brief.spaces],
                        "required": [list(c) for c in brief.contacts]},
        "generator": option.generator,
        "seed": option.seed,
        "signature": [list(s) for s in option.signature],
        "placement": {n: b.to_dict() for n, b in option.placement.items()},
        "scores": option.scores,
    }


def write_rows(rows: Iterable[dict], path: str | Path) -> int:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with path.open("a") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
            n += 1
    return n


def read_rows(path: str | Path) -> list[dict]:
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


def check_row(row: dict) -> tuple[bool, str]:
    """Re-realise and re-verify a stored row; its signature must be unchanged."""
    brief = Brief.from_dict(row["brief"])
    placement = {n: Box.from_dict(b) for n, b in row["placement"].items()}
    intent = assembly_from_placement(brief, placement)
    sig = [list(s) for s in intent.signature()]
    if sig != row["signature"]:
        return False, "signature changed"
    rep = verify(brief, placement, intent)
    if not rep.ok:
        return False, json.dumps({k: d for k, (p, d) in rep.checks.items() if not p})
    return True, "ok"


PROGRAM_INDEX = {"room": 0, "corridor": 1, "stair": 2, "elevator": 3, "void": 4}
NODE_FEATURES = ["w", "l", "h", "prog", "z", "nominal_w", "nominal_l"]


def export_pyg(brief: Brief, options: list[Option], path: str | Path) -> dict:
    """PyG-ready CSV folder (graphs.csv, nodes.csv, edges.csv, meta.yaml) with one graph per verified option, through
    topologicpy's TGraph exporter (PLAN M9). Nodes are spaces with realised and nominal sizes, edges are shared
    walls, the graph label is the option's topology class. Returns counts; {} when TGraph is unavailable."""
    from .. import tgraph
    from ..pipeline import space_graph, topology_classes
    ok = [o for o in options if o.ok]
    if not tgraph.AVAILABLE or not ok:
        return {}
    expanded = ok[0].realised.brief if ok[0].realised is not None else brief
    classes = topology_classes(expanded, [o.placement for o in ok])
    graphs, n_nodes, n_edges = [], 0, 0
    for o, cls in zip(ok, classes):
        g = space_graph(expanded, o.placement)
        for name in g.nodes:
            s, b = expanded.space(name), o.placement[name].to_m()
            g.nodes[name].update({"id": name, "w": b["w"], "l": b["l"], "h": b["h"], "z": b["z"], "x": b["x"] + b["w"] / 2,
                                  "y": b["y"] + b["l"] / 2, "prog": PROGRAM_INDEX.get(s.program, 0), "label": PROGRAM_INDEX.get(s.program, 0),
                                  "nominal_w": s.w, "nominal_l": s.l})
        t = tgraph.from_networkx(g, "id")
        tgraph.set_graph_dictionary(t, {"label": int(cls), "generator": o.generator, "seed": int(o.seed)})
        graphs.append(t); n_nodes += g.number_of_nodes(); n_edges += g.number_of_edges()
    done = tgraph.export_csv(graphs, str(path), node_features=NODE_FEATURES)
    return {"graphs": len(graphs), "nodes": n_nodes, "edges": n_edges, "classes": len(set(classes)), "written": done}
