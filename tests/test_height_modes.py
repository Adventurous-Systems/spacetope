# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Adventurous Systems

"""M18: a declared height is normally a request the level height may override, sometimes a minimum to
clear, and never below `MIN_HEIGHT_M`. A space whose minimum spans more than one level is named as
unplaceable rather than built one storey tall."""
import pytest

from spacetope.brief import MIN_HEIGHT_MM, Brief, BriefError, Space
from spacetope.circulation import validate_compact
from spacetope.preverify import check_bands
from spacetope.solve.grid import Box

pytestmark = pytest.mark.gate_m18


def one(h=3.0, mode="request", program="room", **kw) -> Brief:
    return Brief("t", [Space("a", 4.0, 3.0, h, program=program, height_mode=mode, **kw)], level_height=3.0)


def placed(h_mm: int, w_mm=4000, l_mm=3000):
    return {"a": Box(0, 0, 0, w_mm, l_mm, h_mm)}


# ---------------------------------------------------------------- the declared minimum height

def test_default_mode_is_request():
    assert Space("a", 4.0, 3.0, 3.0).height_mode == "request"
    assert not Space("a", 4.0, 3.0, 3.0).height_is_minimum


def test_height_below_the_minimum_is_rejected_when_the_brief_loads():
    with pytest.raises(BriefError, match=r"below the minimum of 2\.2 m"):
        Space("cupboard", 2.0, 2.0, 2.1)


def test_the_minimum_itself_is_allowed():
    assert Space("low", 2.0, 2.0, 2.2).nominal_mm("h") == 2200


def test_an_unknown_height_mode_is_rejected():
    with pytest.raises(BriefError, match="height_mode must be one of"):
        Space("a", 4.0, 3.0, 3.0, height_mode="maximum")


# ---------------------------------------------------------------- a request adapts to the level height

def test_the_level_height_satisfies_a_requested_height_outside_its_band():
    """The m7 case: rooms ask for 3.0 m with a zero-width band, the brief sets a 3.3333 m level, and the
    engine builds every room at the level height. That is the level overriding a request, not a fault."""
    brief = Brief("t", [Space("a", 4.0, 3.0, 3.0)], level_height=3.3333)
    ok, detail = check_bands(brief, placed(3333))
    assert ok, detail


def test_a_requested_height_that_is_neither_the_level_height_nor_in_band_fails():
    ok, detail = check_bands(one(), placed(2800))
    assert not ok
    assert "neither the level height" in detail


def test_a_requested_height_inside_its_band_passes_without_being_the_level_height():
    brief = Brief("t", [Space("a", 4.0, 3.0, 3.0, tol={"h": (-0.1, 0.1)})], level_height=4.0)
    ok, detail = check_bands(brief, placed(2800))
    assert ok, detail


# ---------------------------------------------------------------- a minimum must be cleared

def test_a_minimum_height_is_cleared_from_above():
    ok, detail = check_bands(one(h=3.0, mode="minimum"), placed(4000))
    assert ok, detail


def test_a_minimum_height_is_not_met_from_below():
    ok, detail = check_bands(one(h=4.0, mode="minimum"), placed(3000))
    assert not ok
    assert "does not clear the required minimum 4000 mm" in detail


def test_a_minimum_height_exactly_met_passes():
    assert check_bands(one(h=4.0, mode="minimum"), placed(4000))[0]


# ---------------------------------------------------------------- the floor applies to every mode

@pytest.mark.parametrize("mode", ("request", "minimum"))
def test_nothing_is_ever_built_below_the_minimum_height(mode):
    brief = Brief("t", [Space("a", 4.0, 3.0, 2.2, height_mode=mode)], level_height=2.1)
    ok, detail = check_bands(brief, placed(2100))
    assert not ok, "a 2.1 m level height must not be allowed to build a 2.1 m space"
    assert f"below the minimum {MIN_HEIGHT_MM} mm" in detail


# ---------------------------------------------------------------- spanning levels

def test_a_requested_height_never_spans_levels():
    assert Space("a", 4.0, 3.0, 6.0).levels_spanned(3000) == 1


@pytest.mark.parametrize("h,levels", [(3.0, 1), (3.1, 2), (6.0, 2), (6.1, 3), (9.0, 3)])
def test_a_minimum_height_spans_as_many_levels_as_it_needs(h, levels):
    assert Space("hall", 10.0, 10.0, h, height_mode="minimum").levels_spanned(3000) == levels


def test_a_space_taller_than_one_level_is_named_as_unplaceable():
    brief = Brief("t", [Space("auditorium", 12.0, 18.0, 7.0, height_mode="minimum")],
                  levels=3, level_height=3.0)
    codes = {p.code: p.message for p in validate_compact(brief)}
    assert "tall_space_spans_levels" in codes
    assert "spans 3 levels" in codes["tall_space_spans_levels"]


def test_a_tall_request_raises_no_problem():
    brief = Brief("t", [Space("office", 4.0, 3.0, 7.0)], levels=3, level_height=3.0)
    assert "tall_space_spans_levels" not in {p.code for p in validate_compact(brief)}


# ---------------------------------------------------------------- the field survives the brief format

def test_height_mode_round_trips_through_the_brief_format():
    d = Brief("t", [Space("hall", 12.0, 18.0, 6.0, height_mode="minimum"),
                    Space("office", 4.0, 3.0, 3.0)], level_height=3.0).to_dict()
    assert d["spaces"][0]["height_mode"] == "minimum"
    assert "height_mode" not in d["spaces"][1], "the default stays out of the written brief"
    back = Brief.from_dict(d)
    assert back.space("hall").height_is_minimum
    assert not back.space("office").height_is_minimum
