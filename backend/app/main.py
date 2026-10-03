"""spacetope API: brief -> generate (job) -> options (scores, graph, GLB per cell) -> select (export).
Geometry work runs in a thread (topologicpy holds the GIL but must not block the event loop)."""
from __future__ import annotations

import asyncio
import json
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from spacetope.brief import Brief, BriefError
from spacetope.circulation import BriefInvalid, prepare
from spacetope.io.brep import save as save_brep
from spacetope.io.glb import cell_catalogue, to_yup, write_glb
from spacetope.io.graph import graph_payload, save_graph
from spacetope.pipeline import Option, generate, rank
from spacetope.solve.registry import CAPABILITIES, GENERATORS, unsupported_reason

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "out" / "api"
OUT.mkdir(parents=True, exist_ok=True)
FIXTURES = ROOT / "fixtures"

app = FastAPI(title="spacetope", version="0.1")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/static", StaticFiles(directory=str(OUT)), name="static")

BRIEFS: dict[str, Brief] = {}
JOBS: dict[str, dict[str, Any]] = {}
_lock = threading.Lock()


class GenerateRequest(BaseModel):
    brief_id: str
    generator: str = "beam"
    seed: int = 0
    params: dict[str, Any] | None = None
    wait: bool = False


class SelectRequest(BaseModel):
    job_id: str
    index: int
    # an export name is a file stem, never a path: letters, digits, dash, underscore (review 2026-09-13, #1)
    name: str | None = Field(default=None, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


def _graph(entry: dict) -> dict | None:
    """Realised wall-node graph for one option, computed once and cached on the job entry."""
    o: Option = entry["option"]
    if not o.ok or o.realised is None:
        return None
    with _lock:
        cached = entry.get("graph")
    if cached is None:
        p = graph_payload(o.realised)
        p["coords_yup"] = [to_yup(c) for c in p["coords"]]
        with _lock:
            cached = entry.setdefault("graph", p)
    return cached


def _option_summary(job_id: str, i: int, o: Option, topology_class: int | None = None) -> dict:
    d = {"index": i, "ok": o.ok, "scores": o.scores, "analysis": o.analysis, "topology_class": topology_class,
         "signature": [list(s) for s in o.signature],
         "placement": {n: b.to_dict() for n, b in o.placement.items()}, "verify": o.report.to_dict(),
         "generator": o.generator, "seed": o.seed}
    if o.ok:
        d["glb_url"] = f"/static/{job_id}/option_{i:02d}.glb"
        d["doors"] = len(o.realised.doors) if o.realised is not None else 0
    return d


def _run_job(job_id: str) -> None:
    job = JOBS[job_id]
    try:
        brief = BRIEFS[job["brief_id"]]
        gen = GENERATORS[job["generator"]]
        options, t_gen, t_real = generate(gen, brief, job["seed"], job["params"], job["generator"])
        ranked = rank(options)
        out_dir = OUT / job_id
        results = []
        # PLAN M9: which options are the same plan up to symmetry and swaps of identical rooms
        from spacetope.placement import topology_classes
        ok_idx = [i for i, o in enumerate(ranked) if o.ok and o.realised is not None]
        classes = dict(zip(ok_idx, topology_classes(ranked[ok_idx[0]].realised.brief, [ranked[i].placement for i in ok_idx]))) if ok_idx else {}
        for i, o in enumerate(ranked):
            entry = {"option": o, "summary": _option_summary(job_id, i, o, classes.get(i))}
            if o.ok and o.realised is not None:
                write_glb(o.realised, out_dir / f"option_{i:02d}.glb")
                entry["cells"] = cell_catalogue(o.realised)
                # graph payload (~0.25 s per option) is built lazily on first detail request
            results.append(entry)
        with _lock:
            job.update({"status": "done", "results": results, "t_gen": round(t_gen, 3), "t_realise": round(t_real, 3),
                        "finished": time.time()})
    except Exception as e:  # report, never hide
        with _lock:
            job.update({"status": "failed", "error": f"{type(e).__name__}: {e}", "finished": time.time()})


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "generators": list(GENERATORS), "capabilities": CAPABILITIES}


@app.get("/api/fixtures")
def fixtures() -> list[dict]:
    out = []
    for p in sorted(FIXTURES.glob("*.yaml")):
        b = Brief.from_path(p)
        out.append({"name": b.name, "spaces": len(b.spaces), "contacts": len(b.contacts), "levels": b.levels})
    return out


@app.get("/api/fixtures/{name}")
def fixture(name: str) -> dict:
    p = FIXTURES / f"{name}.yaml"
    if not p.exists():
        raise HTTPException(404, "unknown fixture")
    return Brief.from_path(p).to_dict()


@app.post("/api/brief")
def post_brief(body: dict) -> dict:
    try:
        b = Brief.from_dict(body)
    except (BriefError, KeyError, TypeError, ValueError) as e:
        raise HTTPException(422, {"message": f"invalid brief: {e}", "problems": [{"code": "parse", "message": str(e), "severity": "error"}]})
    # M7: every brief is validated before it is stored; circulation sections are expanded into concrete spaces.
    try:
        b, warn = prepare(b)
    except BriefInvalid as e:
        raise HTTPException(422, {"message": "invalid brief", "problems": [p.to_dict() for p in e.problems]})
    warnings = [w.to_dict() for w in warn]
    bid = uuid.uuid4().hex[:12]
    BRIEFS[bid] = b
    return {"brief_id": bid, "brief": b.to_dict(), "compact": body, "warnings": warnings}


@app.get("/api/brief/{brief_id}")
def get_brief(brief_id: str) -> dict:
    if brief_id not in BRIEFS:
        raise HTTPException(404, "unknown brief")
    return {"brief_id": brief_id, "brief": BRIEFS[brief_id].to_dict()}


@app.post("/api/generate")
async def post_generate(req: GenerateRequest) -> dict:
    if req.brief_id not in BRIEFS:
        raise HTTPException(404, "unknown brief")
    if req.generator not in GENERATORS:
        raise HTTPException(422, f"unknown generator {req.generator}; choose from {list(GENERATORS)}")
    reason = unsupported_reason(req.generator, BRIEFS[req.brief_id])
    if reason:
        raise HTTPException(422, {"message": reason, "problems": [{"code": "generator", "message": reason, "severity": "error"}]})
    job_id = uuid.uuid4().hex[:12]
    JOBS[job_id] = {"job_id": job_id, "status": "running", "brief_id": req.brief_id, "generator": req.generator,
                    "seed": req.seed, "params": req.params, "started": time.time()}
    if req.wait:
        await asyncio.to_thread(_run_job, job_id)
    else:
        asyncio.get_running_loop().run_in_executor(None, _run_job, job_id)
    return _job_view(job_id)


def _job_view(job_id: str) -> dict:
    with _lock:  # the worker thread updates this dict in place (review 2026-09-13, #7)
        job = dict(JOBS[job_id])
    view = {k: v for k, v in job.items() if k != "results"}
    if job.get("status") == "done":
        view["options"] = len(job["results"])
        view["verified"] = sum(1 for r in job["results"] if r["summary"]["ok"])
    return view


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    if job_id not in JOBS:
        raise HTTPException(404, "unknown job")
    return _job_view(job_id)


@app.get("/api/options/{job_id}")
def get_options(job_id: str) -> list[dict]:
    job = JOBS.get(job_id)
    if job is None:
        raise HTTPException(404, "unknown job")
    if job["status"] != "done":
        raise HTTPException(409, f"job is {job['status']}")
    return [r["summary"] for r in job["results"]]


@app.get("/api/options/{job_id}/{index}")
def get_option(job_id: str, index: int) -> dict:
    job = JOBS.get(job_id)
    if job is None or job["status"] != "done":
        raise HTTPException(404, "unknown or unfinished job")
    if not (0 <= index < len(job["results"])):
        raise HTTPException(404, "no such option")
    r = job["results"][index]
    return {**r["summary"], "graph": _graph(r), "cells": r.get("cells")}


@app.post("/api/select")
def post_select(req: SelectRequest) -> dict:
    job = JOBS.get(req.job_id)
    if job is None or job["status"] != "done":
        raise HTTPException(404, "unknown or unfinished job")
    if not (0 <= req.index < len(job["results"])):
        raise HTTPException(404, "no such option")
    r = job["results"][req.index]
    o: Option = r["option"]
    if not o.ok or o.realised is None:
        raise HTTPException(409, "option did not verify; it cannot be selected")
    stem = (OUT / "selected" / (req.name or f"{req.job_id}_{req.index:02d}")).resolve()
    if not stem.is_relative_to(OUT.resolve()):
        raise HTTPException(422, "export name must stay inside the output directory")
    paths = save_brep(o.realised, stem)
    save_graph(_graph(r), str(stem) + ".graph.json")
    (stem.with_suffix(".option.json")).write_text(json.dumps(r["summary"], indent=1))
    return {"selected": {k: str(v.relative_to(ROOT)) for k, v in paths.items()},
            "graph": str((Path(str(stem) + ".graph.json")).relative_to(ROOT)),
            "glb_url": r["summary"].get("glb_url")}
