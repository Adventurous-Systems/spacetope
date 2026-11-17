# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Adventurous Systems

"""M4 gate: CP-SAT exact engine on the fixtures; infeasibility reported; beam comparison."""
import networkx as nx
import pytest

from spacetope.circulation import prepare
from spacetope.doors import door_graph

from spacetope.brief import Brief, load
from spacetope.pipeline import generate, run_generator
from spacetope.score import access_graph
from spacetope.solve.cpsat import CpsatParams, solve_cpsat
from spacetope.solve.grid import touches
from spacetope.solve.registry import GENERATORS

pytestmark = [pytest.mark.gate_m4, pytest.mark.slow]
SEEDS = (0, 1, 2)


@pytest.fixture(scope="module")
def eight(fixtures_dir):
    brief = load(fixtures_dir / "eight_rooms_corridor.yaml")
    return brief, {s: run_generator(GENERATORS["cpsat"], brief, s, name="cpsat") for s in SEEDS}


def test_cpsat_eight_rooms(fixtures_dir, eight):
    brief, rows = eight
    for seed, row in rows.items():
        assert row["distinct"] >= 5, (seed, row)
        assert row["verified"] == row["options"], (seed, row)
        assert row["adjacency"] == 1.0, (seed, row)
        assert row["t_gen"] < 60.0, (seed, row)
        beam = run_generator(GENERATORS["beam"], brief, seed, name="beam")
        assert row["deviation"] <= beam["deviation"] + 1e-9, (seed, row["deviation"], beam["deviation"])


def test_cpsat_two_levels(fixtures_dir):
    brief, _ = prepare(load(fixtures_dir / "two_levels_stair.yaml"))
    shafts = [s.name for s in brief.spaces if s.is_shaft]
    for seed in SEEDS:
        options, t_gen, t_real = generate(GENERATORS["cpsat"], brief, seed, None, "cpsat")
        assert t_gen < 60.0, (seed, t_gen)
        ok = [o for o in options if o.ok]
        assert len(ok) == len(options) >= 3, (seed, [o.report.to_dict() for o in options if not o.ok])
        assert len({o.signature for o in ok}) >= 3
        for o in ok:
            assert o.scores["adjacency"] == 1.0 and o.scores["vertical"] == 1.0, o.scores
            assert sorted({b.z for b in o.placement.values()}) == [0, 3000]
            for name in ("stair", "lift"):
                assert (o.placement[name].z, o.placement[name].h) == (0, 6000), (seed, name)
            g = door_graph(brief, o.realised.doors)
            g.remove_nodes_from(shafts)
            for comp in nx.connected_components(g):
                assert len({o.placement[n].z for n in comp}) == 1


def test_cpsat_office_30(fixtures_dir):
    brief = load(fixtures_dir / "office_30.yaml")
    assert len(brief.spaces) == 30
    options, t_gen, t_real = generate(GENERATORS["cpsat"], brief, 0, {"time_limit": 300.0, "k": 4}, "cpsat")
    assert t_gen < 300.0, t_gen
    ok = [o for o in options if o.ok]
    assert len(ok) == len(options) >= 3, [o.report.to_dict() for o in options if not o.ok]
    assert len({o.signature for o in ok}) >= 3
    assert all(o.scores["adjacency"] == 1.0 for o in ok)


def test_infeasible_brief_is_reported():
    # three rooms that must all pairwise touch AND a fourth that must touch all three: fine.
    # Make it impossible: a 1 m wide room must touch two others on the same side band with door widths.
    d = {"name": "bad", "spaces": [
        {"name": "a", "w": 1, "l": 1, "h": 3, "tol": 0.0}, {"name": "b", "w": 4, "l": 4, "h": 3, "tol": 0.0},
        {"name": "c", "w": 4, "l": 4, "h": 3, "tol": 0.0}, {"name": "d", "w": 4, "l": 4, "h": 3, "tol": 0.0},
        {"name": "e", "w": 4, "l": 4, "h": 3, "tol": 0.0}, {"name": "f", "w": 4, "l": 4, "h": 3, "tol": 0.0}],
         "contacts": [["a", "b"], ["a", "c"], ["a", "d"], ["a", "e"], ["a", "f"]]}
    brief = Brief.from_dict(d)
    res = solve_cpsat(brief, CpsatParams(k=2, time_limit=20.0))
    assert res.status == "INFEASIBLE" and res.placements == []
