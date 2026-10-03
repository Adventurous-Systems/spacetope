# Algorithm survey — assembling a tolerant space list into a 3D cell complex

Survey date 2026-09-13 (~35 searches). Suitability score 1–5 is for **spacetope's** need: exact face-sharing boxes, ±10–15 % dimensional tolerance, adjacency/access requirements, corridors + stairs/elevators, multi-level, K options for an architect, verifiable in topologicpy. `(bk)` = background knowledge, not a fetched source.

Columns: **Adj** = how adjacency requirements are handled · **Tol** = how dimensional tolerance is handled · **Exact** = yields exact face sharing (Y), only after snapping (S), or no (N).

## A. Classical space allocation and floor-plan generation

| # | Method | Core idea | Adj | Tol | Exact | Dim | Score |
|---|---|---|---|---|---|---|---|
| A1 | Facility layout QAP: CRAFT / CORELAP / ALDEP; Liggett 2000 survey (*Automation in Construction* 9) | Assign activities to grid locations minimising flow×distance; pair-swap improvement | weighted flow matrix | area = cell count | N (blobs) | 2D | 2 — seeding only |
| A2 | Flemming LOOS 1986/89 (*EPB* 13/16) | Orthogonal structures = left-of/below relations between rectangles; rule-based enumeration with pruning; LP dimensioning once topology fixed | required "shares wall segment" relation | LP min/max sides | Y | 2D | **4** — direct ancestor of our topology+LP split |
| A3 | Rectangular dissection enumeration: Steadman *Architectural Morphology* 1983; Steadman & Mitchell "Architectural morphospace" (*EPB* 2010); Bloch/Krishnamurti | Exhaustively enumerate dissections of a rectangle into n cells, read adjacency graphs | read off | post-dimensioning | Y | 2D | 3 — small briefs (≤8–10 rooms), great for option UX |
| A4 | Roth, Hashimshony & Wachman 1982/85 | Adjacency matrix → planar graph → dual → dimensioned plan; several alternatives | graph edges = shared walls | post | Y | 2D | 4 |
| A5 | Rectangular duals / Regular Edge Labellings: Koźmiński–Kinnen 1985, Bhasker–Sahni 1988, Kant & He (*TCS* 1997), Fusy transversal structures; **GPLAN** (arXiv 2008.01803, *AiC* 2021), **G2PLAN / Bisht et al.** (*CGF* 2022), DPLAN (arXiv 2606.21159), L-shaped duals (*JOCO* 2025) | PTP graph → all topologically distinct rectangular/orthogonal duals in linear time; corridor node added when graph is not PTP; LP with min/max width/height per room | hard (graph) | LP bounds = our ±tol | Y | 2D per level | **5** for briefs with rich adjacency graphs |
| A6 | Squared rectangles (Brooks–Smith–Stone–Tutte 1940) (bk) | Electrical-network duality; dimensions solve linearly | – | rigid | Y | 2D | 1 |

## B. Grammar / subdivision / growth

| # | Method | Core idea | Adj | Tol | Exact | Dim | Score |
|---|---|---|---|---|---|---|---|
| B1 | Shape grammars (Stiny); GRAPE graph-grammar implementation (Grasl & Economou 2013); Transformational Palladians (*EPB* 2012) | Graph rewriting on a plan graph | stylistic rules | weak | Y | 2D | 2 |
| B2 | CGA shape (Müller/Wonka SIGGRAPH 2006), CGA++ 2015 | Split/repeat rules subdivide a mass into floors/rooms | none | relative splits | Y | 3D | 3 — mass → levels → cells preprocessor |
| B3 | Squarified treemap floor plans: Marson & Musse 2010; Bruls et al. 2000 (`squarify` on PyPI) | Recursive area-proportional subdivision keeping aspect ≈ 1, corridor inserted after | hierarchical zones only | area + aspect band | Y | 2D (extrude per level) | **4** — sub-second baseline/seed |
| B4 | Constrained growth: Lopes et al. 2010 (TNO) | Grid growth of rooms from seeds with adjacency/area constraints; rectangles then L-shapes; connected floors | constraints | area | Y (grid) | 2.5D | 3 |
| B5 | **MANSION** (arXiv 2603.11554, 2026) | Multi-floor topology-aware constrained growth; vertical cores removed from free region first; load-bearing walls persist across floors as hard constraints; MLLM proposes seeds, energy objective ranks | constraints | area | Y | 3D | **4** — the multi-level discipline to copy |
| B6 | Bao, Yan, Mitra, Wonka 2013 (*TOG*) "good building layouts" | Portal graph of local layout shape-spaces linked by grammar transitions | – | continuous within shape-space | Y | 2D | 3 — post-selection exploration UI |
| B7 | Slicing tree / BSP / k-d subdivision of a volume (Wonka, Marson, Koenig & Knecht 2014 subdivision variant) | Mass → horizontal cuts (levels) → binary H/V cuts per level | via cut order | soft leaves | Y | 3D | 4 |

## C. Optimisation and metaheuristics

| # | Method | Core idea | Adj | Tol | Exact | Dim | Score |
|---|---|---|---|---|---|---|---|
| C1 | Michalek, Choudhary & Papalambros 2002 (*Eng. Opt.* 34) | Discrete topology decisions by evolutionary outer loop, continuous (x,y,w,h) by SQP inner loop | pairwise constraints | bounds | Y when active | 2D | **4** — the discrete/continuous split is our architecture |
| C2 | Rodrigues, Gaspar & Gomes 2013 EPSAP (*CAD* Part 1/2) + multi-level extension (*AiC* 35) | Evolutionary strategy + stochastic hill climbing on rooms/walls/openings; **stairs and lifts as parametric objects across floors** | penalties | penalties | S | 3D | 4 |
| C3 | Bahrehmand et al. 2017 (*Graphical Models*) | Interactive GA with spatial-quality metrics and user preference weights | metrics | metrics | S | 2D | 3 — metric/UX ideas |
| C4 | Merrell, Schkufza & Koltun 2010 (SIGGRAPH Asia) | Bayesian net for brief → Metropolis/SA on a grid (cost = adjacency + area + shape + footprint) → 3D building, stairs as rooms | cost | area cost | Y (grid) | 3D | 4 |
| C5 | Peng, Yang & Wonka 2014 deformable templates | ILP tiles domain with template instances, then continuous deformation | template | deformation | Y | 2D | 3 — rooms in few types |
| C6 | **Wu, Fan, Liu & Wonka 2018 MIQP** (*CGF*) | Rooms as rectangle unions; binary left/right/above/below disjunctions for non-overlap; binary adjacency indicators; quadratic area-deviation objective; hierarchical zones→rooms for scale | binary indicators | bounds + quadratic penalty | Y (adjacency = coordinate equality) | 2D, extends to 3D | **5** — strongest exact formulation |
| C7 | Laignel et al. 2021 (*AiC* 123) CP + GA | Envelope grid; CP assigns cells with adjacency/area; GA explores | CP | area | Y (grid, blobby) | 2D | 3 |
| C8 | Guo & Li 2017 (*FoAR* 6) multi-agent topology finding | Rooms as agents attracted by adjacency, evolutionary refinement; multi-floor topology | forces | – | S | 3D | 3 |
| C9 | **Magnetizing Floor Plan Generator** (Gavrilov, Schneider, Dennemark, Koenig 2020; GitHub hellguz) | Rooms attach one-by-one to a growing corridor spine; public buildings | spine contact | – | S | 2D | **4** — corridor logic |
| C10 | Koenig & Knecht 2014 (*AI EDAM* 28): dense packing vs subdivision; CPlan (C#) | Packing: free movement, overlap penalised, diverse. Subdivision: k-d tree, always valid, faster | cost | cost | S / Y | 2D | 4 (subdivision) |
| C11 | **CP-SAT / MILP box placement with adjacency** (OR-Tools `AddNoOverlap2D`; arXiv 2512.18034 CDCL→CP-SAT warm start 2025) | Interval variables per axis; sizes as integer vars in [0.85·n, 1.15·n]; Boolean b_ij ⇒ x_i+w_i = x_j ∧ y-overlap ≥ door width; K solutions via blocking clauses / solution callback | Booleans | native integer bounds | Y | 2D/3D | **5** |

## D. 3D / multi-level and data-driven

| # | Method | Core idea | Adj | Tol | Exact | Dim | Score |
|---|---|---|---|---|---|---|---|
| D1 | Building-GAN (Chang et al. ICCV 2021, arXiv 2104.13316); multi-storey plan from volumetric design via GNN (EasyChair); Building-GNN (Zhong, Koh, Fricker eCAADe 2023); Building-graph-AI (*IJAC* 2025) | Program graph → voxel graph (multi-storey) via GNN/pointer nets | learned | voxel size | Y (coarse) | 3D | 3 now / 4 as ML target |
| D2 | Graph2Plan (2020), House-GAN/++ (2020/21), HouseDiffusion (CVPR 2023), WallPlan 2022, MaskPLAN 2024, Tell2Design, GSDiff (2408.16258), DStruct2Design (2407.15723), boundary-constrained diffusion (2602.01949), markup vector plans (2604.04859); review arXiv 2504.09694 (2025) | Graph-conditioned generation of residential plans (RPLAN, ~80k) | learned | none | S | 2D | 2 direct; formulation to mirror later |
| D3 | RL: SpaceLayoutGym laser-wall DRL (Kakooee & Dillenburger 2025), multi-agent DRL (*AEI* 2025), LLM + RLVR plans (2605.14117), **space-syntax-guided post-training SSPT** (2602.22507) | Policies over sequential wall/room placement with verifiable rewards | reward | reward | S | 2D | 3 — host for learned proposal over partial assemblies |
| D4 | Roominoes (arXiv 2112.05644) | Retrieve existing 3D rooms, 2D layout, deform to fit; Z3/IP variant maximising wall-to-wall adjacency yields compact void-free layouts | IP | deformation | S | 3D | 3 |
| D5 | 3D VLSI floorplanning: 3D-subTCG, 3D-CBL, labeled tree + dual sequences (ISPD 2008); review Springer 2022 | Layered: per-layer 2D representation + layer assignment | cost | soft modules | Y | layered 3D | 4 (layered) / 2 (true 3D) |

## E. Geometric and combinatorial packing; VLSI representations

| # | Method | Core idea | Adj | Tol | Exact | Dim | Score |
|---|---|---|---|---|---|---|---|
| E1 | Bin/strip packing: bottom-left, skyline, maximal rectangles, guillotine (`rectpack`); 3D extreme points (Crainic 2008; `py3dbp`) | Minimise waste | none | none | S (gaps normal) | 2D/3D | 2 — envelope-fit checks only |
| E2 | **Slicing floorplans (Wong & Liu 1986)** (bk) | Binary H/V cut tree, SA on normalised Polish expressions; soft modules via shape curves merged bottom-up | cost | shape curves (fixed area, aspect band) | Y, no dead space if soft | 2D | **5** for per-level representation |
| E3 | **Non-slicing: sequence pair (Murata 1996), B*-tree (Chang 2000), O-tree, corner block list, TCG**; fixed-outline Fast-SA with soft blocks (Chen & Chang *TCAD* 2006), Adya & Markov 2003; soft sizing under fixed SP is convex (Young/Chu/Ho, Lagrangian) | Relative left/below relations; compaction gives exact contacts; fixed outline = envelope | must be added as cost/constraint (abutment literature exists) | soft modules ≈ our rooms (ours tighter: both sides bounded, easier LP) | Y | 2D | **5** for search-space encoding |
| E4 | Treemap / squarify | see B3 | | | | | |
| E5 | Tetris-like / jigsaw assembly | see G3 | | | | | |

## F. Topology / cell-complex specific

| # | Method | Idea | Score |
|---|---|---|---|
| F1 | **topologicpy** (Jabi): `Cell.Box`, `CellComplex.ByCells` (shapely trims coplanar overlaps, splits partial abutments), `Decompose`, `NonManifoldFaces`, `Graph.ByTopology(viaSharedTopologies=True)` = our wall-node graph realised; papers: Topologic toolkit (eCAADe 2018), Aish & Jabi non-manifold topology (*ASR* 2016), Jabi & Alymani graph ML on 3D topological models (2020), Jabi "Syntopic integration" (Springer 2025), multi-agent movement (*ASR* 2025) | Representation/analysis substrate; **nothing upstream synthesises a complex from a brief — that gap is spacetope** | **5 as substrate**, 0 as generator |
| F2 | Mora, Bédard & Rivard 2008 (*AEI*) conceptual structural design from architectural topology | Structure-from-spaces reasoning; feeds the "walls stack across levels" metric | 2 |
| F3 | Kalay cellular spatial models; Steadman "generating cellular layouts" | Background only; no primary source surfaced | 2 |

## G. Graph-matching / assembly formulations for wall-node ↔ wall-node connection

| # | Formulation | Assessment | Score |
|---|---|---|---|
| G1 | Bipartite matching / Hungarian on wall-face compatibility cost | A matching is local; global realisability (cycles must close geometrically) is not guaranteed. Use only as heuristic scorer / door-to-corridor assignment | 2 |
| G2 | **CSP over face pairings with dimensional compatibility**: per room pair a relation ∈ {left, right, front, back, above, below, none}; consistency = interval algebra per axis; required adjacencies; envelope; then LP for sizes | Exactly the sequence-pair / TCG / MIQP view; CP-SAT handles 50–100 rooms with hierarchy | **5** |
| G3 | Jigsaw / tiling with tolerant edges (deformable templates, Roominoes) | Good when rooms repeat | 3 |
| G4 | Wave Function Collapse (Gumin 2016), Model Synthesis (Merrell 2007/09; Punch-Out 2025) | Grid tiles with local adjacency rules; great for cores/corridor modules on a structural grid, poor for heterogeneous room sizes | 3 (cores/circulation) |
| G5 | **Beam search / MCTS over partial assemblies**: each step = (free wall face, unplaced room, offset); incremental interval validity; final topologicpy check; beam width = diversity = options | Native to our wall-node metaphor; natural host for a learned policy/value later | **4** |
| G6 | SAT/SMT (Z3): dungeon layouts with linear constraints (FDG 2020), ORCSolver (2002.09925) | Great for feasibility and enumerating distinct topologies with blocking clauses; weaker than CP-SAT for quadratic objectives | 4 |

## H. Metrics for ranking options

1. **Adjacency/access satisfaction** — fraction of required pairs sharing a face with overlap ≥ door (0.9 × 2.1 m); from `NonManifoldFaces` + realised graph.
2. **Dimensional deviation** — Σ |d − d*| / d* over w, l, h; aspect penalties.
3. **Compactness** — external surface ÷ volume; external vertical face area (`Decompose`).
4. **Circulation efficiency** — circulation area ÷ net area; mean shortest path on the dual graph weighted by centroid distance; dead-end count.
5. **Space-syntax integration / depth** on the dual graph (networkx closeness; SSPT-style public-space dominance).
6. **Daylight proxy** — fraction of habitable rooms with ≥ 1 external vertical face; external face area per level.
7. **Structural alignment** — fraction of internal vertical face planes on level k coincident with a plane on level k−1 (MANSION treats as hard).
8. **Envelope fit** — union volume ÷ envelope volume; max protrusion.
9. **Vertical connectivity** — every level's dual graph reachable through stair/elevator cells; cores stacked (shared horizontal faces).

Multi-objective ranking: Pareto front (pymoo/DEAP) or architect-weighted sum (Bahrehmand interactive weights).

## Ranked shortlist and selection

1. **Relational CP-SAT model with tolerance bounds** (C6 formulation on C11 tooling) — integer mm sizes in the tolerance band, Boolean adjacency with door-overlap, corridor as elongated soft space, `AddNoOverlap2D` per level, K diverse solutions via blocking clauses. Exact by construction. **Selected: the exact engine (M4).**
2. **Rectangular dual + LP dimensioning** (A5) — enumerates all topologically distinct plans when the brief supplies a rich adjacency graph; corridor node repairs non-PTP graphs. **Selected as optional enumerator for rich briefs (M4, stretch).**
3. **Sequence pair / slicing tree + SA with soft sizing** (E2/E3) — the encoding that scales to 100–300 rooms. **Selected as the encoding vocabulary; SA variant deferred until CP-SAT hits its size limit.**
4. **Layered 3D: cores first, then per-level solve, cross-level alignment as soft term** (B5, C2, D5) — **Selected as the multi-level discipline (M3).**
5. **Beam search over incremental wall-to-wall attachment** (G5) — spacetope's native mechanism, gives options quickly, becomes the ML host. **Selected as the first generator (M2).**
6. **Squarified treemap / k-d subdivision seed** (B3, B7, C10) — sub-second baseline and initialiser. **Selected as baseline in M2.**
7. **Magnetizing corridor spine** (C9) — **Selected as the corridor heuristic inside beam search (M2).**
8. **Z3 feasibility enumeration** (G6) — cross-check only; not scheduled.

Status 2026-09-20 (checked against `spacetope/solve/`): 1, 4, 5 and 6 are implemented; 2 is implemented as the
single-level generator `dual` (`solve/dual.py`, PLAN M12); 7 exists as corridor-first placement plus corridor
stretch, without the post-placement attraction; 3 and 8 are not implemented (PLAN M16, M13). Designs:
`docs/2026-09-14_STRETCH_GOALS_DESIGN.md`; programme: `docs/PLAN.md` §4.9.

Rejected for now: QAP grids (A1), packing heuristics (E1), 2D residential generative models (D2) as generators, WFC (G4) except possibly for core placement on a structural grid, true 3D cube packing.

**Data-driven later**: CP/LP layer remains the verifier; ML replaces the proposal layer — a GNN/diffusion model conditioned on the brief graph emitting relation sets (sequence pairs / contact-edge sets) or scoring beam-search moves (Graph2Plan / HouseDiffusion / Building-GAN style); training data = spacetope's own verified options exported via `Graph.ExportToCSV`, plus real buildings' adjacency graphs from an IFC corpus via `Graph.ByTopology`; SSPT-style RL post-training with section H metrics as verifiable rewards.

**Python libraries**: `ortools` (CP-SAT, LP), `networkx` (planarity, embeddings, duals, space syntax), `shapely`, `scipy.optimize`/`cvxpy`, `topologicpy`, `squarify`, `z3-solver`, `pymoo`/`DEAP`, `rectpack`/`py3dbp` (envelope sanity only), `torch_geometric` (later).
