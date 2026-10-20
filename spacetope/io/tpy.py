"""One-file persistence through topologicpy's native TPY archive (PLAN M14; needs topologicpy >= 0.9.68).

`docs/TOPOLOGICPY_NOTES.md` §13: a TPY round trip keeps cell dictionaries and face apertures with their
dictionaries, which topologic JSON loses. The BREP + selector sidecar path in `io/brep.py` stays as the portable
fallback and as the format older pins can read."""
from __future__ import annotations

from pathlib import Path

from topologicpy.Topology import Topology

from ..realise import Realised

AVAILABLE = hasattr(Topology, "ExportToTPY") and hasattr(Topology, "ByTPYPath")


class TpyUnavailable(RuntimeError):
    pass


def save(r: Realised, path: str | Path) -> Path:
    if not AVAILABLE:
        raise TpyUnavailable("this topologicpy has no TPY persistence; use spacetope.io.brep")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    ok = Topology.ExportToTPY(r.cc, str(path), overwrite=True, includeSubtopologyDictionaries=True, includeApertures=True, silent=True)
    if not ok or not path.exists():
        raise RuntimeError(f"TPY export failed for {path}")
    return path


def load_cellcomplex(path: str | Path):
    if not AVAILABLE:
        raise TpyUnavailable("this topologicpy has no TPY persistence; use spacetope.io.brep")
    return Topology.ByTPYPath(str(path))
