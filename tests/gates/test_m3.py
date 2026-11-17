# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Adventurous Systems

"""M3 gate: two-level fixture with a stair and a lift as shafts (migrated to the M7 circulation form on 2026-09-13).
Vertical connectivity through shafts only; envelope; stacking."""
import networkx as nx
import pytest

from spacetope.brief import Brief, load
from spacetope.circulation import prepare
from spacetope.doors import door_graph
from spacetope.levels import assign_levels, core_stacks, level_height_mm
from spacetope.pipeline import generate
from spacetope.solve.registry import GENERATORS
from spacetope.verify import verify

pytestmark = [pytest.mark.gate_m3, pytest.mark.slow]
SEEDS = (0, 1, 2, 3, 4)


@pytest.fixture(scope="module")
def brief(fixtures_dir):
    expanded, _ = prepare(load(fixtures_dir / "two_levels_stair.yaml"))
    return expanded


@pytest.fixture(scope="module")
def runs(brief):
    return {seed: generate(GENERATORS["beam"], brief, seed, None, "beam") for seed in SEEDS}


def test_level_assignment(brief):
    lv = assign_levels(brief, 0)
    assert "stair" not in lv and "lift" not in lv
    assert lv["corridor_0"] == 0 and lv["corridor_1"] == 1
    assert lv["office_a"] == 0 and lv["office_c"] == 1 and lv["meeting"] == 1
    assert core_stacks(brief, lv) == []
    assert level_height_mm(brief) == 3000


def test_thresholds(runs):
    for seed, (options, t_gen, t_real) in runs.items():
        ok = [o for o in options if o.ok]
        assert len(ok) == len(options) >= 3, (seed, [o.report.to_dict() for o in options if not o.ok])
        assert len({o.signature for o in ok}) >= 3, seed
        assert t_gen + t_real < 30.0, (seed, t_gen, t_real)


def test_levels_and_shafts(brief, runs):
    for seed, (options, _, _) in runs.items():
        for o in options:
            assert sorted({b.z for b in o.placement.values()}) == [0, 3000], seed
            for name in ("stair", "lift"):
                b = o.placement[name]
                assert (b.z, b.h) == (0, 6000), (seed, name, b)
            assert o.scores["vertical"] == 1.0, (seed, o.scores)


def test_every_path_between_levels_passes_through_a_shaft(brief, runs):
    shafts = [s.name for s in brief.spaces if s.is_shaft]
    for seed, (options, _, _) in runs.items():
        for o in options:
            g = door_graph(brief, o.realised.doors)
            assert nx.is_connected(g), seed
            h = g.copy()
            h.remove_nodes_from(shafts)
            for comp in nx.connected_components(h):
                assert len({o.placement[n].z for n in comp}) == 1, (seed, comp)


def test_envelope_constraint(brief, runs):
    options, _, _ = runs[0]
    assert all(o.ok for o in options)
    small = Brief.from_dict({**brief.to_dict(), "envelope": {"w": 8, "l": 8, "h": 6}})
    rep = verify(small, options[0].placement)
    assert not rep.ok and not rep.checks["constraints"][0] and "envelope" in rep.checks["constraints"][1]


def test_stacking(runs):
    vals = [o.scores["stacking"] for opts, _, _ in runs.values() for o in opts]
    assert sum(vals) / len(vals) >= 0.5, vals
