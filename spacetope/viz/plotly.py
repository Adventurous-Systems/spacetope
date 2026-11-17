# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Adventurous Systems

"""Quick-look Plotly figure: cells coloured by program + realised graph overlay. No network calls."""
from __future__ import annotations

from pathlib import Path

import plotly.graph_objects as go
from topologicpy.Topology import Topology

from ..realise import Realised
from ..io.graph import graph_payload

PROGRAM_COLOURS = {"room": "#6baed6", "corridor": "#fdae6b", "stair": "#e6550d", "elevator": "#756bb1", "void": "#bdbdbd"}


def cell_mesh(cell, name: str, colour: str, opacity: float = 0.45) -> go.Mesh3d:
    geo = Topology.Geometry(cell, triangulate=True, silent=True)
    vs, fs = geo["vertices"], geo["faces"]
    return go.Mesh3d(x=[v[0] for v in vs], y=[v[1] for v in vs], z=[v[2] for v in vs],
                     i=[f[0] for f in fs], j=[f[1] for f in fs], k=[f[2] for f in fs],
                     color=colour, opacity=opacity, name=name, hovertext=name, flatshading=True, showscale=False)


def figure(r: Realised, graph: bool = True, title: str | None = None) -> go.Figure:
    data = []
    for cell, name in zip(r.cells, r.names):
        prog = r.brief.space(name).program if name in r.brief.by_name else "void"
        data.append(cell_mesh(cell, name, PROGRAM_COLOURS.get(prog, "#999999")))
    if graph:
        p = graph_payload(r, wall_nodes=True)
        xs, ys, zs = [], [], []
        for a, b in p["edges"]:
            for i in (a, b):
                xs.append(p["coords"][i][0]); ys.append(p["coords"][i][1]); zs.append(p["coords"][i][2])
            xs.append(None); ys.append(None); zs.append(None)
        data.append(go.Scatter3d(x=xs, y=ys, z=zs, mode="lines", line=dict(color="#222", width=3), name="contacts"))
        spaces = [i for i, k in enumerate(p["kinds"]) if k == "space"]
        walls = [i for i, k in enumerate(p["kinds"]) if k == "wall"]
        data.append(go.Scatter3d(x=[p["coords"][i][0] for i in spaces], y=[p["coords"][i][1] for i in spaces],
                                 z=[p["coords"][i][2] for i in spaces], mode="markers+text",
                                 text=[p["names"][i] for i in spaces], marker=dict(size=6, color="#111"), name="spaces"))
        data.append(go.Scatter3d(x=[p["coords"][i][0] for i in walls], y=[p["coords"][i][1] for i in walls],
                                 z=[p["coords"][i][2] for i in walls], mode="markers",
                                 marker=dict(size=3, color="#d62728"), name="shared faces"))
    fig = go.Figure(data=data)
    fig.update_layout(title=title or r.brief.name, scene=dict(aspectmode="data"), margin=dict(l=0, r=0, t=30, b=0))
    return fig


def write_html(r: Realised, path: str | Path, graph: bool = True) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    figure(r, graph).write_html(str(path), include_plotlyjs="cdn")
    return path
