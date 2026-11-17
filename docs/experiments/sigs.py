# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Adventurous Systems

import inspect, importlib
targets = {
 "Cell": ["Box","Prism","ByFaces","ByWires","ByThickenedFace","ByShell","Volume","Cylinder","ByThickenedShell"],
 "CellComplex": ["ByCells","ByFaces","ByWires","Decompose","ExternalBoundary","NonManifoldFaces","Cells","Faces","Box","Prism","ExternalFaces","InternalFaces","Volume"],
 "Topology": ["Translate","Rotate","Place","BoundingBox","SelfMerge","Merge","Union","Boolean","Slice","Impose","Imprint","Difference","Intersect","SetDictionary","Dictionary","TransferDictionaries","TransferDictionariesBySelectors","AddApertures","Apertures","ExportToJSON","ByJSONString","ByJSONPath","JSONString","ExportToBREP","ByBREPString","BREPString","ExportToOBJ","ExportToIFC","ByIFCFile","Geometry","Centroid","InternalVertex","IsInside","SharedTopologies","AdjacentTopologies","SuperTopologies","SubTopologies","ExportToGLTF","Show","Type","TypeAsString","Copy","IsSame","Vertices","Faces","Cells","Explode","Filter","Scale","Orient","RemoveCoplanarFaces","Cleanup","ExportToOBJ","OBJString","ExportToDXF","SetOrigin","Union","Analyze","IsPlanar","ByGeometry","ExportToSVG","ExportToBIM","ByBIMPath","BIMString"],
 "Graph": ["ByTopology","ByVerticesEdges","AddVertex","AddEdge","AddVertices","AddEdges","AdjacencyMatrix","AdjacencyList","NetworkXGraph","ByNetworkXGraph","ShortestPath","ShortestPaths","Vertices","Edges","NavigationGraph","VisibilityGraph","Connect","JSONString","ExportToJSON","ByJSONString","ByJSONPath","PyvisGraph","Show","Topology","Distance","Path","Degree","Diameter","Density","ExportToCSV","ExportToGEXF","ExportToDGCNN","ByDGCNNFile","IsComplete","Isolate","Merge","Union","Flatten","Betweenness","Closeness","IsErdoesRenyi","ByBIMPath","BOTGraph","ExportToBOT","ByCSVPath","ByAdjacencyMatrix","ExportToAdjacencyMatrixCSV","VertexAtCoordinates","NearestVertex","IsBipartite","MaximumFlow","Guess","Communities","MeshData","RemoveEdge","RemoveVertex","Size","Order","Neighbors","AllPaths","TopologicalDistance","LongestPath","AreConnected","IsConnected","Connect","Reshape","VertexDictionary","BuildingGraph","ByMeshData","Prune","VisibilityGraph","ExportToJSON"],
 "Dictionary": ["ByKeysValues","ValueAtKey","Keys","Values","ByMergedDictionaries","SetValueAtKey","PythonDictionary","ByPythonDictionary","Copy","RemoveKey","ListAttributeValues","Filter"],
 "Aperture": ["ByTopologyContext","Topology","ApertureTopology","ByObject","ByBoundaryWithContext"],
 "Face": ["Area","Normal","IsCoplanar","ByWire","ByWires","Rectangle","ByVertices","Centroid","InternalVertex","Box","ByOffset","Vertices","Edges","IsInside","FacingToward","Angle","PlaneEquation","ExternalBoundary","Triangulate","Compactness","Circle"],
 "Wire": ["Rectangle","ByOffset","ByVertices","ByEdges","Circle","Line","Vertices","Length","Planarize","IsClosed","Star","Squircle","Ellipse","Split","Skeleton"],
 "Shell": ["ByFaces","ByWires","Rectangle","Faces","ByThickenedWire","IsClosed","Roof","Skeleton","Pie","HyperbolicParaboloidRectangularDomain"],
 "Vertex": ["Distance","ByCoordinates","Coordinates","X","Y","Z","Origin","IsInternal","NearestVertex","Index"],
 "Plotly": ["DataByTopology","DataByGraph","FigureByData","Show","FigureByTopology","FigureByJSONPath","ExportToImage","ExportToHTML","AddColorBar","FigureByPieChart","DataByDGL","FigureByDataFrame"],
 "Context": ["ByTopologyParameters","Topology"],
 "Helper": ["Version","Flatten","Iterate","Repeat","Transpose","ClusterByKeys"],
 "Cluster": ["ByTopologies","FreeTopologies","Cells","Faces","Vertices"],
}
import topologicpy
for mod, names in targets.items():
    try:
        m = importlib.import_module(f"topologicpy.{mod}")
    except Exception as e:
        print(f"## {mod}: IMPORT ERROR {e}"); continue
    cls = getattr(m, mod)
    print(f"\n## topologicpy.{mod}.{mod}")
    allmeths = [n for n in dir(cls) if not n.startswith("_")]
    for n in names:
        f = getattr(cls, n, None)
        if f is None:
            print(f"  MISSING: {n}"); continue
        try:
            print(f"  {n}{inspect.signature(f)}")
        except Exception as e:
            print(f"  {n}: sig error {e}")
    print(f"  [ALL public: {', '.join(allmeths)}]")
