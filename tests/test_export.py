# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Adventurous Systems

"""OBJ and JSON export of realised complexes come from topologic's mesh data and match the placement."""
import json

import numpy as np
import pytest
import trimesh

from spacetope.brief import load
from spacetope.circulation import prepare
from spacetope.cli import main
from spacetope.io.mesh import json_payload, write_json, write_obj
from spacetope.placement import load_placement
from spacetope.realise import realise

pytestmark = pytest.mark.slow


@pytest.fixture(scope="module")
def eight(fixtures_dir):
    brief, _ = prepare(load(fixtures_dir / "eight_rooms_corridor.yaml"))
    return realise(brief, load_placement(fixtures_dir / "placed" / "eight_rooms_corridor.json"))


def test_json_is_the_cell_complex(eight):
    p = json_payload(eight)
    assert p["format"] == "spacetope-cellcomplex" and p["units"] == "m" and p["up"] == "z"
    assert p["n_cells"] == len(p["cells"]) == eight.n_cells == len(eight.brief.spaces)
    assert sorted(c["name"] for c in p["cells"]) == sorted(eight.names)
    nf = len(p["faces"])
    for c in p["cells"]:
        assert c["faces"] and all(0 <= f < nf for f in c["faces"])
        assert len(c["faces"]) >= 6  # a box has six faces; shared walls may be split
        assert c["dictionary"].get("name") == c["name"]
    for f in p["faces"]:
        assert len(f) >= 3 and all(0 <= i < p["n_vertices"] for i in f)
    # every realised contact is one face owned by exactly two cells
    pairs = {frozenset((p["cells"][s["cells"][0]]["name"], p["cells"][s["cells"][1]]["name"])) for s in p["shared_faces"]}
    contacts = {frozenset((c[0], c[2])) for c in p["contacts"]}
    assert contacts <= pairs, contacts - pairs
    intended = {frozenset(c) for c in eight.brief.contacts}
    assert intended <= contacts  # realised ⊇ intended (verify's rule); extra shared walls are fine


def _parse_obj(text: str) -> dict[str, list[list[int]]]:
    """object name -> list of faces (0-based vertex indices), plus the vertex table under key '__v'."""
    verts, objects, cur = [], {}, None
    for ln in text.splitlines():
        parts = ln.split()
        if not parts:
            continue
        if parts[0] == "v":
            verts.append([float(x) for x in parts[1:4]])
        elif parts[0] == "o":
            cur = parts[1]; objects[cur] = []
        elif parts[0] == "f":
            objects[cur].append([int(x) - 1 for x in parts[1:]])
    objects["__v"] = verts
    return objects


def test_obj_objects_match_placement(eight, tmp_path):
    path = write_obj(eight, tmp_path / "eight.obj")
    text = path.read_text()
    assert text.startswith("# spacetope-cellcomplex")
    assert (tmp_path / "eight.mtl").exists() and "mtllib eight.mtl" in text
    objs = _parse_obj(text)
    verts = np.array(objs.pop("__v"))
    names = list(objs)
    assert names[:eight.n_cells] == [f"cell_{i}" for i in range(eight.n_cells)]
    assert len(names) == eight.n_cells + len(eight.doors)
    for c in json_payload(eight)["cells"]:
        faces = objs[f"cell_{c['index']}"]
        assert len(faces) >= 6 and all(0 <= i < len(verts) for f in faces for i in f)
        pts = verts[sorted({i for f in faces for i in f})]
        b = c["box"]
        assert np.allclose(pts.min(axis=0), [b["x"], b["y"], b["z"]], atol=1e-3), c["name"]
        assert np.allclose(pts.max(axis=0), [b["x"] + b["w"], b["y"] + b["l"], b["z"] + b["h"]], atol=1e-3), c["name"]
    # the file is also loadable by a generic mesh library, with one geometry per object
    sc = trimesh.load(path, force="scene", group_material=False, split_object=True)
    assert len(sc.geometry) == eight.n_cells + len(eight.doors)


def test_cli_export(fixtures_dir, tmp_path):
    rc = main(["export", "--brief", str(fixtures_dir / "three_rooms.yaml"),
               "--placement", str(fixtures_dir / "placed" / "three_rooms.json"),
               "--obj", str(tmp_path / "t.obj"), "--json", str(tmp_path / "t.json")])
    assert rc == 0
    d = json.loads((tmp_path / "t.json").read_text())
    assert d["n_cells"] == 3 and sorted(c["name"] for c in d["cells"]) == ["bedroom", "kitchen", "living"]
    assert (tmp_path / "t.obj").read_text().count("\no cell_") == 3
