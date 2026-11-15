"""M20: affinities in the beam, the eighth check, level rules and the ranking table (PLAN §4.10). Kernel-free
except where a test imports `verify` for its CHECKS tuple."""
import inspect
import random

import pytest

from spacetope import affinity as af
from spacetope import pipeline
from spacetope.brief import Brief
from spacetope.circulation import BriefInvalid, prepare
from spacetope.levels import assign_levels
from spacetope.preverify import check_affinities, preverify
from spacetope.score import METRICS, cheap_scores
from spacetope.solve import beam as bm
from spacetope.solve.grid import Box


def room(name, **kw):
    return {"name": name, "w": 3, "l": 3, "h": 3, **kw}


def brief(spaces, affinities=None, contacts=None, prep=True, **kw):
    d = {"name": "t", "spaces": spaces, "level_height": 3.0, **kw}
    if affinities:
        d["affinities"] = affinities
    if contacts:
        d["contacts"] = contacts
    b = Brief.from_dict(d)
    return prepare(b)[0] if prep else b      # multi-level briefs need circulation to prepare; these tests do not


def box(x, y, z=0, w=3000, l=3000, h=3000):
    return Box(x, y, z, w, l, h)


def corridor_brief(affinities, rooms=("r1", "r2", "wc", "storage", "meeting"), **kw):
    spaces = [{"name": "cor", "w": 1.8, "l": 12, "h": 3, "program": "corridor"}] + [
        room(n, w=3, l=3, program="room", **kw.get(n, {})) for n in rooms]
    return brief(spaces, affinities, contacts=[["cor", n] for n in rooms])


# --- 1. ordering: a tagged group is one run after the corridors and shafts -----------------------------------------

def test_group_run_follows_corridors_and_keeps_order():
    b = brief([{"name": "cor", "w": 1.8, "l": 12, "h": 3, "program": "corridor"}, room("a"), room("w1", tags=["wet"]), room("b"),
               room("w2", tags=["wet"]), room("c"), room("w3", tags=["wet"])],
              [{"tag": "wet", "rule": "stack", "strength": "should"}], contacts=[["cor", n] for n in "a b c w1 w2 w3".split()])
    p = bm.BeamParams()
    aff = bm.AffinityTerms.of(b, p)
    order = bm.order_spaces(b, random.Random(0))
    names = [s.name for s in aff.group_run(order)]
    assert names[0] == "cor"
    assert names[1:4] == [s.name for s in order if s.name in {"w1", "w2", "w3"}]
    assert [n for n in names if n not in {"w1", "w2", "w3"}] == [s.name for s in order if s.name not in {"w1", "w2", "w3"}]


def test_no_search_affinity_means_no_terms():
    b = brief([room("a", affinities=[{"exterior": True}, {"near": "b"}]), room("b")])
    assert bm.AffinityTerms.of(b, bm.BeamParams()) is None
    assert af.search_items(b) == []
    assert bm.AffinityTerms.of(brief([room("a", affinities=[{"touch": "b"}]), room("b")]), bm.BeamParams(w_affinity=0)) is None


# --- 2. the move term on a hand-built partial ----------------------------------------------------------------------

def test_term_met_broken_and_weighted():
    b = brief([room("a", affinities=[{"touch": "b", "weight": 2}, {"touch": "c", "strength": "avoid"}]), room("b"), room("c")])
    aff = bm.AffinityTerms.of(b, bm.BeamParams())
    assert aff.total({"a": box(0, 0)}) == (0.0, frozenset())                        # a partner not placed: nothing yet
    assert aff.total({"a": box(0, 0), "b": box(3000, 0)})[0] == 16.0                # touch met: 8 x weight 2
    assert aff.total({"a": box(0, 0), "b": box(9000, 0)})[0] == 0.0
    assert aff.total({"a": box(0, 0), "c": box(3000, 0)})[0] == -8.0                # an avoid that is broken costs the same
    assert aff.total({"a": box(0, 0), "b": box(3000, 0), "c": box(0, 3000)})[0] == 8.0


def test_incremental_term_equals_full_recompute():
    b = brief([room("a", affinities=[{"touch": "b"}, {"touch": "c", "strength": "avoid"}]), room("b"), room("c")])
    p = bm.BeamParams()
    aff = bm.AffinityTerms.of(b, p)
    st = bm.state_from_placed(b, {"a": box(0, 0)}, p, None, aff)
    for name, bx in (("b", box(3000, 0)), ("c", box(0, 3000))):
        new = dict(st.placed, **{name: bx})
        nxt = bm.extend_state(b, st, new, name, p, None, aff)
        full = bm.state_from_placed(b, new, p, None, aff)
        assert (nxt.aff, nxt.hits) == (full.aff, full.hits) and abs(nxt.score - full.score) < 1e-9
        st = nxt
    assert st.aff == 0.0                                                            # +8 for the touch, -8 for the avoid


def test_below_boxes_judge_stack_when_the_upper_room_is_placed():
    b = brief([room("lo"), room("up", affinities=[{"stack": "lo", "overlap": 0.5}])], levels=2, prep=False)
    aff = bm.AffinityTerms.of(b, bm.BeamParams(), {"lo": box(0, 0, 0)})
    assert aff.total({"up": box(1000, 0, 3000)})[0] == 8.0
    assert aff.total({"up": box(2000, 0, 3000)})[0] == 0.0
    assert aff.stack_boxes("up") == [box(0, 0, 0)]


def test_a_must_touch_pair_is_rewarded_at_w_required():
    b = corridor_brief([{"between": ["storage", "wc"], "kind": "touch", "strength": "must"}])
    p = bm.BeamParams()
    aff = bm.AffinityTerms.of(b, p)
    assert aff.total({"wc": box(0, 0), "storage": box(3000, 0)})[0] == p.w_required
    assert aff.partners("wc") == {"storage"} and aff.min_overlap("wc", "storage") == 900


# --- 3. a hard move is dropped -------------------------------------------------------------------------------------

def test_moves_that_touch_a_must_apart_pair_are_dropped():
    b = corridor_brief([{"between": ["wc", "meeting"], "kind": "apart", "strength": "must"}], rooms=("wc", "meeting", "r1"))
    p = bm.BeamParams()
    aff = bm.AffinityTerms.of(b, p)
    placed = {"cor": Box(0, 0, 0, 1800, 12000, 3000), "wc": Box(1800, 0, 0, 3000, 3000, 3000)}
    st = bm.state_from_placed(b, placed, p, None, aff)
    plain = bm.moves(b, st, b.space("meeting"), p)
    kept = bm.moves(b, st, b.space("meeting"), p, aff=aff)
    touching = lambda m: not af.holds("apart", {}, m["meeting"], m["wc"], 3000)
    assert any(touching(m) for m in plain)                      # without the rule the beam would touch them
    assert kept and not any(touching(m) for m in kept)
    assert aff.breaks_hard({**placed, "meeting": Box(1800, 3000, 0, 3000, 3000, 3000)}, "meeting", Box(1800, 3000, 0, 3000, 3000, 3000))


def test_a_pair_that_names_a_corridor_is_not_dropped():
    b = brief([{"name": "cor", "w": 1.8, "l": 12, "h": 3, "program": "corridor"}, room("wc", program="room")],
              [{"between": ["cor", "wc"], "kind": "apart", "strength": "must"}])
    assert not bm.AffinityTerms.of(b, bm.BeamParams()).hard


# --- 4. must touch is met on a small brief -------------------------------------------------------------------------

def test_must_touch_is_met_by_every_option():
    b = corridor_brief([{"between": ["storage", "wc"], "kind": "touch", "strength": "must"},
                        {"between": ["wc", "meeting"], "kind": "apart", "strength": "must"}])
    options = bm.beam_search(b, bm.BeamParams(k=4, beam_width=8), 0)
    assert options
    for pl in options:
        assert preverify(b, pl)[0]
        assert af.hard_misses(b, pl) == []


def test_redimension_falls_back_when_it_breaks_a_hard_wish():
    b = corridor_brief([{"between": ["storage", "wc"], "kind": "touch", "strength": "must"}], rooms=("storage", "wc"))
    pl = {"cor": Box(0, 0, 0, 1800, 6000, 3000), "storage": Box(1800, 0, 0, 3000, 3000, 3000), "wc": Box(1800, 3000, 0, 3000, 3000, 3000)}
    assert af.hard_misses(b, pl) == []
    resized = dict(pl, wc=Box(1800, 3000, 0, 1000, 3000, 3000))     # a narrower wc keeps its 3 m wall with storage
    assert af.hard_misses(b, resized) == []
    narrow = dict(pl, wc=Box(1800, 3000, 0, 3000, 3000, 3000), storage=Box(1800, 0, 0, 3000, 2500, 3000))
    assert af.hard_misses(b, narrow) and bm._redim_keeping_hard(b, pl, lambda *_: narrow) == pl
    assert bm._redim_keeping_hard(b, pl, lambda *_: None) == pl
    assert bm._redim_keeping_hard(b, pl, lambda *_: resized) == resized


# --- 5. assign_levels honours the must level rules -----------------------------------------------------------------

def level_brief(affinities, **kw):
    return brief([{"name": f"cor{i}", "w": 1.8, "l": 6, "h": 3, "program": "corridor"} for i in range(1)]
                 + [room(n, w=3 + i, l=3) for i, n in enumerate("abcdef")], affinities, levels=3, prep=False, **kw)


def test_must_ground_and_top():
    d = level_brief([]).to_dict()
    for sp in d["spaces"]:
        sp["affinities"] = ([{"ground": True, "strength": "must"}] if sp["name"] == "c" else
                            [{"top": True, "strength": "must"}] if sp["name"] == "a" else [])
    b = Brief.from_dict(d)
    for seed in range(6):
        lv = assign_levels(b, seed)
        assert lv["c"] == 0 and lv["a"] == 2


def test_should_ground_is_not_a_level_rule():
    b = brief([room("a", affinities=[{"ground": True}]), room("b")], levels=2, prep=False)
    assert af.level_rules(b) == {"ground": [], "top": [], "same": []}


def test_must_same_level_keeps_spaces_together():
    entries = [{"between": ["a", "b"], "kind": "same_level", "strength": "must"}, {"between": ["b", "d"], "kind": "same_level", "strength": "must"}]
    for seed in range(8):
        lv = assign_levels(level_brief(entries), seed)
        assert lv["a"] == lv["b"] == lv["d"]
    seeded = [{"between": ["a", "b"], "kind": "same_level", "strength": "must"}]
    b = level_brief(seeded)
    d = b.to_dict()
    for s in d["spaces"]:
        if s["name"] == "a":
            s["wishes"] = {"level": 1}
    for seed in range(4):
        lv = assign_levels(Brief.from_dict(d), seed)
        assert lv["a"] == 1 and lv["b"] == 1


def test_levels_unchanged_without_level_rules():
    plain = level_brief([])
    withsoft = level_brief([{"between": ["a", "b"], "kind": "same_level"}])
    assert all(assign_levels(plain, s) == assign_levels(withsoft, s) for s in range(4))


# --- 6. hard_misses wording ----------------------------------------------------------------------------------------

def test_hard_misses_lines():
    b = brief([room("a", affinities=[{"touch": "b", "strength": "must"}, {"touch": "c", "strength": "never"},
                                     {"exterior": True, "strength": "must"}, {"touch": "d", "strength": "should"}]),
               room("b"), room("c"), room("d"), room("e", affinities=[{"touch": "b", "strength": "must"}])])
    pl = {"a": box(0, 0), "b": box(9000, 0), "c": box(3000, 0), "d": box(0, 9000)}
    lines = af.hard_misses(b, pl)
    assert lines[0].startswith("a must share a wall with b") and "(measured 0.0 m)" in lines[0]
    assert lines[1].startswith("a must never share a wall with c") and "(measured 3.0 m)" in lines[1]
    assert len(lines) == 2                              # the soft miss, the met exterior wish and the unplaced e do not count
    assert af.hard_misses(b, {**pl, "b": box(3000, 3000)}) != []
    assert af.hard_misses(brief([room("a"), room("b")]), {"a": box(0, 0), "b": box(9000, 0)}) == []


def test_must_apart_on_a_required_pair_is_a_plain_error():
    spaces = [room("a", program="room"), room("b", program="room"), {"name": "cor", "w": 1.8, "l": 6, "h": 3, "program": "corridor"}]
    with pytest.raises(BriefInvalid) as e:
        brief(spaces, [{"between": ["a", "b"], "kind": "apart", "strength": "must"}], contacts=[["a", "b"], ["cor", "a"], ["cor", "b"]])
    assert "also requires them to touch" in str(e.value) or any("also requires" in p.message for p in e.value.problems)
    with pytest.raises(BriefInvalid):
        brief(spaces, [{"between": ["b", "a"], "kind": "touch", "strength": "never"}], contacts=[["a", "b"], ["cor", "a"], ["cor", "b"]])
    brief(spaces, [{"between": ["a", "b"], "kind": "apart", "strength": "should"}], contacts=[["a", "b"], ["cor", "a"], ["cor", "b"]])


# --- 7. the eighth check -------------------------------------------------------------------------------------------

def test_check_is_in_preverify_and_verify():
    from spacetope.verify import CHECKS
    assert CHECKS[-1] == "affinities" and len(CHECKS) == 8
    b = corridor_brief([{"between": ["storage", "wc"], "kind": "touch", "strength": "must"}], rooms=("storage", "wc"))
    good = {"cor": Box(0, 0, 0, 1800, 6000, 3000), "storage": Box(1800, 0, 0, 3000, 3000, 3000), "wc": Box(1800, 3000, 0, 3000, 3000, 3000)}
    ok, checks = preverify(b, good)
    assert ok and checks["affinities"] == (True, "ok")
    bad = dict(good, wc=Box(-3000, 3000, 0, 3000, 3000, 3000))
    ok, checks = preverify(b, bad)
    assert not ok and not checks["affinities"][0] and "storage must share a wall with wc" in checks["affinities"][1]


def test_check_detail_is_capped():
    entries = [{"between": ["r1", n], "kind": "touch", "strength": "must"} for n in ("r2", "wc", "storage", "meeting")]
    b = corridor_brief(entries)
    pl = {n: box(30000 * i, 0) for i, n in enumerate(("cor", "r1", "r2", "wc", "storage", "meeting"))}
    ok, detail = check_affinities(b, pl)
    assert not ok and detail.endswith("and 1 more") and detail.count("must") == 3


# --- 8. ranking ----------------------------------------------------------------------------------------------------

def test_one_rank_table_covers_every_metric():
    assert "affinity" in METRICS and set(pipeline.RANK_WEIGHTS) == set(METRICS) and pipeline.RANK_WEIGHTS["affinity"] == 5
    src = inspect.getsource(pipeline)
    assert src.count('"daylight": 2') == 1                                    # one literal table, read by rank and evaluate_top
    assert "RANK_WEIGHTS" in inspect.getsource(pipeline.rank) and "RANK_WEIGHTS" in inspect.getsource(pipeline.evaluate_top)


def test_plain_briefs_score_affinity_one_and_affinity_moves_the_rank():
    b = brief([room("a"), room("b")])
    assert cheap_scores(b, {"a": box(0, 0), "b": box(3000, 0)})["affinity"] == 1.0
    w = brief([room("a", affinities=[{"touch": "b"}]), room("b")])
    assert cheap_scores(w, {"a": box(0, 0), "b": box(3000, 0)})["affinity"] == 1.0
    assert cheap_scores(w, {"a": box(0, 0), "b": box(9000, 0)})["affinity"] == 0.0
    class Rep:
        ok = True
    mk = lambda name, v: pipeline.Option({}, (), Rep(), {m: 0.0 for m in METRICS} | {"affinity": v}, name)
    assert [o.generator for o in pipeline.rank([mk("lo", 0.0), mk("hi", 1.0)])] == ["hi", "lo"]
