# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Adventurous Systems

import time, threading, math
from topologicpy.Vertex import Vertex
from topologicpy.Cell import Cell
from topologicpy.CellComplex import CellComplex
from topologicpy.Topology import Topology
from topologicpy.Dictionary import Dictionary
from topologicpy.Graph import Graph
from topologicpy.Face import Face
from topologicpy.Wire import Wire
from topologicpy.Edge import Edge

def box(x,y,z,w,l,h,name):
    c = Cell.Prism(origin=Vertex.ByCoordinates(x,y,z), width=w, length=l, height=h, placement="lowerleft")
    Topology.SetDictionary(c, Dictionary.ByKeysValues(["name","type"],[name,"room"]))
    return c

print("=== Dictionary value types")
d = Dictionary.ByKeysValues(["i","f","s","l","b","n","nested","ll"],[1, 2.5, "x", [1,2,3], True, None, {"a":1}, [[1,2],[3,4]]])
print("keys:", Dictionary.Keys(d)); print("py:", Dictionary.PythonDictionary(d))
for k in Dictionary.Keys(d): print("  ",k, repr(Dictionary.ValueAtKey(d,k)))

print("=== analysis helpers on 2 touching cells")
A = box(0,0,0,4,4,3,"A"); B = box(4,0,0,4,4,3,"B")
cc = CellComplex.ByCells([A,B], transferDictionaries=True, silent=True)
cells = Topology.Cells(cc)
st = Topology.SharedTopologies(cells[0], cells[1]); print("SharedTopologies:", type(st).__name__, {k:len(v) for k,v in st.items()} if isinstance(st, dict) else st)
sf = Topology.SharedFaces(cells[0], cells[1]); print("SharedFaces:", len(sf), "area", Face.Area(sf[0]))
adj = Topology.AdjacentTopologies(cells[0], cc, topologyType="cell"); print("AdjacentTopologies(cell in cc):", len(adj), [Dictionary.ValueAtKey(Topology.Dictionary(a),"name") for a in adj])
f = sf[0]; sup = Topology.SuperTopologies(f, cc, topologyType="cell"); print("SuperTopologies(face -> cells):", len(sup))
print("SubTopologies(cell,'face'):", len(Topology.SubTopologies(cells[0], "face")))
print("Centroid:", Vertex.Coordinates(Topology.Centroid(cells[0])), "InternalVertex:", Vertex.Coordinates(Topology.InternalVertex(cells[0])))
print("Vertex.IsInternal (2,2,1) in A:", Vertex.IsInternal(Vertex.ByCoordinates(2,2,1), cells[0]), " (6,2,1) in A:", Vertex.IsInternal(Vertex.ByCoordinates(6,2,1), cells[0]))
print("Vertex.IsInternal (2,2,1) in cc, identify=True:", Vertex.IsInternal(Vertex.ByCoordinates(2,2,1), cc, identify=True))
print("Vertex.EnclosingCells:", [Dictionary.ValueAtKey(Topology.Dictionary(c),"name") for c in Vertex.EnclosingCells(Vertex.ByCoordinates(6,2,1), cc)])
print("Cell.Volume:", Cell.Volume(cells[0]), "Face.Area:", Face.Area(f), "Face.Normal:", Face.Normal(f), "IsCoplanar:", Face.IsCoplanar(f, Topology.Faces(cells[0])[0]))
print("Vertex.Distance v-v:", Vertex.Distance(Vertex.ByCoordinates(0,0,0), Vertex.ByCoordinates(3,4,0)), "v-cell:", Vertex.Distance(Vertex.ByCoordinates(10,2,1), cells[0]))
bb = Topology.BoundingBox(cc); print("BoundingBox type:", Topology.TypeAsString(bb), "dict:", Dictionary.PythonDictionary(Topology.Dictionary(bb)))
dec = CellComplex.Decompose(cc); print("Decompose:", {k:len(v) for k,v in dec.items()})
ext = CellComplex.ExternalBoundary(cc); print("ExternalBoundary:", Topology.TypeAsString(ext), "faces", len(Topology.Faces(ext)))
print("Topology.Type:", Topology.Type(cc), Topology.TypeAsString(cc), "IsInstance:", Topology.IsInstance(cc,"CellComplex"))

print("=== Translate/Rotate/Place keep dicts?")
t = Topology.Translate(A, 10,0,0); print("Translate keeps dict:", Dictionary.Keys(Topology.Dictionary(t)), "centroid", Vertex.Coordinates(Topology.Centroid(t)))
r = Topology.Rotate(A, origin=Vertex.Origin(), axis=[0,0,1], angle=90); print("Rotate keeps dict:", Dictionary.Keys(Topology.Dictionary(r)), "centroid", Vertex.Coordinates(Topology.Centroid(r)))
p = Topology.Place(A, originA=Vertex.Origin(), originB=Vertex.ByCoordinates(5,5,0)); print("Place keeps dict:", Dictionary.Keys(Topology.Dictionary(p)), "centroid", Vertex.Coordinates(Topology.Centroid(p)))
print("Is A mutated by Translate? centroid A:", Vertex.Coordinates(Topology.Centroid(A)))
print("Cell.Box placement bottom centroid:", Vertex.Coordinates(Topology.Centroid(Cell.Box(width=4,length=4,height=3,placement="bottom"))), " lowerleft:", Vertex.Coordinates(Topology.Centroid(Cell.Box(width=4,length=4,height=3,placement="lowerleft"))), " center:", Vertex.Coordinates(Topology.Centroid(Cell.Box(width=4,length=4,height=3))))
print("Cell.Box faces:", len(Topology.Faces(Cell.Box())), "Cell.Box == Prism? types", Topology.TypeAsString(Cell.Box()))

print("=== corridor via Wire/Face/ByThickenedFace; L-shaped")
w = Wire.ByVertices([Vertex.ByCoordinates(0,0,0), Vertex.ByCoordinates(10,0,0), Vertex.ByCoordinates(10,2,0), Vertex.ByCoordinates(2,2,0), Vertex.ByCoordinates(2,8,0), Vertex.ByCoordinates(0,8,0)], close=True)
fc = Face.ByWire(w); corr = Cell.ByThickenedFace(fc, thickness=3, bothSides=False)
print("L corridor:", Topology.TypeAsString(corr), "vol", Cell.Volume(corr), "z-range centroid", Vertex.Coordinates(Topology.Centroid(corr)))
corr2 = Cell.ByThickenedFace(fc, thickness=3, bothSides=False, reverse=True); print("reverse=True centroid z:", Vertex.Z(Topology.Centroid(corr2)))
wr = Wire.Rectangle(origin=Vertex.ByCoordinates(0,0,0), width=4, length=2, placement="lowerleft"); print("Wire.Rectangle lowerleft vertices:", [Vertex.Coordinates(v) for v in Topology.Vertices(wr)])
off = Wire.ByOffset(wr, offset=0.5); print("ByOffset area:", Face.Area(Face.ByWire(off)))
# stair as sloped cell (ByWires loft)
w1 = Wire.Rectangle(origin=Vertex.ByCoordinates(0,0,0), width=3, length=1.2, placement="lowerleft")
w2 = Topology.Translate(w1, 0, 0, 3)
stair = Cell.ByWires([w1, w2]); print("Cell.ByWires stair:", Topology.TypeAsString(stair), "faces", len(Topology.Faces(stair)))
# Cell.ByFaces from 6 faces
faces = Topology.Faces(Cell.Box()); c6 = Cell.ByFaces(faces); print("Cell.ByFaces:", Topology.TypeAsString(c6))

print("=== perf 200 + 2 floors")
for n, floors in [(100,2),(196,1)]:
    side = int(math.sqrt(n//floors))
    cells=[box(i*4,j*4,k*3,4,4,3,f"r{i}_{j}_{k}") for i in range(side) for j in range(side) for k in range(floors)]
    t=time.time(); cc=CellComplex.ByCells(cells, transferDictionaries=True, silent=True); t1=time.time()-t
    t=time.time(); g=Graph.ByTopology(cc, direct=True); t2=time.time()-t
    t=time.time(); cc_nt=CellComplex.ByCells(cells, transferDictionaries=False, silent=True); t3=time.time()-t
    print(f"n={len(cells)} floors={floors}: ByCells(transfer) {t1:.2f}s, ByCells(no transfer) {t3:.2f}s, ByTopology {t2:.2f}s, cells={len(Topology.Cells(cc))} gv={len(Graph.Vertices(g))} ge={len(Graph.Edges(g))}")
    t=time.time(); js=Topology.JSONString(cc); print(f"   JSONString {time.time()-t:.2f}s len {len(js)}")
    t=time.time(); geo=Topology.Geometry(cc); print(f"   Geometry {time.time()-t:.2f}s nv {len(geo['vertices'])} nf {len(geo['faces'])}")
    t=time.time(); vs=Graph.Vertices(g); p=Graph.ShortestPath(g, vs[0], vs[-1]); print(f"   ShortestPath {time.time()-t:.2f}s edges {len(Topology.Edges(p)) if p else None}")

print("=== threads smoke test")
errs=[]
def work(k):
    try:
        cells=[box(i*4,j*4,0,4,4,3,f"t{k}_{i}_{j}") for i in range(4) for j in range(4)]
        cc=CellComplex.ByCells(cells, silent=True); g=Graph.ByTopology(cc)
        assert len(Graph.Vertices(g))==16
    except Exception as e: errs.append(repr(e))
t=time.time(); ths=[threading.Thread(target=work,args=(k,)) for k in range(4)]; [x.start() for x in ths]; [x.join() for x in ths]
print("4 threads done in", round(time.time()-t,2), "s errors:", errs)
t=time.time(); [work(k) for k in range(4)]; print("4 sequential in", round(time.time()-t,2), "s")
