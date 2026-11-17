# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Adventurous Systems

"""SpaceGraphs (space node + six wall nodes) and the AssemblyGraph of contact edges.

Intent only: no coordinates. networkx.Graph with node attribute `kind` in {"space", "wall"} and
edge attribute `kind` in {"star", "contact"}. Wall node ids are "<space>.<side>".
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Iterator

import networkx as nx

from .brief import Brief, Space

SIDES = ("+x", "-x", "+y", "-y", "floor", "ceiling")
OPPOSITE = {"+x": "-x", "-x": "+x", "+y": "-y", "-y": "+y", "floor": "ceiling", "ceiling": "floor"}
NORMAL = {"+x": (1, 0, 0), "-x": (-1, 0, 0), "+y": (0, 1, 0), "-y": (0, -1, 0),
          "floor": (0, 0, -1), "ceiling": (0, 0, 1)}
# Which two space axes span a side's face (u, v) in mm terms.
SPAN = {"+x": ("l", "h"), "-x": ("l", "h"), "+y": ("w", "h"), "-y": ("w", "h"),
        "floor": ("w", "l"), "ceiling": ("w", "l")}
HORIZONTAL_SIDES = ("+x", "-x", "+y", "-y")
VERTICAL_SIDES = ("floor", "ceiling")


class AssemblyError(ValueError):
    pass


def wall_id(space: str, side: str) -> str:
    return f"{space}.{side}"


def split_wall_id(wid: str) -> tuple[str, str]:
    space, side = wid.rsplit(".", 1)
    return space, side


@dataclass(frozen=True, order=True)
class Contact:
    a: str
    side_a: str
    b: str
    side_b: str

    def canonical(self) -> "Contact":
        if (self.a, self.side_a) <= (self.b, self.side_b):
            return self
        return Contact(self.b, self.side_b, self.a, self.side_a)

    @property
    def pair(self) -> frozenset[str]:
        return frozenset((self.a, self.b))

    @property
    def is_vertical(self) -> bool:
        return self.side_a in VERTICAL_SIDES

    def to_list(self) -> list[str]:
        return [self.a, self.side_a, self.b, self.side_b]


class AssemblyGraph:
    """Union of per-space star graphs plus contact edges between wall nodes."""

    def __init__(self, brief: Brief):
        self.brief = brief
        self.g = nx.Graph()
        for s in brief.spaces:
            self._add_space(s)

    # --- construction -------------------------------------------------------
    def _add_space(self, s: Space) -> None:
        self.g.add_node(s.name, kind="space", program=s.program)
        for side in SIDES:
            u, v = SPAN[side]
            self.g.add_node(wall_id(s.name, side), kind="wall", space=s.name, side=side,
                            normal=NORMAL[side], span=(u, v),
                            extent_mm=(s.nominal_mm(u), s.nominal_mm(v)))
            self.g.add_edge(s.name, wall_id(s.name, side), kind="star")

    def add_contact(self, a: str, side_a: str, b: str, side_b: str) -> Contact:
        c = Contact(a, side_a, b, side_b).canonical()
        self._check(c)
        self.g.add_edge(wall_id(c.a, c.side_a), wall_id(c.b, c.side_b), kind="contact")
        return c

    def add_contacts(self, contacts: Iterable[tuple[str, str, str, str]]) -> None:
        for a, sa, b, sb in contacts:
            self.add_contact(a, sa, b, sb)

    def remove_contact(self, a: str, side_a: str, b: str, side_b: str) -> None:
        self.g.remove_edge(wall_id(a, side_a), wall_id(b, side_b))

    def _check(self, c: Contact) -> None:
        for name, side in ((c.a, c.side_a), (c.b, c.side_b)):
            if name not in self.brief.by_name:
                raise AssemblyError(f"unknown space {name!r}")
            if side not in SIDES:
                raise AssemblyError(f"unknown side {side!r}")
        if c.a == c.b:
            raise AssemblyError(f"{c.a}: a space cannot contact itself")
        if OPPOSITE[c.side_a] != c.side_b:
            raise AssemblyError(f"{c.a}.{c.side_a} and {c.b}.{c.side_b}: normals are not opposite")

    # --- queries ------------------------------------------------------------
    def spaces(self) -> list[str]:
        return [n for n, d in self.g.nodes(data=True) if d["kind"] == "space"]

    def walls(self, space: str | None = None) -> list[str]:
        return [n for n, d in self.g.nodes(data=True) if d["kind"] == "wall" and (space is None or d["space"] == space)]

    def contacts(self) -> list[Contact]:
        out = []
        for u, v, d in self.g.edges(data=True):
            if d["kind"] != "contact":
                continue
            a, sa = split_wall_id(u)
            b, sb = split_wall_id(v)
            out.append(Contact(a, sa, b, sb).canonical())
        return sorted(out)

    def contacts_of(self, space: str) -> list[Contact]:
        return [c for c in self.contacts() if space in (c.a, c.b)]

    def contact_pairs(self) -> set[frozenset[str]]:
        return {c.pair for c in self.contacts()}

    def wall_contacts(self, space: str, side: str) -> list[Contact]:
        return [c for c in self.contacts() if (c.a, c.side_a) == (space, side) or (c.b, c.side_b) == (space, side)]

    def free_walls(self, space: str) -> list[str]:
        return [s for s in SIDES if not self.wall_contacts(space, s)]

    def space_adjacency(self) -> nx.Graph:
        """Dual graph: one node per space, one edge per contact (any side)."""
        d = nx.Graph()
        d.add_nodes_from(self.spaces())
        for c in self.contacts():
            d.add_edge(c.a, c.b)
        return d

    def missing_required(self) -> set[frozenset[str]]:
        return self.brief.required_pairs() - self.contact_pairs()

    def validate(self) -> None:
        """Raise on structurally impossible intent (does not check geometry)."""
        for c in self.contacts():
            self._check(c)
        # A wall pair may only be contacted once; a floor may only sit on one ceiling per space pair.
        seen = set()
        for c in self.contacts():
            key = (c.a, c.side_a, c.b, c.side_b)
            if key in seen:
                raise AssemblyError(f"duplicate contact {key}")
            seen.add(key)

    # --- identity -------------------------------------------------------------
    def signature(self) -> tuple[tuple[str, str, str, str], ...]:
        """Sorted canonical contact tuples; equal iff the same relations hold."""
        return tuple((c.a, c.side_a, c.b, c.side_b) for c in self.contacts())

    # --- serialisation --------------------------------------------------------
    def to_dict(self) -> dict:
        return {"brief": self.brief.name, "contacts": [c.to_list() for c in self.contacts()]}

    @classmethod
    def from_dict(cls, brief: Brief, d: dict) -> "AssemblyGraph":
        ag = cls(brief)
        ag.add_contacts(tuple(c) for c in d.get("contacts", []))
        return ag

    def copy(self) -> "AssemblyGraph":
        ag = AssemblyGraph.__new__(AssemblyGraph)
        ag.brief = self.brief
        ag.g = self.g.copy()
        return ag

    def __iter__(self) -> Iterator[Contact]:
        return iter(self.contacts())

    def __len__(self) -> int:
        return len(self.contacts())
