"""A stateless schedule: the wall clock alone decides what is on air, so restarts change nothing."""
from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass
from functools import lru_cache

from .catalog import Entry


@dataclass(frozen=True)
class Slot:
    index: int
    start: int          # unix seconds
    end: int
    entries: tuple[Entry, ...]

    @property
    def id(self) -> str:
        return f's{self.index}'


def blocks(entries: list[Entry]) -> list[list[tuple[Entry, ...]]]:
    """Each block is a run of episodes; each episode is one or more entries that take turns between passes."""
    runs = {}
    for e in entries:
        key = ('series', e.series) if e.series else ('single', e.id)
        runs.setdefault(key, {}).setdefault(e.episode, []).append(e)
    return [[tuple(run[n]) for n in sorted(run)] for run in runs.values()]


class Schedule:
    def __init__(self, entries: list[Entry], slot_minutes: int, games_per_slot: int, seed: str, epoch: int = 0):
        if not entries:
            raise ValueError('the catalog is empty')
        self.length = slot_minutes * 60
        self.blocks = blocks(entries)
        self.episodes = sum(len(b) for b in self.blocks)
        self.per_slot = max(1, min(games_per_slot, self.episodes))
        self.epoch = epoch
        self.seed = seed
        self._pass = lru_cache(maxsize=8)(self._build_pass)

    def _order(self, cycle: int) -> list[int]:
        # a fresh shuffle of the blocks for every pass, reproducible from the seed
        rng = random.Random(hashlib.sha256(f'{self.seed}/{cycle}'.encode()).digest())
        order = list(range(len(self.blocks)))
        rng.shuffle(order)
        return order

    def _build_pass(self, cycle: int) -> tuple[Entry, ...]:
        order = self._order(cycle)
        # only the first two can swap, so the previous pass's unswapped order still ends where it really ends
        if len(order) > 2 and order[0] == self._order(cycle - 1)[-1]:
            order[0], order[1] = order[1], order[0]
        return tuple(takes[cycle % len(takes)] for b in order for takes in self.blocks[b])

    def slot(self, index: int) -> Slot:
        picks = []
        for k in range(self.per_slot):
            pos = index * self.per_slot + k
            picks.append(self._pass(pos // self.episodes)[pos % self.episodes])
        start = self.epoch + index * self.length
        return Slot(index, start, start + self.length, tuple(picks))

    def at(self, t: float) -> Slot:
        return self.slot(int((t - self.epoch) // self.length))

    def upcoming(self, t: float, count: int) -> list[Slot]:
        first = self.at(t).index
        return [self.slot(first + i) for i in range(count)]
