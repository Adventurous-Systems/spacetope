"""M1 gate: realise, verify (with named failures), score, persistence, viewer."""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from topologicpy.Dictionary import Dictionary
from topologicpy.Topology import Topology

from spacetope.brief import load
from spacetope.io.brep import load as load_realised, load_cellcomplex, save
from spacetope.io.graph import graph_payload
from spacetope.placement import assembly_from_placement, load_placement
from spacetope.realise import realise
from spacetope.score import METRICS, score
from spacetope.solve.grid import Box
from spacetope.verify import verify

pytestmark = [pytest.mark.gate_m1, pytest.mark.slow]


@pytest.fixture(scope="module")
def three(fixtures_dir):
    return load(fixtures_dir / "three_rooms.yaml"), load_placement(fixtures_dir / "placed" / "three_rooms.json")


@pytest.fixture(scope="module")
def eight(fixtures_dir):
    return load(fixtures_dir / "eight_rooms_corridor.yaml"), load_placement(fixtures_dir / "placed" / "eight_rooms_corridor.json")


def test_realise_three_rooms(three):
    brief, placement = three
    r = realise(brief, placement)
    assert r.n_cells == 3
    intent = assembly_from_placement(brief, placement)
    assert len(intent) == 2 and len(r.shared_faces()) == 2
    assert set(r.realised_contacts()) == set(intent.contacts())
    for c in r.cells:
        keys = set(Dictionary.Keys(Topology.Dictionary(c)))
        assert {"name", "program", "w", "l", "h"} <= keys
    assert sorted(r.names) == ["bedroom", "kitchen", "living"]


def test_realise_eight_rooms_corridor(eight):
    brief, placement = eight
    r = realise(brief, placement)
    assert r.n_cells == 9
    intent = assembly_from_placement(brief, placement)
    assert set(intent.contacts()) <= set(r.realised_contacts())
    assert r.build_seconds < 2.0
    rep = verify(brief, placement)
    assert rep.ok, rep.to_dict()
    assert brief.required_pairs() <= {c.pair for c in r.realised_contacts()}


def test_verify_catches_gap(three):
    brief, placement = three
    intent = assembly_from_placement(brief, placement)
    shifted = dict(placement)
    k = placement["kitchen"]
    shifted["kitchen"] = Box(k.x + 1, k.y, k.z, k.w, k.l, k.h)  # +1 mm gap
    rep = verify(brief, shifted, intent)
    assert not rep.ok
    assert rep.failed_contacts == [{"contact": ["kitchen", "-x", "living", "+x"], "cause": "gap"}]


def test_verify_catches_overlap(three):
    brief, placement = three
    intent = assembly_from_placement(brief, placement)
    shifted = dict(placement)
    k = placement["kitchen"]
    shifted["kitchen"] = Box(k.x - 50, k.y, k.z, k.w, k.l, k.h)  # 50 mm into living
    rep = verify(brief, shifted, intent)
    assert not rep.ok
    assert [f["cause"] for f in rep.failed_contacts] == ["overlap"]
    assert not rep.checks["cell_count"][0] or not rep.checks["no_slivers"][0]


def test_verify_catches_missing(three):
    brief, placement = three
    intent = assembly_from_placement(brief, placement)
    moved = dict(placement)
    b = placement["bedroom"]
    moved["bedroom"] = Box(b.x, b.y + 500, b.z, b.w, b.l, b.h)  # detached
    rep = verify(brief, moved, intent)
    assert not rep.ok
    assert rep.failed_contacts == [{"contact": ["bedroom", "-y", "living", "+y"], "cause": "missing"}]


def test_scores_bounded(eight):
    brief, placement = eight
    r = realise(brief, placement)
    s = score(r)
    assert set(s) == set(METRICS)
    assert s["adjacency"] == 1.0
    assert 0 <= s["deviation"] <= 1 and 0 < s["compactness"] <= 1 and s["circulation"] >= 0 and s["stacking"] == 0.0


def test_persistence_roundtrip(tmp_path, eight):
    brief, placement = eight
    r = realise(brief, placement)
    sig = r.realised_assembly().signature()
    paths = save(r, tmp_path / "eight")
    assert all(p.exists() for p in paths.values())
    cc = load_cellcomplex(tmp_path / "eight")
    names = sorted(Dictionary.ValueAtKey(Topology.Dictionary(c), "name") for c in Topology.Cells(cc))
    assert names == sorted(placement)
    again = load_realised(tmp_path / "eight")
    assert again.realised_assembly().signature() == sig


def test_graph_payload(eight):
    brief, placement = eight
    r = realise(brief, placement)
    p = graph_payload(r)
    assert p["kinds"].count("space") == 9
    assert p["kinds"].count("wall") == len(r.shared_faces())
    # direct cell-cell edges (1 per shared face) + wall-node edges (2 per shared face): flags are additive
    assert p["size"] == 3 * len(r.shared_faces())
    assert p["components"] == 1


def test_html_written(tmp_path, three):
    brief, placement = three
    from spacetope.viz.plotly import write_html
    r = realise(brief, placement)
    out = write_html(r, tmp_path / "three.html")
    assert out.exists() and out.stat().st_size < 200_000
    assert 'cdn.plot.ly' in out.read_text()


def test_cli(tmp_path, fixtures_dir):
    cmd = [sys.executable, "-m", "spacetope.cli", "realise", str(fixtures_dir / "three_rooms.yaml"),
           str(fixtures_dir / "placed" / "three_rooms.json"), "--html", str(tmp_path / "o.html"), "--save", str(tmp_path / "o")]
    res = subprocess.run(cmd, capture_output=True, text=True, cwd=str(fixtures_dir.parent))
    assert res.returncode == 0, res.stderr
    out = json.loads(res.stdout)  # stdout is the JSON alone; library messages go to stderr (STATUS §2.6, fix 2)
    assert out["verify"]["ok"] and out["scores"]["adjacency"] == 1.0
    assert (tmp_path / "o.graph.json").exists()


def test_no_slivers_tolerates_rounding_ties():
    """review 2026-09-13 #8: odd dimensions at odd origins put a volume on a 6-decimal rounding tie."""
    from spacetope.brief import Brief
    brief = Brief.from_dict({"name": "tie", "spaces": [{"name": "a", "w": 8.737, "l": 7.219, "h": 2.5},
                                                       {"name": "b", "w": 8.737, "l": 7.219, "h": 2.5}]})
    placement = {"a": Box(20820, 324, 9529, 8737, 7219, 2500), "b": Box(20820 + 8737, 324, 9529, 8737, 7219, 2500)}
    rep = verify(brief, placement)
    assert rep.checks["no_slivers"][0], rep.checks["no_slivers"][1]


def test_cli_realise_accepts_a_circulation_brief(tmp_path, fixtures_dir):
    """review 2026-09-13 #10: the placement names the expanded spaces, so realise must expand too."""
    gen = subprocess.run([sys.executable, "-m", "spacetope.cli", "generate", str(fixtures_dir / "two_levels_stair.yaml"),
                          "--params", '{"k": 1}', "--out", str(tmp_path / "g"), "--save"],
                         capture_output=True, text=True, cwd=str(fixtures_dir.parent))
    assert gen.returncode == 0, gen.stderr[-500:]
    assert json.loads(gen.stdout)["options"]
    index = json.loads((tmp_path / "g" / "options.json").read_text())
    assert index["kernel"]["backend"] in ("topologic_core", "pythonocc")
    res = subprocess.run([sys.executable, "-m", "spacetope.cli", "realise", str(fixtures_dir / "two_levels_stair.yaml"),
                          str(tmp_path / "g" / "option_00.placement.json")], capture_output=True, text=True,
                         cwd=str(fixtures_dir.parent))
    assert res.returncode == 0, res.stderr[-500:]
    assert json.loads(res.stdout)["verify"]["ok"]
