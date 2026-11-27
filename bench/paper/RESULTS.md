# SpaceTope paper experiments: results and analysis

Every table below is computed from the files in this folder by `bench/paper_results.py`, which fills
`RESULTS.in.md` and writes this file. Edit the template, not this file. Figures come from
`bench/paper_figures.py`.

- **Machine:** Apple M3 Pro, 11 cores, 18 GB, macOS 14.1, Python 3.11.9 (`machine.json`).
- **Pins:** topologicpy 0.9.71, topologic_core 8.0.0, ortools 9.15.
- **Code:** frozen at `f6bc234` (tag `paper-v1`). Later commits change the engine by licence header lines
  only; §11 lists what else changed and which runs it touches.
- **Budgets:** the bench defaults. CP-SAT and dual 20 s per call, 5 s per CP-SAT solve; beam width 16; K = 8.
- **Statistics:** mean ± standard deviation over seeds; Wilson 95 % intervals on proportions; paired Wilcoxon
  signed-rank tests on the same fixture and seed. No mean is pooled over fixtures of different sizes: tables
  are per fixture, and the paired tests count cells.

## Summary

1. **The verifier rejects every injected fault and accepts every control.** Geometry and hard-constraint
   faults: 950/950 (99.6–100.0 %). Faults against the brief: 1567/1567 (99.8–100.0 %). The pilot's seven checks caught 4 of
   21 brief faults; the two new checks close that. Controls rejected: 0/321 (0.0–1.2 %).
2. **The verdict, the topology class and the scores are invariant** under translation, mirroring, rotation,
   reordering and swapping identical spaces, on every placement tested.
3. **The pre-verifier agrees with the kernel** on all but two of about 6,000 placements. It never hides a
   placement the kernel accepts.
4. **CP-SAT and Z3 enumerate identical solution sets** on the two small briefs and both reject the
   contradictory one.
5. **CP-SAT is the reliable generator, the beam the fast one.** On planted briefs with a known solution,
   CP-SAT solves all 520. The beam solves fewer as rooms and required contacts grow, and about
   a quarter of the corridor-served family. The treemap baseline meets the brief on 1 of 240.
6. **The beam's warm start is what lets CP-SAT reach the two large briefs.** Without it CP-SAT verifies 1 and
   2 options on them instead of 29 and 29. The beam's re-dimensioning pass costs about a third of its time
   and lowers deviation slightly; it does not change what verifies.
7. **Three scores never tell options apart** (adjacency, vertical, and daylight almost never), and options
   carry many contacts nobody asked for: about 105 unasked room-to-room pairs on the 64-space school.
8. **Reproducibility is exact for the beam and for CP-SAT in deterministic mode**, absent for CP-SAT in
   default mode, and absent for `dual` in either mode.

Open items that affect what the paper may claim are in §11.

---

## 1. E1: fault injection (Table 6.1)

```
.venv/bin/python bench/validate.py --placements bench/paper/placements \
    --faults bench/paper/e1_faults_v2.csv --metamorphic bench/paper/e1b_metamorphic_v2.csv
```

Input: the 424 verified placements of seeds 0 and 1 from E2, all generators and fixtures. One
fault of each kind is applied to each placement where the fault applies (a placement with no shaft gets no
shaft fault). Code: working tree after `2922bcc` with the corrected `bench/validate.py` (§11). Six workers.

| fault | kind | placements | rejected (Wilson 95 %) | checks that failed (placements) | adjacency < 1 | out of band |
|---|---|---|---|---|---|---|
| `overlap_50mm` | geometry | 424 | 424/424 (99.1–100.0 %) | `built` 424, `cell_count` 424, `no_slivers` 424, `contacts` 424, `dictionaries` 424, `constraints` 424, `doors` 424, `required_contacts` 424, `bands` 424 | 297 | 0 |
| `shaft_half_height` | hard constraint | 211 | 211/211 (98.2–100.0 %) | `constraints` 211, `doors` 176, `required_contacts` 176, `bands` 35 | 176 | 35 |
| `out_of_envelope` | hard constraint | 315 | 315/315 (98.8–100.0 %) | `constraints` 315 | 0 | 0 |
| `gap_required` | brief | 408 | 408/408 (99.1–100.0 %) | `built` 21, `cell_count` 21, `no_slivers` 21, `contacts` 21, `dictionaries` 21, `constraints` 101, `doors` 328, `required_contacts` 408, `bands` 21 | 408 | 0 |
| `shrink_room` | brief | 424 | 424/424 (99.1–100.0 %) | `built` 11, `cell_count` 11, `no_slivers` 11, `contacts` 11, `dictionaries` 11, `constraints` 11, `doors` 90, `required_contacts` 107, `bands` 424 | 107 | 424 |
| `grow_out_of_band` | brief | 424 | 424/424 (99.1–100.0 %) | `constraints` 107, `bands` 424 | 0 | 424 |
| `door_slide` | brief | 311 | 311/311 (98.8–100.0 %) | `constraints` 173, `doors` 311 | 0 | 0 |
| `gap_incidental` | control | 321 | 0/321 (0.0–1.2 %) | none | 0 | 0 |

Rejected by kind, pilot (seven checks, 70 placements, 2026-10-16) against this run (nine checks):

| kind | pilot, seven checks | this run, nine checks |
|---|---|---|
| geometry and hard constraint | 13/13 | 950/950 (99.6–100.0 %) |
| brief | 4/21 | 1567/1567 (99.8–100.0 %) |
| control (must pass) | not run | rejected 0/321 (0.0–1.2 %) |

**Reading.** Every fault is rejected, and each by the check that names it: an overlap fails the build, a gap at
a required contact fails `required_contacts`, a room out of its band fails `bands`, a slid room fails `doors`.
The two faults the pilot let through (a room grown out of band, a room 1 mm off a required contact) are the
two the new checks were written for.

**Adjacency is not a substitute for the check.** The adjacency score falls below 1 for a lost required
contact but not for a room out of band, out of the envelope, or with too short a door wall. A score ranks;
only a check rejects.

**The control needed a correction, and the first run is kept.** In the first run (`e1_faults.csv`) the
control was rejected 81/364 (18.3–26.8 %). Each rejection was correct: moving a room 1 mm off an incidental
neighbour also pushed it out of the envelope (66 placements), left a door wall 1 mm short (18), or took it
off its only corridor (10; where access is by the door rule the corridor contact is not a required pair).
The control now opens a joint only where the move does nothing else. First run, for the record:

| fault | kind | placements | rejected (Wilson 95 %) | checks that failed (placements) | adjacency < 1 | out of band |
|---|---|---|---|---|---|---|
| `overlap_50mm` | geometry | 424 | 424/424 (99.1–100.0 %) | `built` 424, `cell_count` 424, `no_slivers` 424, `contacts` 424, `dictionaries` 424, `constraints` 424, `doors` 424, `required_contacts` 424, `bands` 424 | 297 | 0 |
| `shaft_half_height` | hard constraint | 211 | 211/211 (98.2–100.0 %) | `constraints` 211, `doors` 176, `required_contacts` 176, `bands` 35 | 176 | 35 |
| `out_of_envelope` | hard constraint | 315 | 315/315 (98.8–100.0 %) | `constraints` 315 | 0 | 0 |
| `gap_required` | brief | 408 | 408/408 (99.1–100.0 %) | `built` 22, `cell_count` 22, `no_slivers` 22, `contacts` 22, `dictionaries` 22, `constraints` 102, `doors` 328, `required_contacts` 408, `bands` 22 | 408 | 0 |
| `shrink_room` | brief | 424 | 424/424 (99.1–100.0 %) | `built` 11, `cell_count` 11, `no_slivers` 11, `contacts` 11, `dictionaries` 11, `constraints` 11, `doors` 90, `required_contacts` 107, `bands` 424 | 107 | 424 |
| `grow_out_of_band` | brief | 424 | 424/424 (99.1–100.0 %) | `constraints` 107, `bands` 424 | 0 | 424 |
| `door_slide` | brief | 311 | 311/311 (98.8–100.0 %) | `constraints` 173, `doors` 311 | 0 | 0 |
| `gap_incidental` | control | 364 | 81/364 (18.3–26.8 %) | `constraints` 66, `doors` 28 | 0 | 0 |

**Some brief faults also fail the build**, in both runs (`gap_required` 21, `shrink_room` 11). Where the
moved or shrunk room was joined to the rest only through that wall, the cells no longer form one group
through shared faces, which is a failed merge by rule 1. Every other check then fails with it.

## 2. E1b: metamorphic relations

Same command and sample as E1.

| relation | placements | verdict unchanged | same topology class | scores equal |
|---|---|---|---|---|
| `translate` | 109 | 109/109 (97–100 %) | 109/109 (97–100 %) | 109/109 (97–100 %) |
| `mirror_x` | 424 | 424/424 (99.1–100.0 %) | 424/424 (99.1–100.0 %) | 424/424 (99.1–100.0 %) |
| `mirror_y` | 424 | 424/424 (99.1–100.0 %) | 424/424 (99.1–100.0 %) | 424/424 (99.1–100.0 %) |
| `rotate` | 109 | 109/109 (97–100 %) | 109/109 (97–100 %) | 109/109 (97–100 %) |
| `shuffle` | 424 | 424/424 (99.1–100.0 %) | 424/424 (99.1–100.0 %) | 424/424 (99.1–100.0 %) |
| `swap_identical` | 329 | 329/329 (98.8–100.0 %) | 329/329 (98.8–100.0 %) | 329/329 (98.8–100.0 %) |

Translation and rotation apply only where the brief has no envelope (or a square one), hence fewer placements.

**Reading.** The verdict, the topology class and every score except `envelope_fit` are unchanged under all
six relations. The verifier does not depend on where the plan sits, which way it faces, the order of the
space list, or which of two identical rooms is which.

**`swap_identical` needed a correction, and the first run is kept.** The first definition called two rooms
identical when programme, size, tolerance and level wish matched, and ignored what each must touch. In
`clinic`, `consult_1` and `consult_2` are the same size but only `consult_1` must touch `treatment`.
Swapping them breaks that contact and the verifier rejects it, correctly. All 87 first-run failures are
swaps of rooms with different required neighbours; all 268 swaps of rooms with the same neighbours pass.
The relation now also requires the same wishes, required contacts and marked doors. First run:

| relation | placements | verdict unchanged | same topology class | scores equal |
|---|---|---|---|---|
| `translate` | 109 | 109/109 (97–100 %) | 109/109 (97–100 %) | 109/109 (97–100 %) |
| `mirror_x` | 424 | 423/424 (98.7–100.0 %) | 424/424 (99.1–100.0 %) | 424/424 (99.1–100.0 %) |
| `mirror_y` | 424 | 423/424 (98.7–100.0 %) | 424/424 (99.1–100.0 %) | 424/424 (99.1–100.0 %) |
| `rotate` | 109 | 109/109 (97–100 %) | 109/109 (97–100 %) | 109/109 (97–100 %) |
| `shuffle` | 424 | 423/424 (98.7–100.0 %) | 424/424 (99.1–100.0 %) | 424/424 (99.1–100.0 %) |
| `swap_identical` | 359 | 271/359 (70.8–79.7 %) | 359/359 (98.9–100.0 %) | 272/359 (71.1–79.9 %) |

## 3. E1d: pre-verifier against the kernel

```
.venv/bin/python bench/e1d_from_csv.py bench/paper bench/paper/e1d_confusion.csv
```

The pre-verifier judges integer boxes without the kernel. The table compares its verdict with the kernel
verifier's on every E2 option and every E1 and E1b placement.

| source | group | placements | both accept | both reject | pre-verifier accepts, kernel rejects | pre-verifier rejects, kernel accepts |
|---|---|---|---|---|---|---|
| options_e2 | beam | 560 | 502 | 57 | 1 | 0 |
| options_e2 | cpsat | 499 | 498 | 0 | 1 | 0 |
| options_e2 | dual | 57 | 57 | 0 | 0 | 0 |
| options_e2 | treemap | 40 | 0 | 40 | 0 | 0 |
| e1_faults_v2 | door_slide | 311 | 0 | 311 | 0 | 0 |
| e1_faults_v2 | gap_incidental | 321 | 321 | 0 | 0 | 0 |
| e1_faults_v2 | gap_required | 408 | 0 | 408 | 0 | 0 |
| e1_faults_v2 | grow_out_of_band | 424 | 0 | 424 | 0 | 0 |
| e1_faults_v2 | none | 424 | 424 | 0 | 0 | 0 |
| e1_faults_v2 | out_of_envelope | 315 | 0 | 315 | 0 | 0 |
| e1_faults_v2 | overlap_50mm | 424 | 0 | 424 | 0 | 0 |
| e1_faults_v2 | shaft_half_height | 211 | 0 | 211 | 0 | 0 |
| e1_faults_v2 | shrink_room | 424 | 0 | 424 | 0 | 0 |
| e1b_metamorphic_v2 | mirror_x | 424 | 424 | 0 | 0 | 0 |
| e1b_metamorphic_v2 | mirror_y | 424 | 424 | 0 | 0 | 0 |
| e1b_metamorphic_v2 | rotate | 109 | 109 | 0 | 0 | 0 |
| e1b_metamorphic_v2 | shuffle | 424 | 424 | 0 | 0 | 0 |
| e1b_metamorphic_v2 | swap_identical | 329 | 329 | 0 | 0 | 0 |
| e1b_metamorphic_v2 | translate | 109 | 109 | 0 | 0 | 0 |
| all | all | 6237 | 3621 | 2614 | 2 | 0 |

**Reading.** The pre-verifier never rejects what the kernel accepts, so it hides nothing from the architect.
The two disagreements on E2 options go the other way and cost one wasted build each:

- beam, `school_three_levels`, seed 4, option 4: the kernel build itself failed (every check fails,
  starting with `built`). This is the intermittent kernel fault, not a pre-verifier miss.
- cpsat, `small_hospital`, seed 2, option 1: the kernel fails `doors` alone. Not yet traced; it may be the
  same fault reaching an aperture (NOTES §12) or a real difference in the door rule. See §11.

## 4. E2: main comparison (Tables 6.2 and 6.3)

```
.venv/bin/python bench.py --fixtures all --seeds 0-4 --out bench/paper/scoreboard_e2.csv \
    --per-option bench/paper/options_e2.csv --save-placements bench/paper/placements
```

Commit `33f3856` (`paper-v1` plus the machine record). 196 rows, 5,611 s. Scores are means over the verified
options of a call, so a call with none verified shows 0.

**Table 6.2, core fixtures**, mean ± SD over five seeds:

| fixture | generator | verified / options | adjacency | deviation | topology classes | t_gen (s) | t_realise (s) |
|---|---|---|---|---|---|---|---|
| `three_rooms` | treemap | 0.0 ± 0.0 / 1.0 ± 0.0 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.0 ± 0.0 | 0.00 ± 0.00 | 0.12 ± 0.02 |
| `three_rooms` | beam | 8.0 ± 0.0 / 8.0 ± 0.0 | 1.000 ± 0.000 | 0.000 ± 0.000 | 3.0 ± 0.0 | 0.05 ± 0.04 | 0.85 ± 0.02 |
| `three_rooms` | cpsat | 8.0 ± 0.0 / 8.0 ± 0.0 | 1.000 ± 0.000 | 0.000 ± 0.000 | 3.6 ± 0.5 | 0.16 ± 0.02 | 0.61 ± 0.02 |
| `three_rooms` | dual | 1.0 ± 0.0 / 1.0 ± 0.0 | 1.000 ± 0.000 | 0.031 ± 0.000 | 1.0 ± 0.0 | 19.48 ± 1.18 | 0.11 ± 0.05 |
| `eight_rooms_corridor` | treemap | 0.0 ± 0.0 / 1.0 ± 0.0 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.0 ± 0.0 | 0.00 ± 0.00 | 0.38 ± 0.00 |
| `eight_rooms_corridor` | beam | 8.0 ± 0.0 / 8.0 ± 0.0 | 1.000 ± 0.000 | 0.001 ± 0.001 | 4.0 ± 0.7 | 0.35 ± 0.03 | 3.39 ± 0.03 |
| `eight_rooms_corridor` | cpsat | 8.0 ± 0.0 / 8.0 ± 0.0 | 1.000 ± 0.000 | 0.000 ± 0.000 | 5.0 ± 0.7 | 13.82 ± 2.73 | 3.42 ± 0.15 |
| `eight_rooms_corridor` | dual | 7.4 ± 0.5 / 7.4 ± 0.5 | 1.000 ± 0.000 | 0.013 ± 0.003 | 7.4 ± 0.5 | 19.84 ± 2.95 | 2.39 ± 0.82 |
| `two_levels_stair` | treemap | declines |  |  |  |  |  |
| `two_levels_stair` | beam | 8.0 ± 0.0 / 8.0 ± 0.0 | 1.000 ± 0.000 | 0.000 ± 0.000 | 7.4 ± 0.9 | 0.72 ± 0.07 | 6.40 ± 0.27 |
| `two_levels_stair` | cpsat | 8.0 ± 0.0 / 8.0 ± 0.0 | 1.000 ± 0.000 | 0.000 ± 0.000 | 7.8 ± 0.4 | 11.52 ± 0.93 | 4.50 ± 0.09 |
| `two_levels_stair` | dual | declines |  |  |  |  |  |

**Table 6.3, all fixtures by generator.** Each cell is verified/options summed over five seeds · mean
topology classes per call · mean generation time.

| fixture | spaces | levels | treemap | beam | cpsat | dual |
|---|---|---|---|---|---|---|
| `three_rooms` | 3 | 1 | 0/5 · 0.0 · 0.0 s | 40/40 · 3.0 · 0.1 s | 40/40 · 3.6 · 0.2 s | 5/5 · 1.0 · 19.5 s |
| `house_ground` | 7 | 1 | 0/5 · 0.0 · 0.0 s | 31/40 · 4.0 · 0.2 s | 40/40 · 2.8 · 2.5 s | declines: rooms cannot tile within tolerance (3); no arrangement could be sized (2) |
| `eight_rooms_corridor` | 9 | 1 | 0/5 · 0.0 · 0.0 s | 40/40 · 4.0 · 0.3 s | 40/40 · 5.0 · 13.8 s | 37/37 · 7.4 · 19.8 s |
| `gallery_rich` | 9 | 1 | 0/5 · 0.0 · 0.0 s | 33/40 · 3.6 · 0.4 s | 35/35 · 3.2 · 21.3 s | declines: rooms cannot tile within tolerance |
| `clinic` | 11 | 1 | 0/5 · 0.0 · 0.0 s | 40/40 · 2.8 · 0.5 s | 35/35 · 7.0 · 21.3 s | 1/1 · 1.0 · 4.8 s (1 of 5 seeds); declines: rooms cannot tile within tolerance |
| `two_levels_stair` | 12 | 2 | declines: single-level only | 40/40 · 7.4 · 0.7 s | 40/40 · 7.8 · 11.5 s | declines: single-level only |
| `school_l_corridor` | 14 | 1 | 0/5 · 0.0 · 0.0 s | 6/40 · 1.0 · 2.1 s | 30/30 · 6.0 · 19.1 s | declines: a wished contact encloses a room |
| `school_wing` | 14 | 2 | declines: single-level only | 40/40 · 7.2 · 1.1 s | 40/40 · 8.0 · 15.6 s | declines: single-level only |
| `apartments_four_levels` | 14 | 4 | declines: single-level only | 33/40 · 6.6 · 1.9 s | 40/40 · 2.0 · 5.2 s | declines: single-level only |
| `hotel_floor` | 15 | 1 | 0/5 · 0.0 · 0.0 s | 40/40 · 2.2 · 0.9 s | 35/35 · 7.0 · 21.5 s | 14/14 · 2.8 · 20.7 s |
| `three_levels_core` | 15 | 3 | declines: single-level only | 40/40 · 8.0 · 1.6 s | 40/40 · 7.8 · 12.7 s | declines: single-level only |
| `office_30` | 30 | 1 | 0/5 · 0.0 · 0.0 s | 40/40 · 2.2 · 3.6 s | 25/25 · 5.0 · 17.3 s | declines: rooms cannot tile within tolerance |
| `small_hospital` | 51 | 2 | declines: single-level only | 40/40 · 7.0 · 6.0 s | 29/30 · 5.8 · 19.1 s | declines: single-level only |
| `school_three_levels` | 64 | 3 | declines: single-level only | 39/40 · 7.8 · 24.0 s | 29/29 · 5.8 · 20.6 s | declines: single-level only |

**Beam against CP-SAT**, paired on the 70 (fixture, seed) cells both ran:

| measure | paired cells | beam higher | cpsat higher | equal | Wilcoxon p |
|---|---|---|---|---|---|
| verified share | 70 | 1 | 11 | 58 | 0.004 |
| adjacency | 70 | 0 | 5 | 65 | 0.025 |
| deviation | 70 | 28 | 10 | 32 | 0.002 |
| topology classes | 70 | 21 | 34 | 15 | 0.080 |
| t_gen (s) | 70 | 5 | 65 | 0 | < 0.001 |

**Reading.**

- **The treemap never meets a brief.** It returns one tiling per call and it fails `bands` or
  `required_contacts` every time. Under the pilot's seven checks it passed; this is the M2 gate line that
  now fails and is left failing (`docs/PLAN.md` §5, 2026-11-03).
- **CP-SAT verifies what it returns** (498 of 499 options) but returns fewer than K on the larger briefs
  within its 20 s. The beam always returns eight and loses some to verification: 58 of 560, of which 34 on
  `school_l_corridor`, the chained-corridor brief it is known to manage on few seeds.
- **The beam is faster on every fixture but the largest**, by one to two orders of magnitude on small
  briefs, because CP-SAT spends its budget looking for more options.
- **`dual` runs on four of the eight single-level fixtures.** It declines the rest with a stated reason:
  the rooms cannot tile a rectangle within tolerance, or a wished contact encloses a room. Where it runs, it
  gives the most topology classes per option.

## 5. E3: scaling

Same run as E2. Mean ± SD over five seeds, fixtures in order of size.

| fixture | spaces | beam t_gen (s) | beam t_realise (s) | cpsat t_gen (s) | cpsat t_realise (s) |
|---|---|---|---|---|---|
| `three_rooms` | 3 | 0.05 ± 0.04 | 0.85 ± 0.02 | 0.16 ± 0.02 | 0.61 ± 0.02 |
| `house_ground` | 7 | 0.22 ± 0.02 | 3.12 ± 0.05 | 2.47 ± 0.15 | 3.21 ± 0.06 |
| `eight_rooms_corridor` | 9 | 0.35 ± 0.03 | 3.39 ± 0.03 | 13.82 ± 2.73 | 3.42 ± 0.15 |
| `gallery_rich` | 9 | 0.42 ± 0.02 | 4.65 ± 0.12 | 21.26 ± 0.02 | 3.99 ± 0.07 |
| `clinic` | 11 | 0.52 ± 0.03 | 5.76 ± 0.15 | 21.33 ± 0.02 | 5.00 ± 0.16 |
| `two_levels_stair` | 12 | 0.72 ± 0.07 | 6.40 ± 0.27 | 11.52 ± 0.93 | 4.50 ± 0.09 |
| `school_l_corridor` | 14 | 2.05 ± 0.14 | 7.49 ± 0.13 | 19.07 ± 0.03 | 5.93 ± 0.30 |
| `school_wing` | 14 | 1.07 ± 0.09 | 8.05 ± 0.09 | 15.61 ± 1.77 | 5.48 ± 0.29 |
| `apartments_four_levels` | 14 | 1.85 ± 0.30 | 8.26 ± 0.18 | 5.23 ± 2.20 | 8.21 ± 0.26 |
| `hotel_floor` | 15 | 0.94 ± 0.05 | 8.41 ± 0.13 | 21.55 ± 0.02 | 7.19 ± 0.20 |
| `three_levels_core` | 15 | 1.57 ± 0.06 | 9.49 ± 0.47 | 12.72 ± 2.60 | 6.61 ± 0.38 |
| `office_30` | 30 | 3.63 ± 0.50 | 20.67 ± 0.33 | 17.34 ± 5.31 | 11.43 ± 4.89 |
| `small_hospital` | 51 | 5.99 ± 0.26 | 51.31 ± 11.56 | 19.10 ± 0.04 | 22.42 ± 4.65 |
| `school_three_levels` | 64 | 24.03 ± 1.49 | 82.67 ± 19.46 | 20.61 ± 1.05 | 41.50 ± 8.09 |

![Generation and realisation time against the number of spaces](figures/e3_scaling.png)

**Reading.** Realisation and verification grow smoothly with the number of spaces and dominate the beam's
total from about ten spaces up: 83 s against 24 s of generation on the 64-space school. CP-SAT's generation
time is its budget, flat near 20 s from nine spaces up. CP-SAT's realisation time is lower on the large
briefs only because it returns fewer options to build. The treemap's generation time rounds to zero and is
drawn at 1 ms.

## 6. E10: do the scores tell options apart? (Table 6.4)

```
.venv/bin/python bench/e10_from_csv.py bench/paper/options_e2.csv bench/paper/e10_discrimination.csv
.venv/bin/python bench/e10c_pairs.py bench/paper/placements bench/paper/e10c_pairs.csv
```

Both read the E2 run; nothing is regenerated. A score vector is the eight scores rounded to four decimals.

**Table 6.4a, score spread.** Per score: calls in which it varies across the options / calls with more than
one verified option, then the largest spread seen in any call.

| generator | distinct score vectors / verified options | calls where all options share one vector | adjacency | deviation | compactness | circulation | stacking | vertical | envelope_fit | daylight |
|---|---|---|---|---|---|---|---|---|---|---|
| beam | 267/502 | 4 of 64 | 0/64, 0.00 | 18/64, 0.03 | 60/64, 0.22 | 18/64, 0.08 | 27/64, 0.26 | 0/64, 0.00 | 11/64, 0.04 | 0/64, 0.00 |
| cpsat | 347/498 | 1 of 69 | 0/69, 0.00 | 19/69, 0.07 | 68/69, 0.17 | 19/69, 0.35 | 15/69, 0.13 | 0/69, 0.00 | 15/69, 0.01 | 4/69, 0.17 |
| dual | 56/57 | 0 of 10 | 0/10, 0.00 | 10/10, 0.03 | 10/10, 0.04 | 10/10, 0.05 | 0/10, 0.00 | 0/10, 0.00 | 5/10, 0.02 | 0/10, 0.00 |

![Spread of each score across the options of one call](figures/e10_spread.png)

**Table 6.4b, contacts per verified option:** touching pairs · required pairs · room-to-room pairs nobody
asked for.

| fixture | spaces | beam | cpsat | dual |
|---|---|---|---|---|
| `three_rooms` | 3 | 2 · 2 · 0.2 | 3 · 2 · 0.7 | 3 · 2 · 1.0 |
| `house_ground` | 7 | 10 · 9 · 1.4 | 11 · 9 · 2.0 |  |
| `eight_rooms_corridor` | 9 | 14 · 9 · 5.0 | 14 · 9 · 5.0 | 14 · 9 · 5.0 |
| `gallery_rich` | 9 | 15 · 13 · 2.0 | 14 · 13 · 1.2 |  |
| `clinic` | 11 | 19 · 13 · 5.6 | 18 · 13 · 5.4 | 18 · 13 · 5.0 |
| `two_levels_stair` | 12 | 24 · 12 · 7.3 | 23 · 12 · 6.8 |  |
| `school_l_corridor` | 14 | 25 · 2 · 9.3 | 24 · 2 · 8.4 |  |
| `school_wing` | 14 | 32 · 14 · 12.3 | 28 · 14 · 9.2 |  |
| `apartments_four_levels` | 14 | 32 · 16 · 7.8 | 35 · 16 · 10.0 |  |
| `hotel_floor` | 15 | 26 · 15 · 8.9 | 24 · 15 · 7.2 | 26 · 15 · 8.6 |
| `three_levels_core` | 15 | 33 · 17 · 8.9 | 32 · 17 · 10.5 |  |
| `office_30` | 30 | 57 · 29 · 26.0 | 48 · 29 · 17.8 |  |
| `small_hospital` | 51 | 141 · 57 · 78.3 | 138 · 57 · 73.3 |  |
| `school_three_levels` | 64 | 190 · 75 · 108.0 | 190 · 75 · 104.9 |  |

**Table 6.4c, contacts nobody asked for, by programme pair,** summed over all verified options of the run
(required contacts of the same pair in brackets):

| programme pair | beam | cpsat | dual |
|---|---|---|---|
| room-room | 10739 (1056) | 8107 (967) | 315 (50) |
| room-stair | 411 (0) | 533 (0) | 22 (0) |
| elevator-room | 457 (40) | 375 (35) | 12 (14) |
| corridor-room | 209 (8256) | 540 (6766) | 0 (474) |
| corridor-corridor | 349 (46) | 367 (55) | 0 (0) |
| elevator-stair | 208 (0) | 85 (0) | 0 (0) |
| stair-stair | 79 (0) | 37 (0) | 0 (0) |
| corridor-elevator | 0 (649) | 0 (620) | 0 (14) |
| corridor-stair | 0 (846) | 0 (765) | 0 (14) |
| verified options | 502 | 498 | 57 |

**Reading.**

- **Adjacency and vertical never vary, and daylight in 4 calls of 143.** A verified option meets every
  required contact, so adjacency is 1 by construction now that the check exists. These three scores carry no
  ranking information among verified options.
- **Compactness is the score that separates options**; deviation, circulation and stacking vary in about a
  quarter of calls. About half the beam's options and two thirds of CP-SAT's have a score vector of their
  own.
- **Unasked contacts grow with the brief and are almost all room-to-room.** They outnumber required
  room-to-room contacts by about ten to one for the beam and eight to one for CP-SAT. Nothing scores or
  checks them. This is the measured case for affinities (`apart`, `near`) as a brief-level wish.

## 7. E5: solver cross-check

```
.venv/bin/python bench/e5_z3.py > bench/paper/e5_z3.txt
```

```
E5: Z3 cross-check of the relational model (PLAN M13, design note C)
Counts are the ones gate_m13 asserts; this only prints them.

three_rooms: 3 spaces, 2 required contacts, 16 side assignments possible (4^2)
  Z3     found   16 feasible assignments in    0.0s
  CP-SAT found   16 feasible assignments in    0.3s (last status INFEASIBLE, so it ran to exhaustion)
  identical sets: True   CP-SAT subset of Z3: True

four_rooms: 4 spaces, 3 required contacts, 64 side assignments possible (4^3)
  Z3     found   64 feasible assignments in    0.0s
  CP-SAT found   64 feasible assignments in    3.2s (last status INFEASIBLE, so it ran to exhaustion)
  identical sets: True   CP-SAT subset of Z3: True

contradictory brief (6 spaces, 5 contacts onto one 1x1 m room)
  Z3     unsat
  CP-SAT INFEASIBLE
  both reject: True
```

**Reading.** Z3 and CP-SAT find the same sets of wall assignments, exhaustively, on both briefs, and both
prove the contradictory brief impossible. The relational model neither loses nor invents arrangements.

## 8. E8: ablations (Table 6.5)

```
.venv/bin/python bench.py --fixtures all --generators beam cpsat --seeds 0-4 \
    --params-json '{"beam": {"redim": false}, "cpsat": {"warm_start": false}}' \
    --out bench/paper/e8_ablation.csv --per-option bench/paper/e8_options.csv
```

Commit `2922bcc`. 2,448 s. Compared with the E2 run, cell by cell.

**Beam without its final re-dimensioning** (`redim=False`):

| fixture | spaces | seeds | verified E2 | verified ablated | deviation E2 | deviation ablated | classes E2 | classes ablated | t_gen E2 (s) | t_gen ablated (s) |
|---|---|---|---|---|---|---|---|---|---|---|
| `three_rooms` | 3 | 5 | 40/40 | 40/40 | 0.0000 | 0.0000 | 3.0 | 2.8 | 0.05 | 0.01 |
| `house_ground` | 7 | 5 | 31/40 | 31/40 | 0.0089 | 0.0089 | 4.0 | 4.8 | 0.22 | 0.13 |
| `eight_rooms_corridor` | 9 | 5 | 40/40 | 40/40 | 0.0014 | 0.0031 | 4.0 | 4.6 | 0.35 | 0.20 |
| `gallery_rich` | 9 | 5 | 33/40 | 31/40 | 0.0007 | 0.0022 | 3.6 | 2.8 | 0.42 | 0.25 |
| `clinic` | 11 | 5 | 40/40 | 40/40 | 0.0017 | 0.0017 | 2.8 | 3.4 | 0.52 | 0.32 |
| `two_levels_stair` | 12 | 5 | 40/40 | 40/40 | 0.0000 | 0.0000 | 7.4 | 7.4 | 0.72 | 0.52 |
| `school_l_corridor` | 14 | 5 | 6/40 | 6/40 | 0.0017 | 0.0017 | 1.0 | 1.0 | 2.05 | 1.37 |
| `school_wing` | 14 | 5 | 40/40 | 40/40 | 0.0000 | 0.0000 | 7.2 | 7.2 | 1.07 | 0.75 |
| `apartments_four_levels` | 14 | 5 | 33/40 | 33/40 | 0.0143 | 0.0143 | 6.6 | 6.6 | 1.85 | 1.30 |
| `hotel_floor` | 15 | 5 | 40/40 | 40/40 | 0.0006 | 0.0006 | 2.2 | 2.4 | 0.94 | 0.63 |
| `three_levels_core` | 15 | 5 | 40/40 | 40/40 | 0.0000 | 0.0000 | 8.0 | 8.0 | 1.57 | 1.13 |
| `office_30` | 30 | 5 | 40/40 | 40/40 | 0.0186 | 0.0190 | 2.2 | 2.4 | 3.63 | 2.40 |
| `small_hospital` | 51 | 5 | 40/40 | 40/40 | 0.0047 | 0.0047 | 7.0 | 7.0 | 5.99 | 4.25 |
| `school_three_levels` | 64 | 5 | 39/40 | 40/40 | 0.0054 | 0.0054 | 7.8 | 8.0 | 24.03 | 16.78 |

**CP-SAT without the beam warm start** (`warm_start=False`):

| fixture | spaces | seeds | verified E2 | verified ablated | deviation E2 | deviation ablated | classes E2 | classes ablated | t_gen E2 (s) | t_gen ablated (s) |
|---|---|---|---|---|---|---|---|---|---|---|
| `three_rooms` | 3 | 5 | 40/40 | 40/40 | 0.0000 | 0.0000 | 3.6 | 3.8 | 0.16 | 0.22 |
| `house_ground` | 7 | 5 | 40/40 | 40/40 | 0.0000 | 0.0000 | 2.8 | 3.0 | 2.47 | 3.75 |
| `eight_rooms_corridor` | 9 | 5 | 40/40 | 40/40 | 0.0000 | 0.0000 | 5.0 | 5.0 | 13.82 | 13.86 |
| `gallery_rich` | 9 | 5 | 35/35 | 35/35 | 0.0003 | 0.0003 | 3.2 | 4.0 | 21.26 | 21.13 |
| `clinic` | 11 | 5 | 35/35 | 35/35 | 0.0000 | 0.0000 | 7.0 | 7.0 | 21.33 | 21.12 |
| `two_levels_stair` | 12 | 5 | 40/40 | 40/40 | 0.0000 | 0.0000 | 7.8 | 8.0 | 11.52 | 17.64 |
| `school_l_corridor` | 14 | 5 | 30/30 | 35/35 | 0.0005 | 0.0025 | 6.0 | 7.0 | 19.07 | 21.12 |
| `school_wing` | 14 | 5 | 40/40 | 36/36 | 0.0000 | 0.0000 | 8.0 | 7.2 | 15.61 | 20.50 |
| `apartments_four_levels` | 14 | 5 | 40/40 | 40/40 | 0.0000 | 0.0000 | 2.0 | 2.0 | 5.23 | 4.86 |
| `hotel_floor` | 15 | 5 | 35/35 | 35/35 | 0.0000 | 0.0000 | 7.0 | 7.0 | 21.55 | 21.10 |
| `three_levels_core` | 15 | 5 | 40/40 | 39/40 | 0.0000 | 0.0000 | 7.8 | 7.8 | 12.72 | 19.93 |
| `office_30` | 30 | 5 | 25/25 | 35/35 | 0.0381 | 0.0432 | 5.0 | 7.0 | 17.34 | 21.14 |
| `small_hospital` | 51 | 5 | 29/30 | 1/1 | 0.0021 | 0.0108 | 5.8 | 0.2 | 19.10 | 17.23 |
| `school_three_levels` | 64 | 5 | 29/29 | 2/2 | 0.0022 | 0.0194 | 5.8 | 0.4 | 20.61 | 14.54 |

**Paired tests** over (fixture, seed) cells:

| ablation | measure | paired cells | higher when ablated | lower when ablated | Wilcoxon p |
|---|---|---|---|---|---|
| beam, `redim=False` | verified | 70 | 1 | 1 | 0.655 |
| beam, `redim=False` | adjacency | 70 | 0 | 0 | – |
| beam, `redim=False` | deviation | 70 | 11 | 0 | 0.003 |
| beam, `redim=False` | distinct_topologies | 70 | 11 | 5 | 0.087 |
| beam, `redim=False` | t_gen | 70 | 0 | 70 | < 0.001 |
| cpsat, `warm_start=False` | verified | 70 | 10 | 15 | 0.046 |
| cpsat, `warm_start=False` | adjacency | 70 | 0 | 7 | 0.008 |
| cpsat, `warm_start=False` | deviation | 70 | 11 | 9 | 0.240 |
| cpsat, `warm_start=False` | distinct_topologies | 70 | 19 | 16 | 0.283 |
| cpsat, `warm_start=False` | t_gen | 70 | 44 | 26 | < 0.001 |

**Reading.**

- **Re-dimensioning barely changes what verifies** (two cells of 70, in opposite directions). It takes about a third of the beam's generation time
  and lowers deviation in 11 cells, all single-level. Multi-level briefs are unchanged by construction: the
  multi-level beam never re-dimensions (`docs/PLAN.md`, commit `f127838`).
- **The warm start decides the large briefs.** Without it CP-SAT's verified options over five seeds fall
  from 29 to 1 on `small_hospital` and from 29 to 2 on `school_three_levels`: in 20 s it rarely finds a first
  solution on its own.
- **On two mid-size briefs the warm start costs options.** `office_30` and `school_l_corridor` return more
  verified options without it (35 against 25, and 35 against 30). A plausible cause is time spent on the
  beam run and on the hint; it was not investigated.
- The pooled test on verified options (p near 0.05) mixes those two opposite effects and should not be quoted
  alone; the per-fixture table is the result.

## 9. E9: planted briefs

```
.venv/bin/python bench/planted_run.py --out bench/paper/e9_planted.csv --save bench/paper/planted
```

Engine as `paper-v1`. 12,569 s for the main run. Each brief is written back from a placement built first, so
it has at least one exact solution. One factor varies at a time around a base, 20 seeds per point.
1800 rows; 0 crashed after the retry of 13 cells (§11).

- **Family A:** a rectangle cut into n rooms, no circulation. Base n = 9, t = 0.10, ρ = 0.5, slicing.
- **Family B:** rooms on a 1.8 m corridor. Base 16 rooms, t = 0.10, frontage 0.75, straight, double-loaded,
  one level.

Each cell: briefs solved / briefs that ran, with the Wilson interval; then `class`, the number of briefs
where the planted topology class is among the verified options; then how often `dual` declined.

**Family A**

| sweep point | treemap | beam | cpsat | dual |
|---|---|---|---|---|
| n=4 | 1/20 (1–24 %) | 20/20 (84–100 %); class 11 | 20/20 (84–100 %); class 3 | 20/20 (84–100 %); class 15 |
| n=6 | 0/20 (0–16 %) | 20/20 (84–100 %); class 0 | 20/20 (84–100 %); class 2 | 20/20 (84–100 %); class 0 |
| base | 0/20 (0–16 %) | 19/20 (76–99 %); class 0 | 20/20 (84–100 %); class 0 | 20/20 (84–100 %); class 0 |
| n=12 | 0/20 (0–16 %) | 14/20 (48–85 %); class 0 | 20/20 (84–100 %); class 0 | 2/2 (34–100 %); class 0; declines 18 |
| n=16 | 0/20 (0–16 %) | 9/20 (26–66 %); class 0 | 20/20 (84–100 %); class 0 | 1/1 (21–100 %); class 0; declines 19 |
| t=0.02 | 0/20 (0–16 %) | 19/20 (76–99 %); class 0 | 20/20 (84–100 %); class 0 | 1/1 (21–100 %); class 0; declines 19 |
| t=0.05 | 0/20 (0–16 %) | 19/20 (76–99 %); class 0 | 20/20 (84–100 %); class 0 | 6/6 (61–100 %); class 0; declines 14 |
| t=0.2 | 0/20 (0–16 %) | 19/20 (76–99 %); class 0 | 20/20 (84–100 %); class 0 | 20/20 (84–100 %); class 0 |
| rho=0.25 | 0/20 (0–16 %) | 19/20 (76–99 %); class 0 | 20/20 (84–100 %); class 1 | 20/20 (84–100 %); class 0 |
| rho=0.75 | 0/20 (0–16 %) | 10/20 (30–70 %); class 0 | 20/20 (84–100 %); class 3 | 7/7 (65–100 %); class 0; declines 13 |
| rho=1.0 | 0/20 (0–16 %) | 6/20 (15–52 %); class 2 | 20/20 (84–100 %); class 15 | 12/12 (76–100 %); class 3; declines 8 |
| slicing=False | 0/20 (0–16 %) | 19/20 (76–99 %); class 0 | 20/20 (84–100 %); class 0 | 14/14 (78–100 %); class 0; declines 6 |

**Family B**

| sweep point | beam | cpsat | dual |
|---|---|---|---|
| rooms=8 | 3/20 (5–36 %); class 0 | 20/20 (84–100 %); class 0 | declines |
| base | 6/20 (15–52 %); class 0 | 20/20 (84–100 %); class 0 | declines |
| rooms=24 | 3/20 (5–36 %); class 0 | 20/20 (84–100 %); class 0 | declines |
| rooms=32 | 5/20 (11–47 %); class 0 | 20/20 (84–100 %); class 0 | declines |
| rooms=48 | 7/20 (18–57 %); class 0 | 20/20 (84–100 %); class 0 | declines |
| rooms=64 | 6/20 (15–52 %); class 0 | 20/20 (84–100 %); class 0 | declines |
| t=0.05 | 7/20 (18–57 %); class 0 | 20/20 (84–100 %); class 0 | declines |
| t=0.2 | 6/20 (15–52 %); class 0 | 20/20 (84–100 %); class 0 | declines |
| frontage=0.6 | 8/20 (22–61 %); class 0 | 20/20 (84–100 %); class 0 | declines |
| frontage=0.85 | 4/20 (8–42 %); class 0 | 20/20 (84–100 %); class 0 | declines |
| frontage=0.95 | 6/20 (15–52 %); class 0 | 20/20 (84–100 %); class 0 | declines |
| shape=L | 8/20 (22–61 %); class 0 | 20/20 (84–100 %); class 0 | declines |
| levels=2 | 0/20 (0–16 %); class 0 | 20/20 (84–100 %); class 0 | declines |
| levels=3 | 0/20 (0–16 %); class 0 | 20/20 (84–100 %); class 0 | declines |

![Share of planted briefs solved against each swept parameter](figures/e9_success.png)

**Generation time against size**, mean ± SD over the seeds that ran:

| family | point | beam t_gen (s) | cpsat t_gen (s) | dual t_gen (s) |
|---|---|---|---|---|
| A | n=4 | 0.1 ± 0.0 | 0.5 ± 0.1 | 19.3 ± 5.3 |
| A | n=6 | 0.1 ± 0.0 | 19.7 ± 2.7 | 20.0 ± 2.6 |
| A | n=12 | 0.4 ± 0.1 | 21.3 ± 0.1 | 20.0 ± 0.0 |
| A | n=16 | 0.9 ± 0.3 | 21.5 ± 0.2 | 20.0 ± 0.0 |
| B | rooms=8 | 1.2 ± 0.6 | 1.5 ± 0.6 | – |
| B | rooms=24 | 17.7 ± 2.9 | 11.6 ± 1.5 | – |
| B | rooms=32 | 32.3 ± 1.5 | 19.1 ± 0.7 | – |
| B | rooms=48 | 114.5 ± 12.1 | 61.5 ± 4.8 | – |
| B | rooms=64 | 283.8 ± 18.2 | 144.0 ± 8.2 | – |

**Reading.**

- **CP-SAT solves every planted brief**, 520 of 520, in both families, across every swept parameter, including
  64 rooms and three levels. That is the completeness result: where a solution is known to exist, the exact
  engine finds one within the bench budget.
- **The beam degrades with size and with constraint density in family A**: from 20 of 20 at n = 4 to 9 of 20
  at n = 16, and from 19 of 20 at ρ = 0.25 to 6 of 20 at ρ = 1.0. Tolerance and slicing make no difference.
- **The beam solves about three in ten of one-level family B and none of the multi-level points.** No swept
  parameter explains it, including the frontage ratio the sweep was designed to cross. This is weaker than the beam's
  record on the hand-written fixtures and is the result most worth a follow-up (§11).
- **`dual` solves every brief it accepts and declines many**: most of family A at n ≥ 12, at tight tolerance
  and at high ρ (the rooms cannot tile a rectangle within tolerance), and all of family B (its stated
  reason: the wished contacts leave a room enclosed).
- **The treemap solves 1 of 240.**
- **Beyond the budget:** the beam's generation time on family B grows to about 280 s at 64 rooms, and
  CP-SAT's to about 140 s, well past its nominal 20 s. CP-SAT's time includes its beam warm start, which is
  the likely cause; it was not investigated.

**The planted class is rarely recovered, and that is a property of the measure.** The topology class labels
each room by its size and compares the whole shared-wall graph. Planted rooms all differ in size, so
recovery means the very room in the very place, with the same incidental contacts. Where the brief pins the
plan down it happens (n = 4; ρ = 1.0 for CP-SAT), and elsewhere almost never. Family B has no required
room-to-room contacts, so the order of rooms along the corridor is free and the planted order is one of
thousands. A looser class that ignores room size was tried on 32 small briefs and recovered 2, so it was not
adopted. `solved` is E9's result. Recall of topology classes needs the exhaustive ground truth of the
optional E9b.

## 10. E14: reproducibility

```
.venv/bin/python bench.py --fixtures all --seeds 0-1 --deterministic ...   # twice: det_a, det_b
.venv/bin/python bench.py --fixtures all --seeds 0 ...                     # three times: def_a, def_b, def_c
.venv/bin/python bench/e14_repro.py bench/paper/e14 bench/paper/e14_repro.csv
```

Commit `2922bcc`. 6,597 s in all, one machine. A cell is one (generator, fixture, seed); it is identical when
every run returns the same placements in the same order. The overlap is the Jaccard index of two runs'
option sets, smallest pair, averaged over cells.

| mode | generator | cells with identical options | mean smallest overlap of option sets |
|---|---|---|---|
| deterministic | treemap | 16/16 (81–100 %) | 1.00 |
| deterministic | beam | 28/28 (88–100 %) | 1.00 |
| deterministic | cpsat | 25/25 (87–100 %) | 1.00 |
| deterministic | dual | 3/7 (16–75 %) | 0.55 |
| default | treemap | 8/8 (68–100 %) | 1.00 |
| default | beam | 14/14 (78–100 %) | 1.00 |
| default | cpsat | 0/14 (0–22 %) | 0.08 |
| default | dual | 2/4 (15–85 %) | 0.58 |

**Reading.**

- **The beam and the treemap are deterministic** in either mode.
- **CP-SAT in deterministic mode repeats exactly**, in every cell that returned options. Three of its 28
  cells returned none in either run (`office_30` on both seeds, `small_hospital` on seed 0), where default
  mode returned some on every cell of E2: one worker on a deterministic budget is a smaller search than
  eight workers for 20 s. The two deterministic runs took 2,106 s and 2,081 s for two seeds.
- **CP-SAT in default mode never repeats**, and two runs share under a tenth of their options. Results from
  default mode are reproducible as distributions over seeds, not as plans.
- **`dual` does not repeat in either mode** on `eight_rooms_corridor` and `hotel_floor`. `--deterministic`
  reaches the `cpsat` generator only, not the sizing solves inside `dual`.
- Not done: the second machine.

---

## 11. Departures from the brief, gates that changed, and what looked wrong

**Departures**

1. **The freeze.** `paper-v1` is `f6bc234`. E2 ran at `33f3856`, E8 and E14 at `2922bcc`. Between them the
   engine (`spacetope/`, `bench.py`, `bench/planted_run.py`) gained licence header lines and nothing else.
   `bench/validate.py` did change, twice: crash handling on 2026-11-03, and on 2026-11-23 the
   `swap_identical` relation, the `gap_incidental` control and the worker pool. E1 and E1b are the only runs
   that depend on it, and both were rerun on the final version. The honest tag for the validator is
   `paper-v2`; it has not been made, and the validator's final version is not yet committed.
2. **E1 and E1b have two runs.** The first (`e1_faults.csv`, `e1b_metamorphic.csv`) is kept beside the
   corrected one (`*_v2.csv`). The paper should quote the second and describe the first.
3. **E9 planted class** is reported but is not the headline (§9).
4. **Crashed cells were retried.** 13 E9 cells and one E8 cell (`beam`, `school_three_levels`, seed 2) died
   with `TypeError: unhashable type: 'list'`, the intermittent kernel fault of NOTES §12 in which a cell's
   name is read back as a list. They were rerun in a fresh process and appended.
5. **E14 on one machine only.**
6. **Figures** need matplotlib, which is not a spacetope dependency and was not added to `.venv`. They were
   drawn from a separate environment.
7. **Optional experiments** E1c, E9b and E4 were not run.

**Gates that changed**

- **M2, `test_treemap_baseline_verified`, fails and stays failing** (`docs/PLAN.md` §5, 2026-11-03). The
  treemap gets 0 verified options under nine checks. All other gates were green at the freeze
  (`step1_gates_summary.txt`). They have not been rerun since; no engine code has changed.

**What looked wrong, and is still open**

1. **The beam on planted corridor briefs** (§9): about three in ten solved on one level and none on two or
   three, against 8 of 8 on the hand-written hospital and school. Either planted briefs are harder in a way
   the fixtures are not, or `planted.py` writes family B briefs the beam's corridor heuristics do not expect.
2. **`dual` under `--deterministic`** (§10): either the flag should reach it or the paper should say it does
   not.
3. **One `doors` disagreement** between the pre-verifier and the kernel (§3), untraced.
4. **The intermittent kernel fault** reached four places in these runs: a failed build in E2, cell names in
   E1, E8 and E9. Every case passed on retry. The harness works around it with short-lived workers; the
   package-side guard suggested in NOTES §12 is not written.
5. **`ProcessPoolExecutor(max_tasks_per_child=8)` hangs** on Python 3.11.9 once every worker has served its
   tasks: the run stops with work queued and no workers. `bench/validate.py` now starts a fresh pool per
   batch.
6. **CP-SAT exceeds its 20 s budget** on large multi-part briefs (§9), up to about 140 s at 64 rooms.
