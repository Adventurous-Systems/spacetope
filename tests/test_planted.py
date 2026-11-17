# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Adventurous Systems

"""E9 sanity gate: every planted placement passes all nine checks — a failure here is a bug in planted.py —
and the planted topology class is computable."""
import pytest

from spacetope.circulation import prepare
from spacetope.placement import topology_classes
from spacetope.planted import plant
from spacetope.preverify import preverify
from spacetope.verify import verify

pytestmark = pytest.mark.slow

CASES = [
    ("a", {"n": 9, "slicing": True}),
    ("a", {"n": 12, "slicing": False}),
    ("a", {"n": 4, "t": 0.02}),
    ("b", {"rooms": 8, "frontage": 0.75}),
    ("b", {"rooms": 12, "shape": "L"}),
    ("b", {"rooms": 16, "levels": 2}),
    ("b", {"rooms": 10, "double_loaded": False}),
]


@pytest.mark.parametrize("family,params", CASES)
def test_planted_passes_all_nine_checks(family, params):
    for seed in (0, 1):
        brief, pl = plant(family, dict(params), seed)
        brief, _ = prepare(brief)
        ok, checks = preverify(brief, pl)
        assert ok, (family, params, seed, {k: d for k, (p_, d) in checks.items() if not p_})
        rep = verify(brief, pl)
        assert rep.ok, (family, params, seed, {k: d for k, (p_, d) in rep.checks.items() if not p_})
        assert len(topology_classes(brief, [pl])) == 1


def test_planted_nominals_sit_off_centre_but_in_band():
    brief, pl = plant("a", {"n": 9, "t": 0.10}, 3)
    off_centre = 0
    for s in brief.spaces:
        b = pl[s.name]
        for axis, planted in (("w", b.w), ("l", b.l)):
            lo, hi = s.band(axis)
            assert lo <= planted <= hi, (s.name, axis)
            if planted != s.nominal_mm(axis):
                off_centre += 1
    assert off_centre > len(brief.spaces), "the jitter must move most nominals off the planted sizes"
