"""M9 gate: topologicpy's TGraph on the pinned version (adapter), topology-distinct counts, PyG export."""
import csv
import time

import pytest

from spacetope import tgraph
from spacetope.brief import load
from spacetope.circulation import prepare
from spacetope.doors import door_graph
from spacetope.io.graph import _payload_graph, graph_payload
from spacetope.learn.dataset import export_pyg
from spacetope.pipeline import generate, run_generator, topology_classes
from spacetope.solve.registry import GENERATORS
from spacetope.verify import _door_pairs_graph

pytestmark = [pytest.mark.gate_m9, pytest.mark.slow]
FIXTURES = ("three_rooms", "eight_rooms_corridor", "two_levels_stair")


@pytest.fixture(scope="module")
def built(fixtures_dir):
    out = {}
    for fx in FIXTURES:
        brief = load(fixtures_dir / f"{fx}.yaml")
        options, _, _ = generate(GENERATORS["beam"], brief, 0, {"k": 4}, "beam")
        ok = [o for o in options if o.ok]
        assert ok, fx
        out[fx] = (brief, ok)
    return out


def test_adapter_is_the_only_tgraph_import():
    import pathlib, re
    root = pathlib.Path(tgraph.__file__).parent
    offenders = [str(p.relative_to(root)) for p in root.rglob("*.py")
                 if p.name != "tgraph.py" and re.search(r"topologicpy\.TGraph|import TGraph", p.read_text())]
    assert not offenders, offenders
    assert tgraph.AVAILABLE


@pytest.mark.parametrize("fx", FIXTURES)
def test_wall_node_graph_matches_graph(built, fx):
    _, ok = built[fx]
    r = ok[0].realised
    fast = tgraph.wall_node_graph(r.cc, True)
    assert fast is not None
    names, kinds, coords, edges, verts = _payload_graph(r, True)
    assert fast["order"] == len(verts) and fast["size"] == len(edges)
    assert sorted(n for n, k in zip(fast["names"], fast["kinds"]) if k == "space") == sorted(n for n, k in zip(names, kinds) if k == "space")
    assert sorted(map(tuple, (sorted(round(c, 4) for c in xyz) for xyz in fast["coords"]))) == sorted(map(tuple, (sorted(round(c, 4) for c in xyz) for xyz in coords)))
    # the payload the viewer gets is built from it
    p = graph_payload(r)
    assert p["order"] == fast["order"] and p["size"] == fast["size"] and set(p["kinds"]) <= {"space", "wall"}


def test_door_pairs_match_plan_and_graph(built):
    brief, ok = built["two_levels_stair"]
    for o in ok:
        r = o.realised
        fast = tgraph.door_pairs(r.cc)
        assert fast == _door_pairs_graph(r.cc)
        assert fast == {frozenset(e) for e in door_graph(r.brief, r.doors).edges}
        assert len(fast) == len(r.doors) == 12


def test_tgraph_is_not_slower(built):
    _, ok = built["two_levels_stair"]
    r = ok[0].realised
    def best(fn, n=3):
        ts = []
        for _ in range(n):
            t = time.perf_counter(); fn(); ts.append(time.perf_counter() - t)
        return min(ts)
    fast = best(lambda: tgraph.wall_node_graph(r.cc, True)) + best(lambda: tgraph.door_pairs(r.cc))
    slow = best(lambda: _payload_graph(r, True)) + best(lambda: _door_pairs_graph(r.cc))
    assert fast <= slow, (fast, slow)


def test_distinct_topologies(fixtures_dir):
    brief = load(fixtures_dir / "eight_rooms_corridor.yaml")
    row = run_generator(GENERATORS["beam"], brief, 0, None, "beam")
    assert 1 <= row["distinct_topologies"] <= row["distinct"]
    assert row["distinct_topologies"] < row["distinct"], row  # swaps of the four identical offices collapse
    for fx in ("three_rooms", "two_levels_stair"):
        r2 = run_generator(GENERATORS["beam"], load(fixtures_dir / f"{fx}.yaml"), 0, {"k": 4}, "beam")
        assert 1 <= r2["distinct_topologies"] <= r2["distinct"], (fx, r2)


def test_topology_classes_are_exact(built):
    brief, ok = built["eight_rooms_corridor"]
    expanded, _ = prepare(brief)
    pls = [o.placement for o in ok]
    cls = topology_classes(expanded, pls)
    assert len(cls) == len(pls) and cls[0] == 0
    # renaming two identical offices in a placement keeps its class; mirroring keeps it too
    swapped = dict(pls[0]); swapped["office_a"], swapped["office_b"] = pls[0]["office_b"], pls[0]["office_a"]
    assert topology_classes(expanded, [pls[0], swapped]) == [0, 0]
    # a mirrored plan is the same class
    from spacetope.solve.grid import Box
    width = max(b.x1 for b in pls[0].values())
    mirrored = {n: Box(width - b.x1, b.y, b.z, b.w, b.l, b.h) for n, b in pls[0].items()}
    assert topology_classes(expanded, [pls[0], mirrored]) == [0, 0]
    assert all(isinstance(c, int) for c in cls)


def test_analysis_and_export(built, tmp_path):
    brief, ok = built["two_levels_stair"]
    a = ok[0].analysis
    assert a["connected"] and a["walk_nodes"] == 12 and a["busiest"].startswith("corridor")
    assert set(a["cut_spaces"]) >= {"corridor_0", "corridor_1"}
    assert "analysis" in ok[0].to_dict()
    info = export_pyg(brief, ok, tmp_path / "pyg")
    assert info["written"] and info["graphs"] == len(ok)
    for f in ("nodes.csv", "edges.csv", "graphs.csv"):
        assert (tmp_path / "pyg" / f).exists(), f
    graphs = list(csv.DictReader((tmp_path / "pyg" / "graphs.csv").open()))
    nodes = list(csv.DictReader((tmp_path / "pyg" / "nodes.csv").open()))
    assert len(graphs) == info["graphs"] and len(nodes) == info["nodes"]


def test_api_carries_topology_class_and_analysis():
    from fastapi.testclient import TestClient
    from backend.app.main import app
    client = TestClient(app)
    fx = client.get("/api/fixtures/eight_rooms_corridor").json()
    bid = client.post("/api/brief", json=fx).json()["brief_id"]
    res = client.post("/api/generate", json={"brief_id": bid, "generator": "beam", "seed": 0, "wait": True}).json()
    opts = client.get(f"/api/options/{res['job_id']}").json()
    ok = [o for o in opts if o["ok"]]
    assert ok and all(isinstance(o["topology_class"], int) for o in ok)
    assert len({o["topology_class"] for o in ok}) < len(ok)          # identical-office swaps share a class
    assert all(o["analysis"].get("busiest") == "corridor" for o in ok)
