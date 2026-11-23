"""M27 gate: field briefs. A site, a path, a schedule; contacts emerge; options each do one aspect best (PLAN §4.11)."""
import time

import pytest

from spacetope import field
from spacetope.brief import Brief, load
from spacetope.tessellate import KINDS

pytestmark = pytest.mark.gate_m27
SEEDS = range(6)


@pytest.fixture(scope="module")
def club(fixtures_dir):
    return load(fixtures_dir / "field" / "club.yaml")


@pytest.fixture(scope="module")
def pavilion(fixtures_dir):
    return load(fixtures_dir / "field" / "pavilion.yaml")


@pytest.fixture(scope="module")
def sweep(club):
    return {(k, s): field.solve(club, k, s) for k in KINDS for s in SEEDS}


def test_brief_round_trips_and_stacks_up(club):
    again = Brief.from_dict(club.to_dict())
    assert again.paths == club.paths and again.site == club.site
    f = field.prepare(club)
    assert f.n == 2, "1450 m2 of rooms on 1300 m2 of ground: the schedule goes up a level"
    assert {c.program for c in f.cells} == {"corridor", "stair"}
    assert f.levels["spa"] == f.levels["jacuzzi"], "rooms that must share a wall share a level"
    assert f.fronts == {"reception": f"walk_{f.levels['reception']}", "hall": f"walk_{f.levels['hall']}"}


def test_bad_briefs_are_named(club):
    d = club.to_dict()
    d["paths"] = [{"name": "walk", "points": [[1, 1]]}]
    with pytest.raises(field.FieldInvalid, match="two points"):
        field.prepare(Brief.from_dict(d))
    d = club.to_dict()
    d["site"] = {"boundary": [[0, 0], [1, 0], [1, 1]], "setback": 5}
    with pytest.raises(field.FieldInvalid, match="setback"):
        field.prepare(Brief.from_dict(d))


def test_a_path_through_the_volume(pavilion):
    f = field.prepare(pavilion)
    by = {c.name: c for c in f.cells}
    assert (by["route_0"].k0, by["route_0"].k1) == (0, 0) and (by["route_1"].k0, by["route_1"].k1) == (1, 1)
    assert (by["route_stair"].program, by["route_stair"].k0, by["route_stair"].k1) == ("stair", 0, 1)
    for kind in KINDS:
        r = field.solve(pavilion, kind, 0)
        assert r["ok"], (kind, {k: c["detail"] for k, c in r["checks"].items() if not c["passed"]})
        assert r["scores"]["vertical"] == 1.0, "ground and upper rooms are joined through the stair"


def test_every_solve_is_whole_and_keeps_the_hard_wishes(sweep):
    for key, r in sweep.items():
        for check in ("complete", "no_overlaps"):
            assert r["checks"][check]["passed"], (key, r["checks"][check]["detail"])
        if key[0] != "hex":
            assert r["checks"]["affinities"]["passed"], (key, r["checks"]["affinities"]["detail"])
    # a honeycomb wall is one module side long, so a 0.9 m straight wall between two rooms is not certain (stated limit)
    assert sum(1 for s in SEEDS if sweep[("hex", s)]["checks"]["affinities"]["passed"]) >= 4


def test_reach_is_measured_not_assumed(sweep):
    passing = sum(1 for r in sweep.values() if r["ok"])
    assert passing >= 10, f"{passing} of {len(sweep)} solves pass every kernel-free check (measured 12 on 2026-11-23)"
    assert sum(1 for s in SEEDS if sweep[("voronoi", s)]["ok"]) >= 4
    failed = [r for r in sweep.values() if not r["ok"]]
    assert failed and all("no door-wide wall to the path" in r["checks"]["reach"]["detail"] for r in failed), "a failure says which room"


def test_areas_follow_the_tessellation(sweep):
    mean = {k: sum(sweep[(k, s)]["scores"]["area_deviation"] for s in SEEDS) / len(SEEDS) for k in KINDS}
    assert mean["slice"] < 0.06 and mean["power"] < 0.22 and mean["hex"] < 0.16
    assert mean["voronoi"] > mean["power"], "plain Voronoi does not look at the areas"
    reg = {k: sum(sweep[(k, s)]["scores"]["regularity"] for s in SEEDS) / len(SEEDS) for k in KINDS}
    assert reg["slice"] > reg["voronoi"] > reg["hex"]


def test_same_seed_same_plan_and_fast_enough_to_drag(club, sweep):
    t0 = time.perf_counter()
    again = field.solve(club, "power", 0)
    assert time.perf_counter() - t0 < 1.5
    assert again["cells"] == sweep[("power", 0)]["cells"]
    assert max(sum(r["ms"].values()) for r in sweep.values()) < 1500


def test_a_pinned_room_stays_where_it_is_put(club, sweep):
    pos = {n: tuple(v) for n, v in sweep[("power", 0)]["positions"].items()}
    pos["gym"] = (pos["gym"][0] + 1.5, pos["gym"][1] - 1.0)
    r = field.solve(club, "power", 0, positions=pos, pins=("gym",))
    assert tuple(r["positions"]["gym"]) == pos["gym"]
    assert r["cells"] != sweep[("power", 0)]["cells"]


def test_moving_the_path_moves_the_mass(club, sweep):
    d = club.to_dict()
    d["paths"][0]["points"] = [[6, 6], [30, 20], [30, 52]]
    r = field.solve(Brief.from_dict(d), "power", 0)
    assert r["cells"] != sweep[("power", 0)]["cells"]
    assert all(r["checks"][c]["passed"] for c in ("complete", "no_overlaps"))


@pytest.mark.slow
def test_options_each_do_one_aspect_best(pavilion):
    opts, info = field.options(pavilion, seeds=(0, 1), polish_steps=3)
    assert info["candidates"] == 2 * len(KINDS) and info["passed"] >= 5
    labels = [c for o in opts for c in o.champion]
    assert sorted(labels) == sorted(["balance", *field.ASPECTS]), "one champion per aspect, and the best balance"
    pool = [field._candidate(field.prepare(pavilion, s), k, s, field.relax(field.prepare(pavilion, s), s), {}) for s in (0, 1) for k in KINDS]
    for o in opts:
        assert o.ok and o.report is not None and o.report.ok, o.report.to_dict() if o.report else o.checks
        for label in o.champion:
            if label != "balance":
                key, sign = field.ASPECTS[label]
                assert all(sign * o.scores[key] >= sign * c.scores[key] - 1e-9 for c in pool if c.ok)
