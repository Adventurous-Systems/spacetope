# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Adventurous Systems

"""Persistence: BREP (geometry) + selector sidecar (dictionaries) + placement. Topologic JSON is not used
because it drops sub-topology dictionaries on import (docs/TOPOLOGICPY_NOTES.md §7)."""
from __future__ import annotations

import json
from pathlib import Path

from topologicpy.Dictionary import Dictionary
from topologicpy.Topology import Topology
from topologicpy.Vertex import Vertex

from ..brief import Brief
from ..placement import Placement, load_placement, save_placement
from ..realise import Realised, realise


def _side(stem: Path, ext: str) -> Path:
    """stem + ext, keeping any dots in the stem (a suffix swap would eat them; review 2026-09-13)."""
    return stem.parent / (stem.name + ext)


def save(r: Realised, stem: str | Path) -> dict[str, Path]:
    stem = Path(stem)
    stem.parent.mkdir(parents=True, exist_ok=True)
    brep = _side(stem, ".brep")
    brep.write_text(Topology.BREPString(r.cc))
    sidecar = _side(stem, ".selectors.json")
    sel = []
    for v in r.selectors:
        sel.append({"xyz": Vertex.Coordinates(v), "dict": Dictionary.PythonDictionary(Topology.Dictionary(v))})
    sidecar.write_text(json.dumps(sel, indent=1))
    placed = _side(stem, ".placement.json")
    save_placement(r.placement, placed, r.brief.name)
    briefp = _side(stem, ".brief.json")
    briefp.write_text(json.dumps(r.brief.to_dict(), indent=1))
    out = {"brep": brep, "selectors": sidecar, "placement": placed, "brief": briefp}
    if r.brief.circulation:
        doorsp = _side(stem, ".doors.json")  # BREP drops apertures (M7 plan §2.2)
        doorsp.write_text(json.dumps([d.to_dict() for d in r.doors], indent=1))
        out["doors"] = doorsp
    return out


def load_cellcomplex(stem: str | Path):
    """Geometry + dictionaries from BREP + sidecar (no rebuild)."""
    stem = Path(stem)
    cc = Topology.ByBREPString(_side(stem, ".brep").read_text())
    sel = json.loads(_side(stem, ".selectors.json").read_text())
    selectors = []
    for s in sel:
        v = Vertex.ByCoordinates(*s["xyz"])
        Topology.SetDictionary(v, Dictionary.ByPythonDictionary(s["dict"]))
        selectors.append(v)
    if Topology.IsInstance(cc, "CellComplex"):
        cc = Topology.TransferDictionariesBySelectors(cc, selectors, tranCells=True, numWorkers=1)
        doorsp = _side(stem, ".doors.json")
        if doorsp.exists():
            from ..doors import Door
            from ..realise import attach_doors
            cc = attach_doors(cc, [Door.from_dict(d) for d in json.loads(doorsp.read_text())])
    return cc


def load(stem: str | Path) -> Realised:
    """Full Realised object by rebuilding from the stored brief + placement (exact, deterministic)."""
    stem = Path(stem)
    brief = Brief.from_dict(json.loads(_side(stem, ".brief.json").read_text()))
    placement = load_placement(_side(stem, ".placement.json"))
    return realise(brief, placement)
