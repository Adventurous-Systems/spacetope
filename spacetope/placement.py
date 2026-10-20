"""A placement assigns an integer-mm Box to every space. Intent can be derived from it."""
from __future__ import annotations

import json
from pathlib import Path

from .brief import Brief
from .solve.grid import Box, contact_area, intersects, overlap_len, OPPOSITE
from .spacegraph import AssemblyGraph, Contact, HORIZONTAL_SIDES, SIDES

Placement = dict[str, Box]


def load_placement(path: str | Path) -> Placement:
    d = json.loads(Path(path).read_text())
    return {name: Box.from_dict(b) for name, b in d["boxes"].items()}


def save_placement(placement: Placement, path: str | Path, brief_name: str = "") -> None:
    Path(path).write_text(json.dumps(
        {"brief": brief_name, "boxes": {n: b.to_dict() for n, b in placement.items()}}, indent=2))


def check_complete(brief: Brief, placement: Placement) -> None:
    missing = {s.name for s in brief.spaces} - set(placement)
    extra = set(placement) - {s.name for s in brief.spaces}
    if missing or extra:
        raise ValueError(f"placement/brief mismatch: missing={sorted(missing)} extra={sorted(extra)}")


def assembly_from_placement(brief: Brief, placement: Placement, min_area_mm2: int = 1) -> AssemblyGraph:
    """Every face-coincident pair with positive overlap becomes a contact edge (intent = geometry)."""
    check_complete(brief, placement)
    ag = AssemblyGraph(brief)
    names = list(placement)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            for side in SIDES:
                if contact_area(placement[a], placement[b], side) >= min_area_mm2:
                    ag.add_contact(a, side, b, OPPOSITE[side])
    return ag


def diagnose_contact(c: Contact, placement: Placement, gap_limit_mm: int = 100) -> str:
    """Why a contact is not realised in this placement: 'ok' | 'gap' | 'overlap' | 'missing'."""
    a, b = placement[c.a], placement[c.b]
    if contact_area(a, b, c.side_a) > 0:
        return "ok"
    if intersects(a, b):
        return "overlap"
    axis, ca = a.face_plane(c.side_a)
    _, cb = b.face_plane(c.side_b)
    in_plane = [ax for ax in "xyz" if ax != axis]
    lateral = all(overlap_len(a.interval(ax), b.interval(ax)) > 0 for ax in in_plane)
    if lateral and 0 < abs(ca - cb) <= gap_limit_mm:
        return "gap"
    return "missing"


def overlaps(placement: Placement) -> list[tuple[str, str]]:
    names = list(placement)
    return [(a, b) for i, a in enumerate(names) for b in names[i + 1:] if intersects(placement[a], placement[b])]


def space_graph(brief: Brief, placement: Placement):
    """Room-adjacency graph of a placement with a label per space = program + nominal size (orientation-free).
    Pure networkx + integer boxes; used to tell real topological variety from swaps of identical rooms (PLAN M9)."""
    import networkx as nx
    g = nx.Graph()
    for s in brief.spaces:
        if s.name in placement:
            g.add_node(s.name, kind=f"{s.program}:{min(s.w, s.l):g}x{max(s.w, s.l):g}x{s.h:g}")
    names = list(g.nodes)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            if any(contact_area(placement[a], placement[b], side) > 0 for side in ("+x", "-x", "+y", "-y", "ceiling", "floor")):
                g.add_edge(a, b)
    return g


_ROT = {"+x": "+y", "+y": "-x", "-x": "-y", "-y": "+x", "ceiling": "ceiling", "floor": "floor"}
_MIR = {"+x": "-x", "-x": "+x", "+y": "+y", "-y": "-y", "ceiling": "ceiling", "floor": "floor"}


def _symmetries() -> list[dict[str, str]]:
    """The eight symmetries of a plan (four rotations, each with or without a mirror) as side relabellings."""
    out = []
    for mirror in (False, True):
        cur = {s: (_MIR[s] if mirror else s) for s in _ROT}
        for _ in range(4):
            out.append(dict(cur))
            cur = {s: _ROT[v] for s, v in cur.items()}
    return out


def side_graph(brief: Brief, placement: Placement):
    """Directed graph of shared walls: a -> b carries the side of a that touches b. Node label = program + size."""
    import networkx as nx
    g = nx.DiGraph()
    for s in brief.spaces:
        if s.name in placement:
            g.add_node(s.name, kind=f"{s.program}:{min(s.w, s.l):g}x{max(s.w, s.l):g}x{s.h:g}")
    names = list(g.nodes)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            for side in SIDES:
                if contact_area(placement[a], placement[b], side) > 0:
                    g.add_edge(a, b, side=side); g.add_edge(b, a, side=OPPOSITE[side])
    return g


def topology_classes(brief: Brief, placements: list[Placement]) -> list[int]:
    """Class index per placement. Two placements are in one class when their shared-wall graphs, with the side of
    every contact, are isomorphic under some symmetry of the plan (rotation, mirror) and any swap of identical
    spaces. So "kitchen on the long wall of the living room" and "kitchen on its short wall" differ, while a mirrored
    plan or two identical offices trading places do not (PLAN M9, refined in M12)."""
    import networkx as nx
    from networkx.algorithms.isomorphism import categorical_edge_match, categorical_node_match
    nm, em = categorical_node_match("kind", None), categorical_edge_match("side", None)
    syms = _symmetries()
    reps: list = []
    out: list[int] = []
    for pl in placements:
        g = side_graph(brief, pl)
        found = None
        for k, r in enumerate(reps):
            if g.number_of_edges() != r.number_of_edges():
                continue
            for T in syms:
                gt = g.copy()
                for _a, _b, d in gt.edges(data=True):
                    d["side"] = T[d["side"]]
                if nx.is_isomorphic(gt, r, node_match=nm, edge_match=em):
                    found = k; break
            if found is not None:
                break
        if found is None:
            reps.append(g); found = len(reps) - 1
        out.append(found)
    return out
