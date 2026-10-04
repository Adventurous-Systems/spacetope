"""M17 gate: brief programmes and the L0 dataset.

A programme describes a kind of building; `sample` draws a brief from it. The gate asks three things of every
programme that ships: the briefs it draws are valid, they are briefs the engine can actually build, and rows
come off them fast enough to be worth calling a dataset. Format: `docs/PROGRAMMES.md`.
"""
import json
import time

import pytest

from spacetope.brief import Brief
from spacetope.circulation import prepare
from spacetope.learn.dataset import check_row, placement_row, read_rows, rows_from_programme, write_rows
from spacetope.preverify import preverify
from spacetope.programme import ProgrammeError, Frontage, load, names, sample, variations
from spacetope.solve.registry import GENERATORS

pytestmark = [pytest.mark.gate_m17, pytest.mark.slow]
SHIPPED = ("office", "secondary_school", "clinic", "housing")


def test_every_shipped_programme_is_listed():
    assert set(SHIPPED) <= set(names())
    for nm in SHIPPED:
        assert load(nm)["rooms"]
    with pytest.raises(ProgrammeError):
        load("no_such_programme")


@pytest.mark.parametrize("nm", SHIPPED)
def test_a_hundred_seeds_draw_a_valid_brief(nm):
    for seed in range(100):
        brief, front = sample(nm, seed)
        expanded, warnings = prepare(brief)          # raises BriefInvalid if the draw was nonsense
        assert expanded.spaces and not [w for w in warnings if w.severity == "error"]
        assert isinstance(front, Frontage) and front.ratio > 0
        rooms = [s for s in expanded.spaces if s.program == "room"]
        assert rooms and all("level" in s.wishes for s in rooms)      # every room knows its floor
        corridors = {s.name for s in expanded.spaces if s.program == "corridor"}
        for r in rooms:                                               # ... and opens off that floor's corridor
            partners = {b if a == r.name else a for a, b in expanded.contacts if r.name in (a, b)}
            assert partners & corridors, (nm, seed, r.name)


def test_sampling_is_deterministic():
    for nm in SHIPPED:
        assert sample(nm, 3)[0].to_dict() == sample(nm, 3)[0].to_dict()
        assert sample(nm, 3)[0].to_dict() != sample(nm, 4)[0].to_dict()


@pytest.mark.parametrize("nm", SHIPPED)
def test_the_briefs_it_draws_can_be_built(nm):
    """A programme that draws briefs nothing can build is a benchmark of nothing."""
    good = 0
    for seed in range(20):
        expanded, _ = prepare(sample(nm, seed)[0])
        if any(preverify(expanded, pl)[0] for pl in GENERATORS["beam"](expanded, None, seed)):
            good += 1
    assert good >= 16, f"{nm}: only {good}/20 draws were buildable"


def test_variations_stay_valid():
    expanded_before = prepare(sample("clinic", 1)[0])[0]
    got = variations(sample("clinic", 1)[0], 1)
    assert {"scale", "widen", "narrow", "drop", "duplicate"} <= set(got)
    for kind, v in got.items():
        e, _ = prepare(v)
        assert e.spaces, kind
        if kind == "drop":
            assert len(v.spaces) < len(expanded_before.spaces)
        if kind == "widen":
            assert all(s.band("w")[1] > s.nominal_mm("w") for s in v.spaces if s.program == "room")


def test_rows_come_off_fast_enough_and_can_be_trusted(tmp_path):
    """The L0 entry condition from the exploration note: at least 5,000 pre-verified rows an hour. A sample of
    them is then re-realised through the geometry kernel, so the dataset cannot drift from what is buildable."""
    path = tmp_path / "rows.jsonl"
    t = time.perf_counter()
    n = write_rows(rows_from_programme("clinic", range(0, 12), GENERATORS["beam"], "beam", None, 4), path)
    per_hour = n / (time.perf_counter() - t) * 3600
    assert n >= 20 and per_hour >= 5000, f"{n} rows at {per_hour:,.0f}/hour"
    rows = read_rows(path)
    assert len(rows) == n
    for row in rows[:3]:
        assert row["programme"] == "clinic" and row["preverified"] and row["scores"]["adjacency"] >= 0
        ok, detail = check_row(row)                   # rebuilds the geometry and re-verifies it
        assert ok, detail


def test_the_frontage_reading_predicts_a_hard_brief():
    """Squeeze the envelope of a drawn brief and the reading should turn tight before the brief stops building.
    Measured over four programmes 2026-10-04: 53 % of loose briefs built against 4 % of tight ones."""
    from spacetope.programme import frontage
    seen = {True: [0, 0], False: [0, 0]}          # tight -> [briefs, buildable]
    for nm in ("clinic", "office"):
        for seed in range(5):
            brief, _ = sample(nm, seed)
            if not brief.envelope:
                continue
            for shrink in (1.0, 0.75, 0.6):
                d = brief.to_dict()
                d["envelope"] = {**d["envelope"], "w": round(d["envelope"]["w"] * shrink, 1),
                                 "l": round(d["envelope"]["l"] * shrink, 1)}
                d["name"] = f"{brief.name}_s{shrink}"
                expanded, _ = prepare(Brief.from_dict(d))
                corridor = expanded.circulation["corridor"]
                front = frontage([s.to_dict() for s in expanded.spaces if s.program == "room"], expanded.levels or 1,
                                 float(corridor["w"]),
                                 min(float(corridor["l"]) * 3, max(d["envelope"]["w"], d["envelope"]["l"])))
                built = any(preverify(expanded, pl)[0] for pl in GENERATORS["beam"](expanded, None, seed))
                seen[front.tight][0] += 1
                seen[front.tight][1] += built
    assert seen[True][0] >= 3 and seen[False][0] >= 3, seen
    loose = seen[False][1] / seen[False][0]
    tight = seen[True][1] / seen[True][0]
    assert tight < loose / 2, f"tight {tight:.0%} vs loose {loose:.0%}: the reading is not telling us anything"


def test_the_cli_writes_briefs_and_rows(tmp_path):
    from spacetope.cli import main
    assert main(["programme", "--list"]) == 0
    out = tmp_path / "briefs"
    assert main(["programme", "clinic", "--seeds", "0-2", "--out", str(out), "--variations"]) == 0
    written = sorted(p.name for p in out.glob("*.yaml"))
    assert len([p for p in written if "__" not in p]) == 3 and any("__" in p for p in written)
    assert Brief.from_path(out / "clinic_0.yaml").spaces
    ds = tmp_path / "rows.jsonl"
    assert main(["programme", "clinic", "--seeds", "0-1", "--dataset", str(ds), "--per-brief", "2"]) == 0
    assert len([json.loads(x) for x in ds.read_text().splitlines() if x.strip()]) >= 2
