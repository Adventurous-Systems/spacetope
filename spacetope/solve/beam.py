"""Generator v1: beam search over incremental wall-to-wall attachment (single level, boxes only).

State = placement of a prefix of the spaces. Move = attach the next space to a free wall segment of a
placed space (opposite faces coincident), at one of a small set of alignment offsets, in either
orientation. Corridors may stretch within their length band to receive a room. Validity is an
integer interval test; topologicpy is never called here.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field, replace

from ..brief import Brief, CIRCULATION, Space
from ..doors import corridor_opening_mm, required_overlap_mm, touch_ok
from .grid import Box, any_intersection, bounds, contact_area, overlap_len, touches

HSIDES = ("+x", "-x", "+y", "-y")


@dataclass
class BeamParams:
    beam_width: int = 16
    k: int = 8
    door_mm: int = 900
    rotate: bool = True
    jitter: float = 0.05           # seed-driven score noise for diversity
    w_required: float = 30.0
    w_access: float = 4.0
    w_contact_area: float = 0.3    # per m2
    w_perimeter: float = 2.0       # per m of bbox half-perimeter
    w_dev: float = 40.0            # per unit of summed fractional deviation (corridor stretch)
    w_dead: float = 0.25           # per m2 of bbox area not covered (sweep 2026-09-13: 0.25/100 -> dev 0.007, adj 1.0)
    w_stack: float = 3.0           # bonus for wall planes aligned with the level below
    attach_required_first: bool = True  # a space with placed required partners attaches only to them
    redim: bool = True
    pair_order: bool = True        # a room with a room partner is placed right after it, while the slot beside it is free (PLAN M15)
    w_frontage: float = 0.0        # per metre of projected frontage shortfall; measured 2026-09-20: shaping the score this way
                                   # makes the beam leave rooms off the corridor, so it is off; tight_corridors does the job
    tight_ratio: float = 0.75      # a corridor is tight when its partners' narrow sides need more than this share of its two sides (PLAN M15)


@dataclass
class State:
    placed: dict[str, Box]
    score: float = 0.0
    key: tuple = field(default_factory=tuple)
    # aggregates for incremental scoring
    req_hit: int = 0
    area_mm2: int = 0
    access: frozenset = frozenset()
    dev_sum: float = 0.0


def space_dev(brief: Brief, name: str, b: Box) -> float:
    s = brief.space(name)
    nw, nl = s.nominal_mm("w"), s.nominal_mm("l")
    return min(abs(b.w - nw) / nw + abs(b.l - nl) / nl, abs(b.w - nl) / nl + abs(b.l - nw) / nw)


def _door_ok(a: Box, b: Box, door: int) -> bool:
    for s in HSIDES:
        u, v = touches(a, b, s)
        if u >= door and v > 0:
            return True
    return False


def _finish(brief: Brief, placed: dict[str, Box], p: BeamParams, req_hit: int, area: int, access: frozenset,
            dev_sum: float, ref_planes) -> float:
    bb = bounds(placed.values())
    half_perim = (bb.w + bb.l) / 1000
    covered = sum(b.w * b.l for b in placed.values()) / 1e6
    dead = bb.w * bb.l / 1e6 - covered
    stack = 0.0
    if ref_planes:
        px, py = planes(placed.values())
        tot = len(px) + len(py)
        stack = (len(px & ref_planes[0]) + len(py & ref_planes[1])) / tot if tot else 0.0
    return (p.w_required * req_hit + p.w_access * len(access) + p.w_contact_area * area / 1e6
            - p.w_perimeter * half_perim - p.w_dead * dead - p.w_dev * dev_sum + p.w_stack * stack)


def state_from_placed(brief: Brief, placed: dict[str, Box], p: BeamParams, ref_planes=None) -> State:
    """Full (non-incremental) evaluation; used for initial states and after a corridor stretch."""
    names = list(placed)
    req = brief.required_pairs()
    area, hit = 0, 0
    pairs = set()
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            for s in HSIDES:
                ar = contact_area(placed[a], placed[b], s)
                if ar:
                    area += ar; pairs.add(frozenset((a, b)))
    hit = sum(1 for pr in req if pr in pairs)
    circ = [n for n in names if brief.space(n).program in CIRCULATION]
    access = frozenset(n for n in names if brief.space(n).program == "room" and any(_door_ok(placed[n], placed[c], p.door_mm) for c in circ))
    dev_sum = sum(space_dev(brief, n, b) for n, b in placed.items())
    return State(placed, _finish(brief, placed, p, hit, area, access, dev_sum, ref_planes), contacts_key(placed), hit, area, access, dev_sum)


def extend_state(brief: Brief, parent: State, new: dict[str, Box], name: str, p: BeamParams, ref_planes=None) -> State:
    """Score `new` = parent.placed + box `name` incrementally. Falls back to a full evaluation when
    an existing box changed (corridor stretch)."""
    for n, b in parent.placed.items():
        if new[n] != b:
            return state_from_placed(brief, new, p, ref_planes)
    box = new[name]
    req = brief.required_pairs()
    area, hit = parent.area_mm2, parent.req_hit
    access = set(parent.access)
    sp = brief.space(name)
    touched = set()
    for n, b in parent.placed.items():
        for s in HSIDES:
            ar = contact_area(box, b, s)
            if ar:
                area += ar; touched.add(n)
    hit += sum(1 for n in touched if frozenset((name, n)) in req)
    if sp.program == "room":
        if any(_door_ok(box, parent.placed[c], p.door_mm) for c in touched if brief.space(c).program in CIRCULATION):
            access.add(name)
    elif sp.is_circulation:
        for n in touched:
            if brief.space(n).program == "room" and n not in access and _door_ok(box, parent.placed[n], p.door_mm):
                access.add(n)
    dev_sum = parent.dev_sum + space_dev(brief, name, box)
    access = frozenset(access)
    key = set(parent.key)
    for n in touched:
        for s in HSIDES:
            if contact_area(box, parent.placed[n], s) > 0:
                key.add((name, s, n) if name <= n else (n, OPPOSITE_H[s], name))
    return State(new, _finish(brief, new, p, hit, area, access, dev_sum, ref_planes), frozenset(key), hit, area, access, dev_sum)


def dims(space: Space, rotated: bool, height: int | None = None, length: int | None = None) -> tuple[int, int, int]:
    # the level-height override applies to floor-bound spaces; a shaft keeps its span height (M7)
    h = space.nominal_mm("h") if (space.is_shaft or not height) else height
    w, l = space.nominal_mm("w"), (length or space.nominal_mm("l"))   # `length`: a tight corridor starts longer (M15)
    return (l, w, h) if rotated else (w, l, h)


def planes(boxes) -> tuple[set[int], set[int]]:
    xs, ys = set(), set()
    for b in boxes:
        xs.update((b.x, b.x1)); ys.update((b.y, b.y1))
    return xs, ys


def order_spaces(brief: Brief, rng: random.Random, spaces: list[Space] | None = None) -> list[Space]:
    req = {}
    for a, b in brief.contacts:
        req[a] = req.get(a, 0) + 1
        req[b] = req.get(b, 0) + 1
    tiers: dict[tuple, list[Space]] = {}
    for s in (spaces if spaces is not None else brief.spaces):
        tier = (0 if s.program == "corridor" else 1 if s.is_circulation else 2, -req.get(s.name, 0))
        tiers.setdefault(tier, []).append(s)
    out = []
    for t in sorted(tiers):
        group = tiers[t]
        group.sort(key=lambda s: -(s.w * s.l))
        # small seed-driven perturbation: swap neighbours within a tier
        for i in range(len(group) - 1):
            if rng.random() < 0.3:
                group[i], group[i + 1] = group[i + 1], group[i]
        out.extend(group)
    return out


def pair_adjacent(brief: Brief, order: list[Space]) -> list[Space]:
    """PLAN M15: rooms that must touch each other are placed as one contiguous run, walked from an end of their
    chain (lab, prep room, lab; imaging, x-ray, control room). Each usually also needs the corridor, and the only
    position touching both is the slot beside the partner on the corridor's side. Placed apart, other rooms take
    that slot; placed hub-first, the hub can land at the corridor's end with one free side (both measured)."""
    import networkx as nx
    names = [s.name for s in order]
    g = nx.Graph()
    g.add_edges_from((a, b) for a, b in brief.contacts if a in names and b in names
                     and brief.space(a).program == "room" and brief.space(b).program == "room")
    if g.number_of_edges() == 0:
        return list(order)
    by_name = {s.name: s for s in order}
    out = list(names)
    for comp in sorted(nx.connected_components(g), key=lambda c: min(names.index(n) for n in c)):
        sub = g.subgraph(comp)
        ends = sorted((n for n in comp if sub.degree(n) == 1), key=names.index) or sorted(comp, key=names.index)
        run = list(nx.dfs_preorder_nodes(sub, ends[0]))
        at = min(out.index(n) for n in comp)
        out = [n for n in out if n not in comp]
        out[at:at] = run
    return [by_name[n] for n in out]


def tight_corridors(brief: Brief, spaces: list[Space], envelope: dict[str, int] | None, p: "BeamParams") -> dict[str, int]:
    """PLAN M15: corridors whose required partners, narrow side on, need more than `tight_ratio` of the two long sides
    the corridor can ever offer. Returns {corridor: length to start at in mm}. On these corridors spaces attach narrow
    side on only, and the corridor starts long enough for them instead of stretching room by room."""
    out: dict[str, int] = {}
    names = {s.name for s in spaces}
    corridors = [c for c in spaces if c.program == "corridor"]
    # spaces that need a corridor but name no particular one: every room when the brief has circulation (rule D8),
    # and shafts on a chained spine. They fall to whichever segment takes them, so share them out (M15b).
    explicit = {a for a, b in brief.contacts for a in (a, b) if brief.space(a).program == "corridor"}
    shared = [s for s in spaces if (s.program == "room" and brief.circulation) or s.is_vertical]
    shared = [s for s in shared if not any(frozenset((s.name, c.name)) in {frozenset(q) for q in brief.contacts} for c in corridors)]
    share = sum(min(s.nominal_mm("w"), s.nominal_mm("l")) for s in shared) // max(1, len(corridors))
    for c in corridors:
        partners = [brief.space(b if a == c.name else a) for a, b in brief.contacts if c.name in (a, b)]
        demand = sum(min(s.nominal_mm("w"), s.nominal_mm("l")) for s in partners
                     if (s.name in names or s.is_shaft) and s.program != "corridor")
        demand += share
        limit = c.band("l")[1]
        if envelope is not None:
            limit = min(limit, max(envelope["w"], envelope["l"]))
        if c.wishes.get("segment"):
            # a chained spine exists because one straight corridor could not carry the level: frontage is scarce by
            # construction, so its segments take spaces narrow side on. They keep their nominal length and stretch
            # as rooms arrive, because an L only fits the envelope if each arm stops where the other begins (M15b).
            out[c.name] = c.nominal_mm("l")
            continue
        if limit <= 0 or demand / (2 * limit) <= p.tight_ratio:
            continue
        out[c.name] = max(c.nominal_mm("l"), min(limit, int(demand / 2 * 1.06) // 100 * 100 + 100))
    return out


def frontage_shortfall(brief: Brief, placed: dict[str, Box], remaining: list[Space], envelope: dict[str, int] | None,
                       reserve: float = 0.08) -> float:
    """Metres of corridor wall the unplaced spaces will lack. For each placed corridor: the wall still free on its two
    long sides if it stretched to its limit, less a reserve for alignment gaps, against the narrow nominal side of every
    unplaced space that must touch it. On a loose brief this is zero throughout; on a tight one it charges every metre
    a space spends beyond its narrow side, from the first step, which is what turns rooms and stairs narrow side on."""
    if not remaining:
        return 0.0
    short = 0
    rem = {s.name: s for s in remaining}
    for cname, cbox in placed.items():
        cs = brief.space(cname)
        if cs.program != "corridor":
            continue
        demand = 0
        for a, b in brief.contacts:
            other = b if a == cname else a if b == cname else None
            if other is None:
                continue
            if other in rem:
                o = rem[other]
                demand += min(o.nominal_mm("w"), o.nominal_mm("l"))   # the beam places at nominal size
            elif other in placed and not any(touches(cbox, placed[other], sd)[0] for sd in HSIDES):
                o = brief.space(other)                                 # placed off its corridor: the need has not gone away
                demand += min(o.nominal_mm("w"), o.nominal_mm("l"))
        if demand == 0:
            continue
        along_y = cbox.l >= cbox.w
        limit = cs.band("l")[1]
        if envelope is not None:
            limit = min(limit, envelope["l"] if along_y else envelope["w"])
        used = 0
        for n, b in placed.items():
            if n == cname:
                continue
            for side in (("+x", "-x") if along_y else ("+y", "-y")):
                used += touches(cbox, b, side)[0]
        short += max(0, demand - (int(2 * limit * (1.0 - reserve)) - used))
    return short / 1000.0


OPPOSITE_H = {"+x": "-x", "-x": "+x", "+y": "-y", "-y": "+y"}


def contacts_key(placed: dict[str, Box]) -> frozenset:
    """Relation key: (a, side_of_a, b) for every touching pair with a <= b (name order)."""
    names = sorted(placed)
    key = set()
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            for s in HSIDES:
                if contact_area(placed[a], placed[b], s) > 0:
                    key.add((a, s, b))
    return frozenset(key)


def evaluate(brief: Brief, placed: dict[str, Box], p: BeamParams, ref_planes: tuple[set[int], set[int]] | None = None) -> float:
    """Full evaluation of a placement (see state_from_placed)."""
    return state_from_placed(brief, placed, p, ref_planes).score


def offsets_for(target: Box, other_boxes: list[Box], axis: str, length: int, min_overlap: int,
                plane: tuple[str, int] | None = None) -> list[int]:
    """Alignment offsets along `axis`: target ends, centre, door-minimum overlaps, and the ends of
    boxes that already sit on the same plane (corner alignment with co-planar neighbours only)."""
    lo, hi = target.interval(axis)
    cands = {lo, hi - length, lo + (hi - lo - length) // 2, hi - min_overlap, lo + min_overlap - length}
    for b in other_boxes:
        if plane is not None:
            pax, pc = plane
            if b.interval(pax)[0] != pc and b.interval(pax)[1] != pc:
                continue
        blo, bhi = b.interval(axis)
        cands.update({blo, bhi, blo - length, bhi - length})
    return sorted(c for c in cands if overlap_len((c, c + length), (lo, hi)) >= min_overlap)


def stretch_corridor(cor: Box, axis: str, need: tuple[int, int], band: tuple[int, int]) -> Box | None:
    """Extend a corridor along its long axis to cover interval `need`, within its length band."""
    lo, hi = cor.interval(axis)
    nlo, nhi = min(lo, need[0]), max(hi, need[1])
    if (nlo, nhi) == (lo, hi):
        return cor
    if nhi - nlo > band[1]:
        return None
    if axis == "x":
        return Box(nlo, cor.y, cor.z, nhi - nlo, cor.l, cor.h)
    return Box(cor.x, nlo, cor.z, cor.w, nhi - nlo, cor.h)


def moves(brief: Brief, state: State, space: Space, p: BeamParams, height: int | None = None,
          envelope: dict[str, int] | None = None, context: list[Box] | None = None,
          level_z: int | None = None, tight: dict[str, int] | None = None) -> list[dict[str, Box]]:
    out: list[dict[str, Box]] = []
    placed = state.placed
    orientations = [False, True] if (p.rotate and space.w != space.l) else [False]
    others = list(placed.values())
    partners = {b if a == space.name else a for a, b in brief.contacts if space.name in (a, b)}
    restrict = p.attach_required_first and bool(partners & set(placed))
    targets = [n for n in placed if n in partners] if restrict else list(placed)
    out = _moves_to(brief, state, space, p, targets, others, orientations, height, envelope, context, level_z, tight=tight)
    if not out and restrict:  # required partner has no free face: fall back to any placed space
        out = _moves_to(brief, state, space, p, [n for n in placed if n not in partners], others, orientations, height, envelope, context, level_z, tight=tight)
    if not out:  # last resort: allow a door pair to graze, which door planning will then report
        out = _moves_to(brief, state, space, p, list(placed), others, orientations, height, envelope, context, level_z,
                        enforce_doors=False, tight=tight)
    return out


def _moves_to(brief, state, space, p, targets, others, orientations, height, envelope, context, level_z=None,
              enforce_doors=True, tight=None) -> list[dict[str, Box]]:
    out: list[dict[str, Box]] = []
    placed = state.placed
    for pname in targets:
        pbox = placed[pname]
        pspace = brief.space(pname)
        for side in HSIDES:
            for rot in orientations:
                sw, sl, sh = dims(space, rot, height, (tight or {}).get(space.name))
                if tight and pname in tight and space.program != "corridor" and sw != sl:
                    along = sl if side in ("+x", "-x") else sw          # the side this space would lay along the corridor
                    if along != min(sw, sl):
                        continue                                          # tight corridor: narrow side on only (M15)
                # place on the level being assembled; a tall shaft target starts below it (M7)
                z = level_z if level_z is not None else pbox.z
                if side in ("+x", "-x"):
                    axis, length = "y", sl
                    x = pbox.x1 if side == "+x" else pbox.x - sw
                else:
                    axis, length = "x", sw
                    y = pbox.y1 if side == "+y" else pbox.y - sl
                if pspace.program == "corridor" and space.program == "room":
                    long_axis = "y" if pbox.l >= pbox.w else "x"
                    if (side in ("+y", "-y") and long_axis == "y") or (side in ("+x", "-x") and long_axis == "x"):
                        continue  # rooms do not cap a corridor's ends; the corridor must stay stretchable
                min_ov = required_overlap_mm(brief, space.name, pname, p.door_mm)
                # corridor may stretch to receive the room: widen the candidate set beyond its ends
                stretchable = pspace.program == "corridor" and (axis == ("y" if pbox.l >= pbox.w else "x"))
                target = pbox
                plane_axis = "x" if side in ("+x", "-x") else "y"
                plane_coord = x if side in ("+x", "-x") else y
                cand_offsets = offsets_for(target, others, axis, length, min_ov, (plane_axis, plane_coord + (sw if side == "-x" else sl if side == "-y" else 0)))
                if stretchable:
                    lo, hi = pbox.interval(axis)
                    cand_offsets = sorted(set(cand_offsets) | {hi, lo - length})
                for off in cand_offsets:
                    if side in ("+x", "-x"):
                        box = Box(x, off, z, sw, sl, sh)
                    else:
                        box = Box(off, y, z, sw, sl, sh)
                    new = dict(placed)
                    if stretchable and overlap_len(box.interval(axis), pbox.interval(axis)) < min_ov:
                        band = pspace.band("l")
                        need = box.interval(axis)
                        st = stretch_corridor(pbox, axis, (need[0], need[1]), band)
                        if st is None:
                            continue
                        new[pname] = st
                        if any_intersection(st, [b for n, b in new.items() if n != pname]):
                            continue
                    if any_intersection(box, [b for n, b in new.items() if n != space.name]):
                        continue
                    back = {"+x": "-x", "-x": "+x", "+y": "-y", "-y": "+y"}[side]
                    if touches(box, new[pname], back)[0] < min_ov:
                        continue
                    if corridor_opening_mm(brief, space.name, pname):
                        # segments of one spine turn a corner: they meet end on (exactly the corridor width) and run
                        # on different axes. Laid side by side or in line they are walkable but add no frontage,
                        # which is the only reason to chain a corridor at all (M15b).
                        if touches(box, new[pname], back)[0] != min_ov:
                            continue
                        if (box.w >= box.l) == (new[pname].w >= new[pname].l):
                            continue
                    if enforce_doors and any(not touch_ok(brief, space.name, box, n, b, p.door_mm)
                                             for n, b in new.items() if n != space.name):
                        continue  # a pair that needs a door would only graze this box
                    new[space.name] = box
                    if envelope is not None:
                        bb = bounds(list(new.values()) + (context or []))
                        if bb.w > envelope["w"] or bb.l > envelope["l"]:
                            continue
                    out.append(new)
    return out


def beam_search(brief: Brief, params: BeamParams | None = None, seed: int = 0, *,
                spaces: list[Space] | None = None, fixed: dict[str, Box] | None = None,
                context: list[Box] | None = None, ref_planes: tuple[set[int], set[int]] | None = None,
                envelope: dict[str, int] | None = None, height: int | None = None, z0: int = 0,
                normalise_output: bool = True, redim: bool | None = None,
                scorer=None, trace: list | None = None, batch_scorer=None) -> list[dict[str, Box]]:
    """Place `spaces` (default: all) one by one. `fixed` boxes are pre-placed (cores on this level);
    `context` boxes (other levels) only count towards the envelope bounding box.
    `scorer(brief, state, progress, ref_planes) -> float` replaces the hand-weighted score (M6).
    `trace`, when a list, receives one entry per step: the full candidate pool before truncation.
    `batch_scorer(brief, states, progress, ref_planes) -> list[float]` scores a whole pool in one call (GNN)."""
    p = params or BeamParams()
    if any(s.program == "corridor" and s.wishes.get("segment") for s in brief.spaces) and p.w_access < p.w_required:
        # On a chained spine a room names no corridor, so reaching one by a door *is* the requirement and carries
        # the weight a required contact would. Without this the search prefers a room anywhere (0) over stretching a
        # segment to take it (a corridor's length deviation costs more than access was worth) — measured (M15b).
        p = replace(p, w_access=p.w_required)
    rng = random.Random(seed)
    order = order_spaces(brief, rng, spaces)
    if p.pair_order:
        order = pair_adjacent(brief, order)
    if not order and not fixed:
        return []  # nothing to place on this level (a stale `expanded: true` file can get here)
    n_steps = max(1, len(order))
    tight = tight_corridors(brief, order, envelope, p)
    beam: list[State] = []
    if fixed:
        beam.append(state_from_placed(brief, dict(fixed), p, ref_planes))
        rest = order
    else:
        first = order[0]
        for rot in ([False, True] if (p.rotate and first.w != first.l) else [False]):
            w, l, h = dims(first, rot, height, tight.get(first.name))
            beam.append(state_from_placed(brief, {first.name: Box(0, 0, z0, w, l, h)}, p, ref_planes))
        rest = order[1:]
    for step, space in enumerate(rest, start=1):
        pool: dict[frozenset, State] = {}
        progress = step / n_steps
        if scorer is not None and batch_scorer is None:
            # learned per-state scorer: apply it after merging duplicates, like the batch path (3,437 -> ~600 calls)
            def batch_scorer(brief_, states_, progress_, ref_planes_, _f=scorer):
                return [_f(brief_, st_, progress_, ref_planes_) for st_ in states_]
        if batch_scorer is not None:
            cands: dict[frozenset, State] = {}
            for st in beam:
                for new in moves(brief, st, space, p, height, envelope, context, level_z=z0, tight=tight):
                    ns = extend_state(brief, st, new, space.name, p, ref_planes)
                    if ns.key not in cands or cands[ns.key].score < ns.score:
                        cands[ns.key] = ns   # dedupe on the hand score first; the batch scorer then ranks the survivors
            if cands:
                states = list(cands.values())
                for ns, sc in zip(states, batch_scorer(brief, states, progress, ref_planes)):
                    ns.score = float(sc) + rng.uniform(-p.jitter, p.jitter)
                    if p.w_frontage:
                        ns.score -= p.w_frontage * frontage_shortfall(brief, ns.placed, rest[step:], envelope)
                    pool[ns.key] = ns
        else:
            for st in beam:
                for new in moves(brief, st, space, p, height, envelope, context, level_z=z0, tight=tight):
                    ns = extend_state(brief, st, new, space.name, p, ref_planes)
                    ns.score += rng.uniform(-p.jitter, p.jitter)
                    if p.w_frontage:
                        ns.score -= p.w_frontage * frontage_shortfall(brief, ns.placed, rest[step:], envelope)
                    if ns.key not in pool or pool[ns.key].score < ns.score:
                        pool[ns.key] = ns
        if not pool:
            return []
        if trace is not None:
            trace.append({"step": step, "progress": progress, "ref_planes": ref_planes, "pool": list(pool.values())})
        beam = sorted(pool.values(), key=lambda s: -s.score)[:p.beam_width]
    beam.sort(key=lambda s: -s.score)
    results = [normalise(st.placed) if normalise_output else dict(st.placed) for st in beam[:p.k]]
    if (p.redim if redim is None else redim):
        from .redim import redimension
        results = [redimension(brief, pl) or pl for pl in results]
    return results


def normalise(placed: dict[str, Box]) -> dict[str, Box]:
    """Translate so the bounding box starts at the origin (keeps every contact exact)."""
    bb = bounds(placed.values())
    return {n: Box(b.x - bb.x, b.y - bb.y, b.z - bb.z, b.w, b.l, b.h) for n, b in placed.items()}
