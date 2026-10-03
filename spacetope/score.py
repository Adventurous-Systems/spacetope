"""Metrics for ranking options (docs/ALGORITHM_SURVEY.md §H). v0: four metrics + stacking placeholder."""
from __future__ import annotations

import math

import networkx as nx
from topologicpy.Face import Face

from .brief import Brief, CIRCULATION
from .placement import Placement
from .realise import Realised
from .solve.grid import overlap_len, touches
from .units import to_mm

METRICS = ("adjacency", "deviation", "compactness", "circulation", "stacking", "vertical", "envelope_fit", "daylight")
DOOR_MM = 900
HSIDES = ("+x", "-x", "+y", "-y")


def adjacency(brief: Brief, realised_pairs: set[frozenset[str]]) -> float:
    req = brief.required_pairs()
    if not req:
        return 1.0
    return len(req & realised_pairs) / len(req)


def deviation(brief: Brief, placement: Placement) -> float:
    """Mean fractional deviation over spaces and axes; rotation-invariant (a 4x3 room laid 3x4 is exact)."""
    tot, n = 0.0, 0
    for name, b in placement.items():
        s = brief.space(name)
        nw, nl, nh = s.nominal_mm("w"), s.nominal_mm("l"), s.nominal_mm("h")
        plain = abs(b.w - nw) / nw + abs(b.l - nl) / nl
        swapped = abs(b.w - nl) / nl + abs(b.l - nw) / nw
        tot += min(plain, swapped) + abs(b.h - nh) / nh
        n += 3
    return tot / n if n else 0.0


def compactness(r: Realised) -> float:
    """Cube-equivalent form factor in (0, 1]: surface of a cube with the same volume / external surface."""
    vol = sum(b.volume() for b in r.placement.values()) / 1e9
    ext = sum(Face.Area(f) for f in r.external_faces())
    if ext <= 0 or vol <= 0:
        return 0.0
    cube = 6 * (vol ** (2 / 3))
    return min(1.0, cube / ext)


def circulation(brief: Brief, placement: Placement) -> float:
    """Circulation floor area / habitable floor area (>= 0; lower is leaner)."""
    circ = sum(b.w * b.l for n, b in placement.items() if brief.space(n).program in CIRCULATION)
    net = sum(b.w * b.l for n, b in placement.items() if brief.space(n).program == "room")
    return circ / net if net else 0.0


def stacking(placement: Placement) -> float:
    """Fraction of vertical wall planes on level k that coincide with a plane on level k-1 (0 if single level)."""
    levels = sorted({b.z for b in placement.values()})
    if len(levels) < 2:
        return 0.0
    planes = {}
    for z in levels:
        on = [b for b in placement.values() if b.z <= z < b.z1]  # a shaft counts on every level it covers
        planes[z] = ({b.x for b in on} | {b.x1 for b in on}, {b.y for b in on} | {b.y1 for b in on})
    hits, tot = 0, 0
    for lo, hi in zip(levels, levels[1:]):
        for i in (0, 1):
            tot += len(planes[hi][i])
            hits += len(planes[hi][i] & planes[lo][i])
    return hits / tot if tot else 0.0


def access_graph(brief: Brief, placement: Placement) -> nx.Graph:
    """Walkable adjacency: horizontal contacts with door-width overlap, plus vertical contacts
    between two cores of the same program (a stair stack, a lift stack). Floors are not doors."""
    g = nx.Graph()
    g.add_nodes_from(placement)
    names = list(placement)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            sa, sb = brief.space(a), brief.space(b)
            for side in HSIDES:
                u, v = touches(placement[a], placement[b], side)
                if u >= DOOR_MM and v >= 2000:
                    g.add_edge(a, b)
            if sa.is_vertical and sa.program == sb.program:
                for side in ("ceiling", "floor"):
                    if touches(placement[a], placement[b], side)[0] > 0:
                        g.add_edge(a, b)
    return g


def vertical(brief: Brief, placement: Placement, doors: list | None = None) -> float:
    """Fraction of spaces in the largest walkable component (1.0 = everything reachable).
    Circulation briefs walk through planned doors (M7); legacy briefs through door-width wall contacts."""
    if brief.circulation and doors is not None:
        from .doors import door_graph
        g = door_graph(brief, doors, placement)
    else:
        g = access_graph(brief, placement)
    if g.number_of_nodes() == 0:
        return 0.0
    return max(len(c) for c in nx.connected_components(g)) / g.number_of_nodes()


def envelope_fit(brief: Brief, placement: Placement) -> float:
    if not brief.envelope:
        return 0.0
    env = to_mm(brief.envelope["w"]) * to_mm(brief.envelope["l"]) * to_mm(brief.envelope["h"])
    return min(1.0, sum(b.volume() for b in placement.values()) / env) if env else 0.0


def daylight(brief: Brief, placement: Placement) -> float:
    """Fraction of rooms with at least one vertical face not fully covered by neighbours."""
    rooms = [n for n in placement if brief.space(n).program == "room"]
    if not rooms:
        return 0.0
    lit = 0
    for n in rooms:
        b = placement[n]
        exterior = False
        for side in HSIDES:
            axis = "y" if side in ("+x", "-x") else "x"
            length = b.l if axis == "y" else b.w
            covered = 0
            for m, o in placement.items():
                if m == n:
                    continue
                u, v = touches(b, o, side)
                if u > 0 and v >= b.h:
                    covered += u
            if covered < length:
                exterior = True
                break
        lit += exterior
    return lit / len(rooms)


def score(r: Realised) -> dict[str, float]:
    pairs = {c.pair for c in r.realised_contacts()}
    return {
        "adjacency": round(adjacency(r.brief, pairs), 6),
        "deviation": round(deviation(r.brief, r.placement), 6),
        "compactness": round(compactness(r), 6),
        "circulation": round(circulation(r.brief, r.placement), 6),
        "stacking": round(stacking(r.placement), 6),
        "vertical": round(vertical(r.brief, r.placement, r.doors), 6),
        "envelope_fit": round(envelope_fit(r.brief, r.placement), 6),
        "daylight": round(daylight(r.brief, r.placement), 6),
    }



def analysis(r: Realised) -> dict:
    """Space-syntax style readings of the walkable graph, reported beside the scores but not ranked (PLAN M9):
    which space carries the most through-movement, which spaces or doors are single points of failure.
    Door graph for circulation briefs, access graph otherwise. Pure networkx."""
    if r.brief.circulation:
        from .doors import door_graph
        g = door_graph(r.brief, r.doors, r.placement)
    else:
        g = access_graph(r.brief, r.placement)
    if g.number_of_nodes() == 0:
        return {}
    btw = nx.betweenness_centrality(g)
    top = max(btw, key=btw.get)
    depth = {}
    if nx.is_connected(g) and g.number_of_nodes() > 1:
        ecc = nx.eccentricity(g)
        depth = {"diameter": max(ecc.values()), "mean_depth": round(sum(dict(nx.shortest_path_length(g, top)).values()) / (g.number_of_nodes() - 1), 4)}
    routes = vertical_routes(r.brief, g)
    return {**routes, "walk_nodes": g.number_of_nodes(), "walk_edges": g.number_of_edges(), "connected": nx.is_connected(g),
            "busiest": top, "busiest_betweenness": round(btw[top], 4),
            "cut_spaces": sorted(nx.articulation_points(g)), "bridge_doors": sorted(sorted(e) for e in nx.bridges(g)), **depth}


def compactness_boxes(placement: Placement) -> float:
    """Same form factor as `compactness`, from integer boxes: external surface = all box faces minus twice the
    shared contact areas. Equal to the kernel value for exact complexes; used before anything is built (PLAN M10)."""
    from .solve.grid import contact_area
    boxes = list(placement.values())
    vol = sum(b.volume() for b in boxes) / 1e9
    surf = sum(2 * (b.w * b.l + b.w * b.h + b.l * b.h) for b in boxes)
    shared = 0
    for i, a in enumerate(boxes):
        for b in boxes[i + 1:]:
            shared += sum(contact_area(a, b, s) for s in ("+x", "-x", "+y", "-y", "ceiling", "floor"))
    ext = (surf - 2 * shared) / 1e6
    if ext <= 0 or vol <= 0:
        return 0.0
    return min(1.0, 6 * (vol ** (2 / 3)) / ext)


def cheap_scores(brief: Brief, placement: Placement) -> dict[str, float]:
    """The eight metrics from boxes alone, for ranking before realisation (PLAN M10)."""
    from .doors import plan_doors
    from .solve.grid import contact_area
    names = list(placement)
    pairs = {frozenset((a, b)) for i, a in enumerate(names) for b in names[i + 1:]
             if any(contact_area(placement[a], placement[b], s) > 0 for s in ("+x", "-x", "+y", "-y", "ceiling", "floor"))}
    doors = plan_doors(brief, placement)[0] if brief.circulation else []
    return {
        "adjacency": round(adjacency(brief, pairs), 6),
        "deviation": round(deviation(brief, placement), 6),
        "compactness": round(compactness_boxes(placement), 6),
        "circulation": round(circulation(brief, placement), 6),
        "stacking": round(stacking(placement), 6),
        "vertical": round(vertical(brief, placement, doors), 6),
        "envelope_fit": round(envelope_fit(brief, placement), 6),
        "daylight": round(daylight(brief, placement), 6),
    }


def vertical_routes(brief: Brief, g: "nx.Graph") -> dict:
    """PLAN M14: how many independent ways lead down from every upper level, read from the door graph.
    `vertical_routes` counts vertex-disjoint door paths between a level's corridor and the ground corridor (stairs and
    lifts); `stair_routes` counts them with the lifts taken out, which is the number that matters when a lift cannot
    be used. The minimum over upper levels is reported. Empty for single-level or non-circulation briefs."""
    n = int(brief.levels or 1)
    if n < 2 or not brief.circulation:
        return {}
    corridors: dict[int, str] = {}
    for s in brief.spaces:
        if s.program == "corridor" and s.wishes.get("level") is not None and s.name in g:
            corridors.setdefault(int(s.wishes["level"]), s.name)
    if 0 not in corridors or len(corridors) < 2:
        return {}
    lifts = [s.name for s in brief.spaces if s.program == "elevator" and s.name in g]
    no_lifts = g.copy(); no_lifts.remove_nodes_from(lifts)

    def routes(graph, a, b) -> int:
        if a not in graph or b not in graph or not nx.has_path(graph, a, b):
            return 0
        return nx.node_connectivity(graph, a, b) if not graph.has_edge(a, b) else 1 + nx.node_connectivity(nx.restricted_view(graph, [], [(a, b)]), a, b)
    ups = [k for k in corridors if k > 0]
    return {"vertical_routes": min(routes(g, corridors[k], corridors[0]) for k in ups),
            "stair_routes": min(routes(no_lifts, corridors[k], corridors[0]) for k in ups)}
