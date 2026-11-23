"""M25 gate: one measure for boxes and cells (PLAN §4.11). On integer boxes `layout` reads what the box code reads."""
import time
from pathlib import Path

import networkx as nx
import pytest
from shapely.geometry import Polygon

from spacetope import affinity, layout
from spacetope.brief import Brief, Space, load
from spacetope.circulation import BriefInvalid, prepare
from spacetope.doors import access_graph, door_graph, plan_doors
from spacetope.layout import Prism, Table, conform, from_placement
from spacetope.score import cheap_scores
from spacetope.solve.grid import Box
from spacetope.solve.registry import GENERATORS

pytestmark = pytest.mark.gate_m25
ROOT = Path(__file__).resolve().parents[2]
PER_BRIEF = 4


def _briefs():
    out = []
    for p in sorted(list((ROOT / "fixtures").glob("*.yaml")) + list((ROOT / "fixtures" / "site").glob("*.yaml"))):
        try:
            out.append((p.relative_to(ROOT / "fixtures").as_posix(), prepare(load(p))[0]))
        except BriefInvalid:
            continue   # a brief that does not validate has no placements to compare
    return out


BRIEFS = _briefs()


@pytest.fixture(scope="module")
def placements():
    return {name: GENERATORS["beam"](brief, None, 0)[:PER_BRIEF] for name, brief in BRIEFS}


@pytest.mark.parametrize("name,brief", BRIEFS, ids=[n for n, _ in BRIEFS])
def test_boxes_read_the_same(name, brief, placements):
    assert placements[name], "beam gave nothing to compare"
    for pl in placements[name]:
        t = Table(from_placement(pl))
        assert layout.affinity(brief, t) == affinity.measure(brief, pl)
        box, cell = cheap_scores(brief, pl), layout.scores(brief, t)
        for k in layout.BOX_EQUAL:
            assert cell[k] == pytest.approx(box[k], abs=1e-6), k
        walk = door_graph(brief, plan_doors(brief, pl)[0], pl) if brief.circulation else access_graph(brief, pl)
        assert {frozenset(e) for e in t.walk(brief).edges} == {frozenset(e) for e in walk.edges}


def test_hard_only_report_matches(placements):
    name, brief = next((n, b) for n, b in BRIEFS if affinity.has_hard(b))
    for pl in placements[name]:
        assert layout.affinity(brief, from_placement(pl), strengths=affinity.HARD) == affinity.measure(brief, pl, strengths=affinity.HARD)


def test_conform_is_idempotent_and_crosses_levels():
    # the lift's wall is split by a ground-floor neighbour; the room above must get that vertex through the lift
    pl = {"lift": Box(0, 7000, 0, 2400, 2400, 7000), "upper": Box(0, 0, 3500, 8000, 7000, 3500),
          "lower_a": Box(0, 0, 0, 1200, 7000, 3500), "lower_b": Box(1200, 0, 0, 6800, 7000, 3500)}
    once = conform(from_placement(pl))
    assert {n: p.to_dict() for n, p in conform(once).items()} == {n: p.to_dict() for n, p in once.items()}
    t = Table(once, conformed=True)
    assert t.touch("lift", "upper") == (2400.0, 3500)
    assert t.contact("lift", "upper") == 2400 * 3500
    assert t.vertical("lower_b", "upper") == 6800 * 7000


def test_cells_that_are_not_boxes():
    # two rooms meeting on a slanted wall, turned 30 degrees anticlockwise; north is turned with them
    import math
    c, s = math.cos(math.radians(30)), math.sin(math.radians(30))
    turn = lambda pts: [(1000 * (x * c - y * s), 1000 * (x * s + y * c)) for x, y in pts]  # noqa: E731
    lay = {"a": Prism(Polygon(turn([(0, 0), (5, 0), (6, 4), (0, 4)])), 0, 3000),
           "b": Prism(Polygon(turn([(5, 0), (10, 0), (10, 4), (6, 4)])), 0, 3000)}
    brief = Brief("two", [Space("a", 5, 4, 3, affinities=({"touch": "b", "strength": "must"}, {"facade": "S", "strength": "should"})),
                          Space("b", 5, 4, 3, affinities=({"facade": "N", "strength": "should"}, {"facade": "W", "strength": "should"}))],
                  site={"north": 330})   # turning the plan 30° anticlockwise puts north at 330° clockwise from plan +y
    t = Table(lay)
    u, v = t.touch("a", "b")
    assert u == pytest.approx(1000 * math.hypot(1, 4), abs=2) and v == 3000
    rep = layout.affinity(brief, t)
    met = {(i["a"], i["kind"], i.get("side")): i["met"] for i in rep["items"]}
    assert met == {("a", "touch", None): True, ("a", "facade", "S"): True, ("b", "facade", "N"): True, ("b", "facade", "W"): False}
    assert layout.scores(brief, t)["adjacency"] == 1.0
    assert nx.is_connected(t.walk(brief))


def test_fast_enough_to_run_on_a_drag(placements):
    name = "school_three_levels.yaml"
    brief = dict(BRIEFS)[name]
    pl = placements[name][0]
    t0 = time.perf_counter()
    for _ in range(3):
        t = Table(from_placement(pl))
        layout.affinity(brief, t)
        layout.scores(brief, t)
    assert (time.perf_counter() - t0) / 3 < 0.25, "64 spaces on three levels must read in a quarter of a second"
