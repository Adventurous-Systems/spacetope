"""AssemblyGraph intent + Placement coordinates -> topologicpy CellComplex with dictionaries."""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from topologicpy.Cell import Cell
from topologicpy.CellComplex import CellComplex
from topologicpy.Dictionary import Dictionary
from topologicpy.Face import Face
from topologicpy.Topology import Topology
from topologicpy.Vertex import Vertex

from .brief import Brief
from .placement import Placement, check_complete
from .spacegraph import AssemblyGraph, Contact
from .units import to_m
from .solve.grid import Box


class RealiseError(RuntimeError):
    pass


def cell_dictionary(brief: Brief, name: str, box: Box) -> dict:
    s = brief.space(name)
    d = {"name": name, "program": s.program, "w": to_m(box.w), "l": to_m(box.l), "h": to_m(box.h),
         "level_z": to_m(box.z)}
    if s.serves is not None:
        d["serves"] = [int(s.serves[0]), int(s.serves[1])]
    for axis, val in (("w", box.w), ("l", box.l), ("h", box.h)):
        nom = s.nominal_mm(axis)
        d[f"dev_{axis}"] = round((val - nom) / nom, 6)
    return d


KERNEL_RETRIES = 2


def make_cell(name: str, box: Box, dictionary: dict):
    """Build one box cell and prove it landed where asked. In long-lived processes topologic_core
    occasionally fails inside Cell.Box (its own translate step) and returns None or a box left at the
    origin, with only a printed message (docs/TOPOLOGICPY_NOTES.md §12). Retry, then fail by name rather
    than let a None or a misplaced cell reach CellComplex.ByCells."""
    m = box.to_m()
    want = (round(m["x"] + m["w"] / 2, 6), round(m["y"] + m["l"] / 2, 6), round(m["z"] + m["h"] / 2, 6))
    last = "no cell returned"
    for _attempt in range(KERNEL_RETRIES + 1):
        c = Cell.Box(origin=Vertex.ByCoordinates(m["x"], m["y"], m["z"]), width=m["w"], length=m["l"], height=m["h"],
                     placement="lowerleft")
        if c is None:
            continue
        got = tuple(round(v, 6) for v in Vertex.Coordinates(Topology.Centroid(c)))
        if all(abs(a - b) < 1e-5 for a, b in zip(got, want)):
            Topology.SetDictionary(c, Dictionary.ByPythonDictionary(dictionary))
            return c
        last = f"centroid {got}, expected {want}"
    raise RealiseError(f"kernel failed to build cell {name!r} ({last}) after {KERNEL_RETRIES + 1} attempts")


def make_selector(box: Box, dictionary: dict):
    m = box.to_m()
    v = Vertex.ByCoordinates(round(m["x"] + m["w"] / 2, 6), round(m["y"] + m["l"] / 2, 6), round(m["z"] + m["h"] / 2, 6))
    Topology.SetDictionary(v, Dictionary.ByPythonDictionary(dictionary))
    return v


@dataclass
class Realised:
    brief: Brief
    placement: Placement
    intent: AssemblyGraph
    cc: object                       # CellComplex (or Cell for a single space)
    cells: list = field(default_factory=list)   # Topology.Cells order
    names: list[str] = field(default_factory=list)  # name per cell, same order
    selectors: list = field(default_factory=list)
    build_seconds: float = 0.0
    doors: list = field(default_factory=list)          # planned doors (spacetope.doors.Door), M7
    door_problems: list = field(default_factory=list)  # planning problems (spacetope.circulation.Problem)

    @property
    def n_cells(self) -> int:
        return len(self.cells)

    def cell_of(self, name: str):
        return self.cells[self.names.index(name)]

    def name_of(self, cell) -> str | None:
        """Name a cell by dictionary, falling back to centroid lookup."""
        n = Dictionary.ValueAtKey(Topology.Dictionary(cell), "name")
        if n:
            return n
        cx, cy, cz = Vertex.Coordinates(Topology.Centroid(cell))
        for name, b in self.placement.items():
            m = b.to_m()
            if abs(m["x"] + m["w"] / 2 - cx) < 1e-4 and abs(m["y"] + m["l"] / 2 - cy) < 1e-4 and abs(m["z"] + m["h"] / 2 - cz) < 1e-4:
                return name
        return None

    def shared_faces(self) -> list:
        if Topology.IsInstance(self.cc, "CellComplex"):
            return CellComplex.NonManifoldFaces(self.cc)
        return []

    def external_faces(self) -> list:
        if Topology.IsInstance(self.cc, "CellComplex"):
            return CellComplex.ExternalFaces(self.cc)
        return Topology.Faces(self.cc)

    def realised_contacts(self) -> list[Contact]:
        """Contacts read back from the built complex: one per shared face (cells named)."""
        out: list[Contact] = []
        for f in self.shared_faces():
            cells = Topology.SuperTopologies(f, self.cc, topologyType="cell") or []
            if len(cells) != 2:
                continue
            n = Face.Normal(f)
            axis = max(range(3), key=lambda i: abs(n[i]))
            axname = "xyz"[axis]
            plane = Vertex.Coordinates(Topology.Centroid(f))[axis]
            na, nb = self.name_of(cells[0]), self.name_of(cells[1])
            if na is None or nb is None:
                continue
            ba, bb = self.placement[na], self.placement[nb]
            # the cell whose max on this axis lies on the plane owns the '+' side
            def side_for(box: Box) -> str:
                hi = to_m(box.interval(axname)[1])
                if axname == "z":
                    return "ceiling" if abs(hi - plane) < 1e-4 else "floor"
                return f"+{axname}" if abs(hi - plane) < 1e-4 else f"-{axname}"
            out.append(Contact(na, side_for(ba), nb, side_for(bb)).canonical())
        return sorted(set(out))

    def realised_assembly(self) -> AssemblyGraph:
        ag = AssemblyGraph(self.brief)
        for c in self.realised_contacts():
            ag.add_contact(c.a, c.side_a, c.b, c.side_b)
        return ag


def door_face(d):
    """A door as a planar quad on its wall, built from corners so its orientation is explicit."""
    h0, h1 = d.z_mm, d.z_mm + d.height_mm
    if d.side in ("+x", "-x"):
        corners = [(d.plane_mm, d.lo_mm, h0), (d.plane_mm, d.hi_mm, h0), (d.plane_mm, d.hi_mm, h1), (d.plane_mm, d.lo_mm, h1)]
    else:
        corners = [(d.lo_mm, d.plane_mm, h0), (d.hi_mm, d.plane_mm, h0), (d.hi_mm, d.plane_mm, h1), (d.lo_mm, d.plane_mm, h1)]
    f = Face.ByVertices([Vertex.ByCoordinates(to_m(x), to_m(y), to_m(z)) for x, y, z in corners])
    Topology.SetDictionary(f, Dictionary.ByPythonDictionary({
        "name": d.name, "kind": d.kind, "a": d.a, "b": d.b, "level": d.level,
        "width": to_m(d.width_mm), "height": to_m(d.height_mm)}))
    return f


def attach_doors(cc, doors: list):
    """Attach doors as apertures on the complex's faces (topologicpy hosts each on its shared wall)."""
    if not doors:
        return cc
    faces = [door_face(d) for d in doors]
    return Topology.AddApertures(cc, faces, exclusive=False, subTopologyType="face", tolerance=0.001)


def realise(brief: Brief, placement: Placement, intent: AssemblyGraph | None = None, with_doors: bool = True) -> Realised:
    """Build the complex. Raises RealiseError when the kernel cannot form a complex.
    Circulation briefs (M7) also get their doors planned and, unless with_doors=False, attached."""
    from .placement import assembly_from_placement
    check_complete(brief, placement)
    intent = intent or assembly_from_placement(brief, placement)
    t0 = time.perf_counter()
    cells, selectors = [], []
    for name, box in placement.items():
        d = cell_dictionary(brief, name, box)
        cells.append(make_cell(name, box, d))
        selectors.append(make_selector(box, d))
    if len(cells) == 1:
        cc = cells[0]
    else:
        cc = CellComplex.ByCells(cells, silent=True)
    # 0.9.57 returns None when the cells do not merge, 0.9.71 an empty CellComplex (docs/TOPOLOGICPY_NOTES.md §14)
    if cc is None or (len(cells) > 1 and not (Topology.Cells(cc) or [])):
        raise RealiseError("CellComplex.ByCells built nothing (gaps or disjoint cells)")
    if Topology.IsInstance(cc, "CellComplex"):
        cc = Topology.TransferDictionariesBySelectors(cc, selectors, tranCells=True, numWorkers=1)
    built = Topology.Cells(cc) if Topology.IsInstance(cc, "CellComplex") else [cc]
    r = Realised(brief=brief, placement=placement, intent=intent, cc=cc, cells=built, selectors=selectors,
                 build_seconds=time.perf_counter() - t0)
    r.names = [r.name_of(c) or "?" for c in built]
    if brief.circulation:
        from .doors import plan_doors
        r.doors, r.door_problems = plan_doors(brief, placement)
        if with_doors and Topology.IsInstance(cc, "CellComplex"):
            r.cc = attach_doors(r.cc, r.doors)
    return r
