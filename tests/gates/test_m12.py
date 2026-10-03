"""M12 gate: rectangular-dual generator (design note B)."""
import re

import pytest

import yaml

from spacetope.brief import Brief, load
from spacetope.circulation import prepare
from spacetope.pipeline import run_generator
from spacetope.solve.registry import GENERATORS, GeneratorUnsupported

pytestmark = [pytest.mark.gate_m12, pytest.mark.slow]


@pytest.fixture(scope="module")
def rows(fixtures_dir):
    out = {}
    for fx in ("three_rooms", "eight_rooms_corridor"):
        brief = load(fixtures_dir / f"{fx}.yaml")
        out[fx] = {"dual": run_generator(GENERATORS["dual"], brief, 0, None, "dual"),
                   "beam": run_generator(GENERATORS["beam"], brief, 0, None, "beam")}
    return out


@pytest.mark.parametrize("fx", ("three_rooms", "eight_rooms_corridor"))
def test_dual_options_are_verified_and_one_per_class(rows, fx):
    row = rows[fx]["dual"]
    assert row["options"] >= 1, row
    assert row["verified"] == row["options"], row
    assert row["distinct_topologies"] == row["verified"], row       # one option per topology class
    assert row["adjacency"] == 1.0, row
    assert row["t_gen"] < 60.0, row


def test_dual_variety_on_the_corridor_brief(rows):
    assert rows["eight_rooms_corridor"]["dual"]["distinct_topologies"] >= 5, rows["eight_rooms_corridor"]["dual"]


def test_known_limit_without_a_corridor(rows):
    """Chord triangulation makes every pair on a face touch, so on a brief with no corridor the dual reaches fewer
    classes than the beam (PLAN decision 2026-09-20). This test pins the fact so a fix shows up as a change."""
    assert rows["three_rooms"]["dual"]["distinct_topologies"] <= rows["three_rooms"]["beam"]["distinct_topologies"]


def test_dual_beats_beam_on_topological_variety(rows):
    assert rows["eight_rooms_corridor"]["dual"]["distinct_topologies"] > rows["eight_rooms_corridor"]["beam"]["distinct_topologies"], rows["eight_rooms_corridor"]


def test_dual_on_the_clinic(fixtures_dir):
    row = run_generator(GENERATORS["dual"], load(fixtures_dir / "clinic.yaml"), 0, {"time_limit": 120.0, "max_seeds": 400}, "dual")
    assert row["verified"] >= 1 and row["verified"] == row["options"], row


def test_non_planar_wishes_are_refused():
    names = ["a", "b", "c", "d", "e"]
    spaces = [{"name": n, "w": 4, "l": 4, "h": 3, "program": "room"} for n in names]
    contacts = [[a, b] for i, a in enumerate(names) for b in names[i + 1:]]      # K5
    brief = Brief.from_dict({"name": "k5", "spaces": spaces, "contacts": contacts})
    with pytest.raises(GeneratorUnsupported):
        GENERATORS["dual"](brief, None, 0)


def test_multi_level_is_refused(fixtures_dir):
    with pytest.raises(GeneratorUnsupported):
        GENERATORS["dual"](load(fixtures_dir / "two_levels_stair.yaml"), None, 0)


def test_it_says_why_when_it_cannot_tile(fixtures_dir):
    """A brief whose rooms chain to each other has no rectangular plan inside a ±10 % tolerance. Rather than hand
    the architect an empty gallery, the generator names the wall it hit and what would clear it (PLAN §6.0,
    answered 2026-10-03)."""
    for fx, least in (("house_ground", 20), ("gallery_rich", 20)):
        brief, _ = prepare(load(fixtures_dir / f"{fx}.yaml"))
        with pytest.raises(GeneratorUnsupported) as e:
            GENERATORS["dual"](brief, {"k": 4, "time_limit": 45.0}, 0)
        msg = str(e.value)
        assert "cannot tile" in msg and "tolerance" in msg
        pct = int(re.search(r"±(\d+) %", msg).group(1))
        assert pct >= least, msg                       # it asks for real extra room, not a rounding
        assert "beam" in msg and "cpsat" in msg        # and points at the engines that can do it


def test_the_advice_it_gives_is_true(fixtures_dir):
    """Widen the tolerance as the message asks and the same brief does produce plans. Without this the message
    could be a comfortable fiction."""
    raw = yaml.safe_load((fixtures_dir / "house_ground.yaml").read_text())
    wide = Brief.from_dict({**raw, "name": "house_wide", "spaces": [{**s, "tol": 0.5} for s in raw["spaces"]]})
    row = run_generator(GENERATORS["dual"], wide, 0, {"k": 4, "time_limit": 90.0}, "dual")
    assert row["verified"] >= 1 and row["verified"] == row["options"], row
    assert row["adjacency"] == 1.0, row


def test_a_brief_it_can_do_is_unaffected(fixtures_dir):
    brief, _ = prepare(load(fixtures_dir / "eight_rooms_corridor.yaml"))
    assert len(GENERATORS["dual"](brief, {"k": 4, "time_limit": 45.0}, 0)) >= 4
