# Brief programmes

A fixture is one building. A **programme** is a kind of building: "a secondary school has ten to eighteen
classrooms, one or two science labs each with a prep room, a library and a canteen on the ground floor, two
stairs and a lift". `spacetope.programme.sample(name, seed)` draws one brief from that description, and
`variations(brief, seed)` perturbs a brief that already exists. Both are pure and deterministic in the seed.

Three uses: a benchmark suite per building type instead of a handful of fixtures; robustness sweeps, where a
variation asks "does this generator still work if every room grows twenty percent"; and the training data the
learning track needs, which is briefs by the thousand rather than by the dozen.

Programmes live in `programmes/*.yaml`. Four ship with the project: `office`, `secondary_school`, `clinic`,
`housing`.

## Using them

```bash
spacetope programme --list                                   # what exists
spacetope programme clinic --seeds 0-99 --out out/briefs     # a brief YAML per seed
spacetope programme clinic --seeds 0-9 --out out/briefs --variations
spacetope programme office --seeds 0-499 --dataset out/rows.jsonl   # dataset rows instead
```

In Python:

```python
from spacetope.programme import sample, variations
brief, frontage = sample("clinic", seed=7)      # a Brief, and how hard it will be to build
if frontage.tight:
    ...                                          # its rooms want more corridor than the envelope allows
sweep = variations(brief, seed=7)                # {"scale": Brief, "widen": Brief, ...}
```

## The format

```yaml
name: secondary_school
levels: {min: 2, max: 3}            # or a plain number
level_height: 3.5
envelope: {area_factor: [1.7, 2.3], aspect: [1.8, 3.0]}
circulation:
  corridor: {w: 2.4, l: from_frontage}
  stairs: {count: 2, w: 3, l: 6}
  lifts: {count: 1, w: 2.4, l: 2.4}
  doors: {room: {w: 0.9, h: 2.1}, jamb: 0.1}
rooms:
  - {type: classroom, w: 8, l: 7, count: [10, 18], exterior: 1.0, level: any}
  - {type: science_lab, w: 10, l: 7, count: [1, 2], level: upper,
     attach: {type: prep_room, w: 4, l: 5, door: true}}
  - {type: wc, w: 4, l: 4, count_per_level: 2}
adjacency:
  - {between: [meeting, kitchen], p: 0.5, door: true}
tolerance: {room: 0.10, corridor: {l: [-0.5, 2.0]}}
```

| key | meaning |
|---|---|
| `levels` | a number, or `{min, max}` drawn inclusively |
| `envelope` | omit for no envelope. `area_factor` multiplies the busiest level's floor area, **including the corridor and shafts**; `aspect` is width over length. Either may be a range |
| `circulation.corridor.l` | a length in metres, or `from_frontage` to derive it: half the metres of wall the busiest level's rooms want, narrow side on |
| `circulation.stairs` / `lifts` | `{count, w, l}`, expanded into the list the brief format wants. Dropped on a single-level brief |
| `rooms[].count` | a number or `[lo, hi]`. `count_per_level` repeats it on every level instead |
| `rooms[].level` | `any` (the emptiest level), `ground`, `upper`, a number, or a list to choose from |
| `rooms[].exterior` | the probability this room asks for an outside wall |
| `rooms[].attach` | hang another room off this one, with a door by default. Chains: an `attach` may itself carry an `attach` |
| `adjacency` | optional room-to-room wishes between two types, with probability `p` and an optional `door` |
| `tolerance` | `room` is a symmetric fraction; `corridor.l` is a `[lo, hi]` pair of fractions |
| `corridor_contacts` | default true: every room is given a contact with its level's corridor |

Rooms are named `type_NN`. Every room is assigned a concrete level when it is drawn, because a room can only
be told to open off `corridor_<k>` once its k is known, and **that contact is what makes a brief buildable**:
without it the search has little reason to put a room on a corridor at all, and almost nothing verifies
(measured 2026-10-04, PLAN §5). `any` sends a room to the emptiest level so the floors stay balanced.

## Frontage: how hard will this brief be?

`sample` returns a `Frontage` alongside the brief. It compares the metres of corridor wall the busiest level's
rooms want, narrow side on, with the two sides of the longest corridor the envelope allows. Above 85 percent
the brief is `tight`, which is where the beam was measured to start failing in M15a.

It is a reading, not a refusal: a tight brief may still build, and the exact engine copes better than the beam.
With the shipped programmes it rarely fires, because the corridor length is derived from the same demand. It
earns its keep when an architect writes a fixed envelope that is too small for the rooms inside it.

## Variations

`variations(brief, seed)` returns one perturbed brief per kind. A kind that cannot apply to a brief is left out
rather than returned unchanged.

| kind | what it changes |
|---|---|
| `scale` | every room 20 % larger or smaller |
| `widen` / `narrow` | every room's tolerance to ±20 % or ±2 % |
| `drop` | removes a room and its contacts |
| `duplicate` | copies a room |
| `stretch_envelope` | 25 % wider, 10 % shallower |
| `undoor` | turns one marked door contact into a plain contact |

## Writing one

Start from the programme closest to what you want and change the room list. Two things to watch. Keep
`area_factor` at or above about 1.5, since a floor is rooms plus corridor plus shafts plus the space between
them. And prefer `from_frontage` for the corridor unless you mean a specific length, because a corridor too
short for its rooms is the single most common reason a brief does not build.
