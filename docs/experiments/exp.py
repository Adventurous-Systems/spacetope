# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Adventurous Systems

import time, pickle, copy, json
from topologicpy.Vertex import Vertex
from topologicpy.Cell import Cell
from topologicpy.CellComplex import CellComplex
from topologicpy.Topology import Topology
from topologicpy.Dictionary import Dictionary
from topologicpy.Graph import Graph
from topologicpy.Face import Face
from topologicpy.Cluster import Cluster

def box(x,y,z,w,l,h,name):
    c = Cell.Prism(origin=Vertex.ByCoordinates(x,y,z), width=w, length=l, height=h, placement="lowerleft")
    Topology.SetDictionary(c, Dictionary.ByKeysValues(["name","type"],[name,"room"]))
    return c

def report(label, cells, tol=0.0001):
    cc = CellComplex.ByCells(cells, transferDictionaries=True, tolerance=tol)
    if cc is None:
        print(f"[{label}] ByCells returned None"); return None
    print(f"[{label}] type={Topology.TypeAsString(cc)} cells={len(Topology.Cells(cc))} faces={len(Topology.Faces(cc))} internalFaces={len(CellComplex.InternalFaces(cc))} externalFaces={len(CellComplex.ExternalFaces(cc))} nonManifold={len(CellComplex.NonManifoldFaces(cc))}")
    names=[Dictionary.ValueAtKey(Topology.Dictionary(c),"name") for c in Topology.Cells(cc)]
    print("   cell dict names:", names)
    return cc

# 1. exact touching
A = box(0,0,0,4,4,3,"A"); B = box(4,0,0,4,4,3,"B")
cc = report("touch exact", [A,B])
g = Graph.ByTopology(cc, direct=True, toExteriorTopologies=False)
print("   graph vertices:", len(Graph.Vertices(g)), "edges:", len(Graph.Edges(g)))
for v in Graph.Vertices(g):
    d = Topology.Dictionary(v); print("   gv:", Dictionary.Keys(d), [Dictionary.ValueAtKey(d,k) for k in Dictionary.Keys(d)])
# faces of cc dicts?
for f in CellComplex.InternalFaces(cc):
    print("   internal face dict keys:", Dictionary.Keys(Topology.Dictionary(f)))

# 2. mismatched 4.0 vs 4.05
A = box(0,0,0,4,4,3,"A"); B = box(4.05,0,0,4,4,3,"B")
cc = report("gap 0.05", [A,B])
if cc is not None:
    print("   result type:", Topology.TypeAsString(cc))
A = box(0,0,0,4,4,3,"A"); B = box(4.05,0,0,4,4,3,"B")
cc = report("gap 0.05 tol=0.1", [A,B], tol=0.1)

# 3. overlap 0.05
A = box(0,0,0,4,4,3,"A"); B = box(3.95,0,0,4,4,3,"B")
cc = report("overlap 0.05", [A,B])

# 4. partial face share: small cell abuts big face
A = box(0,0,0,8,4,3,"big"); B = box(8,1,0,3,2,3,"small")
cc = report("partial abut", [A,B])
if cc:
    for f in Topology.Faces(cc):
        print("   face area", Face.Area(f))
    g = Graph.ByTopology(cc, direct=True)
    print("   graph edges:", len(Graph.Edges(g)))

# 5. Tiny 1e-6 mismatch
A = box(0,0,0,4,4,3,"A"); B = box(4.000001,0,0,4,4,3,"B")
cc = report("gap 1e-6", [A,B])

# 6. gap 0.5 (corridor gap) -> what happens
A = box(0,0,0,4,4,3,"A"); B = box(4.5,0,0,4,4,3,"B")
cc = report("gap 0.5", [A,B])

# 7. stacking floors
A = box(0,0,0,4,4,3,"A"); B = box(0,0,3,4,4,3,"B")
cc = report("stacked", [A,B])

# 8. Dictionary w/o transferDictionaries
A = box(0,0,0,4,4,3,"A"); B = box(4,0,0,4,4,3,"B")
cc = CellComplex.ByCells([A,B])
print("[no transfer] names:", [Dictionary.Keys(Topology.Dictionary(c)) for c in Topology.Cells(cc)])

# 9. Pickle / copy
A = box(0,0,0,4,4,3,"A")
try:
    pickle.dumps(A); print("pickle OK")
except Exception as e: print("pickle FAILS:", type(e).__name__, e)
try:
    copy.deepcopy(A); print("deepcopy OK")
except Exception as e: print("deepcopy FAILS:", type(e).__name__, e)
s = Topology.BREPString(A); print("BREPString len", len(s), "roundtrip type:", Topology.TypeAsString(Topology.ByBREPString(s)))
js = Topology.JSONString([A]); print("JSONString len", len(js)); print(js[:600])
# geometry
geo = Topology.Geometry(A); print("Geometry keys:", geo.keys(), "nv", len(geo["vertices"]), "nf", len(geo["faces"]), "faces sample", geo["faces"][:2], "edges sample", geo["edges"][:2])

# 10. Perf: grid of N cells
for n in [25, 100]:
    import math
    side = int(math.sqrt(n))
    cells=[box(i*4,j*4,0,4,4,3,f"r{i}_{j}") for i in range(side) for j in range(side)]
    t=time.time(); cc=CellComplex.ByCells(cells, transferDictionaries=True); t1=time.time()-t
    t=time.time(); g=Graph.ByTopology(cc, direct=True); t2=time.time()-t
    print(f"perf n={len(cells)}: ByCells {t1:.2f}s, ByTopology {t2:.2f}s, cells={len(Topology.Cells(cc))} gv={len(Graph.Vertices(g))} ge={len(Graph.Edges(g))}")
    t=time.time(); adj=Graph.AdjacencyMatrix(g); print(f"   AdjacencyMatrix {time.time()-t:.2f}s size {len(adj)}")
    t=time.time(); nx=Graph.NetworkXGraph(g); print(f"   NetworkX {time.time()-t:.2f}s nodes {nx.number_of_nodes()}")
