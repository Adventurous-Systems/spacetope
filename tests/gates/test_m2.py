# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Adventurous Systems

"""M2 gate: thresholds on the scoreboard for the beam generator and the treemap baseline."""
import json
from pathlib import Path

import pytest

from spacetope.brief import load
from spacetope.pipeline import generate, run_generator
from spacetope.placement import assembly_from_placement, load_placement
from spacetope.solve.registry import GENERATORS

pytestmark = [pytest.mark.gate_m2, pytest.mark.slow]
SEEDS = (0, 1, 2, 3, 4)


@pytest.fixture(scope="module")
def eight_rows(fixtures_dir):
    brief = load(fixtures_dir / "eight_rooms_corridor.yaml")
    return {seed: run_generator(GENERATORS["beam"], brief, seed, name="beam") for seed in SEEDS}


def test_beam_eight_rooms_thresholds(eight_rows):
    for seed, row in eight_rows.items():
        assert row["distinct"] >= 5, (seed, row)
        assert row["verified"] == row["options"] >= 5, (seed, row)
        assert row["t_gen"] + row["t_realise"] < 10.0, (seed, row)
    assert sum(r["adjacency"] for r in eight_rows.values()) / len(SEEDS) >= 0.9, eight_rows
    assert sum(r["deviation"] for r in eight_rows.values()) / len(SEEDS) <= 0.10, eight_rows


def test_treemap_baseline_verified(fixtures_dir):
    brief = load(fixtures_dir / "eight_rooms_corridor.yaml")
    for seed in SEEDS:
        row = run_generator(GENERATORS["treemap"], brief, seed, name="treemap")
        assert row["verified"] >= 1, (seed, row)


def test_beam_recall_three_rooms(fixtures_dir):
    brief = load(fixtures_dir / "three_rooms.yaml")
    target = assembly_from_placement(brief, load_placement(fixtures_dir / "placed" / "three_rooms.json")).signature()
    hits = 0
    for seed in SEEDS:
        options, _, _ = generate(GENERATORS["beam"], brief, seed, {"k": 16}, "beam")
        hits += any(o.ok and o.signature == target for o in options)
    assert hits >= 4, hits


def test_determinism(fixtures_dir):
    brief = load(fixtures_dir / "eight_rooms_corridor.yaml")
    a = run_generator(GENERATORS["beam"], brief, 3, name="beam")
    b = run_generator(GENERATORS["beam"], brief, 3, name="beam")
    for k in ("options", "verified", "distinct", "adjacency", "deviation", "compactness", "circulation"):
        assert a[k] == b[k], k


def test_overlapping_move_rejected(fixtures_dir):
    from spacetope.brief import Space, Brief
    from spacetope.solve.beam import BeamParams, State, moves, evaluate
    from spacetope.solve.grid import Box, intersects
    brief = Brief("t", [Space("a", 4, 4, 3), Space("b", 2, 2, 3), Space("c", 3, 3, 3)])
    placed = {"a": Box(0, 0, 0, 4000, 4000, 3000), "b": Box(4000, 0, 0, 2000, 2000, 3000)}
    st = State(placed, evaluate(brief, placed, BeamParams()))
    for new in moves(brief, st, brief.space("c"), BeamParams()):
        c = new["c"]
        assert not intersects(c, new["a"]) and not intersects(c, new["b"])
