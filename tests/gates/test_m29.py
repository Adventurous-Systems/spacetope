"""M29 gate: bodies on springs in a three-dimensional void; storey cells by default, free cells as a sketch (PLAN §4.11)."""
import time

import pytest
from shapely.geometry import Polygon

from spacetope import cells, field, volume
from spacetope.brief import Brief, load
from spacetope.circulation import prepare
from spacetope.placement import assembly_from_placement
from spacetope.solve.registry import GENERATORS
from spacetope.tessellate import KINDS

pytestmark = pytest.mark.gate_m29
SEEDS = range(4)
H = 3600


@pytest.fixture(scope="module")
def stepped(fixtures_dir):
    return load(fixtures_dir / "volume" / "stepped.yaml")


@pytest.fixture(scope="module")
def sweep(stepped):
    return {(k, s): volume.solve(stepped, k, s) for k in KINDS for s in SEEDS}


def _two_storeys(spaces, **extra) -> Brief:
    return Brief.from_dict({"name": "t", "level_height": 3.0, "spaces": spaces,
                            "void": {"blocks": [{"boundary": [[0, 0], [30, 0], [30, 20], [0, 20]], "levels": [0, 1]}]}, **extra})


def test_void_round_trips_and_gives_each_storey_its_ground(stepped):
    assert Brief.from_dict(stepped.to_dict()).void == stepped.void
    g = field.storey_grounds(stepped)
    assert [round(g[k].area) for k in range(4)] == [912, 624, 256, 256]
    f = field.prepare(stepped)
    assert f.n == 4 and f.ground_at(2).area == pytest.approx(256)


def test_a_bad_void_is_named(stepped):
    d = stepped.to_dict()
    d["void"] = {"blocks": [{"boundary": [[0, 0], [10, 0], [10, 10]], "levels": [1, 1]}]}
    with pytest.raises(field.FieldInvalid, match="storey 0"):
        field.prepare(Brief.from_dict(d))
    d["void"] = {"blocks": [{"levels": [0, 0]}]}
    with pytest.raises(field.FieldInvalid, match="boundary"):
        field.prepare(Brief.from_dict(d))


def test_bodies_are_lenses_grown_to_fill_the_void(stepped):
    f = field.prepare(stepped)
    rooms, asked, radius, storeys, fill = volume.bodies(f)
    hall = [s.name for s in rooms].index("hall")
    assert storeys[hall] == 2 and set(storeys.tolist()) == {1, 2}, "a hall twice the storey height stands through two"
    assert (asked * storeys).sum() * fill == pytest.approx(volume.capacity(f).sum())
    assert radius[hall] ** 2 * 3.141592653589793 == pytest.approx(140 * fill, rel=1e-3)   # the plan disc holds the area asked


def test_storeys_emerge_balanced_and_the_hard_wishes_fix_theirs(sweep):
    for s in SEEDS:
        r = sweep[("power", s)]
        # no storey is asked for more than a tenth over what it has; a small storey can stay a body short (three
        # rooms fill the tower floor, two leave it a quarter empty), so the under side is looser
        assert all(q["asked"] <= 1.10 * q["has"] for q in r["storeys"]), [(q["asked"], q["has"]) for q in r["storeys"]]
        assert r["scores"]["storey_balance"] <= 0.30, [(q["asked"], q["has"]) for q in r["storeys"]]
        assert r["room_levels"]["reception"] == r["room_levels"]["hall"] == r["room_levels"]["creche"] == 0
        assert r["room_levels"]["spa"] == r["room_levels"]["jacuzzi"], "rooms that must touch float to one storey"


def test_every_solve_is_whole_and_inside_the_void(stepped, sweep):
    grounds = field.storey_grounds(stepped)
    for key, r in sweep.items():
        assert r["checks"]["complete"]["passed"] and r["checks"]["no_overlaps"]["passed"], (key, r["checks"])
        for c in r["cells"]:
            for k in range(c["levels"][0], c["levels"][1] + 1):
                assert Polygon(c["ring"]).difference(grounds[k].buffer(0.005)).area < 0.05, (key, c["name"], k)
    assert sum(1 for r in sweep.values() if r["ok"]) >= 16, "measured 18 of 20 on 2026-11-23"
    assert max(sum(r["ms"].values()) for r in sweep.values()) < 1500


def test_a_tall_room_stands_through_two_storeys(sweep):
    for kind in KINDS:
        hall = next(c for c in sweep[(kind, 0)]["cells"] if c["name"] == "hall")
        assert hall["levels"] == [0, 1]
        above = [c for c in sweep[(kind, 0)]["cells"] if c["levels"] == [1, 1]]
        assert all(Polygon(c["ring"]).intersection(Polygon(hall["ring"])).area < 0.05 for c in above), "the storey above divides what is left"


def test_same_seed_same_contraption(stepped, sweep):
    assert volume.solve(stepped, "power", 0)["positions"] == sweep[("power", 0)]["positions"]


def test_inflating_a_body_gives_it_ground_and_the_rest_answer(stepped, sweep):
    before = sweep[("power", 0)]
    area = lambda r, n: next(c["area"] for c in r["cells"] if c["name"] == n)  # noqa: E731
    t0 = time.perf_counter()
    after = volume.solve(stepped, "power", 0, positions=before["positions"], scales={"gym": 2.0})
    assert time.perf_counter() - t0 < 1.0
    assert area(after, "gym") > 1.4 * area(before, "gym")
    assert after["checks"]["complete"]["passed"] and after["checks"]["no_overlaps"]["passed"]
    assert after["fill"] < before["fill"], "one body larger, so every body is grown a little less"
    assert after["scores"]["storey_balance"] <= 0.3


def test_a_moved_body_is_pinned_on_the_storey_it_was_put(stepped, sweep):
    before = sweep[("power", 0)]
    pos = {n: tuple(v) for n, v in before["positions"].items()}
    k = before["room_levels"]["salon"]
    to = k + 1 if k < 3 else k - 1
    pos["salon"] = (8.0, 12.0, (to + 0.5) * 3.6)
    after = volume.solve(stepped, "power", 0, positions=pos, pins=("salon",))
    assert after["room_levels"]["salon"] == to and tuple(after["positions"]["salon"]) == pos["salon"]


def test_wall_node_springs_have_a_direction():
    b = _two_storeys([{"name": n, "area": 40} for n in "abcdefghijkl"])     # twelve bodies, five of them sprung
    f = field.prepare(b)
    r = float(volume.bodies(f)[2][0])          # all the bodies are the same size
    for seed in range(3):
        p = volume.relax(f, seed, sided=(("a", "+x", "b"), ("a", "ceiling", "c"), ("d", "-y", "e")))
        assert p["b"][0] > p["a"][0] + r and abs(p["b"][2] - p["a"][2]) < 0.1, "b is east of a, on a's storey"
        assert p["c"][2] > p["a"][2] + 2.5, "c is on the storey above a"
        assert ((p["c"][0] - p["a"][0]) ** 2 + (p["c"][1] - p["a"][1]) ** 2) ** 0.5 < 0.6 * r, "and over it: their plans mostly overlap"
        assert p["e"][1] < p["d"][1] - r, "e is south of d"


def test_a_box_option_gives_its_springs(fixtures_dir):
    brief, _ = prepare(load(fixtures_dir / "two_levels_stair.yaml"))
    ag = assembly_from_placement(brief, GENERATORS["beam"](brief, None, 0)[0])
    sp = volume.springs_from_assembly(ag)
    assert len(sp) == len(ag) and {s[1] for s in sp} <= {"+x", "-x", "+y", "-y", "floor", "ceiling"}
    assert any(s[1] in ("floor", "ceiling") for s in sp), "the stair stack is a vertical spring"


def test_with_a_path_the_rooms_of_each_storey_line_it():
    b = _two_storeys([{"name": f"r{i}", "area": 45} for i in range(8)], paths=[{"name": "walk", "width": 2, "points": [[2, 10], [28, 10]]}])
    r = volume.solve(b, "power", 0)
    assert {c["program"] for c in r["cells"]} == {"room", "corridor", "stair"}
    assert r["checks"]["reach"]["passed"] and r["scores"]["vertical"] == 1.0


@pytest.mark.slow
@pytest.mark.parametrize("kind", ["power", "slice", "hex"])
def test_storey_cells_become_a_cell_complex(stepped, kind):
    f = field.prepare(stepped, 0)
    pos = volume.relax(f, 0)
    rep = cells.verify_layout(f.brief, volume.build(f, pos, kind))
    failed = {k: d for k, (p, d) in rep.checks.items() if not p and k in ("built", "cell_count", "no_slivers", "contacts", "dictionaries")}
    assert not failed, failed


@pytest.mark.slow
def test_the_sketch_builds_free_cells(stepped, sweep):
    from topologicpy.Topology import Topology
    f = field.prepare(stepped, 0)
    sk = volume.free(f, {n: tuple(v) for n, v in sweep[("power", 0)]["positions"].items()})
    assert not sk["missing"] and sk["volume_off"] < 0.3
    assert sum(p["volume"] for p in sk["pieces"]) == pytest.approx(sk["void_m3"], rel=1e-3), "the pieces fill the void"
    assert sk["faces"]["sloping"] > 0, "a sketch: walls slope, and the report says how many"
    cc, built = volume.realise_free(sk)
    assert len(built) == len(sk["pieces"]) and len(Topology.Cells(cc)) == len(built)
