"""M7: expand a brief's compact circulation section into concrete spaces, and validate briefs before generation.

    corridor:  {w, l, segments?}              -> corridor_<k> on every level, or a chain corridor_<k>_1..N
                                                 when `segments` > 1 (an L or U spine); `l` is one segment
    stairs:    [{name, w, l, serves?}]        -> one stair space spanning its levels
    lifts:     [{name, w, l, serves?}]        -> one elevator space spanning its levels
    doors:     {room: {w, h}, stair: {w, h}, lift: {w, h}, jamb}

Plan: docs/2026-09-13_M7_vertical_circulation_plan.md (§3).
"""
from __future__ import annotations

from dataclasses import dataclass

from .brief import Brief, BriefError, Space, corridor_names, corridor_segments, generated_names

DEFAULT_DOORS = {"room": {"w": 0.9, "h": 2.1}, "stair": {"w": 1.0, "h": 2.1}, "lift": {"w": 1.1, "h": 2.1}, "jamb": 0.1}
HEAD_CLEARANCE = 0.3  # metres between the top of a door and the level's ceiling
SHAFT_KEYS = (("stairs", "stair"), ("lifts", "elevator"))


@dataclass(frozen=True)
class Problem:
    code: str
    message: str
    severity: str = "error"  # "error" blocks generation; "warning" is reported

    def to_dict(self) -> dict:
        return {"code": self.code, "message": self.message, "severity": self.severity}


class BriefInvalid(ValueError):
    def __init__(self, problems: list[Problem]):
        self.problems = problems
        super().__init__("; ".join(p.message for p in problems if p.severity == "error"))


def _fmt(x: float) -> str:
    return f"{x:g}"


def level_height_m(brief: Brief) -> float:
    """Level height in metres, always a whole number of millimetres (review 2026-09-13, #3)."""
    if brief.level_height:
        return round(float(brief.level_height), 3)
    floor_bound = [s.h for s in brief.spaces if not s.is_shaft]
    return round(max(floor_bound), 3) if floor_bound else 3.0


def door_spec(brief: Brief) -> dict:
    """Door sizes in metres, brief values over defaults."""
    given = (brief.circulation or {}).get("doors") or {}
    spec = {k: dict(v) for k, v in DEFAULT_DOORS.items() if isinstance(v, dict)}
    for kind in ("room", "stair", "lift"):
        spec[kind].update({k: float(v) for k, v in (given.get(kind) or {}).items()})
    spec["jamb"] = float(given.get("jamb", DEFAULT_DOORS["jamb"]))
    return spec


def door_kind(program: str) -> str:
    return {"stair": "stair", "elevator": "lift"}.get(program, "room")


def _span(item: dict, n: int) -> tuple[int, int]:
    serves = item.get("serves")
    if serves is None:
        return (0, n - 1)
    return (int(serves[0]), int(serves[1]))


# ----------------------------------------------------------------------------- validation (compact brief)

def validate_compact(brief: Brief) -> list[Problem]:
    problems: list[Problem] = []
    n = brief.levels or 1
    if not isinstance(n, int) or n < 1:
        return [Problem("levels", f"levels must be a whole number of at least 1, got {brief.levels!r}")]
    H = level_height_m(brief)
    circ = brief.circulation or {}

    if brief.envelope and "h" in brief.envelope and n * H > float(brief.envelope["h"]) + 1e-9:
        problems.append(Problem("envelope_height",
                                f"{n} levels × {_fmt(H)} m need {_fmt(n * H)} m; the envelope is {_fmt(float(brief.envelope['h']))} m tall"))

    if n > 1:
        legacy = [s.name for s in brief.spaces if s.is_vertical and s.serves is None]
        if legacy:
            problems.append(Problem("legacy_shafts",
                                    f"{', '.join(legacy)} look like stairs or lifts split by floor; "
                                    f"declare each once under circulation.stairs or circulation.lifts"))

    shafts: list[tuple[str, str, tuple[int, int], dict]] = []
    for key, program in SHAFT_KEYS:
        for item in circ.get(key) or []:
            name = str(item.get("name", "?"))
            lo, hi = _span(item, n)
            shafts.append((name, program, (lo, hi), item))
            noun = "stair" if program == "stair" else "lift"
            if lo > hi:
                problems.append(Problem("span_order", f"{name} serves levels {lo}–{hi}; the first level must not be above the last"))
            if lo < 0 or hi > n - 1:
                bad = hi if hi > n - 1 else lo
                problems.append(Problem("span_range", f"{name} serves level {bad}, the brief has levels 0–{n - 1}"))
            for dim in ("w", "l"):
                if float(item.get(dim, 0)) <= 0:
                    problems.append(Problem("shaft_size", f"{noun} {name} needs a positive {dim}"))

    if n > 1:
        for k in range(n):
            if not any(p == "stair" and lo <= k <= hi for _, p, (lo, hi), _ in shafts):
                problems.append(Problem("stair_coverage", f"level {k} is not served by any stair"))
        explicit_corridor_levels = {s.wishes.get("level") for s in brief.spaces if s.program == "corridor"}
        if not circ.get("corridor"):
            missing = [k for k in range(n) if k not in explicit_corridor_levels]
            if missing:
                problems.append(Problem("corridor_coverage",
                                        f"level{'s' if len(missing) > 1 else ''} {', '.join(map(str, missing))} "
                                        f"{'have' if len(missing) > 1 else 'has'} no corridor; add circulation.corridor"))

    if circ.get("corridor"):
        c = circ["corridor"]
        for dim in ("w", "l"):
            if float(c.get(dim, 0)) <= 0:
                problems.append(Problem("corridor_size", f"circulation.corridor needs a positive {dim}"))
        raw = c.get("segments", 1)
        try:
            segs = int(raw or 1)
        except (TypeError, ValueError):
            segs = 0
        if segs < 1 or segs > 6:
            problems.append(Problem("corridor_segments",
                                    f"circulation.corridor.segments must be a whole number from 1 to 6, got {raw!r}"))
        elif segs > 1:
            # M15b: a chained corridor has no single name a contact can point at, so access is judged by door
            spine = {f"corridor_{k}" for k in range(n)}
            used = sorted({f"{a} – {b}" for a, b in brief.contacts if a in spine or b in spine})
            if used:
                problems.append(Problem("corridor_chain",
                                        f"with {segs} corridor segments a room reaches the corridor by a door to "
                                        f"whichever segment it touches, so {len(used)} contact"
                                        f"{'s' if len(used) > 1 else ''} to the spine "
                                        f"({', '.join(used[:3])}{', …' if len(used) > 3 else ''}) "
                                        f"{'are' if len(used) > 1 else 'is'} dropped", "warning"))

    for s in brief.spaces:
        lv = s.wishes.get("level")
        if lv is not None and not (0 <= int(lv) <= n - 1):
            problems.append(Problem("room_level", f"{s.name} asks for level {lv}, the brief has levels 0–{n - 1}"))

    explicit = {s.name for s in brief.spaces}
    clash = sorted(explicit & set(generated_names(brief)))
    if clash:
        problems.append(Problem("name_clash", f"{', '.join(clash)} would be generated by circulation; rename the space"))

    # doors must fit their walls and the level height
    spec = door_spec(brief)
    jamb = spec["jamb"]
    for kind, d in (("room", spec["room"]), ("stair", spec["stair"]), ("lift", spec["lift"])):
        if d["h"] + HEAD_CLEARANCE > H + 1e-9:
            problems.append(Problem("door_height",
                                    f"{kind} door height {_fmt(d['h'])} m does not fit a {_fmt(H)} m level "
                                    f"with {_fmt(HEAD_CLEARANCE)} m head clearance"))
    for name, program, _, item in shafts:
        d = spec[door_kind(program)]
        need = d["w"] + 2 * jamb
        longest = max(float(item.get("w", 0)), float(item.get("l", 0)))
        if longest + 1e-9 < need:
            problems.append(Problem("door_width",
                                    f"{name} needs {_fmt(need)} m of wall for its door "
                                    f"({_fmt(d['w'])} m door + 2 × {_fmt(jamb)} m jambs); its longest side is {_fmt(longest)} m"))
    room_need = spec["room"]["w"] + 2 * jamb
    for s in brief.spaces:
        if s.program != "room":
            continue
        longest_mm = max(s.band("w")[1], s.band("l")[1])
        if longest_mm / 1000 + 1e-9 < room_need:
            problems.append(Problem("door_width",
                                    f"{s.name} needs {_fmt(room_need)} m of wall for its door; "
                                    f"its longest side is at most {_fmt(longest_mm / 1000)} m"))
    return problems


# ----------------------------------------------------------------------------- expansion

def expand(brief: Brief) -> Brief:
    """Concrete corridors and shafts from the circulation section. Idempotent; briefs without one pass through."""
    if brief.expanded or not brief.circulation:
        return brief
    n = brief.levels or 1
    H = level_height_m(brief)
    circ = brief.circulation
    spaces = list(brief.spaces)
    contacts = list(brief.contacts)
    doors = list(brief.door_pairs)
    corridor = circ.get("corridor")
    segments = corridor_segments(brief) if corridor else 1
    if corridor:
        for k in range(n):
            names_k = corridor_names(brief, k)
            for i, nm in enumerate(names_k):
                spaces.append(Space(name=nm, w=float(corridor["w"]), l=float(corridor["l"]), h=H,
                                    program="corridor", tol=corridor.get("tol"),
                                    wishes={"level": k, "generated": True, **({"segment": i + 1} if segments > 1 else {})}))
            for a, b in zip(names_k, names_k[1:]):
                contacts.append((a, b))        # consecutive segments meet: an opening the width of the corridor
    if segments > 1:
        # a contact to the spine cannot say which segment; the door rule (every room's door opens onto a corridor
        # on its level) carries the requirement instead, so those contacts and their doors go (M15b, PLAN §6)
        spine = {f"corridor_{k}" for k in range(n)}
        contacts = [(a, b) for a, b in contacts if a not in spine and b not in spine]
        doors = [(a, b) for a, b in doors if a not in spine and b not in spine]
    for key, program in SHAFT_KEYS:
        for item in circ.get(key) or []:
            lo, hi = _span(item, n)
            name = str(item["name"])
            spaces.append(Space(name=name, w=float(item["w"]), l=float(item["l"]),
                                h=round((hi - lo + 1) * round(H * 1000) / 1000, 3),  # exact multiple of the mm level height
                                program=program, tol=item.get("tol"), wishes={"generated": True}, serves=(lo, hi)))
            if corridor and segments == 1:
                for k in range(lo, hi + 1):
                    pair = (name, f"corridor_{k}")
                    if frozenset(pair) not in {frozenset(c) for c in contacts}:
                        contacts.append(pair)
                    doors.append(pair)
            # chained corridors: which segment a shaft lands on is the generator's choice; `doors.door_kind_for`
            # already requires a door wherever a shaft meets a corridor, and door planning places it (M15b)
    return Brief(name=brief.name, spaces=spaces, contacts=contacts, envelope=brief.envelope, levels=brief.levels,
                 level_height=H, circulation=circ, door_pairs=doors, expanded=True)


# ----------------------------------------------------------------------------- validation (expanded brief)

def space_level(s: Space) -> int | None:
    lv = s.wishes.get("level")
    return int(lv) if lv is not None else None


def validate_expanded(brief: Brief) -> list[Problem]:
    problems: list[Problem] = []
    n = brief.levels or 1
    by = brief.by_name
    known_levels: dict[int, float] = {k: 0.0 for k in range(n)}
    placed_somewhere = False
    for s in brief.spaces:
        if s.is_shaft:
            continue
        placed_somewhere = True
        lv = space_level(s)
        if lv is not None and 0 <= lv < n:
            known_levels[lv] += s.w * s.l
    if not placed_somewhere:
        problems.append(Problem("empty", "the brief has no floor-bound spaces"))
    if n > 1:
        # a level with no floor-bound space pinned to it can still receive unpinned rooms; only flag when nothing can go there
        unpinned = [s for s in brief.spaces if not s.is_shaft and space_level(s) is None]
        for k in range(n):
            pinned = any(space_level(s) == k for s in brief.spaces if not s.is_shaft)
            if not pinned and not unpinned:
                problems.append(Problem("empty_level", f"level {k} has no spaces"))

    for a, b in brief.contacts:
        sa, sb = by[a], by[b]
        if sa.is_shaft and sb.is_shaft:
            continue
        if sa.is_shaft or sb.is_shaft:
            shaft, other = (sa, sb) if sa.is_shaft else (sb, sa)
            lv = space_level(other)
            if lv is not None and not (shaft.serves[0] <= lv <= shaft.serves[1]):
                problems.append(Problem("contact_level",
                                        f"{shaft.name} does not serve level {lv}, so it cannot touch {other.name}"))
            continue
        la, lb = space_level(sa), space_level(sb)
        if la is not None and lb is not None and la != lb:
            problems.append(Problem("contact_level", f"{a} (level {la}) cannot touch {b} (level {lb})"))

    if brief.envelope and "w" in brief.envelope and "l" in brief.envelope:
        footprint = float(brief.envelope["w"]) * float(brief.envelope["l"])
        shaft_area = {k: sum(s.w * s.l for s in brief.spaces if s.is_shaft and s.serves[0] <= k <= s.serves[1]) for k in range(n)}
        for k in range(n):
            need = known_levels[k] + shaft_area[k]
            if need > footprint + 1e-9:
                problems.append(Problem("footprint",
                                        f"level {k} needs about {need:.0f} m², the footprint is {footprint:.0f} m²", "warning"))
    return problems


def prepare(brief: Brief) -> tuple[Brief, list[Problem]]:
    """Validate, expand, validate again. Raises BriefInvalid on any error; returns the expanded brief and warnings."""
    problems = validate_compact(brief)
    if any(p.severity == "error" for p in problems):
        raise BriefInvalid(problems)
    try:
        expanded = expand(brief)
    except BriefError as e:
        raise BriefInvalid(problems + [Problem("expansion", str(e))])
    problems += validate_expanded(expanded)
    if any(p.severity == "error" for p in problems):
        raise BriefInvalid(problems)
    return expanded, [p for p in problems if p.severity == "warning"]
