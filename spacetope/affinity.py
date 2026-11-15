"""M19 affinity: wishes that relate a space to another space, a group of spaces or the site (PLAN §4.10).

`expand(brief)` turns what the architect wrote (per-space entries, top-level entries, tag rules and the legacy
`wishes.exterior`) into a flat, deterministic list of `Affinity`; `validate(brief)` reports malformed entries in
plain language; `measure(brief, placement)` judges every affinity on integer boxes. Pure Python, no kernel.
"""
from __future__ import annotations

import dataclasses
import math
from dataclasses import dataclass

import networkx as nx

from .brief import Brief, generated_names
from .circulation import Problem
from .doors import access_graph, door_graph, plan_doors
from .levels import level_height_mm
from .solve.grid import Box, contact_area, overlap_len, touches
from .units import to_mm

PAIR_KINDS = ("touch", "near", "apart", "stack", "same_level")
SITE_KINDS = ("facade", "exterior", "ground", "top")
KINDS = PAIR_KINDS + SITE_KINDS
STRENGTHS = ("must", "should", "avoid", "never")
HARD = ("must", "never")
NEGATIVE = ("avoid", "never")
RULES = ("stack", "cluster", "same_level", "apart", "near")
SIDES = {"N": "+y", "E": "+x", "S": "-y", "W": "-x"}   # the box side of each compass side when the site north is 0
BEARING = {"+y": 0, "+x": 90, "-y": 180, "-x": 270}     # box side -> degrees clockwise from plan +y
COMPASS = {"N": 0, "E": 90, "S": 180, "W": 270}
SITE_KEYS = ("north", "hemisphere")
HSIDES = ("+x", "-x", "+y", "-y")
ALL_SIDES = HSIDES + ("ceiling", "floor")
DEFAULTS = {"touch": {"min": 0.9}, "near": {"depth": 2}, "stack": {"overlap": 0.5},
            "facade": {"min": 1.0}, "exterior": {"min": 1.0}}
RULE_PARAMS = {"stack": {"overlap": 0.5}, "near": {"depth": 2}, "cluster": {"min": 0.001}}
LOWER_BETTER = ("apart", "near", "same_level")
SLP = {"A": ("must", None), "E": ("should", 4), "I": ("should", 2), "O": ("should", 1), "X": ("avoid", None)}


def slp(letter: str) -> tuple[str, int | None] | None:
    """Muther's SLP closeness letter as (strength, weight); U (unimportant) is no affinity at all."""
    return SLP.get(str(letter).upper())


@dataclass(frozen=True)
class Affinity:
    """One wish. `others` is empty for site kinds, one name for a pair and several for a group, which is met
    when any of them satisfies the predicate. `source` names the written entry it came from."""
    kind: str
    a: str
    others: tuple[str, ...]
    strength: str
    weight: float
    params: dict
    source: str


class _Bad(Exception):
    def __init__(self, code: str, message: str):
        self.code, self.message = code, message


def refs(entry) -> list[str]:
    """Space names a written entry points at (its target or `between`), for pruning when spaces go away."""
    if not isinstance(entry, dict):
        return []
    out = [entry[k] for k in PAIR_KINDS if isinstance(entry.get(k), str)]
    if isinstance(entry.get("between"), (list, tuple)):
        out += [n for n in entry["between"] if isinstance(n, str)]
    return out


def prune(brief: Brief, known: set[str]) -> Brief:
    """The brief without affinity entries that name a space outside `known`."""
    ok = lambda e: all(n in known for n in refs(e))
    spaces = [dataclasses.replace(s, affinities=tuple(e for e in s.affinities if ok(e))) if s.affinities else s
              for s in brief.spaces]
    return dataclasses.replace(brief, spaces=spaces, affinities=[e for e in brief.affinities if ok(e)])


# ----------------------------------------------------------------------------- reading what was written

_WANT = {"min": "a length in metres, 0 or more", "depth": "a whole number of doors, 1 or more",
         "overlap": "a share above 0 and up to 1"}
_OK = {"min": lambda v: v >= 0, "depth": lambda v: v >= 1 and float(v).is_integer(), "overlap": lambda v: 0 < v <= 1}


def _number(source: str, key: str, v) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not _OK[key](v):
        raise _Bad("affinity_entry", f"{source}: {key} must be {_WANT[key]}, got {v!r}")
    return v


def _common(entry: dict, source: str, extra: set[str]) -> tuple[str, float]:
    for k in entry:
        if k not in extra | {"strength", "weight"}:
            raise _Bad("affinity_entry", f"{source}: unknown key {k!r}")
    strength = entry.get("strength", "should")
    if strength not in STRENGTHS:
        raise _Bad("affinity_strength", f"{source}: strength {strength!r} is not one of {', '.join(STRENGTHS)}")
    weight = entry.get("weight", 1)
    if isinstance(weight, bool) or not isinstance(weight, (int, float)) or weight <= 0:
        raise _Bad("affinity_entry", f"{source}: weight must be a number above 0, got {weight!r}")
    return strength, weight


def _params(entry: dict, source: str, defaults: dict) -> dict:
    return {k: _number(source, k, entry[k]) if k in entry else v for k, v in defaults.items()}


def _name(source: str, v, known: set[str]) -> str:
    if not isinstance(v, str) or v not in known:
        raise _Bad("affinity_space", f"{source}: {v!r} is not a space in this brief")
    return v


def _space_entry(owner: str, entry, known: set[str]) -> Affinity:
    if not isinstance(entry, dict):
        raise _Bad("affinity_entry", f"{owner}: affinity {entry!r} must be a mapping such as {{facade: S}}")
    kinds = [k for k in entry if k in KINDS]
    if len(kinds) != 1:
        raise _Bad("affinity_kind", f"{owner}: affinity {dict(entry)!r} needs exactly one kind of {', '.join(KINDS)}"
                   if kinds else f"{owner}: affinity {dict(entry)!r} has an unknown kind; use one of {', '.join(KINDS)}")
    kind = kinds[0]
    v = entry[kind]
    source = f"{owner}: {kind}" + ("" if v is True else f" {v}")
    strength, weight = _common(entry, source, {kind} | set(DEFAULTS.get(kind, {})))
    params = _params(entry, source, DEFAULTS.get(kind, {}))
    if kind in PAIR_KINDS:
        other = _name(source, v, known)
        if other == owner:
            raise _Bad("affinity_self", f"{source}: a space cannot have an affinity with itself")
        return Affinity(kind, owner, (other,), strength, weight, params, source)
    if kind == "facade":
        if v != "sun" and v not in SIDES:
            raise _Bad("affinity_side", f"{source}: side {v!r} is not one of {', '.join(SIDES)} or sun")
        params = {"side": v, **params}
    elif v is not True:
        raise _Bad("affinity_entry", f"{source}: write {kind}: true")
    return Affinity(kind, owner, (), strength, weight, params, source)


def _tags(entry: dict, key: str, count: int, source: str) -> list[str]:
    v = entry.get(key)
    ok = isinstance(v, str) if count == 1 else (isinstance(v, (list, tuple)) and len(v) == count and all(isinstance(t, str) for t in v))
    if not ok:
        raise _Bad("affinity_entry", f"{source}: {key} must be " + ("one tag name" if count == 1 else f"a list of {count} tag names"))
    return [v] if count == 1 else list(v)


def _top_entry(entry, known: set[str], by_tag: dict[str, list[str]], problems: list[Problem]) -> list[Affinity]:
    if not isinstance(entry, dict):
        raise _Bad("affinity_entry", f"affinity {entry!r} must be a mapping such as {{between: [a, b], kind: near}}")
    if "rule" in entry:
        return _rule(entry, by_tag, problems)
    if "between" not in entry:
        raise _Bad("affinity_entry", f"affinity {dict(entry)!r} needs between and kind, or tag/tags and rule")
    pair = entry["between"]
    source = f"between {pair}"
    if not (isinstance(pair, (list, tuple)) and len(pair) == 2):
        raise _Bad("affinity_entry", f"{source}: between must list exactly two space names")
    a, b = _name(source, pair[0], known), _name(source, pair[1], known)
    source = f"between {a}, {b}"
    kind = entry.get("kind")
    if kind not in KINDS:
        raise _Bad("affinity_kind", f"{source}: kind {kind!r} is not one of {', '.join(PAIR_KINDS)}")
    if kind not in PAIR_KINDS:
        raise _Bad("affinity_kind", f"{source}: {kind} relates a space to the site; write it on the space itself")
    source += f": {kind}"
    if a == b:
        raise _Bad("affinity_self", f"{source}: a space cannot have an affinity with itself")
    strength, weight = _common(entry, source, {"between", "kind"} | set(DEFAULTS.get(kind, {})))
    return [Affinity(kind, a, (b,), strength, weight, _params(entry, source, DEFAULTS.get(kind, {})), source)]


def _rule(entry: dict, by_tag: dict[str, list[str]], problems: list[Problem]) -> list[Affinity]:
    rule = entry["rule"]
    if rule not in RULES:
        raise _Bad("affinity_rule", f"affinity {dict(entry)!r}: rule {rule!r} is not one of {', '.join(RULES)}")
    pairs = rule == "near" or (rule == "apart" and "tags" in entry)
    groups = _tags(entry, "tags" if pairs else "tag", 2 if pairs else 1, f"affinity {dict(entry)!r}")
    source = ("tags " + ", ".join(groups) if len(groups) == 2 else f"tag {groups[0]}") + f": {rule}"
    strength, weight = _common(entry, source, {"rule", "tag", "tags"} | set(RULE_PARAMS.get(rule, {})))
    params = _params(entry, source, RULE_PARAMS.get(rule, {}))
    for t in groups:
        if t not in by_tag:
            problems.append(Problem("affinity_tag", f"{source}: no space carries the tag {t!r}, so the rule does nothing", "warning"))
    mk = lambda kind, a, others, p=params: Affinity(kind, a, tuple(others), strength, weight, dict(p), source)
    A = by_tag.get(groups[0], [])
    out: list[Affinity] = []
    if rule in ("stack", "cluster"):
        kind = "stack" if rule == "stack" else "touch"
        out = [mk(kind, a, [o for o in A if o != a]) for a in A if len(A) > 1]
    elif rule == "same_level":
        out = [mk("same_level", a, [A[0]], {}) for a in A[1:]]
    elif rule == "near":
        B = by_tag.get(groups[1], [])
        out = [mk("near", a, [o for o in B if o != a]) for a in A if any(o != a for o in B)]
    elif len(groups) == 2:
        seen: set = set()
        for a in A:
            for b in by_tag.get(groups[1], []):
                if a != b and frozenset((a, b)) not in seen:
                    seen.add(frozenset((a, b)))
                    out.append(mk("apart", a, [b], {}))
    else:
        out = [mk("apart", a, [b], {}) for i, a in enumerate(A) for b in A[i + 1:]]
    return out


def _conflicts(brief: Brief, affs: list[Affinity]) -> list[Problem]:
    """A hard 'apart' (or 'never touch') on a pair that also has a required contact can never be met."""
    required = brief.required_pairs()
    out, seen = [], set()
    for af in affs:
        if af.strength not in HARD or len(af.others) != 1 or frozenset((af.a, af.others[0])) not in required:
            continue
        if (af.kind == "apart" and af.strength == "must") or (af.kind == "touch" and af.strength == "never"):
            pair = frozenset((af.a, af.others[0]))
            if (pair, af.kind) in seen:
                continue
            seen.add((pair, af.kind))
            wish = "must stay apart from" if af.kind == "apart" else "must never touch"
            out.append(Problem("affinity_conflict", f"{af.source}: {af.a} {wish} {af.others[0]}, but the brief also requires "
                               f"them to touch (contacts); drop one of the two"))
    return out


def _parse(brief: Brief) -> tuple[list[Affinity], list[Problem]]:
    known = {s.name for s in brief.spaces} | set(generated_names(brief))
    by_tag: dict[str, list[str]] = {}
    for s in brief.spaces:
        for t in s.tags:
            by_tag.setdefault(t, []).append(s.name)
    out: list[Affinity] = []
    problems: list[Problem] = []
    explicit_exterior: set[str] = set()
    for s in brief.spaces:
        for e in s.affinities:
            try:
                out.append(_space_entry(s.name, e, known))
                if out[-1].kind == "exterior":
                    explicit_exterior.add(s.name)
            except _Bad as bad:
                problems.append(Problem(bad.code, bad.message))
    for e in brief.affinities:
        try:
            out += _top_entry(e, known, by_tag, problems)
        except _Bad as bad:
            problems.append(Problem(bad.code, bad.message))
    for s in brief.spaces:
        if s.wishes.get("exterior") and s.name not in explicit_exterior:
            out.append(Affinity("exterior", s.name, (), "should", 1, dict(DEFAULTS["exterior"]), "wishes.exterior"))
    problems += _conflicts(brief, out)
    return out, problems


def expand(brief: Brief) -> list[Affinity]:
    """Every affinity the brief asks for, in a stable order: per-space entries in space order, top-level entries as
    written, then the legacy `wishes.exterior`. Malformed entries are skipped (`validate` says why)."""
    return _parse(brief)[0]


def validate(brief: Brief) -> list[Problem]:
    """Plain-language problems with the written affinities: one error per bad entry, a warning for a tag rule
    whose tag no space carries."""
    return _parse(brief)[1]


# ----------------------------------------------------------------------------- the site (M21)

def site_of(brief: Brief) -> tuple[float, str]:
    """(north, hemisphere) of the brief's `site`, with the defaults 0 and N; unreadable values fall back too."""
    site = brief.site if isinstance(brief.site, dict) else {}
    north = site.get("north", 0)
    ok = isinstance(north, (int, float)) and not isinstance(north, bool) and math.isfinite(north)
    return (float(north) % 360 if ok else 0.0), ("S" if site.get("hemisphere") == "S" else "N")


def validate_site(brief: Brief) -> list[Problem]:
    """One plain error per bad part of `site`: an unknown key, a north that is not a number, a hemisphere not N or S."""
    site = brief.site
    if site is None:
        return []
    if not isinstance(site, dict):
        return [Problem("site_key", f"site must be a mapping such as {{north: 30, hemisphere: N}}, got {site!r}")]
    out = [Problem("site_key", f"site: unknown key {k!r}; use north and hemisphere") for k in site if k not in SITE_KEYS]
    north = site.get("north", 0)
    if isinstance(north, bool) or not isinstance(north, (int, float)) or not math.isfinite(north):
        out.append(Problem("site_north", f"site: north must be a number of degrees clockwise from plan +y, got {north!r}"))
    if site.get("hemisphere", "N") not in ("N", "S"):
        out.append(Problem("site_hemisphere", f"site: hemisphere must be N or S, got {site['hemisphere']!r}"))
    return out


def compass_faces(side: str, north: float = 0.0, hemisphere: str = "N") -> list[str]:
    """The box sides whose outward normal is within 45 degrees of a compass side (N, E, S, W or sun), given the angle
    of true north clockwise from plan +y. At exactly 45 degrees two sides tie and either meets the wish. `sun` is the
    side facing the equator: S in the northern hemisphere, N in the southern (orientation only, PLAN §4.10 M21)."""
    if side == "sun":
        side = "N" if hemisphere == "S" else "S"
    bearing = (north + COMPASS[side]) % 360
    return [b for b in HSIDES if round(min((BEARING[b] - bearing) % 360, (bearing - BEARING[b]) % 360), 9) <= 45]


# ----------------------------------------------------------------------------- measuring

def _levels(b: Box, H: int) -> tuple[int, int]:
    return b.z // H, (b.z1 - 1) // H


def _metres(mm: int) -> float:
    return round(mm / 1000, 6)


def _uncovered(name: str, b: Box, placement: dict[str, Box]) -> dict[str, int]:
    """Wall length per horizontal side not covered by a full-height neighbour (the reading `daylight` uses)."""
    out = {}
    for side in HSIDES:
        length = b.l if side in ("+x", "-x") else b.w
        covered = 0
        for m, o in placement.items():
            if m != name:
                u, v = touches(b, o, side)
                if u > 0 and v >= b.h:
                    covered += u
        out[side] = max(0, length - covered)
    return out


def measure(brief: Brief, placement: dict[str, Box], *, strengths: tuple[str, ...] | None = None,
            kinds: tuple[str, ...] | None = None) -> dict:
    """Judge every affinity of `brief` on `placement`. `met` always means the wish is satisfied (so for `never`
    and `avoid` it is the predicate's negation); a space missing from the placement leaves the item unmeasured.
    `strengths` and `kinds` restrict the judged affinities (`HARD` for the cheap hard check, `("facade",)` for the
    orientation pass); the tallies then cover those only."""
    H = level_height_mm(brief)
    cache: dict = {}
    north, hemi = site_of(brief)
    top = max((_levels(b, H)[1] for b in placement.values()), default=0)

    def walk() -> nx.Graph:
        if "g" not in cache:
            cache["g"] = (door_graph(brief, plan_doors(brief, placement)[0], placement) if brief.circulation
                          else access_graph(brief, placement))
        return cache["g"]

    def pair(af: Affinity, a: str, o: str):
        """(satisfied, value, target, unit) for one partner, or None when it cannot be judged."""
        A, B = placement[a], placement[o]
        p = af.params
        if af.kind == "touch":
            u = max(touches(A, B, s)[0] for s in HSIDES)
            return u >= to_mm(p["min"]) and u > 0, _metres(u), p["min"], "m"
        if af.kind == "apart":
            area = sum(contact_area(A, B, s) for s in ALL_SIDES)
            return area == 0, round(area / 1e6, 6), 0, "m2"
        if af.kind == "near":
            g = walk()
            if a not in g or o not in g or not nx.has_path(g, a, o):
                return (False, None, p["depth"], "doors") if a in g and o in g else None
            d = nx.shortest_path_length(g, a, o)
            return d <= p["depth"], d, p["depth"], "doors"
        if af.kind == "stack":
            adjacent = A.z1 == B.z or B.z1 == A.z
            area = overlap_len(A.interval("x"), B.interval("x")) * overlap_len(A.interval("y"), B.interval("y"))
            share = area / min(A.w * A.l, B.w * B.l) if adjacent else 0.0
            return adjacent and share >= p["overlap"] - 1e-9, round(share, 6), p["overlap"], "share"
        (a0, a1), (b0, b1) = _levels(A, H), _levels(B, H)
        gap = max(a0 - b1, b0 - a1, 0)
        return gap == 0, gap, 0, "levels"

    def site(af: Affinity, a: str):
        b = placement[a]
        p = af.params
        if af.kind in ("facade", "exterior"):
            sides = _uncovered(a, b, placement)
            u = max(sides[f] for f in compass_faces(p["side"], north, hemi)) if af.kind == "facade" else max(sides.values())
            return u >= to_mm(p["min"]) and u > 0, _metres(u), p["min"], "m"
        lv = _levels(b, H)
        if af.kind == "ground":
            return b.z == 0, lv[0], 0, "level"
        return lv[1] == top, lv[1], top, "level"

    items = []
    for af in expand(brief):
        if (strengths is not None and af.strength not in strengths) or (kinds is not None and af.kind not in kinds):
            continue
        item = {"kind": af.kind, "a": af.a, "others": list(af.others), "strength": af.strength, "weight": af.weight,
                "met": None, "value": None, "target": None, "unit": None, "by": None, "source": af.source}
        if af.kind == "facade":
            item.update(side=af.params["side"], faces=compass_faces(af.params["side"], north, hemi))
        if af.a in placement:
            if af.kind in PAIR_KINDS:
                parts = [(o, r) for o in af.others if o in placement for r in [pair(af, af.a, o)] if r is not None]
            else:
                r = site(af, af.a)
                parts = [(None, r)] if r is not None else []
            if parts:
                low = af.kind in LOWER_BETTER
                best = lambda ps: min(ps, key=lambda t: (t[1][1] is None, 0 if t[1][1] is None else (t[1][1] if low else -t[1][1])))
                hits = [t for t in parts if t[1][0]]
                o, (ok, value, target, unit) = best(hits or parts)
                neg = af.strength in NEGATIVE
                item.update(met=(not bool(hits)) if neg else bool(hits), value=value, target=target, unit=unit)
                if o is not None and (hits or not neg) and (hits or value is not None):
                    item["by"] = o
                if neg and not hits:
                    item["by"] = None
        items.append(item)

    def tally(hard: bool) -> dict:
        its = [i for i in items if i["met"] is not None and (i["strength"] in HARD) == hard]
        return {"met": sum(1 for i in its if i["met"]), "total": len(its)}

    soft = [i for i in items if i["met"] is not None and i["strength"] not in HARD]
    wsum = sum(i["weight"] for i in soft)
    score = round(sum(i["weight"] for i in soft if i["met"]) / wsum, 6) if wsum else 1.0
    report = {"score": score, "soft": tally(False), "hard": tally(True),
              "unmeasured": sum(1 for i in items if i["met"] is None), "items": items}
    if brief.site is not None:
        report["site"] = {"north": north, "hemisphere": hemi}
    return report


# ----------------------------------------------------------------------------- what the generators and checks use

SEARCH_KINDS = ("touch", "apart", "stack", "same_level")   # the kinds a search can judge on a partial placement


def written(brief: Brief) -> bool:
    """True when the brief carries any per-space or top-level affinity entry (a cheap guard before `expand`)."""
    return bool(brief.affinities) or any(s.affinities for s in brief.spaces)


def search_items(brief: Brief) -> list[Affinity]:
    """The affinities a search can score: kinds `touch`, `apart`, `stack`, `same_level`, with at least one partner.
    `exterior`, `facade`, `near`, `ground` and `top` need the finished plan and are left to the check and the ranking."""
    return [a for a in expand(brief) if a.kind in SEARCH_KINDS and a.others] if written(brief) else []


def holds(kind: str, params: dict, A: Box, B: Box, H: int) -> bool:
    """The predicate of a search kind on two boxes: the same reading as `measure`, without the detail."""
    if kind in ("touch", "apart"):
        gap = A.x1 < B.x or B.x1 < A.x or A.y1 < B.y or B.y1 < A.y or A.z1 < B.z or B.z1 < A.z   # no shared face possible
        if kind == "apart":
            return gap or not any(contact_area(A, B, s) for s in ALL_SIDES)
        if gap or A.z1 <= B.z or B.z1 <= A.z:
            return False
        u = max(touches(A, B, s)[0] for s in HSIDES)
        return u > 0 and u >= to_mm(params["min"])
    if kind == "stack":
        if A.z1 != B.z and B.z1 != A.z:
            return False
        area = overlap_len(A.interval("x"), B.interval("x")) * overlap_len(A.interval("y"), B.interval("y"))
        return area / min(A.w * A.l, B.w * B.l) >= params["overlap"] - 1e-9
    (a0, a1), (b0, b1) = _levels(A, H), _levels(B, H)
    return max(a0 - b1, b0 - a1, 0) == 0


def has_hard(brief: Brief) -> bool:
    return written(brief) and any(a.strength in HARD for a in expand(brief))


def level_rules(brief: Brief) -> dict:
    """What `must` affinities say about levels: names that must be on the ground level or the top level, and the
    pairs that must share a level (for `levels.assign_levels`)."""
    out = {"ground": [], "top": [], "same": []}
    if not written(brief):
        return out
    for a in expand(brief):
        if a.strength != "must":
            continue
        if a.kind in ("ground", "top"):
            out[a.kind].append(a.a)
        elif a.kind == "same_level":
            out["same"] += [(a.a, o) for o in a.others]
    return out


_VERB = {"touch": "share a wall with", "near": "be within {target} doors of", "apart": "have no wall, floor or ceiling in common with",
         "stack": "sit over or under", "same_level": "be on the same level as"}
_SITE = {"exterior": "have an outside wall", "ground": "be on the ground level", "top": "be on the top level"}


def describe(item: dict) -> str:
    """One plain line for a `must`/`never` item that was not met."""
    kind, a = item["kind"], item["a"]
    if kind in _VERB:
        verb = _VERB[kind].format(target=item["target"]) + " " + " or ".join(item["others"])
    elif kind == "facade":
        side = item.get("side") or item["source"].split()[-1]
        verb = "have an outside wall that faces the equator" if side == "sun" else f"have an outside wall facing {side}"
    else:
        verb = _SITE[kind]
    line = f"{a} must never {verb}" if item["strength"] == "never" else f"{a} must {verb}"
    return line + (f" (measured {item['value']} {item['unit']})" if item["value"] is not None else "")


def hard_misses(brief: Brief, placement: dict[str, Box]) -> list[str]:
    """Plain-language lines for every `must`/`never` affinity that is judged and not met. Unmeasured items (a space
    not in the placement) do not count. Cheap enough to call per candidate."""
    if not written(brief):
        return []
    return [describe(i) for i in measure(brief, placement, strengths=HARD)["items"] if i["met"] is False]
