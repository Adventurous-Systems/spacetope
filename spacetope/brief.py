"""The architect's brief: spaces with nominal dimensions, tolerance bands, programs and wishes."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import yaml

from .units import to_mm

AXES = ("w", "l", "h")
PROGRAMS = ("room", "corridor", "stair", "elevator", "void")
CIRCULATION = ("corridor", "stair", "elevator")

# Default tolerance bands per program as (lo_frac, hi_frac) per axis.
# Corridors: fixed width, free length up to 3x nominal. Cores: fixed footprint.
DEFAULT_BANDS: dict[str, dict[str, tuple[float, float]]] = {
    "room": {"w": (-0.10, 0.10), "l": (-0.10, 0.10), "h": (0.0, 0.0)},
    "corridor": {"w": (0.0, 0.0), "l": (-0.5, 2.0), "h": (0.0, 0.0)},
    "stair": {"w": (0.0, 0.0), "l": (0.0, 0.0), "h": (0.0, 0.0)},
    "elevator": {"w": (0.0, 0.0), "l": (0.0, 0.0), "h": (0.0, 0.0)},
    "void": {"w": (-0.9, 3.0), "l": (-0.9, 3.0), "h": (0.0, 0.0)},
}


class BriefError(ValueError):
    pass


@dataclass(frozen=True)
class Space:
    name: str
    w: float
    l: float
    h: float
    program: str = "room"
    tol: float | dict[str, tuple[float, float]] | None = None
    wishes: dict[str, Any] = field(default_factory=dict)
    serves: tuple[int, int] | None = None   # stairs and lifts: inclusive range of levels the shaft spans (M7)

    def __post_init__(self) -> None:
        if self.program not in PROGRAMS:
            raise BriefError(f"{self.name}: unknown program {self.program!r}")
        for a in AXES:
            if getattr(self, a) <= 0:
                raise BriefError(f"{self.name}: {a} must be positive")

    def nominal(self, axis: str) -> float:
        return float(getattr(self, axis))

    def nominal_mm(self, axis: str) -> int:
        return to_mm(self.nominal(axis))

    def fractions(self, axis: str) -> tuple[float, float]:
        """(lo_frac, hi_frac) for an axis: explicit dict > symmetric float > program default."""
        if isinstance(self.tol, dict) and axis in self.tol:
            lo, hi = self.tol[axis]
            return float(lo), float(hi)
        if isinstance(self.tol, (int, float)):
            t = float(self.tol)
            if axis == "h":
                return (0.0, 0.0)
            return (-t, t)
        return DEFAULT_BANDS[self.program][axis]

    def band(self, axis: str) -> tuple[int, int]:
        """Integer-mm (lo, hi) inclusive band for an axis; lo <= nominal <= hi, lo >= 1."""
        n = self.nominal_mm(axis)
        lo_f, hi_f = self.fractions(axis)
        lo = max(1, int(round(n * (1 + lo_f))))
        hi = max(lo, int(round(n * (1 + hi_f))))
        if not (lo <= n <= hi):
            raise BriefError(f"{self.name}: band for {axis} does not contain the nominal")
        return lo, hi

    @property
    def is_circulation(self) -> bool:
        return self.program in CIRCULATION

    @property
    def is_vertical(self) -> bool:
        return self.program in ("stair", "elevator")

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"name": self.name, "w": self.w, "l": self.l, "h": self.h, "program": self.program}
        if self.tol is not None:
            d["tol"] = self.tol
        if self.wishes:
            d["wishes"] = dict(self.wishes)
        if self.serves is not None:
            d["serves"] = [int(self.serves[0]), int(self.serves[1])]
        return d

    @property
    def is_shaft(self) -> bool:
        return self.is_vertical and self.serves is not None


@dataclass
class Brief:
    name: str
    spaces: list[Space]
    contacts: list[tuple[str, str]] = field(default_factory=list)  # required contacts (a, b)
    envelope: dict[str, float] | None = None  # {"w","l","h"} metres, AABB from origin (M3)
    levels: int | None = None  # number of distinct z-bands (M3)
    level_height: float | None = None
    circulation: dict[str, Any] | None = None  # compact corridor/stairs/lifts/doors section (M7)
    door_pairs: list[tuple[str, str]] = field(default_factory=list)  # contacts explicitly marked {door: true}
    expanded: bool = False  # True once circulation has been expanded into concrete spaces

    def __post_init__(self) -> None:
        names = [s.name for s in self.spaces]
        if len(set(names)) != len(names):
            raise BriefError("duplicate space names")
        if self.envelope is not None:  # consumers index all three (review 2026-09-13, #2)
            missing = [k for k in ("w", "l", "h") if self.envelope.get(k) is None]
            if missing:
                raise BriefError(f"envelope needs w, l and h in metres; missing {', '.join(missing)}")
            self.envelope = {k: float(self.envelope[k]) for k in ("w", "l", "h")}
            if any(v <= 0 for v in self.envelope.values()):
                raise BriefError("envelope dimensions must be positive")
        if self.level_height is not None:  # whole millimetres, so metres and mm never disagree (review #3)
            self.level_height = round(float(self.level_height), 3)
            if self.level_height <= 0:
                raise BriefError("level_height must be positive")
        known = set(names) | (set() if self.expanded else set(generated_names(self)))
        norm: list[tuple[str, str]] = []
        for a, b in self.contacts:
            if a not in known or b not in known:
                raise BriefError(f"contact {a}-{b} references an unknown space")
            if a == b:
                raise BriefError(f"contact {a}-{a} is self-referential")
            norm.append((a, b))
        self.contacts = norm
        pairs = {frozenset(c) for c in norm}
        doors: list[tuple[str, str]] = []
        for a, b in self.door_pairs:
            if frozenset((a, b)) not in pairs:
                raise BriefError(f"door {a}-{b} has no matching contact")
            doors.append((a, b))
        self.door_pairs = doors

    @property
    def by_name(self) -> dict[str, Space]:
        return {s.name: s for s in self.spaces}

    def space(self, name: str) -> Space:
        return self.by_name[name]

    def required_pairs(self) -> set[frozenset[str]]:
        return {frozenset(p) for p in self.contacts}

    def marked_door_pairs(self) -> set[frozenset[str]]:
        return {frozenset(p) for p in self.door_pairs}

    # --- serialisation -----------------------------------------------------
    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Brief":
        spaces = []
        for s in d.get("spaces", []):
            s = dict(s)
            tol = s.get("tol")
            if isinstance(tol, dict):
                tol = {k: (float(v[0]), float(v[1])) for k, v in tol.items()}
            serves = s.get("serves")
            spaces.append(Space(name=str(s["name"]), w=float(s["w"]), l=float(s["l"]), h=float(s["h"]),
                                program=s.get("program", "room"), tol=tol, wishes=dict(s.get("wishes", {}) or {}),
                                serves=(int(serves[0]), int(serves[1])) if serves is not None else None))
        contacts, door_pairs = [], []
        for c in d.get("contacts", []):
            if len(c) not in (2, 3):
                raise BriefError(f"contact {c!r} must be [a, b] or [a, b, {{door: true}}]")
            a, b = str(c[0]), str(c[1])
            contacts.append((a, b))
            if len(c) == 3 and isinstance(c[2], dict) and c[2].get("door"):
                door_pairs.append((a, b))
        return cls(name=str(d.get("name", "brief")), spaces=spaces, contacts=contacts,
                   envelope=d.get("envelope"), levels=d.get("levels"), level_height=d.get("level_height"),
                   circulation=d.get("circulation"), door_pairs=door_pairs, expanded=bool(d.get("expanded", False)))

    @classmethod
    def from_path(cls, path: str | Path) -> "Brief":
        p = Path(path)
        text = p.read_text()
        data = json.loads(text) if p.suffix == ".json" else yaml.safe_load(text)
        return cls.from_dict(data)

    def to_dict(self) -> dict[str, Any]:
        doors = self.marked_door_pairs()
        d: dict[str, Any] = {"name": self.name, "spaces": [s.to_dict() for s in self.spaces],
                             "contacts": [list(c) + ([{"door": True}] if frozenset(c) in doors else []) for c in self.contacts]}
        if self.envelope:
            d["envelope"] = dict(self.envelope)
        if self.levels is not None:
            d["levels"] = self.levels
        if self.level_height is not None:
            d["level_height"] = self.level_height
        if self.circulation is not None:
            d["circulation"] = self.circulation
        if self.expanded:
            d["expanded"] = True
        return d

    def to_yaml(self) -> str:
        return yaml.safe_dump(self.to_dict(), sort_keys=False)


def corridor_segments(brief: "Brief") -> int:
    """How many boxes each level's corridor is made of (M15b). 1 = one straight corridor, the default."""
    c = (brief.circulation or {}).get("corridor") or {}
    try:
        return max(1, int(c.get("segments", 1) or 1))
    except (TypeError, ValueError):
        return 1


def corridor_names(brief: "Brief", level: int) -> list[str]:
    """The corridor spaces expansion creates on one level: `corridor_<k>`, or `corridor_<k>_1..N` when chained."""
    n = corridor_segments(brief)
    return [f"corridor_{level}"] if n == 1 else [f"corridor_{level}_{i + 1}" for i in range(n)]


def generated_names(brief: "Brief") -> list[str]:
    """Names that expanding `brief.circulation` will create (corridor_<k>, stairs, lifts). With chained corridors
    the spine name `corridor_<k>` stays accepted as an alias so briefs written for one corridor still load; the
    contacts that use it are dropped during expansion with a warning (M15b)."""
    circ = brief.circulation or {}
    n = int(brief.levels or 1)
    out: list[str] = []
    if circ.get("corridor"):
        for k in range(n):
            out.append(f"corridor_{k}")
            out += [nm for nm in corridor_names(brief, k) if nm != f"corridor_{k}"]
    for key in ("stairs", "lifts"):
        out += [str(item["name"]) for item in (circ.get(key) or []) if "name" in item]
    return out


def load(path: str | Path) -> Brief:
    return Brief.from_path(path)
