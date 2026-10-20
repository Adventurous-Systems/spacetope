"""M8 gate: how many floors? Arithmetic bounds, then verified options for each candidate count.
Plan: docs/2026-09-13_M7_vertical_circulation_plan.md §7."""
import pytest

from spacetope.brief import Brief, load
from spacetope.floors import areas, bounds, brief_for_levels, search
from spacetope.solve.registry import GENERATORS

pytestmark = [pytest.mark.gate_m8, pytest.mark.slow]


@pytest.fixture(scope="module")
def base(fixtures_dir):
    return load(fixtures_dir / "three_levels_core.yaml")


def with_envelope(brief, w, l, h):
    return Brief.from_dict({**brief.to_dict(), "envelope": {"w": w, "l": l, "h": h}})


def test_bounds_without_an_envelope_footprint(fixtures_dir):
    b = bounds(load(fixtures_dir / "three_rooms.yaml"))
    assert b.feasible and b.min_levels == 1
    assert b.candidates(3) == [1, 2, 3]
    assert "no envelope footprint" in b.reason


def test_areas_split_rooms_corridor_and_shafts(base):
    a = areas(base)
    assert round(a.rooms) == 113 and round(a.corridor) == 18 and round(a.shafts) == 21
    assert a.per_level(1) > a.per_level(2) > a.per_level(3)   # rooms spread, corridor and shafts repeat
    assert a.room_frontage == 28.5 and a.shaft_frontage == 5.5   # corridor wall the rooms and shafts need
    assert a.frontage_per_level(1) > a.frontage_per_level(3)


def test_bounds_report_corridor_frontage_without_moving_the_bound(base):
    """Frontage is reported, not used to move the bound: a first attempt at flagging tight counts failed to
    predict the measured failures, so the honest signal is the per-candidate reason after generating."""
    b = bounds(with_envelope(base, 12, 10, 9))
    assert b.frontage_supply > 0 and b.tight == []
    assert "tight" not in b.reason


def test_bounds_force_more_floors(base):
    """Calibrated against measurement: at 12 x 10 m only three floors build, and the bound says three."""
    b = bounds(with_envelope(base, 12, 10, 9))
    assert (b.min_levels, b.max_levels, b.feasible) == (3, 3, True)
    assert "77 m² each, within the 78 m² usable of a 120 m² footprint" in b.reason


def test_bounds_infeasible_because_the_envelope_is_too_low(base):
    b = bounds(with_envelope(base, 12, 10, 3))
    assert not b.feasible and b.candidates() == []
    assert b.reason == "3 floors × 3 m need 9 m; the envelope is 3 m tall"


def test_bounds_infeasible_because_the_footprint_is_too_small(base):
    b = bounds(with_envelope(base, 6, 5, 30))
    assert not b.feasible and "even 8 floors need about" in b.reason


def test_brief_for_levels_remaps_what_names_a_floor(base):
    """Level wishes and shaft spans go, because they name a floor that may not exist. Corridor contacts are
    remapped onto a corridor that does exist, so every room still has one to open onto, and rooms that must
    touch each other are sent to the same corridor."""
    v = brief_for_levels(base, 2)
    assert v.levels == 2
    assert [s.name for s in v.spaces if "level" in s.wishes] == []
    assert all(item.get("serves") is None for key in ("stairs", "lifts") for item in v.circulation.get(key) or [])
    named = [c for c in v.contacts if c[0].startswith("corridor_") or c[1].startswith("corridor_")]
    assert named, "rooms must keep a corridor to open onto"
    assert all(int(name.split("_")[1]) < 2 for c in named for name in c if name.startswith("corridor_"))
    assert ("office_c", "meeting") in v.contacts or ("meeting", "office_c") in v.contacts   # room pair kept
    linked = {c[0] if c[1].startswith("corridor_") else c[1]: c[0] if c[0].startswith("corridor_") else c[1]
              for c in named}
    assert linked.get("office_c") == linked.get("meeting"), "rooms that must touch share a corridor, so one floor"


def test_search_verifies_the_smallest_count_the_bound_allows(base):
    """At 12 x 10 m the bound and reality agree on three floors, and the search verifies it."""
    brief = with_envelope(base, 12, 10, 9)
    b, results = search(brief, GENERATORS["beam"], seed=0, keep=2, most=2)
    assert [r.levels for r in results] == [3] and b.min_levels == 3
    assert sum(r.t_gen + r.t_build for r in results) < 60.0
    for o in results[0].verified:
        assert len({box.z for box in o.placement.values()}) == 3 and o.scores["vertical"] == 1.0
    assert results[0].verified


def test_search_explains_a_candidate_that_produces_nothing(base):
    """At 20 x 8 m the area bound allows two floors, but 8 m is too shallow for rooms on both sides of the corridor,
    so only three floors build; the two-floor candidate must say why. (Until 2026-09-20 this used 14 x 12 m; the M15
    beam now fits two floors there, so that envelope no longer leaves a candidate empty.)"""
    brief = with_envelope(base, 20, 8, 9)
    b, results = search(brief, GENERATORS["beam"], seed=0, keep=2, most=2)
    assert [r.levels for r in results] == [2, 3] and b.min_levels == 2
    assert any(r.verified for r in results)
    empty = [r for r in results if not r.verified]
    assert empty and all(r.reason.startswith(f"{r.levels} floors:") for r in empty)
    assert all("none verified" in r.reason or "no layout" in r.reason for r in empty)


def test_search_verifies_every_candidate_when_the_envelope_is_roomy(base):
    brief = with_envelope(base, 22, 16, 9)
    b, results = search(brief, GENERATORS["beam"], seed=0, keep=2, most=2)
    assert [r.levels for r in results] == [1, 2] and b.min_levels == 1
    for r in results:
        assert r.verified, (r.levels, r.reason)
        for o in r.verified:
            assert len({box.z for box in o.placement.values()}) == r.levels


def test_bounds_use_integer_millimetres_for_the_height_limit(base):
    """review 2026-09-13 #9: 8.1 // 2.7 is 2.0 in floats; in millimetres it is 3."""
    b = bounds(Brief.from_dict({**base.to_dict(), "level_height": 2.7, "envelope": {"w": 22, "l": 16, "h": 8.1}}))
    assert b.max_levels == 3


def test_brief_for_levels_does_not_mutate_the_caller(base):
    before = base.to_dict()
    brief_for_levels(base, 2)
    assert base.to_dict() == before
