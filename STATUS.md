# spacetope — status

**Date:** 2026-09-22 · **Branch:** `m9-stretch` (2 commits ahead of `main`) · **Working tree:** clean

Turn an architect's list of spaces into candidate non-manifold cell complexes, verify them, score them, and
offer the architect a choice. Full context in `docs/PLAN.md`; that file's §0 explains the idea in plain words
and §4.9 holds the current programme.

---

## 1. Where the project stands

Everything through M15 is built and gated. Two milestones were attempted and failed their gates: M6 (learning
the proposal) and M16 (sequence pair). Both are recorded rather than quietly dropped, and neither is wired into
the engine.

| # | Milestone | State | Gate |
|---|---|---|---|
| M0 | Foundations | done | 17 |
| M1 | Realiser, verifier, scorer, viewer | done | 12 |
| M2 | Beam search, single level | done | 26 |
| M3 | Vertical movement, emergent levels | done | 6 |
| M4 | Exact engine (CP-SAT) | done | 4 |
| M5 | Web canvas and option selection | done | 8 |
| M6 | Learning the proposal | **gate failed** (allowed), parked | 4 |
| M7 | Vertical circulation and doors | done | 47 |
| M8 | Floor-count search | done | 12 |
| M9 | topologicpy on the pinned version | done | 10 |
| M10 | Measured engine fixes | done | 10 |
| M11 | Cross-level alignment in CP-SAT | done | 4 |
| M12 | Rectangular-dual generator | done | 8 |
| M13 | Z3 cross-check | done | 4 |
| M14 | topologicpy 0.9.71 | done | 5 |
| M15a | Beam on tight corridors | done | 17 (with b, c) |
| M15b | Chained (L, U) corridors | done with `cpsat` | ” |
| M15c | Gap-closing pass | **measured and dropped**: nothing to close | ” |
| M16 | Sequence pair + annealing | **gate failed**, not registered | 14 |
| M17 | Brief programmes and dataset L0 | planned | — |

**225 tests** collected in total, 63 of them fast. All green as of 2026-09-22 on topologicpy 0.9.71.

---

## 2. What the engine does today

A brief lists spaces with nominal sizes, a tolerance band, a program, and wishes. It may declare an envelope, a
number of levels, and a compact circulation section (corridor template, stairs, lifts, door sizes). Expansion
turns that into concrete spaces; validation reports problems in plain sentences before anything is generated.

**Generators** — `(brief, params, seed) -> placements`, all verified by the same checks:

| Engine | Good for | Not for |
|---|---|---|
| `beam` | every brief first; multi-level with shafts; warm start for the others | guaranteeing a wish is met (wishes are scored, not enforced) |
| `cpsat` | rich room-to-room wishes; chained corridors; proving a brief impossible | a short time budget on a coupled level |
| `dual` | listing genuinely different plan topologies for a rich wish graph | multi-level; non-planar wish graphs; briefs without a corridor |
| `treemap` | a baseline and a seed | any wish, any band, more than one level |

**Then**: integer-millimetre dimensioning, realisation into a `CellComplex` with doors as apertures, seven
verification checks, scores, and a ranking. Options are exported as GLB, BREP with a selector sidecar, OBJ,
JSON, and (since M14) a single TPY archive that keeps dictionaries and doors.

**Interfaces**: `spacetope generate|realise|floors|export`, a FastAPI backend, and a React canvas.

---

## 3. What was measured, and what it cost

Numbers are from seed 0 unless stated. Every claim here has a decisions row in `docs/PLAN.md` §5.

- **The beam used to fail on large briefs.** On a 51-space hospital and a 64-space school it verified nothing.
  M15a fixed that: a corridor whose rooms need more than three quarters of its two sides starts at the length
  they need and takes rooms narrow side on, and chains of rooms that must touch are placed as one run. Both
  briefs now verify, and the beam got faster: 37 s to 4 s, and 42 s to 16 s.
- **"Distinct" counted less than it looked.** The relation signature names rooms, so swapping two identical
  offices counted as a new option. Under exact labelled isomorphism the eight-room brief gives the beam 3 real
  topologies out of 8 options, CP-SAT 3 of 4, and the dual enumerator 8 of 8. `distinct_topologies` is now a
  column in the scoreboard and a plan letter on each option card.
- **topologicpy 0.9.71 changed a failure mode.** A failed merge now returns an empty complex, not `None`, and a
  sub-millimetre gap no longer heals. `realise` treats a complex without cells as a failed build on any version.
- **Z3 agrees with CP-SAT.** On small briefs both enumerate identical sets of wall assignments (16 of 16, 64 of
  64) and both call the contradictory brief impossible, so the M10–M12 changes to the solver model neither
  removed nor invented arrangements.
- **There are no gaps to close.** Across seven fixtures and all three generators, enclosed empty ground is zero.
  The empty ground is the plan's outline, which the architect has confirmed is not a defect and may be a feature.

---

## 4. Known limits

These are measured and gated, not suspicions.

- **The beam on chained corridors** reaches a verified layout on one seed in four. `cpsat` finds the corner from
  feasibility alone. Use `cpsat` for briefs with `segments: N`.
- **The dual enumerator** reaches fewer topologies than the beam on briefs without a corridor, and none at all on
  `house_ground` or `gallery_rich`, where rooms chain to each other. Chord triangulation forces every pair on a
  face to touch; voids instead of chords is the likely fix.
- **CP-SAT is not seed-deterministic.** Speed was kept over reproducibility. Two runs of the same brief can give
  different plans, so gate assertions must hold for any valid solution.
- **Two shafts no longer guarantee two ways down** once a spine is chained: the stair and the lift can land on
  different segments, and the route between levels then passes through the opening they share. The option
  analysis reports the number of independent routes so this is visible.
- **`seqpair` is not registered.** Bottom-left packing pulls rooms off the corridor they must touch, so it
  returns nothing past about ten spaces on a corridor.
- **M6's learned scorers** never beat the hand-tuned beam and are not in the pipeline.

---

## 5. Open questions (`docs/PLAN.md` §6)

1. **Does the sequence-pair approach get another decoder or get dropped?** The fit would be the dual's
   wall-segment sizer, where nothing compacts toward an origin. Against doing anything: since M15a no brief in
   the repository needs it.
2. **Rectangular duals for briefs with room-to-room doors**, and for briefs with no corridor: voids instead of
   chords inside a face, and enumerating the staircase directions instead of sampling them.
3. **Chained corridors, option (b).** Access is currently judged by the door rule. A disjunctive contact form
   would let an architect say which segment a room belongs to, and would let scoring rather than search fix the
   beam's unreliability.

Answered recently: ragged outlines are not a defect (2026-09-21); chained corridors take option (a) (2026-09-20).

---

## 6. Licensing

spacetope is Apache-2.0 and stays that way: topologicpy 0.9.71 is LGPL-3.0-or-later and spacetope imports it
without copying or modifying it, which is the case the LGPL permits. Reviewed against the installed
distributions on 2026-09-27; `NOTICE` carries the detail.

One obligation is open. `topologic_core`, the binary geometry kernel, declares no licence in its metadata and
its upstream source is AGPL-3.0, and it is an in-process C extension. **A Rust core owned by this project is in
development to replace it.** Meanwhile topologicpy 0.9.71 prefers a PythonOCC backend and falls back to this
kernel only because `pythonocc-core` (LGPL-3.0) is not installed, so that may be a faster route; it is untested
and would need the same verify-everything treatment as a version bump. Until one lands, do not distribute a
build that carries the binary.

## 7. Running it

```bash
pytest -m "not slow"                       # fast suite, 63 tests
pytest -m gate_m15                         # one milestone's gate
cd e2e && npx playwright test              # browser tests, mocked
python -m bench.dead_space                 # where a layout's empty ground goes
python bench.py --out bench/scoreboard.csv # the scoreboard
```

Run the slow gates **one marker at a time**. A batched run of all of them was killed for low memory on this
machine on 2026-09-20.

**Stack**: Python 3.11.9 in `.venv`, `topologicpy==0.9.71` (LGPL-3.0-or-later) with `topologic_core==8.0.0`,
ortools, networkx, shapely; `z3-solver` as a development dependency. The environment from before the 0.9.71 bump
is recorded in `docs/experiments/2026-09-20_pip_freeze_before_m14.txt` if a rollback is ever needed.

---

## 8. A note on the documents

`CLAUDE.md` and every dated note under `docs/` are excluded by `.gitignore`, so they are local to this machine
and not part of the upstream repository. That includes the design and exploration notes this status refers to:
the stretch-goal design, the performance and learning exploration, and the topologicpy options note. `docs/PLAN.md`,
`docs/TOPOLOGICPY_NOTES.md`, `docs/ALGORITHM_SURVEY.md` and this file are tracked.

Two interactive explainers were published as private pages:
[Spacetope Field Guide](https://claude.ai/artifact/LogkrcvLKvqZ1Fnq3Zgms7) and
[Stretch Goals Explorer](https://claude.ai/artifact/1RhyCyuLTcjUGxSydstrCR).
