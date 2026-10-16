# spacetope

An exploration of topological and graph-grammar assemblies: turn an architect's list of spaces
(width, length, height, tolerance, program) into verified, scored **cell complexes**
(topologicpy `CellComplex`) with corridors, stairs and elevators, and let the architect choose.

Read `CLAUDE.md` for the working rules and `docs/PLAN.md` for the roadmap and gates.

## Setup (macOS arm64, Python 3.11)

```bash
python3.11 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/python -m pytest -m "gate_m0 or gate_m1"        # fast gates (~10 s)
.venv/bin/python -m pytest -m "gate_m2 or gate_m3 or gate_m4"   # generator gates (~10 min)
```

## Use

```bash
# generate, verify, score and rank options for a brief
.venv/bin/spacetope generate fixtures/eight_rooms_corridor.yaml --generator beam --seed 0 --out out/eight --html --save
.venv/bin/spacetope generate fixtures/two_levels_stair.yaml --generator cpsat --out out/two --html

# realise a hand-placed layout (integer-mm boxes) and verify it
.venv/bin/spacetope realise fixtures/three_rooms.yaml fixtures/placed/three_rooms.json --html out/three.html

# scoreboard over every generator, fixture and seed
.venv/bin/python bench.py && column -s, -t bench/scoreboard.csv
```

Open the written `.html` files in a browser: cells coloured by program, shared-face (wall) nodes in red,
the realised graph in black.

## Web canvas (M5)

Two terminals: the API, then the Vite dev server, which proxies `/api` and `/static` to port 8000.

```bash
.venv/bin/uvicorn backend.app.main:app --port 8000 --reload --reload-dir spacetope --reload-dir backend
cd frontend && npm install && npx vite --port 5173
```

Open http://localhost:5173. Load a fixture, press Generate, click an option card. The 3D complex sits behind the
wall-node graph. Click a red wall node to highlight the two cells sharing that face. Hold Space to orbit the 3D view.
"Select and export" writes BREP, selectors, placement and graph JSON under `out/api/selected/`.

## Browser tests

```bash
cd e2e && npm install && npx playwright install chromium
npx playwright test                           # mocked backend, replays e2e/fixtures (needs Vite only)
REAL_BACKEND=1 npx playwright test            # real API on :8000, includes the 15 s first-option check
REAL_BACKEND=1 RECORD=1 npx playwright test   # real run that also refreshes e2e/fixtures
```

## Learning the move scorer (M6)

PyTorch and PyTorch Geometric add about 560 MB installed.

```bash
.venv/bin/pip install --no-cache-dir torch==2.14.0 torch-geometric==2.8.0.post1
.venv/bin/python -m spacetope.learn.train_all       # linear + graph scorers from one teacher run (~2-3 min)
.venv/bin/python -m pytest -m gate_m6               # learned beams at width 8 vs hand-tuned beam at 16
SPACETOPE_STUDENT_WIDTH=6 .venv/bin/python -m pytest -m gate_m6   # try another student width
```

Weights land in `spacetope/learn/weights.json` (linear) and `spacetope/learn/gnn.pt` (graph network).
The held-out briefs come from `spacetope/synth.py` with seeds disjoint from training.
Results are written to `bench/history/`.

## Brief format

```yaml
name: eight_rooms_corridor
levels: 1                 # optional; 2+ enables cores-first multi-level assembly
level_height: 3           # optional; default = tallest space
envelope: {w: 20, l: 14, h: 6}   # optional AABB from the origin
spaces:
  - {name: corridor, w: 1.8, l: 12, h: 3, program: corridor}     # width fixed, length free (0.5x..3x)
  - {name: office_a, w: 4, l: 3, h: 3, program: room, wishes: {exterior: true}}  # ±10 % per side
  - {name: stair_0, w: 3, l: 5, h: 3, program: stair}             # fixed footprint, stacked across levels
contacts:                 # required shared faces (door-width overlap)
  - [corridor, office_a]
```

### Multi-level briefs with circulation (M7)

Declare stairs and lifts once. Each becomes one space through every level it serves. Corridors are generated per level, and doors are placed where access is needed.

```yaml
name: three_levels_core
levels: 3
level_height: 3
envelope: {w: 22, l: 16, h: 9}
circulation:
  corridor: {w: 1.8, l: 10}              # generates corridor_0, corridor_1, corridor_2
  stairs:
    - {name: stair, w: 3, l: 5}           # serves every level by default
  lifts:
    - {name: lift, w: 2.5, l: 2.5, serves: [0, 2]}
  doors: {room: {w: 0.9, h: 2.1}, stair: {w: 1.0, h: 2.1}, lift: {w: 1.1, h: 2.1}, jamb: 0.1}  # defaults
spaces:
  - {name: office_c, w: 4, l: 3, h: 3, program: room, wishes: {level: 1}}
  - {name: meeting, w: 5, l: 4, h: 3, program: room, wishes: {level: 1}}
contacts:
  - [corridor_1, office_c]
  - [office_c, meeting, {door: true}]     # a door between two rooms
```

Doors go between each corridor and every stair and lift on each served level, and between each room and one corridor on its level. Room-to-room doors are added only where a contact is marked. Every brief is validated before generation, and problems come back as plain messages, for example "level 2 is not served by any stair". Exports include a `.doors.json` file, because BREP drops doors.

## Layout

`spacetope/brief.py` (brief) · `spacegraph.py` (wall nodes, contact edges, signatures) · `solve/` (grid, beam,
multilevel, cpsat, redim, treemap) · `realise.py` / `verify.py` / `score.py` · `io/` (BREP + selectors, graph JSON) ·
`viz/plotly.py` · `cli.py` · `tests/gates/test_m{N}.py` · `bench.py`.

## Licence

Dual-licensed: **AGPL-3.0-or-later** (`LICENSE`), or a **commercial licence** from Adventurous Systems for
use without the AGPL's obligations (`COMMERCIAL.md`). Versions up to commit `c419c33` (2026-10-16) were
released under Apache-2.0 and stay so for whoever has them. Third-party terms are in `NOTICE`: topologicpy
0.9.71 is LGPL-3.0-or-later; the `topologic_core` kernel it falls back to is AGPL-3.0 upstream and is not
covered by a commercial licence. Contributions need a DCO sign-off and the CLA in `CONTRIBUTING.md`, which is
what makes the commercial licence possible.
