# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Adventurous Systems

"""E10c by programme pair, from the saved E2 placements, no regeneration: which contacts did
nobody ask for, and between which programmes?

For every *verified* saved placement, each touching pair of spaces is counted under the pair of
their programmes (room-room, corridor-room, room-stair, ...), split into pairs the brief requires
and pairs it does not. Touching is the pilot's definition (`bench/discrimination.py`): a positive
contact area on any of the six sides. One row per (generator, fixture, programme pair), with means
per option.

Usage, from the repository root:
  .venv/bin/python bench/e10c_pairs.py bench/paper/placements bench/paper/e10c_pairs.csv
"""
from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))
from spacetope.brief import load  # noqa: E402
from spacetope.circulation import prepare  # noqa: E402
from spacetope.placement import load_placement  # noqa: E402
from spacetope.solve.grid import contact_area  # noqa: E402

SIDES = ("+x", "-x", "+y", "-y", "ceiling", "floor")


def main() -> None:
    src, out = Path(sys.argv[1]), Path(sys.argv[2])
    briefs: dict[str, object] = {}
    options: dict[tuple[str, str], int] = defaultdict(int)
    counts: dict[tuple[str, str, str], list[int]] = defaultdict(lambda: [0, 0])  # [required, unasked]
    for path in sorted(src.glob("*/*/*.json")):
        meta = json.loads(path.read_text())
        if not meta.get("verified"):
            continue
        gen, fx = meta["generator"], meta["fixture"]
        if fx not in briefs:
            briefs[fx] = prepare(load(Path("fixtures") / f"{fx}.yaml"))[0]
        brief = briefs[fx]
        pl = load_placement(path)
        req = brief.required_pairs()
        names = list(pl)
        options[(gen, fx)] += 1
        for i, a in enumerate(names):
            for b in names[i + 1:]:
                if any(contact_area(pl[a], pl[b], s) > 0 for s in SIDES):
                    pair = "-".join(sorted((brief.space(a).program, brief.space(b).program)))
                    counts[(gen, fx, pair)][frozenset((a, b)) not in req] += 1

    rows = []
    for (gen, fx, pair), (required, unasked) in sorted(counts.items()):
        n = options[(gen, fx)]
        rows.append({"generator": gen, "fixture": fx, "programme_pair": pair, "verified_options": n,
                     "required_mean": round(required / n, 2), "unasked_mean": round(unasked / n, 2),
                     "unasked_share": round(unasked / (required + unasked), 4)})
    with out.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    print(f"wrote {len(rows)} rows to {out}\n\nunasked touching pairs per verified option, by programme pair")
    per: dict[tuple[str, str], list[int]] = defaultdict(lambda: [0, 0])
    for (gen, fx, pair), (_, unasked) in counts.items():
        per[(gen, pair)][0] += unasked
    for (gen, _fx), n in options.items():
        for key in per:
            if key[0] == gen:
                per[key][1] += n
    for (gen, pair), (unasked, n) in sorted(per.items()):
        print(f"  {gen:8s} {pair:20s} {unasked / n:6.2f}")


if __name__ == "__main__":
    main()
