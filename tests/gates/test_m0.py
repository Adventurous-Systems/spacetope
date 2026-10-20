"""M0 gate: pins, brief round trip, assembly validation, relation signature."""
import json
from importlib.metadata import version

import pytest

from spacetope.brief import Brief, BriefError, Space, load
from spacetope.spacegraph import AssemblyError, AssemblyGraph, SIDES
from spacetope.units import to_m, to_mm

pytestmark = pytest.mark.gate_m0

FIXTURE_NAMES = ("three_rooms", "eight_rooms_corridor", "two_levels_stair")


def test_pins():
    assert version("topologicpy") == "0.9.71"
    assert version("topologic_core") == "8.0.0"


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_brief_roundtrip(fixtures_dir, name):
    b = load(fixtures_dir / f"{name}.yaml")
    assert b.name == name and len(b.spaces) >= 3
    for s in b.spaces:
        for axis in ("w", "l", "h"):
            mm = s.nominal_mm(axis)
            assert isinstance(mm, int) and abs(to_m(mm) - s.nominal(axis)) < 1e-6
            lo, hi = s.band(axis)
            assert isinstance(lo, int) and isinstance(hi, int) and 1 <= lo <= mm <= hi
    again = Brief.from_dict(json.loads(json.dumps(b.to_dict())))
    assert again.to_dict() == b.to_dict()


def test_band_semantics():
    room = Space("r", 4, 3, 3)
    assert room.band("w") == (3600, 4400) and room.band("h") == (3000, 3000)
    corridor = Space("c", 1.8, 12, 3, program="corridor")
    assert corridor.band("w") == (1800, 1800) and corridor.band("l") == (6000, 36000)
    custom = Space("x", 4, 3, 3, tol={"w": (-0.2, 0.0)})
    assert custom.band("w") == (3200, 4000) and custom.band("l") == (2700, 3300)
    with pytest.raises(BriefError):
        Space("bad", 4, 3, 3, program="garage")
    with pytest.raises(BriefError):
        Brief("dup", [Space("a", 1, 1, 1), Space("a", 1, 1, 1)])
    with pytest.raises(BriefError):
        Brief("unknown", [Space("a", 1, 1, 1)], contacts=[("a", "zz")])


def test_assembly_validation(fixtures_dir):
    b = load(fixtures_dir / "three_rooms.yaml")
    ag = AssemblyGraph.from_dict(b, json.loads((fixtures_dir / "assemblies" / "three_rooms.json").read_text()))
    ag.validate()
    assert len(ag.spaces()) == 3 and len(ag.walls()) == 18 and len(ag) == 2
    assert ag.missing_required() == set()
    assert ag.free_walls("kitchen") == [s for s in SIDES if s != "-x"]
    with pytest.raises(AssemblyError):
        ag.add_contact("kitchen", "+x", "bedroom", "+x")  # same normals
    with pytest.raises(AssemblyError):
        ag.add_contact("kitchen", "+x", "garage", "-x")  # unknown space
    with pytest.raises(AssemblyError):
        ag.add_contact("kitchen", "+x", "kitchen", "-x")  # self contact
    with pytest.raises(AssemblyError):
        ag.add_contact("kitchen", "up", "bedroom", "down")  # unknown side
    ag.add_contact("bedroom", "ceiling", "kitchen", "floor")
    assert ag.contacts()[-1].is_vertical or any(c.is_vertical for c in ag.contacts())


def test_signature_is_order_independent_and_relation_sensitive(fixtures_dir):
    b = load(fixtures_dir / "three_rooms.yaml")
    a1 = AssemblyGraph(b)
    a1.add_contact("living", "+x", "kitchen", "-x")
    a1.add_contact("living", "+y", "bedroom", "-y")
    a2 = AssemblyGraph(b)
    a2.add_contact("bedroom", "-y", "living", "+y")  # reversed order and orientation
    a2.add_contact("kitchen", "-x", "living", "+x")
    assert a1.signature() == a2.signature()
    a3 = a1.copy()
    a3.remove_contact("living", "+y", "bedroom", "-y")
    a3.add_contact("living", "-y", "bedroom", "+y")
    assert a3.signature() != a1.signature()
    assert a1.space_adjacency().number_of_edges() == 2


def test_units():
    assert to_mm(4.0) == 4000 and to_mm(1.8) == 1800
    assert to_mm(0.0005) in (0, 1)  # half a millimetre rounds either way; it must not be anything else
    assert to_m(4400) == 4.4
