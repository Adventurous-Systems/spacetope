"""M20 gate: affinities in the generators (PLAN §4.10). One group of tests per gate line.

Line 3 and line 6 are the numbers the architect fixed: soft affinity of the beam's pre-verified placements, and beam time.
Line 4 reads the two recorded baselines (`bench/history/*_m19_affinity.csv`, `*_m20_affinity.csv`, made by
`python -m bench.affinity_baseline`); line 5 compares against `tests/gates/m20_beam_reference.json`.
"""
import copy
import csv
import json
import statistics
import time
from pathlib import Path

import pytest

from bench.beam_reference import beam_reference
from spacetope import affinity
from spacetope.brief import Brief, load
from spacetope.circulation import prepare
from spacetope.pipeline import RANK_WEIGHTS, Option, evaluate_placements, evaluate_top, generate, rank
from spacetope.preverify import preverify
from spacetope.score import METRICS, cheap_scores, score
from spacetope.solve.cpsat import CpsatParams, solve_cpsat
from spacetope.solve.registry import GENERATORS
from spacetope.verify import verify

pytestmark = [pytest.mark.gate_m20, pytest.mark.slow]
ROOT = Path(__file__).resolve().parent.parent.parent
HIST = ROOT / "bench" / "history"
M19_CSV = HIST / "2026-11-15_m19_affinity.csv"
M20_CSV = HIST / "2026-11-15_m20_affinity.csv"
REFERENCE = ROOT / "tests" / "gates" / "m20_beam_reference.json"
SEARCHED = ("touch", "apart", "stack", "same_level")


def prepared(fixtures_dir, name):
    return prepare(load(fixtures_dir / f"{name}.yaml"))[0]


# --- line 1: hard rules on eight_rooms_hard ---------------------------------------------------------------------

@pytest.mark.parametrize("seed", [0, 1, 2])
def test_beam_returns_verified_options_that_meet_every_hard_rule(fixtures_dir, seed):
    brief = load(fixtures_dir / "eight_rooms_hard.yaml")
    options, _, _ = generate(GENERATORS["beam"], brief, seed, None, "beam")
    ver = [o for o in options if o.ok]
    assert ver, f"seed {seed}: none of {len(options)} options verified"
    for o in ver:
        assert o.analysis["affinity"]["hard"] == {"met": 2, "total": 2}
        assert affinity.hard_misses(prepared(fixtures_dir, "eight_rooms_hard"), o.placement) == []


def test_cpsat_returns_verified_options_that_meet_every_hard_rule(fixtures_dir):
    brief = load(fixtures_dir / "eight_rooms_hard.yaml")
    options, _, _ = generate(GENERATORS["cpsat"], brief, 0, {"k": 2, "time_limit": 30.0, "workers": 4}, "cpsat")
    ver = [o for o in options if o.ok]
    assert ver, f"none of {len(options)} options verified"
    expanded = prepared(fixtures_dir, "eight_rooms_hard")
    for o in ver:
        assert affinity.hard_misses(expanded, o.placement) == []


# --- line 2: the eighth check ------------------------------------------------------------------------------------

def test_a_broken_must_fails_the_check_in_preverify_and_in_verify_with_the_wish_named(fixtures_dir):
    full = prepared(fixtures_dir, "eight_rooms_hard")
    d = load(fixtures_dir / "eight_rooms_hard.yaml").to_dict()
    d.pop("affinities")
    bare = prepare(Brief.from_dict(d))[0]
    # beam placements of the same rooms without the hard rules: some of them break one
    bad = [pl for pl in GENERATORS["beam"](bare, None, 0) if preverify(bare, pl)[0] and affinity.hard_misses(full, pl)]
    assert bad, "no placement breaks a must; the fixture no longer tests anything"
    pl = bad[0]
    ok, checks = preverify(full, pl)
    assert not ok and not checks["affinities"][0]
    rep = verify(full, pl)
    assert rep.checks["built"][0] and not rep.ok and not rep.checks["affinities"][0]
    miss = affinity.hard_misses(full, pl)[0]
    for detail in (checks["affinities"][1], rep.checks["affinities"][1]):
        assert miss.split(" (")[0] in detail
        assert "wc" in detail and ("storage" in detail or "meeting" in detail)


@pytest.mark.parametrize("name", ["eight_rooms_hard", "two_levels_stair", "clinic"])
def test_preverify_accepting_means_the_affinities_check_passes_in_verify(fixtures_dir, name):
    brief = prepared(fixtures_dir, name)
    accepted = [pl for pl in GENERATORS["beam"](brief, None, 0) if preverify(brief, pl)[0]][:3]
    assert accepted
    for pl in accepted:
        assert verify(brief, pl).checks["affinities"][0]


# --- line 3: the soft margin (kernel-free) -----------------------------------------------------------------------

def mean_affinity(brief):
    scores = []
    for seed in range(3):
        scores += [affinity.measure(brief, pl)["score"] for pl in GENERATORS["beam"](brief, None, seed) if preverify(brief, pl)[0]]
    assert scores
    return sum(scores) / len(scores), len(scores)


@pytest.mark.parametrize("name,floor", [("school_three_levels", 0.90), ("small_hospital", 0.82)])
def test_soft_affinity_margin(fixtures_dir, name, floor):
    mean, n = mean_affinity(prepared(fixtures_dir, name))
    print(f"\n{name}: mean affinity {mean:.4f} over {n} pre-verified placements (floor {floor})")
    assert mean >= floor


# --- line 4: no fixture below its M19 baseline -------------------------------------------------------------------

def read(path):
    with open(path) as f:
        return {(r["fixture"], int(r["seed"])): r for r in csv.DictReader(f)}


def test_no_fixture_has_fewer_verified_options_or_a_lower_affinity_than_at_m19():
    old, new = read(M19_CSV), read(M20_CSV)
    assert set(old) <= set(new) and ("eight_rooms_hard", 0) in new
    for key, o in old.items():
        n = new[key]
        assert int(n["verified"]) >= int(o["verified"]), f"{key}: verified {o['verified']} -> {n['verified']}"
        if o["affinity"] != "" and n["affinity"] != "":
            assert float(n["affinity"]) >= float(o["affinity"]) - 1e-6, f"{key}: affinity {o['affinity']} -> {n['affinity']}"
        elif o["affinity"] != "":
            pytest.fail(f"{key}: M19 verified {o['verified']} with an affinity, M20 has none")


# --- line 5: the beam is unchanged where it has nothing to search on ---------------------------------------------

def test_beam_placements_are_identical_on_briefs_without_searched_affinities(fixtures_dir):
    ref = json.loads(REFERENCE.read_text())
    checked = []
    for p in sorted(fixtures_dir.glob("*.yaml")):
        brief = prepare(load(p))[0]
        if any(a.kind in SEARCHED for a in affinity.search_items(brief)):
            continue
        assert p.stem in ref["fixtures"], f"no reference for {p.stem}"
        got = beam_reference(p, ref["seed"])
        assert got == ref["fixtures"][p.stem], p.stem
        checked.append(p.stem)
    assert len(checked) >= 8, checked


# --- line 6: generation time -------------------------------------------------------------------------------------

@pytest.mark.parametrize("name,baseline_s", [("school_three_levels", 20.4), ("small_hospital", 4.3)])
def test_beam_cpu_time_is_within_a_quarter_of_the_scoreboard(fixtures_dir, name, baseline_s):
    brief = prepared(fixtures_dir, name)
    times = []
    for _ in range(3):
        t = time.process_time()
        GENERATORS["beam"](brief, None, 0)
        times.append(time.process_time() - t)
    med = statistics.median(times)
    print(f"\n{name}: beam t_gen (CPU) {[round(x, 2) for x in times]} median {med:.2f} s, limit {1.25 * baseline_s:.2f} s")
    assert med <= 1.25 * baseline_s


# --- line 7: CP-SAT ----------------------------------------------------------------------------------------------

def _room(name, w=3, l=3, **kw):
    return {"name": name, "w": w, "l": l, "h": 3, "program": "room", **kw}


def _two_levels(affs):
    spaces = [_room("w0", 3, 2, wishes={"level": 0}, tags=["wet"]), _room("o0", wishes={"level": 0}),
              _room("w1", 3, 2, wishes={"level": 1}, tags=["wet"]), _room("o1", wishes={"level": 1})]
    d = {"name": "t", "level_height": 3.0, "spaces": spaces, "affinities": affs, "levels": 2,
         "envelope": {"w": 12, "l": 9, "h": 6},
         "circulation": {"corridor": {"w": 1.8, "l": 6}, "stairs": [{"name": "stair", "w": 2.5, "l": 4}]}}
    return prepare(Brief.from_dict(d))[0]


def _solve(brief, k=1, t=15.0, **kw):
    return solve_cpsat(brief, CpsatParams(k=k, time_limit=t, workers=4, **kw), 0)


def test_cpsat_uses_the_affinities_on_a_two_level_brief():
    soft = [{"tag": "wet", "rule": "stack", "strength": "should", "weight": 3}]
    hard = [{"between": ["w0", "w1"], "kind": "stack", "strength": "must"},
            {"between": ["o0", "o1"], "kind": "stack", "strength": "never"}]
    brief = _two_levels(soft)
    on, off = _solve(brief, w_affinity=80_000), _solve(brief, w_affinity=0)
    assert on.placements and off.placements
    s_on, s_off = (affinity.measure(brief, r.placements[0])["score"] for r in (on, off))
    assert s_on >= s_off and s_on == 1.0
    hb = _two_levels(hard)
    res = _solve(hb)
    assert res.placements, res.status
    for pl in res.placements:
        assert affinity.measure(hb, pl)["hard"] == {"met": 2, "total": 2}
        assert preverify(hb, pl)[1]["affinities"][0]


def test_cpsat_reports_a_contradictory_pair_as_impossible():
    d = {"name": "t", "level_height": 3.0, "spaces": [_room("a"), _room("b")],
         "affinities": [{"between": ["a", "b"], "kind": "touch", "strength": "must"},
                        {"between": ["a", "b"], "kind": "touch", "strength": "never"}]}
    res = _solve(prepare(Brief.from_dict(d))[0], k=2, t=10.0)
    assert not res.placements and res.status == "INFEASIBLE"


# --- line 8: the score is ranked ---------------------------------------------------------------------------------

def test_affinity_is_a_metric_and_rank_and_evaluate_top_share_one_weight(fixtures_dir):
    assert "affinity" in METRICS and RANK_WEIGHTS["affinity"] == 5 and set(METRICS) <= set(RANK_WEIGHTS)
    brief = prepared(fixtures_dir, "eight_rooms_hard")
    pls = [pl for pl in GENERATORS["beam"](brief, None, 0) if preverify(brief, pl)[0]][:2]
    assert pls
    opts = evaluate_placements(brief, pls, "beam", 0)
    built = [o for o in opts if o.ok]
    assert built
    for o in built:
        assert o.scores["affinity"] == cheap_scores(brief, o.placement)["affinity"] == round(affinity.measure(brief, o.placement)["score"], 6)
    # rank orders by the same table: an option's key moves with its affinity at weight 5
    a, b = copy.copy(built[0]), copy.copy(built[0])
    a.scores, b.scores = dict(built[0].scores, affinity=1.0), dict(built[0].scores, affinity=0.0)
    assert rank([b, a]) == [a, b]
    assert rank([b, a], {"affinity": 0}) in ([b, a], [a, b])
    top, info = evaluate_top(brief, pls, "beam", 0, keep=1)
    assert top and info["placements"] == len(pls)
