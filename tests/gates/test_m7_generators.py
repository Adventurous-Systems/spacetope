# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Adventurous Systems

"""M7.5 gate: generators declare what they support; treemap refuses multi-level briefs with a plain message."""
import pytest

from spacetope.brief import load
from spacetope.circulation import prepare
from spacetope.pipeline import generate
from spacetope.solve.registry import CAPABILITIES, GENERATORS, GeneratorUnsupported

pytestmark = pytest.mark.gate_m7


def test_capabilities_declared():
    assert set(CAPABILITIES) == set(GENERATORS)
    assert CAPABILITIES["treemap"]["multi_level"] is False
    assert CAPABILITIES["beam"]["multi_level"] and CAPABILITIES["cpsat"]["multi_level"]


def test_treemap_refuses_multi_level(fixtures_dir):
    brief, _ = prepare(load(fixtures_dir / "three_levels_core.yaml"))
    with pytest.raises(GeneratorUnsupported, match="treemap is single-level only"):
        generate(GENERATORS["treemap"], brief, 0, None, "treemap")


def test_api_health_and_422(fixtures_dir):
    from fastapi.testclient import TestClient
    from backend.app.main import app
    c = TestClient(app)
    assert c.get("/api/health").json()["capabilities"]["treemap"] == {"multi_level": False}
    bid = c.post("/api/brief", json=load(fixtures_dir / "three_levels_core.yaml").to_dict()).json()["brief_id"]
    res = c.post("/api/generate", json={"brief_id": bid, "generator": "treemap", "seed": 0, "wait": True})
    assert res.status_code == 422
    assert res.json()["detail"]["problems"][0]["message"] == "treemap is single-level only"
