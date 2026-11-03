# Step 0.3 dry run and run estimates

One seed of `bench.py` on a small, a medium and one of the two largest fixtures, all four generators,
bench budgets unchanged. Machine and pins: `machine.json`. Code: `f6bc234` (tag `paper-v1`).

```
.venv/bin/python bench.py --fixtures three_rooms clinic school_three_levels --seeds 0 \
    --out bench/paper/dryrun_scoreboard.csv --per-option bench/paper/dryrun_options.csv
```

Wall clock 3:33, of which 210 s is generation and realisation; the rest is start-up.

| fixture | spaces | treemap | beam | cpsat | dual | per seed |
|---|---|---|---|---|---|---|
| `three_rooms` | 3 | 0.1 s | 0.6 s | 0.7 s | 18.2 s | 19.6 s |
| `clinic` | 11 | 0.4 s | 4.0 s | 24.5 s | 5.0 s | 34.0 s |
| `school_three_levels` | 64 | declines | 82.7 s | 74.1 s | declines | 156.8 s |

`dual` spends its whole 20 s budget even on three rooms, so it, not the brief's size, sets the floor
for small single-level fixtures.

## What the dry run already says about the new checks

- **beam and CP-SAT lose nothing.** `verified == options` on all three fixtures (8/8, 8/8, 8/8 and
  8/8, 7/7, 6/6). The brief predicted treemap losses only, and that is what happened.
- **treemap gets 0 of 1 everywhere**: `bands` on `three_rooms`, and `doors required_contacts bands`
  on `clinic`.
- **The adjacency score does vary** once the intent comes from the brief: 1.0 for beam, CP-SAT and
  dual, 0.2308 for treemap on `clinic`. The pilot's "adjacency is 1.00 for every option" was an
  artefact of taking the intent from the placement being judged.
- **Unasked contacts are confirmed at the pilot's scale.** `school_three_levels`: 187 touching pairs,
  75 required, **105 room-to-room pairs nobody asked for** (beam); 196/75/112 for CP-SAT.
- **The pre-verifier agreed with the kernel on 49 of 49 options**, as in every run so far.

## Estimates for the runs in order

Sequential, one process, from the per-fixture costs above interpolated on space count and on which
generators decline a brief. Treat them as ±50 %: they exist so a run is not launched blind.

| # | Experiment | Estimate | Basis |
|---|---|---|---|
| 1 | E2, E3 | **≈ 1 h** | 14 fixtures × 5 seeds; ≈ 690 s per seed (272 s over the 8 single-level fixtures with four generators, 418 s over the 6 multi-level with two) |
| 2 | E1d | minutes | reads `options_e2.csv` plus the E1 mutants |
| 3 | E1 faults | **30–45 min** | 8 faults × ≥100 placements, process pool of 6, verifying saved placements |
| 4 | E1b metamorphic | **20–30 min** | 6 relations over the same sample |
| 5 | E10a, E10c | < 1 min | pure CSV analysis |
| 6 | E5 | 25 s | `pytest -m gate_m13` |
| 7 | E8 ablations | **≈ 25 min** | beam-only grid ≈ 9 min, CP-SAT-only ≈ 16 min, 5 seeds each |
| 8 | E9 planted | **5–8 h** | ≈ 33 sweep points × 20 seeds ≈ 660 briefs, ≈ 30 s each; CP-SAT's 20 s budget dominates |
| 9 | E14 repro | **≈ 2 h** | 7 seed-runs, 4 of them deterministic on one worker and so slower per solve |

**Total ≈ 10–12 h**, dominated by E9. E9 and E14 are the two worth splitting across sessions; both
stream rows and resume.

## Departures from the brief, so far

- Step 0.3 was run after Steps 1–6 rather than before, because the machine rebooted mid-sweep and the
  code was already written. The estimates above are therefore measured on the frozen code, which is
  what the later runs will use.
- The brief's expectation that E5 "expects identical sets (16 of 16, 64 of 64 when recorded)" cannot be
  read off `gate_m13` as it stands: the gate passes or fails without printing the counts. E5 needs that
  print added before it can produce `e5_z3.txt`.
