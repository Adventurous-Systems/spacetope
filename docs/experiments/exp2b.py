import json, os, tempfile
from topologicpy.Vertex import Vertex
from topologicpy.Cell import Cell
from topologicpy.CellComplex import CellComplex
from topologicpy.Cluster import Cluster
from topologicpy.Topology import Topology
from topologicpy.Dictionary import Dictionary
from topologicpy.Graph import Graph
from topologicpy.Face import Face
from topologicpy.Wire import Wire
from topologicpy.Aperture import Aperture
from topologicpy.Context import Context

def box(x,y,z,w,l,h,name):
    c = Cell.Prism(origin=Vertex.ByCoordinates(x,y,z), width=w, length=l, height=h, placement="lowerleft")
    Topology.SetDictionary(c, Dictionary.ByKeysValues(["name","type"],[name,"room"]))
    return c


def main():
    print("=== touching via Merge / SelfMerge")
    A = box(0,0,0,4,4,3,"A"); B = box(4,0,0,4,4,3,"B")
    m = Topology.Merge(A,B, tranDict=False); print("Merge touching ->", Topology.TypeAsString(m), [Dictionary.ValueAtKey(Topology.Dictionary(c),"name") for c in Topology.Cells(m)])
    sm = Topology.SelfMerge(Cluster.ByTopologies([A,B]), transferDictionaries=True); print("SelfMerge touching ->", Topology.TypeAsString(sm), [Dictionary.Keys(Topology.Dictionary(c)) for c in Topology.Cells(sm)])
    u = Topology.Union(A,B); print("Union touching ->", Topology.TypeAsString(u), "cells", len(Topology.Cells(u)))
    
    print("=== 3 rooms + corridor, graph modes")
    rooms = [box(0,0,0,4,4,3,"R1"), box(4,0,0,4,4,3,"R2"), box(8,0,0,4,4,3,"R3"), box(0,4,0,12,2,3,"Corr")]
    cc = CellComplex.ByCells(rooms, transferDictionaries=True, silent=True)
    for kw in [dict(direct=True), dict(direct=False, viaSharedTopologies=True), dict(direct=True, toExteriorTopologies=True), dict(direct=True, useInternalVertex=True, storeBREP=True)]:
        g = Graph.ByTopology(cc, **kw)
        vs = Graph.Vertices(g)
        cats = [Dictionary.ValueAtKey(Topology.Dictionary(v),"category") for v in vs]
        print(kw, "-> v", len(vs), "e", len(Graph.Edges(g)), "categories", sorted(set(cats)), "keys of v0", Dictionary.Keys(Topology.Dictionary(vs[0])))
        if kw.get("storeBREP"):
            print("  brep key length:", len(str(Dictionary.ValueAtKey(Topology.Dictionary(vs[0]),"brep"))))
    
    print("=== Apertures (doors)")
    cc = CellComplex.ByCells(rooms, transferDictionaries=True, silent=True)
    internal = CellComplex.InternalFaces(cc)
    print("internal faces:", len(internal))
    # door on the face between R1 and Corr: face at y=4 for x in 0..4
    doors=[]
    for f in internal:
        c = Topology.Centroid(f)
        print("  internal face centroid", Vertex.Coordinates(c), "normal", Face.Normal(f))
        if abs(Vertex.Y(c)-4)<1e-6:
            d = Face.Rectangle(origin=Vertex.ByCoordinates(Vertex.X(c), 4, 1.05), width=0.9, length=2.1, direction=[0,1,0])
            Topology.SetDictionary(d, Dictionary.ByKeysValues(["type","name"],["door", f"door_{round(Vertex.X(c),1)}"]))
            doors.append(d)
    print("doors:", len(doors))
    cc2 = Topology.AddApertures(cc, doors, subTopologyType="face")
    print("apertures on cc:", len(Topology.Apertures(cc2)), "faces with apertures:", len(Topology.Apertures(cc2, subTopologyType="face")))
    ap = Topology.Apertures(cc2)[0]; print("aperture object type:", Topology.TypeAsString(ap), type(ap))
    for kw in [dict(direct=False, directApertures=True), dict(direct=False, viaSharedApertures=True), dict(direct=False, viaSharedApertures=True, toExteriorApertures=True)]:
        g = Graph.ByTopology(cc2, **kw)
        vs = Graph.Vertices(g)
        cats = [Dictionary.ValueAtKey(Topology.Dictionary(v),"category") for v in vs]
        names = [Dictionary.ValueAtKey(Topology.Dictionary(v),"name") for v in vs]
        print(kw, "-> v", len(vs), "e", len(Graph.Edges(g)), "cats", cats, "names", names)
    
    print("=== manual Aperture.ByTopologyContext")
    f = internal[0]
    ctx = Context.ByTopologyParameters(f, 0.5,0.5,0.5)
    apt = Aperture.ByTopologyContext(doors[0], ctx)
    print("aperture:", apt, Topology.TypeAsString(apt) if apt else None, "Aperture.Topology ->", Topology.TypeAsString(Aperture.Topology(apt)) if apt else None)
    
    print("=== JSON round trip CellComplex with dicts+apertures")
    js = Topology.JSONString(cc2)
    data = json.loads(js)
    print("top-level list len:", len(data), "types:", sorted(set(d["type"] for d in data)), "toplevel count:", sum(1 for d in data if d["dictionary"].get("toplevel")))
    top = [d for d in data if d["dictionary"].get("toplevel")][0]
    print("toplevel entry keys:", list(top.keys()), "brep present:", "brep" in top, "dict:", top["dictionary"])
    cellentries = [d for d in data if d["type"]=="Cell"]
    print("cell entries:", len(cellentries), "sample dict:", cellentries[0]["dictionary"])
    apentries = [d for d in data if d.get("apertures")]
    print("entries with apertures:", len(apentries))
    back = Topology.ByJSONString(js)
    print("ByJSONString ->", type(back), Topology.TypeAsString(back) if not isinstance(back, list) else [Topology.TypeAsString(b) for b in back])
    b = back[0] if isinstance(back, list) else back
    print("  cells", len(Topology.Cells(b)), "names", [Dictionary.ValueAtKey(Topology.Dictionary(c),"name") for c in Topology.Cells(b)], "apertures", len(Topology.Apertures(b)))
    
    print("=== Graph JSON")
    g = Graph.ByTopology(cc2, direct=True, viaSharedApertures=True)
    gj = Graph.JSONString(g, vertexLabelKey="name"); gd = json.loads(gj)
    print("graph json keys:", list(gd.keys()))
    print("vertices sample:", json.dumps(gd["vertices"][list(gd["vertices"].keys())[0]] if isinstance(gd["vertices"], dict) else gd["vertices"][0])[:400])
    print("edges sample:", json.dumps(gd["edges"][list(gd["edges"].keys())[0]] if isinstance(gd["edges"], dict) else gd["edges"][0])[:400])
    jd = Graph.JSONData(g); print("JSONData keys:", list(jd.keys()), "vertices type:", type(jd["vertices"]).__name__)
    Graph.ExportToJSON(g, os.path.join(tempfile.gettempdir(), "g.json"), overwrite=True)
    g2 = Graph.ByJSONPath(os.path.join(tempfile.gettempdir(), "g.json"))
    print("ByJSONPath roundtrip v/e:", len(Graph.Vertices(g2)), len(Graph.Edges(g2)))

if __name__ == '__main__':
    main()
