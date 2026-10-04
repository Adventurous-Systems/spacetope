"""Brief programmes: a family of buildings one can draw briefs from (PLAN M17).

A fixture is one building. A programme is the kind of building: "a secondary school has eighteen to
twenty-six classrooms, two or three science labs each with a shared prep room, a library and a canteen on the
ground floor, two stairs and a lift". `sample(programme, seed)` draws one brief from that description, and
`variations(brief, seed)` perturbs a brief that already exists. Both are pure and deterministic in the seed.

Three uses. A benchmark suite per building type instead of the handful of fixtures. Robustness sweeps, where a
variation asks "does this generator still work if every room grows 20 %". And the training data the learning
track needs, which is briefs by the thousand rather than by the dozen.

The format is documented in `docs/PROGRAMMES.md`. Pure Python: no topologicpy, no solver.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .brief import Brief, BriefError

PROGRAMMES = Path(__file__).resolve().parent.parent / "programmes"
FRONTAGE_LIMIT = 0.85       # a level needing more than this share of its corridor's two sides rarely builds (M15a)


class ProgrammeError(ValueError):
    """The programme file cannot be read, or asks for something that cannot be drawn."""


@dataclass(frozen=True)
class Frontage:
    """What one level asks of its corridor, against what the corridor can offer."""
    needed_mm: int
    available_mm: int

    @property
    def ratio(self) -> float:
        return self.needed_mm / self.available_mm if self.available_mm else float("inf")

    @property
    def tight(self) -> bool:
        return self.ratio > FRONTAGE_LIMIT


def load(name: str | Path) -> dict:
    """A programme by name (`office`) or by path."""
    path = Path(name)
    if not path.exists():
        path = PROGRAMMES / f"{name}.yaml"
    if not path.exists():
        raise ProgrammeError(f"no programme named {name!r}; looked in {PROGRAMMES}")
    data = yaml.safe_load(path.read_text())
    if not isinstance(data, dict) or "rooms" not in data:
        raise ProgrammeError(f"{path} is not a programme: it needs at least a `rooms` list")
    return data


def names() -> list[str]:
    return sorted(p.stem for p in PROGRAMMES.glob("*.yaml")) if PROGRAMMES.exists() else []


# ----------------------------------------------------------------------------- drawing one brief

def _count(spec: Any, rng: random.Random, default: int = 1) -> int:
    """`3`, or `[lo, hi]` drawn inclusively."""
    if spec is None:
        return default
    if isinstance(spec, (list, tuple)):
        return rng.randint(int(spec[0]), int(spec[1]))
    return int(spec)


def _levels_of(spec: Any, rng: random.Random) -> int:
    if isinstance(spec, dict):
        return rng.randint(int(spec.get("min", 1)), int(spec.get("max", spec.get("min", 1))))
    return _count(spec, rng, 1)


def _pick_level(where: Any, n_levels: int, rng: random.Random, level_load: dict[int, float], area: float) -> int:
    """`0`, `any`, `upper`, `ground`, or a list to choose from. Every room gets a level here rather than leaving it
    to the brief: a room can only be told to open off `corridor_<k>` once its k is known, and that contact is what
    makes a brief buildable (measured 2026-10-04). `any` goes to the emptiest level, so the floors stay balanced."""
    if where == "ground":
        pick = 0
    elif where == "upper":
        pick = min(level_load, key=lambda k: level_load[k]) if n_levels == 1 else min(
            (k for k in level_load if k > 0), key=lambda k: level_load[k])
    elif isinstance(where, (list, tuple)):
        allowed = [int(w) for w in where if int(w) < n_levels] or [0]
        pick = min(allowed, key=lambda k: level_load[k])
    elif where is None or where == "any":
        pick = min(level_load, key=lambda k: level_load[k])
    else:
        pick = min(int(where), n_levels - 1)
    level_load[pick] += area
    return pick


def _room(name: str, spec: dict, level: int | None, rng: random.Random, height: float, tol) -> dict:
    wishes: dict[str, Any] = {}
    if level is not None:
        wishes["level"] = int(level)
    p_ext = spec.get("exterior")
    if p_ext is not None and rng.random() < float(p_ext):
        wishes["exterior"] = True
    out = {"name": name, "w": float(spec["w"]), "l": float(spec["l"]), "h": float(spec.get("h", height)),
           "program": spec.get("program", "room")}
    if wishes:
        out["wishes"] = wishes
    if tol is not None:
        out["tol"] = tol
    return out


def _attach_chain(parent: str, spec: dict, counters: dict, spaces: list, contacts: list,
                  level: int | None, rng: random.Random, height: float, tol) -> None:
    """`attach` hangs a room off another and may chain further, which is what makes a wish graph rich."""
    counters[spec["type"]] = counters.get(spec["type"], 0) + 1
    name = f"{spec['type']}_{counters[spec['type']]:02d}"
    spaces.append(_room(name, spec, level, rng, height, tol))
    contacts.append([parent, name, {"door": True}] if spec.get("door", True) else [parent, name])
    child = spec.get("attach")
    if child:
        _attach_chain(name, child, counters, spaces, contacts, level, rng, height, tol)


def frontage(spaces: list[dict], n_levels: int, corridor_w: float, corridor_max_l: float) -> Frontage:
    """Metres of corridor wall the rooms of the busiest level want, narrow side on, against the two sides a
    corridor of `corridor_max_l` offers. The threshold that matters was measured in M15a, not guessed."""
    per_level: dict[int, int] = {}
    for s in spaces:
        k = int((s.get("wishes") or {}).get("level", 0))
        per_level[k] = per_level.get(k, 0) + int(round(min(float(s["w"]), float(s["l"])) * 1000))
    needed = max(per_level.values()) if per_level else 0
    return Frontage(needed, int(round(2 * corridor_max_l * 1000)))


def sample(programme: dict | str, seed: int = 0, name: str | None = None) -> tuple[Brief, Frontage]:
    """One brief drawn from a programme, with the frontage reading that says whether it will be hard to build."""
    prog = load(programme) if isinstance(programme, (str, Path)) else programme
    rng = random.Random(seed)
    n_levels = _levels_of(prog.get("levels", 1), rng)
    height = float(prog.get("level_height", 3.0))
    tol_spec = prog.get("tolerance") or {}
    room_tol = tol_spec.get("room")
    spaces: list[dict] = []
    contacts: list[list] = []
    counters: dict[str, int] = {}
    by_type: dict[str, list[str]] = {}
    level_load: dict[int, float] = {k: 0.0 for k in range(n_levels)}
    for spec in prog["rooms"]:
        if "type" not in spec or "w" not in spec or "l" not in spec:
            raise ProgrammeError(f"room entry needs type, w and l: {spec!r}")
        area = float(spec["w"]) * float(spec["l"])
        if "count_per_level" in spec:
            draws = [k for k in range(n_levels) for _ in range(_count(spec["count_per_level"], rng))]
            for k in draws:
                level_load[k] += area
        else:
            draws = [_pick_level(spec.get("level"), n_levels, rng, level_load, area) for _ in range(_count(spec.get("count"), rng))]
        for level in draws:
            counters[spec["type"]] = counters.get(spec["type"], 0) + 1
            nm = f"{spec['type']}_{counters[spec['type']]:02d}"
            spaces.append(_room(nm, spec, level, rng, height, room_tol))
            by_type.setdefault(spec["type"], []).append(nm)
            att = spec.get("attach")
            if att:
                for _ in range(_count(att.get("per"), rng)):
                    before = len(spaces)
                    _attach_chain(nm, att, counters, spaces, contacts, level, rng, height, room_tol)
                    for s in spaces[before:]:
                        by_type.setdefault(s["name"].rsplit("_", 1)[0], []).append(s["name"])
    if not spaces:
        raise ProgrammeError("the programme drew no rooms")
    # optional room-to-room wishes
    for link in prog.get("adjacency") or []:
        a_type, b_type = link["between"]
        for a in by_type.get(a_type, []):
            for b in by_type.get(b_type, []):
                if a >= b or rng.random() >= float(link.get("p", 0)):
                    continue
                la = (next(s for s in spaces if s["name"] == a).get("wishes") or {}).get("level")
                lb = (next(s for s in spaces if s["name"] == b).get("wishes") or {}).get("level")
                if la is not None and lb is not None and la != lb:
                    continue
                contacts.append([a, b, {"door": True}] if link.get("door") else [a, b])
    if prog.get("corridor_contacts", True):
        for s in spaces:
            k = int((s.get("wishes") or {}).get("level", 0))
            contacts.append([f"corridor_{k}", s["name"]])
    circ = dict(prog.get("circulation") or {})
    corridor = dict(circ.get("corridor") or {"w": 1.8, "l": 12})
    # the corridor is as long as the rooms of one level need, narrow side on, over its two sides
    per_level: dict[int, float] = {}
    for s in spaces:
        k = int((s.get("wishes") or {}).get("level", 0))
        per_level[k] = per_level.get(k, 0.0) + min(float(s["w"]), float(s["l"]))
    want = max(per_level.values()) / 2 if per_level else 10.0
    if corridor.get("l") in (None, "from_frontage"):
        corridor["l"] = round(max(6.0, want), 1)
    if "tol" not in corridor and isinstance(tol_spec.get("corridor"), dict) and "l" in tol_spec["corridor"]:
        corridor["tol"] = {"l": list(tol_spec["corridor"]["l"])}
    circ["corridor"] = corridor
    for key, kind in (("stairs", "stair"), ("lifts", "lift")):
        spec = circ.get(key)
        if isinstance(spec, dict):                 # {count, w, l} -> the list expansion wants
            circ[key] = [{"name": f"{kind}_{i + 1}" if _count(spec.get("count"), rng) > 1 else kind,
                          "w": float(spec["w"]), "l": float(spec["l"])}
                         for i in range(_count(spec.get("count"), rng))]
        elif spec is None and key == "stairs" and n_levels > 1:
            circ[key] = [{"name": "stair", "w": 3.0, "l": 5.5}]
    if n_levels == 1:
        circ.pop("stairs", None); circ.pop("lifts", None)
    circ_area = float(corridor["w"]) * float(corridor["l"])
    for key in ("stairs", "lifts"):
        circ_area += sum(float(it["w"]) * float(it["l"]) for it in (circ.get(key) or []))
    front = frontage(spaces, n_levels, float(corridor["w"]),
                     min(float(corridor["l"]) * 3, _envelope_side(prog, spaces, n_levels, circ_area)))
    d: dict[str, Any] = {"name": name or f"{prog.get('name', 'programme')}_{seed}", "levels": n_levels,
                         "level_height": height, "spaces": spaces, "contacts": contacts, "circulation": circ}
    env = _envelope(prog, spaces, n_levels, height, rng, circ_area)
    if env:
        d["envelope"] = env
    try:
        return Brief.from_dict(d), front
    except BriefError as e:
        raise ProgrammeError(f"programme {prog.get('name', '?')} seed {seed} drew an unreadable brief: {e}") from e


def _level_area(spaces: list[dict], n_levels: int, circulation: float = 0.0) -> float:
    """Floor area of the busiest level, counting what expansion will add. Leaving the corridor and the shafts out
    undersizes the envelope badly where they are a large share of a floor (housing: measured 2026-10-04)."""
    per: dict[int, float] = {}
    for s in spaces:
        k = int((s.get("wishes") or {}).get("level", 0))
        per[k] = per.get(k, 0.0) + float(s["w"]) * float(s["l"])
    return (max(per.values()) if per else 0.0) + circulation


def _envelope_side(prog: dict, spaces: list[dict], n_levels: int, circulation: float = 0.0) -> float:
    spec = prog.get("envelope")
    if not spec:
        return 1e6
    area = _level_area(spaces, n_levels, circulation) * float(_pair(spec.get("area_factor", 1.8))[1])
    aspect = float(_pair(spec.get("aspect", 2.0))[1])
    return (area * aspect) ** 0.5


def _pair(v: Any) -> tuple[float, float]:
    if isinstance(v, (list, tuple)):
        return float(v[0]), float(v[1])
    return float(v), float(v)


def _envelope(prog: dict, spaces: list[dict], n_levels: int, height: float, rng: random.Random,
              circulation: float = 0.0) -> dict | None:
    spec = prog.get("envelope")
    if not spec:
        return None
    lo, hi = _pair(spec.get("area_factor", 1.8))
    area = _level_area(spaces, n_levels, circulation) * rng.uniform(lo, hi)
    lo, hi = _pair(spec.get("aspect", 2.0))
    aspect = rng.uniform(lo, hi)
    w = (area * aspect) ** 0.5
    return {"w": round(w, 1), "l": round(area / w, 1), "h": round(n_levels * height, 3)}


# ----------------------------------------------------------------------------- perturbing one brief

VARIATIONS = ("scale", "widen", "narrow", "drop", "duplicate", "stretch_envelope", "undoor")


def variations(brief: Brief, seed: int = 0, kinds: tuple[str, ...] = VARIATIONS) -> dict[str, Brief]:
    """One perturbed brief per kind, for sweeps: which change breaks which generator. Kinds that cannot apply to
    this brief are left out rather than returned unchanged."""
    out: dict[str, Brief] = {}
    for kind in kinds:
        rng = random.Random(seed * 131 + VARIATIONS.index(kind))
        made = _variation(brief, kind, rng)
        if made is not None:
            out[kind] = made
    return out


def _variation(brief: Brief, kind: str, rng: random.Random) -> Brief | None:
    d = brief.to_dict()
    rooms = [s for s in d["spaces"] if s.get("program", "room") == "room"]
    if kind == "scale":
        f = rng.choice((0.8, 1.2))
        for s in d["spaces"]:
            if s.get("program", "room") == "room":
                s["w"], s["l"] = round(s["w"] * f, 3), round(s["l"] * f, 3)
    elif kind in ("widen", "narrow"):
        for s in d["spaces"]:
            if s.get("program", "room") == "room":
                s["tol"] = 0.2 if kind == "widen" else 0.02
    elif kind == "drop":
        if len(rooms) < 3:
            return None
        gone = rng.choice(rooms)["name"]
        d["spaces"] = [s for s in d["spaces"] if s["name"] != gone]
        d["contacts"] = [c for c in d["contacts"] if gone not in (c[0], c[1])]
    elif kind == "duplicate":
        if not rooms:
            return None
        src = dict(rng.choice(rooms))
        src["name"] = f"{src['name']}_copy"
        d["spaces"].append(src)
    elif kind == "stretch_envelope":
        if not d.get("envelope"):
            return None
        d["envelope"] = {**d["envelope"], "w": round(d["envelope"]["w"] * 1.25, 1),
                         "l": round(d["envelope"]["l"] / 1.1, 1)}
    elif kind == "undoor":
        marked = [c for c in d["contacts"] if len(c) == 3]
        if not marked:
            return None
        victim = rng.choice(marked)
        d["contacts"] = [c[:2] if c is victim else c for c in d["contacts"]]
    else:
        raise ProgrammeError(f"unknown variation {kind!r}")
    d["name"] = f"{brief.name}__{kind}"
    try:
        return Brief.from_dict(d)
    except BriefError:
        return None
