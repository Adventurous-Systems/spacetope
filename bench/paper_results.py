# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Adventurous Systems

"""The paper's tables, computed from the recorded runs under `bench/paper/` and written into
`RESULTS.md` through its template.

`RESULTS.in.md` holds the prose with `{{name}}` placeholders; this fills each with a Markdown table
or a number and writes `RESULTS.md`, so no figure in the text is typed by hand. Statistics follow
the experiments brief: mean and standard deviation over seeds, Wilson 95 % intervals for every
proportion, paired Wilcoxon signed-rank tests on the same fixture and seed, and no mean pooled over
fixtures of different sizes.

Usage, from the repository root:
  .venv/bin/python bench/paper_results.py bench/paper
"""
from __future__ import annotations

import csv
import re
import statistics as st
import sys
from collections import Counter, defaultdict
from math import sqrt
from pathlib import Path

from scipy.stats import wilcoxon

GENS = ("treemap", "beam", "cpsat", "dual")
CORE = ("three_rooms", "eight_rooms_corridor", "two_levels_stair")
METRICS = ("adjacency", "deviation", "compactness", "circulation", "stacking", "vertical", "envelope_fit",
           "daylight")
FAULT_ORDER = ("overlap_50mm", "shaft_half_height", "out_of_envelope", "gap_required", "shrink_room",
               "grow_out_of_band", "door_slide", "gap_incidental")
CHECKS = ("built", "cell_count", "no_slivers", "contacts", "dictionaries", "constraints", "doors",
          "required_contacts", "bands")


def rows(path: Path) -> list[dict]:
    with path.open() as f:
        return list(csv.DictReader(f))


def wilson(k: int, n: int) -> str:
    """k/n with its Wilson 95 % interval, as text."""
    if n == 0:
        return "–"
    z, p = 1.96, k / n
    mid = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    lo, hi = 100 * max(0.0, mid - half), 100 * min(1.0, mid + half)
    nd = 1 if n >= 200 else 0   # a large sample earns the decimal; without it 99.6 % prints as 100
    return f"{k}/{n} ({lo:.{nd}f}–{hi:.{nd}f} %)"


def table(head: list[str], body: list[list]) -> str:
    out = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in body]
    return "\n".join(out)


def ms(vals: list[float], nd: int = 2) -> str:
    if not vals:
        return "–"
    return f"{st.mean(vals):.{nd}f} ± {st.stdev(vals) if len(vals) > 1 else 0.0:.{nd}f}"


def pval(x: list[float], y: list[float]) -> str:
    if len(x) < 6 or all(a == b for a, b in zip(x, y)):
        return "–"
    p = wilcoxon(x, y).pvalue
    return "< 0.001" if p < 0.001 else f"{p:.3f}"


def spaces_of() -> dict[str, tuple[int, int]]:
    sys.path.insert(0, str(Path.cwd()))
    from spacetope.brief import load
    from spacetope.circulation import prepare
    out = {}
    for p in sorted(Path("fixtures").glob("*.yaml")):
        b, _ = prepare(load(p))
        out[p.stem] = (len(b.spaces), b.levels or 1)
    return out


# ----------------------------------------------------------------------------- E1, E1b, E1d

def faults_table(P: Path, name: str) -> str:
    by: dict[str, list[dict]] = defaultdict(list)
    for r in rows(P / name):
        by[r["transform"]].append(r)
    body = []
    for t in FAULT_ORDER:
        rs = by.get(t, [])
        if not rs:
            continue
        rej = [r for r in rs if r["verify"] != "True"]
        checks = Counter(c for r in rej for c in r["failed"].split())
        shown = ", ".join(f"`{c}` {checks[c]}" for c in CHECKS if checks[c]) or "none"
        body.append([f"`{t}`", rs[0]["kind"], len(rs), wilson(len(rej), len(rs)), shown,
                     sum(float(r["adjacency"]) < 1 for r in rs), sum(int(r["bands_violated"]) > 0 for r in rs)])
    return table(["fault", "kind", "placements", "rejected (Wilson 95 %)", "checks that failed (placements)",
                  "adjacency < 1", "out of band"], body)


def faults_by_kind(P: Path, name: str) -> dict[str, str]:
    by: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for r in rows(P / name):
        kind = "geometry + hard" if r["kind"] in ("geometry", "hard constraint") else r["kind"]
        by[kind][0] += r["verify"] != "True"
        by[kind][1] += 1
    return {k: wilson(*v) for k, v in by.items()}


def metamorphic_table(P: Path, name: str) -> str:
    by: dict[str, list[dict]] = defaultdict(list)
    for r in rows(P / name):
        by[r["transform"]].append(r)
    body = []
    for t in ("translate", "mirror_x", "mirror_y", "rotate", "shuffle", "swap_identical"):
        rs = by.get(t, [])
        n = len(rs)
        body.append([f"`{t}`", n, wilson(sum(r["verdict_unchanged"] == "True" for r in rs), n),
                     wilson(sum(r["same_topology_class"] == "True" for r in rs), n),
                     wilson(sum(r["scores_equal"] == "True" for r in rs), n)])
    return table(["relation", "placements", "verdict unchanged", "same topology class", "scores equal"], body)


def e1d_table(P: Path) -> str:
    body = []
    for r in rows(P / "e1d_confusion.csv"):
        body.append([r["source"].replace(".csv", ""), r["group"], r["placements"], r["both_accept"],
                     r["both_reject"], r["false_accept"], r["false_reject"]])
    return table(["source", "group", "placements", "both accept", "both reject", "pre-verifier accepts, kernel rejects",
                  "pre-verifier rejects, kernel accepts"], body)


# ----------------------------------------------------------------------------- E2, E3

def board(P: Path, name: str) -> dict[tuple[str, str], list[dict]]:
    out: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in rows(P / name):
        out[(r["generator"], r["fixture"])].append(r)
    return out


def core_table(e2: dict) -> str:
    body = []
    for fx in CORE:
        for g in GENS:
            rs = e2.get((g, fx), [])
            if not rs:
                body.append([f"`{fx}`", g, "declines", "", "", "", "", ""])
                continue
            f = lambda k: [float(r[k]) for r in rs]  # noqa: E731
            body.append([f"`{fx}`", g, f"{ms(f('verified'), 1)} / {ms(f('options'), 1)}", ms(f("adjacency"), 3),
                         ms(f("deviation"), 3), ms(f("distinct_topologies"), 1), ms(f("t_gen")), ms(f("t_realise"))])
    return table(["fixture", "generator", "verified / options", "adjacency", "deviation", "topology classes",
                  "t_gen (s)", "t_realise (s)"], body)


def declined(P: Path) -> dict[tuple[str, str], str]:
    out: dict[tuple[str, str], Counter] = defaultdict(Counter)
    for line in (P / "e2_run.log").read_text().splitlines():
        m = re.match(r"\s+(\w+)\s+(\w+)\s+seed \d+: skipped \(\w+: (.*)\)", line)
        if m:
            why = m.group(3)
            short = ("single-level only" if "single-level" in why else
                     "rooms cannot tile within tolerance" if "cannot tile" in why else
                     "a wished contact encloses a room" if "enclosed" in why else
                     "no arrangement could be sized" if "arrangements" in why else why[:40])
            out[(m.group(1), m.group(2))][short] += 1
    return {k: "; ".join(f"{w} ({n})" if len(c) > 1 else w for w, n in c.most_common()) for k, c in out.items()}


def all_table(e2: dict, sizes: dict, why: dict) -> str:
    body = []
    for fx in sorted(sizes, key=lambda f: sizes[f]):
        row = [f"`{fx}`", sizes[fx][0], sizes[fx][1]]
        for g in GENS:
            rs = e2.get((g, fx), [])
            cell = ""
            if rs:
                v, o = sum(int(r["verified"]) for r in rs), sum(int(r["options"]) for r in rs)
                cell = (f"{v}/{o} · {st.mean(float(r['distinct_topologies']) for r in rs):.1f} · "
                        f"{st.mean(float(r['t_gen']) for r in rs):.1f} s")
                if len(rs) < 5:
                    cell += f" ({len(rs)} of 5 seeds)"
            if (g, fx) in why:
                cell = (cell + "; " if cell else "") + f"declines: {why[(g, fx)]}"
            row.append(cell)
        body.append(row)
    return table(["fixture", "spaces", "levels", *GENS], body)


def scaling_table(e2: dict, sizes: dict) -> str:
    body = []
    for fx in sorted(sizes, key=lambda f: sizes[f]):
        row = [f"`{fx}`", sizes[fx][0]]
        for g in ("beam", "cpsat"):
            rs = e2.get((g, fx), [])
            row += [ms([float(r["t_gen"]) for r in rs]), ms([float(r["t_realise"]) for r in rs])]
        body.append(row)
    return table(["fixture", "spaces", "beam t_gen (s)", "beam t_realise (s)", "cpsat t_gen (s)",
                  "cpsat t_realise (s)"], body)


def paired(e2: dict, a: str, b: str) -> str:
    cells_a = {(r["fixture"], r["seed"]): r for (g, _), rs in e2.items() if g == a for r in rs}
    cells_b = {(r["fixture"], r["seed"]): r for (g, _), rs in e2.items() if g == b for r in rs}
    keys = sorted(set(cells_a) & set(cells_b))
    body = []
    for label, fn in (("verified share", lambda r: int(r["verified"]) / max(1, int(r["options"]))),
                      ("adjacency", lambda r: float(r["adjacency"])), ("deviation", lambda r: float(r["deviation"])),
                      ("topology classes", lambda r: float(r["distinct_topologies"])),
                      ("t_gen (s)", lambda r: float(r["t_gen"]))):
        x, y = [fn(cells_a[k]) for k in keys], [fn(cells_b[k]) for k in keys]
        body.append([label, len(keys), sum(p > q for p, q in zip(x, y)), sum(p < q for p, q in zip(x, y)),
                     sum(p == q for p, q in zip(x, y)), pval(x, y)])
    return table(["measure", "paired cells", f"{a} higher", f"{b} higher", "equal", "Wilcoxon p"], body)


# ----------------------------------------------------------------------------- E10

def spread_table(P: Path) -> str:
    by: dict[str, list[dict]] = defaultdict(list)
    for r in rows(P / "e10_discrimination.csv"):
        by[r["generator"]].append(r)
    body = []
    for g in ("beam", "cpsat", "dual"):
        rs = by[g]
        multi = [r for r in rs if int(r["verified_options"]) > 1]
        row = [g, f"{sum(int(r['distinct_score_vectors']) for r in rs)}/{sum(int(r['verified_options']) for r in rs)}",
               f"{sum(int(r['distinct_score_vectors']) == 1 for r in multi)} of {len(multi)}"]
        for m in METRICS:
            varies = sum(float(r[f"{m}_spread"]) > 0 for r in multi)
            row.append(f"{varies}/{len(multi)}, {max(float(r[f'{m}_spread']) for r in rs):.2f}")
        body.append(row)
    return table(["generator", "distinct score vectors / verified options", "calls where all options share one vector",
                  *METRICS], body)


def contacts_table(P: Path, sizes: dict) -> str:
    by: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in rows(P / "e10_discrimination.csv"):
        by[(r["generator"], r["fixture"])].append(r)
    body = []
    for fx in sorted(sizes, key=lambda f: sizes[f]):
        row = [f"`{fx}`", sizes[fx][0]]
        for g in ("beam", "cpsat", "dual"):
            rs = by.get((g, fx), [])
            if not rs:
                row.append("")
                continue
            n = sum(int(r["verified_options"]) for r in rs)
            w = lambda k: sum(float(r[k]) * int(r["verified_options"]) for r in rs) / n  # noqa: E731
            row.append(f"{w('touching_pairs_mean'):.0f} · {w('required_pairs_mean'):.0f} · "
                       f"{w('unwished_room_room_mean'):.1f}")
        body.append(row)
    return table(["fixture", "spaces", "beam", "cpsat", "dual"], body)


def pairs_table(P: Path) -> str:
    tot: dict[tuple[str, str], list[float]] = defaultdict(lambda: [0.0, 0.0])
    opts: dict[str, int] = defaultdict(int)
    seen = set()
    for r in rows(P / "e10c_pairs.csv"):
        n = int(r["verified_options"])
        if (r["generator"], r["fixture"]) not in seen:
            seen.add((r["generator"], r["fixture"]))
            opts[r["generator"]] += n
        t = tot[(r["programme_pair"], r["generator"])]
        t[0] += float(r["unasked_mean"]) * n
        t[1] += float(r["required_mean"]) * n
    pairs = sorted({p for p, _ in tot}, key=lambda p: -sum(tot[(p, g)][0] for g in ("beam", "cpsat", "dual")))
    body = [[p] + [f"{tot[(p, g)][0]:.0f} ({tot[(p, g)][1]:.0f})" for g in ("beam", "cpsat", "dual")] for p in pairs]
    body.append(["verified options"] + [opts[g] for g in ("beam", "cpsat", "dual")])
    return table(["programme pair", "beam", "cpsat", "dual"], body)


# ----------------------------------------------------------------------------- E8

def ablation_table(e2: dict, e8: dict, sizes: dict, g: str) -> str:
    body = []
    for fx in sorted(sizes, key=lambda f: sizes[f]):
        a = {r["seed"]: r for r in e2.get((g, fx), [])}
        b = {r["seed"]: r for r in e8.get((g, fx), [])}
        seeds = sorted(set(a) & set(b))
        if not seeds:
            continue
        s = lambda d, k: sum(int(d[x][k]) for x in seeds)  # noqa: E731
        m = lambda d, k, nd=2: f"{st.mean(float(d[x][k]) for x in seeds):.{nd}f}"  # noqa: E731
        body.append([f"`{fx}`", sizes[fx][0], len(seeds), f"{s(a, 'verified')}/{s(a, 'options')}",
                     f"{s(b, 'verified')}/{s(b, 'options')}", m(a, "deviation", 4), m(b, "deviation", 4),
                     m(a, "distinct_topologies", 1), m(b, "distinct_topologies", 1), m(a, "t_gen"), m(b, "t_gen")])
    return table(["fixture", "spaces", "seeds", "verified E2", "verified ablated", "deviation E2", "deviation ablated",
                  "classes E2", "classes ablated", "t_gen E2 (s)", "t_gen ablated (s)"], body)


def ablation_tests(e2: dict, e8: dict) -> str:
    body = []
    for g, what in (("beam", "beam, `redim=False`"), ("cpsat", "cpsat, `warm_start=False`")):
        a = {(r["fixture"], r["seed"]): r for (gg, _), rs in e2.items() if gg == g for r in rs}
        b = {(r["fixture"], r["seed"]): r for (gg, _), rs in e8.items() if gg == g for r in rs}
        keys = sorted(set(a) & set(b))
        for k in ("verified", "adjacency", "deviation", "distinct_topologies", "t_gen"):
            x, y = [float(a[c][k]) for c in keys], [float(b[c][k]) for c in keys]
            body.append([what, k, len(keys), sum(q > p for p, q in zip(x, y)), sum(q < p for p, q in zip(x, y)),
                         pval(x, y)])
    return table(["ablation", "measure", "paired cells", "higher when ablated", "lower when ablated", "Wilcoxon p"],
                 body)


# ----------------------------------------------------------------------------- E9

def planted_table(P: Path, family: str) -> str:
    by: dict[tuple[str, str], list[dict]] = defaultdict(list)
    order: list[str] = []
    for r in rows(P / "e9_planted.csv"):
        if r["family"] != family or not r["generator"]:
            continue
        if r["point"] not in order:
            order.append(r["point"])
        by[(r["point"], r["generator"])].append(r)
    gens = [g for g in GENS if any((p, g) in by for p in order)]
    body = []
    for p in order:
        row = [p]
        for g in gens:
            rs = by.get((p, g), [])
            ran = [r for r in rs if r["status"] == "ok"]
            crashed = sum(r["status"].startswith("TypeError") for r in rs)
            if not ran:
                row.append("declines" if rs else "")
                continue
            cell = wilson(sum(r["solved"] == "True" for r in ran), len(ran))
            if g != "treemap":
                cell += f"; class {sum(r['planted_class_found'] == 'True' for r in ran)}"
            if g == "dual" and len(ran) < len(rs):
                cell += f"; declines {len(rs) - len(ran) - crashed}"
            if crashed:
                cell += f"; crashed {crashed}"
            row.append(cell)
        body.append(row)
    return table(["sweep point", *gens], body)


def planted_time(P: Path) -> str:
    by: dict[tuple[str, str, str], list[float]] = defaultdict(list)
    for r in rows(P / "e9_planted.csv"):
        if r["status"] == "ok" and r["swept"] in ("n", "rooms"):
            by[(r["family"], r["point"], r["generator"])].append(float(r["t_gen"]))
    pts = []
    for fam, p, _ in by:
        if (fam, p) not in pts:
            pts.append((fam, p))
    body = [[fam.upper(), p] + [ms(by.get((fam, p, g), []), 1) for g in ("beam", "cpsat", "dual")] for fam, p in pts]
    return table(["family", "point", "beam t_gen (s)", "cpsat t_gen (s)", "dual t_gen (s)"], body)


# ----------------------------------------------------------------------------- E14

def repro_table(P: Path) -> str:
    per: dict[tuple[str, str], list] = defaultdict(lambda: [0, 0, []])
    for r in rows(P / "e14_repro.csv"):
        c = per[(r["mode"], r["generator"])]
        c[0] += 1
        c[1] += r["identical"] == "True"
        c[2].append(float(r["jaccard_min"]))
    body = [[mode, g, wilson(per[(mode, g)][1], per[(mode, g)][0]), f"{st.mean(per[(mode, g)][2]):.2f}"]
            for mode in ("deterministic", "default") for g in GENS if (mode, g) in per]
    return table(["mode", "generator", "cells with identical options", "mean smallest overlap of option sets"], body)


def main() -> None:
    P = Path(sys.argv[1])
    sizes = spaces_of()
    e2, e8 = board(P, "scoreboard_e2.csv"), board(P, "e8_ablation.csv")
    v1 = faults_by_kind(P, "e1_faults.csv")
    v2 = faults_by_kind(P, "e1_faults_v2.csv")
    e9 = rows(P / "e9_planted.csv")
    fill = {
        "table_faults": faults_table(P, "e1_faults_v2.csv"),
        "table_faults_first": faults_table(P, "e1_faults.csv"),
        "table_metamorphic": metamorphic_table(P, "e1b_metamorphic_v2.csv"),
        "table_metamorphic_first": metamorphic_table(P, "e1b_metamorphic.csv"),
        "kind_geometry": v2.get("geometry + hard", "–"), "kind_brief": v2.get("brief", "–"),
        "kind_control": v2.get("control", "–"), "kind_control_first": v1.get("control", "–"),
        "n_placements": str(sum(r["transform"] == "none" for r in rows(P / "e1_faults_v2.csv"))),
        "table_e1d": e1d_table(P),
        "table_core": core_table(e2),
        "table_all": all_table(e2, sizes, declined(P)),
        "table_scaling": scaling_table(e2, sizes),
        "table_beam_cpsat": paired(e2, "beam", "cpsat"),
        "table_spread": spread_table(P),
        "table_contacts": contacts_table(P, sizes),
        "table_pairs": pairs_table(P),
        "table_ablation_beam": ablation_table(e2, e8, sizes, "beam"),
        "table_ablation_cpsat": ablation_table(e2, e8, sizes, "cpsat"),
        "table_ablation_tests": ablation_tests(e2, e8),
        "table_planted_a": planted_table(P, "a"),
        "table_planted_b": planted_table(P, "b"),
        "table_planted_time": planted_time(P),
        "e9_rows": str(len(e9)),
        "e9_crashed": str(sum(r["status"].startswith("TypeError") for r in e9)),
        "table_repro": repro_table(P),
        "e5": (P / "e5_z3.txt").read_text().strip(),
    }
    text = (P / "RESULTS.in.md").read_text()
    missing = set(re.findall(r"\{\{(\w+)\}\}", text)) - set(fill)
    if missing:
        sys.exit(f"RESULTS.in.md asks for unknown values: {sorted(missing)}")
    (P / "RESULTS.md").write_text(re.sub(r"\{\{(\w+)\}\}", lambda m: fill[m.group(1)], text))
    print(f"wrote {P / 'RESULTS.md'}")


if __name__ == "__main__":
    main()
