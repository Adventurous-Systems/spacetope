"""M19 gate: affinity vocabulary, expansion and measurement (PLAN §4.10). One group of tests per gate line.

M19 changed no generator: the gate shows that the new brief keys are carried, measured and reported. (Its line 4,
"generators untouched", is retired by M20, whose gate line 5 replaces it.) Unit-level detail lives in `tests/test_affinity.py`.
"""
import csv
import subprocess
import sys
from pathlib import Path

import pytest

from spacetope import affinity
from spacetope.brief import Brief, load
from spacetope.circulation import BriefInvalid, prepare
from spacetope.floors import brief_for_levels
from spacetope.pipeline import generate
from spacetope.preverify import preverify
from spacetope.programme import variations
from spacetope.solve.grid import Box
from spacetope.solve.registry import GENERATORS

pytestmark = [pytest.mark.gate_m19, pytest.mark.slow]
ROOT = Path(__file__).resolve().parent.parent.parent
M20_FIXTURES = {"eight_rooms_hard"}       # added after the M19 baseline was recorded
BASELINE = ROOT / "bench" / "history" / "2026-11-15_m19_affinity.csv"
EDITED = ("school_three_levels", "small_hospital", "apartments_four_levels")


def room(name, **kw):
    return {"name": name, "w": 3, "l": 3, "h": 3, **kw}


def brief(spaces, affinities=None, **kw):
    d = {"name": "t", "spaces": spaces, "level_height": 3.0, **kw}
    if affinities:
        d["affinities"] = affinities
    return Brief.from_dict(d)


def box(x, y, z, w=3000, l=3000, h=3000):
    return Box(x, y, z, w, l, h)


# --- line 1: parse and round trip -------------------------------------------------------------------------------

def test_tags_and_all_three_forms_survive_every_transformation():
    d = {"name": "t", "levels": 1, "circulation": {"corridor": {"w": 1.5, "l": 8}}, "spaces": [
        room("w1", tags=["wet"], affinities=[{"facade": "S"}, {"touch": "q"}]), room("w2", tags=["wet"]),
        room("q", tags=["quiet"], affinities=[{"apart": "w1", "strength": "must"}]), room("r4")],
        "affinities": [{"between": ["w1", "q"], "kind": "near", "depth": 2, "weight": 4}, {"tag": "wet", "rule": "stack"}]}
    b = Brief.from_dict(d)
    assert Brief.from_dict(b.to_dict()).to_dict() == b.to_dict() == Brief.from_dict(d).to_dict()
    once, _ = prepare(b)
    twice, _ = prepare(b)
    assert affinity.expand(b) == affinity.expand(once) == affinity.expand(twice) and affinity.expand(b)
    assert twice.to_dict()["affinities"] == d["affinities"]
    kept = brief_for_levels(Brief.from_dict({**d, "levels": 3}), 2)
    assert [s.tags for s in kept.spaces[:2]] == [("wet",), ("wet",)] and len(kept.affinities) == 2
    for seed in range(5):
        v = variations(b, seed=seed, kinds=("drop", "duplicate"))["drop"]
        names = {s.name for s in v.spaces}
        refs = [n for s in v.spaces for e in s.affinities for n in affinity.refs(e)] + [n for e in v.affinities for n in affinity.refs(e)]
        assert set(refs) <= names | {"corridor_0"}
        assert not [p for p in affinity.validate(v) if p.severity == "error"]


# --- line 2: every kind, both polarities, group rules, a rotated room, a shaft ------------------------------------

def _pair(kind, extra=None, **flags):
    return brief([room("a", affinities=[{kind: "b", **(extra or {}), **flags}]), room("b")])


TOUCH = {"a": box(0, 0, 0), "b": box(3000, 0, 0)}
FAR = {"a": box(0, 0, 0), "b": box(9000, 0, 0)}
UP = {"a": box(0, 0, 0), "b": box(0, 0, 3000)}
# (name, brief, placement where the *positive* wish is met, placement where it is not)
PAIRS = [("touch", _pair("touch"), TOUCH, FAR), ("apart", _pair("apart"), FAR, TOUCH),
         ("near", _pair("near", {"depth": 1}), TOUCH, FAR), ("stack", _pair("stack"), UP, FAR),
         ("same_level", _pair("same_level"), FAR, UP)]


@pytest.mark.parametrize("name,br,yes,no", PAIRS, ids=[p[0] for p in PAIRS])
def test_pair_kinds_and_polarity(name, br, yes, no):
    kind = br.spaces[0].affinities[0]
    neg = brief([room("a", affinities=[{**kind, "strength": "never"}]), room("b")])
    met = lambda b, pl: affinity.measure(b, pl)["items"][0]["met"]
    assert (met(br, yes), met(br, no)) == (True, False)
    assert (met(neg, yes), met(neg, no)) == (False, True)       # `never` is the negation, `met` still means satisfied


def test_site_kinds_polarity_rotation_and_shaft():
    site = brief([room("a", affinities=[{"facade": "E"}, {"exterior": True}, {"ground": True}, {"top": True}]), room("b")])
    free = {"a": box(0, 0, 0), "b": box(0, 3000, 0)}
    got = [i["met"] for i in affinity.measure(site, free)["items"]]
    assert got == [True, True, True, True]
    walled = {"a": box(0, 3000, 0), "b": box(3000, 3000, 0)}          # east neighbour covers the wall
    assert affinity.measure(site, walled)["items"][0]["met"] is False
    rot = brief([room("a", w=6, l=2, affinities=[{"facade": "N"}]), room("b")])
    i = affinity.measure(rot, {"a": box(0, 0, 0, w=2000, l=6000), "b": box(0, 6000, 0, w=500, l=3000)})["items"][0]
    assert (i["met"], i["value"]) == (True, 1.5)                       # the laid box counts, not the nominal one
    shaft = {"name": "st", "w": 2, "l": 2, "h": 6, "program": "stair", "serves": [0, 1]}
    sh = Brief.from_dict({"name": "t", "level_height": 3.0, "levels": 3, "spaces": [
        room("up", affinities=[{"stack": "st"}, {"same_level": "st"}]), shaft]})
    pl = {"up": box(0, 0, 6000, w=2000, l=2000), "st": box(0, 0, 0, w=2000, l=2000, h=6000)}
    assert [i["met"] for i in affinity.measure(sh, pl)["items"]] == [True, False]
    assert affinity.measure(sh, pl | {"up": box(0, 0, 3000, w=2000, l=2000)})["items"][1]["met"] is True


def test_group_rules_any_of_and_scoring():
    spaces = [room(n, tags=["wet"]) for n in ("w1", "w2", "w3")] + [room("q", tags=["quiet"]), room("n", tags=["noisy"])]
    br = brief(spaces, [{"tag": "wet", "rule": "stack"}, {"tag": "wet", "rule": "cluster", "weight": 3},
                        {"tags": ["quiet", "noisy"], "rule": "apart", "strength": "must"}])
    pl = {"w1": box(0, 0, 0), "w2": box(0, 0, 3000), "w3": box(30000, 0, 0), "q": box(9000, 0, 0), "n": box(15000, 0, 0)}
    r = affinity.measure(br, pl)
    by = {(i["source"], i["a"]): (i["met"], i["by"]) for i in r["items"]}
    assert by["tag wet: stack", "w1"] == (True, "w2") and by["tag wet: stack", "w3"][0] is False
    assert [i["met"] for i in r["items"] if "cluster" in i["source"]] == [False] * 3
    assert r["hard"] == {"met": 1, "total": 1} and r["soft"] == {"met": 2, "total": 6}
    assert r["score"] == round(2 / (3 + 9), 6)                         # weights: stack 1 x3, cluster 3 x3
    assert affinity.measure(brief([room("a")]), {"a": box(0, 0, 0)})["score"] == 1.0


# --- line 3: validation ----------------------------------------------------------------------------------------

BAD = [({"touch": "ghost"}, "affinity_space"), ({"adjacent": "b"}, "affinity_kind"), ({"touch": "b", "strength": "maybe"}, "affinity_strength"),
       ({"facade": "Q"}, "affinity_side"), ({"touch": "a"}, "affinity_self"), ({"touch": "b", "min": -1}, "affinity_entry"),
       ({"touch": "b", "colour": "red"}, "affinity_entry"), ({"exterior": "yes"}, "affinity_entry"), ("touch b", "affinity_entry")]
BAD_TOP = [({"between": ["a", "zz"], "kind": "near"}, "affinity_space"), ({"between": ["a", "a"], "kind": "near"}, "affinity_self"),
           ({"between": ["a", "b"], "kind": "sparkle"}, "affinity_kind"), ({"tag": "x", "rule": "dance"}, "affinity_rule"),
           ({"between": ["a"], "kind": "near"}, "affinity_entry")]


@pytest.mark.parametrize("entry,code", BAD)
def test_bad_space_entry_is_one_plain_error(entry, code):
    br = brief([room("a", affinities=[entry]), room("b")])
    (p,) = affinity.validate(br)
    assert (p.severity, p.code) == ("error", code) and p.message.startswith("a") and len(p.message) > 20
    with pytest.raises(BriefInvalid) as e:
        prepare(br)
    assert [q.code for q in e.value.problems] == [code]


@pytest.mark.parametrize("entry,code", BAD_TOP)
def test_bad_top_level_entry_is_one_plain_error(entry, code):
    br = brief([room("a", tags=["x"]), room("b", tags=["x"])], [entry])
    assert [(p.severity, p.code) for p in affinity.validate(br)] == [("error", code)]
    with pytest.raises(BriefInvalid):
        prepare(br)


def test_a_tag_nobody_carries_is_a_warning_not_an_error():
    br = brief([room("a"), room("b")], [{"tag": "ghosts", "rule": "stack"}])
    _, warnings = prepare(br)
    assert [(p.code, p.severity) for p in warnings] == [("affinity_tag", "warning")]


# --- line 4 (generators untouched) is retired by M20; its replacement is M20 gate line 5 (beam hashes) ----------


# --- line 5: no kernel; the report on an option is `measure` on its placement --------------------------------------

def test_affinity_imports_without_topologicpy():
    code = "import sys, spacetope.affinity; sys.exit(1 if 'topologicpy' in sys.modules else 0)"
    assert subprocess.run([sys.executable, "-c", code], cwd=ROOT).returncode == 0


def test_option_report_equals_measure_and_plain_briefs_have_none(fixtures_dir):
    brief_ = load(fixtures_dir / "two_levels_stair.yaml")
    options, _, _ = generate(GENERATORS["beam"], brief_, 0, None, "beam")
    verified = [o for o in options if o.ok]
    assert verified
    for o in verified:
        assert o.analysis["affinity"] == affinity.measure(o.realised.brief, o.placement)
    plain, _, _ = generate(GENERATORS["beam"], load(fixtures_dir / "three_rooms.yaml"), 0, None, "beam")
    assert plain and all("affinity" not in o.analysis for o in plain)


# --- line 6: the baseline is recorded and cannot go stale --------------------------------------------------------

def rows():
    with open(BASELINE) as f:
        return list(csv.DictReader(f))


def test_baseline_has_a_row_per_fixture_with_affinities_and_seed(fixtures_dir):
    # pinned to the fixtures that existed at M19: fixtures added later (eight_rooms_hard) are not in this CSV
    expected = {p.stem for p in sorted(fixtures_dir.glob("*.yaml")) if p.stem not in M20_FIXTURES and affinity.expand(prepare(load(p))[0])}
    assert set(EDITED) <= expected and {"clinic", "two_levels_stair", "three_levels_core"} <= expected
    got = {(r["fixture"], r["generator"], int(r["seed"])) for r in rows()}
    assert got == {(fx, "beam", s) for fx in expected for s in range(3)}
    for r in rows():
        assert int(r["verified"]) <= int(r["options"]) and int(r["soft_met"]) <= int(r["soft_total"]) and int(r["hard_met"]) <= int(r["hard_total"])


def test_recorded_numbers_agree_with_the_current_code(fixtures_dir):
    """Kernel-free recomputation on one cheap fixture: the beam's pre-verified placements, measured now."""
    fx, seed = "two_levels_stair", 0
    (rec,) = [r for r in rows() if r["fixture"] == fx and int(r["seed"]) == seed]
    expanded, _ = prepare(load(fixtures_dir / f"{fx}.yaml"))
    reports = [affinity.measure(expanded, pl) for pl in GENERATORS["beam"](expanded, None, seed) if preverify(expanded, pl)[0]]
    assert len(reports) == int(rec["verified"])
    for key in ("soft", "hard"):
        assert sum(r[key]["met"] for r in reports) == int(rec[f"{key}_met"])
        assert sum(r[key]["total"] for r in reports) == int(rec[f"{key}_total"])
    assert round(sum(r["score"] for r in reports) / len(reports), 4) == float(rec["affinity"])
