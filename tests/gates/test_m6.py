# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Adventurous Systems

"""M6 gate (research track; allowed to fail, outcome recorded in docs/PLAN.md §5).

Model A: learned move scorers inside beam search at width 8 — a linear scorer and a graph neural
network (PyTorch Geometric) trained on the same teacher data — each compared with the hand-weighted
beam at width 16 on the 20 held-out synthetic briefs, at equal or lower generation time.
Model B: not implemented yet.
"""
import json
import os
from pathlib import Path

import pytest

from spacetope.learn.dataset import check_row, option_row, read_rows, write_rows
from spacetope.learn.gnn import DEFAULT_GNN, GNNScorer
from spacetope.learn.scorer import DEFAULT_WEIGHTS, LinearScorer
from spacetope.pipeline import generate
from spacetope.solve.beam import BeamParams, beam_search
from spacetope.solve.multilevel import beam_multilevel
from spacetope.solve.registry import GENERATORS
from spacetope.synth import heldout_briefs, synth_brief

pytestmark = [pytest.mark.gate_m6, pytest.mark.slow]
LEARNED_WIDTH = int(os.environ.get("SPACETOPE_STUDENT_WIDTH", "8"))  # student width; the heuristic runs at 16
RESULTS = Path("bench/history/2026-09-13_m6_heldout_3way.json")


def learned_generator(width: int = LEARNED_WIDTH, kind: str = "linear"):
    kw = {"scorer": LinearScorer.load(DEFAULT_WEIGHTS)} if kind == "linear" else {"batch_scorer": GNNScorer.load(DEFAULT_GNN)}

    def gen(brief, params, seed):
        p = BeamParams(beam_width=width)
        if (brief.levels or 1) > 1 or brief.envelope:
            return beam_multilevel(brief, p, seed, **kw)
        return beam_search(brief, p, seed, **kw)
    return gen


def test_dataset_integrity(tmp_path):
    path = tmp_path / "rows.jsonl"
    for seed in (1, 2):
        brief = synth_brief(seed, n_spaces=10, levels=1)
        options, _, _ = generate(GENERATORS["beam"], brief, 0, {"k": 3}, "beam")
        write_rows((option_row(brief, o) for o in options if o.ok), path)
    rows = read_rows(path)
    assert len(rows) >= 4
    for r in rows:
        ok, why = check_row(r)
        assert ok, why


@pytest.fixture(scope="module")
def comparison():
    assert DEFAULT_WEIGHTS.exists() and DEFAULT_GNN.exists(), "train first: python -m spacetope.learn.train_all"
    linear, gnn = learned_generator(kind="linear"), learned_generator(kind="gnn")
    rows = []
    for brief in heldout_briefs():
        h_opts, h_tg, _ = generate(GENERATORS["beam"], brief, 0, None, "beam")
        h8_opts, h8_tg, _ = generate(GENERATORS["beam"], brief, 0, {"beam_width": LEARNED_WIDTH}, "beam_narrow")
        l_opts, l_tg, _ = generate(linear, brief, 0, None, "beam_linear")
        g_opts, g_tg, _ = generate(gnn, brief, 0, None, "beam_gnn")
        def summary(opts, tg):
            ok = [o for o in opts if o.ok]
            return {"verified": len(ok), "distinct": len({o.signature for o in ok}),
                    "adjacency": sum(o.scores["adjacency"] for o in ok) / len(ok) if ok else 0.0,
                    "deviation": sum(o.scores["deviation"] for o in ok) / len(ok) if ok else 1.0,
                    "t_gen": round(tg, 3)}
        rows.append({"brief": brief.name, "spaces": len(brief.spaces), "levels": brief.levels or 1,
                     "heuristic": summary(h_opts, h_tg), "learned": summary(l_opts, l_tg),
                     "gnn": summary(g_opts, g_tg),
                     # reported, not asserted: the hand-weighted beam at the student's width isolates what learning adds
                     "heuristic_narrow": summary(h8_opts, h8_tg)})
    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    RESULTS.write_text(json.dumps({"student_width": LEARNED_WIDTH, "heuristic_width": 16, "rows": rows}, indent=1))
    return rows


def _mean(rows, who, key):
    return sum(r[who][key] for r in rows) / len(rows)


def _check_against_heuristic(rows, who):
    assert all(r[who]["verified"] > 0 for r in rows), [r["brief"] for r in rows if r[who]["verified"] == 0]
    report = {k: (round(_mean(rows, who, k), 4), round(_mean(rows, "heuristic", k), 4))
              for k in ("t_gen", "distinct", "adjacency", "deviation")}
    assert report["t_gen"][0] <= report["t_gen"][1], report
    assert report["distinct"][0] >= report["distinct"][1], report
    assert report["adjacency"][0] >= report["adjacency"][1], report
    assert report["deviation"][0] <= report["deviation"][1], report


def test_learned_matches_heuristic_at_lower_cost(comparison):
    _check_against_heuristic(comparison, "learned")


def test_gnn_matches_heuristic_at_lower_cost(comparison):
    _check_against_heuristic(comparison, "gnn")


@pytest.mark.xfail(reason="Model B (graph-conditioned relation-set generator) is not implemented yet", strict=True)
def test_model_b_relation_sets_dimension_to_verified():
    from spacetope.learn import relation_generator  # noqa: F401  (does not exist yet)
