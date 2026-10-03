"""M15c gate: no generator leaves a gap to close.

M15c planned a pass that slides rooms together. Measured first (`bench/dead_space.py`): the beam, the exact engine
and the dual enumerator all produce layouts with no empty ground enclosed by spaces and no gap between neighbours
along a corridor, because the beam already pays for uncovered ground (`BeamParams.w_dead`) and offers a
neighbour's edges as alignment offsets. So the pass was not written; this gate keeps the property it aimed at.
The empty ground that remains is the plan's outline, which sliding a room cannot change.
"""
import pytest

from bench.dead_space import bbox_dead, corridor_side_gaps, enclosed_holes
from spacetope.brief import load
from spacetope.circulation import prepare
from spacetope.preverify import preverify
from spacetope.solve.grid import Box
from spacetope.solve.registry import GENERATORS

pytestmark = [pytest.mark.gate_m15, pytest.mark.slow]
BEAM = ("eight_rooms_corridor", "hotel_floor", "clinic", "house_ground", "small_hospital")


@pytest.mark.parametrize("fx", BEAM)
def test_beam_layouts_have_nothing_to_close(fixtures_dir, fx):
    brief, _ = prepare(load(fixtures_dir / f"{fx}.yaml"))
    ok = [pl for pl in GENERATORS["beam"](brief, None, 0) if preverify(brief, pl)[0]]
    assert ok, fx
    for pl in ok[:3]:
        assert enclosed_holes(pl) == 0.0, fx
        gap_m, gaps = corridor_side_gaps(brief, pl)
        assert gap_m <= 2.0, (fx, gaps, gap_m)


@pytest.mark.parametrize("gen,params", [("cpsat", {"k": 1, "time_limit": 40.0, "per_solve_max": 20.0}),
                                        ("dual", {"k": 1, "time_limit": 40.0})])
def test_the_other_generators_leave_nothing_to_close(fixtures_dir, gen, params):
    brief, _ = prepare(load(fixtures_dir / "eight_rooms_corridor.yaml"))
    ok = [pl for pl in GENERATORS[gen](brief, params, 0) if preverify(brief, pl)[0]]
    assert ok, gen
    assert enclosed_holes(ok[0]) == 0.0
    assert corridor_side_gaps(brief, ok[0])[0] == 0.0


def test_the_measurement_would_notice_a_gap(fixtures_dir):
    """Without this the gate above could pass because the measurement is blind."""
    brief, _ = prepare(load(fixtures_dir / "eight_rooms_corridor.yaml"))
    pl = [p for p in GENERATORS["beam"](brief, None, 0) if preverify(brief, p)[0]][0]
    victim = max((n for n in pl if brief.space(n).program == "room"), key=lambda n: pl[n].x)
    b = pl[victim]
    moved = {**pl, victim: Box(b.x + 2000, b.y, b.z, b.w, b.l, b.h)}
    assert enclosed_holes(moved) > 5.0
    assert corridor_side_gaps(brief, moved)[0] >= 2.0
    assert bbox_dead(moved) > bbox_dead(pl)
