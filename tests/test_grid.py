# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Adventurous Systems

import pytest

from spacetope.solve.grid import Box, any_intersection, bounds, contact_area, intersects, overlap_len, touches

pytestmark = pytest.mark.gate_m2

A = Box(0, 0, 0, 4000, 4000, 3000)


@pytest.mark.parametrize("a,b,exp", [
    ((0, 4), (4, 8), 0), ((0, 4), (2, 8), 2), ((0, 4), (5, 8), 0), ((0, 8), (2, 3), 1), ((2, 3), (0, 8), 1),
    ((0, 4), (0, 4), 4), ((0, 4), (-2, 1), 1), ((0, 4), (4, 4), 0), ((1, 1), (0, 4), 0), ((0, 10), (10, 0), 0),
])
def test_overlap_len(a, b, exp):
    assert overlap_len(a, b) == exp


@pytest.mark.parametrize("box,side,exp", [
    (Box(4000, 0, 0, 4000, 4000, 3000), "+x", (4000, 3000)),        # flush
    (Box(4000, 1000, 0, 3000, 2000, 3000), "+x", (2000, 3000)),     # partial
    (Box(4000, 4000, 0, 4000, 4000, 3000), "+x", (0, 0)),           # corner only
    (Box(4001, 0, 0, 4000, 4000, 3000), "+x", (0, 0)),              # 1 mm gap
    (Box(3999, 0, 0, 4000, 4000, 3000), "+x", (0, 0)),              # overlap is not a touch
    (Box(-4000, 0, 0, 4000, 4000, 3000), "-x", (4000, 3000)),
    (Box(0, 4000, 0, 4000, 4000, 3000), "+y", (4000, 3000)),
    (Box(0, -2000, 0, 2000, 2000, 3000), "-y", (2000, 3000)),
    (Box(0, 0, 3000, 4000, 4000, 3000), "ceiling", (4000, 4000)),
    (Box(1000, 1000, -3000, 1000, 1000, 3000), "floor", (1000, 1000)),
])
def test_touches(box, side, exp):
    assert touches(A, box, side) == exp
    assert contact_area(A, box, side) == exp[0] * exp[1]


def test_intersects_and_bounds():
    assert intersects(A, Box(3999, 0, 0, 4000, 4000, 3000))
    assert not intersects(A, Box(4000, 0, 0, 4000, 4000, 3000))
    assert not intersects(A, Box(0, 0, 3000, 4000, 4000, 3000))
    assert any_intersection(Box(1, 1, 1, 1, 1, 1), [A])
    assert bounds([A, Box(4000, 0, 0, 4000, 4000, 3000)]) == Box(0, 0, 0, 8000, 4000, 3000)
    with pytest.raises(ValueError):
        Box(0, 0, 0, 0, 1, 1)
