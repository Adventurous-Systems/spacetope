"""M19: affinity vocabulary, expansion, validation and measurement on hand-built placements (no kernel)."""
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


def brief(spaces, affinities=None, **kw):
    d = {"name": "t", "spaces": spaces, "level_height": 3.0, **kw}
    if affinities:
        d["affinities"] = affinities
    return Brief.from_dict(d)


def box(x, y, z, w=3000, l=3000, h=3000):
    return Box(x, y, z, w, l, h)


def item(brief_, placement, i=0):
    return af.measure(brief_, placement)["items"][i]


def pair_brief(entry, names=("a", "b"), **kw):
    return brief([room(names[0], affinities=[entry]), room(names[1])], **kw)


# --- vocabulary -------------------------------------------------------------

def test_slp_scale():
    assert [af.slp(c) for c in "AEIOUX"] == [("must", None), ("should", 4), ("should", 2), ("should", 1), None, ("avoid", None)]
    assert af.SIDES == {"N": "+y", "E": "+x", "S": "-y", "W": "-x"}


# --- touch / apart / near / stack / same_level, both polarities ------------

def test_touch_both_polarities():
    pl = {"a": box(0, 0, 0), "b": box(3000, 0, 0)}
    i = item(pair_brief({"touch": "b"}), pl)
    assert (i["met"], i["value"], i["target"], i["unit"], i["by"]) == (True, 3.0, 0.9, "m", "b")
    assert item(pair_brief({"touch": "b", "strength": "never"}), pl)["met"] is False
    far = {"a": box(0, 0, 0), "b": box(3000, 2500, 0)}          # 0.5 m of shared wall: below a door
    assert item(pair_brief({"touch": "b"}), far)["met"] is False
    assert item(pair_brief({"touch": "b", "min": 0.4}), far)["met"] is True
    assert item(pair_brief({"touch": "b", "strength": "avoid"}), far)["met"] is True


def test_apart_counts_floors_and_walls():
    side = {"a": box(0, 0, 0), "b": box(3000, 0, 0)}
    above = {"a": box(0, 0, 0), "b": box(0, 0, 3000)}
    gap = {"a": box(0, 0, 0), "b": box(5000, 0, 0)}
    br = pair_brief({"apart": "b", "strength": "must"})
    assert item(br, side)["met"] is False and item(br, side)["value"] == 9.0
    assert item(br, above)["met"] is False
    i = item(br, gap)
    assert (i["met"], i["value"], i["unit"]) == (True, 0.0, "m2")
    assert item(pair_brief({"apart": "b", "strength": "never"}), side)["met"] is True


def test_near_door_graph_depth_legacy():
    spaces = [room("a", affinities=[{"near": "c", "depth": 2}]), room("b"), room("c")]
    br = brief(spaces)
    chain = {"a": box(0, 0, 0), "b": box(3000, 0, 0), "c": box(6000, 0, 0)}
    i = item(br, chain)
    assert (i["met"], i["value"], i["target"], i["unit"]) == (True, 2, 2, "doors")
    i = item(brief([room("a", affinities=[{"near": "c", "depth": 1}]), room("b"), room("c")]), chain)
    assert i["met"] is False and i["value"] == 2
    apart = {"a": box(0, 0, 0), "b": box(3000, 0, 0), "c": box(20000, 0, 0)}
    i = item(br, apart)
    assert i["met"] is False and i["value"] is None
    never = brief([room("a", affinities=[{"near": "c", "strength": "never"}]), room("b"), room("c")])
    assert item(never, apart)["met"] is True and item(never, chain)["met"] is False


def test_stack_overlap_share_and_adjacency():
    br = pair_brief({"stack": "b"})
    full = {"a": box(0, 0, 0), "b": box(0, 0, 3000)}
    half = {"a": box(0, 0, 0), "b": box(1500, 0, 3000)}
    off = {"a": box(0, 0, 0), "b": box(2000, 0, 3000)}
    two_up = {"a": box(0, 0, 0), "b": box(0, 0, 6000)}
    assert item(br, full)["value"] == 1.0 and item(br, full)["met"]
    assert item(br, half)["met"] is True and item(br, half)["value"] == 0.5
    assert item(br, off)["met"] is False
    assert item(br, two_up)["met"] is False
    assert item(pair_brief({"stack": "b", "strength": "avoid"}), full)["met"] is False


def test_same_level():
    br = pair_brief({"same_level": "b"})
    assert item(br, {"a": box(0, 0, 0), "b": box(9000, 0, 0)})["met"] is True
    i = item(br, {"a": box(0, 0, 0), "b": box(0, 0, 3000)})
    assert (i["met"], i["value"], i["unit"]) == (False, 1, "levels")
    assert item(pair_brief({"same_level": "b", "strength": "never"}), {"a": box(0, 0, 0), "b": box(0, 0, 3000)})["met"] is True


# --- site kinds -------------------------------------------------------------

def test_facade_and_exterior_uncovered_wall():
    br = brief([room("a", affinities=[{"facade": "E"}]), room("b")])
    east_free = {"a": box(0, 0, 0), "b": box(0, 3000, 0)}
    i = item(br, east_free)
    assert (i["met"], i["value"], i["target"], i["unit"]) == (True, 3.0, 1.0, "m")
    east_blocked = {"a": box(0, 0, 0), "b": box(3000, 0, 0)}
    assert item(br, east_blocked)["met"] is False and item(br, east_blocked)["value"] == 0.0
    partly = {"a": box(0, 0, 0), "b": box(3000, 0, 0, l=2500)}      # 0.5 m of the east wall left
    assert item(br, partly)["met"] is False
    south = brief([room("a", affinities=[{"facade": "S", "strength": "never"}]), room("b")])
    assert item(south, east_blocked)["met"] is False
    ext = brief([room("a", affinities=[{"exterior": True}]), room("b")])
    wrapped = {"a": box(3000, 3000, 0), "b": box(0, 0, 0)}
    assert item(ext, wrapped)["met"] is True
    boxed = {"a": box(3000, 3000, 0), "b": box(6000, 3000, 0)}
    assert item(ext, boxed)["value"] == 3.0                         # north and south are still free


def test_exterior_unmet_when_surrounded():
    ring = {"a": box(3000, 3000, 0)}
    names = ["n", "s", "e", "w"]
    ring |= {"n": box(3000, 6000, 0), "s": box(3000, 0, 0), "e": box(6000, 3000, 0), "w": box(0, 3000, 0)}
    br = brief([room("a", affinities=[{"exterior": True}])] + [room(n) for n in names])
    i = item(br, ring)
    assert i["met"] is False and i["value"] == 0.0
    never = brief([room("a", affinities=[{"exterior": True, "strength": "never"}])] + [room(n) for n in names])
    assert item(never, ring)["met"] is True


def test_ground_and_top():
    br = brief([room("a", affinities=[{"ground": True}]), room("b", affinities=[{"top": True}, {"ground": True, "strength": "never"}])])
    pl = {"a": box(0, 0, 0), "b": box(0, 0, 3000)}
    items = af.measure(br, pl)["items"]
    assert [i["met"] for i in items] == [True, True, True]
    pl = {"a": box(0, 0, 0), "b": box(0, 0, 0)}
    assert [i["met"] for i in af.measure(br, pl)["items"]] == [True, True, False]
    assert [i["met"] for i in af.measure(br, {"a": box(0, 0, 3000), "b": box(0, 0, 0)})["items"]] == [False, False, False]


def test_facade_sun_is_measured_since_m21_and_a_missing_space_is_unmeasured():
    br = brief([room("a", affinities=[{"facade": "sun"}, {"touch": "b"}]), room("b"), room("c")])
    r = af.measure(br, {"a": box(0, 0, 0)})
    assert r["unmeasured"] == 1 and r["soft"] == {"met": 1, "total": 1}
    assert [i["met"] for i in r["items"]] == [True, None]
    r = af.measure(br, {"a": box(0, 0, 0), "b": box(3000, 0, 0)})
    assert r["unmeasured"] == 0 and r["soft"] == {"met": 2, "total": 2}


# --- rotated rooms and shafts ----------------------------------------------

def test_rotated_room_uses_the_box_not_the_nominal():
    br = brief([room("a", w=6, l=2, affinities=[{"facade": "N"}]), room("b")])
    # a is laid 2 wide (x) by 6 long (y); b covers its north face except nothing: north wall is 2 m long
    pl = {"a": box(0, 0, 0, w=2000, l=6000), "b": box(0, 6000, 0, w=500, l=3000)}
    i = item(br, pl)
    assert i["value"] == 1.5 and i["met"] is True
    pl = {"a": box(0, 0, 0, w=2000, l=6000), "b": box(0, 6000, 0, w=1500, l=3000)}
    assert item(br, pl)["met"] is False


def test_shaft_spans_levels_for_stack_and_same_level():
    shaft = {"name": "st", "w": 2, "l": 2, "h": 6, "program": "stair", "serves": [0, 1]}
    d = {"name": "t", "level_height": 3.0, "levels": 3, "spaces": [
        room("up", affinities=[{"stack": "st"}, {"same_level": "st"}]), shaft, room("low", affinities=[{"same_level": "st"}])]}
    br = Brief.from_dict(d)
    pl = {"up": box(0, 0, 6000, w=2000, l=2000), "st": box(0, 0, 0, w=2000, l=2000, h=6000), "low": box(5000, 0, 3000)}
    items = af.measure(br, pl)["items"]
    assert items[0]["met"] is True                      # the shaft's top is the room's floor
    assert items[1]["met"] is False and items[1]["value"] == 1
    assert items[2]["met"] is True                      # the shaft spans the room's level
    assert af.measure(br, pl | {"up": box(0, 0, 3000, w=2000, l=2000)})["items"][1]["met"] is True


# --- group rules -----------------------------------------------------------

def test_expand_tag_rules():
    spaces = [room("w1", tags=["wet"]), room("w2", tags=["wet"]), room("w3", tags=["wet"]),
              room("q1", tags=["quiet"]), room("n1", tags=["noisy"]), room("n2", tags=["noisy"]), room("solo", tags=["one"])]
    rules = [{"tag": "wet", "rule": "stack"}, {"tag": "wet", "rule": "cluster"}, {"tag": "wet", "rule": "same_level"},
             {"tags": ["quiet", "noisy"], "rule": "apart", "strength": "must"}, {"tag": "noisy", "rule": "apart"},
             {"tags": ["quiet", "noisy"], "rule": "near", "weight": 3}, {"tag": "one", "rule": "stack"}]
    out = af.expand(brief(spaces, rules))
    stack = [x for x in out if x.source == "tag wet: stack"]
    assert [(x.kind, x.a, x.others) for x in stack] == [("stack", "w1", ("w2", "w3")), ("stack", "w2", ("w1", "w3")), ("stack", "w3", ("w1", "w2"))]
    cluster = [x for x in out if x.source == "tag wet: cluster"]
    assert cluster[0].kind == "touch" and cluster[0].params == {"min": 0.001} and cluster[0].others == ("w2", "w3")
    same = [x for x in out if x.kind == "same_level"]
    assert [(x.a, x.others) for x in same] == [("w2", ("w1",)), ("w3", ("w1",))]
    apart = [(x.a, x.others, x.strength) for x in out if x.source == "tags quiet, noisy: apart"]
    assert apart == [("q1", ("n1",), "must"), ("q1", ("n2",), "must")]
    within = [(x.a, x.others) for x in out if x.source == "tag noisy: apart"]
    assert within == [("n1", ("n2",))]
    near = [x for x in out if x.kind == "near"]
    assert [(x.a, x.others, x.weight) for x in near] == [("q1", ("n1", "n2"), 3)]
    assert not [x for x in out if "one" in x.source]


def test_group_measurement_any_of():
    spaces = [room("w1", tags=["wet"]), room("w2", tags=["wet"]), room("w3", tags=["wet"])]
    br = brief(spaces, [{"tag": "wet", "rule": "stack"}, {"tag": "wet", "rule": "cluster"}])
    pl = {"w1": box(0, 0, 0), "w2": box(0, 0, 3000), "w3": box(20000, 0, 0)}
    r = af.measure(br, pl)
    stack = r["items"][:3]
    assert [(i["met"], i["by"]) for i in stack] == [(True, "w2"), (True, "w1"), (False, "w1")]
    assert stack[2]["value"] == 0.0
    cluster = r["items"][3:]
    assert [i["met"] for i in cluster] == [False, False, False]
    r = af.measure(br, pl | {"w3": box(3000, 0, 0)})
    assert r["items"][3]["met"] and r["items"][3]["by"] == "w3"


def test_near_rule_and_negative_group():
    spaces = [room("ward", tags=["ward"]), room("n1", tags=["nurse"]), room("n2", tags=["nurse"])]
    br = brief(spaces, [{"tags": ["ward", "nurse"], "rule": "near", "strength": "never"}])
    pl = {"ward": box(0, 0, 0), "n1": box(3000, 0, 0), "n2": box(30000, 0, 0)}
    i = item(br, pl)
    assert i["met"] is False and i["by"] == "n1"
    assert item(br, {"ward": box(0, 0, 0), "n1": box(20000, 0, 0), "n2": box(30000, 0, 0)})["met"] is True


# --- legacy wish, scoring ---------------------------------------------------

def test_legacy_exterior_wish():
    br = brief([room("a", wishes={"exterior": True}), room("b")])
    (x,) = af.expand(br)
    assert (x.kind, x.strength, x.weight, x.source) == ("exterior", "should", 1, "wishes.exterior")
    explicit = brief([room("a", wishes={"exterior": True}, affinities=[{"exterior": True, "strength": "must"}]), room("b")])
    assert [(x.strength, x.source) for x in af.expand(explicit)] == [("must", "a: exterior")]


def test_score_weights_soft_items_only():
    br = brief([room("a", affinities=[{"touch": "b", "weight": 3}, {"touch": "c", "weight": 1}, {"apart": "d", "strength": "must"}]),
                room("b"), room("c"), room("d")])
    pl = {"a": box(0, 0, 0), "b": box(3000, 0, 0), "c": box(20000, 0, 0), "d": box(3000, 3000, 0)}
    r = af.measure(br, pl)
    assert r["score"] == 0.75
    assert r["soft"] == {"met": 1, "total": 2} and r["hard"] == {"met": 1, "total": 1}
    assert af.measure(brief([room("a")]), {"a": box(0, 0, 0)}) == {"score": 1.0, "soft": {"met": 0, "total": 0}, "hard": {"met": 0, "total": 0}, "unmeasured": 0, "items": []}


def test_measure_is_json_serialisable():
    import json
    br = brief([room("a", affinities=[{"touch": "b"}, {"facade": "sun"}, {"near": "b"}]), room("b")])
    json.dumps(af.measure(br, {"a": box(0, 0, 0), "b": box(3000, 0, 0)}))


# --- validation -------------------------------------------------------------

BAD = [
    ({"touch": "ghost"}, "affinity_space", "ghost"),
    ({"adjacent": "b"}, "affinity_kind", "unknown kind"),
    ({"touch": "b", "strength": "maybe"}, "affinity_strength", "maybe"),
    ({"facade": "Q"}, "affinity_side", "'Q'"),
    ({"touch": "a"}, "affinity_self", "itself"),
    ({"touch": "b", "min": -1}, "affinity_entry", "min"),
    ({"touch": "b", "colour": "red"}, "affinity_entry", "colour"),
    ({"exterior": "yes"}, "affinity_entry", "exterior: true"),
    ("touch b", "affinity_entry", "mapping"),
]


@pytest.mark.parametrize("entry,code,text", BAD)
def test_space_entry_errors(entry, code, text):
    br = pair_brief(entry)
    (p,) = af.validate(br)
    assert p.severity == "error" and p.code == code and text in p.message and p.message.startswith("a")
    with pytest.raises(BriefInvalid) as e:
        prepare(br)
    assert [q.code for q in e.value.problems] == [code]


def test_top_level_errors_and_tag_warning():
    spaces = [room("a", tags=["x"]), room("b", tags=["x"])]
    bad = [{"between": ["a", "zz"], "kind": "near"}, {"between": ["a", "a"], "kind": "near"}, {"between": ["a", "b"], "kind": "sparkle"},
           {"between": ["a", "b"], "kind": "ground"}, {"tag": "x", "rule": "dance"}, {"between": ["a"], "kind": "near"},
           {"tags": ["x", "y"], "rule": "stack"}]
    br = brief(spaces, bad)
    assert [p.code for p in af.validate(br)] == ["affinity_space", "affinity_self", "affinity_kind", "affinity_kind", "affinity_rule",
                                                 "affinity_entry", "affinity_entry"]
    warn = af.validate(brief(spaces, [{"tag": "ghosts", "rule": "stack"}]))
    assert [(p.code, p.severity) for p in warn] == [("affinity_tag", "warning")]
    _, warnings = prepare(brief(spaces, [{"tag": "ghosts", "rule": "stack"}]))
    assert [p.code for p in warnings] == ["affinity_tag"]


def test_generated_names_are_valid_targets_and_exterior_wish_is_silent():
    d = {"name": "t", "levels": 1, "circulation": {"corridor": {"w": 1.5, "l": 8}}, "spaces": [
        room("a", wishes={"exterior": True}, affinities=[{"near": "corridor_0"}])]}
    br = Brief.from_dict(d)
    assert af.validate(br) == []
    _, warnings = prepare(br)
    assert warnings == [] or all(p.code != "affinity_tag" for p in warnings)


# --- round trips ------------------------------------------------------------

def rich():
    return brief([room("w1", tags=["wet"], affinities=[{"facade": "S", "strength": "should"}]), room("w2", tags=["wet"]),
                  room("q", tags=["quiet"], affinities=[{"apart": "w1"}])],
                 [{"between": ["w1", "q"], "kind": "near", "depth": 2, "weight": 4}, {"tag": "wet", "rule": "stack"}])


def test_round_trip_and_unchanged_serialisation():
    b = rich()
    d = b.to_dict()
    assert d["spaces"][0]["tags"] == ["wet"] and d["affinities"][1] == {"tag": "wet", "rule": "stack"}
    assert Brief.from_dict(d).to_dict() == d
    plain = brief([room("a")]).to_dict()
    assert "affinities" not in plain and "tags" not in plain["spaces"][0] and "affinities" not in plain["spaces"][0]


def test_prepare_twice_gives_same_expansion():
    for d in (rich().to_dict(),
              {**rich().to_dict(), "levels": 1, "circulation": {"corridor": {"w": 1.5, "l": 8}}}):
        b = Brief.from_dict(d)
        once, _ = prepare(b)
        twice, _ = prepare(b)
        assert af.expand(b) == af.expand(once) == af.expand(twice)
        assert twice.to_dict()["affinities"] == d["affinities"]


def test_brief_for_levels_keeps_and_prunes():
    d = {"name": "t", "levels": 3, "circulation": {"corridor": {"w": 1.5, "l": 8}}, "spaces": [
        room("a", tags=["wet"], affinities=[{"near": "corridor_2"}, {"touch": "b"}]), room("b", tags=["wet"])],
         "affinities": [{"between": ["b", "corridor_2"], "kind": "near"}, {"tag": "wet", "rule": "stack"}]}
    out = brief_for_levels(Brief.from_dict(d), 1)
    assert [dict(e) for e in out.spaces[0].affinities] == [{"touch": "b"}]
    assert out.spaces[0].tags == ("wet",)
    assert out.affinities == [{"tag": "wet", "rule": "stack"}]
    keep = brief_for_levels(Brief.from_dict(d), 3)
    assert len(keep.spaces[0].affinities) == 2 and len(keep.affinities) == 2


def test_variations_drop_and_duplicate():
    spaces = [room(n, tags=["t"], affinities=[{"touch": nxt}]) for n, nxt in (("r1", "r2"), ("r2", "r3"), ("r3", "r1"))]
    spaces += [room("r4")]
    b = brief(spaces, [{"between": ["r1", "r4"], "kind": "near"}, {"tag": "t", "rule": "stack"}])
    found = False
    for seed in range(40):
        v = variations(b, seed=seed, kinds=("drop",)).get("drop")
        gone = ({"r1", "r2", "r3", "r4"} - {s.name for s in v.spaces}).pop()
        names = {s.name for s in v.spaces}
        assert all(n in names for s in v.spaces for e in s.affinities for n in af.refs(e))
        assert all(n in names for e in v.affinities for n in af.refs(e))
        assert af.validate(v) == [] or all(p.severity == "warning" for p in af.validate(v))
        found |= gone == "r4"
    assert found
    dup = variations(b, seed=1, kinds=("duplicate",))["duplicate"]
    copy = dup.space(next(s.name for s in dup.spaces if s.name.endswith("_copy")))
    assert copy.tags == ("t",) and len(copy.affinities) == 1


def test_dataset_round_trip():
    b = rich()
    assert Brief.from_dict(Brief.from_dict(b.to_dict()).to_dict()).to_dict() == b.to_dict()


def test_affinity_module_needs_no_kernel():
    pure = "import sys, spacetope.affinity; sys.exit(1 if 'topologicpy' in sys.modules else 0)"
    assert subprocess.run([sys.executable, "-c", pure]).returncode == 0
    from spacetope.score import access_graph
    assert access_graph is af.access_graph
