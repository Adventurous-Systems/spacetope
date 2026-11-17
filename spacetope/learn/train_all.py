# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Adventurous Systems

"""Train both learned move scorers on the same teacher data (single- and multi-level briefs).

python -m spacetope.learn.train_all [--single 30] [--multi 20] [--max-pool 80]

Writes spacetope/learn/weights.json (linear) and spacetope/learn/gnn.pt (graph network).
Stops collecting briefs early if free disk space drops below --min-free-gb.
"""
from __future__ import annotations

import argparse
import json
import random
import shutil
from pathlib import Path
import time

import numpy as np
import torch

from ..solve.beam import BeamParams, beam_search, contacts_key
from ..solve.multilevel import beam_multilevel
from ..synth import synth_brief
from .gnn import DEFAULT_GNN, state_graph, train_gnn
from .scorer import DEFAULT_WEIGHTS, FEATURES, _final_quality, features, train


def teacher_run(brief, seed: int, width: int):
    trace: list = []
    p = BeamParams(beam_width=width, k=width)
    if (brief.levels or 1) > 1:
        outs = beam_multilevel(brief, p, seed, trace=trace)
    else:
        outs = beam_search(brief, p, seed, normalise_output=False, redim=False, trace=trace)
    return outs, trace


def collect(brief, seed: int, width: int, max_pool: int):
    outs, trace = teacher_run(brief, seed, width)
    if not outs:
        return [], []
    final_key = contacts_key(max(outs, key=lambda pl: _final_quality(brief, pl)))
    rng = random.Random(seed)
    lin, gnn = [], []
    for e in trace:
        pos = [s for s in e["pool"] if s.key <= final_key]
        neg = [s for s in e["pool"] if not s.key <= final_key]
        if not pos or not neg:
            continue
        neg = rng.sample(neg, min(len(neg), max(1, max_pool - len(pos))))
        pos = pos[:max_pool]
        fp = [features(brief, s, e["progress"], e["ref_planes"]) for s in pos]
        fn = [features(brief, s, e["progress"], e["ref_planes"]) for s in neg]
        lin.append((np.array(fp), np.array(fn)))
        gnn.append(([state_graph(brief, s, e["progress"], e["ref_planes"]) for s in pos],
                    [state_graph(brief, s, e["progress"], e["ref_planes"]) for s in neg]))
    return lin, gnn


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--single", type=int, default=30)
    ap.add_argument("--multi", type=int, default=20)
    ap.add_argument("--start", type=int, default=1000)
    ap.add_argument("--width", type=int, default=32)
    ap.add_argument("--max-pool", type=int, default=80)
    ap.add_argument("--epochs", type=int, default=12)
    ap.add_argument("--min-free-gb", type=float, default=1.5)
    args = ap.parse_args(argv)
    rng = np.random.default_rng(args.start)
    plan = [("single", args.start + i) for i in range(args.single)] + [("multi", args.start + 500 + i) for i in range(args.multi)]
    lin_groups, gnn_groups, used = [], [], []
    t0 = time.time()
    for kind, seed in plan:
        free_gb = shutil.disk_usage(Path(__file__).resolve().parent).free / 1e9
        if free_gb < args.min_free_gb:
            print(f"STOP collecting: free disk {free_gb:.2f} GB < {args.min_free_gb} GB", flush=True)
            break
        if kind == "single":
            brief = synth_brief(seed, n_spaces=int(rng.integers(8, 21)), levels=1)
        else:
            brief = synth_brief(seed, n_spaces=int(rng.integers(12, 25)), levels=int(rng.integers(2, 4)))
        t = time.time()
        lin, gnn = collect(brief, seed, args.width, args.max_pool)
        lin_groups.extend(lin); gnn_groups.extend(gnn); used.append(brief.name)
        print(f"{kind:6s} seed={seed} spaces={len(brief.spaces)} levels={brief.levels or 1} groups={len(lin)} "
              f"graphs={sum(len(p) + len(q) for p, q in gnn)} {time.time() - t:.1f}s free={free_gb:.2f}GB", flush=True)
    if not lin_groups:
        raise SystemExit("no training data collected")

    scorer, info = train(lin_groups)
    lin_meta = {"briefs": len(used), "teacher_width": args.width, **info,
                "weights": dict(zip(FEATURES, [round(float(x), 4) for x in scorer.w]))}
    scorer.save(DEFAULT_WEIGHTS, lin_meta)
    print("LINEAR", json.dumps({k: lin_meta[k] for k in ("briefs", "groups", "pairs")}), json.dumps(lin_meta["history"][-1]),
          json.dumps(lin_meta["weights"]), flush=True)

    gmean, gstd = scorer.mean.astype(np.float32), scorer.std.astype(np.float32)
    for pos, neg in gnn_groups:  # standardise the global features exactly as the linear model does
        for d in pos + neg:
            d.g = (d.g - torch.from_numpy(gmean)) / torch.from_numpy(gstd)
    gnn, ginfo = train_gnn(gnn_groups, gmean, gstd, epochs=args.epochs)
    gnn.save(DEFAULT_GNN, {"briefs": len(used), "teacher_width": args.width, **ginfo})
    print("GNN", json.dumps({k: ginfo[k] for k in ("groups", "val_groups", "val_pairs")}), json.dumps(ginfo["history"][-1]),
          f"total {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
