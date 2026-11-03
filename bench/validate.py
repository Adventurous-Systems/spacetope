"""E1/E1b: fault injection and metamorphic invariance on saved placements (the generalised pilot).

Reads the placements that `bench.py --save-placements` wrote, applies one fault of each kind and every
metamorphic relation to each verified placement, and streams one CSV row per (placement, transform).
Faults must be rejected (the control must pass); metamorphic relations must change neither the verdict,
nor the topology class, nor any score except `envelope_fit`.

Usage, from the repository root:
  .venv/bin/python bench/validate.py --placements bench/paper/placements \
      --faults bench/paper/e1_faults.csv --metamorphic bench/paper/e1b_metamorphic.csv \
      [--seeds 0 1] [--workers 6] [--resume]

The pool passes plain strings and dicts only; every worker rebuilds the brief from the fixture file
(PLAN §7: no library-spawned workers, nothing topologic crosses a process boundary).
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from functools import lru_cache
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

HS = ("+x", "-x", "+y", "-y")
DIR = {"+x": (1, 0), "-x": (-1, 0), "+y": (0, 1), "-y": (0, -1)}
FAULT_KIND = {"overlap_50mm": "geometry", "shaft_half_height": "hard constraint", "out_of_envelope": "hard constraint",
              "gap_required": "brief", "shrink_room": "brief", "grow_out_of_band": "brief",
              "door_slide": "brief", "gap_incidental": "control"}
COLUMNS = ["kind", "transform", "fixture", "generator", "seed", "option", "file", "detail", "preverify", "verify",
           "failed", "adjacency", "bands_violated", "same_topology_class", "scores_equal", "seconds"]


# ----------------------------------------------------------------------------- worker side

@lru_cache(maxsize=32)
def _brief(fixture: str):
    from spacetope.brief import load
    from spacetope.circulation import prepare
    brief, _ = prepare(load(Path("fixtures") / f"{fixture}.yaml"))
    return brief


def _shift(b, dx=0, dy=0, dz=0):
    from spacetope.solve.grid import Box
    return Box(b.x + dx, b.y + dy, b.z + dz, b.w, b.l, b.h)


def _touching(brief, pl):
    from spacetope.solve.grid import contact_area
    req = brief.required_pairs()
    names = sorted(pl)
    out = []
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            for s in HS:
                if contact_area(pl[a], pl[b], s) > 0:
                    out.append((a, b, s, frozenset((a, b)) in req))
    return out


def m_gap(brief, pl, rng, want_required: bool):
    from spacetope.placement import overlaps
    cands = _touching(brief, pl)
    rng.shuffle(cands)
    for a, c, s, req in cands:
        if req is not want_required:
            continue
        if brief.space(c).program == "room":
            mover, (dx, dy) = c, DIR[s]
        elif brief.space(a).program == "room":
            mover, (dx, dy) = a, (-DIR[s][0], -DIR[s][1])
        else:
            continue
        new = dict(pl)
        new[mover] = _shift(pl[mover], dx, dy)
        if not overlaps(new):
            if want_required:
                return new, f"{mover} moved 1 mm off {c if mover == a else a}"
            from spacetope.preverify import check_required_contacts
            if check_required_contacts(brief, new)[0]:   # the control must only open an incidental joint
                return new, f"{mover} moved 1 mm off {c if mover == a else a}"
    return None, "no candidate"


def m_overlap(brief, pl, rng):
    cands = _touching(brief, pl)
    rng.shuffle(cands)
    for a, c, s, _ in cands:
        if brief.space(c).program == "corridor" or brief.space(c).is_vertical:
            continue
        dx, dy = DIR[s]
        new = dict(pl)
        new[c] = _shift(pl[c], -dx * 50, -dy * 50)
        return new, f"{c} pushed 50 mm into {a}"
    return None, "no candidate"


def m_shrink(brief, pl, rng):
    from spacetope.solve.grid import Box
    rooms = [n for n in sorted(pl) if brief.space(n).program == "room"]
    if not rooms:
        return None, "no room"
    n = rng.choice(rooms)
    b = pl[n]
    new = dict(pl)
    new[n] = Box(b.x, b.y, b.z, int(b.w * 0.75), b.l, b.h)
    return new, f"{n} width cut to 75 %"


def m_grow(brief, pl, rng):
    from spacetope.placement import overlaps
    from spacetope.solve.grid import Box
    rooms = [n for n in sorted(pl) if brief.space(n).program == "room"]
    rng.shuffle(rooms)
    for n in rooms:
        b = pl[n]
        for nb in (Box(b.x, b.y, b.z, int(b.w * 1.3), b.l, b.h),
                   Box(b.x - int(b.w * 0.3), b.y, b.z, b.w + int(b.w * 0.3), b.l, b.h),
                   Box(b.x, b.y, b.z, b.w, int(b.l * 1.3), b.h),
                   Box(b.x, b.y - int(b.l * 0.3), b.z, b.w, b.l + int(b.l * 0.3), b.h)):
            new = dict(pl)
            new[n] = nb
            if not overlaps(new):
                return new, f"{n} grown 30 %"
    return None, "no candidate"


def m_shaft(brief, pl, rng):
    from spacetope.solve.grid import Box
    for n in sorted(pl):
        if brief.space(n).is_shaft:
            b = pl[n]
            new = dict(pl)
            new[n] = Box(b.x, b.y, b.z, b.w, b.l, b.h // 2)
            return new, f"{n} cut to half height"
    return None, "no shaft"


def m_envelope(brief, pl, rng):
    if not brief.envelope:
        return None, "no envelope"
    dx = int(brief.envelope["w"] * 1000)
    return {n: _shift(b, dx=dx) for n, b in pl.items()}, "layout moved out of the envelope"


def m_door_slide(brief, pl, rng):
    """Slide a room along its corridor wall until the shared run is under the door width plus jambs."""
    from spacetope.doors import required_overlap_mm
    from spacetope.placement import overlaps
    from spacetope.preverify import check_required_contacts
    if not brief.circulation:
        return None, "no circulation"
    cands = _touching(brief, pl)
    rng.shuffle(cands)
    for a, c, s, _ in cands:
        room, corr = (a, c) if brief.space(a).program == "room" else (c, a)
        if brief.space(room).program != "room" or brief.space(corr).program != "corridor":
            continue
        rb, cb = pl[room], pl[corr]
        need = required_overlap_mm(brief, room, corr)
        axis = "y" if s in ("+x", "-x") else "x"
        run = min(getattr(rb, axis + "1"), getattr(cb, axis + "1")) - max(getattr(rb, axis), getattr(cb, axis))
        for sign in (1, -1):
            new = dict(pl)
            new[room] = _shift(rb, **{"d" + axis: sign * (run - need // 2)})
            left = min(getattr(new[room], axis + "1"), getattr(cb, axis + "1")) - \
                max(getattr(new[room], axis), getattr(cb, axis))
            if 0 < left < need and not overlaps(new) and check_required_contacts(brief, new)[0]:
                return new, f"{room} slid to a {left} mm run on {corr} (< {need})"
    return None, "no candidate"


def t_translate(brief, pl, rng):
    if brief.envelope:
        return None, "envelope"
    return {n: _shift(b, 12345, 6789) for n, b in pl.items()}, "translate (12 345, 6 789) mm"


def t_mirror_x(brief, pl, rng):
    from spacetope.solve.grid import Box
    X1 = max(b.x1 for b in pl.values()); X0 = min(b.x for b in pl.values())
    return {n: Box(X0 + X1 - b.x1, b.y, b.z, b.w, b.l, b.h) for n, b in pl.items()}, "mirror in x"


def t_mirror_y(brief, pl, rng):
    from spacetope.solve.grid import Box
    Y1 = max(b.y1 for b in pl.values()); Y0 = min(b.y for b in pl.values())
    return {n: Box(b.x, Y0 + Y1 - b.y1, b.z, b.w, b.l, b.h) for n, b in pl.items()}, "mirror in y"


def t_rotate(brief, pl, rng):
    from spacetope.solve.grid import Box
    if brief.envelope and brief.envelope["w"] != brief.envelope["l"]:
        return None, "rectangular envelope"
    Y1 = max(b.y1 for b in pl.values())
    return {n: Box(Y1 - b.y1, b.x, b.z, b.l, b.w, b.h) for n, b in pl.items()}, "rotate 90 degrees"


def t_shuffle(brief, pl, rng):
    items = list(pl.items())
    rng.shuffle(items)
    return dict(items), "shuffle space order"


def t_swap_identical(brief, pl, rng):
    """Swap the boxes of two spaces with the same programme, nominal size, tolerance and level wish."""
    def key(s):
        return (s.program, s.w, s.l, s.h, str(s.tol), s.wishes.get("level"))
    groups: dict = {}
    for n in sorted(pl):
        groups.setdefault(key(brief.space(n)), []).append(n)
    twins = [g for g in groups.values() if len(g) >= 2]
    if not twins:
        return None, "no identical pair"
    a, b = rng.choice(twins)[:2]
    new = dict(pl)
    new[a], new[b] = pl[b], pl[a]
    return new, f"swap {a} and {b}"


FAULTS = {"gap_required": lambda b, p, r: m_gap(b, p, r, True), "gap_incidental": lambda b, p, r: m_gap(b, p, r, False),
          "overlap_50mm": m_overlap, "shrink_room": m_shrink, "grow_out_of_band": m_grow,
          "shaft_half_height": m_shaft, "out_of_envelope": m_envelope, "door_slide": m_door_slide}
METAMORPHIC = {"translate": t_translate, "mirror_x": t_mirror_x, "mirror_y": t_mirror_y, "rotate": t_rotate,
               "shuffle": t_shuffle, "swap_identical": t_swap_identical}


def bands_violated(brief, pl) -> int:
    from spacetope.preverify import check_bands
    ok, detail = check_bands(brief, pl)
    return 0 if ok else int(detail.split(" ")[0])


def record(brief, pl, ref=None) -> dict:
    from spacetope.placement import topology_classes
    from spacetope.preverify import preverify
    from spacetope.score import cheap_scores
    from spacetope.verify import verify
    t0 = time.perf_counter()
    pv, _ = preverify(brief, pl)
    rep = verify(brief, pl)
    sc = cheap_scores(brief, pl)
    row = {"preverify": pv, "verify": rep.ok,
           "failed": " ".join(k for k, (ok, _) in rep.checks.items() if not ok),
           "adjacency": round(sc["adjacency"], 4), "bands_violated": bands_violated(brief, pl),
           "seconds": round(time.perf_counter() - t0, 2)}
    if ref is not None:
        ref_pl, ref_ok, ref_scores = ref
        row["same_topology_class"] = len(set(topology_classes(brief, [ref_pl, pl]))) == 1
        row["scores_equal"] = all(abs(sc[k] - ref_scores[k]) < 1e-6 for k in sc if k != "envelope_fit")
        row["verify"] = rep.ok
        row["verdict_unchanged"] = rep.ok == ref_ok
    return row


def work(fixture: str, meta: dict, path: str) -> list[dict]:
    """All transforms of one saved placement; returns plain rows only."""
    from spacetope.placement import load_placement
    from spacetope.score import cheap_scores
    from spacetope.verify import verify
    brief = _brief(fixture)
    pl = load_placement(path)
    base = {"fixture": fixture, "generator": meta.get("generator", ""), "seed": meta.get("seed", ""),
            "option": meta.get("option", ""), "file": path}
    ref_ok = verify(brief, pl).ok
    ref_scores = cheap_scores(brief, pl)
    rows = [{**base, "kind": "original", "transform": "none", "detail": "",
             **record(brief, pl)}]
    for name, fn in METAMORPHIC.items():
        new, why = fn(brief, pl, random.Random((path, name).__str__()))
        if new is None:
            continue
        rows.append({**base, "kind": "metamorphic", "transform": name, "detail": why,
                     **record(brief, new, ref=(pl, ref_ok, ref_scores))})
    for name, fn in FAULTS.items():
        new, why = fn(brief, pl, random.Random((path, name).__str__()))
        if new is None:
            continue
        rows.append({**base, "kind": FAULT_KIND[name], "transform": name, "detail": why,
                     **record(brief, new)})
    return rows


# ----------------------------------------------------------------------------- parent side

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--placements", required=True)
    ap.add_argument("--faults", default="bench/paper/e1_faults.csv")
    ap.add_argument("--metamorphic", default="bench/paper/e1b_metamorphic.csv")
    ap.add_argument("--seeds", nargs="*", type=int, default=[0, 1])
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--resume", action="store_true")
    args = ap.parse_args()

    jobs = []
    for p in sorted(Path(args.placements).rglob("*.json")):
        meta = json.loads(p.read_text())
        if meta.get("seed") in args.seeds and meta.get("verified"):
            jobs.append((meta["fixture"], meta, str(p)))

    f_path, m_path = Path(args.faults), Path(args.metamorphic)
    done = set()
    if args.resume:
        for path in (f_path, m_path):
            if path.exists():
                with path.open() as f:
                    done |= {r["file"] for r in csv.DictReader(f)}
        jobs = [j for j in jobs if j[2] not in done]

    cols_m = COLUMNS + ["verdict_unchanged"]
    new_f, new_m = not f_path.exists(), not m_path.exists()
    f_path.parent.mkdir(parents=True, exist_ok=True)
    with f_path.open("a", newline="") as ff, m_path.open("a", newline="") as mf:
        fw = csv.DictWriter(ff, fieldnames=COLUMNS)
        mw = csv.DictWriter(mf, fieldnames=cols_m)
        if new_f:
            fw.writeheader()
        if new_m:
            mw.writeheader()
        t0 = time.time()
        n = 0
        with ProcessPoolExecutor(max_workers=args.workers) as ex:
            futs = {ex.submit(work, fx, meta, path): path for fx, meta, path in jobs}
            for fut in as_completed(futs):
                for row in fut.result():
                    if row["kind"] == "metamorphic":
                        mw.writerow({k: row.get(k, "") for k in cols_m})
                    else:
                        fw.writerow({k: row.get(k, "") for k in COLUMNS})
                ff.flush(); mf.flush()
                n += 1
                print(f"{n}/{len(jobs)} {futs[fut]} ({time.time() - t0:.0f}s)", flush=True)
    print(f"done: {n} placements in {time.time() - t0:.0f}s -> {f_path}, {m_path}")


if __name__ == "__main__":
    main()
