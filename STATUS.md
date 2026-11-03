# spacetope — status

**Date:** 2026-10-24 · **Branch:** `main` (M0–M17 and the relicensing merged) · **Next:** §2

Turn an architect's list of spaces into candidate non-manifold cell complexes, verify them, score them, and
offer the architect a choice. Full context in `docs/PLAN.md`; that file's §0 explains the idea in plain words
and §4.9 holds the programme that has been delivered. §2 below is the next one.

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
| M5 | Web canvas and option selection | done | 7 |
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
| M17 | Brief programmes and dataset L0 | done | 14 |

**250 tests** collected in total, 63 of them fast. All green as of 2026-10-04 on topologicpy 0.9.71.

2026-10-16: the canvas opacity slider had no effect on large briefs (`school_three_levels`). A material first
drawn opaque keeps an opaque shader, and on a large GLB that first frame comes before the slider value is
applied; `ComplexScene.jsx` now recompiles a material when it switches between opaque and translucent.

---

## 2. The next programme (planned 2026-10-24)

Three things now ask for work. Two are developments: **affinity** (spaces placed by what they need, not only by
what they touch) and **curves** (cell complexes whose walls need not be planar). One is a bridge: spacetope
now has consumers, AFlow being the first, and what they read needs a form that survives spacetope changing.
This section records what was found, the plan, and the order, with reasons. It replaces nothing in
`docs/PLAN.md`; the milestones move there, with decision rows in §5, when they start.

### 2.1 The order, and why

| # | Milestone | Track | Size | Why in this place |
|---|---|---|---|---|
| M18a | The contract, versioned, and a release discipline | bridge | ≈ 1 week | spacetope's output is read by other programs, and nothing in it says which version it is (§2.4). Every later milestone changes the brief or the output, so this comes first. |
| M18b | Rectilinear polygon envelope (a site outline, not a bounding box) | bridge | ≈ 2 weeks | Real sites are L- and T-shaped, and a bounding box either wastes them or does not fit them. An outline is also where orientation and a curved boundary will come from. |
| M19 | Affinity: vocabulary, expansion and measurement (no generator changes) | affinity | ≈ 1 week | Measure first, as with every earlier generator change. Briefs already declare `exterior: true` and nothing reads it. |
| M20 | Affinity in the generators: hard and soft | affinity | ≈ 2–3 weeks | The architectural value is here: wet rooms that stack, quiet rooms away from noisy ones, rooms on the sunny side. |
| M21 | Site orientation and sun | affinity | ≈ 1 week | Turns "the south side" into the side that gets the sun, from latitude and true north. |
| M22 | Curves C0: kernel facts, backend decision, verification of curved contacts | curves | ≈ 1 week | Curved geometry rests on the kernel, and two of the measured facts (§2.3) break the current verifier. Nothing curved is shown before this is settled. |
| M23 | Curves C1: curved envelope | curves | ≈ 1–2 weeks | The cheapest curve with a real use: a curved façade or site edge on a rectilinear plan. |
| M24 | Curves C2: curvilinear grids (polar first) | curves | ≈ 3 weeks | Arc corridors, rooms around a round court, radial plans, with the search layer unchanged. |
| C3 | Free-form (NURBS) walls | curves | research | Parked until C2 has been used on a real brief. |

The reasoning behind the order:

- **The bridge goes first because it is small and everything else changes what crosses it.** Affinities add to
  the brief and to the option report. Curves change what a placement is.
- **Affinity goes before curves.** It is pure Python on the cheap model. It touches no kernel. It fixes a wish
  the briefs already carry and nobody reads. And it changes the architectural quality of every option on every
  brief. Curves change the geometry of a minority of buildings and carry kernel risk.
- **Curves start with an experiment, not a feature.** This is the project's rule for any new kernel behaviour.
  The facts in §2.3 already show that a naive approach fails verification.

### 2.2 Affinity

**What exists.** "Adjacency" today means one thing: a required contact (`contacts:`), which must become a shared
face, which CP-SAT treats as hard and the beam scores heavily. The CP-SAT objective has no other wish term; it
minimises deviation and perimeter and rewards cross-level alignment. `wishes.level` is honoured. `wishes.exterior`
is written by the programmes and by `school_wing.yaml`, but **no generator or score reads it**. `daylight` counts
every room with an uncovered wall, whether or not it asked for one. There is no site north, so "south" has no
meaning yet.

**What affinity means here.** A wish that relates a space to another space, to a group of spaces, or to the site,
with a strength. Contact is one kind of affinity among several. Architects already work this way: adjacency
matrices and bubble diagrams with graded closeness. The standard scale is Muther's Systematic Layout Planning
(1961): A (absolutely necessary), E, I, O, U (unimportant), X (undesirable).

**Kinds**, each measurable on integer boxes without the kernel:

| Kind | Between | Met when | Examples |
|---|---|---|---|
| `touch` | space–space | a shared face of door width (today's contact) | consult ↔ corridor |
| `near` | space–space | door-graph depth ≤ k, or walking distance ≤ d | ward ↔ nurse station |
| `apart` | space–space | no shared wall or floor; optionally depth ≥ k | bedroom ↔ plant; music ↔ library |
| `stack` | space–space | plan overlap across adjacent levels ≥ a footprint | wet over wet (risers); structural cores |
| `same_level` | space–space | same z band | teaching suite |
| `facade` | space–site | exterior wall length ≥ x on a named side, or facing the sun (M21) | living rooms to the sun, galleries away from it |
| `exterior` | space–site | any exterior wall ≥ x (the existing wish, finally read) | classrooms, offices |
| `ground` / `top` | space–site | on level 0 / on the top level | entrance, café / plant, roof terrace |

**Groups by tag.** A space carries `tags: [wet, quiet, public, …]`. Group rules expand into pair affinities when the
brief is expanded, the same way the circulation section expands into corridors and shafts:

```yaml
spaces:
  - {name: bath_1, w: 2.4, l: 2.0, tags: [wet]}
  - {name: bed_1,  w: 3.6, l: 3.2, tags: [quiet], affinities: [{facade: sun, strength: should}]}
affinities:
  - {tag: wet, rule: stack, strength: should}           # wet rooms over wet rooms
  - {tag: wet, rule: cluster, strength: should}         # wet rooms share walls on a level
  - {tags: [quiet, noisy], rule: apart, strength: must}
```

After expansion, generators see only pair affinities and site affinities. They never see tags, so the rule
vocabulary can grow without touching a generator.

**Strengths.** There are four: `must` and `never` are hard, `should` and `avoid` are soft, with weights. An SLP
chart imports as A → `must`, E/I/O → `should` with weights 4/2/1, U → nothing, and X → `avoid` (or `never` when
the architect says so).

**Where it lives in the wall-node graph.** The site becomes **environment nodes**: `outside:N`, `outside:E`,
`outside:S`, `outside:W`, `ground`, `sky`. A `facade` affinity is then a contact edge from a room's wall node to an
outside node. It is the same kind of edge as a room-to-room contact, so the assembly graph stays one graph.
This is already how the `dual` generator works: its four outer vertices N, E, S, W are exactly these nodes, so
facade affinities cost it nothing. In CP-SAT, a facade affinity is a Boolean saying that a room's wall lies on
the envelope or bounding-box side. In the beam it is a move-score term. `apart` is the negation of the contact
Booleans CP-SAT already has.

**What the architect sees.** There is a new score, `affinity`: weighted satisfaction in [0, 1]. Next to it is a
per-affinity report on every option card: met, missed, and by how much. The report says *which* wish was
traded, not just a number. `daylight` changes meaning: it counts the rooms that asked for an exterior wall and
got one. `must` and `never` become an eighth verification check, so an option that breaks one is never shown
(rule 6).

**Wet rooms, in detail, because they are the hard case.** Two readings have to be chosen between in M20. In the
first, `stack` means plan overlap across levels (cheap, and CP-SAT already has the stacking literals from M11).
In the second, wet rooms must touch a generated **riser**, a `void` shaft that spans levels and is expanded the
way stairs are. The riser reading is more truthful, because what matters on site is a shared vertical duct. It
also reuses the shaft machinery that already works. It costs one cell per riser.

**Gates (sketch).**
- **M19:** affinities parse, expand and report. A baseline `affinity` score is recorded for every fixture with
  affinities added: wet stacking in the apartments, quiet/noisy separation in the school, exterior in the clinic
  and the office. Generators are untouched.
- **M20:** `must` and `never` are met by 100 % of verified options. `should` satisfaction beats the M19 baseline by
  a margin fixed in the M19 decision row. The verified count and time are no worse than the scoreboard. All
  earlier gates stay green.
- **M21:** with site north and latitude, the sun side is computed and flips between the hemispheres. A brief
  rotated by its own north produces the same affinity score.

**Cheap trick for orientation (M21).** Every plan has eight symmetries (four rotations, two mirrors). When the
envelope allows it, choosing the best of the eight for the site affinities is a post-search step that costs
microseconds. It changes no topology. topologicpy's `Sun` module (`Sun.Azimuth`, `Sun.Altitude`, `Sun.Vector`)
would give the solar weights for each façade direction, but it depends on `ephem` and runs `pip install ephem`
on import when that is missing. So either `ephem` becomes a declared dependency (licence to be checked), or the
standard solar-position formulae are written into `score.py`, which is a few dozen lines.

### 2.3 Curves

**Measured on 2026-10-24.** These were run on topologicpy 0.9.71 and topologic_core 8.0.0, and on the released
wheels from 0.9.0 to 0.9.87.

- Exact curves arrived in **topologicpy 0.9.69 (2026-09-13)**, so the current pin already has them. The new
  functions are `Edge.Arc` (exact, no longer a polyline), `Edge.ByCurve` and `Edge.ByNurbsParameters`,
  `Face.ByNurbsParameters`, and a `polyhedron` flag on `Cell.Cylinder`, `Cone`, `Sphere`, `ByThickenedFace` and
  `ByWires`. Releases since 0.9.71 add parametric surfaces (catenoid, helicoid, hyperbolic paraboloid and others),
  up to 0.9.87, the latest. **0.9.87 removes `topologicpy.Graph`** (it ships `Graph_deprecated.py`; 0.9.86 still
  has `Graph.py`), in favour of `TGraph`. spacetope still calls `Graph.ByTopology`, so a bump past 0.9.86 needs
  the move to `TGraph` first (§2.6, step 4).
- topologicpy's own exact-curve cell builders (`polyhedron=False`) **need the PythonOCC backend**. On
  topologic_core they print a warning and return `None`. `pythonocc-core` is distributed through conda only, not
  PyPI.
- topologic_core's own lower-level calls build exact curved cells: a cylinder has three faces, the volume is π
  rather than a faceted approximation, and the BRep round-trips. But that leans harder on the very dependency the
  Rust core is meant to replace.
- **`CellComplex.ByCells` merges cells across a curved shared face only when the two surfaces are identical**:
  - A ring and the cylinder that cut it give two cells and one shared curved face.
  - A cylinder rebuilt with the same parameters gives the same result.
  - A cylinder rotated 37° about its axis gives two cells, but the shared wall splits into two faces at the
    moved seam.
  - A radius 0.5 mm off gives **zero cells**, the same failure as a gap between boxes.
  - Slicing a box with a curved face (`Topology.Slice`) gives two cells with one curved shared face.
- **`Graph.ByTopology(direct=True, viaSharedTopologies=True)` misses the adjacency across a curved face.** Two
  concentric cells share a centroid and collapse into one graph vertex. With internal vertices there are two
  vertices but still no edge. `Topology.SharedFaces` and `Topology.AdjacentTopologies` do find the contact. The
  realised-graph check "realised ⊇ intended" would therefore fail on every curved wall.
- **The export path breaks.** `Topology.Geometry` returns no usable mesh for a curved cell, while
  `Topology.Tessellate(parallel=False)` returns triangles. The GLB and OBJ exporters need the second.

**The idea that keeps the engine intact: curvature is a coordinate system, not a search problem.** The search
layer reasons about wall nodes and contacts between integer boxes. A box in a *chart*, a mapping (u, v, z) → space,
keeps every contact, every door rule and every pre-verify check. Only the geometry changes:

- In the **Cartesian chart**, the one used today, a box is a box.
- In the **polar chart**, u is a radius in millimetres and v is an angle in integer units. A "box" becomes an
  annular sector. Walls of constant u are cylinders and walls of constant v are radial planes. Two sectors that
  share a u-wall share a cylindrical face.

The generators run unchanged in (u, v). Only `realise`, the areas and lengths in `score`, and the exporters
become chart-aware. A sector's area, for example, is ½·Δθ·(r₁² − r₀²).

**Rule 1 has to be restated for curves, in a decision row.** The measurements show that equal parameters merge
and a wall built twice with a moved seam splits. The restated rule is: **exact in the chart; shared curved walls
built once.** Every curved wall is one surface, made once, with one seam, and used by both cells (or cut with
`Slice` from one surface). It is never two surfaces that happen to have equal coordinates. Integer millimetres
stay the rule for the u, v, z coordinates.

**Stages.**

- **C0 = M22, the experiment and three decisions.**
  1. The backend. The choices are PythonOCC (LGPL, conda-only, which complicates a pip-installed server),
     topologic_core's raw calls (which deepen the dependency we are leaving), or the Rust core. **Whether the
     Rust core will have curved surfaces at all decides the shape of the curve track.** If it will be planar
     only, curves live behind an OCC backend permanently.
  2. Contact verification for curved walls: by `Topology.SharedFaces` on the built complex, or by a face index,
     not by `Graph.ByTopology`. The box path keeps today's check.
  3. Tessellated GLB export, keeping the `cell_{i}` contract.

  The gate: a two-cell and a ten-cell polar complex build, verify (contacts, dictionaries, no slivers), export
  and round-trip on the chosen backend. Every earlier gate stays green, because boxes take the old path.
- **C1 = M23, curved envelope.** The plan stays rectilinear and its outer cells are clipped by a curved boundary,
  such as an arc façade or a curved site edge from M18b's outline. Inner walls stay planar, and only exterior
  faces curve, so no shared curved face is needed yet. A clipped cell is smaller than its brief asked for, so
  every clipped cell is reported with its area against the brief's, and the deviation score counts it.
- **C2 = M24, the polar chart, then piecewise charts.** First the polar chart: a ring corridor with rooms off it,
  around a round court. Then piecewise charts, such as a straight run that turns into an arc, which is the
  curved version of M15b's chained corridors. Doors stay on radial (planar) walls at first. The first place a
  door needs a curved wall gets its own decision row.
- **C3, free-form walls.** This means NURBS walls from `Face.ByNurbsParameters`, splitting a volume by a family
  of surfaces. It is parked until C2 has been used on a real brief.

### 2.4 The bridge: spacetope and its consumers

AFlow is the first consumer of spacetope. What a consumer can rely on today is the command line and the files
`generate --save` writes: `options.json` and, for each option, the placement, brief, doors, selectors, graph and
BREP files. None of them carries a version, and no schema says what they contain. Reading `spacetope/cli.py`
shows two defects in that interface:

1. `generate` reports a brief that fails validation as `{"error": "..."}` with exit code 2, the same shape and
   code as an unsupported generator. A brief that fails to load raises a traceback. A consumer cannot tell an
   invalid brief from an unsupported request, nor either from a crash.
2. There is no way to say how many options to return from the command line except through `--params`, and that
   depends on the generator.

**Develop spacetope first, then integrate? Yes for capabilities, no for the contract.** spacetope leads, and
features are designed, built and gated here in spacetope's own terms. The interface that consumers read is
designed and versioned first, and changes before anything is built on a new form of it. In practice:

1. **The command line and its files are the public API, and they get a version.** `options.json` gains
   `"contract": 1`. JSON Schemas for the brief, options, placement and doors files ship in the package. Errors
   become an object, `{"error": {"kind": "invalid_brief" | "unsupported" | "infeasible" | "not_found" |
   "timeout", "messages": [...]}}`, with one exit code per kind. Additive changes, such as affinities, keep the
   major version; breaking ones, such as charts, raise it.
2. **Golden outputs are produced by spacetope's tests.** A contract test generates options for a few fixtures and
   validates them against the schemas. Consumers take the goldens as data and test against them, so a change
   here shows up in their tests rather than in their users' hands.
3. **Releases.** A tag (`v0.18.0`, …) at every green milestone gate, with the contract version in the release
   notes. A consumer installs a tagged release into an environment of its own rather than pointing at a working
   checkout, and moves its pin deliberately.
4. **Linux.** spacetope has only been tested on macOS Apple Silicon. M18a adds a Linux CI run of the fast suite
   and the contract test. topologic_core publishes Linux wheels.
5. **Reproducible runs.** CP-SAT is not seed-deterministic (§5). A `--deterministic` mode (one search worker and
   a fixed seed) gives the same options for the same brief and seed, at a cost in time that M18a measures.
6. **Code never moves between spacetope and another repository** in either direction without a licence
   decision. A feature is done here when its gate is green and the contract test passes.

**M18a gate (sketch):**
- The schemas validate the golden outputs of four fixtures.
- Every error kind is produced by a brief made to cause it, with the right exit code.
- `spacetope --version` and the contract version are printed.
- `--deterministic` gives identical options on two runs of the same brief and seed.
- The Linux CI job is green.
- `v0.18.0` is tagged.

### 2.5 Decisions needed from the architect

1. **Strength vocabulary:** `must / should / avoid / never`, with SLP letters accepted on import, or the letters
   throughout?
2. **Wet rooms:** `stack` by plan overlap, or a generated riser shaft?
3. **Curves backend:** will the Rust core carry curved surfaces? If not, is a conda-installed PythonOCC
   acceptable on the server?
4. **Releases:** a tag at every green gate, or a slower cadence?

### 2.6 Variant plan: the PythonOCC backend (recorded 2026-10-24, not adopted)

**Decision for now: stay on `topologic_core` 8.0.0.** This variant is kept so the switch can be made quickly when
it is chosen. It would replace the "Rust core first" route for the kernel question (§7) and settle M22's backend
choice, but it changes how spacetope is installed. A trial on 2026-10-25 ran every gate on PythonOCC; the
results are at the end of this section.

**Facts (2026-10-24):**
- **topologicpy has moved to PythonOCC.** Its README now recommends installing from conda-forge. The conda-forge
  package of 0.9.71 depends on `pythonocc-core >=7.9.3` and not on `topologic_core` at all. On PyPI too,
  topologicpy does not depend on `topologic_core`; spacetope's `pyproject.toml` is what pins it.
- **`pythonocc-core` is conda-only.** It is LGPL-3.0-or-later and on conda-forge for osx-arm64, linux-64 and
  linux-aarch64 (7.9.3; 8.0.1.2 from 2026-10-16). It is not on PyPI, so `pip install` alone cannot provide it.
- **The backend is chosen at runtime.** topologicpy uses PythonOCC whenever `OCC` imports, and
  `TOPOLOGICPY_CORE_BACKEND=pythonocc | topologic_core` forces one. No spacetope module imports `topologic_core`
  directly; `realise.py` mentions it only in a comment on the workaround for intermittent failures.

**Steps, in order:**
1. **Environment.** Use one tool that installs both conda and PyPI packages; pixi is recommended, with its lock
   file committed and a ready-made CI action (a conda environment file with `conda-lock` would also work).
   - From conda-forge: `python 3.11.*` and `pythonocc-core ==7.9.3`, the build current when 0.9.71 shipped.
   - From PyPI: everything else, including `topologicpy==0.9.71`.
   - `topologic_core==8.0.0` leaves `pyproject.toml`.
   - The README install section moves from pyenv and `.venv` to `pixi install` / `pixi run`, and says that
     pip alone no longer gives a working engine.
2. **Pin the backend, as the version is pinned.** Set `TOPOLOGICPY_CORE_BACKEND=pythonocc` in the environment,
   so a missing OCC fails loudly instead of falling back. `tests/gates/test_m0.py` asserts the PythonOCC backend
   and the `pythonocc-core` version instead of `topologic_core == 8.0.0`.
3. **Verify everything on the new kernel**, as M14 did for the version bump. Change only the backend and keep
   topologicpy at 0.9.71, so a change in results can only come from the kernel. Run every gate one marker at a
   time, then re-check the facts in `docs/TOPOLOGICPY_NOTES.md` that were measured on `topologic_core`:
   - rule 1: what a failed merge returns, gaps, overlaps and slivers;
   - dictionary transfer through `ByCells` and selectors;
   - doors as apertures (`AddApertures`, `directApertures`);
   - BREP strings and TPY files, including whether files written by `topologic_core` still load;
   - what `Geometry` and `MeshData` give the OBJ and GLB exporters;
   - whether the workaround in `realise.make_cell` is still needed.

   **Speed is the main risk.** The PythonOCC backend is about 25,000 lines of Python over OCC, where
   `topologic_core` is C++. The ~10 ms per cell figure and the gates' timing thresholds may not hold.
4. **Move from `Graph` to `TGraph`**, which is needed for any bump past 0.9.86 whichever backend is used:
   `verify.py`, `io/graph.py`, `tests/test_door_smoke.py` and `tests/test_shaft_smoke.py` move onto the
   `tgraph.py` adapter. `Graph.ByTopology` also misses contacts across curved walls (§2.3).
5. **Keep in step with topologicpy releases.**
   - Pin bumps stay deliberate, verify-everything tasks, but become routine. The first target is the newest
     release without a breaking change, once step 4 is done.
   - A scheduled CI job installs the latest topologicpy and `pythonocc-core` from conda-forge and runs the fast
     suite and the smoke tests, so a break like 0.9.87's shows up the week it ships.
   - Deprecated calls are replaced when a release deprecates them, not when it removes them.
   - Kernel problems found here are reported upstream.
6. **Records.** `NOTICE`, §7 here and the `docs/PLAN.md` licensing rows: `topologic_core` leaves the dependency
   list, and `pythonocc-core` is LGPL and imported only, which would close the kernel question for closed builds
   and commercial licences. §2.3 and M22: the curves track no longer waits on the Rust core.

**Trial, 2026-10-25: spacetope runs on PythonOCC.** This was done in a side environment, with `.venv`,
`pyproject.toml` and the default backend left as they are.

How the side environment was built:

```bash
micromamba create -p ~/mamba/envs/spacetope-occ -c conda-forge python=3.11 pythonocc-core=7.9.3 numpy=2.4.6
# the PyPI versions of .venv (pip freeze), minus topologic_core and torch:
~/mamba/envs/spacetope-occ/bin/python -m pip install -r pins.txt
~/mamba/envs/spacetope-occ/bin/python -m pip install --no-deps --no-build-isolation -e .
export TOPOLOGICPY_CORE_BACKEND=pythonocc   # fail loudly rather than fall back
```

The environment ran Python 3.11.17, topologicpy 0.9.71 and OCC 7.9. `topologic_core` was not installed and
the backend check reported PythonOCC.

**Results.** Every gate was run one marker at a time on both backends. Times are pytest's own; M6 was left
out because it needs torch.

| Gate | PythonOCC | topologic_core | PythonOCC time | topologic_core time |
|---|---|---|---|---|
| M0 | 14 of 17 | 17 of 17 | 2.5 s | 1.6 s |
| M1 | 12 | 12 | 12.1 s | 5.8 s |
| M2 | 26 | 26 | 62.4 s | 25.4 s |
| M3 | 6 | 6 | 49.5 s | 25.6 s |
| M4 | 4 | 4 | 382 s | 334 s |
| M5 | 7 of 8 | 7 of 8 | 12.4 s | 7.2 s |
| M7 | 47 | 47 | 444 s | 300 s |
| M8 | 12 | 12 | 17.3 s | 11.3 s |
| M9 | 10 | 10 | 29.2 s | 14.0 s |
| M10 | 10 | 10 | 414 s | 375 s |
| M11 | 4 | 4 | 72.5 s | 46.3 s |
| M12 | 11 | 11 | 168 s | 160 s |
| M13 | 4 | 4 | 21.7 s | 23.1 s |
| M14 | 5 | 5 | 14.0 s | 6.9 s |
| M15 | 17 | 17 | 265 s | 236 s |
| M16 | 14 | 14 | 19.3 s | 22.4 s |
| M17 | 14 | 14 | 167 s | 211 s |
| other slow | 3 | 3 | 2.3 s | 1.3 s |
| fast suite | 62 of 63 | 63 of 63 | 5.6 s | 8.9 s |

`spacetope generate --generator beam --seed 0` gave the same options with the same scores on both backends.
`eight_rooms_corridor` realised in 6.2 s against 2.3 s, and `school_three_levels` (64 spaces) in 107 s against
67 s. BREP files written on `topologic_core` load on PythonOCC with every cell and every name.

**What the trial found:**
1. **Speed.** Gates that are mostly kernel run about 2× slower, and gates that are mostly solver about 1.1×.
   Realisation is 1.6–2.6× slower. Every timing threshold in the gates still passed.
2. **A failed merge looks different.** A 0.5 mm gap or two disjoint boxes give a `CellComplex` *with* both
   cells and no shared face, where `topologic_core` 0.9.71 gives an empty complex. "No cells means a failed
   build" therefore no longer fires. This accounts for two of M0's failures,
   `test_gap_above_tolerance_builds_nothing` and `test_disjoint_cells_form_cluster_with_disconnected_graph`.
   Options are still protected, because the contacts check finds no shared face. But rule 1's wording,
   `built_nothing` in the smoke tests and the build check in `realise` must test "every intended contact is a
   shared face" (or "the complex is connected"), not "the complex has cells". An overlap still makes a sliver
   (3 cells), and a 0.05 mm gap heals to one shared face, as on 0.9.57.
3. **The backend prints warnings to stdout.** `Topology.Shells - Warning: ...` appears 8 times before the JSON
   of `spacetope generate`, so a consumer reading stdout as JSON breaks. The CLI must send library output to
   stderr, or write its JSON to a file. This belongs in M18a either way.
4. **The pin test**, M0's third failure, asserts `topologic_core == 8.0.0`, as expected.
5. **Not caused by the backend:** one M5 test, a word search left over from when the canvas was first set up,
   fails on both backends, on `main` too, because it matches an ordinary variable name.

**Fix plan (2026-10-25; reviewed, and fixes 1–4 written and tested the same day; results below).** These fixes make
spacetope correct on *both* backends. They do not switch
the default: `.venv` stays on `topologic_core`. Each fix comes with a test that runs on whichever backend is
active, so the suite is the proof on both.

1. **A failed merge is "not connected", not "no cells".** On `topologic_core` 0.9.71 a merge that fails gives
   an empty complex. On PythonOCC it gives every cell with no shared face between the parts that failed to
   meet. One definition covers both: **a build fails when its cells are not one connected group through shared
   faces.** That is what "empty" meant on `topologic_core`, so behaviour there does not change.
   - `realise.py:180`: after `ByCells`, raise `RealiseError` when there are no cells *or* the shared-face graph
     of the built cells has more than one component. The graph comes from `realised_contacts()`, which is
     computed once and kept on the `Realised`, because `verify` reads it again.
   - `tests/test_topologic_smoke.py`: `built_nothing(cc)` becomes `failed_merge(cc)` with the same definition.
     The two failing tests then assert the backend-neutral fact.
   - A new smoke test: a gap between the second and third of three boxes is a failed merge on both backends.
     Measured first: on `topologic_core` every partial gap gives an empty complex, and on PythonOCC it gives
     all three cells with one shared face. So "one connected group" is exactly what `topologic_core` already
     enforced. `realise` on a 1 mm gap now raises on both backends, and `verify` reports it under `built`.
   - Records: rule 1 in the working rules ("test that the cells form one connected group, never `is None`,
     and not the cell count alone"), and `docs/TOPOLOGICPY_NOTES.md` §14 with the PythonOCC facts marked
     `[RUN]`.
2. **The command line's stdout carries only its JSON.** The warnings come from inside topologicpy:
   `CellComplex.ExternalFaces`, called by the `compactness` score (`score.py:43`), calls `Topology.Shells` on
   a shell and prints. More library messages can appear on any version, so the fix is at the boundary:
   - `cli.py`: `main` runs each command with `contextlib.redirect_stdout(sys.stderr)`. The commands write their
     JSON through one `emit(obj)` helper to the real stdout. That covers the ten `print(json.dumps(...))`
     calls. Library messages still appear on stderr.
   - The CLI tests in `tests/gates/test_m1.py` no longer skip to the first `{`: they parse the whole of stdout
     from `generate` and `realise` as one JSON document.
   - The warning itself is reported upstream. It is a library message, not a spacetope fault.
3. **The pin test knows which kernel it is on.** A small `spacetope/kernel.py` holds the one call that asks
   topologicpy which backend is active. That call (`Topology._IsTopologicCoreBackend()`) is private, so it
   stays in this one place. The module returns `{"backend": ..., "version": ...}`.
   - `test_pins` asserts topologicpy 0.9.71, then the active backend's pinned version: `topologic_core` 8.0.0,
     or OCC 7.9 for `pythonocc-core` 7.9.3. When `TOPOLOGICPY_CORE_BACKEND` is set, it also asserts that the
     backend named there is the one in use.
   - `options.json` records the kernel, so an option says what built it. This is additive, and it belongs to
     M18a's contract.
4. **M5's word search is dropped** (decided 2026-10-25). The canvas was set up once and the check has long
   passed, so the test and its line in the M5 gate in `docs/PLAN.md` are removed. M5 now has 7 tests.

**Order and proof.**
- Fixes 4, 3 and 2 come first; they are small and independent. Fix 1 comes last, because it changes
  `realise`.
- The fast suite and M0, M1, M5 and M14 run on both environments after each fix.
- Before committing, every gate runs one marker at a time on both backends (about 45 minutes each), because
  fix 1 touches every build.

**Commits** (no co-author trailer, per the working rules):
- this plan (`STATUS.md` and the `docs/PLAN.md` edit);
- fixes 2–4;
- fix 1 with its notes.

**Results after the fixes (2026-10-25).** Every gate was run one marker at a time on both backends, plus the fast
suite. M6 was left out on PythonOCC because the side environment has no torch.

| | PythonOCC | topologic_core |
|---|---|---|
| fast suite | 63 of 63 | 63 of 63 |
| M0 (with the new partial-gap smoke test) | 18 of 18 | 18 of 18 |
| M1, M2, M3, M4, M5 (now 7), M7–M17, other slow | all pass | all pass |
| kernel-heavy gates (M1, M2, M3, M9, M14) | 11–62 s | 6–26 s |

One more kernel fact turned up and is now in `docs/TOPOLOGICPY_NOTES.md` §14. With a `tolerance` wider than the
gap (1 or 10 mm against 0.5 mm), PythonOCC *heals* the gap by stretching a cell, leaving one cell 0.004 m³ larger.
`topologic_core` 0.9.71 never heals. spacetope merges only at the default 0.1 mm, so its results are unaffected.
The smoke test now asserts the default case on both backends, and "two cells or nothing, never a sliver" for the
wider tolerances.

**What adoption would now take:** steps 1–6 above, plus the fix plan above, and new kernel facts in
`docs/TOPOLOGICPY_NOTES.md` marked `[RUN]` on PythonOCC. Finding 1 is a cost to accept, or to win back with
fewer builds (M10 already builds only what is shown).

### 2.7 Addendum (2026-11-02): diagrams as input, and more complex buildings

Two tracks were planned on top of this programme in
`docs/2026-11-02_DIAGRAMS_AND_COMPLEX_BUILDINGS_PLAN.md`, on branch `plan-diagrams-complex-buildings`:
**track D**, the affinity/adjacency *diagram* (bubble diagram, SLP chart) as a first-class input — a
BriefGraph model with area-first bubbles and a position sidecar, an editor in the canvas (M25), staged
import from charts, vector drawings and hand sketches (M27), and the M20 affinity report rendered back on
the architect's own drawing; **track X**, buildings past the current window — departments/zones declared
or derived by clustering the affinity graph, solved hierarchically and in parallel (M26), circulation
loops, hierarchies, multi-core stair coverage and atria (M28), and the graph post-processor of the
2026-09-14 exploration once its decoder conditions are measured (M29). Both tracks are pure Python on the
cheap model and need only M18a + M19 to start, so they may jump the curves queue; the decision rows are in
that document's §4.

---

## 3. What the engine does today

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

**Interfaces**: `spacetope generate|realise|floors|export|programme`, a FastAPI backend, and a React canvas.

**Programmes** (`docs/PROGRAMMES.md`) describe a *kind* of building rather than one building: office, secondary
school, clinic and housing ship with the project. `spacetope programme clinic --seeds 0-99 --out dir` draws a
hundred briefs; `--dataset rows.jsonl` turns them into training rows instead, at about 5,500 an hour across the
four families. `variations` perturbs a brief seven ways for robustness sweeps.

---

## 4. What was measured, and what it cost

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
  sub-millimetre gap no longer heals. Since 2026-10-25 `realise` fails a build whose cells are not one group
  joined through shared faces, which covers every version and both backends (§2.6).
- **Z3 agrees with CP-SAT.** On small briefs both enumerate identical sets of wall assignments (16 of 16, 64 of
  64) and both call the contradictory brief impossible, so the M10–M12 changes to the solver model neither
  removed nor invented arrangements.
- **There are no gaps to close.** Across seven fixtures and all three generators, enclosed empty ground is zero.
  The empty ground is the plan's outline, which the architect has confirmed is not a defect and may be a feature.

---

## 5. Known limits

These are measured and gated, not suspicions.

- **The beam on chained corridors** reaches a verified layout on one seed in four. `cpsat` finds the corner from
  feasibility alone. Use `cpsat` for briefs with `segments: N`.
- **The dual enumerator** reaches fewer topologies than the beam on briefs without a corridor, and none at all on
  `house_ground` or `gallery_rich`. The cause was measured on 2026-10-03: a rectangular plan is a perfect tiling,
  so those rooms cannot tile within ±10 % (they need about ±50 % and ±30 %). It is a property of the method, not a
  defect, and the generator now says so with the tolerance that would clear it instead of returning nothing.
- **CP-SAT is not seed-deterministic.** Speed was kept over reproducibility. Two runs of the same brief can give
  different plans, so gate assertions must hold for any valid solution.
- **Two shafts no longer guarantee two ways down** once a spine is chained: the stair and the lift can land on
  different segments, and the route between levels then passes through the opening they share. The option
  analysis reports the number of independent routes so this is visible.
- **`seqpair` is not registered.** Bottom-left packing pulls rooms off the corridor they must touch, so it
  returns nothing past about ten spaces on a corridor.
- **M6's learned scorers** never beat the hand-tuned beam and are not in the pipeline.

---

## 6. Open questions (`docs/PLAN.md` §6)

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

## 7. Licensing

Since 2026-10-16 spacetope is **dual-licensed: AGPL-3.0-or-later, or a commercial licence** from
**Adventurous Systems** (`COMMERCIAL.md`). Versions up to `c419c33` were Apache-2.0 and stay so for whoever has
them. Adventurous Systems holds the copyright (by written assignment from the author, who held it personally
until then) and the CLA lets contributions be relicensed, so Adventurous Systems can use spacetope in a closed
product regardless of the public licence. topologicpy 0.9.71 is LGPL-3.0-or-later and is imported, not copied or modified, which suits
both licences. `NOTICE` carries the detail.

One obligation is open, and it now limits the commercial side only. `topologic_core`, the binary geometry kernel, declares no licence in its metadata and
its upstream source is AGPL-3.0, and it is an in-process C extension. **A Rust core owned by this project is in
development to replace it.** Meanwhile topologicpy 0.9.71 prefers a PythonOCC backend and falls back to this
kernel only because `pythonocc-core` (LGPL-3.0) is not installed, so that may be a faster route; it is untested
and would need the same verify-everything treatment as a version bump. The AGPL release may carry the binary;
a closed build or a commercial licensee may not, until one of the two lands.

## 8. Running it

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

## 9. A note on the documents

Every dated note under `docs/` is excluded by `.gitignore`, so the notes are local working documents and not
part of the upstream repository. That includes the design and exploration notes this status refers to:
the stretch-goal design, the performance and learning exploration, and the topologicpy options note. `docs/PLAN.md`,
`docs/TOPOLOGICPY_NOTES.md`, `docs/ALGORITHM_SURVEY.md` and this file are tracked.
