"""M15a gate: the beam on large, corridor-tight briefs (tight-corridor mode, chains of room partners in one run)."""
import random

import pytest

from spacetope.brief import load
from spacetope.circulation import prepare
from spacetope.pipeline import generate
from spacetope.solve.beam import BeamParams, order_spaces, pair_adjacent, tight_corridors
from spacetope.solve.registry import GENERATORS

pytestmark = [pytest.mark.gate_m15, pytest.mark.slow]


@pytest.mark.parametrize("fx", ("small_hospital", "school_three_levels"))
def test_beam_gives_verified_options_on_the_large_briefs(fixtures_dir, fx):
    options, t_gen, _ = generate(GENERATORS["beam"], load(fixtures_dir / f"{fx}.yaml"), 0, None, "beam", build="top", keep=4)
    ok = [o for o in options if o.ok]
    assert len(ok) >= 4, [{k: d for k, (p, d) in o.report.checks.items() if not p} for o in options if not o.ok][:2]
    assert all(o.scores["adjacency"] == 1.0 and o.scores["vertical"] == 1.0 for o in ok), [o.scores for o in ok]
    assert t_gen < 60.0, t_gen          # was 37 s and 42 s with nothing verified


def test_tight_corridors_are_detected_only_where_frontage_is_tight(fixtures_dir):
    p = BeamParams()
    for fx, expect in (("eight_rooms_corridor", False), ("hotel_floor", False), ("small_hospital", True), ("school_three_levels", True)):
        brief, _ = prepare(load(fixtures_dir / f"{fx}.yaml"))
        env = {k: int(v * 1000) for k, v in brief.envelope.items()} if brief.envelope else None
        level0 = [s for s in brief.spaces if not s.is_shaft and s.wishes.get("level", 0) in (0, None)]
        tight = tight_corridors(brief, level0, env, p)
        assert bool(tight) == expect, (fx, tight)
        for name, length in tight.items():
            assert brief.space(name).nominal_mm("l") <= length <= max(env["w"], env["l"])


def test_chains_of_room_partners_are_placed_as_one_run(fixtures_dir):
    brief, _ = prepare(load(fixtures_dir / "school_three_levels.yaml"))
    level1 = [s for s in brief.spaces if not s.is_shaft and s.wishes.get("level") == 1]
    names = [s.name for s in pair_adjacent(brief, order_spaces(brief, random.Random(0), level1))]
    i = names.index("prep_room")
    assert {names[i - 1], names[i + 1]} == {"science_lab_1", "science_lab_2"}, names[:8]     # the hub sits between its partners
    assert sorted(names) == sorted(s.name for s in level1) and names[0] == "corridor_1"
    brief, _ = prepare(load(fixtures_dir / "small_hospital.yaml"))
    level0 = [s for s in brief.spaces if not s.is_shaft and s.wishes.get("level") == 0]
    names = [s.name for s in pair_adjacent(brief, order_spaces(brief, random.Random(0), level0))]
    i = names.index("xray")
    assert {names[i - 1], names[i + 1]} == {"imaging", "imaging_control"}, names[:10]
