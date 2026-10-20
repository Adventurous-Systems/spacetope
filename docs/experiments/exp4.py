import json, os, tempfile
from topologicpy.Vertex import Vertex
from topologicpy.Cell import Cell
from topologicpy.CellComplex import CellComplex
from topologicpy.Topology import Topology
from topologicpy.Dictionary import Dictionary
from topologicpy.Graph import Graph
from topologicpy.Face import Face
from topologicpy.Aperture import Aperture
from topologicpy.Context import Context
from topologicpy.Edge import Edge

def box(x,y,z,w,l,h,name):
    c = Cell.Prism(origin=Vertex.ByCoordinates(x,y,z), width=w, length=l, height=h, placement="lowerleft")
    Topology.SetDictionary(c, Dictionary.ByKeysValues(["name","type"],[name,"room"]))
    return c
def main():
    rooms = [box(0,0,0,4,4,3,"R1"), box(4,0,0,4,4,3,"R2"), box(8,0,0,4,4,3,"R3"), box(0,4,0,12,2,3,"Corr")]
    cc = CellComplex.ByCells(rooms, transferDictionaries=True, silent=True)
    internal = CellComplex.InternalFaces(cc)
    doors=[]
    for f in internal:
        c = Topology.Centroid(f)
        if abs(Vertex.Y(c)-4)<1e-6:
            d = Face.Rectangle(origin=Vertex.ByCoordinates(Vertex.X(c), 4, 1.05), width=0.9, length=2.1, direction=[0,1,0])
            Topology.SetDictionary(d, Dictionary.ByKeysValues(["type","name"],["door", f"door_{round(Vertex.X(c),1)}"]))
            doors.append(d)
    # exterior window on R1 south wall (y=0)
    win = Face.Rectangle(origin=Vertex.ByCoordinates(2, 0, 1.5), width=1.2, length=1.0, direction=[0,1,0])
    Topology.SetDictionary(win, Dictionary.ByKeysValues(["type","name"],["window","win_R1"]))
    cc2 = Topology.AddApertures(cc, doors+[win], subTopologyType="face")
    print("same object returned?", cc2 is cc)
    aps = Topology.Apertures(cc2, subTopologyType="face")
    print("apertures on faces:", len(aps), "types:", [Topology.TypeAsString(a) for a in aps][:2], type(aps[0]))
    print("aperture dict:", Dictionary.PythonDictionary(Topology.Dictionary(aps[0])))
    # which faces have apertures
    n=0
    for f in Topology.Faces(cc2):
        fa = Topology.Apertures(f)
        if fa: n+=1
    print("faces carrying apertures:", n)
    dec = CellComplex.Decompose(cc2); print("Decompose aperture buckets:", {k:len(v) for k,v in dec.items() if "Aperture" in k and len(v)})
    for kw in [dict(direct=True), dict(direct=False, directApertures=True), dict(direct=False, viaSharedApertures=True), dict(direct=False, viaSharedApertures=True, toExteriorApertures=True), dict(direct=True, viaSharedApertures=True, toExteriorApertures=True)]:
        g = Graph.ByTopology(cc2, **kw)
        vs = Graph.Vertices(g)
        names = [Dictionary.ValueAtKey(Topology.Dictionary(v),"name") for v in vs]
        cats = [Dictionary.ValueAtKey(Topology.Dictionary(v),"category") for v in vs]
        es = Graph.Edges(g)
        ecat = sorted(set(Dictionary.ValueAtKey(Topology.Dictionary(e),"category") for e in es))
        print(kw, "-> v", len(vs), "e", len(es), "names", names, "vcats", sorted(set(cats)), "ecats", ecat)
        if es: print("   edge dict:", Dictionary.PythonDictionary(Topology.Dictionary(es[0])))

    print("=== manual Aperture.ByTopologyContext")
    f = internal[0]
    ctx = Context.ByTopologyParameters(f, 0.5,0.5,0.5)
    apt = Aperture.ByTopologyContext(doors[0], ctx)
    print("aperture:", type(apt), "Aperture.Topology ->", Topology.TypeAsString(Aperture.Topology(apt)) if apt else None)

    print("=== JSON round trip CellComplex with dicts+apertures")
    js = Topology.JSONString(cc2)
    data = json.loads(js)
    print("top-level list len:", len(data), "types:", sorted(set(d["type"] for d in data)), "toplevel count:", sum(1 for d in data if d["dictionary"].get("toplevel")))
    top = [d for d in data if d["dictionary"].get("toplevel")][0]
    print("toplevel entry keys:", list(top.keys()), "type", top["type"], "dict:", top["dictionary"])
    cellentries = [d for d in data if d["type"]=="Cell"]
    print("cell entries:", len(cellentries), "sample keys:", list(cellentries[0].keys()), "dict:", cellentries[0]["dictionary"])
    apentries = [d for d in data if d.get("apertures")]
    print("entries with apertures:", len(apentries), "aperture entry sample:", json.dumps(apentries[0]["apertures"][0])[:300] if apentries else None)
    back = Topology.ByJSONString(js)
    print("ByJSONString ->", type(back).__name__, [Topology.TypeAsString(b) for b in back] if isinstance(back, list) else Topology.TypeAsString(back))
    b = back[0] if isinstance(back, list) else back
    print("  cells", len(Topology.Cells(b)), "names", [Dictionary.ValueAtKey(Topology.Dictionary(c),"name") for c in Topology.Cells(b)], "face apertures", len(Topology.Apertures(b, subTopologyType="face")))
    ok = Topology.ExportToJSON(cc2, os.path.join(tempfile.gettempdir(), "cc.json"), overwrite=True); print("ExportToJSON ->", ok)
    b2 = Topology.ByJSONPath(os.path.join(tempfile.gettempdir(), "cc.json")); print("ByJSONPath ->", type(b2).__name__)

    print("=== Graph JSON")
    g = Graph.ByTopology(cc2, direct=True, viaSharedApertures=True)
    gj = Graph.JSONString(g, vertexLabelKey="name"); gd = json.loads(gj)
    print("graph json keys:", list(gd.keys()), "vertices container:", type(gd["vertices"]).__name__, "edges container:", type(gd["edges"]).__name__)
    v0 = gd["vertices"][next(iter(gd["vertices"]))] if isinstance(gd["vertices"], dict) else gd["vertices"][0]
    e0 = gd["edges"][next(iter(gd["edges"]))] if isinstance(gd["edges"], dict) else gd["edges"][0]
    print("vertex sample:", json.dumps(v0)[:500]); print("edge sample:", json.dumps(e0)[:500])
    jd = Graph.JSONData(g); print("JSONData keys:", list(jd.keys()), "vertices:", type(jd["vertices"]).__name__, "sample:", json.dumps(jd["vertices"][0] if isinstance(jd["vertices"], list) else jd["vertices"][next(iter(jd["vertices"]))])[:300])
    Graph.ExportToJSON(g, os.path.join(tempfile.gettempdir(), "g.json"), overwrite=True)
    g2 = Graph.ByJSONPath(os.path.join(tempfile.gettempdir(), "g.json"))
    print("ByJSONPath roundtrip v/e:", len(Graph.Vertices(g2)), len(Graph.Edges(g2)), "names:", [Dictionary.ValueAtKey(Topology.Dictionary(v),"name") for v in Graph.Vertices(g2)])
    nx = Graph.NetworkXGraph(g); print("networkx node attrs sample:", list(nx.nodes(data=True))[0])
    print("Graph.Topology(g) ->", Topology.TypeAsString(Graph.Topology(g)))
    # AddVertex/AddEdge manual (e.g. stairs connecting floors)
    v1 = Vertex.ByCoordinates(50,50,0); Topology.SetDictionary(v1, Dictionary.ByKeysValues(["name"],["stairA"]))
    v2 = Vertex.ByCoordinates(50,50,3); Topology.SetDictionary(v2, Dictionary.ByKeysValues(["name"],["stairB"]))
    e = Edge.ByVertices([v1,v2]); Topology.SetDictionary(e, Dictionary.ByKeysValues(["kind"],["stair"]))
    g3 = Graph.AddEdge(g, e, transferVertexDictionaries=True, transferEdgeDictionaries=True)
    print("after AddEdge: v", len(Graph.Vertices(g3)), "e", len(Graph.Edges(g3)), "mutated original?", len(Graph.Vertices(g)))
    ne = [x for x in Graph.Edges(g3) if Dictionary.ValueAtKey(Topology.Dictionary(x),"kind")=="stair"]; print("stair edge dict:", Dictionary.PythonDictionary(Topology.Dictionary(ne[0])) if ne else None)
    g4 = Graph.Connect(g3, [Graph.Vertices(g3)[0]], [Graph.NearestVertex(g3, v1)]); print("Connect -> e", len(Graph.Edges(g4)))
    am = Graph.AdjacencyMatrix(g4); print("AdjacencyMatrix rows", len(am), "row0", am[0])
    sp = Graph.ShortestPath(g4, Graph.Vertices(g4)[0], Graph.Vertices(g4)[-1], returnVertices=True); print("ShortestPath ->", type(sp), Topology.TypeAsString(sp[0]) if sp else None, sp[1] if sp else None)
if __name__ == "__main__":
    main()
