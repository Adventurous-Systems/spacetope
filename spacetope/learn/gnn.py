# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Adventurous Systems

"""Model A' (M6): a graph neural network move scorer (PyTorch Geometric).

Each candidate beam state becomes a graph over ALL spaces of the level being assembled:
  nodes  = spaces; features = program one-hot, placed flag, nominal w/l (m/10), deviation,
           free horizontal wall length per side (fraction), number of required partners, number
           placed, level-plane alignment for placed boxes (stacking signal)
  edges  = realised contacts (type 0) and required contacts from the brief (type 1), both directions
The GNN embeds nodes with two relational GraphConv layers, mean- and max-pools placed nodes, and
concatenates the standardised linear features (spacetope.learn.scorer.features) before an MLP head.
Trained with the same pairwise ranking loss and teacher labels as the linear scorer.
"""
from __future__ import annotations

import json
import math
import random
import time
from pathlib import Path

import numpy as np
import torch
from torch import nn
from torch_geometric.data import Batch, Data
from torch_geometric.nn import RGCNConv, global_max_pool, global_mean_pool

from ..brief import PROGRAMS, Brief
from ..solve.beam import HSIDES, State, planes
from .scorer import FEATURES, _free_length, features

NODE_DIM = len(PROGRAMS) + 1 + 2 + 1 + 4 + 2 + 1
GLOBAL_DIM = len(FEATURES)
DEFAULT_GNN = Path(__file__).with_name("gnn.pt")
torch.set_num_threads(max(1, min(8, torch.get_num_threads())))


def state_graph(brief: Brief, st: State, progress: float, ref_planes, gmean=None, gstd=None) -> Data:
    placed = st.placed
    names = [s.name for s in brief.spaces if s.name in placed] + [s.name for s in brief.spaces if s.name not in placed]
    # restrict to the spaces on the level(s) present in the state plus unplaced spaces sharing a required contact
    idx = {n: i for i, n in enumerate(names)}
    boxes = list(placed.values())
    rx, ry = (ref_planes or (set(), set()))
    x = np.zeros((len(names), NODE_DIM), dtype=np.float32)
    req_deg: dict[str, int] = {}
    for a, b in brief.contacts:
        req_deg[a] = req_deg.get(a, 0) + 1; req_deg[b] = req_deg.get(b, 0) + 1
    for n, i in idx.items():
        sp = brief.space(n)
        x[i, PROGRAMS.index(sp.program)] = 1.0
        o = len(PROGRAMS)
        x[i, o + 1] = sp.w / 10.0; x[i, o + 2] = sp.l / 10.0
        x[i, o + 9] = req_deg.get(n, 0) / 10.0
        if n in placed:
            b = placed[n]
            x[i, o] = 1.0
            nw, nl = sp.nominal_mm("w"), sp.nominal_mm("l")
            x[i, o + 3] = min(abs(b.w - nw) / nw + abs(b.l - nl) / nl, abs(b.w - nl) / nl + abs(b.l - nw) / nw)
            for k, sd in enumerate(HSIDES):
                length = b.l if sd in ("+x", "-x") else b.w
                x[i, o + 4 + k] = _free_length(b, sd, boxes) / max(1, length)
            if ref_planes:
                hits = (b.x in rx) + (b.x1 in rx) + (b.y in ry) + (b.y1 in ry)
                x[i, o + 10] = hits / 4.0
        partners = [q for a, q2 in brief.contacts for q in ((q2,) if a == n else (a,) if q2 == n else ())]
        x[i, o + 8] = sum(1 for q in partners if q in placed) / max(1, len(partners))
    src, dst, typ = [], [], []
    for (a, _side, b) in st.key:
        if a in idx and b in idx:
            src += [idx[a], idx[b]]; dst += [idx[b], idx[a]]; typ += [0, 0]
    for a, b in brief.contacts:
        if a in idx and b in idx:
            src += [idx[a], idx[b]]; dst += [idx[b], idx[a]]; typ += [1, 1]
    g = features(brief, st, progress, ref_planes).astype(np.float32)
    if gmean is not None:
        g = (g - gmean) / gstd
    data = Data(x=torch.from_numpy(x),
                edge_index=torch.tensor([src, dst], dtype=torch.long) if src else torch.zeros((2, 0), dtype=torch.long),
                edge_type=torch.tensor(typ, dtype=torch.long),
                placed=torch.from_numpy(x[:, len(PROGRAMS)] > 0.5),
                g=torch.from_numpy(g).unsqueeze(0))
    return data


class MoveGNN(nn.Module):
    def __init__(self, hidden: int = 48):
        super().__init__()
        self.inp = nn.Linear(NODE_DIM, hidden)
        self.c1 = RGCNConv(hidden, hidden, num_relations=2)
        self.c2 = RGCNConv(hidden, hidden, num_relations=2)
        self.head = nn.Sequential(nn.Linear(2 * hidden + GLOBAL_DIM, hidden), nn.ReLU(), nn.Linear(hidden, 1))
        self.lin_skip = nn.Linear(GLOBAL_DIM, 1)   # linear path: the model starts no worse than a linear scorer

    def forward(self, batch: Batch) -> torch.Tensor:
        h = torch.relu(self.inp(batch.x))
        h = torch.relu(self.c1(h, batch.edge_index, batch.edge_type)) + h
        h = torch.relu(self.c2(h, batch.edge_index, batch.edge_type)) + h
        mask = batch.placed
        hp, bp = h[mask], batch.batch[mask]
        n_graphs = batch.num_graphs
        mean = global_mean_pool(hp, bp, size=n_graphs)
        mx = global_max_pool(hp, bp, size=n_graphs)
        z = torch.cat([mean, mx, batch.g], dim=1)
        return (self.head(z) + self.lin_skip(batch.g)).squeeze(-1)


class GNNScorer:
    """Batch scorer for beam_search(batch_scorer=...)."""

    def __init__(self, model: MoveGNN, gmean: np.ndarray, gstd: np.ndarray):
        self.model = model.eval()
        self.gmean, self.gstd = gmean.astype(np.float32), gstd.astype(np.float32)

    @torch.no_grad()
    def __call__(self, brief: Brief, states: list[State], progress: float, ref_planes) -> list[float]:
        graphs = [state_graph(brief, s, progress, ref_planes, self.gmean, self.gstd) for s in states]
        return self.model(Batch.from_data_list(graphs)).tolist()

    def save(self, path: str | Path = DEFAULT_GNN, meta: dict | None = None) -> None:
        torch.save({"state_dict": self.model.state_dict(), "gmean": self.gmean, "gstd": self.gstd,
                    "hidden": self.model.inp.out_features, "features": list(FEATURES), "meta": meta or {}}, path)

    @classmethod
    def load(cls, path: str | Path = DEFAULT_GNN) -> "GNNScorer":
        ck = torch.load(path, weights_only=False)
        if ck["features"] != list(FEATURES):
            raise ValueError("GNN was trained on a different global feature set")
        m = MoveGNN(ck["hidden"]); m.load_state_dict(ck["state_dict"])
        return cls(m, np.asarray(ck["gmean"]), np.asarray(ck["gstd"]))


def train_gnn(groups: list[tuple[list[Data], list[Data]]], gmean: np.ndarray, gstd: np.ndarray, epochs: int = 12,
              pairs_per_group: int = 24, batch_pairs: int = 256, lr: float = 3e-3, seed: int = 0, hidden: int = 48,
              val_frac: float = 0.15) -> tuple[GNNScorer, dict]:
    """Pairwise ranking on (pos, neg) graph pairs; groups are split by brief step for validation."""
    torch.manual_seed(seed); rng = random.Random(seed)
    order = list(range(len(groups))); rng.shuffle(order)
    n_val = max(1, int(len(order) * val_frac)) if len(order) > 1 else 0  # one group: train on it, no validation
    val_ids, train_ids = set(order[:n_val]), order[n_val:]

    def sample_pairs(ids):
        pairs = []
        for gi in ids:
            pos, neg = groups[gi]
            for _ in range(min(pairs_per_group, len(pos) * len(neg))):
                pairs.append((rng.choice(pos), rng.choice(neg)))
        return pairs

    model = MoveGNN(hidden)
    opt = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=1e-5)
    val_pairs = sample_pairs(val_ids)
    history = []
    t0 = time.time()
    for ep in range(epochs):
        model.train(); pairs = sample_pairs(train_ids); rng.shuffle(pairs)
        tot, n = 0.0, 0
        for k in range(0, len(pairs), batch_pairs):
            chunk = pairs[k:k + batch_pairs]
            bp = Batch.from_data_list([p for p, _ in chunk]); bn = Batch.from_data_list([q for _, q in chunk])
            loss = nn.functional.softplus(-(model(bp) - model(bn))).mean()
            opt.zero_grad(); loss.backward(); opt.step()
            tot += float(loss) * len(chunk); n += len(chunk)
        model.eval()
        with torch.no_grad():
            correct = 0
            for k in range(0, len(val_pairs), 512):
                chunk = val_pairs[k:k + 512]
                correct += int(((model(Batch.from_data_list([p for p, _ in chunk])) -
                                 model(Batch.from_data_list([q for _, q in chunk]))) > 0).sum())
        history.append({"epoch": ep, "train_loss": round(tot / max(1, n), 4), "val_pair_acc": round(correct / max(1, len(val_pairs)), 4),
                        "seconds": round(time.time() - t0, 1)})
        print(json.dumps(history[-1]), flush=True)
    return GNNScorer(model, gmean, gstd), {"groups": len(groups), "val_groups": n_val, "val_pairs": len(val_pairs), "history": history}
