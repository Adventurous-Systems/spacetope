"""M15b gate: chained (L, U) corridors. A level's spine may be several boxes; a room reaches it by a door to
whichever segment it touches, so contacts to the spine name are dropped with a warning (PLAN §6, option a)."""
import pathlib

import pytest
import yaml

from spacetope.brief import Brief, corridor_names, corridor_segments, load
from spacetope.circulation import prepare
from spacetope.doors import corridor_opening_mm, door_graph
from spacetope.pipeline import generate
from spacetope.solve.grid import touches
from spacetope.solve.registry import GENERATORS

pytestmark = [pytest.mark.gate_m15, pytest.mark.slow]
HSIDES = ("+x", "-x", "+y", "-y")
BUDGET = {"k": 2, "time_limit": 120.0, "per_solve_max": 60.0}


def corner(placement, a, b) -> int:
    return max(touches(placement[a], placement[b], s)[0] for s in HSIDES)


def test_expansion_chains_the_spine_and_explains_dropped_contacts(fixtures_dir):
    raw = yaml.safe_load((fixtures_dir / "school_l_corridor.yaml").read_text())
    brief = Brief.from_dict({**raw, "contacts": raw["contacts"] + [["corridor_0", "class_1"]]})
    assert corridor_segments(brief) == 2 and corridor_names(brief, 0) == ["corridor_0_1", "corridor_0_2"]
    expanded, warnings = prepare(brief)
    corridors = [s.name for s in expanded.spaces if s.program == "corridor"]
    assert corridors == ["corridor_0_1", "corridor_0_2"]
    assert ("corridor_0_1", "corridor_0_2") in expanded.contacts
    assert not any("corridor_0" in c for c in expanded.contacts for c in c if c == "corridor_0")
    assert [w.code for w in warnings] == ["corridor_chain"] and "corridor_0 – class_1" in warnings[0].message
    # the segments meet over the full corridor width: an opening, not a door
    assert corridor_opening_mm(expanded, "corridor_0_1", "corridor_0_2") == 2400
    assert corridor_opening_mm(expanded, "corridor_0_1", "class_1") == 0


def test_one_straight_corridor_cannot_serve_this_brief(fixtures_dir):
    """Why the fixture chains its corridor: the rooms need more frontage, narrow side on, than the two sides of the
    longest straight corridor the envelope allows."""
    brief, _ = prepare(load(fixtures_dir / "school_l_corridor.yaml"))
    demand = sum(min(s.nominal_mm("w"), s.nominal_mm("l")) for s in brief.spaces if s.program == "room")
    straight = 2 * max(int(brief.envelope["w"] * 1000), int(brief.envelope["l"] * 1000))
    assert demand > straight, (demand, straight)


def test_cpsat_turns_the_corner_and_verifies(fixtures_dir):
    brief = load(fixtures_dir / "school_l_corridor.yaml")
    options, t_gen, _ = generate(GENERATORS["cpsat"], brief, 0, BUDGET, "cpsat", build="top", keep=2)
    ok = [o for o in options if o.ok]
    assert len(ok) == len(options) >= 2, [{k: d for k, (p, d) in o.report.checks.items() if not p} for o in options if not o.ok]
    assert t_gen < 150.0, t_gen
    for o in ok:
        r = o.realised
        a, b = "corridor_0_1", "corridor_0_2"
        assert corner(o.placement, a, b) == 2400                                   # end on, the full corridor width
        pa, pb = o.placement[a], o.placement[b]
        assert (pa.w >= pa.l) != (pb.w >= pb.l)                                    # and on different axes: a corner
        assert o.scores["adjacency"] == 1.0 and o.scores["vertical"] == 1.0
        rooms = [s.name for s in r.brief.spaces if s.program == "room"]
        assert len({d.a for d in r.doors} | {d.b for d in r.doors}) >= len(rooms)
        g = door_graph(r.brief, r.doors, o.placement)
        assert g.has_edge(a, b) and g.edges[a, b]["kind"] == "opening"              # walkable without a door
        assert o.analysis["connected"]


def test_shafts_reach_a_segment_on_every_level_they_serve(fixtures_dir):
    raw = yaml.safe_load((fixtures_dir / "school_l_corridor.yaml").read_text())
    rooms = [dict(s) for s in raw["spaces"] if s["name"].startswith("class_")][:6]
    for i, s in enumerate(rooms):
        s["wishes"] = {"level": i % 2, "exterior": True}
    brief = Brief.from_dict({"name": "l_two_levels", "levels": 2, "level_height": 3.5,
                             "envelope": {"w": 26, "l": 24, "h": 7}, "spaces": rooms, "contacts": [],
                             "circulation": {"corridor": {"w": 2.4, "l": 12, "segments": 2},
                                             "stairs": [{"name": "stair", "w": 3, "l": 5.5}],
                                             "lifts": [{"name": "lift", "w": 2.4, "l": 2.4}]}})
    options, _, _ = generate(GENERATORS["cpsat"], brief, 0, BUDGET, "cpsat", build="top", keep=2)
    ok = [o for o in options if o.ok]
    assert len(ok) == len(options) >= 2, [{k: d for k, (p, d) in o.report.checks.items() if not p} for o in options if not o.ok]
    for o in ok:
        for shaft in ("stair", "lift"):
            for level in (0, 1):
                assert any(d.level == level and shaft in (d.a, d.b) for d in o.realised.doors), (shaft, level, o.analysis)
        # One route, not two. With a chained spine the stair and the lift may land on different segments, and a
        # route between levels then runs through the opening between them, which both share — so two shafts stop
        # guaranteeing two independent ways down (measured 2026-09-21; CP-SAT is not seed-deterministic, so this
        # depends on the run). What must hold is that every level keeps a way down.
        assert o.analysis["connected"] and o.analysis["vertical_routes"] >= 1 and o.analysis["stair_routes"] >= 1
        assert o.scores["vertical"] == 1.0


def test_beam_keeps_the_corner_perpendicular_when_it_places_one(fixtures_dir):
    """The beam is unreliable on chained spines (one seed in four; PLAN §5 2026-09-20), so this pins the geometry
    rule rather than a success rate: whenever it does place both segments, they meet end on and turn."""
    brief, _ = prepare(load(fixtures_dir / "school_l_corridor.yaml"))
    seen = 0
    for seed in (0, 1, 2, 3):
        for pl in GENERATORS["beam"](brief, None, seed):
            a, b = "corridor_0_1", "corridor_0_2"
            if corner(pl, a, b):
                seen += 1
                assert corner(pl, a, b) == 2400
                assert (pl[a].w >= pl[a].l) != (pl[b].w >= pl[b].l)
    assert seen > 0
