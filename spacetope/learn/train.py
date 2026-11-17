# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Adventurous Systems

"""Train Model A: python -m spacetope.learn.train [--briefs 40] [--width 48] [--out spacetope/learn/weights.json]

Training briefs are single-level synthetic briefs from seeds disjoint from the held-out set.
"""
from __future__ import annotations

import argparse
import json
import time

import numpy as np

from ..synth import synth_brief
from .scorer import DEFAULT_WEIGHTS, FEATURES, teacher_examples, train


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--briefs", type=int, default=40)
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--width", type=int, default=48)
    ap.add_argument("--min-spaces", type=int, default=8)
    ap.add_argument("--max-spaces", type=int, default=20)
    ap.add_argument("--out", default=str(DEFAULT_WEIGHTS))
    args = ap.parse_args(argv)
    rng = np.random.default_rng(args.start)
    groups = []
    t0 = time.time()
    for i in range(args.briefs):
        seed = args.start + i
        n = int(rng.integers(args.min_spaces, args.max_spaces + 1))
        brief = synth_brief(seed, n_spaces=n, levels=1)
        t = time.time()
        g = teacher_examples(brief, seed, width=args.width)
        groups.extend(g)
        pos = sum(len(p) for p, _ in g); neg = sum(len(q) for _, q in g)
        print(f"brief {i + 1}/{args.briefs} seed={seed} spaces={len(brief.spaces)} steps={len(g)} pos={pos} neg={neg} {time.time() - t:.1f}s", flush=True)
    if not groups:
        raise SystemExit("no training groups produced")
    scorer, info = train(groups)
    meta = {"briefs": args.briefs, "start": args.start, "teacher_width": args.width, "seconds": round(time.time() - t0, 1), **info,
            "weights": dict(zip(FEATURES, [round(float(x), 4) for x in scorer.w]))}
    scorer.save(args.out, meta)
    print(json.dumps(meta, indent=1), flush=True)


if __name__ == "__main__":
    main()
