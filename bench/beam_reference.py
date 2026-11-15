"""Beam reference hashes (PLAN M20 gate line 5): the SHA-256 of the placements the beam returns, seed 0, per fixture.

`placement_hash` is the canonical form the gate recomputes: each placement as sorted name -> [x, y, z, w, l, h],
list order kept. Run from the repo root to (re)write tests/gates/m20_beam_reference.json:

    .venv/bin/python -m bench.beam_reference [out.json]
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

from spacetope.brief import load
from spacetope.circulation import prepare
from spacetope.solve.registry import GENERATORS

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "tests" / "gates" / "m20_beam_reference.json"


def canonical(placements) -> str:
    return json.dumps([{n: [b.x, b.y, b.z, b.w, b.l, b.h] for n, b in sorted(pl.items())} for pl in placements],
                      separators=(",", ":"))


def placement_hash(placements) -> str:
    return hashlib.sha256(canonical(placements).encode()).hexdigest()


def beam_reference(path: Path, seed: int = 0) -> dict:
    brief, _ = prepare(load(path))
    pls = GENERATORS["beam"](brief, None, seed)
    return {"sha256": placement_hash(pls), "placements": len(pls)}


def main(out: Path = OUT) -> None:
    ref = {}
    for p in sorted((ROOT / "fixtures").glob("*.yaml")):
        ref[p.stem] = beam_reference(p)
        print(p.stem, ref[p.stem], flush=True)
    out.write_text(json.dumps({"seed": 0, "fixtures": ref}, indent=1) + "\n")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else OUT)
