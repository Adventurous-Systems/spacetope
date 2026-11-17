# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Adventurous Systems

"""Which geometry kernel topologicpy is running on, and the version pinned for each (STATUS §2.6).

topologicpy 0.9.71 picks PythonOCC when `OCC` imports and falls back to topologic_core; the environment variable
TOPOLOGICPY_CORE_BACKEND forces one. The only way to ask which is active is a private call, so it lives here."""
from __future__ import annotations

import os
from importlib.metadata import version

PINS = {"topologic_core": "8.0.0", "pythonocc": "7.9"}  # pythonocc-core 7.9.3 reports OCC.VERSION 7.9.x
ENV_VAR = "TOPOLOGICPY_CORE_BACKEND"
_ALIASES = {"pythonocc": "pythonocc", "occ": "pythonocc", "python_occ": "pythonocc",
            "topologic_core": "topologic_core", "topologiccore": "topologic_core", "core": "topologic_core"}


def active() -> dict[str, str]:
    """{"backend": "topologic_core" | "pythonocc", "version": ...} for the kernel topologicpy is using now."""
    from topologicpy.Topology import Topology
    if Topology._IsTopologicCoreBackend():
        return {"backend": "topologic_core", "version": version("topologic_core")}
    import OCC
    return {"backend": "pythonocc", "version": OCC.VERSION}


def requested() -> str | None:
    """The backend named by TOPOLOGICPY_CORE_BACKEND, or None when topologicpy chooses ("auto" or unset)."""
    value = os.environ.get(ENV_VAR, "auto").strip().lower()
    return _ALIASES.get(value)
