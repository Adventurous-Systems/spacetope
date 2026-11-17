# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Adventurous Systems

"""M18 gate: the verifier tests the brief, not the placement against itself.

Two new checks (the eighth and ninth): `required_contacts` takes its expectation from the brief's required
pairs, so a fault that slides a room off a required contact no longer removes the intent with it (H1b);
`bands` rejects any space outside its tolerance band. One test per pilot fault, asserting that the *right*
check fails, and one control asserting that a 1 mm gap on an incidental contact still passes everything.
"""
import pytest

from spacetope.brief import load
from spacetope.circulation import prepare
from spacetope.doors import required_overlap_mm
from spacetope.placement import overlaps
from spacetope.preverify import SIDES, preverify
from spacetope.solve.grid import Box, contact_area
from spacetope.solve.registry import GENERATORS
from spacetope.verify import CHECKS, verify

pytestmark = [pytest.mark.gate_m18, pytest.mark.slow]

HS = ("+x", "-x", "+y", "-y")
DIR = {"+x": (1, 0), "-x": (-1, 0), "+y": (0, 1), "-y": (0, -1)}


def shift(b: Box, dx=0, dy=0, dz=0) -> Box:
    return Box(b.x + dx, b.y + dy, b.z + dz, b.w, b.l, b.h)


def touching_pairs(brief, pl):
    """(a, b, side, required) for every horizontally touching pair, in deterministic order."""
    req = brief.required_pairs()
    names = sorted(pl)
    out = []
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            for s in HS:
                if contact_area(pl[a], pl[b], s) > 0:
                    out.append((a, b, s, frozenset((a, b)) in req))
    return out


def gap_fault(brief, pl, want_required: bool):
    """Move a room 1 mm off a (required | incidental) contact, keeping the placement overlap-free."""
    for a, b, s, req in touching_pairs(brief, pl):
        if req is not want_required:
            continue
        if brief.space(b).program == "room":
            mover, (dx, dy) = b, DIR[s]
        elif brief.space(a).program == "room":
            mover, (dx, dy) = a, (-DIR[s][0], -DIR[s][1])
        else:
            continue
        new = dict(pl)
        new[mover] = shift(pl[mover], dx, dy)
        if not overlaps(new):
            return new, mover, frozenset((a, b))
    return None, None, None


@pytest.fixture(scope="module")
def corridor_case(fixtures_dir):
    brief, _ = prepare(load(fixtures_dir / "eight_rooms_corridor.yaml"))
    pls = GENERATORS["beam"](brief, None, 0)
    pl = next(p for p in pls if preverify(brief, p)[0])
    return brief, pl


@pytest.fixture(scope="module")
def stair_case(fixtures_dir):
    brief, _ = prepare(load(fixtures_dir / "two_levels_stair.yaml"))
    pls = GENERATORS["beam"](brief, None, 0)
    pl = next(p for p in pls if preverify(brief, p)[0])
    return brief, pl


def test_report_has_nine_checks(corridor_case):
    brief, pl = corridor_case
    assert len(CHECKS) == 9 and CHECKS[-2:] == ("required_contacts", "bands")
    rep = verify(brief, pl)
    assert rep.ok, {k: d for k, (p, d) in rep.checks.items() if not p}
    assert set(rep.checks) == set(CHECKS)


def test_gap_off_required_contact_fails_required_contacts_not_contacts(corridor_case):
    brief, pl = corridor_case
    new, mover, pair = gap_fault(brief, pl, want_required=True)
    assert new is not None, "no movable required contact found"
    ok, checks = preverify(brief, new)
    assert not checks["required_contacts"][0], checks["required_contacts"][1]
    rep = verify(brief, new)
    assert not rep.ok
    assert not rep.checks["required_contacts"][0]
    # H1a vs H1b: the placement-derived intent no longer carries the lost pair, so `contacts` passes
    assert rep.checks["contacts"][0], rep.checks["contacts"][1]
    assert "-".join(sorted(pair)) in rep.checks["required_contacts"][1]


def test_gap_off_incidental_contact_still_passes(corridor_case):
    brief, pl = corridor_case
    found = False
    for a, b, s, req in touching_pairs(brief, pl):
        if req or brief.space(b).program != "room" or brief.space(a).program != "room":
            continue
        new = dict(pl)
        new[b] = shift(pl[b], *DIR[s])
        if overlaps(new) or not preverify(brief, new)[0]:
            continue  # the slide broke something else (a required contact, a door run); try another pair
        rep = verify(brief, new)
        assert rep.ok, {k: d for k, (p, d) in rep.checks.items() if not p}
        found = True
        break
    assert found, "no incidental room-room contact to open"


def test_room_shrunk_fails_bands(corridor_case):
    brief, pl = corridor_case
    name = next(n for n in sorted(pl) if brief.space(n).program == "room")
    b = pl[name]
    new = dict(pl)
    new[name] = Box(b.x, b.y, b.z, int(b.w * 0.75), b.l, b.h)
    ok, checks = preverify(brief, new)
    assert not checks["bands"][0] and name in checks["bands"][1]
    rep = verify(brief, new)
    assert not rep.ok and not rep.checks["bands"][0]


def test_room_grown_out_of_band_fails_bands(corridor_case):
    brief, pl = corridor_case
    for name in sorted(pl):
        if brief.space(name).program != "room":
            continue
        b = pl[name]
        for nb in (Box(b.x, b.y, b.z, int(b.w * 1.3), b.l, b.h),
                   Box(b.x - int(b.w * 0.3), b.y, b.z, b.w + int(b.w * 0.3), b.l, b.h),
                   Box(b.x, b.y, b.z, b.w, int(b.l * 1.3), b.h),
                   Box(b.x, b.y - int(b.l * 0.3), b.z, b.w, b.l + int(b.l * 0.3), b.h)):
            new = dict(pl)
            new[name] = nb
            if not overlaps(new):
                _, checks = preverify(brief, new)
                assert not checks["bands"][0], "a room grown 30 % must leave its band"
                assert checks["no_overlaps"][0]
                return
    pytest.fail("no room with free space to grow into")


def test_overlap_rejected(corridor_case):
    brief, pl = corridor_case
    a, b, s, _ = next(t for t in touching_pairs(brief, pl)
                      if brief.space(t[1]).program == "room" and not brief.space(t[1]).is_vertical)
    dx, dy = DIR[s]
    new = dict(pl)
    new[b] = shift(pl[b], -dx * 50, -dy * 50)
    ok, checks = preverify(brief, new)
    assert not checks["no_overlaps"][0]
    assert not verify(brief, new).ok


def test_shaft_half_height_fails_constraints(stair_case):
    brief, pl = stair_case
    name = next(n for n in sorted(pl) if brief.space(n).is_shaft)
    b = pl[name]
    new = dict(pl)
    new[name] = Box(b.x, b.y, b.z, b.w, b.l, b.h // 2)
    _, checks = preverify(brief, new)
    assert not checks["constraints"][0] and name in checks["constraints"][1]


def test_out_of_envelope_fails_constraints(stair_case):
    brief, pl = stair_case
    dx = int(brief.envelope["w"] * 1000)
    new = {n: shift(b, dx=dx) for n, b in pl.items()}
    _, checks = preverify(brief, new)
    assert not checks["constraints"][0]


def test_room_slid_to_narrow_door_run_fails_doors(stair_case):
    # needs a brief with a `circulation:` section: without one the doors check is vacuous by design
    brief, pl = stair_case
    for a, b, s, req in touching_pairs(brief, pl):
        room, corr = (a, b) if brief.space(a).program == "room" else (b, a)
        if brief.space(room).program != "room" or brief.space(corr).program != "corridor":
            continue
        rb, cb = pl[room], pl[corr]
        need = required_overlap_mm(brief, room, corr)   # door width + 2 jambs for this pair
        axis = "y" if s in ("+x", "-x") else "x"   # slide along the shared wall
        lo = max(getattr(rb, axis), getattr(cb, axis))
        hi = min(getattr(rb, axis + "1"), getattr(cb, axis + "1"))
        run = hi - lo
        slide = run - (need // 2)                   # leave half a door's worth of shared run
        for sign in (1, -1):
            new = dict(pl)
            new[room] = shift(rb, **{"d" + axis: sign * slide})
            left = min(getattr(new[room], axis + "1"), getattr(cb, axis + "1")) - \
                max(getattr(new[room], axis), getattr(cb, axis))
            if overlaps(new) or left <= 0 or left >= need:
                continue
            if not any(contact_area(new[room], pl[o], sd) > 0 for o in pl if o != room for sd in SIDES
                       if frozenset((room, o)) in brief.required_pairs()) and brief.required_pairs():
                pass  # fine: the door rule, not required_contacts, is what this fault must trip
            _, checks = preverify(brief, new)
            if checks["required_contacts"][0]:      # isolate the door failure from a lost required contact
                assert not checks["doors"][0], f"{room} with a {left} mm run (< {need}) must fail doors"
                return
    pytest.skip("no slide found that narrows a door run without losing the required contact")
