"""Every brief in fixtures/ loads, validates and expands; the UI lists them all through /api/fixtures."""
from pathlib import Path

import pytest

from spacetope.brief import corridor_segments, load
from spacetope.circulation import prepare

FIXTURES = sorted(Path(__file__).resolve().parent.parent.joinpath("fixtures").glob("*.yaml"))


@pytest.mark.parametrize("path", FIXTURES, ids=[p.stem for p in FIXTURES])
def test_fixture_validates(path):
    brief = load(path)
    assert brief.name == path.stem, "fixture name must match its file name (the API loads by name)"
    expanded, warnings = prepare(brief)
    assert expanded.spaces
    # every room can get a door: it has a required contact with a corridor, or the brief has no corridor at all
    corridors = {s.name for s in expanded.spaces if s.program == "corridor"}
    if corridors and corridor_segments(brief) == 1:      # a chained spine has no one name to point at (PLAN M15b)
        for s in expanded.spaces:
            if s.program == "room":
                partners = {b if a == s.name else a for a, b in expanded.contacts if s.name in (a, b)}
                assert partners & corridors, f"{s.name} has no required contact with a corridor"
    assert not warnings, [w.message for w in warnings]
