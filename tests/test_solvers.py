# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Adventurous Systems

"""Solver-level regressions from the 2026-09-13 review: doors survive re-dimensioning (#5) and the
CP-SAT touch literal measures the whole overlap (#6)."""
import pytest

from spacetope.brief import Brief
from spacetope.circulation import prepare
from spacetope.doors import plan_doors, touch_ok
from spacetope.solve.cpsat import CpsatParams, solve_cpsat
from spacetope.solve.redim import redimension
from spacetope.solve.registry import GENERATORS
from spacetope.synth import synth_brief

pytestmark = [pytest.mark.gate_m7, pytest.mark.slow]


def test_redimension_keeps_every_door_wall():
    for seed in range(4):
        brief = synth_brief(seed, levels=1)
        for pl in GENERATORS["beam"](brief, {"redim": False, "k": 3}, seed):
            out = redimension(brief, pl) or pl
            names = list(out)
            for i, a in enumerate(names):
                for b in names[i + 1:]:
                    assert touch_ok(brief, a, out[a], b, out[b]), (brief.name, a, b)
            assert plan_doors(brief, out)[1] == [], brief.name


def test_cpsat_touch_literal_needs_the_whole_door_width():
    """A 4 x 1 m room (tol 0) can only meet a 1.1 m door on its 4 m side."""
    brief, _ = prepare(Brief.from_dict({
        "name": "thin", "levels": 1, "level_height": 3,
        "circulation": {"corridor": {"w": 1.8, "l": 10}},
        "spaces": [{"name": "thin", "w": 4, "l": 1.0, "h": 3, "program": "room", "tol": 0.0}],
        "contacts": [["corridor_0", "thin"]]}))
    res = solve_cpsat(brief, CpsatParams(k=3, time_limit=20.0), 0)
    assert res.placements, res.status
    for pl in res.placements:
        assert touch_ok(brief, "thin", pl["thin"], "corridor_0", pl["corridor_0"])
        assert plan_doors(brief, pl)[1] == []
