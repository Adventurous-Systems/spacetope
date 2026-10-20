"""Contract with topologicpy: the two-box facts in docs/TOPOLOGICPY_NOTES.md §3.
If any of these change after a version bump, update the notes, then the rules, never just the assertion."""
import pytest

pytestmark = [pytest.mark.gate_m0, pytest.mark.slow]

from topologicpy.Vertex import Vertex
from topologicpy.Cell import Cell
from topologicpy.CellComplex import CellComplex
from topologicpy.Cluster import Cluster
from topologicpy.Topology import Topology
from topologicpy.Dictionary import Dictionary
from topologicpy.Graph import Graph
from topologicpy.Face import Face


def box(x, y, z, w, l, h, name="c"):
    c = Cell.Box(origin=Vertex.ByCoordinates(x, y, z), width=w, length=l, height=h, placement="lowerleft")
    Topology.SetDictionary(c, Dictionary.ByKeysValues(["name"], [name]))
    return c


def build(cells, **kw):
    return CellComplex.ByCells(cells, silent=True, **kw)


def test_exact_touch_shares_one_face():
    cc = build([box(0, 0, 0, 4, 4, 3, "A"), box(4, 0, 0, 4, 4, 3, "B")])
    assert cc is not None and len(Topology.Cells(cc)) == 2
    assert len(Topology.Faces(cc)) == 11
    shared = CellComplex.NonManifoldFaces(cc)
    assert len(shared) == 1 and abs(Face.Area(shared[0]) - 12.0) < 1e-6
    g = Graph.ByTopology(cc, direct=True, silent=True)
    assert len(Graph.Vertices(g)) == 2 and len(Graph.Edges(g)) == 1


def built_nothing(cc) -> bool:
    """A failed merge: None on 0.9.57, an empty CellComplex on 0.9.71 (notes §14)."""
    return cc is None or not (Topology.Cells(cc) or [])


def test_gap_below_tolerance_never_makes_a_sliver():
    # 0.9.57 healed a 0.05 mm gap into 2 cells; 0.9.71 builds nothing. Either way: two cells or none, never three.
    cc = build([box(0, 0, 0, 4, 4, 3), box(4 + 5e-5, 0, 0, 4, 4, 3)])
    assert built_nothing(cc) or len(Topology.Cells(cc)) == 2


def test_gap_above_tolerance_builds_nothing():
    # 0.5 mm gap: tolerance is a coincidence epsilon, not a healing distance.
    for tol in (0.0001, 0.001, 0.01):
        assert built_nothing(build([box(0, 0, 0, 4, 4, 3), box(4.0005, 0, 0, 4, 4, 3)], tolerance=tol))


def test_overlap_creates_sliver_cell():
    cc = build([box(0, 0, 0, 4, 4, 3), box(3.95, 0, 0, 4, 4, 3)])
    assert cc is not None and len(Topology.Cells(cc)) == 3


def test_partial_abut_splits_big_face():
    big = box(0, 0, 0, 8, 4, 3, "big")
    small = box(8, 1, 0, 3, 2, 3, "small")  # -x face spans y 1..3, z 0..3 -> 6 m2
    cc = build([big, small])
    assert cc is not None and len(Topology.Cells(cc)) == 2
    shared = CellComplex.NonManifoldFaces(cc)
    assert len(shared) == 1 and abs(Face.Area(shared[0]) - 6.0) < 1e-6
    # big's +x face (12 m2) is split into shared 6 + remainder pieces
    assert len(Topology.Faces(cc)) > 11


def test_stacked_shares_horizontal_face():
    cc = build([box(0, 0, 0, 4, 4, 3), box(0, 0, 3, 4, 4, 3)])
    assert cc is not None and len(Topology.Cells(cc)) == 2
    shared = CellComplex.NonManifoldFaces(cc)
    assert len(shared) == 1 and abs(Face.Area(shared[0]) - 16.0) < 1e-6


def test_disjoint_cells_form_cluster_with_disconnected_graph():
    a, b = box(0, 0, 0, 4, 4, 3), box(10, 0, 0, 4, 4, 3)
    assert built_nothing(build([a, b]))
    cl = Cluster.ByTopologies([a, b])
    assert len(Topology.Cells(cl)) == 2
    g = Graph.ByTopology(cl, direct=True, silent=True)
    assert len(Graph.Vertices(g)) == 2 and len(Graph.Edges(g)) == 0


def test_dictionaries_are_recovered_by_selectors_whatever_the_default():
    cells = [box(0, 0, 0, 4, 4, 3, "A"), box(4, 0, 0, 4, 4, 3, "B")]
    cc = build(cells)
    names = [Dictionary.ValueAtKey(Topology.Dictionary(c), "name") for c in Topology.Cells(cc)]
    assert names in ([None, None], ["A", "B"], ["B", "A"])   # dropped on 0.9.57, kept on 0.9.71; selectors work on both
    selectors = []
    for c in cells:
        v = Topology.InternalVertex(c)
        Topology.SetDictionary(v, Topology.Dictionary(c))
        selectors.append(v)
    cc = Topology.TransferDictionariesBySelectors(cc, selectors, tranCells=True, numWorkers=1)
    names = sorted(Dictionary.ValueAtKey(Topology.Dictionary(c), "name") for c in Topology.Cells(cc))
    assert names == ["A", "B"]


def test_brep_roundtrip_keeps_cells():
    cc = build([box(0, 0, 0, 4, 4, 3), box(4, 0, 0, 4, 4, 3)])
    s = Topology.BREPString(cc)
    back = Topology.ByBREPString(s)
    assert len(Topology.Cells(back)) == 2 and len(CellComplex.NonManifoldFaces(back)) == 1
