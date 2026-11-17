# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Adventurous Systems

"""M7.0: doors as apertures on shared faces, including per-floor pieces of shaft walls (spike 2026-09-13, plan §2.2)."""
import networkx as nx
import pytest
from topologicpy.CellComplex import CellComplex
from topologicpy.Dictionary import Dictionary
from topologicpy.Face import Face
from topologicpy.Graph import Graph
from topologicpy.Topology import Topology
from topologicpy.Vertex import Vertex

from spacetope.realise import realise
from tests.test_shaft_smoke import H, LEVELS, shaft_model

pytestmark = [pytest.mark.gate_m7, pytest.mark.slow]


def door_face(boxes, a, b, level, width=900, height=2100):
    A, B = boxes[a], boxes[b]
    lo = max(A.y, B.y); hi = min(A.y1, B.y1)
    origin = Vertex.ByCoordinates(A.x1 / 1000, (lo + hi) / 2000, (level * H + height / 2) / 1000)
    f = Face.Rectangle(origin=origin, width=width / 1000, length=height / 1000, direction=[1, 0, 0], placement="center")
    Topology.SetDictionary(f, Dictionary.ByPythonDictionary({"name": f"door_{a}_{b}_{level}", "kind": "door"}))
    return f


def build_with_doors():
    brief, boxes = shaft_model()
    r = realise(brief, boxes)
    planned = [(a, b, k) for k in range(LEVELS)
               for a, b in ((f"corridor_{k}", f"room_{k}"), ("stair", f"corridor_{k}"), ("lift", f"corridor_{k}"))]
    doors = [door_face(boxes, a, b, k) for a, b, k in planned]
    cc = Topology.AddApertures(r.cc, doors, exclusive=False, subTopologyType="face", tolerance=0.001)
    return r, cc, planned


def test_all_doors_attach_on_internal_faces_and_keep_dictionaries():
    r, cc, planned = build_with_doors()
    assert len(Topology.Apertures(cc, subTopologyType="face")) == len(planned)
    dec = CellComplex.Decompose(cc)
    assert len(dec["internalVerticalApertures"]) == len(planned) and len(dec["externalVerticalApertures"]) == 0
    names = sorted(Dictionary.ValueAtKey(Topology.Dictionary(c), "name") for c in Topology.Cells(cc))
    assert None not in names and len(names) == r.n_cells


def test_door_graph_has_exactly_the_planned_links():
    _, cc, planned = build_with_doors()
    G = Graph.NetworkXGraph(Graph.ByTopology(cc, direct=False, directApertures=True, silent=True))
    got = {frozenset((G.nodes[a]["name"], G.nodes[b]["name"])) for a, b in G.edges()}
    assert got == {frozenset((a, b)) for a, b, _ in planned}


def test_brep_drops_doors_documented():
    _, cc, _ = build_with_doors()
    back = Topology.ByBREPString(Topology.BREPString(cc))
    assert len(Topology.Apertures(back, subTopologyType="face")) == 0  # hence the doors.json sidecar
