"""Generate -> realise -> verify -> score -> rank. Produces Options and scoreboard rows."""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from .brief import Brief
from .placement import Placement, assembly_from_placement, space_graph, topology_classes  # noqa: F401 (re-exported)
from .realise import Realised
from .score import METRICS, analysis, score
from .verify import VerifyReport, verify


@dataclass
class Option:
    placement: Placement
    signature: tuple
    report: VerifyReport
    scores: dict[str, float] = field(default_factory=dict)
    generator: str = ""
    seed: int = 0
    analysis: dict = field(default_factory=dict)   # reported, not ranked (PLAN M9)

    @property
    def ok(self) -> bool:
        return self.report.ok

    @property
    def realised(self) -> Realised | None:
        return self.report.realised

    def to_dict(self) -> dict:
        return {"generator": self.generator, "seed": self.seed, "ok": self.ok, "scores": self.scores, "analysis": self.analysis,
                "signature": [list(s) for s in self.signature],
                "placement": {n: b.to_dict() for n, b in self.placement.items()},
                "verify": self.report.to_dict()}


def evaluate_placements(brief: Brief, placements: list[Placement], generator: str = "", seed: int = 0) -> list[Option]:
    opts = []
    for pl in placements:
        intent = assembly_from_placement(brief, pl)
        rep = verify(brief, pl, intent)
        sc = score(rep.realised) if rep.ok and rep.realised else {}
        an = analysis(rep.realised) if rep.ok and rep.realised else {}
        opts.append(Option(pl, intent.signature(), rep, sc, generator, seed, an))
    return opts


def rank(options: list[Option], weights: dict[str, float] | None = None) -> list[Option]:
    w = {"adjacency": 10, "deviation": -5, "compactness": 3, "circulation": -1, "stacking": 1,
         "vertical": 10, "envelope_fit": 0, "daylight": 2}
    if weights:
        w.update(weights)
    def key(o: Option) -> float:
        return sum(w[m] * o.scores.get(m, 0.0) for m in METRICS) if o.ok else -1e9
    return sorted(options, key=key, reverse=True)


RANK_WEIGHTS = {"adjacency": 10, "deviation": -5, "compactness": 3, "circulation": -1, "stacking": 1,
                "vertical": 10, "envelope_fit": 0, "daylight": 2}


def evaluate_top(brief: Brief, placements: list[Placement], generator: str = "", seed: int = 0, keep: int = 3) -> tuple[list[Option], dict]:
    """PLAN M10: pre-verify every placement on integer boxes, rank on box-only scores, and build geometry only
    until `keep` options have passed the full verifier. Returns the built options and what was skipped."""
    from .score import cheap_scores
    from .verify import preverify
    passed = []
    rejected = 0
    for pl in placements:
        ok, _ = preverify(brief, pl)
        if ok:
            sc = cheap_scores(brief, pl)
            passed.append((sum(RANK_WEIGHTS[k] * sc.get(k, 0.0) for k in METRICS), pl))
        else:
            rejected += 1
    passed.sort(key=lambda t: t[0], reverse=True)
    out: list[Option] = []
    seen: set = set()
    built = 0
    for _, pl in passed:
        if sum(1 for o in out if o.ok) >= keep:
            break
        intent = assembly_from_placement(brief, pl)
        sig = intent.signature()
        if sig in seen:
            continue
        seen.add(sig)
        out.extend(evaluate_placements(brief, [pl], generator, seed)); built += 1
    return out, {"placements": len(placements), "prerejected": rejected, "built": built, "skipped": len(passed) - built}


def generate(gen, brief: Brief, seed: int = 0, params: dict | None = None, name: str = "",
             build: str = "all", keep: int = 3) -> tuple[list[Option], float, float]:
    if not brief.expanded:  # every brief is validated; circulation sections are expanded (M7)
        from .circulation import prepare
        brief, _ = prepare(brief)  # raises BriefInvalid with plain messages
    t0 = time.perf_counter()
    placements = gen(brief, params, seed)
    t_gen = time.perf_counter() - t0
    t1 = time.perf_counter()
    if build == "top":
        options, _info = evaluate_top(brief, placements, name, seed, keep)
    else:
        options = evaluate_placements(brief, placements, name, seed)
    t_real = time.perf_counter() - t1
    return options, t_gen, t_real


def run_generator(gen, brief: Brief, seed: int = 0, params: dict | None = None, name: str = "") -> dict:
    options, t_gen, t_real = generate(gen, brief, seed, params, name)
    ok = [o for o in options if o.ok]
    distinct = len({o.signature for o in ok})
    expanded = ok[0].realised.brief if ok and ok[0].realised is not None else brief
    distinct_topologies = len(set(topology_classes(expanded, [o.placement for o in ok]))) if ok else 0
    def mean(metric: str) -> float:
        return round(sum(o.scores[metric] for o in ok) / len(ok), 4) if ok else 0.0
    return {"options": len(options), "verified": len(ok), "distinct": distinct, "distinct_topologies": distinct_topologies,
            **{m: mean(m) for m in METRICS}, "t_gen": round(t_gen, 3), "t_realise": round(t_real, 3)}
