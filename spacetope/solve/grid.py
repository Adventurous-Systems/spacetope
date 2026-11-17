# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Adventurous Systems

"""Integer-millimetre boxes and interval tests. Pure Python, no topologicpy."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from ..units import to_m


@dataclass(frozen=True)
class Box:
    """Axis-aligned box in integer mm; (x, y, z) is the lower-left-bottom corner."""
    x: int
    y: int
    z: int
    w: int
    l: int
    h: int

    def __post_init__(self) -> None:
        for a in ("w", "l", "h"):
            if getattr(self, a) <= 0:
                raise ValueError(f"Box.{a} must be positive")

    @property
    def x1(self) -> int:
        return self.x + self.w

    @property
    def y1(self) -> int:
        return self.y + self.l

    @property
    def z1(self) -> int:
        return self.z + self.h

    def interval(self, axis: str) -> tuple[int, int]:
        return {"x": (self.x, self.x1), "y": (self.y, self.y1), "z": (self.z, self.z1)}[axis]

    def volume(self) -> int:
        return self.w * self.l * self.h

    def face_plane(self, side: str) -> tuple[str, int]:
        """(axis, coordinate) of the plane holding a side face."""
        return {"+x": ("x", self.x1), "-x": ("x", self.x), "+y": ("y", self.y1), "-y": ("y", self.y),
                "ceiling": ("z", self.z1), "floor": ("z", self.z)}[side]

    def to_m(self) -> dict[str, float]:
        return {k: to_m(getattr(self, k)) for k in ("x", "y", "z", "w", "l", "h")}

    def to_dict(self) -> dict[str, int]:
        return {k: getattr(self, k) for k in ("x", "y", "z", "w", "l", "h")}

    @classmethod
    def from_dict(cls, d: dict) -> "Box":
        return cls(int(d["x"]), int(d["y"]), int(d["z"]), int(d["w"]), int(d["l"]), int(d["h"]))


def overlap_len(a: tuple[int, int], b: tuple[int, int]) -> int:
    """Length of the intersection of two closed intervals (0 if they only touch or are apart)."""
    return max(0, min(a[1], b[1]) - max(a[0], b[0]))


def intersects(a: Box, b: Box) -> bool:
    """Positive-volume intersection."""
    return all(overlap_len(a.interval(ax), b.interval(ax)) > 0 for ax in "xyz")


def touches(a: Box, b: Box, side: str) -> tuple[int, int]:
    """If face `side` of a is coincident with the opposite face of b, return the overlap
    rectangle dims (u_len, v_len) in mm along the two in-plane axes; else (0, 0)."""
    axis, coord = a.face_plane(side)
    other = OPPOSITE[side]
    b_axis, b_coord = b.face_plane(other)
    if b_coord != coord:
        return (0, 0)
    in_plane = [ax for ax in "xyz" if ax != axis]
    u = overlap_len(a.interval(in_plane[0]), b.interval(in_plane[0]))
    v = overlap_len(a.interval(in_plane[1]), b.interval(in_plane[1]))
    return (u, v) if u > 0 and v > 0 else (0, 0)


def contact_area(a: Box, b: Box, side: str) -> int:
    u, v = touches(a, b, side)
    return u * v


def any_intersection(box: Box, others: Iterable[Box]) -> bool:
    return any(intersects(box, o) for o in others)


def bounds(boxes: Iterable[Box]) -> Box | None:
    bs = list(boxes)
    if not bs:
        return None
    x0 = min(b.x for b in bs); y0 = min(b.y for b in bs); z0 = min(b.z for b in bs)
    x1 = max(b.x1 for b in bs); y1 = max(b.y1 for b in bs); z1 = max(b.z1 for b in bs)
    return Box(x0, y0, z0, x1 - x0, y1 - y0, z1 - z0)


OPPOSITE = {"+x": "-x", "-x": "+x", "+y": "-y", "-y": "+y", "floor": "ceiling", "ceiling": "floor"}
