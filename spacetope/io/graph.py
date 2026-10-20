"""Graph payloads for the viewer and for persistence: names, kinds, coordinates, index-pair edges."""
from __future__ import annotations

import json
from pathlib import Path

from topologicpy.Dictionary import Dictionary
from topologicpy.Edge import Edge
from topologicpy.Graph import Graph
from topologicpy.Topology import Topology
from topologicpy.Vertex import Vertex

from ..realise import Realised


def realised_graph(r: Realised, wall_nodes: bool = True):
    """topologicpy Graph of the built complex; wall_nodes adds one vertex per shared face."""
    return Graph.ByTopology(r.cc, direct=True, viaSharedTopologies=wall_nodes, silent=True)


def _payload_graph(r: Realised, wall_nodes: bool):
    """names, kinds, coords, edges, vertices through topologicpy.Graph (pre-M9 path, the fallback)."""
    g = realised_graph(r, wall_nodes)
    verts = Graph.Vertices(g)
    coords = [Vertex.Coordinates(v) for v in verts]
    dicts = [Dictionary.PythonDictionary(Topology.Dictionary(v)) for v in verts]
    names, kinds = [], []
    for d in dicts:
        n = d.get("name")
        if n:
            names.append(n); kinds.append("space")
        else:
            names.append(d.get("category", "wall")); kinds.append("wall")
    index = {tuple(round(c, 5) for c in xyz): i for i, xyz in enumerate(coords)}
    edges = []
    for e in Graph.Edges(g):
        a = tuple(round(c, 5) for c in Vertex.Coordinates(Edge.StartVertex(e)))
        b = tuple(round(c, 5) for c in Vertex.Coordinates(Edge.EndVertex(e)))
        if a in index and b in index:
            edges.append([index[a], index[b]])
    return names, kinds, coords, edges, verts


def graph_payload(r: Realised, wall_nodes: bool = True) -> dict:
    from ..tgraph import wall_node_graph
    fast = wall_node_graph(r.cc, wall_nodes)  # PLAN M9: TGraph, several times faster; None -> Graph path
    if fast is not None:
        names, kinds, coords, edges, verts = fast["names"], fast["kinds"], fast["coords"], fast["edges"], fast["names"]
    else:
        names, kinds, coords, edges, verts = _payload_graph(r, wall_nodes)
    dual = r.realised_assembly().space_adjacency()
    return {"order": len(verts), "size": len(edges), "names": names, "kinds": kinds, "coords": coords,
            "edges": edges, "components": len([c for c in _components(dual)]),
            "contacts": [c.to_list() for c in r.realised_contacts()],
            "doors": [d.to_dict() for d in r.doors],
            "signature": list(map(list, r.realised_assembly().signature()))}


def _components(g):
    import networkx as nx
    return nx.connected_components(g)


def save_graph(payload: dict, path: str | Path) -> None:
    Path(path).write_text(json.dumps(payload, indent=1))
