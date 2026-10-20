"""Sequence-pair search with simulated annealing (PLAN M16, design note §D).

An arrangement is written as two orderings of the spaces. A space before another in *both* orderings is to its
left; before in the first and after in the second is above it. Every pair therefore gets exactly one of left,
right, above, below without a coordinate being chosen, which is the same relational vocabulary the CP-SAT model
speaks and the one `redim` preserves.

Coordinates come from the orderings by packing: each space is pushed as far left and as far down as its
predecessors allow. That is a longest path in two implied graphs, computed here in O(n log n) per direction with
a max-Fenwick tree over the second ordering (Tang & Wong), so a candidate is scored in well under a millisecond
and the annealer can afford thousands of them. Only the survivors are sized exactly, by `redim`, and only those
are handed to the kernel.

Pure Python: no topologicpy, and ortools only through `redim` at the end.
"""
from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass

from ..brief import Brief, Space
from ..doors import required_overlap_mm
from ..levels import envelope_mm, level_height_mm
from ..preverify import preverify
from .grid import Box, bounds, contact_area, intersects, overlap_len, touches

HSIDES = ("+x", "-x", "+y", "-y")


class CyclicRelations(ValueError):
    """A layout whose pairwise relations cannot be put in one order: not a sequence pair."""


@dataclass
class SeqPairParams:
    k: int = 8                    # options wanted
    restarts: int = 6
    iterations: int = 3000        # annealing steps per restart
    time_limit: float = 60.0
    door_mm: int = 900
    cooling: float = 0.995
    accept0: float = 0.35         # share of worsening moves accepted at the start, sets the temperature
    warm_start: bool = True       # begin one restart from the beam's best layout
    w_contact: float = 60.0       # per metre a required pair is short of sharing its wall
    w_access: float = 40.0        # per metre a room is short of reaching a corridor
    w_envelope: float = 250.0     # per metre the layout overruns the envelope (that makes it illegal)
    w_perimeter: float = 4.0      # per metre of bounding-box half-perimeter
    w_dead: float = 0.5           # per m2 of bounding box no space covers


# ----------------------------------------------------------------------------- packing

class _MaxBit:
    """Fenwick tree over `n` slots answering "largest value stored below this slot"."""

    __slots__ = ("n", "t")

    def __init__(self, n: int) -> None:
        self.n = n
        self.t = [0] * (n + 1)

    def update(self, i: int, v: int) -> None:
        i += 1
        while i <= self.n:
            if self.t[i] < v:
                self.t[i] = v
            i += i & -i

    def below(self, i: int) -> int:
        """Max over slots [0, i)."""
        r = 0
        while i > 0:
            if self.t[i] > r:
                r = self.t[i]
            i -= i & -i
        return r


def pack(plus: list[str], minus: list[str], size: dict[str, tuple[int, int]]) -> dict[str, tuple[int, int]]:
    """Lower-left corner of every space, packed against its predecessors. `size` is (width, length) in mm."""
    pos = {v: i for i, v in enumerate(minus)}
    n = len(plus)
    xs: dict[str, int] = {}
    bit = _MaxBit(n)
    for v in plus:                       # left of v: earlier in both orderings
        p = pos[v]
        x = bit.below(p)
        xs[v] = x
        bit.update(p, x + size[v][0])
    ys: dict[str, int] = {}
    bit = _MaxBit(n)
    for v in reversed(plus):             # below v: later in the first ordering, earlier in the second
        p = pos[v]
        y = bit.below(p)
        ys[v] = y
        bit.update(p, y + size[v][1])
    return {v: (xs[v], ys[v]) for v in plus}


def boxes(order: tuple[list[str], list[str]], size: dict[str, tuple[int, int]], z: int, h: dict[str, int]) -> dict[str, Box]:
    xy = pack(order[0], order[1], size)
    return {v: Box(xy[v][0], xy[v][1], z, size[v][0], size[v][1], h[v]) for v in order[0]}


# ----------------------------------------------------------------------------- reading a sequence pair off a layout

def from_placement(placement: dict[str, Box]) -> tuple[list[str], list[str]]:
    """The orderings a laid-out plan implies, so the beam and the exact engine can warm-start the annealer.

    Only the relations the geometry *forces* are used: two spaces apart along x whose y ranges overlap are left and
    right of each other, and vice versa. A pair apart on both axes is free, and saying anything about it can make
    the relations unorderable (measured 2026-09-21), so it is left to the ordering to settle."""
    names = sorted(placement)
    after_p: dict[str, set[str]] = {n: set() for n in names}
    after_n: dict[str, set[str]] = {n: set() for n in names}
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            A, B = placement[a], placement[b]
            ov_x = overlap_len(A.interval("x"), B.interval("x"))
            ov_y = overlap_len(A.interval("y"), B.interval("y"))
            if ov_y > 0 and A.x1 <= B.x:                       # a left of b
                after_p[a].add(b); after_n[a].add(b)
            elif ov_y > 0 and B.x1 <= A.x:
                after_p[b].add(a); after_n[b].add(a)
            elif ov_x > 0 and A.y1 <= B.y:                     # a below b: b comes first in the first ordering
                after_p[b].add(a); after_n[a].add(b)
            elif ov_x > 0 and B.y1 <= A.y:
                after_p[a].add(b); after_n[b].add(a)
    return _topo(names, after_p), _topo(names, after_n)


def _topo(names: list[str], after: dict[str, set[str]]) -> list[str]:
    indeg = {n: 0 for n in names}
    for n in names:
        for m in after[n]:
            indeg[m] += 1
    ready = sorted(n for n in names if not indeg[n])
    out: list[str] = []
    while ready:
        n = ready.pop(0)
        out.append(n)
        for m in sorted(after[n]):
            indeg[m] -= 1
            if not indeg[m]:
                ready.append(m)
        ready.sort()
    if len(out) != len(names):               # a cycle: the per-pair choice was inconsistent, so say so
        raise CyclicRelations(f"{len(names) - len(out)} spaces could not be ordered")
    return out


# ----------------------------------------------------------------------------- cost

def apart(a: Box, b: Box, need: int) -> int:
    """How far this pair is from sharing `need` mm of wall, in mm; 0 when it already does. A distance, not a flag:
    the annealer needs a slope to walk down, and "contact missing" on its own is a cliff (PLAN M16)."""
    gap_x = max(0, max(a.x, b.x) - min(a.x1, b.x1))
    gap_y = max(0, max(a.y, b.y) - min(a.y1, b.y1))
    ov_x = overlap_len(a.interval("x"), b.interval("x"))
    ov_y = overlap_len(a.interval("y"), b.interval("y"))
    on_side = gap_x + max(0, need - ov_y)        # meeting on a wall perpendicular to x
    on_end = gap_y + max(0, need - ov_x)         # ... to y
    return min(on_side, on_end)


def snap(pl: dict[str, Box], wanted: list[tuple[str, str, int]], env: dict[str, int] | None) -> dict[str, Box]:
    """Repair a packed layout: a pair that is flush but meets only at a corner is slid along the shared wall until
    it really shares it.

    **Measured dead end, kept for the record and not used** (PLAN §5, 2026-09-21). It was meant to put back the
    alignment compaction does not preserve, but a packed layout is dense: the neighbour a room would slide into is
    already there. It fixed no brief, made the annealer three times slower, and made room sizes worse (deviation
    on `eight_rooms_corridor` 0.000 -> 0.015) because a slid room drags `redim` with it."""
    out = dict(pl)
    for a, b, need in wanted:
        if apart(out[a], out[b], need) == 0:
            continue
        for mover, anchor in ((a, b), (b, a)):
            m, o = out[mover], out[anchor]
            done = False
            for axis in ("x", "y"):
                mlo, mhi = m.interval(axis)
                olo, ohi = o.interval(axis)
                for delta in (olo - mlo, ohi - mhi, olo + need - mhi, ohi - need - mlo):
                    if delta == 0:
                        continue
                    cand = Box(m.x + delta, m.y, m.z, m.w, m.l, m.h) if axis == "x" else Box(m.x, m.y + delta, m.z, m.w, m.l, m.h)
                    if cand.x < 0 or cand.y < 0:
                        continue
                    if env is not None and (cand.x1 > env["w"] or cand.y1 > env["l"]):
                        continue
                    if apart(cand, o, need) != 0:
                        continue
                    if any(intersects(cand, ob) for n, ob in out.items() if n != mover):
                        continue
                    out[mover] = cand
                    done = True
                    break
                if done:
                    break
            if done:
                break
    return out


def cost(brief: Brief, pl: dict[str, Box], p: SeqPairParams, env: dict[str, int] | None,
         required: list[tuple[str, str, int]], rooms: list[str], corridors: list[str]) -> float:
    missing = sum(apart(pl[a], pl[b], need) for a, b, need in required) / 1000
    stranded = 0.0
    for r in rooms:
        if r in corridors:
            continue
        stranded += min((apart(pl[r], pl[c], required_overlap_mm(brief, r, c, p.door_mm)) for c in corridors),
                        default=0) / 1000
    bb = bounds(pl.values())
    over = 0
    if env is not None:
        over = max(0, bb.w - env["w"]) + max(0, bb.l - env["l"])
    dead = (bb.w * bb.l - sum(b.w * b.l for b in pl.values())) / 1e6
    return (p.w_contact * missing + p.w_access * stranded + p.w_envelope * over / 1000
            + p.w_perimeter * (bb.w + bb.l) / 1000 + p.w_dead * dead)


def _wall(a: Box, b: Box, side: str) -> int:
    return touches(a, b, side)[0]


# ----------------------------------------------------------------------------- search

def _moves(rng: random.Random, plus: list[str], minus: list[str], rot: dict[str, bool],
           rotatable: list[str], hint: tuple[str, str] | None):
    """One random change, returned as a function that undoes it."""
    n = len(plus)
    pick = rng.random()
    if hint is not None and pick < 0.2:                      # pull a pair that is not touching together
        a, b = hint
        i, j = plus.index(a), plus.index(b)
        plus.insert(i + (0 if i < j else 1), plus.pop(j))
        i, j = minus.index(a), minus.index(b)
        minus.insert(i + (0 if i < j else 1), minus.pop(j))
        return None                                          # a big move: caller re-reads the state
    if pick < 0.35 and rotatable:
        v = rng.choice(rotatable)
        rot[v] = not rot[v]
        return ("rot", v)
    i, j = rng.randrange(n), rng.randrange(n)
    if i == j:
        j = (j + 1) % n
    which = "both" if pick > 0.8 else ("plus" if pick > 0.575 else "minus")
    if which in ("plus", "both"):
        plus[i], plus[j] = plus[j], plus[i]
    if which == "minus":
        minus[i], minus[j] = minus[j], minus[i]
    elif which == "both":                       # the same two spaces swap in the second ordering too
        ii, jj = minus.index(plus[i]), minus.index(plus[j])
        minus[ii], minus[jj] = minus[jj], minus[ii]
    return (which, i, j)


def _undo(move, plus: list[str], minus: list[str], rot: dict[str, bool]) -> None:
    if move is None:
        return
    if move[0] == "rot":
        rot[move[1]] = not rot[move[1]]
        return
    which, i, j = move
    if which in ("plus", "both"):
        plus[i], plus[j] = plus[j], plus[i]
    if which == "minus":
        minus[i], minus[j] = minus[j], minus[i]
    elif which == "both":
        ii, jj = minus.index(plus[i]), minus.index(plus[j])
        minus[ii], minus[jj] = minus[jj], minus[ii]


def anneal(brief: Brief, p: SeqPairParams, seed: int, start: tuple[list[str], list[str]] | None,
           spaces: list[Space], env: dict[str, int] | None, deadline: float) -> list[tuple[float, dict[str, Box]]]:
    rng = random.Random(seed)
    names = [s.name for s in spaces]
    H = level_height_mm(brief)
    h = {s.name: (s.nominal_mm("h") if s.is_shaft else H) for s in spaces}
    nominal = {s.name: (s.nominal_mm("w"), s.nominal_mm("l")) for s in spaces}
    rotatable = [s.name for s in spaces if s.w != s.l and s.program != "corridor"]
    corridors = [s.name for s in spaces if s.program == "corridor"]
    rooms = [s.name for s in spaces if s.program == "room"]
    # a corridor is as long as the spaces it must carry, narrow side on, shared over the corridors of the level
    demand = sum(min(*nominal[r]) for r in names if r not in corridors)
    size0 = dict(nominal)
    for c in corridors:
        lo, hi = brief.space(c).band("l")
        want = max(lo, min(hi, demand // max(1, 2 * len(corridors))))
        if env is not None:
            want = min(want, max(env["w"], env["l"]))
        size0[c] = (nominal[c][0], want)
    if start is not None and set(start[0]) == set(names):
        plus, minus = list(start[0]), list(start[1])
    else:
        plus, minus = list(names), list(names)
        rng.shuffle(plus); rng.shuffle(minus)
    rot = {n: False for n in names}
    required = [(a, b, required_overlap_mm(brief, a, b, p.door_mm)) for a, b in brief.contacts
                if a in nominal and b in nominal]

    clen = {c: size0[c][1] for c in corridors}          # a corridor's length is searched, not guessed (PLAN M16)
    bands = {c: brief.space(c).band("l") for c in corridors}
    cap = max(env["w"], env["l"]) if env is not None else max(hi for _lo, hi in bands.values()) if bands else 0

    def sizes():
        out = {}
        for n in names:
            w, l = size0[n]
            if n in clen:
                l = clen[n]
            out[n] = (l, w) if rot[n] else (w, l)
        return out

    def evaluate():
        pl = boxes((plus, minus), sizes(), 0, h)
        return cost(brief, pl, p, env, required, rooms, corridors), pl

    cur, cur_pl = evaluate()
    best_archive: dict[tuple, tuple[float, dict[str, Box]]] = {_signature(cur_pl): (cur, dict(cur_pl))}
    temp = max(1.0, abs(cur) * 0.3) / max(1e-9, -math.log(p.accept0))
    for step in range(p.iterations):
        if step % 64 == 0 and time.perf_counter() > deadline:
            break
        hint = None
        worst = 0
        for a, b, need in required:
            d = apart(cur_pl[a], cur_pl[b], need)
            if d > worst:
                worst, hint = d, (a, b)
        before = (list(plus), list(minus)) if hint is not None else None
        if corridors and rng.random() < 0.15:
            c = rng.choice(corridors)
            was = clen[c]
            lo, hi = bands[c]
            step = rng.choice((-3000, -1500, -500, 500, 1500, 3000))
            clen[c] = max(lo, min(hi, min(cap, was + step) if cap else was + step))
            move, before = ("clen", c, was), None
        else:
            move = _moves(rng, plus, minus, rot, rotatable, hint)
        cand, cand_pl = evaluate()
        delta = cand - cur
        if delta <= 0 or rng.random() < math.exp(-delta / max(temp, 1e-9)):
            cur, cur_pl = cand, cand_pl
            key = _signature(cur_pl)
            if key not in best_archive or best_archive[key][0] > cur:
                best_archive[key] = (cur, dict(cur_pl))
        elif before is not None:
            plus[:], minus[:] = before
        elif move is not None and move[0] == "clen":
            clen[move[1]] = move[2]
        else:
            _undo(move, plus, minus, rot)
        temp *= p.cooling
    return sorted(best_archive.values(), key=lambda t: t[0])


def _signature(pl: dict[str, Box]) -> tuple:
    names = sorted(pl)
    out = []
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            for s in HSIDES:
                if contact_area(pl[a], pl[b], s) > 0:
                    out.append((a, s, b))
    return tuple(out)


def seqpair_generator(brief: Brief, params: dict | None = None, seed: int = 0) -> list[dict[str, Box]]:
    p = SeqPairParams(**(params or {}))
    t0 = time.perf_counter()
    spaces = list(brief.spaces)
    env = envelope_mm(brief)
    start = None
    if p.warm_start:
        from .beam import BeamParams, beam_search
        warm = beam_search(brief, BeamParams(k=1, beam_width=8), seed, envelope=env, height=level_height_mm(brief))
        if warm:
            try:
                start = from_placement(warm[0])
            except CyclicRelations:
                start = None          # a layout this encoding cannot hold: begin from a shuffle instead
    out: list[dict[str, Box]] = []
    seen: set[tuple] = set()
    for r in range(p.restarts):
        left = p.time_limit - (time.perf_counter() - t0)
        if left <= 0 or len(out) >= p.k:
            break
        share = left if r == p.restarts - 1 else left / max(1, p.restarts - r)
        for _score, pl in anneal(brief, p, seed * 131 + r, start if r == 0 else None, spaces, env,
                                 time.perf_counter() + share):
            if len(out) >= p.k:
                break
            fixed = _finish(brief, pl, p)
            if fixed is None:
                continue
            key = _signature(fixed)
            if key in seen:
                continue
            seen.add(key)
            out.append(fixed)
    return out


def _finish(brief: Brief, pl: dict[str, Box], p: SeqPairParams) -> dict[str, Box] | None:
    """Size the packed layout exactly inside the tolerance bands, then keep it only if it is legal."""
    from .redim import redimension
    fixed = redimension(brief, pl, door_mm=p.door_mm) or pl
    return fixed if preverify(brief, fixed)[0] else None
