# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Adventurous Systems

"""OBJ and JSON export of a realised cell complex, taken from topologic itself.

Both formats come from `Topology.Geometry` of every cell of the complex, merged into one vertex table
(integer-millimetre keys) and one face table (vertex-set keys), so a shared wall is one face owned by two
cells and every cell's index is its `Topology.Cells` position. Cells are named by matching each cell's
bounding box to the placement, so the export does not depend on dictionary survival.

- OBJ: one object `cell_{i}` per cell (i in `Realised.cells` order, the same index the GLB uses) with
  polygon faces, a material per program in a sidecar .mtl, and one object `door_{j}` per door aperture.
  Metres, Z up (topologic's frame; the GLB writer is the one that rotates to Y up).
- JSON: the non-manifold structure itself: shared vertex and face tables, cells as face-index lists with
  name, program, box and dictionary, the faces shared by two cells, contacts and doors.

Topologic's own `ExportToOBJ`, `ExportToJSON` and `MeshData` are not used: the first calls PyPI for a
version header, the second loses dictionaries and the third drops cells (docs/TOPOLOGICPY_NOTES.md).
"""
from __future__ import annotations

import json
from pathlib import Path

from topologicpy.Dictionary import Dictionary
from topologicpy.Topology import Topology

from ..realise import Realised
from ..solve.grid import Box

MTL_RGB = {"room": (0.42, 0.68, 0.84), "corridor": (0.99, 0.68, 0.42), "stair": (0.90, 0.33, 0.05),
           "elevator": (0.46, 0.42, 0.69), "void": (0.74, 0.74, 0.74), "door": (0.59, 0.39, 0.24)}
FORMAT = "spacetope-cellcomplex"
VERSION = 1


def _bbox(points: list[list[float]]) -> tuple[list[float], list[float]]:
    lo = [min(p[k] for p in points) for k in range(3)]
    hi = [max(p[k] for p in points) for k in range(3)]
    return lo, hi


def _name_by_box(lo: list[float], hi: list[float], placement: dict[str, Box], tol: float = 1e-3) -> str | None:
    for name, b in placement.items():
        m = b.to_m()
        if all(abs(lo[k] - m[a]) <= tol for k, a in enumerate("xyz")) and \
           abs(hi[0] - (m["x"] + m["w"])) <= tol and abs(hi[1] - (m["y"] + m["l"])) <= tol and abs(hi[2] - (m["z"] + m["h"])) <= tol:
            return name
    return None


def complex_data(r: Realised) -> dict:
    """Vertices, faces and per-cell face lists of the built complex, with each cell named and tagged.

    Built from `Topology.Geometry` per cell in `Topology.Cells` order (the GLB's `cell_{i}` index), merged
    into one vertex table keyed by integer-millimetre coordinates and one face table keyed by vertex set,
    so a shared wall is one face owned by two cells. `Topology.MeshData` is not used: in 0.9.57 mode=1
    returns face indices beyond its vertex table and mode=0 dropped 2 of 12 cells on a two-level complex
    (docs/TOPOLOGICPY_NOTES.md §12)."""
    vertices: list[list[float]] = []
    vid: dict[tuple[int, int, int], int] = {}
    faces: list[list[int]] = []
    fid: dict[frozenset[int], int] = {}
    cells = []
    for idx, cell in enumerate(r.cells):
        g = Topology.Geometry(cell, triangulate=False, silent=True)
        local: list[int] = []
        for v in g["vertices"]:
            key = (int(round(v[0] * 1000)), int(round(v[1] * 1000)), int(round(v[2] * 1000)))
            if key not in vid:
                vid[key] = len(vertices)
                vertices.append([key[0] / 1000.0, key[1] / 1000.0, key[2] / 1000.0])
            local.append(vid[key])
        fl: list[int] = []
        for f in g["faces"]:
            ids = [local[i] for i in f]
            key = frozenset(ids)
            if key not in fid:
                fid[key] = len(faces)
                faces.append(ids)
            fl.append(fid[key])
        pts = [vertices[i] for i in set(local)]
        lo, hi = _bbox(pts)
        name = _name_by_box(lo, hi, r.placement) or (r.names[idx] if idx < len(r.names) else f"cell_{idx}")
        program = r.brief.space(name).program if name in r.brief.by_name else "void"
        d = Topology.Dictionary(cell)
        cells.append({"index": idx, "name": name, "program": program, "faces": sorted(set(fl)),
                      "box": r.placement[name].to_m() if name in r.placement else {"min": lo, "max": hi},
                      "dictionary": Dictionary.PythonDictionary(d) if d is not None else {}})
    owners: dict[int, list[int]] = {}
    for c in cells:
        for f in c["faces"]:
            owners.setdefault(f, []).append(c["index"])
    shared = [{"face": f, "cells": cs} for f, cs in sorted(owners.items()) if len(cs) == 2]
    return {"vertices": vertices, "faces": faces, "cells": cells, "shared_faces": shared}


def json_payload(r: Realised) -> dict:
    data = complex_data(r)
    return {"format": FORMAT, "version": VERSION, "units": "m", "up": "z", "brief": r.brief.name,
            "n_vertices": len(data["vertices"]), "n_faces": len(data["faces"]), "n_cells": len(data["cells"]),
            **data,
            "contacts": [c.to_list() for c in r.realised_contacts()],
            "doors": [d.to_dict() for d in r.doors]}


def write_json(r: Realised, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(json_payload(r), indent=1))
    return path


def _door_corners(d) -> list[tuple[float, float, float]]:
    h0, h1 = d.z_mm / 1000.0, (d.z_mm + d.height_mm) / 1000.0
    p, lo, hi = d.plane_mm / 1000.0, d.lo_mm / 1000.0, d.hi_mm / 1000.0
    if d.side in ("+x", "-x"):
        return [(p, lo, h0), (p, hi, h0), (p, hi, h1), (p, lo, h1)]
    return [(lo, p, h0), (hi, p, h0), (hi, p, h1), (lo, p, h1)]


def write_obj(r: Realised, path: str | Path, mtl: bool = True) -> Path:
    """One OBJ object per cell (`cell_{i}`) and per door (`door_{j}`); polygon faces; metres, Z up."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = complex_data(r)
    lines = [f"# {FORMAT} v{VERSION}: {r.brief.name}; units metres, Z up; {len(data['cells'])} cells, {len(r.doors)} doors"]
    if mtl:
        mtl_path = path.with_suffix(".mtl")
        mtl_lines = []
        for prog, (cr, cg, cb) in MTL_RGB.items():
            mtl_lines += [f"newmtl {prog}", f"Kd {cr:.3f} {cg:.3f} {cb:.3f}", "d 1.0", ""]
        mtl_path.write_text("\n".join(mtl_lines))
        lines.append(f"mtllib {mtl_path.name}")
    for v in data["vertices"]:
        lines.append(f"v {v[0]:.6f} {v[1]:.6f} {v[2]:.6f}")
    for c in data["cells"]:
        lines.append(f"o cell_{c['index']}")
        lines.append(f"# name {c['name']} program {c['program']}")
        if mtl:
            lines.append(f"usemtl {c['program'] if c['program'] in MTL_RGB else 'void'}")
        for f in c["faces"]:
            lines.append("f " + " ".join(str(i + 1) for i in data["faces"][f]))  # OBJ indices are 1-based
    base = len(data["vertices"])
    for j, d in enumerate(r.doors):
        lines.append(f"o door_{j}")
        lines.append(f"# {d.kind} door {d.a} -> {d.b} level {d.level}")
        if mtl:
            lines.append("usemtl door")
        for x, y, z in _door_corners(d):
            lines.append(f"v {x:.6f} {y:.6f} {z:.6f}")
        lines.append(f"f {base + 1} {base + 2} {base + 3} {base + 4}")
        base += 4
    path.write_text("\n".join(lines) + "\n")
    return path
