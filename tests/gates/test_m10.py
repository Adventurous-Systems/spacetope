"""M10 gate: measured engine fixes. CP-SAT budget rule, frontage cut, pure pre-verify, build only what is shown."""
import pytest

from spacetope.brief import load
from spacetope.circulation import prepare
from spacetope.pipeline import generate, rank
from spacetope.score import cheap_scores, score
from spacetope.solve.grid import Box
from spacetope.solve.registry import GENERATORS
from spacetope.verify import preverify, verify

pytestmark = [pytest.mark.gate_m10, pytest.mark.slow]
PRE_FIXTURES = ("three_rooms", "eight_rooms_corridor", "two_levels_stair", "three_levels_core", "house_ground", "gallery_rich")


@pytest.mark.parametrize("fx", PRE_FIXTURES)
def test_preverify_never_accepts_what_verify_rejects(fixtures_dir, fx):
    brief, _ = prepare(load(fixtures_dir / f"{fx}.yaml"))
    placements = GENERATORS["beam"](brief, None, 0)
    assert placements
    accepted = 0
    for pl in placements:
        pre, _checks = preverify(brief, pl)
        if pre:
            accepted += 1
            rep = verify(brief, pl)
            assert rep.ok, (fx, {k: d for k, (p, d) in rep.checks.items() if not p})
            # box-only scores equal the scores read from the built complex
            cheap, exact = cheap_scores(brief, pl), score(rep.realised)
            for k in exact:
                assert abs(cheap[k] - exact[k]) < 1e-4, (fx, k, cheap[k], exact[k])
    assert accepted >= 1, fx


def test_preverify_rejects_broken_placements(fixtures_dir):
    brief, _ = prepare(load(fixtures_dir / "two_levels_stair.yaml"))
    pl = GENERATORS["beam"](brief, {"k": 1}, 0)[0]
    assert preverify(brief, pl)[0]
    a = "office_a"
    moved = dict(pl); b = pl[a]; moved[a] = Box(b.x + 100_000, b.y, b.z, b.w, b.l, b.h)      # off the corridor: no door
    ok, checks = preverify(brief, moved)
    assert not ok and not checks["doors"][0] or not checks["constraints"][0]
    clash = dict(pl); other = pl["office_b"]; clash[a] = Box(other.x, other.y, other.z, b.w, b.l, b.h)  # on top of office_b
    ok, checks = preverify(brief, clash)
    assert not ok and not checks["no_overlaps"][0]
    short = {k: v for k, v in pl.items() if k != a}
    assert not preverify(brief, short)[0]


def test_build_top_matches_build_all_and_is_cheaper(fixtures_dir):
    brief = load(fixtures_dir / "eight_rooms_corridor.yaml")
    all_opts, _, t_all = generate(GENERATORS["beam"], brief, 0, None, "beam")
    top_opts, _, t_top = generate(GENERATORS["beam"], brief, 0, None, "beam", build="top", keep=3)
    want = [o.signature for o in rank([o for o in all_opts if o.ok])[:3]]
    got = [o.signature for o in rank([o for o in top_opts if o.ok])]
    assert got == want
    assert len(top_opts) == 3 and all(o.ok for o in top_opts)
    assert t_top <= 0.5 * t_all, (t_top, t_all)


def test_cpsat_budget_gives_the_hospital_an_option(fixtures_dir):
    brief = load(fixtures_dir / "small_hospital.yaml")
    options, t_gen, _ = generate(GENERATORS["cpsat"], brief, 0, {"time_limit": 300.0, "k": 4}, "cpsat", build="top", keep=1)
    ok = [o for o in options if o.ok]
    assert ok, "no verified option for small_hospital within 300 s"
    assert ok[0].scores["adjacency"] == 1.0
    assert t_gen < 330.0, t_gen


def test_frontage_cut_is_valid_and_not_slower(fixtures_dir):
    """The cut is redundant: with it, CP-SAT must still find options with every required contact on the briefs it
    solved before, within the same budget."""
    for fx, limit in (("eight_rooms_corridor", 60.0), ("hotel_floor", 120.0), ("clinic", 120.0)):
        brief = load(fixtures_dir / f"{fx}.yaml")
        options, t_gen, _ = generate(GENERATORS["cpsat"], brief, 0, {"time_limit": limit, "k": 2}, "cpsat", build="top", keep=2)
        ok = [o for o in options if o.ok]
        assert ok and all(o.scores["adjacency"] == 1.0 for o in ok), fx
        assert t_gen < limit + 15.0, (fx, t_gen)
