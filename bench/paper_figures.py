# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Adventurous Systems

"""The paper's three figures, from the recorded runs under `bench/paper/`, as SVG and PNG.

  e3_scaling   generation and realisation time against the number of spaces, per generator, log scales
  e9_success   share of planted briefs solved against each swept parameter, with Wilson 95 % bands
  e10_spread   how far each score varies across the options of one call, per generator

Needs matplotlib, which is not a spacetope dependency: run it from any environment that has it.

Usage, from the repository root:
  python bench/paper_figures.py bench/paper bench/paper/figures
"""
from __future__ import annotations

import csv
import re
import sys
from collections import defaultdict
from math import sqrt
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

COLOUR = {"treemap": "#8a8a8a", "beam": "#1b6ca8", "cpsat": "#c1440e", "dual": "#3a7d44"}
MARK = {"treemap": "x", "beam": "o", "cpsat": "s", "dual": "^"}
METRICS = ("adjacency", "deviation", "compactness", "circulation", "stacking", "vertical", "envelope_fit",
           "daylight")
plt.rcParams.update({"font.size": 9, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.grid": True, "grid.alpha": 0.25, "svg.fonttype": "none"})


def rows(path: Path) -> list[dict]:
    with path.open() as f:
        return list(csv.DictReader(f))


def wilson(k: int, n: int) -> tuple[float, float, float]:
    z, p = 1.96, k / n
    mid = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return p, max(0.0, mid - half), min(1.0, mid + half)


def save(fig, out: Path, name: str) -> None:
    fig.tight_layout()
    for ext in ("svg", "png"):
        fig.savefig(out / f"{name}.{ext}", dpi=200)
    plt.close(fig)
    print(f"wrote {out / name}.svg and .png")


def spaces_of(P: Path) -> dict[str, int]:
    """Spaces per fixture after expansion, read from the saved placements (no spacetope import needed)."""
    import json
    out = {}
    for d in sorted((P / "placements" / "beam").iterdir()):
        first = next(iter(sorted(d.glob("*.json"))), None)
        if first:
            meta = json.loads(first.read_text())
            out[d.name] = len(meta.get("boxes") or meta.get("placement") or meta.get("spaces") or [])
    return out


def e3(P: Path, out: Path) -> None:
    sizes = spaces_of(P)
    by: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in rows(P / "scoreboard_e2.csv"):
        by[(r["generator"], r["fixture"])].append(r)
    fig, axes = plt.subplots(1, 2, figsize=(7.2, 3.2), sharex=True)
    for ax, key, title in zip(axes, ("t_gen", "t_realise"), ("generation", "realisation and verification")):
        for g in ("treemap", "beam", "cpsat", "dual"):
            pts = sorted((sizes[fx], sum(float(r[key]) for r in rs) / len(rs))
                         for (gg, fx), rs in by.items() if gg == g and fx in sizes)
            pts = [(x, max(y, 1e-3)) for x, y in pts]   # the treemap's generation time rounds to 0: drawn at 1 ms
            ax.plot([x for x, _ in pts], [y for _, y in pts], MARK[g], color=COLOUR[g], label=g, ms=4.5,
                    ls="-" if g in ("beam", "cpsat") else "", lw=0.8, alpha=0.9)
        ax.set_xscale("log"); ax.set_yscale("log")
        ax.set_xticks([3, 5, 10, 20, 30, 60]); ax.set_xticklabels(["3", "5", "10", "20", "30", "60"])
        ax.minorticks_off()
        ax.set_xlabel("spaces in the brief"); ax.set_title(title, fontsize=9)
    axes[0].set_ylabel("seconds per call, mean of 5 seeds")
    axes[0].legend(frameon=False, fontsize=8)
    save(fig, out, "e3_scaling")


def e9(P: Path, out: Path) -> None:
    data = [r for r in rows(P / "e9_planted.csv") if r["generator"]]
    panels = [("a", "n", "rooms (family A)"), ("a", "t", "tolerance t (A)"), ("a", "rho", "share of contacts required ρ (A)"),
              ("a", "slicing", "slicing (A)"), ("b", "rooms", "rooms (family B)"), ("b", "t", "tolerance t (B)"),
              ("b", "frontage", "frontage ratio (B)"), ("b", "shape", "corridor shape (B)"), ("b", "levels", "levels (B)")]
    base = {"a": {"n": "9", "t": "0.1", "rho": "0.5", "slicing": "True"},
            "b": {"rooms": "16", "t": "0.1", "frontage": "0.75", "shape": "straight", "levels": "1"}}
    fig, axes = plt.subplots(3, 3, figsize=(7.6, 6.6), sharey=True)
    for ax, (fam, swept, title) in zip(axes.flat, panels):
        cells: dict[tuple[str, str], list[int]] = defaultdict(lambda: [0, 0])
        for r in data:
            if r["family"] != fam or r["status"] != "ok":
                continue
            if r["swept"] == swept:
                value = r["point"].split("=", 1)[1] if "=" in r["point"] else base[fam][swept]
            elif r["point"] == "base":
                value = base[fam][swept]
            else:
                continue
            c = cells[(r["generator"], value)]
            c[0] += r["solved"] == "True"; c[1] += 1
        values = sorted({v for _, v in cells}, key=lambda v: (0, float(v)) if re.fullmatch(r"[\d.]+", v) else (1, v))
        for g in ("treemap", "beam", "cpsat", "dual"):
            xs, ys, lo, hi = [], [], [], []
            for i, v in enumerate(values):
                if (g, v) in cells and cells[(g, v)][1] >= 5:
                    p, a, b = wilson(*cells[(g, v)])
                    xs.append(i); ys.append(p); lo.append(a); hi.append(b)
            if xs:
                ax.fill_between(xs, lo, hi, color=COLOUR[g], alpha=0.12, lw=0)
                ax.plot(xs, ys, MARK[g] + "-", color=COLOUR[g], ms=4, lw=0.9, label=g)
        ax.set_xticks(range(len(values))); ax.set_xticklabels(values)
        ax.set_ylim(-0.04, 1.04); ax.set_title(title, fontsize=8.5)
    for ax in axes[:, 0]:
        ax.set_ylabel("briefs solved")
    axes[1, 0].legend(frameon=False, fontsize=7.5, loc="center")
    save(fig, out, "e9_success")


def e10(P: Path, out: Path) -> None:
    data = [r for r in rows(P / "e10_discrimination.csv") if int(r["verified_options"]) > 1]
    gens = ("beam", "cpsat", "dual")
    fig, ax = plt.subplots(figsize=(7.2, 3.2))
    for j, g in enumerate(gens):
        rs = [r for r in data if r["generator"] == g]
        box = ax.boxplot([[float(r[f"{m}_spread"]) for r in rs] for m in METRICS],
                         positions=[i + (j - 1) * 0.26 for i in range(len(METRICS))], widths=0.22,
                         patch_artist=True, flierprops={"ms": 2.5, "marker": "o", "mfc": COLOUR[g], "mec": "none"},
                         medianprops={"color": "black", "lw": 0.9}, whiskerprops={"color": COLOUR[g]},
                         capprops={"color": COLOUR[g]}, boxprops={"facecolor": COLOUR[g], "alpha": 0.55, "lw": 0})
        box["boxes"][0].set_label(f"{g} ({len(rs)} calls)")
    ax.set_xticks(range(len(METRICS))); ax.set_xticklabels(METRICS, rotation=20, ha="right")
    ax.set_ylabel("largest − smallest score\nacross the options of one call")
    ax.legend(frameon=False, fontsize=8)
    save(fig, out, "e10_spread")


def main() -> None:
    P, out = Path(sys.argv[1]), Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    e3(P, out)
    e9(P, out)
    e10(P, out)


if __name__ == "__main__":
    main()
