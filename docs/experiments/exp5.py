# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Adventurous Systems

import json, sys
import topologicpy; print("VERSION", topologicpy.__version__, topologicpy.__file__)
from topologicpy.Vertex import Vertex
from topologicpy.Cell import Cell
from topologicpy.CellComplex import CellComplex
from topologicpy.Topology import Topology
from topologicpy.Dictionary import Dictionary
from topologicpy.Face import Face
from topologicpy.Graph import Graph
def box(x,y,z,w,l,h,name):
    c = Cell.Prism(origin=Vertex.ByCoordinates(x,y,z), width=w, length=l, height=h, placement="lowerleft")
    Topology.SetDictionary(c, Dictionary.ByKeysValues(["name","type"],[name,"room"]))
    return c
def main():
    A = box(0,0,0,4,4,3,"A")
    js = Topology.JSONString(A); b = Topology.ByJSONString(js); b = b[0] if isinstance(b, list) else b
    print("single cell roundtrip dict:", Dictionary.PythonDictionary(Topology.Dictionary(b)))
    rooms = [box(0,0,0,4,4,3,"R1"), box(4,0,0,4,4,3,"R2"), box(0,4,0,8,2,3,"Corr")]
    cc = CellComplex.ByCells(rooms, transferDictionaries=True, silent=True)
    Topology.SetDictionary(cc, Dictionary.ByKeysValues(["building"],["B1"]))
    # face dicts
    for i,f in enumerate(CellComplex.InternalFaces(cc)):
        Topology.SetDictionary(f, Dictionary.ByKeysValues(["wall"],[f"w{i}"]))
    doors=[]
    for f in CellComplex.InternalFaces(cc):
        c = Topology.Centroid(f)
        if abs(Vertex.Y(c)-4)<1e-6:
            d = Face.Rectangle(origin=Vertex.ByCoordinates(Vertex.X(c), 4, 1.05), width=0.9, length=2.1, direction=[0,1,0])
            Topology.SetDictionary(d, Dictionary.ByKeysValues(["name"],[f"door_{round(Vertex.X(c),1)}"])); doors.append(d)
    cc = Topology.AddApertures(cc, doors, subTopologyType="face")
    print("before: cc dict", Dictionary.PythonDictionary(Topology.Dictionary(cc)), "cells", [Dictionary.ValueAtKey(Topology.Dictionary(c),"name") for c in Topology.Cells(cc)], "face dicts", [Dictionary.ValueAtKey(Topology.Dictionary(f),"wall") for f in Topology.Faces(cc) if Dictionary.ValueAtKey(Topology.Dictionary(f),"wall")], "apertures", [Dictionary.ValueAtKey(Topology.Dictionary(a),"name") for a in Topology.Apertures(cc, subTopologyType="face")])
    js = Topology.JSONString(cc)
    b = Topology.ByJSONString(js); b = b[0] if isinstance(b, list) else b
    print("after JSON: type", Topology.TypeAsString(b), "cc dict", Dictionary.PythonDictionary(Topology.Dictionary(b)) if Topology.Dictionary(b) else None)
    print("  cells", [Dictionary.PythonDictionary(Topology.Dictionary(c)) for c in Topology.Cells(b)])
    print("  face dicts", [Dictionary.ValueAtKey(Topology.Dictionary(f),"wall") for f in Topology.Faces(b) if Dictionary.ValueAtKey(Topology.Dictionary(f),"wall")])
    aps = Topology.Apertures(b, subTopologyType="face"); print("  apertures", len(aps), [Dictionary.ValueAtKey(Topology.Dictionary(a),"name") for a in aps])
    # does graph survive?
    g = Graph.ByTopology(b, direct=True); print("  graph on restored: v", len(Graph.Vertices(g)), "e", len(Graph.Edges(g)))
    # Alternative: BREP + separate dictionary sidecar via TransferDictionariesBySelectors
    selectors=[]
    for c in Topology.Cells(cc):
        v = Topology.InternalVertex(c); Topology.SetDictionary(v, Topology.Dictionary(c)); selectors.append(v)
    b2 = Topology.ByBREPString(Topology.BREPString(cc))
    b2 = Topology.TransferDictionariesBySelectors(b2, selectors, tranCells=True, numWorkers=1)
    print("BREP + selectors: cells", [Dictionary.ValueAtKey(Topology.Dictionary(c),"name") for c in Topology.Cells(b2)])
if __name__ == "__main__":
    main()
