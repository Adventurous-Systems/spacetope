"""M11 gate: cross-level alignment as a soft term in CP-SAT (design note A)."""
import pytest

from spacetope.brief import load
from spacetope.pipeline import generate
from spacetope.solve.registry import GENERATORS

pytestmark = [pytest.mark.gate_m11, pytest.mark.slow]


@pytest.mark.parametrize("fx", ("two_levels_stair", "three_levels_core", "apartments_four_levels"))
def test_cpsat_stacks_as_well_as_the_beam(fixtures_dir, fx):
    brief = load(fixtures_dir / f"{fx}.yaml")
    beam, _, _ = generate(GENERATORS["beam"], brief, 0, None, "beam")
    cps, t_gen, _ = generate(GENERATORS["cpsat"], brief, 0, {"k": 4}, "cpsat")
    ok_b = [o for o in beam if o.ok]; ok_c = [o for o in cps if o.ok]
    assert ok_b and ok_c
    assert len(ok_c) == len(cps), [o.report.to_dict()["checks"] for o in cps if not o.ok][:1]
    assert all(o.scores["adjacency"] == 1.0 for o in ok_c)
    best_b = max(o.scores["stacking"] for o in ok_b); best_c = max(o.scores["stacking"] for o in ok_c)
    assert best_c >= best_b - 0.05, (fx, best_c, best_b)
    assert t_gen < 72.0, t_gen          # the pre-M11 gate allowed 60 s; +20 %


def test_stacking_term_can_be_switched_off(fixtures_dir):
    brief = load(fixtures_dir / "two_levels_stair.yaml")
    on, _, _ = generate(GENERATORS["cpsat"], brief, 0, {"k": 2}, "cpsat")
    off, _, _ = generate(GENERATORS["cpsat"], brief, 0, {"k": 2, "w_stack": 0}, "cpsat")
    s_on = max(o.scores["stacking"] for o in on if o.ok); s_off = max(o.scores["stacking"] for o in off if o.ok)
    assert s_on >= s_off - 1e-9, (s_on, s_off)
