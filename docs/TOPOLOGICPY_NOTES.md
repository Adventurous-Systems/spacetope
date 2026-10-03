# topologicpy notes — verified behaviour for spacetope

Environment: topologicpy **0.9.57**, topologic_core **8.0.0**, Python 3.11.9, macOS 14 arm64. Verified 2026-09-13.
Legend: `[RUN]` executed locally · `[SRC]` read from installed source · `[DOC]` docs/PyPI · `[?]` uncertain.
Companion findings from earlier work: dictionary loss on JSON round-trip, TGraph bugs.

## 1. Install

- `pip install topologicpy==0.9.57 topologic_core==8.0.0`. Requires-Python `>=3.8,<3.15`. Deps: numpy, scipy, pandas, shapely, plotly, lark, webcolors. `[SRC]`
- topologic_core wheels: Windows x86-64, Linux x86-64 manylinux2014, **macOS arm64 only** (no x86_64, no sdist). `[DOC]`
- Latest on PyPI: topologicpy 0.9.68 (2026-09-07), topologic_core 8.0.4. 0.9.68 is pure-Python, signature-identical for everything we use except added `silent` kwargs; `CellComplex.ByCells` source byte-identical. 0.9.68 adds `Core.py` backend switch `TOPOLOGICPY_CORE_BACKEND=pythonocc|topologic_core|auto` and drops the hard `topologic_core` requirement (install it yourself). Licence: 0.9.57 metadata AGPL-3.0; 0.9.68 README says LGPL. `[SRC][DOC]`

## 2. Boxes and transforms `[SRC][RUN]`

```python
Cell.Box(origin=None, width=1, length=1, height=1, uSides=1, vSides=1, wSides=1,
         direction=[0,0,1], placement='center', tolerance=0.0001)
Cell.Prism(...)                # same, plus mantissa=6
```
- `placement`: `center` | `bottom` | `lowerleft` (min corner). width=X, length=Y, height=Z. `lowerleft` box(4,4,3) at origin → centroid (2,2,1.5).
- Keep `uSides=vSides=wSides=1` (subdivision uses `Topology.Slice`, slow).
- `Topology.Translate(t, x, y, z, transferDictionaries=True)`, `Rotate(t, origin, axis=[0,0,1], angle_deg, ...)`, `Place(t, originA, originB)`, `Scale(...)` — all return **new objects**, keep dictionaries by default.
- `Topology.BoundingBox(t)` → a Cell whose dictionary has `xmin..zmax, width, length, height`.
- `Cell.ByWires([bottomRect, topRect], triangulate=False)` lofts (sloped stair volume possible, but sloped faces won't share with neighbours — prefer boxes).

## 3. CellComplex — the tolerance truth `[RUN]`

```python
CellComplex.ByCells(cells, transferDictionaries=False, tolerance=0.0001, silent=False)
CellComplex.ByFaces(faces, transferDictionaries=False, tolerance=0.0001, silent=False)
CellComplex.Decompose(cc, tiltAngle=10.0) -> dict
CellComplex.NonManifoldFaces(cc) / InternalFaces / ExternalFaces / ExternalBoundary(cc) -> Shell
Topology.SelfMerge(t, transferDictionaries=False, tolerance=0.0001)
Topology.Merge/Union/Slice/Impose/Imprint/Difference/Intersect(a, b, tranDict=False, tolerance=0.0001)
```
`ByCells` flattens all faces → `ByFaces` (groups faces by quantised plane, **shapely** subtracts overlapping coplanar polygons so duplicates collapse and partial overlaps split) → core build. Returns a **Cell** if 1 cell results, **None** if 0 (docstring says Cluster; it is None). `[SRC][RUN]`

Two 4×4×3 boxes, box B moved along x:

| Situation | Result |
|---|---|
| exact touch (x=4) | CellComplex, 2 cells, 11 faces, 1 shared face (area 12); graph 2v/1e |
| gap 1e-6, 5e-5 | still merges (below tolerance 1e-4) |
| gap 5e-4, 0.05, 0.5 | **`None` at every tolerance 1e-4…1.0** — tolerance is not a healing distance |
| overlap 0.05 | **3 cells** (47.4, 0.6, 47.4): a sliver phantom room; merged dictionary on the sliver |
| 3×2 box abutting an 8×4 wall | big wall face **auto-split** (12+6+3+3); shared 6 m² face; graph edge created — no Slice/Imprint needed |
| B stacked at z=3 | merges with 1 shared horizontal face |
| disjoint | `Merge` → Cluster; `Graph.ByTopology(cluster)` gives disconnected vertices (fine) |

Consequences: solver emits exact coordinates on an integer mm grid; never rely on tolerance; check cell count after every build.

`Topology.Union` fuses touching cells into one (internal wall removed) — never for rooms. `SelfMerge(Cluster.ByTopologies(cells), transferDictionaries=True)` also yields a CellComplex and kept cell dictionaries in-process.

`Decompose` keys: `cells, externalVerticalFaces, internalVerticalFaces, topHorizontalFaces, bottomHorizontalFaces, internalHorizontalFaces, externalInclinedFaces, internalInclinedFaces`, matching `*Apertures`, plus aggregates. Assumes +Z up.

## 4. Graph `[SRC][RUN]`

```python
Graph.ByTopology(topology, direct=True, directApertures=False, viaSharedTopologies=False,
    viaSharedApertures=False, toExteriorTopologies=False, toExteriorApertures=False,
    toContents=False, toOutposts=False, useInternalVertex=False, storeBREP=False,
    ontology=True, mantissa=6, tolerance=0.0001, silent=False)
```
On 3 rooms + corridor, 3 doors, 1 window:
- `direct=True`: vertex per cell, edge per shared face (4v/5e). Edge dict `relationship='Direct'`.
- `direct=False, directApertures=True`: edges only where the shared face carries an aperture (4v/3e).
- `viaSharedTopologies=True`: **adds a vertex per shared face = our wall nodes** (9v/10e). This is the realised wall-node graph.
- `viaSharedApertures=True`: vertex per door (7v/6e). `toExteriorTopologies=True`: vertex per exterior face (20v/21e). Flags are additive.
- Vertex dicts copy the cell dictionary + `category`, `index`, `ontology_*` (set `ontology=False` to skip).
- `Graph.AddEdge(graph, edge, transferVertexDictionaries, transferEdgeDictionaries)` **mutates** the graph. No `AddEdges`. `Graph.Connect(graph, vsA, vsB)`.
- `Graph.NetworkXGraph(graph)` → nx.Graph with node attrs incl. `x,y,z,pos`; `Graph.ByNetworkXGraph(...)`. `AdjacencyMatrix`, `AdjacencyList`, `AdjacentVertices`, `VertexDegree`.
- `Graph.ShortestPath(graph, vA, vB, edgeKey='Length', ..., useAStar=False, returnVertices=False)` pure-Python; `IsConnected`, `ConnectedComponents`, `Betweenness/ClosenessCentrality`, `Depth`, `Integration/Choice`.
- `Graph.NavigationGraph(face, ...)` / `VisibilityGraph(face, ...)` are 2D on a Face; NavigationGraph spawns processes.
- JSON: `Graph.JSONString/JSONData/ExportToJSON/ByJSONPath`. Format `{"properties":{}, "vertices":{label:{x,y,z,index,...}}, "edges":{label:{source,target,...}}}` — dicts keyed by label. Round-trips names and edges. Also `ExportToCSV` (DGL), `ExportToGEXF`, `BOTGraph`, `ExportToJSONLD`.
- Display: `Graph.Show(...)`, `Graph.PyvisGraph(graph, path)`.

## 5. Dictionaries `[SRC][RUN]`

```python
Dictionary.ByKeysValues(keys, values); ByPythonDictionary(d); PythonDictionary(d); ValueAtKey(d, key, default)
Topology.SetDictionary(t, dict_or_Dictionary)  # returns same object
Topology.Dictionary(t)
Topology.TransferDictionariesBySelectors(t, selectors, tranVertices=False, tranEdges=False,
                                         tranFaces=False, tranCells=False, tolerance=0.0001, numWorkers=None)
```
- Value types round-trip: int, float, str, list, nested dict, None. **bool → int**.
- `ByCells(transferDictionaries=False)` drops all cell dictionaries. `True` re-attaches by point-in-cell lookup (~4× slower; face dictionaries still lost).
- `Merge(tranDict=True)` and `TransferDictionariesBySelectors(numWorkers=None)` spawn **2×CPU processes** — on macOS this crashes without `if __name__ == "__main__"`. **Always `numWorkers=1`.**
- Canonical pattern (Building_Tower notebook): `sel = Topology.InternalVertex(cell); Topology.SetDictionary(sel, d)` for each cell; after the build, `TransferDictionariesBySelectors(cc, sels, tranCells=True, numWorkers=1)`. Verified.

## 6. Apertures (doors/windows) `[RUN]`

- Door = a `Face.Rectangle(origin, width=0.9, length=2.1, direction=<wall normal>)` lying on the wall plane, with a dictionary; `Topology.AddApertures(cc, [door], exclusive=False, subTopologyType="face", tolerance=0.001)` (mutates + returns). Host found by BVH clash + `Vertex.IsInternal`.
- Query: `Topology.Apertures(cc, subTopologyType="face")` (returns the aperture Faces). `Decompose` buckets them.
- Graph flags `directApertures / viaSharedApertures / toExteriorApertures` use them; edge/vertex dicts inherit the aperture dict.

## 7. Serialisation and viewing `[RUN]`

- **Topologic JSON** (`Topology.JSONString/ExportToJSON/ByJSONString/ByJSONPath`): a list of every sub-topology with uuid refs. **Round-trip loses cell/face dictionaries and duplicates apertures** (0.9.57 and 0.9.68). Do not use as the persistence format for tagged buildings.
- **BREP** (`Topology.BREPString(t)`, `ByBREPString(s)`, `ExportToBREP`): geometry only, exact round-trip, ~3.8 KB per box. **Persist BREP + a selector sidecar** `[{"name":..., "xyz":[...], "dict":{...}}]` and re-apply with `TransferDictionariesBySelectors`.
- `[RUN 2026-09-14]` `Topology.MeshData(cc, mode=1)` on a 9-cell complex returns 44 vertices but face indices up to 145: unusable. `mode=0` is consistent (shared vertex table, faces listed per cell so a shared wall appears twice, `cells` = face-index lists in `Topology.Cells` order); On a 12-cell two-level complex with two shafts, `mode=0` returned only 10 `cells` lists. `spacetope/io/mesh.py` therefore uses `Topology.Geometry` per cell of `Topology.Cells` and merges vertices (mm keys) and faces (vertex-set keys) itself; that gives 48 faces on the 9-cell complex, equal to `Topology.Faces`.
- **Mesh for the web**: `Topology.Geometry(t, triangulate=True, mode=0)` → `{vertices, edges, faces, *_dicts}`; `Topology.MeshData(t, mode=1)` adds `cells` (face-index lists per cell) — use per cell to build one GLB node per cell (trimesh). No GLB/glTF/STL exporter in the library; `ExportToOBJ` exists but makes an HTTP call to PyPI for a version header (offline stall).
- **IFC**: import only (`Topology.ByIFCFile/ByIFCPath`, `IFC.TopologiesByPath`); export via ifcopenshell yourself.
- **Plotly**: `Plotly.DataByTopology(t, faceColorKey=..., faceLabelKey=...)` + `Plotly.DataByGraph(g, vertexLabelKey=...)` → `Plotly.FigureByData(data)` → `fig.write_html(path, include_plotlyjs='cdn')` (12 KB). `Topology.Show(..., renderer='browser')` outside Jupyter.

## 8. Analysis helpers `[SRC][RUN]`

`Cell.Volume`, `Face.Area`, `Face.Normal`, `Face.IsCoplanar`, `Face.PlaneEquation`, `Topology.Centroid`, `Topology.InternalVertex`, `Vertex.IsInternal(v, t, identify=True)` (returns containing Cell), `Vertex.EnclosingCells`, `Topology.SharedTopologies(a, b)` → `{vertices, edges, wires, faces}`, `Topology.SharedFaces(a, b)`, `Topology.AdjacentTopologies(cell, cc, topologyType='cell')`, `Topology.SuperTopologies(face, cc, 'cell')` (the 1–2 cells bounding a face), `Vertex.Distance(v, t)`, `Topology.Filter(topologies, key=, value=)`, `Topology.SpatialRelationship(a, b)`. No `Topology.IsInside`, no `Topology.Boolean` (private `_Boolean`).

## 9. Corridors and stairs `[RUN]`

- L/U corridor: `Wire.ByVertices(pts, close=True)` → `Face.ByWire` → `Cell.ByThickenedFace(face, thickness=h, bothSides=False)` (extrudes +normal; `reverse=True` flips). Verified volume 96 for a 6-vertex L × 3 m. `Wire.ByOffset(wire, offset)` shrinks a CCW rectangle inward for positive offset.
- Stairs/elevators: box cells stacked with identical footprints so `ceiling ↔ floor` faces coincide; an elevator may be a single tall cell (lateral faces auto-split against each level's corridor). Vertical link semantics live in the graph (`Graph.AddEdge` with `{"kind": "stair"}` dictionary) or emerge from the shared horizontal face.

## 10. Performance and process model `[RUN]` (M-series arm64)

| Cells | `ByCells` | `ByCells(transferDictionaries=True)` | `Graph.ByTopology` |
|---|---|---|---|
| 25 | 0.8 s | – | 0.1 s |
| 98 (2 levels) | 0.9 s | 4.1 s | 0.5 s |
| 196 | 2.5 s | 10.6 s | 0.9 s |

- `JSONString` 0.4–0.8 s; `Geometry` ≤ 0.13 s; `ShortestPath` < 0.1 s.
- **Not picklable** (`pickle`, `deepcopy` raise). `Topology.Copy(t)` for in-process copies. Multiprocess search must pass specs/BREP strings and rebuild per worker.
- **Threads give no speed-up** (GIL held by the pybind core); thread safety of shared objects untested `[?]` — one topology per thread.
- The library prints warnings to stdout; `silent=True` is not threaded through every inner call.
- `Topology.Show`, `Graph.Show`, OBJ export call PyPI for a version check; nothing at import time.

## 11. Reference examples

- `notebooks/Building_Tower.ipynb` (upstream): prisms + core cut via `Topology.Difference`, `CellComplex.ByCells`, selectors, `Graph.ByTopology`, `Graph.ExportToCSV`.
- Upstream `tests/test_CellComplex.py`, `test_Graph.py`, `test_Aperture.py`, `test_Dictionary.py`, `test_Topology_BREPString.py`.
- Session experiment scripts (scratchpad, not in repo): `exp.py … exp5.py` — port the two-box cases into `tests/test_topologic_smoke.py` in M0.

## 12. Intermittent kernel failures in long-lived processes `[RUN]`

Seen repeatedly on 2026-09-13 during runs that build hundreds of complexes in one process (gate suites,
the M6 comparison): topologicpy prints, with no exception,

```
Topology.Translate - Error: The core translate operation failed. Returning the original input.
Topology.Scale - Error: Core scale operation failed. Returning None.
Topology.Translate - Error: The input topology parameter is not a valid topology. Returning None.
Topology.SetDictionary - Error: the input topology parameter is not a valid topology ... Returning None.
```

`Cell.Box(placement="lowerleft")` translates internally, so when the core translate fails the box is
silently **left at the origin**, and when a later step gets `None` the cell is `None`. Consequences seen:
a `TypeError` deep in a gate run, and one option that failed verification once and never again (a
misplaced cell overlaps its neighbours, so the cell-count and volume checks reject it). Never reproduced
in a fresh process; cause in the kernel unknown (resource exhaustion suspected).

Mitigation in spacetope: `realise.make_cell` checks each built cell's centroid against the intended box,
retries twice, and raises `RealiseError("kernel failed to build cell ...")`, so the failure is named and
`verify` reports `built: False` instead of the process crashing. Multiprocess search with plain specs per
worker (already the rule) also bounds how much one process asks of the kernel.

## 13. Unused graph machinery and the 0.9.71 differential (2026-09-20)

Full note: `docs/2026-09-20_TOPOLOGICPY_OPPORTUNITIES.md`. Facts, all `[RUN]` unless marked:

- `[RUN 0.9.57]` `TGraph.ByTopology(cc, direct=True, viaSharedTopologies=True)` gives the same order and size as `Graph.ByTopology` (38, 78 on a 12-cell complex) in 0.037 s vs 0.190 s.
- `[RUN 0.9.57]` `TGraph.AccessGraph(cc, viaSharedApertures=True)` returns spaces + doors as vertices (24, 24 for 12 spaces and 12 doors): a kernel-derived door graph.
- `[RUN 0.9.57]` `TGraph.Match(pattern, target, vertexKeys=[...])` finds labelled subgraph matches (12 wish triangles in 1 ms). `TGraph.ExportToCSV` writes a PyG-ready folder (`nodes.csv, edges.csv, graphs.csv, meta.yaml`).
- `[RUN 0.9.57 and 0.9.71]` `TGraph.Integration` fails: `ClosenessCentrality() got an unexpected keyword argument 'mode'`. `BetweennessCentrality`, `CutVertices`, `Bridges` work.
- `[RUN 0.9.57]` `TGraph.IsIsomorphic(a, b, wlKey="kind")` ignores differing vertex labels (True for two 3-paths with different middle labels); structure-only it is correct. Use networkx for labelled isomorphism.
- `[RUN 0.9.57]` `Face.Skeleton` on an L-shaped face: 12 edges, 1.1 s. `ShapeGrammar` operations: Replace, Transform, Union, Difference, Symmetric Difference, Intersect, Merge, Slice, Impose, Imprint, Divide; rules are topology → topology, not graph rewriting. `GA` needs `pygad` (absent).
- `[RUN 0.9.71]` `Topology.ExportToTPY` / `ByTPYPath` round-trip cell dictionaries and face apertures with their dictionaries (2.9 KB, 29 ms / 3 ms). `Topology.JSONString` round trip still loses cell dictionaries.
- `[RUN 0.9.71]` `Cell.Inflate(cell, faces)` moved 4 of 6 faces to the limiting faces (12 → 90 m³). `Topology.Touches/Overlaps/Disjoint` correct on two boxes. New `TGraph.DisjointPaths`, `MinimumCut`, `VertexConnectivity`, `BiconnectedComponents` work on a door-graph-shaped TGraph (2 disjoint paths between corridors; cut = stair + lift).
- `[SRC]` 0.9.71 metadata: LGPL-3.0-or-later; deps numpy, scipy, pandas, shapely, plotly, lark, webcolors, nbformat, requests, packaging. `Graph` API identical to 0.9.57 (188 methods).

## 14. Behaviour changes on the pin bump 0.9.57 → 0.9.71 (2026-09-20, all `[RUN]`)

Found by `tests/test_topologic_smoke.py` on the first run after the bump; probed with two 4 × 4 × 3 m boxes.

| Case | 0.9.57 | 0.9.71 |
|---|---|---|
| exact contact | CellComplex, 2 cells, 11 faces, 1 shared | same |
| gap 0.05 mm (below `tolerance`) | merged: 2 cells | **empty CellComplex** (0 cells, 0 faces) |
| gap 0.5 mm (above `tolerance`) | `None` | **empty CellComplex**, not `None` |
| disjoint (6 m apart) | `None` | **empty CellComplex**, not `None` |
| overlap 50 mm | 3 cells, one a 0.6 m³ sliver | same |
| `ByCells` default dictionaries | dropped (names `None`) | **kept** (`transferDictionaries=False` still returns names) |

Consequences. A failed merge is now an object, so "`ByCells` is not `None`" is no longer a test of anything:
`realise` treats a complex without cells as a failed build on every version. Sub-tolerance gaps no longer heal,
which only tightens rule 1 (exact integer-mm coordinates). Selectors are still applied after `ByCells`; with 0.9.71
they are redundant for cells but harmless, and they remain the path for older pins. Licence: LGPL-3.0-or-later.
