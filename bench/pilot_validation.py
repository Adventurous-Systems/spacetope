"""Pilot validation: fault injection (mutations) and metamorphic invariance on real SpaceTope options.
Run with cwd = repo root:  .venv/bin/python ../pilot_validation.py out.json"""
import json
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))
from spacetope.brief import load  # noqa: E402
from spacetope.circulation import prepare  # noqa: E402
from spacetope.placement import overlaps, topology_classes  # noqa: E402
from spacetope.preverify import preverify  # noqa: E402
from spacetope.score import cheap_scores  # noqa: E402
from spacetope.solve.grid import Box, touches  # noqa: E402
from spacetope.solve.registry import GENERATORS  # noqa: E402
from spacetope.verify import verify  # noqa: E402

HS = ("+x", "-x", "+y", "-y")
rng = random.Random(7)


def bands_violated(brief, pl):
    bad = 0
    for n, x in pl.items():
        s = brief.space(n)
        bw, bl, bh = s.band("w"), s.band("l"), s.band("h")
        plain = bw[0] <= x.w <= bw[1] and bl[0] <= x.l <= bl[1]
        rot = bl[0] <= x.w <= bl[1] and bw[0] <= x.l <= bw[1]
        hok = bh[0] <= x.h <= bh[1] or s.is_shaft
        if not ((plain or rot) and hok):
            bad += 1
    return bad


def shift(b, dx=0, dy=0, dz=0):
    return Box(b.x + dx, b.y + dy, b.z + dz, b.w, b.l, b.h)


def touching_pairs(pl, required=None):
    out = []
    names = list(pl)
    for i, a in enumerate(names):
        for c in names[i + 1:]:
            for s in HS:
                u, v = touches(pl[a], pl[c], s)
                if u > 0:
                    req = required is not None and frozenset((a, c)) in required
                    out.append((a, c, s, req))
    return out


DIR = {"+x": (1, 0), "-x": (-1, 0), "+y": (0, 1), "-y": (0, -1)}


def m_gap(brief, pl, want_required):
    req = brief.required_pairs()
    cands = [t for t in touching_pairs(pl, req) if t[3] == want_required]
    rng.shuffle(cands)
    for a, c, s, _ in cands:
        # c sits on side s of a: move c 1 mm further along s, or a 1 mm the other way when c is circulation
        if brief.space(c).program == "room":
            mover, (dx, dy) = c, DIR[s]
        elif brief.space(a).program == "room":
            mover, (dx, dy) = a, (-DIR[s][0], -DIR[s][1])
        else:
            continue
        new = dict(pl)
        new[mover] = shift(pl[mover], dx, dy)
        if not overlaps(new):
            return new, f"{mover} moved 1 mm off {c if mover == a else a}"
    return None, "no candidate"


def m_overlap(brief, pl):
    cands = touching_pairs(pl)
    rng.shuffle(cands)
    for a, c, s, _ in cands:
        if brief.space(c).program == "corridor" or brief.space(c).is_vertical:
            continue
        dx, dy = DIR[s]
        new = dict(pl)
        new[c] = shift(pl[c], -dx * 50, -dy * 50)   # c pushed 50 mm into a
        return new, f"{c} pushed 50 mm into {a}"
    return None, "no candidate"


def m_shrink(brief, pl):
    rooms = [n for n in pl if brief.space(n).program == "room"]
    rng.shuffle(rooms)
    for n in rooms:
        b = pl[n]
        new = dict(pl)
        new[n] = Box(b.x, b.y, b.z, int(b.w * 0.75), b.l, b.h)
        return new, f"{n} width cut to 75 %"
    return None, "no candidate"


def m_grow_outward(brief, pl):
    """Grow a room by 30 % on a side with nothing beyond it (stays exact, leaves band)."""
    rooms = [n for n in pl if brief.space(n).program == "room"]
    rng.shuffle(rooms)
    for n in rooms:
        b = pl[n]
        for side in HS:
            if side == "+x":
                nb = Box(b.x, b.y, b.z, int(b.w * 1.3), b.l, b.h)
            elif side == "-x":
                d = int(b.w * 0.3); nb = Box(b.x - d, b.y, b.z, b.w + d, b.l, b.h)
            elif side == "+y":
                nb = Box(b.x, b.y, b.z, b.w, int(b.l * 1.3), b.h)
            else:
                d = int(b.l * 0.3); nb = Box(b.x, b.y - d, b.z, b.w, b.l + d, b.h)
            new = dict(pl); new[n] = nb
            if not overlaps(new):
                return new, f"{n} grown 30 % on {side}"
    return None, "no candidate"


def m_shaft(brief, pl):
    for n, b in pl.items():
        if brief.space(n).is_shaft:
            new = dict(pl)
            new[n] = Box(b.x, b.y, b.z, b.w, b.l, b.h // 2)
            return new, f"{n} cut to half height"
    return None, "no shaft"


def m_envelope(brief, pl):
    if not brief.envelope:
        return None, "no envelope"
    dx = int(brief.envelope["w"] * 1000)
    return {n: shift(b, dx=dx) for n, b in pl.items()}, "layout moved out of the envelope"


def t_translate(brief, pl):
    if brief.envelope:
        return None, "envelope"
    return {n: shift(b, 12345, 6789) for n, b in pl.items()}, "translate (12 345, 6 789) mm"


def t_mirror(brief, pl):
    X = max(b.x1 for b in pl.values()); X0 = min(b.x for b in pl.values())
    return {n: Box(X0 + X - b.x1, b.y, b.z, b.w, b.l, b.h) for n, b in pl.items()}, "mirror in x"


def t_rotate(brief, pl):
    Y1 = max(b.y1 for b in pl.values())
    out = {n: Box(Y1 - b.y1, b.x, b.z, b.l, b.w, b.h) for n, b in pl.items()}
    if brief.envelope:
        e = brief.envelope
        if e["w"] != e["l"]:
            return None, "rectangular envelope"
    return out, "rotate 90 degrees"


def t_shuffle(brief, pl):
    items = list(pl.items()); rng.shuffle(items)
    return dict(items), "shuffle space order"


MUTATIONS = {"gap_required": lambda b, p: m_gap(b, p, True), "gap_incidental": lambda b, p: m_gap(b, p, False),
             "overlap_50mm": m_overlap, "shrink_room": m_shrink, "grow_out_of_band": m_grow_outward,
             "shaft_half_height": m_shaft, "out_of_envelope": m_envelope}
METAMORPHIC = {"translate": t_translate, "mirror": t_mirror, "rotate": t_rotate, "shuffle": t_shuffle}


def record(brief, pl, label, kind, ref_class_rep=None, ref_scores=None):
    t0 = time.perf_counter()
    pv, _ = preverify(brief, pl)
    rep = verify(brief, pl)
    sc = cheap_scores(brief, pl)
    row = {"kind": kind, "transform": label, "preverify": pv, "verify": rep.ok,
           "failed": [k for k, (ok, _) in rep.checks.items() if not ok],
           "adjacency": sc["adjacency"], "bands_violated": bands_violated(brief, pl),
           "seconds": round(time.perf_counter() - t0, 2)}
    if ref_class_rep is not None:
        row["same_topology_class"] = len(set(topology_classes(brief, [ref_class_rep, pl]))) == 1
        row["scores_equal"] = all(abs(sc[k] - ref_scores[k]) < 1e-6 for k in sc if k != "envelope_fit")
    return row


def main():
    out = Path(sys.argv[1])
    rows = []
    for fx, gen, n_opts in (("eight_rooms_corridor", "beam", 4), ("two_levels_stair", "beam", 3)):
        brief, _ = prepare(load(Path("fixtures") / f"{fx}.yaml"))
        opts = GENERATORS[gen](brief, None, 0)[:n_opts]
        for i, pl in enumerate(opts):
            base = record(brief, pl, "none", "original")
            base.update(fixture=fx, option=i); rows.append(base); print(base, flush=True)
            ref_scores = cheap_scores(brief, pl)
            for name, fn in METAMORPHIC.items():
                new, why = fn(brief, pl)
                if new is None:
                    continue
                r = record(brief, new, name, "metamorphic", pl, ref_scores); r.update(fixture=fx, option=i, detail=why)
                rows.append(r); print(r, flush=True)
            for name, fn in MUTATIONS.items():
                new, why = fn(brief, pl)
                if new is None:
                    continue
                r = record(brief, new, name, "mutation"); r.update(fixture=fx, option=i, detail=why)
                rows.append(r); print(r, flush=True)
    out.write_text(json.dumps(rows, indent=1))


if __name__ == "__main__":
    main()
