# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Adventurous Systems

"""Baseline: integer slicing-tree treemap. Areas proportional to w*l, exact tiling by construction.
Ignores adjacency and dimension bands; exists to give an always-valid comparison point and a seed."""
from __future__ import annotations

import math
import random

from ..brief import Brief
from .grid import Box


def _split(items: list[tuple[str, int]], x: int, y: int, w: int, l: int, out: dict[str, Box], h: int, vertical: bool) -> None:
    if len(items) == 1:
        out[items[0][0]] = Box(x, y, 0, w, l, h)
        return
    total = sum(a for _, a in items)
    # split the list at the point closest to half the area
    acc, cut = 0, 1
    best = None
    for i in range(1, len(items)):
        acc += items[i - 1][1]
        d = abs(acc - total / 2)
        if best is None or d < best:
            best, cut = d, i
    left, right = items[:cut], items[cut:]
    frac = sum(a for _, a in left) / total
    if vertical:  # cut along x
        wl = max(1, min(w - 1, int(round(w * frac))))
        _split(left, x, y, wl, l, out, h, not vertical)
        _split(right, x + wl, y, w - wl, l, out, h, not vertical)
    else:
        ll = max(1, min(l - 1, int(round(l * frac))))
        _split(left, x, y, w, ll, out, h, not vertical)
        _split(right, x, y + ll, w, l - ll, out, h, not vertical)


def treemap(brief: Brief, params: dict | None = None, seed: int = 0) -> list[dict[str, Box]]:
    rng = random.Random(seed)
    items = [(s.name, s.nominal_mm("w") * s.nominal_mm("l")) for s in brief.spaces]
    rng.shuffle(items)
    items.sort(key=lambda t: -t[1])
    total = sum(a for _, a in items)
    aspect = (params or {}).get("aspect", 1.0 + 0.5 * rng.random())
    W = int(round(math.sqrt(total * aspect)))
    L = int(math.ceil(total / W))
    h = max(s.nominal_mm("h") for s in brief.spaces)
    out: dict[str, Box] = {}
    _split(items, 0, 0, W, L, out, h, vertical=W >= L)
    return [out]
