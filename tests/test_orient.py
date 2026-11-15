"""M21: the eight symmetries of a placement and the orientation pass (no kernel)."""
from spacetope import affinity as af
from spacetope import orient
from spacetope.brief import Brief
from spacetope.solve.grid import Box, bounds


def room(name, **kw):
    return {"name": name, "w": 3, "l": 3, "h": 3, **kw}


def brief(spaces, site=None, **kw):
    d = {"name": "t", "spaces": spaces, "level_height": 3.0, **kw}
    if site is not None:
        d["site"] = site
    return Brief.from_dict(d)


# an L-shaped two-level plan, off the origin, with a tall shaft: no symmetry of its own
PLAN = {"a": Box(1000, 2000, 0, 4000, 2000, 3000), "b": Box(5000, 2000, 0, 2000, 5000, 3000),
        "c": Box(1000, 4000, 3000, 3000, 3000, 3000), "shaft": Box(4000, 2000, 0, 1000, 1000, 6000)}


def test_there_are_eight_distinct_origin_anchored_placements_that_keep_z_and_sizes():
    sym = orient.symmetries(PLAN)
    assert list(sym) == list(orient.NAMES) and len(sym) == 8
    keys = {tuple(sorted((n, tuple(b.to_dict().values())) for n, b in q.items())) for q in sym.values()}
    assert len(keys) == 8
    for q in sym.values():
        bb = bounds(q.values())
        assert (bb.x, bb.y, bb.z) == (0, 0, 0) and set(q) == set(PLAN)
        assert {n: (b.z, b.h, b.w * b.l) for n, b in q.items()} == {n: (b.z, b.h, b.w * b.l) for n, b in PLAN.items()}
    assert sym["id"]["a"] == Box(0, 0, 0, 4000, 2000, 3000)
    assert (bounds(sym["r90"].values()).w, bounds(sym["r90"].values()).l) == (bounds(sym["id"].values()).l, bounds(sym["id"].values()).w)


def test_contacts_survive_every_symmetry():
    from spacetope.solve.grid import contact_area
    def pairs(q):
        return {frozenset((m, n)) for m in q for n in q if m < n and any(contact_area(q[m], q[n], s) for s in ("+x", "-x", "+y", "-y", "ceiling", "floor"))}
    base = pairs(orient.symmetries(PLAN)["id"])
    assert base and all(pairs(q) == base for q in orient.symmetries(PLAN).values())


def test_fitting_keeps_the_identity_first_and_drops_what_leaves_the_envelope():
    free = brief([room("a")])
    assert list(orient.fitting(free, PLAN)) == list(orient.NAMES)
    tight = brief([room("a")], envelope={"w": 6, "l": 5, "h": 6})   # plan is 6 x 5 after moving to the origin
    assert list(orient.fitting(tight, PLAN)) == ["id", "r180", "mx", "mx_r180"]
    assert orient.fitting(tight, PLAN)["id"] is PLAN
    narrow = brief([room("a")], envelope={"w": 1, "l": 1, "h": 6})
    assert list(orient.fitting(narrow, PLAN)) == ["id"]


def _sunny(strength="should"):
    return brief([room("a", affinities=[{"facade": "sun", "strength": strength}]), room("b")])


def test_best_turns_a_plan_so_the_wish_is_met_and_records_it():
    b = _sunny()
    pl = {"a": Box(0, 0, 0, 3000, 3000, 3000), "b": Box(0, -3000, 0, 3000, 3000, 3000)}   # b covers a's sun side
    q, rec = orient.best(b, pl)
    assert rec["facade_before"] == 0.0 and rec["facade_after"] == 1.0 and rec["symmetry"] != "id"
    assert af.measure(b, q)["items"][0]["met"] is True
    assert set(rec) == {"symmetry", "facade_before", "facade_after"}


def test_the_identity_wins_ties_and_is_returned_untouched():
    b = _sunny()
    pl = {"a": Box(5000, 7000, 0, 3000, 3000, 3000)}                # open on every side: all eight score 1.0
    q, rec = orient.best(b, pl)
    assert q is pl and rec == {"symmetry": "id", "facade_before": 1.0, "facade_after": 1.0}


def test_fewer_hard_misses_beat_a_better_soft_score():
    b = brief([room("a", affinities=[{"facade": "sun", "strength": "must"}, {"facade": "N", "strength": "should", "weight": 3}]),
               room("b")])
    pl = {"a": Box(0, 0, 0, 3000, 3000, 3000), "b": Box(0, -3000, 0, 3000, 3000, 3000)}
    q, rec = orient.best(b, pl)
    assert orient.facade_score(b, q)[0] == 0 and rec["symmetry"] != "id"


def test_wants_facade_only_for_briefs_with_a_facade_wish():
    assert orient.wants_facade(_sunny())
    assert not orient.wants_facade(brief([room("a", affinities=[{"exterior": True}]), room("b")]))
    assert not orient.wants_facade(brief([room("a"), room("b")]))


def test_the_module_states_the_mirroring_condition():
    assert "hinge" in orient.__doc__ and "run direction" in orient.__doc__


def test_the_eight_form_a_group():
    key = lambda q: tuple(sorted((n, tuple(b.to_dict().values())) for n, b in q.items()))
    every = {key(q) for q in orient.symmetries(PLAN).values()}
    for q in orient.symmetries(PLAN).values():
        assert {key(r) for r in orient.symmetries(q).values()} == every
