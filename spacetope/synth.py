# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Adventurous Systems

"""Synthetic briefs for training and held-out evaluation (M6), in the M7 circulation form.

Deterministic by seed. Each brief has 8-30 spaces after expansion and 1-3 levels. Every level gets a
generated corridor. Multi-level briefs declare one stair, and from 16 spaces one lift, each spanning all
levels. Rooms carry their level as a wish, need a door to their level's corridor, and a few room-room
contacts are added on the same level. `synth_brief` returns the expanded brief (what generators and the
learning code use); `synth_compact` returns what an architect would write.
Held-out briefs use seeds from a range disjoint from training seeds.
"""
from __future__ import annotations

import random

from .brief import Brief
from .circulation import prepare

ROOM_TYPES = [  # (prefix, w, l) in metres
    ("office", 4.0, 3.0), ("office", 3.6, 3.0), ("meeting", 5.0, 4.0), ("kitchen", 3.0, 3.0),
    ("wc", 2.0, 3.0), ("storage", 2.0, 2.0), ("print", 2.0, 2.5), ("studio", 6.0, 4.0),
    ("lab", 5.0, 5.0), ("quiet", 2.5, 2.5),
]
TRAIN_SEEDS = range(0, 10_000)
HELDOUT_SEEDS = range(90_000, 90_020)


def synth_compact(seed: int, n_spaces: int | None = None, levels: int | None = None) -> Brief:
    rng = random.Random(seed)
    levels = levels or rng.choice([1, 1, 2, 2, 3])
    n_spaces = n_spaces or rng.randint(8, 30)
    stairs = [{"name": "stair", "w": 3.0, "l": 5.0}] if levels > 1 else []
    lifts = [{"name": "lift", "w": 2.5, "l": 2.5}] if levels > 1 and n_spaces >= 16 else []
    n_generated = levels + len(stairs) + len(lifts)
    n_rooms = max(levels * 2, n_spaces - n_generated)
    per_level = [n_rooms // levels + (1 if k < n_rooms % levels else 0) for k in range(levels)]
    corridor_l = float(min(30, max(8, 2 * max(per_level))))  # both sides of the corridor serve rooms
    spaces: list[dict] = []
    contacts: list[list[str]] = []
    counters: dict[str, int] = {}
    for k in range(levels):
        level_rooms = []
        for _ in range(per_level[k]):
            prefix, w, l = rng.choice(ROOM_TYPES)
            counters[prefix] = counters.get(prefix, 0) + 1
            name = f"{prefix}_{counters[prefix]}"
            wishes = {"level": k}
            if prefix in ("office", "studio", "meeting") and rng.random() < 0.6:
                wishes["exterior"] = True
            spaces.append({"name": name, "w": w, "l": l, "h": 3.0, "program": "room", "wishes": wishes})
            contacts.append([f"corridor_{k}", name])
            level_rooms.append(name)
        for _ in range(rng.randint(0, max(0, len(level_rooms) // 4))):
            a, b = rng.sample(level_rooms, 2)
            if [a, b] not in contacts and [b, a] not in contacts:
                contacts.append([a, b])
    return Brief.from_dict({
        "name": f"synth_{seed}", "levels": levels, "level_height": 3.0, "spaces": spaces, "contacts": contacts,
        "circulation": {"corridor": {"w": 1.8, "l": corridor_l}, "stairs": stairs, "lifts": lifts},
    })


def synth_brief(seed: int, n_spaces: int | None = None, levels: int | None = None) -> Brief:
    expanded, _ = prepare(synth_compact(seed, n_spaces, levels))
    return expanded


def heldout_briefs() -> list[Brief]:
    return [synth_brief(s) for s in HELDOUT_SEEDS]


def training_briefs(n: int, start: int = 0) -> list[Brief]:
    return [synth_brief(s) for s in TRAIN_SEEDS[start:start + n]]
