"""M26: any layout into topologic (PLAN §4.11).

The way in is the same for every tessellation, and for boxes too:

    plan polygons  ->  conform (shared vertices, whole millimetres)  ->  one prism Cell per space, built face by
    face (floor, ceiling, one quad per wall edge)  ->  CellComplex.ByCells (the kernel imprints one level's plan
    on the next)  ->  dictionaries by selector  ->  read back and compare with the measure

Cells are real topologic Cells with planar faces; a wall two spaces share is one non-manifold Face. `verify_layout`
proves it: the pairs of cells the kernel joins by a face must be the pairs `layout.Table` says share a wall, floor
or ceiling.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from topologicpy.Cell import Cell
from topologicpy.CellComplex import CellComplex
from topologicpy.Dictionary import Dictionary
from topologicpy.Face import Face
from topologicpy.Topology import Topology
from topologicpy.Vertex import Vertex
from topologicpy.Wire import Wire

from . import affinity as _aff
from . import layout as _layout
from .brief import Brief, CIRCULATION
from .layout import Layout, Prism, Table, conform, rings_of
from .realise import KERNEL_RETRIES, RealiseError

CHECKS = ("complete", "no_overlaps", "built", "cell_count", "no_slivers", "contacts", "dictionaries", "reach", "affinities")
MIN_CONTACT_MM2 = 10_000.0   # 0.01 m²: below this the measure does not insist that the kernel finds a face
OVERLAP_MM2 = 100.0


def _v(x: float, y: float, z: float):
    return Vertex.ByCoordinates(x / 1000.0, y / 1000.0, z / 1000.0)


def _cap(rings: list, z: int):
    shell = [_v(x, y, z) for x, y in rings[0]]
    if len(rings) == 1:
        return Face.ByVertices(shell, silent=True)
    return Face.ByWires(Wire.ByVertices(shell, close=True, silent=True),
                        [Wire.ByVertices([_v(x, y, z) for x, y in r], close=True, silent=True) for r in rings[1:]], silent=True)


def _straight(ring: list) -> list:
    """The ring without the vertices that lie exactly on a straight wall. `conform` puts them there so the measure
    can read shared edges; the kernel imprints neighbours itself and is several times faster without them."""
    out = [q for k, q in enumerate(ring)
           if (q[0] - ring[k - 1][0]) * (ring[(k + 1) % len(ring)][1] - q[1]) != (q[1] - ring[k - 1][1]) * (ring[(k + 1) % len(ring)][0] - q[0])]
    return out if len(out) >= 3 else ring


def prism_cell(name: str, p: Prism, dictionary: dict | None = None):
    """One space as a Cell: floor, ceiling and a vertical quad per plan edge. The volume is checked against the
    prism's, with the same retries `realise.make_cell` gives the kernel."""
    rings = [_straight(r) for r in rings_of(p.poly)]
    want = p.volume / 1e9
    last = "no cell returned"
    for _attempt in range(KERNEL_RETRIES + 1):
        faces = [_cap(rings, p.z0), _cap(rings, p.z1)]
        for r in rings:
            for k, a in enumerate(r):
                b = r[(k + 1) % len(r)]
                faces.append(Face.ByVertices([_v(*a, p.z0), _v(*b, p.z0), _v(*b, p.z1), _v(*a, p.z1)], silent=True))
        if any(f is None for f in faces):
            last = "a face could not be built"
            continue
        c = Cell.ByFaces(faces, silent=True)
        if c is None or not Topology.IsInstance(c, "Cell"):
            continue
        got = Cell.Volume(c)
        if abs(got - want) <= 1e-6 + 1e-6 * want:
            if dictionary:
                Topology.SetDictionary(c, Dictionary.ByPythonDictionary(dictionary))
            return c
        last = f"volume {got:.6f} m3, expected {want:.6f}"
    raise RealiseError(f"kernel failed to build cell {name!r} ({last}) after {KERNEL_RETRIES + 1} attempts")


def cell_dictionary(brief: Brief, name: str, p: Prism) -> dict:
    s = brief.space(name)
    w, l = s.nominal("w"), s.nominal("l")
    d = {"name": name, "program": s.program, "w": w, "l": l, "h": p.h / 1000.0, "level_z": p.z0 / 1000.0,
         "area": round(p.area / 1e6, 6), "dev_area": round((p.area / 1e6 - w * l) / (w * l), 6),
         "walls": sum(len(r) for r in rings_of(p.poly))}
    if s.serves is not None:
        d["serves"] = [int(s.serves[0]), int(s.serves[1])]
    return d


@dataclass
class RealisedLayout:
    """A built layout. Duck-types what `io.glb` and `io.brep` read from `realise.Realised`."""
    brief: Brief
    layout: Layout
    table: Table
    cc: object
    cells: list = field(default_factory=list)
    names: list[str] = field(default_factory=list)
    build_seconds: float = 0.0
    doors: list = field(default_factory=list)
    placement: dict = field(default_factory=dict)   # empty: the GLB is meshed from the cells themselves

    @property
    def n_cells(self) -> int:
        return len(self.cells)

    def kernel_pairs(self) -> set[frozenset]:
        """Pairs of named cells that share a face in the complex."""
        if not Topology.IsInstance(self.cc, "CellComplex"):
            return set()
        out = set()
        for f in CellComplex.NonManifoldFaces(self.cc) or []:
            cs = Topology.SuperTopologies(f, self.cc, topologyType="cell") or []
            ns = {Dictionary.ValueAtKey(Topology.Dictionary(c), "name") for c in cs}
            ns.discard(None)
            if len(ns) == 2:
                out.add(frozenset(ns))
        return out


def realise_layout(brief: Brief, layout: Layout) -> RealisedLayout:
    """Build the complex. Raises RealiseError when the kernel cannot form one."""
    t0 = time.perf_counter()
    lay = conform(layout)
    cells, selectors = [], []
    for name, p in lay.items():
        d = cell_dictionary(brief, name, p)
        cells.append(prism_cell(name, p, d))
        q = p.poly.representative_point()
        sel = Vertex.ByCoordinates(round(q.x / 1000, 6), round(q.y / 1000, 6), round((p.z0 + p.z1) / 2000, 6))
        Topology.SetDictionary(sel, Dictionary.ByPythonDictionary(d))
        selectors.append(sel)
    if not cells:
        raise RealiseError("nothing to build")
    cc = cells[0] if len(cells) == 1 else CellComplex.ByCells(cells, silent=True)
    if cc is None or (len(cells) > 1 and not (Topology.Cells(cc) or [])):
        raise RealiseError("CellComplex.ByCells built nothing (gaps or disjoint cells)")
    if Topology.IsInstance(cc, "CellComplex"):
        cc = Topology.TransferDictionariesBySelectors(cc, selectors, tranCells=True, numWorkers=1)
    built = Topology.Cells(cc) if Topology.IsInstance(cc, "CellComplex") else [cc]
    names = [Dictionary.ValueAtKey(Topology.Dictionary(c), "name") or "?" for c in built]
    return RealisedLayout(brief=brief, layout=lay, table=Table(lay, conformed=True), cc=cc, cells=built, names=names,
                          build_seconds=time.perf_counter() - t0)


# ----------------------------------------------------------------------------- checks

def overlapping(layout: Layout) -> list[tuple[str, str]]:
    names = list(layout)
    out = []
    for i, a in enumerate(names):
        A = layout[a]
        ab = A.poly.bounds
        for b in names[i + 1:]:
            B = layout[b]
            if min(A.z1, B.z1) <= max(A.z0, B.z0):
                continue
            bb = B.poly.bounds
            if ab[0] >= bb[2] or bb[0] >= ab[2] or ab[1] >= bb[3] or bb[1] >= ab[3]:
                continue
            if A.poly.intersection(B.poly).area > OVERLAP_MM2:
                out.append((a, b))
    return out


def _graze(layout: Layout, a: str, b: str, tol: float = 2.0) -> bool:
    """True when two prisms meet only along a line: within `tol` mm in plan and no gap in height."""
    A, B = layout[a], layout[b]
    return max(A.z0, B.z0) <= min(A.z1, B.z1) and A.poly.distance(B.poly) <= tol


def precheck(brief: Brief, layout, show: int = 3) -> dict[str, tuple[bool, str]]:
    """The checks that need no kernel: every space has ground, none overlap, rooms reach the circulation, and the
    `must`/`never` affinities hold. Cheap enough to run on every drag."""
    t = _layout.table(layout)
    L = t.layout
    checks: dict[str, tuple[bool, str]] = {}
    missing = sorted(s.name for s in brief.spaces if s.name not in L)
    checks["complete"] = (not missing, "all spaces have ground" if not missing else f"no ground for {', '.join(missing[:4])}")
    ov = overlapping(L)
    checks["no_overlaps"] = (not ov, "none" if not ov else f"overlapping pairs {ov[:4]}")
    circ = {n for n in L if brief.space(n).program in CIRCULATION}
    if circ:
        g = t.walk(brief)
        import networkx as nx
        ok_from = set()
        for comp in nx.connected_components(g):
            if comp & circ:
                ok_from |= comp
        cut = sorted(n for n in L if brief.space(n).program == "room" and n not in ok_from)
        whole = nx.is_connected(g.subgraph(circ)) if len(circ) > 1 else True
        detail = "every room opens onto the path" if not cut else f"no door-wide wall to the path: {', '.join(cut[:4])}" + (f" and {len(cut) - 4} more" if len(cut) > 4 else "")
        if not whole:
            detail += "; the path is in separate pieces"
        checks["reach"] = (not cut and whole, detail)
    else:
        checks["reach"] = (True, "no path to reach")
    if _aff.written(brief):
        misses = [_aff.describe(i) for i in _layout.affinity(brief, t, strengths=_aff.HARD)["items"] if i["met"] is False]
    else:
        misses = []
    more = f"; and {len(misses) - show} more" if len(misses) > show else ""
    checks["affinities"] = (not misses, "; ".join(misses[:show]) + more if misses else "ok")
    return checks


@dataclass
class LayoutReport:
    ok: bool
    checks: dict[str, tuple[bool, str]]
    realised: RealisedLayout | None = None

    def to_dict(self) -> dict:
        return {"ok": self.ok, "checks": {k: {"passed": p, "detail": d} for k, (p, d) in self.checks.items()}}


def verify_layout(brief: Brief, layout: Layout) -> LayoutReport:
    """Build the layout and hold the kernel's reading against the measure's."""
    pre = precheck(brief, layout)
    checks: dict[str, tuple[bool, str]] = {k: pre[k] for k in ("complete", "no_overlaps")}
    try:
        r = realise_layout(brief, layout)
    except RealiseError as e:
        checks["built"] = (False, str(e))
        for k in ("cell_count", "no_slivers", "contacts", "dictionaries"):
            checks[k] = (False, "not built")
        checks["reach"], checks["affinities"] = pre["reach"], pre["affinities"]
        return LayoutReport(False, checks)
    checks["built"] = (True, f"{Topology.TypeAsString(r.cc)} in {r.build_seconds:.2f}s")
    n = len(r.layout)
    checks["cell_count"] = (r.n_cells == n, f"{r.n_cells} cells for {n} spaces")
    expected = sorted(p.volume / 1e9 for p in r.layout.values())
    actual = sorted(Cell.Volume(c) for c in r.cells)
    bad = [round(a, 6) for a, e in zip(actual, expected) if abs(a - e) > 1e-6 + 1e-6 * e] if len(actual) == len(expected) else [round(a, 6) for a in actual]
    checks["no_slivers"] = (len(actual) == len(expected) and not bad, "volumes match" if not bad and len(actual) == len(expected) else f"unexpected volumes {bad[:5]}")
    kernel = r.kernel_pairs()
    measured = r.table.pairs()
    firm = {p for p in measured if r.table.contact(*tuple(p)) >= MIN_CONTACT_MM2}
    lost = firm - kernel
    extra = {p for p in kernel - measured if not _graze(r.layout, *tuple(p))}   # a face of no width is not a contact
    detail = f"{len(firm)} measured, {len(kernel)} in the complex"
    if lost:
        detail += "; not joined by a face: " + ", ".join("–".join(sorted(p)) for p in sorted(lost, key=sorted)[:3])
    if extra:
        detail += "; joined but not measured: " + ", ".join("–".join(sorted(p)) for p in sorted(extra, key=sorted)[:3])
    checks["contacts"] = (not lost and not extra, detail)
    untagged = sum(1 for nm in r.names if nm == "?")
    checks["dictionaries"] = (untagged == 0, "all cells tagged" if not untagged else f"{untagged} cells have no name")
    checks["reach"], checks["affinities"] = pre["reach"], pre["affinities"]
    return LayoutReport(all(p for p, _ in checks.values()), checks, r)
