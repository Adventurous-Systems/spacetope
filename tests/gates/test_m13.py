"""M13 gate: Z3 cross-check of the relational model (design note C). Needs the dev dependency z3-solver."""
import pytest

z3 = pytest.importorskip("z3")

from bench.z3check import assignment_of, assignments, feasible  # noqa: E402
from spacetope.brief import Brief, load  # noqa: E402
from spacetope.solve.cpsat import CpsatParams, solve_cpsat  # noqa: E402
from spacetope.solve.registry import GENERATORS  # noqa: E402

pytestmark = [pytest.mark.gate_m13, pytest.mark.slow]

FOUR = {"name": "four_rooms", "spaces": [
    {"name": "hall", "w": 6, "l": 4, "h": 3, "program": "room"}, {"name": "study", "w": 3, "l": 3.5, "h": 3, "program": "room"},
    {"name": "bath", "w": 2, "l": 2.5, "h": 3, "program": "room"}, {"name": "bed", "w": 4, "l": 4.5, "h": 3, "program": "room"}],
    "contacts": [["hall", "study"], ["hall", "bath"], ["hall", "bed"]]}


def _cpsat_assignments(brief, k=600, limit=240.0):
    res = solve_cpsat(brief, CpsatParams(k=k, time_limit=limit, per_solve_max=5.0, w_stack=0))
    return res, {assignment_of(brief, pl) for pl in res.placements}


@pytest.mark.parametrize("brief", [pytest.param(None, id="three_rooms"), pytest.param(FOUR, id="four_rooms")])
def test_z3_and_cpsat_enumerate_the_same_assignments(fixtures_dir, brief):
    b = load(fixtures_dir / "three_rooms.yaml") if brief is None else Brief.from_dict(brief)
    zs = assignments(b, cap=1024)
    res, cs = _cpsat_assignments(b)
    assert zs, "Z3 found nothing"
    assert cs <= zs, sorted(cs - zs)[:3]                  # everything CP-SAT builds, Z3 also finds
    # CP-SAT blocks on the same required-touch vector and ran to exhaustion: the sets must be equal
    assert res.statuses[-1] == "INFEASIBLE", res.statuses[-3:]
    assert cs == zs, (len(cs), len(zs), sorted(zs - cs)[:3])
    assert len(zs) == 4 ** len(b.contacts) or len(zs) < 4 ** len(b.contacts)


def test_contradictory_brief_is_unsat_in_both():
    d = {"name": "too_many_neighbours", "spaces": [{"name": "a", "w": 1, "l": 1, "h": 3, "program": "room", "tol": 0.0}] +
         [{"name": n, "w": 4, "l": 4, "h": 3, "program": "room", "tol": 0.0} for n in "bcdef"],
         "contacts": [["a", n] for n in "bcdef"]}
    brief = Brief.from_dict(d)
    assert feasible(brief) == "unsat"
    assert solve_cpsat(brief, CpsatParams(k=2, time_limit=20.0)).status == "INFEASIBLE"


def test_dual_options_are_inside_the_z3_set(fixtures_dir):
    b = load(fixtures_dir / "three_rooms.yaml")
    zs = assignments(b, cap=1024)
    pls = GENERATORS["dual"](b, {"k": 4, "time_limit": 30.0}, 0)
    assert pls and all(assignment_of(b, pl) in zs for pl in pls)
    beam = GENERATORS["beam"](b, None, 0)
    assert beam and all(assignment_of(b, pl) in zs for pl in beam)
