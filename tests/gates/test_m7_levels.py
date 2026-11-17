# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Adventurous Systems

"""M7.2 gate: the beam generator on shaft briefs (plan §6, M7.2)."""
import pytest

from spacetope.brief import load
from spacetope.circulation import door_spec, prepare
from spacetope.levels import assign_levels, level_height_mm
from spacetope.pipeline import generate
from spacetope.solve.grid import touches
from spacetope.solve.registry import GENERATORS
from spacetope.units import to_mm

pytestmark = [pytest.mark.gate_m7, pytest.mark.slow]
SEEDS = (0, 1, 2, 3, 4)
FIXTURES = ("two_levels_stair", "three_levels_core")


@pytest.fixture(scope="module", params=FIXTURES)
def runs(request, fixtures_dir):
    brief, _ = prepare(load(fixtures_dir / f"{request.param}.yaml"))
    return brief, {seed: generate(GENERATORS["beam"], brief, seed, None, "beam") for seed in SEEDS}


def test_shafts_are_not_assigned_a_single_level(fixtures_dir):
    brief, _ = prepare(load(fixtures_dir / "three_levels_core.yaml"))
    lv = assign_levels(brief, 0)
    assert "stair" not in lv and "lift" not in lv
    assert [lv[f"corridor_{k}"] for k in range(3)] == [0, 1, 2]
    assert lv["studio"] == 2 and lv["meeting"] == 1


def test_options_verify_and_differ(runs):
    brief, by_seed = runs
    for seed, (options, t_gen, t_real) in by_seed.items():
        assert len(options) >= 3, (brief.name, seed, len(options))
        failed = [o.report.to_dict()["checks"] for o in options if not o.ok]
        assert not failed, (brief.name, seed, failed[:1])
        assert len({o.signature for o in options}) >= 3, (brief.name, seed)
        assert t_gen + t_real < 30.0, (brief.name, seed, t_gen, t_real)


def test_each_shaft_is_one_cell_with_its_span(runs):
    brief, by_seed = runs
    H = level_height_mm(brief)
    for seed, (options, _, _) in by_seed.items():
        for o in options:
            assert o.realised.n_cells == len(brief.spaces)
            for s in brief.spaces:
                if s.is_shaft:
                    b = o.placement[s.name]
                    lo, hi = s.serves
                    assert (b.z, b.h) == (lo * H, (hi - lo + 1) * H), (brief.name, seed, s.name, b)


def test_each_shaft_leaves_room_for_a_door_to_every_served_corridor(runs):
    brief, by_seed = runs
    spec = door_spec(brief)
    for seed, (options, _, _) in by_seed.items():
        for o in options:
            for s in brief.spaces:
                if not s.is_shaft:
                    continue
                kind = "stair" if s.program == "stair" else "lift"
                need = to_mm(spec[kind]["w"] + 2 * spec["jamb"])
                for k in range(s.serves[0], s.serves[1] + 1):
                    corridor = o.placement[f"corridor_{k}"]
                    best = max(touches(o.placement[s.name], corridor, side)[0] for side in ("+x", "-x", "+y", "-y"))
                    assert best >= need, (brief.name, seed, s.name, f"corridor_{k}", best, need)
