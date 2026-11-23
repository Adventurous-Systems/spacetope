"""Plan drawings of a field solve as SVG: one column per solve, one row per level. No dependencies."""
from __future__ import annotations

from pathlib import Path

FILL = {"room": "#c8703f", "corridor": "#74c2cc", "stair": "#3d8f9a", "elevator": "#756bb1", "void": "#bdbdbd"}


def svg(solves: list[dict], scale: float = 8.0, pad: float = 16.0) -> str:
    """`solves` are `field.solve` results (or dicts with ground, cells, positions, levels, kind, scores)."""
    xs = [p[0] for r in solves for p in r["ground"]]
    ys = [p[1] for r in solves for p in r["ground"]]
    x0, y0 = min(xs), min(ys)
    w, h = (max(xs) - x0) * scale + 2 * pad, (max(ys) - y0) * scale + 2 * pad + 18
    rows = max(r["levels"] for r in solves)
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{len(solves) * w:.0f}" height="{rows * h:.0f}" '
           f'font-family="Helvetica, Arial, sans-serif" font-size="9"><rect width="100%" height="100%" fill="#ece5da"/>']
    for ci, r in enumerate(solves):
        for k in range(r["levels"]):
            ox, oy = ci * w + pad, (rows - k) * h - pad
            pt = lambda p: f"{ox + (p[0] - x0) * scale:.1f},{oy - (p[1] - y0) * scale:.1f}"  # noqa: E731
            out.append(f'<polygon points="{" ".join(pt(p) for p in r["ground"])}" fill="none" stroke="#222"/>')
            for c in r["cells"]:
                if c["levels"][0] <= k <= c["levels"][1]:
                    out.append(f'<polygon points="{" ".join(pt(p) for p in c["ring"])}" fill="{FILL.get(c["program"], "#999")}" '
                               f'stroke="#3a2a20" stroke-width="0.8"/>')
            for c in r["cells"]:
                if c["program"] == "room" and c["level"] == k and c["name"] in r.get("positions", {}):
                    x, y = pt(r["positions"][c["name"]]).split(",")
                    out.append(f'<circle cx="{x}" cy="{y}" r="1.6"/><text x="{float(x) + 3:.1f}" y="{float(y) + 3:.1f}">{c["name"]}</text>')
            sc = r.get("scores", {})
            note = " · ".join(f"{label} {sc[k_]:.2f}" for k_, label in (("affinity", "wishes"), ("area_deviation", "area off"), ("regularity", "regular")) if k_ in sc)
            out.append(f'<text x="{ox:.0f}" y="{(rows - k - 1) * h + 14:.0f}" font-size="10">{r.get("kind", "")} · level {k} · {note}</text>')
    out.append("</svg>")
    return "\n".join(out)


def write_svg(solves: list[dict], path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(svg(solves))
    return path
