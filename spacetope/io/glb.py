# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Adventurous Systems

"""GLB with one named node per cell (`cell_{i}`, i in Topology.Cells order) and one per door (`door_{j}`).

Doors are openings, not slabs: each cell is built face by face and the door rectangles on its walls are cut
out, so you can see through a doorway. The door node itself is the aperture face (zero thickness, the same
geometry topologicpy holds as an Aperture). Coordinates are converted Z-up (topologic) -> Y-up (three.js)
by (x, y, z) -> (x, z, -y), a rotation, so winding is preserved.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import trimesh
from topologicpy.Topology import Topology

from ..realise import Realised
from ..solve.grid import OPPOSITE, Box

DOOR_RGBA = [150, 100, 60, 255]
PROGRAM_RGBA = {"room": [107, 174, 214, 255], "corridor": [253, 174, 107, 255], "stair": [230, 85, 13, 255],
                "elevator": [117, 107, 177, 255], "void": [189, 189, 189, 255]}
SIDES = ("+x", "-x", "+y", "-y", "floor", "ceiling")


def to_yup(xyz) -> list[float]:
    x, y, z = xyz
    return [float(x), float(z), -float(y)]


def _yup(points: np.ndarray) -> np.ndarray:
    """(N, 3) in metres, Z-up -> Y-up."""
    return points[:, [0, 2, 1]] * np.array([1.0, 1.0, -1.0])


def _side_frame(box: Box, side: str):
    """(point(u, v) -> (x, y, z) in mm, u range, v range, outward normal) for one side of a box."""
    if side == "+x":
        return (lambda u, v: (box.x1, u, v)), (box.y, box.y1), (box.z, box.z1), (1, 0, 0)
    if side == "-x":
        return (lambda u, v: (box.x, u, v)), (box.y, box.y1), (box.z, box.z1), (-1, 0, 0)
    if side == "+y":
        return (lambda u, v: (u, box.y1, v)), (box.x, box.x1), (box.z, box.z1), (0, 1, 0)
    if side == "-y":
        return (lambda u, v: (u, box.y, v)), (box.x, box.x1), (box.z, box.z1), (0, -1, 0)
    if side == "ceiling":
        return (lambda u, v: (u, v, box.z1)), (box.x, box.x1), (box.y, box.y1), (0, 0, 1)
    return (lambda u, v: (u, v, box.z)), (box.x, box.x1), (box.y, box.y1), (0, 0, -1)


def _quads_with_holes(u0: int, u1: int, v0: int, v1: int, holes: list[tuple[int, int, int, int]]):
    """Split a rectangle into quads that avoid the holes: band by every hole edge in v, then split each
    band by the hole edges in u and drop the pieces that fall inside an opening."""
    vs = sorted({v0, v1} | {v for h in holes for v in h[2:]})
    out = []
    for vb, vt in zip(vs, vs[1:]):
        band = [(h[0], h[1]) for h in holes if h[2] <= vb and h[3] >= vt]
        us = sorted({u0, u1} | {u for h in band for u in h})
        for ul, ur in zip(us, us[1:]):
            if any(a <= ul and b >= ur for a, b in band):
                continue
            out.append((ul, ur, vb, vt))
    return out


def _append_quad(verts: list, faces: list, corners, normal) -> None:
    base = len(verts)
    verts.extend(corners)
    p0, p1, p2 = (np.array(c, dtype=float) for c in corners[:3])
    if float(np.dot(np.cross(p1 - p0, p2 - p0), np.array(normal, dtype=float))) >= 0:
        faces.extend([[base, base + 1, base + 2], [base, base + 2, base + 3]])
    else:
        faces.extend([[base + 2, base + 1, base], [base + 3, base + 2, base]])


def _mesh(verts: list, faces: list) -> trimesh.Trimesh | None:
    if not faces:
        return None
    v = _yup(np.array(verts, dtype=float) / 1000.0)
    m = trimesh.Trimesh(vertices=v, faces=np.array(faces, dtype=int), process=False)
    m.merge_vertices()  # quads are built per face; merging shared corners keeps a doorless box watertight
    return m


def door_holes(name: str, doors: list) -> dict[str, list[tuple[int, int, int, int]]]:
    """Per side of the space `name`, the door rectangles in that side's (u, v) frame."""
    holes: dict[str, list[tuple[int, int, int, int]]] = {}
    for d in doors:
        if name not in (d.a, d.b):
            continue
        side = d.side if d.a == name else OPPOSITE[d.side]
        holes.setdefault(side, []).append((d.lo_mm, d.hi_mm, d.z_mm, d.z_mm + d.height_mm))
    return holes


def box_mesh(box: Box, holes: dict[str, list[tuple[int, int, int, int]]] | None = None) -> trimesh.Trimesh | None:
    """Exact box mesh from an integer-mm Box, with door openings cut out of the given sides."""
    verts: list = []
    faces: list = []
    for side in SIDES:
        point, (u0, u1), (v0, v1), normal = _side_frame(box, side)
        for ul, ur, vb, vt in _quads_with_holes(u0, u1, v0, v1, (holes or {}).get(side, [])):
            _append_quad(verts, faces, [point(ul, vb), point(ur, vb), point(ur, vt), point(ul, vt)], normal)
    return _mesh(verts, faces)


def door_mesh(d) -> trimesh.Trimesh | None:
    """The aperture face itself: a zero-thickness quad on the wall plane."""
    normal = (1, 0, 0) if d.side in ("+x", "-x") else (0, 1, 0)
    h0, h1 = d.z_mm, d.z_mm + d.height_mm
    if d.side in ("+x", "-x"):
        corners = [(d.plane_mm, d.lo_mm, h0), (d.plane_mm, d.hi_mm, h0), (d.plane_mm, d.hi_mm, h1), (d.plane_mm, d.lo_mm, h1)]
    else:
        corners = [(d.lo_mm, d.plane_mm, h0), (d.hi_mm, d.plane_mm, h0), (d.hi_mm, d.plane_mm, h1), (d.lo_mm, d.plane_mm, h1)]
    verts: list = []
    faces: list = []
    _append_quad(verts, faces, corners, normal)
    return _mesh(verts, faces)


def cell_mesh(cell) -> trimesh.Trimesh | None:
    """Triangulated geometry of a built topologic cell (no openings; used for cross-checking)."""
    geo = Topology.Geometry(cell, triangulate=True, silent=True)
    v = np.array(geo.get("vertices", []), dtype=float)
    f = np.array(geo.get("faces", []), dtype=int)
    if len(v) == 0 or len(f) == 0:
        return None
    return trimesh.Trimesh(vertices=_yup(v), faces=f, process=False)


def scene(r: Realised, source: str = "placement") -> trimesh.Scene:
    """source="placement": exact boxes with door openings (fast, default). "topology": the built cells."""
    sc = trimesh.Scene()
    for i, (cell, name) in enumerate(zip(r.cells, r.names)):
        if source == "placement" and name in r.placement:
            m = box_mesh(r.placement[name], door_holes(name, r.doors))
        else:
            m = cell_mesh(cell)
        if m is None:
            continue
        program = r.brief.space(name).program if name in r.brief.by_name else "void"
        m.visual.face_colors = PROGRAM_RGBA.get(program, [153, 153, 153, 255])
        sc.add_geometry(m, node_name=f"cell_{i}", geom_name=f"cell_{i}")
    for j, d in enumerate(r.doors):
        m = door_mesh(d)
        if m is None:
            continue
        m.visual.face_colors = DOOR_RGBA
        sc.add_geometry(m, node_name=f"door_{j}", geom_name=f"door_{j}")
    return sc


def write_glb(r: Realised, path: str | Path, source: str = "placement") -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(scene(r, source).export(file_type="glb"))
    return path


def cell_catalogue(r: Realised) -> list[dict]:
    """Per-cell dictionaries in cell order (what the viewer recolours from)."""
    from topologicpy.Dictionary import Dictionary
    out = []
    for i, cell in enumerate(r.cells):
        d = Topology.Dictionary(cell)
        out.append({"index": i, **(Dictionary.PythonDictionary(d) if d is not None else {})})
    return out
