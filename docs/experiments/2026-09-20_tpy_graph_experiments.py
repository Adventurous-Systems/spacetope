"""[RUN] experiments: which topologicpy 0.9.57 graph algorithms work on spacetope's realised complexes and graphs."""
import json, time, sys, os, traceback
import networkx as nx
S = "/private/tmp/claude-501/-Users-arlav-GitHub-spacetope/0f6934eb-8b32-4d75-9f92-754cbdad4672/scratchpad"
from topologicpy.Graph import Graph
from topologicpy.TGraph import TGraph
from topologicpy.Topology import Topology
from topologicpy.Dictionary import Dictionary
from spacetope.io.brep import load
from spacetope.doors import door_graph
def step(name, fn):
    t = time.perf_counter()
    try: out = fn(); print(f"[{name}] ok {time.perf_counter() - t:.3f}s ->", out, flush=True)
    except Exception as ex: print(f"[{name}] FAIL {type(ex).__name__}: {str(ex)[:160]}", flush=True)
r = load(f"{S}/tls/option_00"); cc = r.cc
print("complex:", r.n_cells, "cells,", len(r.doors), "doors")
# b. realised graph: Graph vs TGraph
step("Graph.ByTopology shared", lambda: (lambda g: (Graph.Order(g), Graph.Size(g)))(Graph.ByTopology(cc, direct=True, viaSharedTopologies=True, silent=True)))
tg_holder = {}
def tg_build():
    g = TGraph.ByTopology(cc, direct=True, viaSharedTopologies=True, silent=True); tg_holder["g"] = g
    return (len(TGraph.Vertices(g)), len(TGraph.Edges(g)))
step("TGraph.ByTopology shared", tg_build)
# c. access graph through apertures (doors)
ag = {}
def access():
    g = TGraph.AccessGraph(cc, viaSharedApertures=True, silent=True) if "silent" in TGraph.AccessGraph.__code__.co_varnames else TGraph.AccessGraph(cc, viaSharedApertures=True)
    ag["g"] = g
    ours = door_graph(r.brief, r.doors)
    return {"tgraph": (len(TGraph.Vertices(g)), len(TGraph.Edges(g))), "spacetope door graph": (ours.number_of_nodes(), ours.number_of_edges())}
step("TGraph.AccessGraph via apertures", access)
# d. space syntax on the door graph (networkx -> TGraph)
def syntax():
    ours = door_graph(r.brief, r.doors)
    for n in ours.nodes: ours.nodes[n]["id"] = n; ours.nodes[n]["program"] = r.brief.space(n).program
    g = TGraph.ByNetworkXGraph(ours, vertexID="id"); ag["door_tg"] = g
    integ = TGraph.Integration(g, silent=True)
    vs = TGraph.Vertices(g)
    names = [TGraph.VertexDictionary(g, i).get("id") if isinstance(TGraph.VertexDictionary(g, i), dict) else None for i in range(len(vs))]
    top = sorted(zip(integ, names), reverse=True)[:3]
    btw = TGraph.BetweennessCentrality(g, silent=True)
    return {"integration top3": top, "betweenness max": max(btw) if btw else None, "cut vertices": len(TGraph.CutVertices(g)), "bridges": len(TGraph.Bridges(g))}
step("Integration / Betweenness / CutVertices on the door graph", syntax)
# e. option similarity: WL kernel and isomorphism between beam options of eight_rooms
ex = json.load(open(f"{S}/explainer_data.json"))["eight_rooms_corridor:beam"]
def opt_graph(o):
    g = nx.Graph()
    for n in o["boxes"]: g.add_node(n, id=n, program=("corridor" if n == "corridor" else "room"))
    for a, sa, b, sb in o["contacts"]: g.add_edge(a, b)
    return TGraph.ByNetworkXGraph(g, vertexID="id")
def similar():
    gs = [opt_graph(o) for o in ex["options"][:4]]
    k = [[TGraph.WLKernel(gs[i], gs[j], labelKey="program", silent=True) for j in range(4)] for i in range(4)]
    iso = [[TGraph.IsIsomorphic(gs[i], gs[j], silent=True) for j in range(4)] for i in range(4)]
    return {"WL kernel row0": [round(x, 3) if x is not None else None for x in k[0]], "isomorphic row0": iso[0]}
step("WLKernel / IsIsomorphic between options", similar)
# f. pattern matching: corridor + two rooms that also touch each other (a wish triangle)
def match():
    pat = nx.Graph(); pat.add_node("c", id="c", program="corridor"); pat.add_node("a", id="a", program="room"); pat.add_node("b", id="b", program="room")
    pat.add_edges_from([("c", "a"), ("c", "b"), ("a", "b")])
    P = TGraph.ByNetworkXGraph(pat, vertexID="id"); T = opt_graph(ex["options"][0])
    m = TGraph.Match(P, T, vertexKeys=["program"], maxMatches=200, silent=True)
    return {"matches": len(m), "first": m[0] if m else None}
step("TGraph.Match wish-triangle pattern", match)
# i. PyG-ready CSV export
def csv():
    path = f"{S}/tg_csv"; g = opt_graph(ex["options"][0])
    TGraph.ExportToCSV(g, path, overwrite=True) if "overwrite" in TGraph.ExportToCSV.__code__.co_varnames else TGraph.ExportToCSV(g, path)
    return sorted(os.listdir(path))
step("TGraph.ExportToCSV (PyG-ready)", csv)
# h. straight skeleton of an L-shaped envelope as a corridor spine
def skeleton():
    from topologicpy.Face import Face; from topologicpy.Wire import Wire; from topologicpy.Vertex import Vertex
    pts = [(0,0),(30,0),(30,12),(14,12),(14,26),(0,26)]
    f = Face.ByWire(Wire.ByVertices([Vertex.ByCoordinates(x, y, 0) for x, y in pts], close=True))
    sk = Face.Skeleton(f); ma = Face.MedialAxis(f)
    return {"skeleton edges": len(Topology.Edges(sk)) if sk else None, "medial axis edges": len(Topology.Edges(ma)) if ma else None}
step("Face.Skeleton / MedialAxis on an L-shaped envelope", skeleton)
# j. shape grammar: one rule (slice a box by a plane) applied to a cell
def grammar():
    from topologicpy.ShapeGrammar import ShapeGrammar
    import inspect
    sg = ShapeGrammar()
    return {"AddRule": str(inspect.signature(sg.AddRule))[:200], "ApplyRule": str(inspect.signature(sg.ApplyRule))[:160]}
step("ShapeGrammar signatures", grammar)
