"""M26 gate: five tessellations, and one way into topologic for all of them (PLAN §4.11)."""
import numpy as np
import pytest
import shapely
from shapely.geometry import Point, Polygon

from spacetope import cells, field
from spacetope.brief import load
from spacetope.circulation import prepare
from spacetope.layout import from_placement
from spacetope.solve.registry import GENERATORS
from spacetope.tessellate import KINDS, Seed, power_diagram, tessellate

pytestmark = pytest.mark.gate_m26
SITE = Polygon([(0, 0), (30, 0), (34, 18), (20, 26), (12, 16), (0, 20)])   # concave on purpose
KERNEL = ("built", "cell_count", "no_slivers", "contacts", "dictionaries")


def _seeds(n: int, seed: int) -> list[Seed]:
    rng = np.random.default_rng(seed)
    out = []
    while len(out) < n:
        p = rng.uniform([0, 0], [34, 26])
        if SITE.contains(Point(p)):
            out.append(Seed(f"r{len(out)}", float(p[0]), float(p[1]), float(rng.choice([12, 20, 30, 60]))))
    return out


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("n", [8, 20])
def test_a_tessellation_is_a_partition(kind, n):
    seeds = _seeds(n, n)
    got = tessellate(kind, SITE, seeds)
    assert set(got) == {s.name for s in seeds}, "every seed gets ground"
    assert all(p.geom_type == "Polygon" and p.is_valid and p.area > 0 for p in got.values())
    union = shapely.union_all(list(got.values()))
    assert union.area == pytest.approx(SITE.area, rel=2e-3), "the cells fill the region"
    assert sum(p.area for p in got.values()) == pytest.approx(union.area, rel=2e-3), "and do not overlap"


def test_areas_by_kind():
    seeds = _seeds(20, 20)
    share = {s.name: s.area * SITE.area / sum(q.area for q in seeds) for s in seeds}
    err = {k: float(np.mean([abs(p.area - share[n]) / share[n] for n, p in tessellate(k, SITE, seeds).items()])) for k in KINDS}
    assert err["slice"] < 0.02          # cuts are placed by area
    assert err["power"] < 0.25 < err["voronoi"]   # weights chase the areas; plain Voronoi does not look at them
    assert err["grid"] < 0.5 and err["hex"] < 0.15


def test_power_diagram_with_no_weights_is_voronoi():
    P = np.array([[2.0, 2.0], [8.0, 3.0], [5.0, 8.0]])
    cells_ = power_diagram(P, np.zeros(3), (0, 0, 10, 10))
    for i, V in enumerate(cells_):
        c = Polygon(V).representative_point()
        assert int(np.argmin(((P - [c.x, c.y]) ** 2).sum(axis=1))) == i
    heavy = power_diagram(P, np.array([20.0, 0.0, 0.0]), (0, 0, 10, 10))
    assert Polygon(heavy[0]).area > Polygon(cells_[0]).area


def test_unknown_kind_is_named():
    with pytest.raises(ValueError, match="voronoi"):
        tessellate("penrose", SITE, _seeds(3, 1))


@pytest.mark.slow
@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("fixture,seed", [("club", 4), ("pavilion", 0)])
def test_every_kind_becomes_a_cell_complex(kind, fixture, seed, fixtures_dir):
    f = field.prepare(load(fixtures_dir / "field" / f"{fixture}.yaml"), seed)
    lay = field.build(f, field.relax(f, seed), kind)
    rep = cells.verify_layout(f.brief, lay)
    failed = {k: rep.checks[k][1] for k in KERNEL if not rep.checks[k][0]}
    assert not failed, failed
    assert rep.realised.n_cells == len(lay)
    assert rep.realised.kernel_pairs() >= {p for p in rep.realised.table.pairs() if rep.realised.table.contact(*tuple(p)) >= cells.MIN_CONTACT_MM2}


@pytest.mark.slow
def test_boxes_go_in_by_the_same_door(fixtures_dir):
    brief, _ = prepare(load(fixtures_dir / "two_levels_stair.yaml"))
    pl = GENERATORS["beam"](brief, None, 0)[0]
    rep = cells.verify_layout(brief, from_placement(pl))
    failed = {k: rep.checks[k][1] for k in KERNEL if not rep.checks[k][0]}
    assert not failed, failed
