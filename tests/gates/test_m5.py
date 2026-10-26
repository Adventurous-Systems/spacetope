"""M5 gate: API contract, GLB node naming, export round trip."""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.main import ROOT, app
from spacetope.io.brep import load_cellcomplex
from spacetope.placement import assembly_from_placement
from spacetope.brief import Brief

pytestmark = [pytest.mark.gate_m5, pytest.mark.slow]


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


@pytest.fixture(scope="module")
def job(client):
    fx = client.get("/api/fixtures/two_levels_stair").json()
    bid = client.post("/api/brief", json=fx).json()["brief_id"]
    res = client.post("/api/generate", json={"brief_id": bid, "generator": "beam", "seed": 0, "wait": True}).json()
    assert res["status"] == "done", res
    return res


def test_health_and_fixtures(client):
    assert client.get("/api/health").json()["ok"]
    names = {f["name"] for f in client.get("/api/fixtures").json()}
    assert {"three_rooms", "eight_rooms_corridor", "two_levels_stair", "office_30"} <= names
    assert client.post("/api/brief", json={"spaces": [{"name": "a", "w": -1, "l": 1, "h": 1}]}).status_code == 422


def test_generate_and_options(client, job):
    assert job["verified"] == job["options"] >= 3
    opts = client.get(f"/api/options/{job['job_id']}").json()
    assert len(opts) >= 3
    for o in opts:
        assert o["ok"] and "scores" in o and "signature" in o and o["glb_url"].startswith("/static/")
    detail = client.get(f"/api/options/{job['job_id']}/0").json()
    assert detail["graph"]["order"] > 0 and len(detail["graph"]["coords_yup"]) == detail["graph"]["order"]
    assert len(detail["cells"]) == 12 and all("name" in c for c in detail["cells"])


def test_glb_has_one_node_per_cell(client, job):
    import trimesh
    opts = client.get(f"/api/options/{job['job_id']}").json()
    glb = client.get(opts[0]["glb_url"]).content
    scene = trimesh.load(trimesh.util.wrap_as_stream(glb), file_type="glb")
    names = {n for n in scene.graph.nodes_geometry}
    assert {n for n in names if n.startswith("cell_")} == {f"cell_{i}" for i in range(12)}, names
    # stair 2 + lift 2 (one door per served level) + one door per room (8)
    assert len([n for n in names if n.startswith("door_")]) == opts[0]["doors"] == 12, names


def test_select_roundtrip(client, job):
    res = client.post("/api/select", json={"job_id": job["job_id"], "index": 0, "name": "m5_test"}).json()
    stem = ROOT / res["selected"]["brep"]
    assert stem.exists()
    cc = load_cellcomplex(stem.with_suffix(""))
    from topologicpy.Dictionary import Dictionary
    from topologicpy.Topology import Topology
    names = sorted(Dictionary.ValueAtKey(Topology.Dictionary(c), "name") for c in Topology.Cells(cc))
    assert len(names) == 12 and None not in names
    opt = json.loads((stem.with_suffix(".option.json")).read_text())
    brief = Brief.from_dict(json.loads(stem.with_suffix(".brief.json").read_text()))
    from spacetope.solve.grid import Box
    placement = {n: Box.from_dict(b) for n, b in opt["placement"].items()}
    assert [list(s) for s in assembly_from_placement(brief, placement).signature()] == opt["signature"]



def test_placement_glb_matches_topology_cells(fixtures_dir):
    """The fast GLB (built from placement boxes) must equal the built topologic cells, cell by cell."""
    import numpy as np
    import trimesh
    from spacetope.brief import load
    from spacetope.io.glb import scene
    from spacetope.placement import load_placement
    from spacetope.realise import realise
    brief = load(fixtures_dir / "eight_rooms_corridor.yaml")
    r = realise(brief, load_placement(fixtures_dir / "placed" / "eight_rooms_corridor.json"))
    fast, slow = scene(r, "placement"), scene(r, "topology")
    assert set(fast.geometry) == set(slow.geometry) == {f"cell_{i}" for i in range(r.n_cells)}
    for name, m in fast.geometry.items():
        t = slow.geometry[name]
        assert np.allclose(m.bounds, t.bounds, atol=1e-6), name
        assert m.is_watertight and m.volume > 0, name
        assert abs(m.volume - abs(t.volume)) < 1e-6, name


def test_select_rejects_paths_and_keeps_dotted_names(client, job):
    """review 2026-09-13 #1: the export name is a file stem, never a path."""
    for bad in ("../../tmp/pwn", "a/b", "..", ".hidden", "x" * 70):
        res = client.post("/api/select", json={"job_id": job["job_id"], "index": 0, "name": bad})
        assert res.status_code == 422, (bad, res.status_code)
    res = client.post("/api/select", json={"job_id": job["job_id"], "index": 0, "name": "v1-2"})
    assert res.status_code == 200 and res.json()["selected"]["brep"].endswith("selected/v1-2.brep")


def test_job_view_is_safe_while_the_worker_updates(client):
    """review 2026-09-13 #7: polling must never see a dict that changes size mid-iteration."""
    import threading
    from backend.app import main as api
    api.JOBS["poll"] = {"job_id": "poll", "status": "running"}
    stop = threading.Event()
    def churn():
        n = 0
        while not stop.is_set():
            with api._lock:
                api.JOBS["poll"].update({f"k{n % 50}": n})
            n += 1
    t = threading.Thread(target=churn); t.start()
    try:
        for _ in range(3000):
            api._job_view("poll")
    finally:
        stop.set(); t.join(); api.JOBS.pop("poll", None)
