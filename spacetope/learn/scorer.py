# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Adventurous Systems

"""Model A (M6): a learned linear move scorer for beam search, trained by pairwise ranking.

Teacher: the hand-weighted beam at a wide beam width. For each step we keep the teacher's whole
candidate pool; a candidate is positive when its relation key is a subset of the relation key of
the teacher's best final layout (keys survive translation and re-dimensioning), negative otherwise.
Student: w . standardise(features) used as the beam score at a narrower width.
Pure numpy, no topologicpy in the loop.
"""
from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from ..brief import Brief
from ..placement import assembly_from_placement
from ..solve.beam import HSIDES, BeamParams, State, beam_search, contacts_key, planes
from ..solve.grid import Box, bounds, touches

FEATURES = ("req_frac", "access_frac", "contact_area", "half_perim", "dead", "dev_mean", "stack",
            "aspect", "corridor_free", "blocked", "progress")
DEFAULT_WEIGHTS = Path(__file__).with_name("weights.json")


def _free_length(box: Box, side: str, others: list[Box]) -> int:
    axis = "y" if side in ("+x", "-x") else "x"
    length = box.l if axis == "y" else box.w
    used = sum(touches(box, o, side)[0] for o in others if o is not box)
    return max(0, length - used)


def features(brief: Brief, st: State, progress: float, ref_planes=None) -> np.ndarray:
    placed = st.placed
    n = len(placed)
    boxes = list(placed.values())
    req = brief.required_pairs()
    rooms_total = sum(1 for s in brief.spaces if s.program == "room") or 1
    nominal_area = sum(s.nominal_mm("w") * s.nominal_mm("l") for s in brief.spaces) / 1e6
    bb = bounds(boxes)
    covered = sum(b.w * b.l for b in boxes) / 1e6
    dead = bb.w * bb.l / 1e6 - covered
    stack = 0.0
    if ref_planes:
        px, py = planes(boxes)
        tot = len(px) + len(py)
        stack = (len(px & ref_planes[0]) + len(py & ref_planes[1])) / tot if tot else 0.0
    aspect = min(4.0, max(bb.w, bb.l) / max(1, min(bb.w, bb.l)) - 1.0)
    # remaining capacity on corridor long sides, relative to corridor length
    free, cap = 0, 0
    for name, b in placed.items():
        if brief.space(name).program != "corridor":
            continue
        sides = ("+x", "-x") if b.l >= b.w else ("+y", "-y")
        for sd in sides:
            free += _free_length(b, sd, boxes)
            cap += b.l if b.l >= b.w else b.w
    corridor_free = free / cap if cap else 0.0
    # unplaced spaces whose placed required partners have no free horizontal wall left
    unplaced = [s.name for s in brief.spaces if s.name not in placed]
    blocked = 0
    for u in unplaced:
        partners = [b if a == u else a for a, b in brief.contacts if u in (a, b)]
        placed_partners = [q for q in partners if q in placed]
        if placed_partners and all(sum(_free_length(placed[q], sd, boxes) for sd in HSIDES) == 0 for q in placed_partners):
            blocked += 1
    return np.array([
        st.req_hit / max(1, len(req)),
        len(st.access) / rooms_total,
        st.area_mm2 / 1e6 / max(1.0, nominal_area),
        (bb.w + bb.l) / 1000 / max(1.0, math.sqrt(nominal_area)),
        dead / max(1.0, nominal_area),
        st.dev_sum / max(1, n),
        stack,
        aspect,
        corridor_free,
        blocked / max(1, len(unplaced)),
        progress,
    ], dtype=float)


@dataclass
class LinearScorer:
    w: np.ndarray
    mean: np.ndarray
    std: np.ndarray

    def __call__(self, brief: Brief, st: State, progress: float, ref_planes=None) -> float:
        x = (features(brief, st, progress, ref_planes) - self.mean) / self.std
        return float(self.w @ x)

    def save(self, path: str | Path, meta: dict | None = None) -> None:
        Path(path).write_text(json.dumps({"features": list(FEATURES), "w": self.w.tolist(), "mean": self.mean.tolist(),
                                          "std": self.std.tolist(), "meta": meta or {}}, indent=1))

    @classmethod
    def load(cls, path: str | Path = DEFAULT_WEIGHTS) -> "LinearScorer":
        d = json.loads(Path(path).read_text())
        if d["features"] != list(FEATURES):
            raise ValueError("weights were trained on a different feature set")
        return cls(np.array(d["w"]), np.array(d["mean"]), np.array(d["std"]))


def _final_quality(brief: Brief, placement: dict[str, Box]) -> float:
    """Cheap proxy of the ranking used downstream (no topologicpy): adjacency, deviation, compactness."""
    from ..score import adjacency, deviation
    pairs = assembly_from_placement(brief, placement).contact_pairs()
    bb = bounds(placement.values())
    area = sum(b.w * b.l for b in placement.values())
    fill = area / max(1, bb.w * bb.l)
    return 10 * adjacency(brief, pairs) - 5 * deviation(brief, placement) + 3 * fill


def teacher_examples(brief: Brief, seed: int, width: int = 48, max_pool: int = 200) -> list[tuple[np.ndarray, np.ndarray]]:
    """[(X_pos, X_neg)] per step from one teacher run on a single-level brief."""
    trace: list = []
    outs = beam_search(brief, BeamParams(beam_width=width, k=width), seed, normalise_output=False, redim=False, trace=trace)
    if not outs:
        return []
    best = max(outs, key=lambda pl: _final_quality(brief, pl))
    final_key = contacts_key(best)
    rng = random.Random(seed)
    groups = []
    for entry in trace:
        pool = entry["pool"]
        if len(pool) > max_pool:
            pos_pool = [s for s in pool if s.key <= final_key]
            neg_pool = [s for s in pool if not s.key <= final_key]
            pool = pos_pool + rng.sample(neg_pool, min(len(neg_pool), max_pool - len(pos_pool)))
        pos = [features(brief, s, entry["progress"], entry["ref_planes"]) for s in pool if s.key <= final_key]
        neg = [features(brief, s, entry["progress"], entry["ref_planes"]) for s in pool if not s.key <= final_key]
        if pos and neg:
            groups.append((np.array(pos), np.array(neg)))
    return groups


def train(groups: list[tuple[np.ndarray, np.ndarray]], epochs: int = 300, lr: float = 0.05, l2: float = 1e-3,
          pairs_per_group: int = 64, seed: int = 0) -> tuple[LinearScorer, dict]:
    """Pairwise logistic ranking: maximise sigma(w . (x_pos - x_neg)). Full-batch gradient descent."""
    rng = np.random.default_rng(seed)
    allx = np.vstack([np.vstack([p, n]) for p, n in groups])
    mean, std = allx.mean(0), allx.std(0) + 1e-9
    diffs = []
    for p, n in groups:
        k = min(pairs_per_group, len(p) * len(n))
        i = rng.integers(0, len(p), k); j = rng.integers(0, len(n), k)
        diffs.append(((p[i] - mean) / std) - ((n[j] - mean) / std))
    D = np.vstack(diffs)
    w = np.zeros(D.shape[1])
    history = []
    for ep in range(epochs):
        z = D @ w
        sig = 1 / (1 + np.exp(-np.clip(z, -30, 30)))
        loss = float(np.mean(np.log1p(np.exp(-np.clip(z, -30, 30)))) + l2 * w @ w)
        grad = -(D * (1 - sig)[:, None]).mean(0) + 2 * l2 * w
        w -= lr * grad
        if ep % 50 == 0 or ep == epochs - 1:
            history.append({"epoch": ep, "loss": round(loss, 5), "pair_acc": round(float((z > 0).mean()), 4)})
    return LinearScorer(w, mean, std), {"pairs": int(len(D)), "groups": len(groups), "history": history}
