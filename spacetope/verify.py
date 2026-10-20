"""The six checks every option must pass before it is shown."""
from __future__ import annotations

from dataclasses import dataclass, field

from topologicpy.Cell import Cell
from topologicpy.Dictionary import Dictionary
from topologicpy.Edge import Edge
from topologicpy.Topology import Topology
from topologicpy.Vertex import Vertex

from .brief import Brief
from .levels import level_height_mm
from .placement import Placement, diagnose_contact, overlaps
from .preverify import check_constraints, preverify  # noqa: F401 (pure checks live in preverify.py; re-exported)
from .realise import Realised, RealiseError, realise
from .spacegraph import AssemblyGraph, Contact
from .units import to_m

CHECKS = ("built", "cell_count", "no_slivers", "contacts", "dictionaries", "constraints", "doors")
REQUIRED_KEYS = ("name", "program", "w", "l", "h")


@dataclass
class VerifyReport:
    ok: bool
    checks: dict[str, tuple[bool, str]]
    failed_contacts: list[dict] = field(default_factory=list)  # {"contact": [...], "cause": str}
    realised: Realised | None = None

    def to_dict(self) -> dict:
        return {"ok": self.ok, "checks": {k: {"passed": p, "detail": d} for k, (p, d) in self.checks.items()},
                "failed_contacts": self.failed_contacts}

    def causes(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for f in self.failed_contacts:
            out[f["cause"]] = out.get(f["cause"], 0) + 1
        return out


def _contact_failures(intent: AssemblyGraph, realised_contacts: set[Contact], placement: Placement) -> list[dict]:
    fails = []
    for c in intent.contacts():
        if c in realised_contacts:
            continue
        cause = diagnose_contact(c, placement)
        if cause == "ok":
            # geometry says the faces coincide; if the kernel still did not realise it, say so explicitly
            cause = "unrealised"
        fails.append({"contact": c.to_list(), "cause": cause})
    return fails


def _door_pairs_graph(cc) -> set:
    """Door pairs through topologicpy.Graph (the pre-M9 path, kept as the fallback)."""
    from topologicpy.Graph import Graph
    g = Graph.ByTopology(cc, direct=False, directApertures=True, silent=True)
    verts = Graph.Vertices(g) or []
    names = [Dictionary.ValueAtKey(Topology.Dictionary(v), "name") for v in verts]
    index = {tuple(round(c, 5) for c in Vertex.Coordinates(v)): n for v, n in zip(verts, names)}
    realised = set()
    for e in Graph.Edges(g) or []:
        a = index.get(tuple(round(c, 5) for c in Vertex.Coordinates(Edge.StartVertex(e))))
        b = index.get(tuple(round(c, 5) for c in Vertex.Coordinates(Edge.EndVertex(e))))
        if a and b:
            realised.add(frozenset((a, b)))
    return realised


def check_doors(brief: Brief, r: Realised) -> tuple[bool, str]:
    """M7.4: planned doors exist, sit on internal walls, match topologic's door graph, and give access."""
    if not brief.circulation:
        return True, "no doors required"
    from topologicpy.CellComplex import CellComplex
    from .doors import access_problems
    issues = [p.message for p in r.door_problems] + [p.message for p in access_problems(brief, r.placement, r.doors)]
    if not Topology.IsInstance(r.cc, "CellComplex"):
        return (not issues and not r.doors), "; ".join(issues) or "no complex to host doors"
    attached = Topology.Apertures(r.cc, subTopologyType="face") or []
    if len(attached) != len(r.doors):
        issues.append(f"{len(attached)} doors attached, {len(r.doors)} planned")
    internal = CellComplex.Decompose(r.cc)["internalVerticalApertures"]
    if len(internal) != len(attached):
        issues.append(f"{len(attached) - len(internal)} doors are not on internal walls")
    from .tgraph import door_pairs
    realised = door_pairs(r.cc)  # TGraph: same graph, ~4x faster (PLAN M9); None -> fall back to Graph
    if realised is None:
        realised = _door_pairs_graph(r.cc)
    planned = {d.pair for d in r.doors}
    for pair in sorted(planned - realised, key=sorted):
        issues.append("missing door: " + "–".join(sorted(pair)))
    for pair in sorted(realised - planned, key=sorted):
        issues.append("unexpected door: " + "–".join(sorted(pair)))
    return (not issues), ("; ".join(issues) if issues else f"{len(r.doors)} doors")


def verify(brief: Brief, placement: Placement, intent: AssemblyGraph | None = None) -> VerifyReport:
    from .placement import assembly_from_placement
    intent = intent or assembly_from_placement(brief, placement)
    checks: dict[str, tuple[bool, str]] = {}
    ov = overlaps(placement)
    try:
        r = realise(brief, placement, intent)
    except RealiseError as e:
        fails = [f for f in _contact_failures(intent, set(), placement) if f["cause"] != "unrealised"]
        if ov:
            for f in fails:
                if f["cause"] == "missing":
                    f["cause"] = "overlap" if tuple(sorted((f["contact"][0], f["contact"][2]))) in {tuple(sorted(p)) for p in ov} else f["cause"]
        checks["built"] = (False, str(e))
        for k in CHECKS[1:]:
            checks[k] = (False, "not built")
        return VerifyReport(False, checks, fails)

    checks["built"] = (True, f"{Topology.TypeAsString(r.cc)} in {r.build_seconds:.2f}s")
    n = len(brief.spaces)
    checks["cell_count"] = (r.n_cells == n, f"{r.n_cells} cells for {n} spaces" + (f"; overlapping pairs {ov}" if ov else ""))

    # slivers: every built cell volume must match exactly one placement box
    # compare sorted volumes pairwise with a tolerance of 1000 mm³: exact equality of two 6-decimal roundings
    # failed on rounding ties (review 2026-09-13, #8)
    expected = sorted(b.volume() / 1e9 for b in placement.values())
    actual = sorted(Cell.Volume(c) for c in r.cells)
    same_count = len(actual) == len(expected)
    slivers = [round(a_, 6) for a_, e_ in zip(actual, expected) if abs(a_ - e_) > 1e-6] if same_count else [round(a_, 6) for a_ in actual]
    ok = same_count and not slivers
    checks["no_slivers"] = (ok, "volumes match" if ok else f"unexpected volumes {slivers[:5]}")

    realised = set(r.realised_contacts())
    fails = _contact_failures(intent, realised, placement)
    checks["contacts"] = (not fails, f"{len(intent)} intended, {len(realised)} realised, {len(fails)} failed")

    missing_keys = []
    for c in r.cells:
        d = Topology.Dictionary(c)
        keys = set(Dictionary.Keys(d)) if d is not None else set()
        if not set(REQUIRED_KEYS) <= keys:
            missing_keys.append(sorted(set(REQUIRED_KEYS) - keys))
    checks["dictionaries"] = (not missing_keys, "all cells tagged" if not missing_keys else f"{len(missing_keys)} cells missing {missing_keys[0]}")

    checks["constraints"] = check_constraints(brief, placement)
    checks["doors"] = check_doors(brief, r)
    ok = all(p for p, _ in checks.values())
    return VerifyReport(ok, checks, fails, r)
