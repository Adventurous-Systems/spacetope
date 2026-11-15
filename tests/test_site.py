"""M21: the site block, compass resolution and `facade: sun` on hand-built placements (no kernel)."""
import copy
import subprocess
import sys

import pytest

from spacetope import affinity as af
from spacetope.brief import Brief
from spacetope.circulation import BriefInvalid, prepare
from spacetope.floors import brief_for_levels
from spacetope.programme import variations
from spacetope.solve.grid import Box


def room(name, **kw):
    return {"name": name, "w": 3, "l": 3, "h": 3, **kw}


def brief(spaces, site=None, **kw):
    d = {"name": "t", "spaces": spaces, "level_height": 3.0, **kw}
    if site is not None:
        d["site"] = site
    return Brief.from_dict(d)


def box(x, y, z=0, w=3000, l=3000, h=3000):
    return Box(x, y, z, w, l, h)


# --- the block travels with the brief -----------------------------------------------------------------------------

def test_site_round_trips_and_is_emitted_only_when_present():
    assert "site" not in brief([room("a")]).to_dict()
    site = {"north": 30, "hemisphere": "S"}
    b = brief([room("a", affinities=[{"facade": "sun"}]), room("b"), room("c"), room("d")], site, levels=1,
              circulation={"corridor": {"w": 1.5, "l": 6}})
    assert b.to_dict()["site"] == site and Brief.from_dict(b.to_dict()).to_dict() == b.to_dict()
    once, _ = prepare(b)
    twice, _ = prepare(b)
    assert once.site == twice.site == site and once.to_dict()["site"] == site
    assert brief_for_levels(b, 2).site == site
    made = [v for seed in range(5) for v in variations(b, seed=seed, kinds=("drop", "duplicate")).values()]
    assert made and all(v.site == site for v in made)


@pytest.mark.parametrize("site,code", [({"nrth": 3}, "site_key"), ({"north": "up"}, "site_north"), ({"north": True}, "site_north"),
                                       ({"north": float("nan")}, "site_north"), ({"hemisphere": "E"}, "site_hemisphere"),
                                       ("north", "site_key")])
def test_each_malformed_site_gives_one_named_problem(site, code):
    problems = af.validate_site(brief([room("a")], site))
    assert [p.code for p in problems] == [code] and problems[0].severity == "error"
    with pytest.raises(BriefInvalid) as e:
        prepare(brief([room("a")], site))
    assert [p.code for p in e.value.problems] == [code]


def test_a_good_site_has_no_problem_and_defaults_apply():
    assert af.validate_site(brief([room("a")], {"north": -20.5, "hemisphere": "N"})) == []
    assert af.validate_site(brief([room("a")], {})) == []
    assert af.site_of(brief([room("a")])) == (0.0, "N")
    assert af.site_of(brief([room("a")], {"north": -90, "hemisphere": "S"})) == (270.0, "S")


# --- compass resolution --------------------------------------------------------------------------------------------

@pytest.mark.parametrize("north,side,faces", [
    (0, "N", ["+y"]), (0, "E", ["+x"]), (0, "S", ["-y"]), (0, "W", ["-x"]),
    (30, "E", ["+x"]), (30, "S", ["-y"]), (30, "N", ["+y"]),
    (90, "N", ["+x"]), (90, "E", ["-y"]), (90, "S", ["-x"]), (90, "W", ["+y"]),
    (180, "N", ["-y"]), (180, "E", ["-x"]), (180, "S", ["+y"]),
    (270, "N", ["-x"]), (270, "E", ["+y"]), (270, "S", ["+x"]),
    (45, "N", ["+x", "+y"]), (45, "E", ["+x", "-y"]), (45, "S", ["-x", "-y"]), (45, "W", ["-x", "+y"]),
    (44.9, "N", ["+y"]), (45.1, "N", ["+x"])])
def test_compass_side_resolves_to_the_box_sides_within_45_degrees(north, side, faces):
    assert sorted(af.compass_faces(side, north)) == sorted(faces)


def test_sun_follows_the_hemisphere():
    assert af.compass_faces("sun", 0, "N") == ["-y"] and af.compass_faces("sun", 0, "S") == ["+y"]
    assert af.compass_faces("sun", 90, "N") == ["-x"] and af.compass_faces("sun", 180, "S") == ["-y"]


def _facade(side, site=None, strength="should"):
    b = brief([room("a", affinities=[{"facade": side, "strength": strength}]), room("b")], site)
    return af.measure(b, {"a": box(0, 0), "b": box(3000, 0)})   # b covers a's +x wall


def test_measurement_uses_the_site_and_the_tie_meets_the_wish_through_either_side():
    assert _facade("E")["items"][0]["met"] is False                       # +x is covered
    r = _facade("E", {"north": 90})["items"][0]                            # E is now -y, open
    assert r["met"] is True and r["value"] == 3.0 and r["faces"] == ["-y"] and r["side"] == "E"
    tie = _facade("E", {"north": 45})["items"][0]                          # +x (covered) and -y (open) tie
    assert tie["met"] is True and tie["faces"] == ["+x", "-y"]
    assert _facade("N", {"north": 45})["items"][0]["faces"] == ["+x", "+y"]


def test_sun_is_measured_in_both_hemispheres():
    assert _facade("sun")["items"][0]["met"] is True                       # -y is open
    for north, hemi, met in ((0, "N", True), (180, "N", True), (0, "S", True)):
        assert _facade("sun", {"north": north, "hemisphere": hemi})["items"][0]["met"] is met
    b = brief([room("a", affinities=[{"facade": "sun"}]), room("b"), room("c")], {"hemisphere": "N", "north": 0})
    covered = {"a": box(0, 0), "b": box(0, -3000)}                         # b covers a's -y, the sun side
    r = af.measure(b, covered)
    assert r["items"][0]["met"] is False and r["unmeasured"] == 0 and r["soft"] == {"met": 0, "total": 1}
    south = brief([room("a", affinities=[{"facade": "sun"}]), room("b")], {"hemisphere": "S"})
    assert af.measure(south, covered)["items"][0]["met"] is True           # the sun side is +y there


def test_report_keys_are_additive_and_absent_without_a_site():
    b = brief([room("a", affinities=[{"facade": "sun"}, {"exterior": True}]), room("b")])
    r = af.measure(b, {"a": box(0, 0), "b": box(3000, 0)})
    assert "site" not in r
    assert r["items"][0]["side"] == "sun" and r["items"][0]["faces"] == ["-y"]
    assert "side" not in r["items"][1] and "faces" not in r["items"][1]
    with_site = af.measure(brief([room("a", affinities=[{"facade": "sun"}])], {"north": 10}), {"a": box(0, 0)})
    assert with_site["site"] == {"north": 10.0, "hemisphere": "N"}


def test_a_report_without_site_equals_the_site_free_reading_apart_from_the_new_keys():
    spaces = [room("a", affinities=[{"facade": "W"}, {"facade": "N", "strength": "avoid"}]), room("b")]
    pl = {"a": box(0, 0), "b": box(3000, 0)}
    plain = af.measure(brief(spaces), pl)
    explicit = af.measure(brief(copy.deepcopy(spaces), {"north": 0, "hemisphere": "N"}), pl)
    strip = lambda r: [{k: v for k, v in i.items() if k not in ("side", "faces")} for i in r["items"]]
    assert strip(plain) == strip(explicit) and plain["score"] == explicit["score"]
    assert [i["met"] for i in plain["items"]] == [True, False]


def test_describe_reads_faces_the_equator_for_sun():
    b = brief([room("a", affinities=[{"facade": "sun", "strength": "must"}]), room("b")])
    miss = af.measure(b, {"a": box(0, 0), "b": box(0, -3000)})["items"][0]
    assert miss["met"] is False
    assert af.describe(miss) == "a must have an outside wall that faces the equator (measured 0.0 m)"
    assert af.hard_misses(b, {"a": box(0, 0), "b": box(0, -3000)}) == [af.describe(miss)]
    assert af.hard_misses(b, {"a": box(0, 0), "b": box(0, 3000)}) == []


def test_affinity_stays_free_of_the_kernel():
    code = "import sys, spacetope.affinity, spacetope.orient; sys.exit(1 if 'topologicpy' in sys.modules else 0)"
    assert subprocess.run([sys.executable, "-c", code]).returncode == 0
