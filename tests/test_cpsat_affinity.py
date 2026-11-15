"""M20, CP-SAT part: affinities as constraints and rewarded literals (PLAN §4.10). Small briefs, short time limits;
placements are judged with `affinity.measure`, never by the model's own literals."""
from pathlib import Path

import pytest

from spacetope import affinity
from spacetope.brief import Brief, load
from spacetope.circulation import BriefInvalid, prepare
from spacetope.solve.cpsat import CpsatParams, solve_cpsat

ROOT = Path(__file__).resolve().parent.parent


def room(name, w=3, l=3, **kw):
    return {"name": name, "w": w, "l": l, "h": 3, "program": "room", **kw}


def make(spaces, affinities=(), **kw):
    d = {"name": "t", "level_height": 3.0, "spaces": spaces, **kw}
    if affinities:
        d["affinities"] = list(affinities)
    return prepare(Brief.from_dict(d))[0]


def solve(brief, k=2, t=8.0, **kw):
    return solve_cpsat(brief, CpsatParams(k=k, time_limit=t, workers=4, **kw), 0)


def met(brief, pl):
    r = affinity.measure(brief, pl)
    return r, [i for i in r["items"] if i["met"] is False]


FOUR = [room(n) for n in ("a", "b", "c", "d")]
HARD = [{"between": ["a", "b"], "kind": "touch", "strength": "must"},
        {"between": ["c", "d"], "kind": "apart", "strength": "must"}]


def test_hard_touch_and_apart_hold_where_the_free_optimum_breaks_them():
    free = solve(make(FOUR), k=1, w_affinity=0)
    f = free.placements[0]
    # unconstrained: the compact packing of four equal squares touches c and d (and a, b alike), so apart is broken
    assert affinity.measure(make(FOUR, HARD), f)["hard"]["met"] < 2
    res = solve(make(FOUR, HARD))
    assert res.placements, res.status
    for pl in res.placements:
        r, missed = met(make(FOUR, HARD), pl)
        assert r["hard"] == {"met": 2, "total": 2} and not missed


def test_eight_rooms_corridor_with_a_touch_and_an_apart():
    d = load(ROOT / "fixtures" / "eight_rooms_corridor.yaml").to_dict()
    d["affinities"] = [{"between": ["storage", "wc"], "kind": "touch", "strength": "must"},
                       {"between": ["wc", "meeting"], "kind": "apart", "strength": "must"}]
    brief = prepare(Brief.from_dict(d))[0]
    res = solve(brief, k=2, t=25.0)
    assert res.placements, res.status
    for pl in res.placements:
        assert affinity.measure(brief, pl)["hard"] == {"met": 2, "total": 2}


def test_never_touch_is_exact_not_just_a_false_literal():
    """Two rooms that would pack side by side (a touches b) must end up with no wall of 0.9 m or more."""
    brief = make([room("a"), room("b")], [{"between": ["a", "b"], "kind": "touch", "strength": "never"}])
    res = solve(brief, k=1)
    assert res.placements, res.status
    r, missed = met(brief, res.placements[0])
    assert not missed and r["hard"]["met"] == 1


def test_soft_cluster_and_soft_apart_are_no_worse_and_somewhere_better():
    spaces = [room("a", tags=["wet"]), room("b", tags=["wet"]), room("c"), room("d", tags=["wet"])]
    cluster = [{"tag": "wet", "rule": "cluster", "strength": "should", "weight": 4}]
    apart = [{"between": ["a", "b"], "kind": "apart", "strength": "should", "weight": 2},
             {"between": ["c", "d"], "kind": "apart", "strength": "should", "weight": 2}]
    better = 0
    for affs in (cluster, apart):
        brief = make(spaces, affs)
        on = solve(brief, k=1, w_affinity=80_000).placements[0]
        off = solve(brief, k=1, w_affinity=0).placements[0]
        s_on, s_off = (affinity.measure(brief, p)["score"] for p in (on, off))
        assert s_on >= s_off
        better += s_on > s_off
    assert better >= 1


def two_levels(affs):
    spaces = [room("w0", w=3, l=2, wishes={"level": 0}, tags=["wet"]), room("o0", wishes={"level": 0}),
              room("w1", w=3, l=2, wishes={"level": 1}, tags=["wet"]), room("o1", wishes={"level": 1})]
    return make(spaces, affs, levels=2, envelope={"w": 12, "l": 9, "h": 6},
                circulation={"corridor": {"w": 1.8, "l": 6}, "stairs": [{"name": "stair", "w": 2.5, "l": 4}]})


def test_stack_rule_between_two_levels_is_met():
    brief = two_levels([{"tag": "wet", "rule": "stack", "strength": "should", "weight": 3}])
    res = solve(brief, k=1, t=15.0)
    assert res.placements, res.status
    r = affinity.measure(brief, res.placements[0])
    stacks = [i for i in r["items"] if i["kind"] == "stack"]
    assert stacks and all(i["met"] for i in stacks), stacks


def test_hard_stack_and_never_stack():
    brief = two_levels([{"between": ["w0", "w1"], "kind": "stack", "strength": "must"},
                        {"between": ["o0", "o1"], "kind": "stack", "strength": "never"}])
    res = solve(brief, k=1, t=15.0)
    assert res.placements, res.status
    assert affinity.measure(brief, res.placements[0])["hard"] == {"met": 2, "total": 2}


def test_contradictory_hard_rules_report_impossible_quickly():
    brief = make([room("a"), room("b")], [{"between": ["a", "b"], "kind": "touch", "strength": "must"},
                                           {"between": ["a", "b"], "kind": "touch", "strength": "never"}])
    res = solve(brief, k=2, t=10.0)
    assert not res.placements and res.status == "INFEASIBLE" and res.seconds < 10.0


def test_touch_across_levels_cannot_be_a_must():
    brief = two_levels([{"between": ["w0", "w1"], "kind": "touch", "strength": "must"}])
    assert solve(brief, k=1, t=5.0).status == "INFEASIBLE"


def test_no_affinities_leaves_the_model_untouched():
    """Without affinities no affinity variable exists, and the soft weight changes nothing in the model."""
    import spacetope.solve.cpsat as C
    from ortools.sat.python import cp_model

    sizes = []

    class Stop(Exception):
        pass

    def fake(self, m, *a, **k):
        pr = m.Proto()
        sizes.append((len(pr.variables), len(pr.constraints), list(pr.objective.coeffs), [v.name for v in pr.variables]))
        raise Stop

    brief = make(FOUR)
    real = cp_model.CpSolver.Solve
    cp_model.CpSolver.Solve = fake
    try:
        for w in (80_000, 0):
            with pytest.raises(Stop):
                C.solve_cpsat(brief, C.CpsatParams(k=1, time_limit=2, w_affinity=w), 0)
    finally:
        cp_model.CpSolver.Solve = real
    assert sizes[0][:3] == sizes[1][:3]
    assert not any(n.startswith("af_") for n in sizes[0][3])


def test_budget_skips_soft_terms_but_keeps_hard_ones():
    spaces = [room("a", tags=["wet"]), room("b", tags=["wet"]), room("c", tags=["wet"])]
    affs = [{"tag": "wet", "rule": "cluster", "strength": "should"}, HARD[1] | {"between": ["a", "c"]}]
    brief = make(spaces, affs)
    res = solve(brief, k=1, affinity_literals_max=1)
    assert res.placements
    assert affinity.measure(brief, res.placements[0])["hard"] == {"met": 1, "total": 1}
