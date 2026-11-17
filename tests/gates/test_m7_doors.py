# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Adventurous Systems

"""M7.4 gate: doors where access is needed (plan §3.5, §6 M7.4)."""
from collections import Counter

import pytest
from topologicpy.Dictionary import Dictionary
from topologicpy.Topology import Topology

from spacetope.brief import Brief, load
from spacetope.circulation import prepare
from spacetope.doors import plan_doors
from spacetope.io.brep import load_cellcomplex, save
from spacetope.io.glb import scene
from spacetope.pipeline import generate
from spacetope.realise import attach_doors, realise
from spacetope.solve.grid import Box
from spacetope.solve.registry import GENERATORS
from spacetope.verify import check_doors

pytestmark = [pytest.mark.gate_m7, pytest.mark.slow]
FIXTURES = ("two_levels_stair", "three_levels_core")
CASES = [(f, g, s) for f in FIXTURES for g in ("beam", "cpsat") for s in (0, 1, 2)]


@pytest.fixture(scope="module")
def runs(fixtures_dir):
    out = {}
    for fixture, gen, seed in CASES:
        brief, _ = prepare(load(fixtures_dir / f"{fixture}.yaml"))
        options, _, _ = generate(GENERATORS[gen], brief, seed, None, gen)
        out[(fixture, gen, seed)] = (brief, options)
    return out


def test_every_option_passes_the_door_check(runs):
    for case, (brief, options) in runs.items():
        assert options, case
        for o in options:
            assert o.realised.door_problems == [], (case, [p.message for p in o.realised.door_problems])
            passed, detail = o.report.checks["doors"]
            assert passed, (case, detail)
            assert o.ok, (case, {k: d for k, (p, d) in o.report.checks.items() if not p})


def test_door_counts_follow_the_rules(runs):
    for case, (brief, options) in runs.items():
        rooms = [s for s in brief.spaces if s.program == "room"]
        marked_room_pairs = [p for p in brief.door_pairs if all(brief.space(x).program == "room" for x in p)]
        expected = Counter()
        for s in brief.spaces:
            if s.is_shaft:
                expected["stair" if s.program == "stair" else "lift"] += s.serves[1] - s.serves[0] + 1
        expected["room"] = len(rooms) + len(marked_room_pairs)
        for o in options:
            got = Counter(d.kind for d in o.realised.doors)
            assert got == expected, (case, got, expected)
            per_room = Counter(d.a for d in o.realised.doors if d.kind == "room" and brief.space(d.b).program == "corridor")
            assert all(per_room[r.name] == 1 for r in rooms), (case, per_room)
            for k in range(brief.levels or 1):
                assert any(d.kind == "stair" and d.level == k for d in o.realised.doors), (case, k)
            assert o.scores["vertical"] == 1.0, case


def test_doors_survive_export_and_reload(runs, tmp_path):
    brief, options = runs[("three_levels_core", "beam", 0)]
    r = options[0].realised
    paths = save(r, tmp_path / "opt")
    assert paths["doors"].exists()
    cc = load_cellcomplex(tmp_path / "opt")
    apertures = Topology.Apertures(cc, subTopologyType="face")
    assert len(apertures) == len(r.doors)
    names = sorted(Dictionary.ValueAtKey(Topology.Dictionary(a), "name") for a in apertures)
    assert names == sorted(d.name for d in r.doors)


def test_glb_doors_are_openings_not_slabs(runs):
    """Each door is the aperture face (zero thickness) and its opening is cut out of both cells."""
    brief, options = runs[("two_levels_stair", "beam", 0)]
    r = options[0].realised
    sc = scene(r)
    door_nodes = [n for n in sc.geometry if n.startswith("door_")]
    assert len(door_nodes) == len(r.doors)
    for j, d in enumerate(r.doors):
        mesh = sc.geometry[f"door_{j}"]
        assert abs(mesh.area - d.width_mm * d.height_mm / 1e6) < 1e-6, d.name   # a quad, not a box
        assert not mesh.is_watertight, d.name
    for i, name in enumerate(r.names):
        b = r.placement[name]
        surface = 2 * (b.w * b.l + b.w * b.h + b.l * b.h) / 1e6
        opening = sum(d.width_mm * d.height_mm for d in r.doors if name in (d.a, d.b)) / 1e6
        assert abs(sc.geometry[f"cell_{i}"].area - (surface - opening)) < 1e-6, name


def test_room_without_enough_wall_gets_a_named_problem():
    brief, _ = prepare(Brief.from_dict({
        "name": "narrow", "levels": 1, "level_height": 3,
        "circulation": {"corridor": {"w": 1.8, "l": 10}},
        "spaces": [{"name": "office", "w": 4, "l": 3, "h": 3, "program": "room"}],
        "contacts": [["corridor_0", "office"]]}))
    placement = {"corridor_0": Box(0, 0, 0, 1800, 10000, 3000), "office": Box(1800, 9100, 0, 4000, 3000, 3000)}
    doors, problems = plan_doors(brief, placement)
    assert doors == []
    assert [p.message for p in problems] == ["office needs 1.1 m of shared wall with corridor_0 on level 0 for its door; it has 0.9 m"]


def test_missing_door_is_named(runs):
    brief, options = runs[("two_levels_stair", "beam", 0)]
    placement = options[0].placement
    r = realise(brief, placement, with_doors=False)
    partial = [d for d in r.doors if not (d.a == "stair" and d.b == "corridor_1")]
    assert len(partial) == len(r.doors) - 1
    r.cc = attach_doors(r.cc, partial)
    passed, detail = check_doors(brief, r)
    assert not passed and "missing door: corridor_1–stair" in detail, detail


def test_doors_find_corridors_by_level_whatever_their_name():
    """review 2026-09-13 #4: explicit corridors named hall_ground / hall_first passed validation, then
    door planning looked for corridor_0 and failed every option."""
    brief, _ = prepare(Brief.from_dict({
        "name": "halls", "levels": 2, "level_height": 3,
        "circulation": {"stairs": [{"name": "stair", "w": 3, "l": 5}]},
        "spaces": [{"name": "hall_ground", "w": 1.8, "l": 10, "h": 3, "program": "corridor", "wishes": {"level": 0}},
                   {"name": "hall_first", "w": 1.8, "l": 10, "h": 3, "program": "corridor", "wishes": {"level": 1}},
                   {"name": "office", "w": 4, "l": 3, "h": 3, "program": "room", "wishes": {"level": 0}}],
        "contacts": [["hall_ground", "office"], ["stair", "hall_ground"], ["stair", "hall_first"]]}))
    placement = {"stair": Box(0, 0, 0, 3000, 5000, 6000),
                 "hall_ground": Box(3000, 0, 0, 1800, 10000, 3000), "hall_first": Box(3000, 0, 3000, 1800, 10000, 3000),
                 "office": Box(4800, 0, 0, 4000, 3000, 3000)}
    doors, problems = plan_doors(brief, placement)
    assert problems == []
    assert sorted((d.a, d.b, d.level) for d in doors) == [("office", "hall_ground", 0), ("stair", "hall_first", 1), ("stair", "hall_ground", 0)]
