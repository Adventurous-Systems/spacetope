"""M14 gate: topologicpy >= 0.9.68 features. TPY one-file persistence and vertical-route redundancy.
The pin bump itself is gated by every earlier gate module staying green on the new version."""
import importlib.metadata as md

import pytest
import yaml
from topologicpy.Dictionary import Dictionary
from topologicpy.Topology import Topology

from spacetope.brief import Brief, load
from spacetope.io import tpy
from spacetope.pipeline import generate
from spacetope.solve.registry import GENERATORS

pytestmark = [pytest.mark.gate_m14, pytest.mark.slow]


def test_pin():
    v = tuple(int(x) for x in md.version("topologicpy").split(".")[:3])
    assert v >= (0, 9, 68), md.version("topologicpy")
    assert tpy.AVAILABLE


@pytest.mark.parametrize("fx", ("two_levels_stair", "three_levels_core"))
def test_tpy_round_trip_keeps_dictionaries_and_doors(fixtures_dir, tmp_path, fx):
    options, _, _ = generate(GENERATORS["beam"], load(fixtures_dir / f"{fx}.yaml"), 0, {"k": 1}, "beam")
    r = next(o for o in options if o.ok).realised
    path = tpy.save(r, tmp_path / f"{fx}.tpy")
    back = tpy.load_cellcomplex(path)
    assert Topology.IsInstance(back, "CellComplex")
    names = sorted(Dictionary.ValueAtKey(Topology.Dictionary(c), "name") for c in Topology.Cells(back))
    assert names == sorted(r.names)
    for c in Topology.Cells(back):
        d = Dictionary.PythonDictionary(Topology.Dictionary(c))
        assert {"name", "program", "w", "l", "h"} <= set(d), d
    doors = Topology.Apertures(back, subTopologyType="face") or []
    assert len(doors) == len(r.doors) > 0
    got = sorted(Dictionary.ValueAtKey(Topology.Dictionary(a), "name") for a in doors)
    assert got == sorted(d.name for d in r.doors)


def test_vertical_routes(fixtures_dir):
    brief = load(fixtures_dir / "two_levels_stair.yaml")
    options, _, _ = generate(GENERATORS["beam"], brief, 0, {"k": 2}, "beam")
    for o in (o for o in options if o.ok):
        assert o.analysis["vertical_routes"] == 2 and o.analysis["stair_routes"] == 1, o.analysis   # one stair, one lift
    d = yaml.safe_load((fixtures_dir / "two_levels_stair.yaml").read_text())
    d["name"] = "two_stairs"; d["envelope"] = {"w": 26, "l": 16, "h": 6}
    d["circulation"]["stairs"].append({"name": "stair_b", "w": 3, "l": 5})
    options, _, _ = generate(GENERATORS["beam"], Brief.from_dict(d), 0, {"k": 2}, "beam")
    ok = [o for o in options if o.ok]
    assert ok and all(o.analysis["stair_routes"] == 2 and o.analysis["vertical_routes"] == 3 for o in ok), [o.analysis for o in ok]


def test_tgraph_agrees_on_disjoint_paths(fixtures_dir):
    """The kernel library's own connectivity (new in 0.9.68+) gives the same count as networkx on the door graph."""
    from topologicpy.TGraph import TGraph
    if not hasattr(TGraph, "DisjointPaths"):
        pytest.skip("TGraph.DisjointPaths not in this topologicpy")
    from spacetope.doors import door_graph
    options, _, _ = generate(GENERATORS["beam"], load(fixtures_dir / "two_levels_stair.yaml"), 0, {"k": 1}, "beam")
    o = next(o for o in options if o.ok)
    g = door_graph(o.realised.brief, o.realised.doors)
    for n in g.nodes:
        g.nodes[n]["id"] = n
    t = TGraph.ByNetworkXGraph(g, vertexID="id")
    idx = {(v.get("dictionary") or {}).get("id"): v for v in TGraph.Vertices(t)}
    paths = TGraph.DisjointPaths(t, idx["corridor_1"], idx["corridor_0"], silent=True)
    assert len(paths) == o.analysis["vertical_routes"] == 2
