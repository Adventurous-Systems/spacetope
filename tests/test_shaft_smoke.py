# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Adventurous Systems

"""M7.0: a stair and a lift as single cells through three floors (spike 2026-09-13, plan §2.1)."""
import pytest
from topologicpy.CellComplex import CellComplex
from topologicpy.Face import Face
from topologicpy.Graph import Graph
from topologicpy.Topology import Topology

from spacetope.brief import Brief
from spacetope.realise import realise
from spacetope.solve.grid import Box, touches
from spacetope.verify import verify

pytestmark = [pytest.mark.gate_m7, pytest.mark.slow]
H, LEVELS = 3000, 3


def shaft_model():
    spaces = [{"name": "stair", "w": 3, "l": 5, "h": 9, "program": "stair"},
              {"name": "lift", "w": 2.5, "l": 2.5, "h": 9, "program": "elevator"}]
    boxes = {"stair": Box(0, 0, 0, 3000, 5000, LEVELS * H), "lift": Box(500, 5000, 0, 2500, 2500, LEVELS * H)}
    for k in range(LEVELS):
        spaces += [{"name": f"corridor_{k}", "w": 1.8, "l": 10, "h": 3, "program": "corridor"},
                   {"name": f"room_{k}", "w": 4, "l": 3, "h": 3, "program": "room"}]
        boxes[f"corridor_{k}"] = Box(3000, 0, k * H, 1800, 10000, H)
        boxes[f"room_{k}"] = Box(4800, 0, k * H, 4000, 3000, H)
    return Brief.from_dict({"name": "shaft_smoke", "spaces": spaces, "levels": LEVELS, "level_height": 3}), boxes


def test_shafts_build_one_cell_each_and_split_per_floor():
    brief, boxes = shaft_model()
    r = realise(brief, boxes)
    assert Topology.IsInstance(r.cc, "CellComplex") and r.n_cells == len(boxes)
    for shaft in ("stair", "lift"):
        for k in range(LEVELS):
            corridor = f"corridor_{k}"
            u, v = touches(boxes[shaft], boxes[corridor], "+x")
            assert (u, v) != (0, 0), (shaft, corridor)
            expected_area = u * v / 1e6
            faces = [f for f in CellComplex.NonManifoldFaces(r.cc)
                     if {r.name_of(c) for c in Topology.SuperTopologies(f, r.cc, topologyType="cell")} == {shaft, corridor}]
            assert len(faces) == 1, (shaft, corridor, len(faces))
            assert abs(Face.Area(faces[0]) - expected_area) < 1e-6, (shaft, corridor)
    assert verify(brief, boxes).ok


def test_graph_links_each_shaft_to_every_corridor():
    brief, boxes = shaft_model()
    r = realise(brief, boxes)
    pairs = {c.pair for c in r.realised_contacts()}
    for shaft in ("stair", "lift"):
        for k in range(LEVELS):
            assert frozenset((shaft, f"corridor_{k}")) in pairs
    g = Graph.ByTopology(r.cc, direct=True, silent=True)
    assert len(Graph.Vertices(g)) == len(boxes)
