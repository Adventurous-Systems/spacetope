# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Adventurous Systems

"""E14: CP-SAT deterministic mode — one worker, deterministic-time budgets, byte-identical runs."""
from spacetope.brief import load
from spacetope.circulation import prepare
from spacetope.solve.cpsat import cpsat_generator


def test_two_deterministic_runs_are_byte_identical(fixtures_dir):
    brief, _ = prepare(load(fixtures_dir / "three_rooms.yaml"))
    params = {"deterministic": True, "k": 3, "warm_start": False}
    a = cpsat_generator(brief, dict(params), 0)
    b = cpsat_generator(brief, dict(params), 0)
    assert a, "the deterministic budget must still find options on three_rooms"
    assert a == b, "two deterministic runs of the same brief and seed must give identical placements"


def test_deterministic_default_off(fixtures_dir):
    from spacetope.solve.cpsat import CpsatParams
    assert CpsatParams().deterministic is False
