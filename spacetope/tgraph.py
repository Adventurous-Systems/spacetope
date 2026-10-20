"""Adapter for topologicpy's TGraph: the only module in spacetope that imports it (PLAN M9).

TGraph builds the same graphs as `topologicpy.Graph` from a built complex several times faster and hands back
plain dictionaries. Everything here degrades to `None` when TGraph is missing or a call fails, so callers keep
their `Graph` path as the fallback. The search layer never imports this module.
"""
from __future__ import annotations

from typing import Any

try:  # pragma: no cover - import guard
    from topologicpy.TGraph import TGraph
    AVAILABLE = True
except Exception:  # noqa: BLE001
    TGraph = None
    AVAILABLE = False


def _vertices(g) -> list[dict]:
    return [v for v in (TGraph.Vertices(g) or []) if v.get("active", True)]


def _edges(g) -> list[dict]:
    return [e for e in (TGraph.Edges(g) or []) if e.get("active", True)]


def wall_node_graph(cc, wall_nodes: bool = True) -> dict[str, Any] | None:
    """Realised graph of a complex: one vertex per cell (named) and, with wall_nodes, one per shared face."""
    if not AVAILABLE:
        return None
    try:
        g = TGraph.ByTopology(cc, direct=True, viaSharedTopologies=wall_nodes, silent=True)
        verts = _vertices(g)
        index = {v["index"]: i for i, v in enumerate(verts)}
        names, kinds, coords = [], [], []
        for v in verts:
            d = v.get("dictionary") or {}
            n = d.get("name")
            names.append(n if n else "wall")
            kinds.append("space" if n else "wall")
            coords.append([float(d.get("x", 0.0)), float(d.get("y", 0.0)), float(d.get("z", 0.0))])
        edges = [[index[e["src"]], index[e["dst"]]] for e in _edges(g) if e["src"] in index and e["dst"] in index]
        return {"order": len(verts), "size": len(edges), "names": names, "kinds": kinds, "coords": coords, "edges": edges}
    except Exception:  # noqa: BLE001
        return None


def door_pairs(cc) -> set[frozenset[str]] | None:
    """Pairs of spaces joined by a door aperture, read from the kernel (cells linked through apertures)."""
    if not AVAILABLE:
        return None
    try:
        g = TGraph.ByTopology(cc, direct=False, directApertures=True, silent=True)
        name = {v["index"]: (v.get("dictionary") or {}).get("name") for v in _vertices(g)}
        out = set()
        for e in _edges(g):
            a, b = name.get(e["src"]), name.get(e["dst"])
            if a and b:
                out.add(frozenset((a, b)))
        return out
    except Exception:  # noqa: BLE001
        return None


def from_networkx(g, id_key: str = "id"):
    """A TGraph from a networkx graph whose nodes carry `id_key`; node attributes become vertex dictionaries."""
    if not AVAILABLE:
        return None
    return TGraph.ByNetworkXGraph(g, vertexID=id_key)


def export_csv(graphs: list, path: str, node_features: list[str] | None = None, graph_label_key: str = "label") -> bool:
    """PyG-ready folder (graphs.csv, nodes.csv, edges.csv, meta.yaml) from a list of TGraphs."""
    if not AVAILABLE or not graphs:
        return False
    ok = TGraph.ExportToCSV(graphs, str(path), graphLabelKey=graph_label_key, nodeFeaturesKeys=node_features,
                            overwrite=True, silent=True)
    return bool(ok)


def set_graph_dictionary(g, d: dict) -> None:
    TGraph.SetDictionary(g, d)
