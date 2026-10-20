"""M16 gate: the sequence-pair encoding (design note §D), and the measured reason its generator is not registered.

What is delivered and tested here: the encoding, an O(n log n) packer, and an annealer that solves small
corridor briefs. What is not: a generator for the briefs M16 was meant for. The cause is measured, not guessed —
packing pulls every space toward the origin, so a room keeps the corridor it must touch only when the corridor is
what stops it. On a brief where one long thin space must serve ten rooms, repacking a working layout pulls spaces
off their walls, and each one that moves loses a contact. See PLAN §5, 2026-09-21.
"""
import pytest

from spacetope.brief import load
from spacetope.circulation import prepare
from spacetope.doors import required_overlap_mm
from spacetope.levels import envelope_mm, level_height_mm
from spacetope.preverify import preverify
from spacetope.score import cheap_scores
from spacetope.solve.beam import BeamParams, beam_search
from spacetope.solve.grid import intersects
from spacetope.solve.registry import GENERATORS
from spacetope.solve.seqpair import (CyclicRelations, apart, boxes, from_placement, pack, seqpair_generator)

pytestmark = [pytest.mark.gate_m16, pytest.mark.slow]
FIXTURES = ("three_rooms", "eight_rooms_corridor", "clinic", "hotel_floor", "house_ground", "gallery_rich")


def _warm(brief, seed=0, width=8):
    return beam_search(brief, BeamParams(k=1, beam_width=width), seed,
                       envelope=envelope_mm(brief), height=level_height_mm(brief))


@pytest.mark.parametrize("fx", FIXTURES)
def test_relations_of_a_real_layout_can_always_be_ordered(fixtures_dir, fx):
    brief, _ = prepare(load(fixtures_dir / f"{fx}.yaml"))
    for width in (8, 16):
        for seed in (0, 1, 2):
            warm = _warm(brief, seed, width)
            if not warm:
                continue
            try:
                plus, minus = from_placement(warm[0])
            except CyclicRelations as e:            # only the forced relations are used, so this must not happen
                pytest.fail(f"{fx} w{width} s{seed}: {e}")
            assert sorted(plus) == sorted(minus) == sorted(warm[0])


def test_packing_never_overlaps(fixtures_dir):
    """Whatever the orderings say, the packed layout is a legal set of boxes."""
    import random
    brief, _ = prepare(load(fixtures_dir / "clinic.yaml"))
    names = [s.name for s in brief.spaces]
    size = {s.name: (s.nominal_mm("w"), s.nominal_mm("l")) for s in brief.spaces}
    h = {s.name: s.nominal_mm("h") for s in brief.spaces}
    rng = random.Random(0)
    for _ in range(25):
        plus, minus = list(names), list(names)
        rng.shuffle(plus); rng.shuffle(minus)
        pl = boxes((plus, minus), size, 0, h)
        assert len(pl) == len(names)
        vals = list(pl.values())
        assert not any(intersects(a, b) for i, a in enumerate(vals) for b in vals[i + 1:])
        assert all(b.x >= 0 and b.y >= 0 for b in vals)


def test_a_beam_layout_survives_a_round_trip(fixtures_dir):
    """The encoding can hold a real plan: on this brief every space comes back where it was."""
    brief, _ = prepare(load(fixtures_dir / "eight_rooms_corridor.yaml"))
    pl0 = _warm(brief)[0]
    size = {n: (b.w, b.l) for n, b in pl0.items()}
    h = {n: b.h for n, b in pl0.items()}
    back = boxes(from_placement(pl0), size, 0, h)
    assert all((back[n].x, back[n].y) == (pl0[n].x, pl0[n].y) for n in pl0)
    required = [(a, b, required_overlap_mm(brief, a, b, 900)) for a, b in brief.contacts]
    assert sum(apart(back[a], back[b], n) for a, b, n in required) == 0


def test_the_annealer_solves_a_very_small_brief(fixtures_dir):
    """What it does deliver: legal options with every required contact and exact sizes, on a brief of three rooms."""
    brief, _ = prepare(load(fixtures_dir / "three_rooms.yaml"))
    for seed in (0, 1, 2):
        pls = seqpair_generator(brief, {"k": 4, "time_limit": 20.0}, seed)
        assert len(pls) >= 2 and all(preverify(brief, pl)[0] for pl in pls)
        for pl in pls:
            sc = cheap_scores(brief, pl)
            assert sc["adjacency"] == 1.0 and sc["deviation"] == 0.0, (seed, sc)


def test_it_is_already_behind_the_beam_at_nine_spaces(fixtures_dir):
    """The gate's second line was "deviation ≤ beam" warm-started on this brief. Measured 2026-09-21 it is behind
    on both counts: the beam makes every required contact on every seed, the annealer only on some, and its sizes
    drift further. These assertions pin the gap; if one starts failing, reopen M16 rather than relax it."""
    brief, _ = prepare(load(fixtures_dir / "eight_rooms_corridor.yaml"))
    mine = [pl for pl in seqpair_generator(brief, {"k": 4, "time_limit": 30.0}, 0) if preverify(brief, pl)[0]]
    beam = [pl for pl in GENERATORS["beam"](brief, None, 0) if preverify(brief, pl)[0]]
    assert mine and beam
    assert max(cheap_scores(brief, pl)["adjacency"] for pl in beam) == 1.0
    assert max(cheap_scores(brief, pl)["adjacency"] for pl in mine) < 1.0
    assert min(cheap_scores(brief, pl)["deviation"] for pl in mine) > min(cheap_scores(brief, pl)["deviation"] for pl in beam)


def test_it_gives_nothing_on_the_briefs_it_was_meant_for(fixtures_dir):
    """The gate's first line, measured: on a 60-room level the beam verifies 8 of 8 in 5 s and this returns
    nothing in 60 s. Checked here on a smaller brief so the gate stays quick."""
    brief, _ = prepare(load(fixtures_dir / "clinic.yaml"))
    assert seqpair_generator(brief, {"k": 2, "time_limit": 20.0}, 0) == []


@pytest.mark.parametrize("fx,least", [("clinic", 1), ("house_ground", 1)])
def test_why_it_stops_there(fixtures_dir, fx, least):
    """The measured limit. Packing moves spaces off the walls they were sharing, and a contact goes with each.
    If a future decoder fixes this, this test fails and M16 should be reopened."""
    brief, _ = prepare(load(fixtures_dir / f"{fx}.yaml"))
    pl0 = _warm(brief)[0]
    size = {n: (b.w, b.l) for n, b in pl0.items()}
    h = {n: b.h for n, b in pl0.items()}
    back = boxes(from_placement(pl0), size, 0, h)
    required = [(a, b, required_overlap_mm(brief, a, b, 900)) for a, b in brief.contacts]
    assert sum(apart(pl0[a], pl0[b], n) for a, b, n in required) == 0        # the beam's layout makes them all
    moved = sum(1 for n in back if (back[n].x, back[n].y) != (pl0[n].x, pl0[n].y))
    assert moved >= least
    assert sum(apart(back[a], back[b], n) for a, b, n in required) > 0       # and repacking loses some


def test_the_generator_is_not_registered():
    """Deliberate (PLAN §5, 2026-09-21): it returns nothing on briefs past about ten spaces on a corridor, and
    the beam solves those in seconds since M15a. Registering it would hand the architect an engine that silently
    produces no options. Reopen M16 with a different decoder, not by wiring this one up."""
    assert "seqpair" not in GENERATORS
