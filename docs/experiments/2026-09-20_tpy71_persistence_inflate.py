import inspect, time, os
from topologicpy.Cell import Cell
from topologicpy.CellComplex import CellComplex
from topologicpy.Topology import Topology
from topologicpy.Dictionary import Dictionary
from topologicpy.Vertex import Vertex
from topologicpy.Face import Face
from topologicpy.Aperture import Aperture
import importlib.metadata as m
print("topologicpy", m.version("topologicpy"))
a = Cell.Box(Vertex.ByCoordinates(0, 0, 0), width=4, length=3, height=3, placement="lowerleft")
b = Cell.Box(Vertex.ByCoordinates(4, 0, 0), width=3, length=3, height=3, placement="lowerleft")
a = Topology.SetDictionary(a, Dictionary.ByPythonDictionary({"name": "living", "program": "room"}))
b = Topology.SetDictionary(b, Dictionary.ByPythonDictionary({"name": "kitchen", "program": "room"}))
cc = CellComplex.ByCells([a, b], transferDictionaries=True)
print("built:", Topology.TypeAsString(cc), "cells", len(Topology.Cells(cc)), "names", [Dictionary.ValueAtKey(Topology.Dictionary(c), "name") for c in Topology.Cells(cc)])
# a door aperture on the shared face
shared = [f for f in Topology.Faces(cc) if len(Topology.SuperTopologies(f, cc, topologyType="cell")) == 2][0]
door = Face.Rectangle(origin=Topology.Centroid(shared), width=0.9, length=2.1, direction=Face.Normal(shared))
door = Topology.SetDictionary(door, Dictionary.ByPythonDictionary({"name": "door_living_kitchen"}))
try:
    cc2 = Topology.AddApertures(cc, [door], subTopologyType="face")
    print("apertures before save:", len(Topology.Apertures(cc2, subTopologyType="face")) if "subTopologyType" in inspect.signature(Topology.Apertures).parameters else len(Topology.Apertures(cc2)))
except Exception as ex:
    cc2 = cc; print("aperture add failed:", type(ex).__name__, str(ex)[:120])
print("ExportToTPY sig:", str(inspect.signature(Topology.ExportToTPY))[:200])
path = os.path.abspath("rt_test.tpy")
t = time.perf_counter(); ok = Topology.ExportToTPY(cc2, path, overwrite=True) if "overwrite" in inspect.signature(Topology.ExportToTPY).parameters else Topology.ExportToTPY(cc2, path)
print("export:", ok, f"{time.perf_counter() - t:.3f}s", "size", os.path.getsize(path) if os.path.exists(path) else None)
t = time.perf_counter(); back = Topology.ByTPYPath(path); print("import:", Topology.TypeAsString(back) if back else None, f"{time.perf_counter() - t:.3f}s")
if back:
    cells = Topology.Cells(back)
    print("round trip: cells", len(cells), "names", [Dictionary.ValueAtKey(Topology.Dictionary(c), "name") for c in cells])
    try:
        aps = Topology.Apertures(back, subTopologyType="face") if "subTopologyType" in inspect.signature(Topology.Apertures).parameters else Topology.Apertures(back)
        print("round trip apertures:", len(aps), [Dictionary.ValueAtKey(Topology.Dictionary(x), "name") for x in aps][:3])
    except Exception as ex: print("apertures read failed", str(ex)[:100])
# JSON round trip in 0.9.71 for comparison (0.9.57 loses cell dictionaries)
js = Topology.JSONString(cc2); back2 = Topology.ByJSONString(js)
back2 = back2[0] if isinstance(back2, list) else back2
print("JSON round trip names:", [Dictionary.ValueAtKey(Topology.Dictionary(c), "name") for c in Topology.Cells(back2)] if back2 else None)
# Cell.Inflate
print("Inflate sig:", str(inspect.signature(Cell.Inflate))[:260])
try:
    room = Cell.Box(Vertex.ByCoordinates(1, 1, 0), width=2, length=2, height=3, placement="lowerleft")
    shell = Cell.Box(Vertex.ByCoordinates(0, 0, 0), width=6, length=5, height=3, placement="lowerleft")
    out = Cell.Inflate(room, Topology.Faces(shell))
    from topologicpy.Cell import Cell as C
    print("inflate: volume", round(C.Volume(room), 2), "->", round(C.Volume(out), 2) if out else None, "(shell", round(C.Volume(shell), 2), ")")
except Exception as ex: print("Inflate failed:", type(ex).__name__, str(ex)[:160])
# spatial predicates
for n in ("Touches", "Overlaps", "Disjoint", "Proximity"):
    try: print(n, "->", getattr(Topology, n)(a, b))
    except Exception as ex: print(n, "failed", str(ex)[:80])
