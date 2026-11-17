# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Adventurous Systems

"""E8 ablation flags: beam without re-dimensioning, CP-SAT without the beam warm start.

Both already exist as parameters; these tests pin that each flag changes behaviour and the default does not.
Note (E8a): `beam_multilevel` always calls `beam_search(..., redim=False)` per level and never re-dimensions
afterwards, so the redim ablation is meaningful on single-level briefs only — asserted below.
"""
from spacetope.brief import load
from spacetope.circulation import prepare
from spacetope.solve import cpsat
from spacetope.solve.cpsat import CpsatResult
from spacetope.solve.registry import GENERATORS


def test_beam_redim_flag_changes_single_level_output(fixtures_dir):
    brief, _ = prepare(load(fixtures_dir / "eight_rooms_corridor.yaml"))
    on = GENERATORS["beam"](brief, None, 0)
    off = GENERATORS["beam"](brief, {"redim": False}, 0)
    assert on != off, "redim=False must change at least one placement on a fixture where redim acts"
    assert on == GENERATORS["beam"](brief, {"redim": True}, 0), "the default is redim=True"


def test_beam_redim_flag_is_moot_on_multilevel_briefs(fixtures_dir):
    brief, _ = prepare(load(fixtures_dir / "two_levels_stair.yaml"))
    assert GENERATORS["beam"](brief, {"redim": False}, 0) == GENERATORS["beam"](brief, {"redim": True}, 0), \
        "beam_multilevel never re-dimensions; if this starts failing, E8a applies to multi-level briefs too"


def test_cpsat_warm_start_flag_controls_the_hint(fixtures_dir, monkeypatch):
    captured = []
    monkeypatch.setattr(cpsat, "solve_cpsat",
                        lambda brief, cp, seed, hint=None: captured.append(hint) or CpsatResult("OK", []))
    brief, _ = prepare(load(fixtures_dir / "three_rooms.yaml"))
    cpsat.cpsat_generator(brief, {"time_limit": 5.0}, 0)
    assert captured[-1] is not None, "the default warm start passes a beam placement as the hint"
    cpsat.cpsat_generator(brief, {"time_limit": 5.0, "warm_start": False}, 0)
    assert captured[-1] is None, "warm_start=False must remove the hint"
