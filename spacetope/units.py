# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Adventurous Systems

"""Units: metres in briefs and geometry, integer millimetres inside solvers."""
from __future__ import annotations

MM_PER_M = 1000


def to_mm(metres: float) -> int:
    """Metres -> integer millimetres (round half away from zero is irrelevant at mm scale)."""
    return int(round(metres * MM_PER_M))


def to_m(mm: int) -> float:
    """Integer millimetres -> metres with 6 decimals (topologicpy mantissa)."""
    return round(mm / MM_PER_M, 6)
