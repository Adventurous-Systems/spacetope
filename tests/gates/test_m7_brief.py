# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Adventurous Systems

"""M7.1 gate: compact circulation briefs expand deterministically; each validation rule yields its message;
the API rejects invalid briefs with 422 and returns the expanded form for valid ones."""
import copy

import pytest

from spacetope.brief import Brief, load
from spacetope.circulation import BriefInvalid, expand, prepare, validate_compact

pytestmark = pytest.mark.gate_m7


@pytest.fixture()
def three(fixtures_dir):
    return load(fixtures_dir / "three_levels_core.yaml").to_dict()


def messages(d):
    try:
        _, warnings = prepare(Brief.from_dict(d))
        return [w.message for w in warnings]
    except BriefInvalid as e:
        return [p.message for p in e.problems]


def test_three_levels_expands(fixtures_dir):
    e, warnings = prepare(load(fixtures_dir / "three_levels_core.yaml"))
    assert warnings == []
    names = [s.name for s in e.spaces]
    assert len(names) == 15
    assert names[-5:] == ["corridor_0", "corridor_1", "corridor_2", "stair", "lift"]
    stair, lift = e.space("stair"), e.space("lift")
    assert (stair.serves, stair.h, stair.program) == ((0, 2), 9.0, "stair")
    assert (lift.serves, lift.h, lift.program) == ((0, 2), 9.0, "elevator")
    assert [e.space(f"corridor_{k}").wishes["level"] for k in range(3)] == [0, 1, 2]
    for shaft in ("stair", "lift"):
        for k in range(3):
            assert frozenset((shaft, f"corridor_{k}")) in e.required_pairs()
            assert frozenset((shaft, f"corridor_{k}")) in e.marked_door_pairs()
    assert frozenset(("office_c", "meeting")) in e.marked_door_pairs()
    assert Brief.from_dict(e.to_dict()).to_dict() == e.to_dict()
    assert expand(e).to_dict() == e.to_dict()


def test_two_levels_stair_expands_to_twelve(fixtures_dir):
    e, _ = prepare(load(fixtures_dir / "two_levels_stair.yaml"))
    assert len(e.spaces) == 12


def test_rule_envelope_height(three):
    three["envelope"]["h"] = 6
    assert "3 levels × 3 m need 9 m; the envelope is 6 m tall" in messages(three)


def test_rule_span_range(three):
    three["circulation"]["lifts"][0]["serves"] = [0, 3]
    assert "lift serves level 3, the brief has levels 0–2" in messages(three)


def test_rule_stair_coverage(three):
    three["circulation"]["stairs"][0]["serves"] = [0, 1]
    assert "level 2 is not served by any stair" in messages(three)


def test_rule_room_level(three):
    three["spaces"][0]["wishes"]["level"] = 4
    assert "office_a asks for level 4, the brief has levels 0–2" in messages(three)


def test_rule_contact_level(three):
    three["contacts"].append(["office_a", "meeting"])
    assert "office_a (level 0) cannot touch meeting (level 1)" in messages(three)


def test_rule_shaft_contact_level(three):
    three["circulation"]["lifts"][0]["serves"] = [0, 1]
    three["contacts"].append(["lift", "corridor_2"])
    assert "lift does not serve level 2, so it cannot touch corridor_2" in messages(three)


def test_rule_door_height(three):
    three["level_height"] = 2.2
    three["envelope"]["h"] = 9
    assert "room door height 2.1 m does not fit a 2.2 m level with 0.3 m head clearance" in messages(three)


def test_rule_door_width(three):
    three["circulation"]["lifts"][0].update({"w": 1.0, "l": 1.2})
    assert "lift needs 1.3 m of wall for its door (1.1 m door + 2 × 0.1 m jambs); its longest side is 1.2 m" in messages(three)


LEGACY = {  # the pre-M7 way: one stair and lift member per floor
    "name": "legacy", "levels": 2, "level_height": 3,
    "spaces": [{"name": "stair_0", "w": 3, "l": 5, "h": 3, "program": "stair"},
               {"name": "stair_1", "w": 3, "l": 5, "h": 3, "program": "stair"},
               {"name": "lift_0", "w": 2.5, "l": 2.5, "h": 3, "program": "elevator"},
               {"name": "lift_1", "w": 2.5, "l": 2.5, "h": 3, "program": "elevator"},
               {"name": "corridor_0", "w": 1.8, "l": 10, "h": 3, "program": "corridor", "wishes": {"level": 0}},
               {"name": "corridor_1", "w": 1.8, "l": 10, "h": 3, "program": "corridor", "wishes": {"level": 1}}],
    "contacts": [["stair_0", "stair_1"], ["lift_0", "lift_1"], ["corridor_0", "stair_0"], ["corridor_1", "stair_1"]],
}


def test_rule_legacy_shafts():
    msgs = messages(LEGACY)
    assert ("stair_0, stair_1, lift_0, lift_1 look like stairs or lifts split by floor; "
            "declare each once under circulation.stairs or circulation.lifts") in msgs


def test_rule_corridor_coverage(three):
    del three["circulation"]["corridor"]
    three["levels"] = 2
    three["envelope"]["h"] = 6
    three["circulation"]["lifts"][0]["serves"] = [0, 1]
    three["spaces"] = [s for s in three["spaces"] if s["wishes"]["level"] < 2]
    three["contacts"] = [["office_c", "meeting", {"door": True}]]
    assert "levels 0, 1 have no corridor; add circulation.corridor" in messages(three)


def test_rule_name_clash(three):
    three["spaces"].append({"name": "corridor_0", "w": 1.8, "l": 10, "h": 3, "program": "corridor"})
    assert "corridor_0 would be generated by circulation; rename the space" in messages(three)


def test_footprint_is_a_warning_not_an_error(three):
    three["envelope"].update({"w": 8, "l": 8})
    e_msgs = messages(three)
    assert any(m.startswith("level 0 needs about") and m.endswith("the footprint is 64 m²") for m in e_msgs)
    prepare(Brief.from_dict(three))  # does not raise


def test_api_rejects_invalid_and_expands_valid(fixtures_dir):
    from fastapi.testclient import TestClient
    from backend.app.main import app
    c = TestClient(app)
    good = load(fixtures_dir / "three_levels_core.yaml").to_dict()
    res = c.post("/api/brief", json=good)
    assert res.status_code == 200, res.text
    body = res.json()
    assert len(body["brief"]["spaces"]) == 15 and body["brief"]["expanded"] is True and body["warnings"] == []
    bad = copy.deepcopy(good)
    bad["circulation"]["stairs"][0]["serves"] = [0, 1]
    res = c.post("/api/brief", json=bad)
    assert res.status_code == 422
    assert "level 2 is not served by any stair" in [p["message"] for p in res.json()["detail"]["problems"]]


def test_envelope_needs_all_three_dimensions():
    """review 2026-09-13 #2: a partial envelope used to pass validation and crash generation later."""
    from spacetope.brief import BriefError
    with pytest.raises(BriefError, match="envelope needs w, l and h in metres; missing h"):
        Brief.from_dict({"spaces": [{"name": "a", "w": 4, "l": 3, "h": 3}], "envelope": {"w": 20, "l": 14}})


def test_fractional_level_height_stays_consistent_in_millimetres(three):
    """review 2026-09-13 #3: 10 m over 3 floors gave a stair of 9.9999 m against a 9999 mm expectation."""
    from spacetope.levels import level_height_mm
    three["level_height"] = 3.3333
    three["envelope"]["h"] = 10
    e, _ = prepare(Brief.from_dict(three))
    assert level_height_mm(e) == 3333
    assert e.space("stair").nominal_mm("h") == 3 * 3333
    from spacetope.pipeline import generate
    from spacetope.solve.registry import GENERATORS
    options, _, _ = generate(GENERATORS["beam"], e, 0, {"k": 2}, "beam")
    assert options and all(o.ok for o in options), [o.report.to_dict()["checks"]["constraints"] for o in options if not o.ok]
