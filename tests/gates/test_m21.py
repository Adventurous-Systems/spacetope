"""M21 gate: site orientation and sun (PLAN §4.10). One group of tests per gate line.

Lines 3 and 4 run the beam on the four briefs in `fixtures/site/` (and on every fixture for line 3) and are the slow
part; the beam output is cached per (brief, seed) so each placement list is generated once. Line 6 reads
`bench/history/2026-11-15_m21_site.csv`, written by `python -m bench.site_baseline`, and re-derives one row.
"""
import csv
import functools
import json
import statistics
import time
from pathlib import Path

import pytest

from bench.beam_reference import beam_reference, placement_hash
from bench.site_baseline import NAMES as SITE_NAMES
from bench.site_baseline import row as site_row
from bench.site_baseline import site_brief
from spacetope import affinity, orient
from spacetope.brief import Brief, load
from spacetope.circulation import BriefInvalid, expand, prepare
from spacetope.floors import brief_for_levels
from spacetope.pipeline import generate
from spacetope.preverify import preverify
from spacetope.programme import variations
from spacetope.score import cheap_scores, score
from spacetope.solve.grid import Box
from spacetope.solve.registry import GENERATORS
from spacetope.verify import verify

pytestmark = [pytest.mark.gate_m21, pytest.mark.slow]
ROOT = Path(__file__).resolve().parent.parent.parent
HIST = ROOT / "bench" / "history"
M20_CSV = HIST / "2026-11-15_m20_affinity.csv"
M21_CSV = HIST / "2026-11-15_m21_site.csv"
REFERENCE = ROOT / "tests" / "gates" / "m20_beam_reference.json"
FLOORS = {"school_three_levels": 0.80, "small_hospital": 0.59, "house_ground": 0.97, "clinic": 0.59}


@functools.lru_cache(maxsize=None)
def site_beam(name, seed):
    brief = site_brief(name)
    return brief, GENERATORS["beam"](brief, None, seed)


@functools.lru_cache(maxsize=None)
def fixture_beam(stem):
    brief = prepare(load(ROOT / "fixtures" / f"{stem}.yaml"))[0]
    return brief, GENERATORS["beam"](brief, None, 0)


def passed(name, seed):
    brief, pls = site_beam(name, seed)
    return brief, [pl for pl in pls if preverify(brief, pl)[0]]


def box(x, y, z=0, w=3000, l=3000, h=3000):
    return Box(x, y, z, w, l, h)


def room(name, **kw):
    return {"name": name, "w": 3, "l": 3, "h": 3, **kw}


# --- line 1: the site survives every transformation; malformed keys give one named problem ---------------------------

def test_site_survives_to_dict_prepare_expand_levels_and_variations():
    site = {"north": 30, "hemisphere": "S"}
    d = load(ROOT / "fixtures" / "site" / "school_three_levels.yaml").to_dict()
    d["site"] = site
    b = Brief.from_dict(d)
    assert b.to_dict()["site"] == site and Brief.from_dict(b.to_dict()).site == site
    once, _ = prepare(b)
    twice, _ = prepare(b)
    assert once.site == twice.site == site
    assert expand(b).site == site                       # circulation.expand rebuilds the Brief field by field
    assert brief_for_levels(b, 2).site == site
    made = [v for seed in range(5) for v in variations(b, seed=seed, kinds=("drop", "duplicate")).values()]
    assert made and all(v.site == site for v in made)
    assert "site" not in load(ROOT / "fixtures" / "clinic.yaml").to_dict()


@pytest.mark.parametrize("site,code", [({"nrth": 3}, "site_key"), ({"north": "up"}, "site_north"), ({"north": True}, "site_north"),
                                       ({"hemisphere": "E"}, "site_hemisphere"), ("north", "site_key")])
def test_each_malformed_site_gives_one_named_problem(site, code):
    b = Brief.from_dict({"name": "t", "level_height": 3.0, "spaces": [room("a")], "site": site})
    with pytest.raises(BriefInvalid) as e:
        prepare(b)
    assert [p.code for p in e.value.problems] == [code]


# --- line 2: the compass ---------------------------------------------------------------------------------------------

@pytest.mark.parametrize("north,expected", [
    (0, {"N": "+y", "E": "+x", "S": "-y", "W": "-x"}), (30, {"N": "+y", "E": "+x", "S": "-y", "W": "-x"}),
    (90, {"N": "+x", "E": "-y", "S": "-x", "W": "+y"}), (180, {"N": "-y", "E": "-x", "S": "+y", "W": "+x"}),
    (270, {"N": "-x", "E": "+y", "S": "+x", "W": "-y"})])
def test_compass_sides_resolve_to_the_nearest_box_side(north, expected):
    for side, face in expected.items():
        assert affinity.compass_faces(side, north) == [face]


def test_the_45_degree_tie_gives_two_sides_and_either_meets_the_wish():
    assert sorted(affinity.compass_faces("N", 45)) == ["+x", "+y"]
    b = Brief.from_dict({"name": "t", "level_height": 3.0, "site": {"north": 45},
                         "spaces": [room("a", affinities=[{"facade": "E"}]), room("b")]})
    covers_x = {"a": box(0, 0), "b": box(3000, 0)}
    covers_y = {"a": box(0, 0), "b": box(0, -3000)}
    for pl in (covers_x, covers_y):                    # E at 45 is +x or -y; one is covered, the other open
        item = affinity.measure(b, pl)["items"][0]
        assert item["met"] is True and item["faces"] == ["+x", "-y"]


def test_sun_follows_the_hemisphere_and_is_measured():
    assert affinity.compass_faces("sun", 0, "N") == ["-y"] and affinity.compass_faces("sun", 0, "S") == ["+y"]
    assert affinity.compass_faces("sun", 90, "N") == ["-x"] and affinity.compass_faces("sun", 90, "S") == ["+x"]
    for hemi, covered in (("N", "-y"), ("S", "+y")):
        b = Brief.from_dict({"name": "t", "level_height": 3.0, "site": {"hemisphere": hemi},
                             "spaces": [room("a", affinities=[{"facade": "sun"}]), room("b")]})
        shut = {"a": box(0, 0), "b": box(0, -3000 if covered == "-y" else 3000)}
        shut_report, open_report = (affinity.measure(b, pl) for pl in (shut, {"a": box(0, 0), "b": box(9000, 0)}))
        assert shut_report["items"][0]["met"] is False and open_report["items"][0]["met"] is True
        assert shut_report["unmeasured"] == 0 and shut_report["items"][0]["side"] == "sun"
        assert shut_report["site"] == {"north": 0.0, "hemisphere": hemi}


@pytest.mark.parametrize("stem", ["clinic", "house_ground", "two_levels_stair", "eight_rooms_hard"])
def test_without_a_site_every_m20_report_is_unchanged_apart_from_the_new_keys(stem):
    brief, pls = fixture_beam(stem)
    assert brief.site is None
    for pl in pls:
        report = affinity.measure(brief, pl)
        assert "site" not in report
        for item in report["items"]:
            extra = {"side", "faces"} if item["kind"] == "facade" else set()
            assert set(item) - extra == {"kind", "a", "others", "strength", "weight", "met", "value", "target", "unit", "by", "source"}
            if item["kind"] == "facade" and item["met"] is not None:     # the M20 reading: the fixed side table
                uncovered = affinity._uncovered(item["a"], pl[item["a"]], pl)[affinity.SIDES[item["side"]]]
                assert item["value"] == round(uncovered / 1000, 6)


# --- line 3: neutral --------------------------------------------------------------------------------------------------

def _same_but_affinity(a, b):
    return {k: v for k, v in a.items() if k != "affinity"} == {k: v for k, v in b.items() if k != "affinity"}


def _neutral(brief, pls):
    n = 0
    for pl in pls:
        ok, _ = preverify(brief, pl)
        base = cheap_scores(brief, pl)
        for name, q in orient.fitting(brief, pl).items():
            assert preverify(brief, q)[0] == ok, f"{brief.name}: {name} changed preverify"
            assert _same_but_affinity(cheap_scores(brief, q), base), f"{brief.name}: {name} changed a cheap score"
            n += 1
    return n


def test_every_accepted_symmetry_is_neutral_on_every_fixture():
    total = 0
    for p in sorted((ROOT / "fixtures").glob("*.yaml")):
        brief, pls = fixture_beam(p.stem)
        total += _neutral(brief, pls)
    assert total > 100


@pytest.mark.parametrize("name", SITE_NAMES)
def test_every_accepted_symmetry_is_neutral_on_the_site_briefs(name):
    brief, pls = site_beam(name, 0)
    assert _neutral(brief, pls) > 8


@pytest.mark.parametrize("name", ["house_ground", "clinic"])
def test_the_kernel_verifier_agrees_on_a_sample(name):
    brief, pls = passed(name, 0)
    for pl in pls[:2]:
        base = verify(brief, pl)
        for sym, q in orient.fitting(brief, pl).items():
            rep = verify(brief, q)
            assert {k: v[0] for k, v in rep.checks.items()} == {k: v[0] for k, v in base.checks.items()}, sym
            assert rep.ok == base.ok
            if rep.ok:
                assert _same_but_affinity(score(rep.realised), score(base.realised)), sym


# --- line 4: the margin -----------------------------------------------------------------------------------------------

@pytest.mark.parametrize("name", SITE_NAMES)
def test_facade_margin_and_no_option_gets_worse(name):
    after, before = [], []
    for seed in range(3):
        brief, pls = passed(name, seed)
        for pl in pls:
            q, rec = orient.best(brief, pl)
            b0, b1 = orient.facade_score(brief, pl)[1], orient.facade_score(brief, q)[1]
            assert (rec["facade_before"], rec["facade_after"]) == (b0, b1)
            assert b1 >= b0 - 1e-9, f"{name} seed {seed}: facade {b0} -> {b1}"
            assert len(affinity.hard_misses(brief, q)) <= len(affinity.hard_misses(brief, pl))
            after.append(b1)
            before.append(b0)
    mean = sum(after) / len(after)
    print(f"\n{name}: facade {sum(before) / len(before):.4f} as generated -> {mean:.4f} over {len(after)} options (floor {FLOORS[name]})")
    assert mean >= FLOORS[name]


def test_generate_applies_the_pass_and_records_it():
    brief = load(ROOT / "fixtures" / "site" / "clinic.yaml")
    options, _, _ = generate(GENERATORS["beam"], brief, 0, None, "beam")
    expanded = site_brief("clinic")
    assert options and all(o.analysis["orientation"].keys() == {"symmetry", "facade_before", "facade_after"} for o in options)
    for o in options:
        assert o.analysis["orientation"]["facade_after"] == orient.facade_score(expanded, o.placement)[1]
        if o.ok:
            assert o.analysis["affinity"]["site"] == {"north": 30.0, "hemisphere": "N"}
    assert any(o.analysis["orientation"]["symmetry"] != "id" for o in options)


# --- line 5: untouched where there is no facade wish ------------------------------------------------------------------

def test_the_pass_is_the_identity_without_a_facade_wish_and_the_m20_hashes_reproduce():
    ref = json.loads(REFERENCE.read_text())
    checked = []
    for p in sorted((ROOT / "fixtures").glob("*.yaml")):
        brief = prepare(load(p))[0]
        if affinity.search_items(brief):     # the beam searches these since M20; they are not in the reference
            continue
        assert p.stem in ref["fixtures"], f"no reference for {p.stem}"
        assert not orient.wants_facade(brief)
        assert beam_reference(p, ref["seed"]) == ref["fixtures"][p.stem], p.stem
        checked.append(p.stem)
    assert len(checked) >= 8, checked
    for stem in ("clinic", "house_ground"):
        brief, pls = fixture_beam(stem)
        options, _, _ = generate(GENERATORS["beam"], load(ROOT / "fixtures" / f"{stem}.yaml"), 0, None, "beam")
        assert placement_hash([o.placement for o in options]) == placement_hash(pls) == ref["fixtures"][stem]["sha256"]
        assert all("orientation" not in o.analysis for o in options)
        assert all(orient.best(brief, pl)[0] is pl or not orient.wants_facade(brief) for pl in pls)


def test_the_m20_affinity_csv_reproduces():
    with open(M20_CSV) as f:
        recorded = {(r["fixture"], int(r["seed"])): r for r in csv.DictReader(f)}
    from bench.affinity_baseline import row
    for stem in ("clinic", "house_ground", "two_levels_stair", "eight_rooms_hard"):
        brief = load(ROOT / "fixtures" / f"{stem}.yaml")
        for seed in range(3):
            got, want = row(stem, brief, seed), recorded[(stem, seed)]
            for key in ("options", "verified", "soft_met", "soft_total", "hard_met", "hard_total", "unmeasured"):
                assert int(got[key]) == int(want[key]), (stem, seed, key)
            assert str(got["affinity"]) == want["affinity"] or abs(float(got["affinity"]) - float(want["affinity"])) < 1e-4


# --- line 6: verified count, signatures, time -------------------------------------------------------------------------

def rows():
    with open(M21_CSV) as f:
        return list(csv.DictReader(f))


def test_the_csv_has_a_row_per_site_brief_and_seed_and_the_pass_loses_no_verified_option():
    got = rows()
    assert {(r["fixture"], int(r["seed"])) for r in got} == {(n, s) for n in SITE_NAMES for s in range(3)}
    for r in got:
        assert int(r["verified_with"]) >= int(r["verified_without"]), r
        assert int(r["signatures_after"]) <= int(r["options"]) and r["symmetries"]
        assert float(r["facade_worst"]) <= float(r["facade_generated"]) + 1e-9 <= float(r["facade_after"]) + 1e-9
    lost = {n: sum(int(r["signatures_before"]) - int(r["signatures_after"]) for r in got if r["fixture"] == n) for n in SITE_NAMES}
    print(f"\ndistinct signatures lost to mirror images: {lost}")


def test_a_recorded_row_agrees_with_the_current_code():
    want = next(r for r in rows() if r["fixture"] == "clinic" and int(r["seed"]) == 0)
    got = site_row("clinic", site_brief("clinic"), 0)
    for key in want:
        if key not in ("t_gen", "t_pass"):
            assert str(got[key]) == want[key], key


def test_the_pass_costs_at_most_five_percent_of_beam_generation_on_the_school():
    brief = site_brief("school_three_levels")
    gen, turn = [], []
    for i in range(3):
        t = time.process_time()
        pls = GENERATORS["beam"](brief, None, 0)
        gen.append(time.process_time() - t)
        t = time.process_time()
        for pl in pls:
            orient.best(brief, pl)
        turn.append(time.process_time() - t)
    g, p = statistics.median(gen), statistics.median(turn)
    print(f"\nschool: beam t_gen {[round(x, 2) for x in gen]} median {g:.2f} s; pass {[round(x, 3) for x in turn]} median {p:.3f} s ({100 * p / g:.2f} %)")
    assert p <= 0.05 * g
